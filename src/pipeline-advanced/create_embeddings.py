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
      "headings": {"h1": "...", "h2": "...", ...},
      "heading": {"hN": "..."},
      "full_headings": "..."
    }

Behavior:
- Uses sentence-transformers with the 'paraphrase-xlm-r-multilingual-v1' model.
- Caches embeddings on disk to avoid recomputation across runs (per-model cache).
- Streams input and encodes in small batches to limit memory use.
- Prints the produced output filename.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import sentence_transformers
from sentence_transformers import SentenceTransformer


_MODEL_NAME = "paraphrase-xlm-r-multilingual-v1"
_OPENAI_MODEL_NAME = "text-embedding-3-large"
_BATCH_SIZE = 64


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_meta(chunk: Dict) -> tuple[List[str], Dict[str, str], Dict[str, str], str]:
    # Prefer top-level fields; fall back to legacy "metadata" container for backward compatibility.
    meta = chunk.get("metadata") or {}
    keywords = chunk.get("keywords", meta.get("keywords", []))
    headings = chunk.get("headings", meta.get("headings", {}))
    heading = chunk.get("heading", meta.get("heading", {}))
    full_headings = chunk.get("full_headings", meta.get("full_headings", ""))
    # Ensure types are correct
    if not isinstance(keywords, list):
        keywords = []
    if not isinstance(headings, dict):
        headings = {}
    if not isinstance(heading, dict):
        heading = {}
    if not isinstance(full_headings, str):
        full_headings = ""
    return keywords, headings, heading, full_headings


def convert_chunks_to_embeddings(input_path: str, use_openai: bool = False) -> str:
    """
    Read chunks JSONL and write embeddings NDJSON to <input>.embeddings.ndjson.
    Returns the output file path as a string.
    If use_openai is True, embeddings are computed via OpenAI API (model: text-embedding-3-large).
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    out_path = Path(f"{input_path}.embeddings.ndjson")

    # Initialize encoder or OpenAI client based on mode
    local_model: Optional[SentenceTransformer] = None
    client = None
    if not use_openai:
        local_model = SentenceTransformer(_MODEL_NAME)

    created_at = _iso_utc_now()
    if use_openai:
        try:
            import openai as _openai_pkg  # lazy import to avoid dependency when not used
            from openai import OpenAI as _OpenAI
        except Exception as e:
            raise RuntimeError("OpenAI package not installed. Install with: pip install openai") from e
        api_key = os.environ.get("OPENAIAPIKEY")
        if not api_key:
            raise RuntimeError("Environment variable OPENAIAPIKEY is not set.")
        client = _OpenAI(api_key=api_key)
        model_name = _OPENAI_MODEL_NAME
        model_version = getattr(_openai_pkg, "__version__", "unknown")
    else:
        model_name = _MODEL_NAME
        model_version = getattr(sentence_transformers, "__version__", "unknown")
    model_info = {
        "name": model_name,
        "version": model_version,
    }

    # Simple on-disk cache for embeddings to avoid recomputation across runs.
    # One cache file per input and model name.
    cache_path = Path(f"{input_path}.{model_name}.emb_cache.jsonl")
    emb_cache: Dict[str, List[float]] = {}

    def _cache_key(text: str) -> str:
        """
        Build a stable key for the given text, including model name and version to avoid collisions.
        """
        ver = model_info.get("version", "unknown")
        payload = f"{model_name}\n{ver}\n".encode("utf-8") + (text if isinstance(text, bytes) else str(text)).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    # Load existing cache entries
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as cf:
            for ln in cf:
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                k = rec.get("k")
                v = rec.get("v")
                if isinstance(k, str) and isinstance(v, list):
                    try:
                        emb_cache[k] = [float(x) for x in v]
                    except Exception:
                        continue

    def _persist_cache_items(items: List[tuple[str, List[float]]]) -> None:
        if not items:
            return
        with cache_path.open("a", encoding="utf-8") as cf:
            for k, v in items:
                cf.write(json.dumps({"k": k, "v": v}, ensure_ascii=False) + "\n")

    texts: List[str] = []
    rows: List[Dict] = []

    def flush_batch():
        nonlocal texts, rows
        if not texts:
            return

        # Resolve text embeddings using cache when possible
        text_keys = [_cache_key(t) for t in texts]
        text_embs: List[Optional[List[float]]] = [emb_cache.get(k) for k in text_keys]
        to_compute_idx = [i for i, e in enumerate(text_embs) if e is None]
        if to_compute_idx:
            to_compute_texts = [texts[i] for i in to_compute_idx]
            for t in to_compute_texts:
                print(f"computing embedding for: {t}")
            if use_openai:
                resp = client.embeddings.create(model=model_name, input=to_compute_texts)
                computed_list = [list(map(float, d.embedding)) for d in resp.data]
            else:
                computed = local_model.encode(
                    to_compute_texts,
                    batch_size=min(_BATCH_SIZE, len(to_compute_texts)),
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
                if isinstance(computed, np.ndarray):
                    computed_list: List[List[float]] = computed.astype(float).tolist()
                elif isinstance(computed, list):
                    computed_list = [list(map(float, e)) for e in computed]
                else:
                    computed_list = [list(map(float, np.array(computed).astype(float).tolist()))]

            new_cache_items: List[tuple[str, List[float]]] = []
            for pos, vec in zip(to_compute_idx, computed_list):
                k = text_keys[pos]
                emb_cache[k] = vec
                text_embs[pos] = vec
                new_cache_items.append((k, vec))
            _persist_cache_items(new_cache_items)

        # At this point, all text_embs are filled
        text_embs_filled: List[List[float]] = [e for e in text_embs if e is not None]  # type: ignore


        with out_path.open("a", encoding="utf-8") as out_f:
            for item, text_emb in zip(rows, text_embs_filled):
                keywords, headings, heading, full_headings = _extract_meta(item)
                text = item.get("text", "")
                if not isinstance(text, str):
                    text = str(text)
                rec = {
                    "chunk_id": item.get("chunk_id"),
                    "text": text,
                    "embedding": text_emb,
                    "model": model_info,
                    "created_at": created_at,
                    "approx_tokens": item.get("approx_tokens"),
                    "keywords": keywords,
                    "headings": headings,
                    "heading": heading,
                    "full_headings": full_headings,
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
    parser.add_argument(
        "-openai",
        "--openai",
        action="store_true",
        help="Use OpenAI API (model: text-embedding-3-large) instead of local sentence-transformers.",
    )
    args = parser.parse_args(argv)

    try:
        produced = convert_chunks_to_embeddings(args.input, use_openai=args.openai)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(produced)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
