import os
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

app = FastAPI(title="RPG Mestre")

BASE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

STATE = {
    "scene": "A campanha ainda não começou.",
    "public_history": [],
    "private": {
        "luiz": [],
        "amigo": []
    }
}

client = (
    OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if os.getenv("OPENAI_API_KEY")
    else None
)

MODEL = os.getenv("OPENAI_MODEL", "gpt-6.1-sol")


class Action(BaseModel):
    player: str
    text: str


@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE / "static" / "index.html").read_text(
        encoding="utf-8"
    )


@app.get("/api/state")
def state():
    return {
        "scene": STATE["scene"],
        "public_history": STATE["public_history"][-30:]
    }


@app.post("/api/action")
def action(req: Action):

    player = req.player.strip().lower()

    if player not in ("luiz", "amigo"):
        raise HTTPException(
            400,
            "player deve ser 'luiz' ou 'amigo'"
        )

    text = req.text.strip()

    if not text:
        raise HTTPException(
            400,
            "Ação vazia"
        )

    STATE["private"][player].append({
        "id": str(uuid.uuid4()),
        "text": text
    })

    other = (
        "amigo"
        if player == "luiz"
        else "luiz"
    )

    if not STATE["private"][other]:

        return {
            "status": "waiting",
            "message": "Ação recebida. Aguardando o outro jogador."
        }

    luiz_action = STATE["private"]["luiz"][-1]["text"]
    amigo_action = STATE["private"]["amigo"][-1]["text"]

    prompt = f"""
Você é o Mestre de uma campanha de RPG para dois jogadores.

Ação de Luiz:
{luiz_action}

Ação do Amigo:
{amigo_action}

Cena atual:
{STATE["scene"]}

Histórico recente:
{json.dumps(
    STATE["public_history"][-10:],
    ensure_ascii=False
)}

Resolva o turno de maneira justa e criativa.

Responda somente com JSON válido contendo:

scene:
nova cena pública.

public:
o que ambos os jogadores podem saber.

luiz_private:
informação que somente Luiz deve receber.

amigo_private:
informação que somente o Amigo deve receber.

Não revele informações privadas de um personagem ao outro.
"""

    if not client:
        raise HTTPException(
            500,
            "OPENAI_API_KEY não configurada."
        )

    response = client.responses.create(
        model=MODEL,
        input=prompt
    )

    raw = response.output_text

    start = raw.find("{")
    end = raw.rfind("}")

    data = json.loads(
        raw[start:end + 1]
    )

    STATE["scene"] = data["scene"]

    STATE["public_history"].append(
        data["public"]
    )

    STATE["private"]["luiz"].clear()
    STATE["private"]["amigo"].clear()

    return {
        "status": "resolved",
        "scene": data["scene"],
        "public": data["public"],
        "private": {
            "luiz": data.get(
                "luiz_private",
                ""
            ),
            "amigo": data.get(
                "amigo_private",
                ""
            )
        }
  }
