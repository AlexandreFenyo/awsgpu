#!/usr/bin/env python3
"""
Rerank retrieved chunks for a given question using a Cross-Encoder.

- Input:
  - Arg1: Question (string)
  - Arg2: Path to JSONL file with lines shaped like:
      {
        "chunk_id": "...",
        "text": "...",
        "distance": 0.4710,
        "approx_tokens": 379,
        "keywords": ["...", ...],
        "headings": {...},
        "heading": {...},
        "full_headings": "...",
        "created_at": "..."
      }

- Behavior:
  - Use cross-encoder/ms-marco-MiniLM-L-6-v2 from sentence-transformers to score (question, text) pairs.
  - Truncate inputs to 512 model tokens for reranking (model-side truncation).
  - Add a "reranker" float score to each JSON object.
  - Sort all chunks by "reranker" descending (best first).
  - Write all chunks (not truncated) to <input>.reranked.jq in JSONL order.

Note:
- We only truncate at model input time; we always write back the original (untruncated) chunk text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from sentence_transformers import CrossEncoder
except Exception as exc:  # pragma: no cover
    print(
        "Error: sentence-transformers is required. Install with: pip install sentence-transformers",
        file=sys.stderr,
    )
    raise


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON line in {path}: {e}\nLine: {line[:200]}") from e
            if not isinstance(obj, dict):
                raise ValueError(f"Expected JSON object per line, got: {type(obj)}")
            items.append(obj)
    return items


def write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def build_pairs(question: str, items: List[Dict[str, Any]]) -> List[List[str]]:
    # Each pair is [question, text]
    pairs: List[List[str]] = []
    for obj in items:
        text = obj.get("text", "")
        if not isinstance(text, str):
            text = str(text)
        pairs.append([question, text])
    return pairs


def rerank(question: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []

    # Load CrossEncoder; ensure max_length=512 for model-side truncation
    model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
    pairs = build_pairs(question, items)

    # Predict scores; model tokenization will truncate to max_length
    scores = model.predict(pairs, batch_size=32, show_progress_bar=False)

    # Attach scores
    for obj, score in zip(items, scores):
        obj["reranker"] = float(score)

    # Sort by score descending
    items_sorted = sorted(items, key=lambda x: x.get("reranker", float("-inf")), reverse=True)
    return items_sorted


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rerank chunks for a question using a Cross-Encoder.")
    parser.add_argument("question", help="User question (string)")
    parser.add_argument("input", help="Path to JSONL input file to rerank")
    args = parser.parse_args(argv)

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Error: Input file not found: {in_path}", file=sys.stderr)
        return 1

    try:
        items = read_jsonl(in_path)
        ranked = rerank(args.question, items)
        out_path = Path(f"{str(in_path)}.reranked.jq")
        write_jsonl(out_path, ranked)
        print(str(out_path))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
