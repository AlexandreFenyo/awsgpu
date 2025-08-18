#!/usr/bin/env python3
"""
Create heading-only chunks from a Markdown file for a RAG pipeline.

- Input: a Markdown file path.
- Output: JSONL (<input>.headings.chunks.jq) where each line is a chunk:
    {
      "chunk_id": "<input-filename>-headings-<n>",
      "text": "<heading title only>",
      "metadata": {
        "headings": {"h1": "...", "h2": "...", ...},  # active heading context including current
        "heading_level": <int>,  # 1..6
        "keywords": ["...", ...]
      },
      "approx_tokens": <int>
    }

Behavior:
- One chunk per heading line (any level).
- "text" is the heading title only (without leading #).
- Metadata includes the heading context (same format as create_chunks.py),
  the numeric heading level, and simple keywords extracted from the title.
- No token/size limit is applied to chunks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List, Dict, Optional

# Minimal bilingual (FR/EN) stopwords for simple keyword extraction.
_STOPWORDS = {
    # English
    "the", "and", "for", "with", "that", "this", "these", "those",
    "are", "was", "were", "has", "have", "had", "but", "not",
    "you", "your", "yours", "from", "they", "their", "them",
    "a", "an", "in", "on", "of", "to", "is", "it", "as", "be",
    "by", "or", "if", "we", "our", "us", "at", "can", "could",
    "should", "would", "may", "might", "will", "shall", "do", "does", "did",
    "so", "than", "then", "there", "here", "also", "into", "out", "up", "down",
    # French
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "au", "aux",
    "et", "ou", "mais", "ne", "pas", "plus", "pour", "par", "dans", "sur",
    "ce", "cet", "cette", "ces", "se", "sa", "son", "ses", "leur", "leurs",
    "qui", "que", "quoi", "dont", "où", "quand", "comme", "ainsi",
    "est", "sont", "étaient", "était", "été", "être", "a", "ont", "avait",
    "avec", "sans", "entre", "vers", "chez", "sur", "sous", "après", "avant",
}

def estimate_tokens(text: str) -> int:
    """
    Very simple token estimation: count whitespace-separated words.
    """
    return len(text.split())

_heading_re = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")

def extract_keywords(text: str, top_n: int = 5) -> List[str]:
    """
    Simple keyword extraction for headings:
    - Lowercase
    - Strip punctuation except intra-word hyphens
    - Remove stopwords and tokens shorter than 3 chars
    - Count frequency and return top_n
    """
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9\-]+", text.lower())
    tokens = [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS and not t.isdigit()]
    counts = Counter(tokens)
    if not counts:
        return []
    return [tok for tok, _ in counts.most_common(top_n)]

def build_heading_chunks_from_markdown(md_text: str, source: str) -> List[Dict]:
    """
    Walk the Markdown lines and create one chunk per heading, with metadata:
    - headings: active heading context (h1..h6) including the current heading
    - heading_level: numeric level (1..6)
    - keywords: simple keywords extracted from the heading title
    """
    lines = md_text.splitlines()
    chunks: List[Dict] = []

    # Active heading context, mapping level -> title
    headings: Dict[int, str] = {}

    def current_headings_meta() -> Dict[str, str]:
        # Build an ordered dict-like mapping h1..h6 for metadata
        meta: Dict[str, str] = {}
        for lvl in sorted(headings.keys()):
            meta[f"h{lvl}"] = headings[lvl]
        return meta

    for line in lines:
        m = _heading_re.match(line)
        if not m:
            continue

        level = len(m.group("hashes"))
        title = m.group("title").strip()

        # Update heading context: set this level and drop deeper ones
        headings[level] = title
        for deeper in list(headings.keys()):
            if deeper > level:
                del headings[deeper]

        meta_headings = current_headings_meta()
        keywords = extract_keywords(title, top_n=5)
        chunks.append(
            {
                "chunk_id": "",  # will be filled sequentially below
                "text": title,
                "metadata": {
                    "headings": meta_headings,
                    "heading_level": level,
                    "keywords": keywords,
                },
                "approx_tokens": estimate_tokens(title),
            }
        )

    # Ensure chunk_ids are sequential and stable, using the input filename (including extension)
    base_name = Path(source).name
    for idx, ch in enumerate(chunks, start=1):
        ch["chunk_id"] = f"{base_name}-headings-{idx}"

    return chunks

def write_chunks_jsonl(chunks: List[Dict], outpath: Path) -> None:
    with outpath.open("w", encoding="utf-8") as f:
        for ch in chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")

def convert_markdown_headings_to_chunks(input_path: str) -> str:
    """
    Convert a Markdown file into heading-only chunks JSONL (.headings.chunks.jq).
    Returns the output file path as a string.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")
    text = src.read_text(encoding="utf-8")

    chunks = build_heading_chunks_from_markdown(text, source=str(src))
    out_path = Path(f"{input_path}.headings.chunks.jq")
    write_chunks_jsonl(chunks, out_path)
    return str(out_path)

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create heading-only RAG chunks from a Markdown file."
    )
    parser.add_argument(
        "input",
        help="Path to the input Markdown file",
    )
    args = parser.parse_args(argv)

    try:
        produced = convert_markdown_headings_to_chunks(args.input)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(produced)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
