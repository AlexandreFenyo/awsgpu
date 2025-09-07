#!/usr/bin/env python3
"""
Calcule la distance entre les embeddings de deux chaînes de caractères.

- Utilise sentence-transformers avec le modèle 'paraphrase-xlm-r-multilingual-v1'.
- Aligne la métrique sur celle utilisée par search_chunks.py / Weaviate (cosine distance),
  c'est-à-dire: distance = 1 - cosine_similarity.

Usage:
  ./src/pipeline-advanced/get_emb_distance.py "texte 1" "texte 2"

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
import sys
from typing import List

import numpy as np
import sentence_transformers
from sentence_transformers import SentenceTransformer


_MODEL_NAME = "paraphrase-xlm-r-multilingual-v1"


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """
    Weaviate's cosine distance equivalent:
      distance = 1 - cosine_similarity(a, b)
    """
    # Sécurité numérique
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        # Si une norme est nulle, définir similarité à 0 => distance = 1
        return 1.0
    cos_sim = float(np.dot(a, b) / denom)
    # Bornage numérique
    cos_sim = max(min(cos_sim, 1.0), -1.0)
    return 1.0 - cos_sim


def _embed_texts(texts: List[str]) -> np.ndarray:
    model = SentenceTransformer(_MODEL_NAME)
    vecs = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    if isinstance(vecs, list):
        # Rare selon les versions, mais on gère le cas
        return np.array(vecs, dtype=float)
    return vecs.astype(float)


def compute_distance(text1: str, text2: str) -> dict:
    vecs = _embed_texts([text1, text2])
    a, b = vecs[0], vecs[1]
    dist = _cosine_distance(a, b)
    sim = 1.0 - dist
    return {
        "text1": text1,
        "text2": text2,
        "model": {"name": _MODEL_NAME, "version": getattr(sentence_transformers, "__version__", "unknown")},
        "metric": "cosine",
        "distance": dist,
        "similarity": sim,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calcule la distance (cosine) entre les embeddings de deux chaînes."
    )
    parser.add_argument("text1", help="Première chaîne")
    parser.add_argument("text2", help="Deuxième chaîne")
    args = parser.parse_args(argv)

    try:
        result = compute_distance(args.text1, args.text2)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
