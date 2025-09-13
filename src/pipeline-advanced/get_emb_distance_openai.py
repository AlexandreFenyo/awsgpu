#!/usr/bin/env python3
"""
Calcule la distance entre les embeddings de deux chaînes de caractères en utilisant OpenAI.

- Utilise les modèles 'text-embedding-3-small' ou 'text-embedding-3-large'.
- Aligne la métrique sur celle utilisée par search_chunks.py / Weaviate (cosine distance),
  c.-à-d. : distance = 1 - cosine_similarity.
- La clé d'API OpenAI est lue depuis la variable d'environnement OPENAIAPIKEY
  (avec repli sur OPENAI_API_KEY si non définie).

Usage:
  ./src/pipeline-advanced/get_emb_distance_openai.py "texte 1" "texte 2"
  ./src/pipeline-advanced/get_emb_distance_openai.py -m text-embedding-3-large "texte 1" "texte 2"

Sortie:
  Une ligne JSON contenant:
    {
      "text1": "...",
      "text2": "...",
      "model": {"name": "...", "version": "..."},
      "metric": "cosine",
      "distance": 0.1234,
      "similarity": 0.8766
    }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List

import numpy as np

try:
    from openai import OpenAI  # SDK v1+
except Exception as exc:
    print("Error: openai package is required. Install with: pip install openai", file=sys.stderr)
    raise

try:
    from importlib.metadata import version as _pkg_version  # Python 3.8+
except Exception:
    _pkg_version = None


_ALLOWED_MODELS = [
    "text-embedding-3-small",
    "text-embedding-3-large",
]

_DEFAULT_MODEL = "text-embedding-3-small"


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """
    Weaviate's cosine distance equivalent:
      distance = 1 - cosine_similarity(a, b)
    """
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        # Si une norme est nulle, définir similarité à 0 => distance = 1
        return 1.0
    cos_sim = float(np.dot(a, b) / denom)
    # Bornage numérique
    cos_sim = max(min(cos_sim, 1.0), -1.0)
    return 1.0 - cos_sim


def _embed_texts_openai(texts: List[str], model_name: str, api_key: str) -> np.ndarray:
    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(model=model_name, input=texts)
    # OpenAI renvoie un élément par input, chaque .embedding est une liste de floats
    vecs = np.array([item.embedding for item in resp.data], dtype=float)
    return vecs


def compute_distance_openai(text1: str, text2: str, model_name: str = _DEFAULT_MODEL) -> dict:
    api_key = os.environ.get("OPENAIAPIKEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OpenAI API key. Set OPENAIAPIKEY (or OPENAI_API_KEY).")

    vecs = _embed_texts_openai([text1, text2], model_name, api_key)
    a, b = vecs[0], vecs[1]
    dist = _cosine_distance(a, b)
    sim = 1.0 - dist

    lib_version = "unknown"
    if _pkg_version is not None:
        try:
            lib_version = _pkg_version("openai")
        except Exception:
            lib_version = "unknown"

    return {
        "text1": text1,
        "text2": text2,
        "model": {"name": model_name, "version": lib_version},
        "metric": "cosine",
        "distance": dist,
        "similarity": sim,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calcule la distance (cosine) entre les embeddings de deux chaînes avec OpenAI."
    )
    parser.add_argument("text1", help="Première chaîne")
    parser.add_argument("text2", help="Deuxième chaîne")
    parser.add_argument(
        "-m",
        "--model",
        choices=_ALLOWED_MODELS,
        default=_DEFAULT_MODEL,
        help="Modèle OpenAI à utiliser (text-embedding-3-small ou text-embedding-3-large)",
    )
    args = parser.parse_args(argv)

    try:
        result = compute_distance_openai(args.text1, args.text2, model_name=args.model)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
