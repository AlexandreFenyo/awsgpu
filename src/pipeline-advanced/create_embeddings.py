#!/usr/bin/env python3
"""
Create embeddings from Markdown chunks for a simple RAG pipeline.

- Input: a JSONL file of chunks (as produced by create_chunks.py).
- Output: NDJSON (.embeddings.ndjson) where each line is:
    {
      "chunk_id": "...",
      "text": "...",
      "embedding": [floats],
      "embeddings": [{"level": "hN", "embedding": [floats]}, ...],
      "model": {"name": "...", "version": "..."},
      "created_at": "YYYY-MM-DDTHH:MM:SSZ",
      "approx_tokens": 123,
      "keywords": ["...", ...],
      "headings": {"h1": "...", "h2": "...", ...}
    }

Behavior:
- Uses sentence-transformers with the 'paraphrase-xlm-r-multilingual-v1' model.
- For each chunk, also computes embeddings for each heading level present (h1..h6) and outputs them under "embeddings" as objects with their level label (e.g., {"level": "h2", "embedding": [...]}) ordered by level.
- Caches embeddings on disk to avoid recomputation across runs (per-model cache).
- Streams input and encodes in small batches to limit memory use.
- Prints the produced output filename.
"""

from __future__ import annotations

import argparse
import json
import hashlib
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


def convert_chunks_to_embeddings(input_path: str, include_heading_embeddings: bool = True) -> str:
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

    # Simple on-disk cache for embeddings to avoid recomputation across runs.
    # One cache file per input and model name.
    cache_path = Path(f"{input_path}.{_MODEL_NAME}.emb_cache.jsonl")
    emb_cache: Dict[str, List[float]] = {}

    def _cache_key(text: str) -> str:
        """
        Build a stable key for the given text, including model name and version to avoid collisions.
        """
        ver = model_info.get("version", "unknown")
        payload = f"{_MODEL_NAME}\n{ver}\n".encode("utf-8") + (text if isinstance(text, bytes) else str(text)).encode("utf-8")
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
            computed = model.encode(
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

        if not include_heading_embeddings:
            per_row_embeddings: List[List[Dict[str, object]]] = [[] for _ in rows]
        else:
            # Prepare per-row heading texts ordered by level, and remember their levels
            flat_headings: List[str] = []
            flat_levels: List[str] = []
            counts_per_row: List[int] = []
            for item in rows:
                _, headings = _extract_meta(item)
                ordered_pairs = [
                    (f"h{level}", title)
                    for level, title in sorted(
                        (
                            (int(k[1:]), v)
                            for k, v in headings.items()
                            if isinstance(k, str) and k.startswith("h") and isinstance(v, str) and v.strip()
                        ),
                        key=lambda t: t[0],
                    )
                ]
                counts_per_row.append(len(ordered_pairs))
                for lvl, title in ordered_pairs:
                    flat_levels.append(lvl)
                    flat_headings.append(title)

            # Resolve heading embeddings via cache
            heading_embs_list: List[List[float]] = []
            if flat_headings:
                heading_keys = [_cache_key(h) for h in flat_headings]
                heading_embs_opt: List[Optional[List[float]]] = [emb_cache.get(k) for k in heading_keys]
                to_compute_idx_h = [i for i, e in enumerate(heading_embs_opt) if e is None]
                if to_compute_idx_h:
                    to_compute_headings = [flat_headings[i] for i in to_compute_idx_h]
                    for h in to_compute_headings:
                        print(f"computing embedding for: {h}")
                    computed_h = model.encode(
                        to_compute_headings,
                        batch_size=min(_BATCH_SIZE, len(to_compute_headings)),
                        convert_to_numpy=True,
                        show_progress_bar=False,
                    )
                    if isinstance(computed_h, np.ndarray):
                        computed_h_list: List[List[float]] = computed_h.astype(float).tolist()
                    elif isinstance(computed_h, list):
                        computed_h_list = [list(map(float, e)) for e in computed_h]
                    else:
                        computed_h_list = [list(map(float, np.array(computed_h).astype(float).tolist()))]

                    new_cache_items_h: List[tuple[str, List[float]]] = []
                    for pos, vec in zip(to_compute_idx_h, computed_h_list):
                        k = heading_keys[pos]
                        emb_cache[k] = vec
                        heading_embs_opt[pos] = vec
                        new_cache_items_h.append((k, vec))
                    _persist_cache_items(new_cache_items_h)

                heading_embs_list = [e for e in heading_embs_opt if e is not None]  # type: ignore
            else:
                heading_embs_list = []

            # Reconstruct per-row arrays of heading embeddings with corresponding level labels.
            per_row_embeddings: List[List[Dict[str, object]]] = []
            idx = 0
            for count in counts_per_row:
                if count == 0:
                    per_row_embeddings.append([])
                else:
                    levels_slice = flat_levels[idx : idx + count]
                    embs_slice = heading_embs_list[idx : idx + count]
                    per_row_embeddings.append(
                        [{"level": lvl, "embedding": emb} for lvl, emb in zip(levels_slice, embs_slice)]
                    )
                    idx += count

        with out_path.open("a", encoding="utf-8") as out_f:
            for item, text_emb, heading_embs in zip(rows, text_embs_filled, per_row_embeddings):
                keywords, headings = _extract_meta(item)
                text = item.get("text", "")
                if not isinstance(text, str):
                    text = str(text)
                rec = {
                    "chunk_id": item.get("chunk_id"),
                    "text": text,
                    "embedding": text_emb,
                    "embeddings": heading_embs,
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
    parser.add_argument(
        "--no-heading-embeddings",
        action="store_true",
        help="Skip computing heading embeddings (h1..h6) for chunks",
    )
    args = parser.parse_args(argv)

    try:
        produced = convert_chunks_to_embeddings(args.input, include_heading_embeddings=not args.no_heading_embeddings)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(produced)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
