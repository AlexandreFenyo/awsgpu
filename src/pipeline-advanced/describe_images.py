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
    "l'inclure dans un chunk d'un système d'IA générative de type RAG. Propose donc une version adaptée à un chunk d’ingestion, avec les différentes informations contenues dans cette image, en explicitant par exemple les liens entre les différentes entités présentes dans cette image."
    "Ta réponse est encadrée des tags <IMAGE DESCRIPTION START> et <IMAGE DESCRIPTION END>, en voici un exemple : <IMAGE DESCRIPTION START>tu mets ici la description de l'image<IMAGE DESCRIPTION END>. N'indique pas qu'il s'agit d'une description pour RAG, mets simplement la description. S'il y a des fautes d'orthographe dans ce qui est extrait de l'image, corrige-les. Ne donne pas d'indication sur les couleurs des entités présentes."
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


def convert_markdown_images(md_text: str, client: "OpenAI") -> str:
    """
    Remplace toutes les images data URL par la description retournée par le modèle.
    """

    cache: Dict[str, str] = {}

    def _repl(match: re.Match) -> str:
        data_url = match.group("url")
        if data_url in cache:
            return cache[data_url]
        description = describe_image_with_openai(client, data_url)
        cache[data_url] = description
        return description

    return DATA_IMAGE_MD_PATTERN.sub(_repl, md_text)


def output_path_for(input_path: str) -> str:
    base, ext = os.path.splitext(input_path)
    return f"{base}-converted.md"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Décris les images data URL dans un Markdown via OpenAI et les remplace par du texte."
    )
    parser.add_argument("markdown_file", help="Chemin du fichier Markdown en entrée")
    args = parser.parse_args(argv)

    in_path = args.markdown_file
    if not os.path.isfile(in_path):
        print(f"Erreur: fichier introuvable: {in_path}", file=sys.stderr)
        return 2

    with open(in_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    client = _build_openai_client()

    converted = convert_markdown_images(md_text, client)

    out_path = output_path_for(in_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(converted)

    # Message succinct sur stderr pour ne pas polluer la sortie
    print(f"Conversion terminée. Fichier écrit: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


