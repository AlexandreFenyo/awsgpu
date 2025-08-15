#!/usr/bin/env python3
"""
Create embeddings from Markdown chunks for a simple RAG pipeline.

- Input: a JSONL file of chunks (as produced by create_chunks.py).
- Output: NDJSON (.embeddings.ndjson) where each line is:
    {
      "chunk_id": "...",
      "text": "...",
      "embedding": [floats],
      "model": {"name": "...", "version": "..."},
      "created_at": "YYYY-MM-DDTHH:MM:SSZ",
      "approx_tokens": 123,
      "keywords": ["...", ...],
      "headings": {"h1": "...", "h2": "...", ...}
    }

Behavior:
- Uses sentence-transformers with the 'paraphrase-xlm-r-multilingual-v1' model.
- Streams input and encodes in small batches to limit memory use.
- Prints the produced output filename.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import sentence_transformers
from sentence_transformers import SentenceTransformer


_MODEL_NAME = "paraphrase-xlm-r-multilingual-v1"
_BATCH_SIZE = 64


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_meta(chunk: Dict) -> tuple[List[str], Dict[str, str]]:
    meta = chunk.get("metadata") or {}
    keywords = meta.get("keywords") or []
    headings = meta.get("headings") or {}
    # Ensure types are correct
    if not isinstance(keywords, list):
        keywords = []
    if not isinstance(headings, dict):
        headings = {}
    return keywords, headings


def convert_chunks_to_embeddings(input_path: str) -> str:
    """
    Read chunks JSONL and write embeddings NDJSON to <input>.embeddings.ndjson.
    Returns the output file path as a string.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    out_path = Path(f"{input_path}.embeddings.ndjson")

    model = SentenceTransformer(_MODEL_NAME)

    created_at = _iso_utc_now()
    model_info = {
        "name": _MODEL_NAME,
        "version": getattr(sentence_transformers, "__version__", "unknown"),
    }

    texts: List[str] = []
    rows: List[Dict] = []

    def flush_batch():
        nonlocal texts, rows
        if not texts:
            return
        embeddings = model.encode(texts, batch_size=min(_BATCH_SIZE, len(texts)), convert_to_numpy=True, show_progress_bar=False)
        # Ensure JSON-serializable floats
        if isinstance(embeddings, list):
            embs = [list(map(float, e)) for e in embeddings]
        elif isinstance(embeddings, np.ndarray):
            embs = embeddings.astype(float).tolist()
        else:
            # Fallback
            embs = [list(map(float, np.array(embeddings).astype(float).tolist()))]

        with out_path.open("a", encoding="utf-8") as out_f:
            for item, emb in zip(rows, embs):
                keywords, headings = _extract_meta(item)
                text = item.get("text", "")
                if not isinstance(text, str):
                    text = str(text)
                rec = {
                    "chunk_id": item.get("chunk_id"),
                    "text": text,
                    "embedding": emb,
                    "model": model_info,
                    "created_at": created_at,
                    "approx_tokens": item.get("approx_tokens"),
                    "keywords": keywords,
                    "headings": headings,
                }
                out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        texts = []
        rows = []

    # Ensure output file is empty before writing
    if out_path.exists():
        out_path.unlink()

    with src.open("r", encoding="utf-8") as f:
        for line in f:
            ln = line.strip()
            if not ln:
                continue
            try:
                item = json.loads(ln)
            except json.JSONDecodeError:
                # Skip malformed lines
                continue
            txt = item.get("text", "")
            if not isinstance(txt, str):
                txt = str(txt)
            rows.append(item)
            texts.append(txt)

            if len(texts) >= _BATCH_SIZE:
                flush_batch()

    # Flush any remaining
    flush_batch()

    return str(out_path)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create embeddings NDJSON from chunks JSONL using sentence-transformers."
    )
    parser.add_argument(
        "input",
        help="Path to the input chunks file (JSONL)",
    )
    args = parser.parse_args(argv)

    try:
        produced = convert_chunks_to_embeddings(args.input)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(produced)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
