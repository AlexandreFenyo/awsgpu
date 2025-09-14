from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from flask import Flask, jsonify, request, Response, stream_with_context
import requests

# Répertoire statique pour servir chat.html / chat.css / chat.js
HERE = Path(__file__).resolve().parent
app = Flask(
    __name__,
    static_folder=str(HERE),   # permet de servir chat.css et chat.js
    static_url_path=""         # accessibles à la racine: /chat.css, /chat.js
)

# Réponse fixe renvoyée au front pour test de communication
FIXED_REPLY = (
    "Réponse de test depuis le serveur Flask. "
    "La communication front ↔ backend fonctionne."
)


@app.after_request
def add_cors_headers(resp):
    """
    Ajoute des en-têtes CORS simples pour permettre des tests locaux éventuels.
    """
    origin = request.headers.get("Origin", "*")
    resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Vary"] = "Origin"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.route("/")
def index():
    """
    Sert la page du ChatBot pour simplifier les tests:
    http://localhost:<port>/
    """
    return app.send_static_file("chat.html")


@app.route("/api/ping", methods=["GET"])
def ping():
    """
    Endpoint de santé simple.
    """
    app.logger.info("GET /api/ping from %s", request.remote_addr)
    return jsonify({"pong": True})

@app.route("/api/env", methods=["GET"])
def env_vars():
    """
    Renvoie les variables d'environnement sous forme de tableau JSON:
    [
      {"name": "VAR", "value": "..."},
      ...
    ]

    Attention: expose potentiellement des informations sensibles. À protéger en production.
    """
    items = [{"name": k, "value": v} for k, v in sorted(os.environ.items())]
    app.logger.info("GET /api/env from %s -> %d items", request.remote_addr, len(items))
    return jsonify(items)


@app.route("/api/user", methods=["GET"])
def user_env():
    """
    Renvoie en JSON la valeur de la variable d'environnement USER.
    Sur certains systèmes (ex: Windows), 'USER' peut être absent; on essaie 'USERNAME'.
    """
    user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    app.logger.info("GET /api/user from %s -> USER=%r", request.remote_addr, user)
    return jsonify({"USER": user})


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat():
    """
    Endpoint principal attendu par le front (POST /api/chat).
    - Reçoit l'historique { messages: [{role, content}, ...] }
    - Construit un prompt (dernier message utilisateur)
    - Invoque Ollama en streaming et propage les lignes NDJSON telles quelles
    """
    if request.method == "OPTIONS":
        # Réponse au preflight CORS
        return ("", 204)

    # Récupère JSON si présent, sinon texte brut
    data: Optional[Union[Dict[str, Any], List[Any]]] = request.get_json(silent=True)
    body_text: Optional[str] = None
    if data is None:
        try:
            body_text = request.get_data(as_text=True)
        except Exception:
            body_text = None

    # Logging de la requête
    app.logger.info(
        "POST /api/chat from %s | content-type=%s | json=%s | text-bytes=%s",
        request.remote_addr,
        request.headers.get("Content-Type"),
        "yes" if data is not None else "no",
        len(body_text.encode("utf-8")) if isinstance(body_text, str) else 0,
    )

    # Construit le prompt (dernier message utilisateur)
    messages = []
    if isinstance(data, dict):
        msgs = data.get("messages")
        if isinstance(msgs, list):
            messages = msgs
    user_msgs = []
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                user_msgs.append(c)
    prompt = user_msgs[-1] if user_msgs else (body_text or "")
    if not isinstance(prompt, str):
        prompt = str(prompt)

    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    ollama_url = os.getenv("OLLAMA_URL", "http://192.168.0.21:11434/api/generate")

    app.logger.info("Streaming from Ollama %s with model=%s, prompt_len=%d", ollama_url, model, len(prompt))

    def stream_ollama():
        try:
            # Log de la requête sortante vers Ollama (sur stdout)
            print(
                f"[ollama request] POST {ollama_url} model={model} "
                f"prompt_len={len(prompt)} prompt_preview={prompt[:200]!r}",
                flush=True,
            )

            payload = {"model": model, "prompt": prompt, "stream": True}
            payload_json = json.dumps(payload, ensure_ascii=False)
            def _sh_single_quote_escape(s: str) -> str:
                return s.replace("'", "'\"'\"'")
            curl_cmd = f"curl -N -H 'Content-Type: application/json' -X POST '{ollama_url}' -d '{_sh_single_quote_escape(payload_json)}'"
            print(f"[ollama curl] {curl_cmd}", flush=True)
            with requests.post(
                ollama_url,
                json=payload,
                stream=True,
                timeout=(5, 600),
            ) as r:
                # Log du statut HTTP reçu
                print(f"[ollama response] HTTP {r.status_code}", flush=True)
                r.raise_for_status()
                for line in r.iter_lines(chunk_size=8192, decode_unicode=False):
                    if not line:
                        continue
                    # Log chaque ligne NDJSON de la réponse
                    try:
                        _line_preview = line.decode("utf-8", errors="replace")
                    except Exception:
                        _line_preview = str(line)
                    print(f"[ollama response line] {_line_preview}", flush=True)
                    # Renvoie chaque ligne NDJSON telle quelle vers le client, suivie d'un \n
                    yield line + b"\n"
        except Exception as e:
            # Log de l'erreur (sur stdout)
            print(f"[ollama error] {e}", flush=True)
            # En cas d'erreur, renvoyer une ligne JSON signalant l'erreur + un done:true pour fermer proprement côté front
            err = {"error": str(e), "done": True}
            yield (json.dumps(err) + "\n").encode("utf-8")

    return Response(stream_with_context(stream_ollama()), content_type="application/x-ndjson; charset=utf-8")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Serveur Flask pour le front ChatBot (API de test)."
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=int(os.getenv("PORT", 8111)),
        help="Port d'écoute (défaut: 8111, ou variable d'env PORT).",
    )
    parser.add_argument(
        "-b",
        "--host",
        "--bind",
        dest="host",
        default=os.getenv("HOST", "0.0.0.0"),
        help='Adresse d\'écoute (défaut: "0.0.0.0", utiliser "0.0.0.0" pour toutes les interfaces).',
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Active le niveau de logs DEBUG.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app.logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    app.logger.info("Démarrage du serveur sur http://%s:%s", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
