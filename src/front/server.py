from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from flask import Flask, jsonify, request, Response, stream_with_context
import requests
from threading import RLock

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

# Variables de configuration globales (clé/valeur en chaînes)
CONFIG_VARS: Dict[str, str] = {}
CONFIG_LOCK = RLock()


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


def command_generator(args: List[str]):
    """
    Générateur qui traite les commandes commençant par '/' et produit un flux NDJSON.
    """
    app.logger.info("Traitement de la commande slash: %r", args)
    try:
        cmd = (args[0].lower() if args else "")
        if cmd in ("help", ""):
            path = HERE / "help.txt"
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as e:
                text = f"Fichier d'aide introuvable ({path}): {e}"
            yield (json.dumps({"message": {"role": "assistant", "content": text}}, ensure_ascii=False) + "\n").encode("utf-8")
            yield (json.dumps({"done": True}) + "\n").encode("utf-8")
            return
        elif cmd == "show":
            # Affiche les variables de configuration enregistrées
            with CONFIG_LOCK:
                items = sorted(CONFIG_VARS.items())
            listing = ";".join(f"{k}={v}" for k, v in items)
            yield (json.dumps({"message": {"role": "assistant", "content": listing}}, ensure_ascii=False) + "\n").encode("utf-8")
            yield (json.dumps({"done": True}) + "\n").encode("utf-8")
            return
        elif cmd == "set":
            # Définition / suppression d'une variable de configuration
            name = args[1] if len(args) >= 2 else None
            value = args[2] if len(args) >= 3 else None
            if name:
                with CONFIG_LOCK:
                    if value is None or value == "":
                        CONFIG_VARS.pop(name, None)
                    else:
                        CONFIG_VARS[name] = value
            path = HERE / "setvar.txt"
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as e:
                text = f"Information de configuration introuvable ({path}): {e}"
            yield (json.dumps({"message": {"role": "assistant", "content": text}}, ensure_ascii=False) + "\n").encode("utf-8")
            yield (json.dumps({"done": True}) + "\n").encode("utf-8")
            return
        else:
            msg = f"Commande inconnue: {cmd}. Essayez /help."
            yield (json.dumps({"message": {"role": "assistant", "content": msg}}, ensure_ascii=False) + "\n").encode("utf-8")
            yield (json.dumps({"done": True}) + "\n").encode("utf-8")
            return
    except Exception as e:
        err = {"error": str(e), "done": True}
        yield (json.dumps(err, ensure_ascii=False) + "\n").encode("utf-8")


def command(args: List[str]) -> Response:
    """
    Traite les commandes commençant par '/'.
    Envoie un flux NDJSON compatible avec le front et termine la connexion.
    """
    return Response(stream_with_context(command_generator(args)), content_type="application/x-ndjson; charset=utf-8")

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

    # Commande slash: bypass Ollama et traiter via 'command'
    p = prompt.strip()
    if p.startswith("/"):
        args = p[1:].strip().split() if len(p) > 1 else []
        app.logger.info("Slash command received from %s: %s", request.remote_addr, args)
        cmd = (args[0].lower() if args else "")
        user_env = os.environ.get("USER", "") or os.environ.get("USERNAME", "")
        if cmd != "help" and user_env != "fenyo":
            app.logger.warning("Slash command denied for USER=%r from %s", user_env, request.remote_addr)
            def gen_denied():
                try:
                    path = HERE / "accessdenied.txt"
                    try:
                        text = path.read_text(encoding="utf-8")
                    except Exception as e:
                        text = f"Accès refusé. Fichier introuvable ({path}): {e}"
                    yield (json.dumps({"message": {"role": "assistant", "content": text}}, ensure_ascii=False) + "\n").encode("utf-8")
                    yield (json.dumps({"done": True}) + "\n").encode("utf-8")
                except Exception as e:
                    err = {"error": str(e), "done": True}
                    yield (json.dumps(err, ensure_ascii=False) + "\n").encode("utf-8")
            return Response(stream_with_context(gen_denied()), content_type="application/x-ndjson; charset=utf-8")

        # Préparer la liste de messages à renvoyer au front sans inclure le message slash courant
        client_messages: List[Dict[str, str]] = []
        try:
            for idx, m in enumerate(messages):
                if not (isinstance(m, dict) and m.get("role") in ("user", "assistant")):
                    continue
                c = m.get("content")
                if not isinstance(c, str) or c == "":
                    continue
                # Exclut le dernier message utilisateur s'il commence par '/'
                if idx == len(messages) - 1 and c.strip().startswith("/"):
                    continue
                client_messages.append({"role": m.get("role"), "content": c})
        except Exception:
            client_messages = []

        def gen_slash():
            # 1) Renvoyer au client la liste des messages conservés (sans le slash)
            try:
                yield (json.dumps({"messages": client_messages}, ensure_ascii=False) + "\n").encode("utf-8")
            except Exception:
                pass
            # 2) Puis streamer la réponse de la commande
            for chunk in command_generator(args):
                yield chunk

        return Response(stream_with_context(gen_slash()), content_type="application/x-ndjson; charset=utf-8")

    # Plus de gestion de 'context' transmis par le front (API /api/generate supprimée)

    # Si PROMPT=NONE, n'applique aucun template: on garde le message utilisateur tel quel.
    with CONFIG_LOCK:
        prompt_mode = CONFIG_VARS.get("PROMPT")
    if isinstance(prompt_mode, str) and prompt_mode.upper() == "NONE":
        print("[prompt template] PROMPT=NONE: using raw user message (no template)", flush=True)
    else:
        # Choisit le template selon la position du message utilisateur:
        # - 1er message utilisateur -> prompt-do-not-edit.txt (ou prompt-nofilter-do-not-edit.txt si FILTER=NONE)
        # - sinon -> prompt2-do-not-edit.txt (ou prompt2-nofilter-do-not-edit.txt si FILTER=NONE)
        try:
            is_first_user = len(user_msgs) <= 1
            with CONFIG_LOCK:
                filter_mode = CONFIG_VARS.get("FILTER")
            use_nofilter = isinstance(filter_mode, str) and filter_mode.upper() == "NONE"
            if is_first_user:
                tmpl_filename = "prompt-nofilter-do-not-edit.txt" if use_nofilter else "prompt-do-not-edit.txt"
            else:
                tmpl_filename = "prompt2-nofilter-do-not-edit.txt" if use_nofilter else "prompt2-do-not-edit.txt"
            tmpl_path = HERE / tmpl_filename
            template = tmpl_path.read_text(encoding="utf-8")
            prompt = template.replace("{REQUEST}", prompt)
            print(f"[prompt template] applied from {tmpl_path}", flush=True)
        except Exception as e:
            print(f"[prompt template] error: {e}; using raw prompt", flush=True)

    # Construire la liste de messages pour Ollama (API chat) et injecter le message système
    out_messages: List[Dict[str, str]] = []
    # Charger le contenu du fichier system.txt (avec variantes selon CONFIG_VARS['FUN'])
    system_text = ""
    try:
        # Déterminer le fichier système à utiliser en fonction de la variable FUN
        with CONFIG_LOCK:
            fun = CONFIG_VARS.get("FUN")
        sys_filename = "system.txt"
        if isinstance(fun, str):
            if fun.upper() == "DO":
                sys_filename = "system-DO.txt"
            elif fun.upper() == "SB":
                sys_filename = "system-SB.txt"

        system_path = HERE / sys_filename
        system_text = system_path.read_text(encoding="utf-8").strip()
        print(f"[system prompt] using {system_path}", flush=True)
    except Exception as e:
        print(f"[system prompt] error reading {sys_filename if 'sys_filename' in locals() else 'system.txt'}: {e}; proceeding without system message", flush=True)
        # Repli sur system.txt si une variante échoue
        try:
            if 'sys_filename' in locals() and sys_filename != "system.txt":
                system_path = HERE / "system.txt"
                system_text = system_path.read_text(encoding="utf-8").strip()
                print(f"[system prompt] fallback to {system_path}", flush=True)
        except Exception as e2:
            print(f"[system prompt] fallback error: {e2}", flush=True)
    if system_text:
        out_messages.append({"role": "system", "content": system_text})
    # Partir des messages fournis par le client s'ils existent
    base_messages: List[Dict[str, Any]] = []
    if isinstance(messages, list):
        # Conserver l'ordre de création, et ne transmettre que les messages valides non vides
        base_messages = []
        for m in messages:
            if not (isinstance(m, dict) and "role" in m and "content" in m):
                continue
            role = m.get("role")
            content = m.get("content")
            if role not in ("user", "assistant"):
                continue
            if not isinstance(content, str) or content == "":
                continue
            base_messages.append({"role": role, "content": content})
    if base_messages:
        # Remplacer le contenu du dernier message utilisateur par la version templatisée (prompt)
        replaced = False
        for i in range(len(base_messages) - 1, -1, -1):
            m = base_messages[i]
            if m.get("role") == "user":
                base_messages = base_messages.copy()
                m = dict(m)
                m["content"] = prompt
                base_messages[i] = m
                replaced = True
                break
        if not replaced:
            base_messages.append({"role": "user", "content": prompt})
        out_messages.extend(base_messages)
    else:
        out_messages.append({"role": "user", "content": prompt})

    model = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
    ollama_url = os.getenv("OLLAMA_URL", "http://192.168.0.21:11434/api/chat")

    app.logger.info("Streaming from Ollama %s with model=%s, in_messages=%d, out_messages=%d", ollama_url, model, len(messages), len(out_messages))

    def stream_ollama():
        try:
            # Log de la requête sortante vers Ollama (sur stdout)
            user_preview = ""
            try:
                for m in reversed(out_messages):
                    if isinstance(m, dict) and m.get("role") == "user":
                        c = m.get("content")
                        if isinstance(c, str):
                            user_preview = c[:200]
                            break
            except Exception:
                pass
            print(
                f"[ollama request] POST {ollama_url} model={model} "
                f"messages={len(out_messages)} "
                f"user_preview={user_preview!r}",
                flush=True,
            )

            payload = {"model": model, "messages": out_messages, "stream": True}
            # Taille de contexte explicite pour Ollama
            payload["options"] = {"num_ctx": 131072}
            payload_json = json.dumps(payload, ensure_ascii=False)
            def _sh_single_quote_escape(s: str) -> str:
                return s.replace("'", "'\"'\"'")
            curl_cmd = f"curl -N -H 'Content-Type: application/json' -X POST '{ollama_url}' -d '{_sh_single_quote_escape(payload_json)}'"
            print(f"[ollama curl] {curl_cmd}", flush=True)

            # Avant de contacter Ollama, envoyer au client la liste ordonnée des messages
            # (uniquement les rôles user/assistant) utilisés pour cette requête.
            try:
                client_messages = [
                    m for m in out_messages
                    if isinstance(m, dict) and m.get("role") in ("user", "assistant")
                ]
                yield (json.dumps({"messages": client_messages}, ensure_ascii=False) + "\n").encode("utf-8")
            except Exception as _e:
                # En cas d'erreur, on continue sans bloquer le flux
                pass

            headers = {"Content-Type": "application/json; charset=utf-8"}
            with requests.post(
                ollama_url,
                data=payload_json.encode("utf-8"),
                headers=headers,
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
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
