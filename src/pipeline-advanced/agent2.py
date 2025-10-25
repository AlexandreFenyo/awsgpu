#!/usr/bin/env python3

from __future__ import annotations

from typing import List
from pydantic import BaseModel
import instructor
from openai import OpenAI
from pathlib import Path

class StringList(BaseModel):
    """Un simple conteneur pour une liste de chaînes."""
    items: List[str]


def build_client() -> OpenAI:
    """
    Construit un client OpenAI compatible Ollama, patché par instructor
    pour forcer des sorties structurées.
    """
    base_client = OpenAI(
        base_url="http://192.168.0.21:11434/v1",
        api_key="ollama",  # Valeur factice pour compat OpenAI SDK
    )
    # JSON_SCHEMA est robuste pour demander strictement du JSON
    return instructor.from_openai(base_client, mode=instructor.Mode.JSON_SCHEMA)


def ask_question(question: str, model: str = "gpt-oss:20b") -> List[str]:
    """
    Pose la question au modèle et récupère une liste de chaînes.
    """
    client = build_client()

    # Le client patché par instructor renvoie directement un objet Pydantic validé
    result: StringList = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es un assistant concis. "
                    "Réponds uniquement avec les données demandées."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Retourne STRICTEMENT un tableau JSON de chaînes (pas de texte autour). "
                    "Question: " + question
                ),
            },
        ],
        response_model=StringList,
        temperature=0.2,
    )
    return result.items


# Variable question demandée
#question = "Donne 5 capitales européennes."
# /tmp/res est créé via des commandes décrites dans index.json.AI
question = Path("/tmp/res").read_text(encoding='utf-8')

if __name__ == "__main__":
    import json
    import sys

    q = question
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])

    items = ask_question(q)
    # Affiche le tableau en JSON pour un piping facile
    print(json.dumps(items, ensure_ascii=False))
