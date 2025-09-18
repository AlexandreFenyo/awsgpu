#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script CLI pour interagir avec un serveur Ollama via /api/chat, en proposant un outil "subquery".

Fonctionnalités:
- Prend en paramètres: adresse IP (ou URL) du serveur Ollama, nom du modèle LLM, et un texte utilisateur.
- Envoie une requête POST à /api/chat avec:
  - model: <nom du modèle>
  - options: { "num_ctx": 131072 }
  - messages: message utilisateur (role=user)
  - tools: un outil "subquery" disponible via l'API de tool-calling
- Gère l'appel d'outil: si le modèle appelle "subquery", exécute la fonction Python subquery et renvoie
  le résultat au modèle via un message de rôle "tool".

Dépendances:
- requests (pip install requests)
"""

from __future__ import annotations

import argparse
import json
import sys
import shlex
from typing import Any, Dict, List, Tuple

try:
    import requests
except ImportError as exc:  # pragma: no cover
    sys.stderr.write("Le module 'requests' est requis. Installez-le avec:\n  python -m pip install requests\n")
    raise


def subquery(text: str) -> str:
    """
    Implémentation locale de l'outil 'subquery':
    - prend une chaîne de caractères
    - renvoie la même chaîne transformée en MAJUSCULES
    """
    return text.upper()


def _build_base_url(server: str) -> str:
    """
    Accepte:
    - une IP/hostname (ex: 127.0.0.1 ou my-host) -> http://<server>:11434
    - une URL complète (http://... ou https://...) -> utilisée telle quelle
    """
    server = server.strip().rstrip("/")
    if server.startswith("http://") or server.startswith("https://"):
        return server
    return f"http://{server}:11434"


def _ollama_tools_definition() -> List[Dict[str, Any]]:
    """
    Définition de l'outil 'subquery' pour l'API Ollama (schéma type OpenAI).
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "subquery",
                "description": "Transforme le texte en majuscules et le renvoie tel quel.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Le texte à transformer en majuscules.",
                        }
                    },
                    "required": ["text"],
                },
            },
        }
    ]

def _to_curl(url: str, payload: Dict[str, Any]) -> str:
    """
    Construit une commande curl équivalente à la requête HTTP.
    """
    headers = [
        ("Content-Type", "application/json"),
        ("Accept", "application/json"),
    ]
    parts = ["curl", "-sS", "-X", "POST", shlex.quote(url)]
    for k, v in headers:
        parts.extend(["-H", shlex.quote(f"{k}: {v}")])
    body = json.dumps(payload, ensure_ascii=False)
    parts.extend(["--data", shlex.quote(body)])
    return " ".join(parts)


def _post_chat(base_url: str, payload: Dict[str, Any], timeout: float = 120.0) -> Dict[str, Any]:
    url = f"{base_url}/api/chat"
    curl_cmd = _to_curl(url, payload)
    sys.stderr.write(curl_cmd + "\n")
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        sys.stderr.write(resp.text + "\n")
        raise
    sys.stderr.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return data


def _extract_tool_calls(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extrait de manière robuste la liste des tool_calls depuis le message assistant.
    Les implémentations renvoient souvent:
      message["tool_calls"] = [
        { "id": "...", "type": "function", "function": { "name": "...", "arguments": "<json|string>" } }
      ]
    """
    if not isinstance(message, dict):
        return []
    calls = message.get("tool_calls")
    if isinstance(calls, list):
        return calls
    # Tolérance pour quelques variantes éventuelles
    if isinstance(message.get("tool_call"), list):
        return message["tool_call"]
    return []


def _parse_function_call_arguments(raw_args: Any) -> Dict[str, Any]:
    """
    raw_args peut être un dict ou une chaîne JSON. On tente de parser proprement.
    """
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except Exception:
            # En dernier recours, on encapsule tel quel
            return {"text": raw_args}
    return {}


def run_chat(server: str, model: str, user_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Exécute un échange avec le modèle en gérant un éventuel appel d'outil 'subquery'.
    Retourne la dernière réponse assistant et l'historique des messages.
    """
    base_url = _build_base_url(server)
    tools = _ollama_tools_definition()
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": user_text}
    ]

    # On limite le nombre de boucles pour éviter des cycles infinis d'outils.
    for _ in range(5):
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "options": {"num_ctx": 131072},
            "stream": False,
        }
        data = _post_chat(base_url, payload)
        assistant_msg = data.get("message", {}) if isinstance(data, dict) else {}
        content = assistant_msg.get("content", "")

        tool_calls = _extract_tool_calls(assistant_msg)
        if tool_calls:
            # On ajoute le message assistant contenant la demande d'outil
            messages.append({
                "role": "assistant",
                "content": content or "",
                "tool_calls": tool_calls,
            })

            # Exécuter tous les appels d'outils, puis renvoyer leurs résultats
            for call in tool_calls:
                fn = (call or {}).get("function") or {}
                name = fn.get("name")
                args = _parse_function_call_arguments(fn.get("arguments"))

                if name == "subquery":
                    text_arg = str(args.get("text", ""))
                    result = subquery(text_arg)
                else:
                    # Outil non géré localement
                    result = f"Erreur: outil non supporté '{name}'"

                tool_msg: Dict[str, Any] = {
                    "role": "tool",
                    "name": name or "unknown",
                    "content": result,
                }
                # Si un id d'appel est présent, on le renvoie pour rattacher la réponse (interop OpenAI-like)
                call_id = call.get("id")
                if isinstance(call_id, str) and call_id:
                    tool_msg["tool_call_id"] = call_id

                messages.append(tool_msg)

            # Boucle et redemande au modèle après avoir fourni les résultats d'outils
            continue

        # Pas d'outil demandé: on a la réponse finale
        if content:
            messages.append({"role": "assistant", "content": content})
            return content, messages

        # Si le message n'a pas de contenu ni d'outils, on s'arrête proprement
        break

    # Si on sort par le haut de la boucle sans contenu final
    return "", messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Script pour interroger un serveur Ollama via /api/chat avec un outil 'subquery'."
    )
    parser.add_argument("server", help="Adresse IP ou URL du serveur Ollama (ex: 127.0.0.1 ou http://127.0.0.1:11434)")
    parser.add_argument("model", help="Nom du modèle (ex: llama3)")
    parser.add_argument("text", help="Texte utilisateur à envoyer au modèle")
    args = parser.parse_args(argv)

    try:
        reply, _history = run_chat(args.server, args.model, args.text)
    except requests.HTTPError as e:
        sys.stderr.write(f"Erreur HTTP: {e}\n")
        return 1
    except requests.RequestException as e:
        sys.stderr.write(f"Erreur de connexion: {e}\n")
        return 1
    except Exception as e:  # pragma: no cover
        sys.stderr.write(f"Erreur inattendue: {e}\n")
        return 1

    if reply:
        print(reply)
        return 0

    sys.stderr.write("Aucune réponse de l'assistant.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
