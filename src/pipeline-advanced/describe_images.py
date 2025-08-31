#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script CLI:
- Prend un chemin de fichier Markdown en paramètre.
- Remplace chaque image inline encodée en data URL (ex: ![](data:image/x-emf;base64,AAA...))
  par une description textuelle en Markdown générée par le modèle OpenAI gpt-5-nano.
- Utilise la clé d'API stockée dans la variable d'environnement OPENAIAPIKEY.
- Écrit la sortie dans un fichier suffixé par "-converted.md" à côté du fichier d'entrée.
"""

import argparse
import base64
import io
import os
import re
import sys
import shutil
import subprocess
import tempfile
import json
import hashlib
from urllib import request as _urlrequest, error as _urlerror
from typing import Dict

try:
    # SDK OpenAI officiel (v1.x)
    from openai import OpenAI
except Exception:
    OpenAI = None  # gère l'absence de dépendance plus bas

# Pillow est optionnel mais recommandé pour la conversion vers PNG.
try:
    from PIL import Image
except Exception:
    Image = None

PROMPT_FR = (
    "Voici une image, fournis-moi un texte en Markdown qui décrit son contenu pour pouvoir "
    "l'inclure dans un chunk d'un système d'IA générative de type RAG. Propose donc une version adaptée à un chunk d'ingestion, avec les différentes informations contenues dans cette image, en explicitant par exemple les liens entre les différentes entités présentes dans cette image."
    "N'indique pas qu'il s'agit d'une description pour RAG, mets simplement la description. S'il y a des fautes d'orthographe dans ce qui est extrait de l'image, corrige-les. Ne donne pas d'indication sur les couleurs des entités présentes."
#   "Ta réponse est encadrée des tags <IMAGE DESCRIPTION START> et <IMAGE DESCRIPTION END>, en voici un exemple : <IMAGE DESCRIPTION START>tu mets ici la description de l'image<IMAGE DESCRIPTION END>. N'indique pas qu'il s'agit d'une description pour RAG, mets simplement la description. S'il y a des fautes d'orthographe dans ce qui est extrait de l'image, corrige-les. Ne donne pas d'indication sur les couleurs des entités présentes."
)

PROMPT_OLLAMA_FR = (
    "Tu es un expert en architectures informatiques. Analyse attentivement l'image fournie (schéma technique, ou réseau, ou de composants informatiques, ou de composants de sécurité, ou encore de concepts informatiques divers). Fais les tâches suivantes : "
    "Résumé global en 2-3 phrases : fonction principale du schéma. "
    "Composants détectés : pour chaque élément identifié, donne — nom/label exact tel qu'écrit sur l'image (entre guillemets), "
     "type (ex. routeur, switch, firewall, serveur, VM, client, NAT, base de données), rôle attendu, adresse IP et ports si visibles. "
    "Connexions et flux : liste chaque liaison en précisant origine → destination, protocole/port affiché (ou estimé), et direction du flux. "
    "Séquence de fonctionnement : décris en 6-10 étapes numérotées le flux principal de données ou la logique d'acheminement. "
    "Suggestions d'amélioration/pratiques recommandées (top 3 prioritaires). "
    "Éléments illisibles ou hypothèses : liste tout texte ou symbole que tu ne peux pas lire clairement et explique les hypothèses que tu fais pour l'analyse. "
    "Ne fais pas d'inventions non justifiées : si tu n'es pas sûr d'un élément, indique explicitement 'incertain' et donne les raisons. "
    "Fournis la réponse en texte clair."
)

# Correspond aux data URLs pour images base64, ex:
# ![](data:image/x-emf;base64,AQAAA...==)
DATA_IMAGE_MD_PATTERN = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<url>data:image\/[a-zA-Z0-9.+-]+;base64,[^)]+)\)"
)


def _build_openai_client() -> "OpenAI":
    api_key = os.getenv("OPENAIAPIKEY")
    if not api_key:
        print(
            "Erreur: la variable d'environnement OPENAIAPIKEY est absente.",
            file=sys.stderr,
        )
        sys.exit(1)
    if OpenAI is None:
        print(
            "Erreur: le package 'openai' n'est pas installé. "
            "Installez-le avec: pip install openai",
            file=sys.stderr,
        )
        sys.exit(1)
    return OpenAI(api_key=api_key)


def _convert_emf_to_png_bytes(emf_bytes):
    """
    Tente de convertir des octets EMF vers PNG en utilisant des outils externes si disponibles.
    Essaie successivement: Inkscape, ImageMagick (magick/convert).
    Retourne les octets PNG en cas de succès, sinon None.
    """
    try:
        import shutil as _shutil
        import subprocess as _subprocess
        import tempfile as _tempfile
        import os as _os

        with _tempfile.TemporaryDirectory() as tmpdir:
            in_path = _os.path.join(tmpdir, "input.emf")
            out_path = _os.path.join(tmpdir, "output.png")
            with open(in_path, "wb") as f:
                f.write(emf_bytes)

            # 1) Inkscape
            inkscape = _shutil.which("inkscape")
            if inkscape:
                try:
                    _subprocess.run(
                        [inkscape, "--export-type=png", f"--export-filename={out_path}", in_path],
                        check=True,
                        stdout=_subprocess.DEVNULL,
                        stderr=_subprocess.DEVNULL,
                    )
                    if _os.path.isfile(out_path):
                        with open(out_path, "rb") as f:
                            return f.read()
                except Exception:
                    pass

            # 2) ImageMagick (magick or convert)
            for cmd in ("magick", "convert"):
                bin_path = _shutil.which(cmd)
                if not bin_path:
                    continue
                try:
                    _subprocess.run(
                        [bin_path, in_path, out_path],
                        check=True,
                        stdout=_subprocess.DEVNULL,
                        stderr=_subprocess.DEVNULL,
                    )
                    if _os.path.isfile(out_path):
                        with open(out_path, "rb") as f:
                            return f.read()
                except Exception:
                    continue
    except Exception:
        pass
    return None


def data_url_to_png_data_url(data_url: str) -> str:
    """
    Convertit une data URL d'image vers une data URL PNG si possible.
    Si la conversion échoue ou que Pillow n'est pas disponible, retourne la data URL d'origine.
    """
    try:
        if not data_url.startswith("data:"):
            return data_url
        m = re.match(r"^data:(?P<mime>[^;]+);base64,(?P<b64>.+)$", data_url, re.DOTALL)
        if not m:
            return data_url
        mime = m.group("mime").lower()
        b64 = m.group("b64")
        # Déjà en PNG
        if mime == "image/png":
            return data_url
        raw = base64.b64decode(b64, validate=False)

        # Cas spécial EMF: tenter une conversion via outils externes
        if mime in ("image/x-emf", "image/emf"):
            png_bytes = _convert_emf_to_png_bytes(raw)
            if png_bytes:
                png_b64 = base64.b64encode(png_bytes).decode("ascii")
                return f"data:image/png;base64,{png_b64}"
            # Échec de conversion EMF -> PNG, on rend l'image d'origine
            return data_url

        # Autres formats: tenter via Pillow
        if Image is None:
            return data_url
        with Image.open(io.BytesIO(raw)) as im:
            # Gérer la transparence et les palettes
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                im = im.convert("RGBA")
            else:
                im = im.convert("RGB")
            out = io.BytesIO()
            im.save(out, format="PNG", optimize=True)
            png_b64 = base64.b64encode(out.getvalue()).decode("ascii")
            return f"data:image/png;base64,{png_b64}"
    except Exception:
        # En cas d'échec, on garde l'image d'origine
        return data_url
    return data_url

def _extract_b64(data_url: str):
    m = re.match(r"^data:(?P<mime>[^;]+);base64,(?P<b64>.+)$", data_url, re.DOTALL)
    if not m:
        return None
    return m.group("b64")

def _cache_file_path_for_image(input_path: str, data_url: str):
    b64 = _extract_b64(data_url)
    if not b64:
        return None
    sha1_hex = hashlib.sha1(b64.encode("ascii")).hexdigest()
    dir_name = os.path.dirname(input_path) or "."
    base_name = os.path.basename(input_path)
    return os.path.join(dir_name, f"{base_name}.cache-{sha1_hex}.txt")

def describe_image_with_openai(client: "OpenAI", data_url: str) -> str:
    """
    Envoie l'image (data URL) au modèle et retourne une description en Markdown.
    En cas d'échec, retourne un commentaire HTML contenant l'erreur.
    """
    png_data_url = data_url_to_png_data_url(data_url)
    try:
        resp = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {
                    "role": "system",
                    "content": "Tu es un assistant qui décrit précisément des images en Markdown.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT_FR},
                        {"type": "image_url", "image_url": {"url": png_data_url}},
                    ],
                },
            ],
        )
        content = resp.choices[0].message.content if resp.choices else ""
        if not content or not content.strip():
            return "<!-- Réponse vide du modèle pour cette image -->"
        return content.strip()
    except Exception as e:
        return f"<!-- Erreur lors de la description de l'image: {e} -->"


def describe_image_with_ollama(data_url: str) -> str:
    """
    Utilise Ollama en local (modèle gpt-oss:20b) pour décrire une image.
    Attend que l'API Ollama soit disponible sur http://localhost:11434.
    """
    try:
        png_data_url = data_url_to_png_data_url(data_url)
        m = re.match(r"^data:image\/png;base64,(?P<b64>.+)$", png_data_url, re.DOTALL)
        if not m:
            return "<!-- Impossible d'extraire l'image PNG pour Ollama -->"
        b64 = m.group("b64")
        payload = {
            "model": "Qwen2.5vl:32b",
            # "model": "Qwen2.5vl:3b",
            # "model": "Qwen2.5vl:72b",
            # "prompt": PROMPT_OLLAMA_FR,
            "prompt": PROMPT_FR,
            "images": [b64],
            "stream": False,
        }

        ollama_host = os.environ.get("OLLAMA_HOST")
        if ollama_host:
            host = ollama_host
        else:
            host = "172.22.64.1"
    
        req = _urlrequest.Request(
            "http://" + host + ":11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _urlrequest.urlopen(req, timeout=1200) as resp:
            body = resp.read()
        data = json.loads(body.decode("utf-8"))
        content = data.get("response", "")
        if not content or not content.strip():
            return "<!-- Réponse vide du modèle (Ollama) pour cette image -->"
        return content.strip()
    except _urlerror.URLError as e:
        return f"<!-- Erreur de connexion à Ollama: {e} -->"
    except Exception as e:
        return f"<!-- Erreur lors de la description via Ollama: {e} -->"


def convert_markdown_images(md_text: str, client: "OpenAI", input_path: str, use_local: bool = False, text_only: bool = False) -> str:
    """
    Remplace toutes les images data URL par la description retournée par le modèle.
    """

    cache: Dict[str, str] = {}

    def _repl(match: re.Match) -> str:
        if text_only:
            return "<IMAGE DESCRIPTION START>pas de description<IMAGE DESCRIPTION END>"
        data_url = match.group("url")
        if data_url in cache:
            return cache[data_url]

        # Cache disque basé sur le SHA-1 du base64 d'origine
        cache_file = _cache_file_path_for_image(input_path, data_url)
        if cache_file and os.path.isfile(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as cf:
                    cached_text = cf.read()
                cache[data_url] = cached_text
                return cached_text
            except Exception:
                pass

        # Pas de cache: on interroge le LLM
        print("llm launched")
        description = describe_image_with_ollama(data_url) if use_local else describe_image_with_openai(client, data_url)
        description = "<IMAGE DESCRIPTION START>" + description + "<IMAGE DESCRIPTION END>"

        # Écrit dans le cache disque
        if cache_file:
            try:
                with open(cache_file, "w", encoding="utf-8") as cf:
                    cf.write(description)
            except Exception:
                pass

        cache[data_url] = description
        return description

    return DATA_IMAGE_MD_PATTERN.sub(_repl, md_text)


def output_path_for(input_path: str) -> str:
    base, ext = os.path.splitext(input_path)
    return f"{base}.md.converted.md"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Décris les images data URL dans un Markdown via OpenAI et les remplace par du texte."
    )
    parser.add_argument("markdown_file", help="Chemin du fichier Markdown en entrée")
    parser.add_argument("-l", "--local", action="store_true", help="Utiliser Ollama local (modèle gpt-oss:20b) au lieu d'OpenAI")
    parser.add_argument("-t", "--text", action="store_true", help="Ne pas invoquer de LLM; insérer 'pas de description' pour chaque image")
    args = parser.parse_args(argv)

    in_path = args.markdown_file
    if not os.path.isfile(in_path):
        print(f"Erreur: fichier introuvable: {in_path}", file=sys.stderr)
        return 2

    with open(in_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    client = None
    if not args.local and not args.text:
        client = _build_openai_client()

    converted = convert_markdown_images(md_text, client, in_path, use_local=args.local, text_only=args.text)

    out_path = output_path_for(in_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(converted)

    # Message succinct sur stderr pour ne pas polluer la sortie
    print(f"Conversion terminée. Fichier écrit: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
