from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from flask import Flask, jsonify, request

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


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat():
    """
    Endpoint principal attendu par le front (POST /api/chat).
    - Logue la requête reçue
    - Retourne une réponse JSON contenant un champ 'reply' fixe
    - Renvoie aussi un écho minimal du contenu reçu pour debug
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

    # Prépare un petit écho utile au debug
    echo: Dict[str, Any] = {
        "method": request.method,
        "path": request.path,
        "content_type": request.headers.get("Content-Type"),
        "received": data if data is not None else body_text,
    }

    # Réponse fixe + écho
    return jsonify(
        {
            "ok": True,
            "reply": FIXED_REPLY,
            "echo": echo,
        }
    )


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
