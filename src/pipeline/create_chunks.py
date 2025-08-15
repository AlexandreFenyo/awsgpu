#!/usr/bin/env python3
"""
Create chunks from a Markdown file for a simple RAG pipeline.

- Input: a Markdown file path.
- Output: JSONL (.chunks.jq) where each line is a chunk:
    {
      "chunk_id": "...",
      "text": "...",
      "metadata": { "headings": {"h1": "...", "h2": "...", ...}, "keywords": ["...", ...] },
      "approx_tokens": 123
    }

Constraints and behavior:
- Chunk size ~200 tokens by default, configurable via CLI.
- Simple token estimation without external libraries (based on word count).
- No chunk crosses heading boundaries.
- Markdown tables are converted to simple text preserving their content.
- Metadata includes:
  - Keywords extracted from the chunk text (simple top-N by frequency, minus stopwords).
  - The active heading levels for the chunk.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List, Tuple, Dict, Optional


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


def parse_table_block(lines: List[str], start_idx: int) -> Tuple[str, int]:
    """
    Parse a GitHub-flavored Markdown table starting at start_idx.
    Returns a textual representation of the table and the index of the next line after the table.

    A very simple parser:
    - Detect a header row with '|' and a separator line of dashes.
    - Continue collecting rows while they contain '|'.
    """
    i = start_idx
    if i >= len(lines):
        return "", i

    header_line = lines[i]
    if "|" not in header_line:
        return "", i

    # Must have a separator line next, consisting of dashes and pipes (roughly).
    if i + 1 >= len(lines):
        return "", i

    sep_line = lines[i + 1]
    sep_ok = bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", sep_line))
    if not sep_ok:
        return "", i

    # Collect table lines
    table_lines = [header_line]
    i += 2  # skip header and separator
    while i < len(lines) and "|" in lines[i]:
        table_lines.append(lines[i])
        i += 1

    def split_row(row: str) -> List[str]:
        parts = [cell.strip() for cell in row.strip().strip("|").split("|")]
        return parts

    headers = split_row(table_lines[0])
    rows = [split_row(r) for r in table_lines[1:]]

    # Build a simple textual representation of the table
    rendered_rows: List[str] = []
    for row in rows:
        cells = []
        for col_idx, value in enumerate(row):
            key = headers[col_idx] if col_idx < len(headers) else f"col{col_idx+1}"
            if value:
                cells.append(f"{key}: {value}")
        if cells:
            rendered_rows.append("; ".join(cells))
    if not rendered_rows:
        # Table with only headers or empty rows; just render headers
        rendered_rows.append(" | ".join(headers))

    table_text = "TABLE:\n" + "\n".join(rendered_rows)
    return table_text, i


def extract_keywords(text: str, top_n: int = 5) -> List[str]:
    """
    Simple keyword extraction:
    - Lowercase
    - Strip punctuation except intra-word hyphens
    - Remove stopwords and tokens shorter than 3 chars
    - Count frequency and return top_n
    """
    # Normalize and split on non-letters/digits/hyphens
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9\-]+", text.lower())
    tokens = [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS and not t.isdigit()]
    counts = Counter(tokens)
    if not counts:
        return []
    # Most common, preserving order deterministically
    return [tok for tok, _ in counts.most_common(top_n)]


def build_chunks_from_markdown(
    md_text: str, chunk_size_tokens: int, source: str
) -> List[Dict]:
    """
    Build chunks by walking the Markdown:
    - Maintain heading context (h1..h6).
    - Convert tables into plain text blocks.
    - Accumulate lines within the same heading context up to the token budget.
    - Emit chunks that never cross heading boundaries.
    """
    lines = md_text.splitlines()
    chunks: List[Dict] = []

    # Active heading context, mapping level -> title
    headings: Dict[int, str] = {}
    buffer_lines: List[str] = []

    def current_headings_meta() -> Dict[str, str]:
        # Build an ordered dict-like mapping h1..h6 for metadata
        meta: Dict[str, str] = {}
        for lvl in sorted(headings.keys()):
            meta[f"h{lvl}"] = headings[lvl]
        return meta

    def emit_buffer_as_chunks():
        nonlocal buffer_lines
        if not buffer_lines:
            return
        text = "\n".join(buffer_lines).strip()
        if not text:
            buffer_lines = []
            return

        # Split by lines to pack into chunks without exceeding the token budget.
        out_lines: List[str] = []
        approx = 0
        chunk_idx_local = 0

        def finalize_one(out_text: str):
            nonlocal chunk_idx_local
            chunk_idx_local += 1
            meta_headings = current_headings_meta()
            keywords = extract_keywords(out_text, top_n=5)
            chunks.append(
                {
                    "chunk_id": f"{Path(source).name}-h{'.'.join(str(k) for k in sorted(headings.keys())) or '0'}-{len(chunks)+1}",
                    "text": out_text,
                    "metadata": {
                        "headings": meta_headings,
                        "keywords": keywords,
                    },
                    "approx_tokens": estimate_tokens(out_text),
                }
            )

        for ln in text.splitlines():
            new_approx = approx + estimate_tokens(ln)
            # If adding this line would exceed the budget and we already have content, flush
            if out_lines and new_approx > chunk_size_tokens:
                finalize_one("\n".join(out_lines).strip())
                out_lines = []
                approx = 0
            out_lines.append(ln)
            approx = new_approx

        if out_lines:
            finalize_one("\n".join(out_lines).strip())

        buffer_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Heading?
        m = _heading_re.match(line)
        if m:
            # New heading -> finish current buffer into chunks first
            emit_buffer_as_chunks()

            level = len(m.group("hashes"))
            title = m.group("title").strip()

            # Update heading context: set this level and drop deeper ones
            headings[level] = title
            for deeper in list(headings.keys()):
                if deeper > level:
                    del headings[deeper]
            i += 1
            continue

        # Table block?
        table_text, next_i = parse_table_block(lines, i)
        if table_text:
            buffer_lines.append(table_text)
            i = next_i
            continue

        # Regular text line
        buffer_lines.append(line)
        i += 1

    # Flush any remaining content
    emit_buffer_as_chunks()

    # Ensure chunk_ids are sequential and stable
    for idx, ch in enumerate(chunks, start=1):
        ch["chunk_id"] = f"{Path(source).stem}-{idx}"

    return chunks


def write_chunks_jsonl(chunks: List[Dict], outpath: Path) -> None:
    with outpath.open("w", encoding="utf-8") as f:
        for ch in chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")


def convert_markdown_to_chunks(input_path: str, chunk_size_tokens: int = 200) -> str:
    """
    Convert a Markdown file into chunked JSONL (.chunks.jq).
    Returns the output file path as a string.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")
    text = src.read_text(encoding="utf-8")

    chunks = build_chunks_from_markdown(text, chunk_size_tokens=chunk_size_tokens, source=str(src))
    out_path = Path(f"{input_path}.chunks.jq")
    write_chunks_jsonl(chunks, out_path)
    return str(out_path)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create simple RAG chunks from a Markdown file."
    )
    parser.add_argument(
        "input",
        help="Path to the input Markdown file",
    )
    parser.add_argument(
        "-s",
        "--chunk-size-tokens",
        type=int,
        default=200,
        help="Approximate token size of chunks (default: 200)",
    )
    args = parser.parse_args(argv)

    try:
        produced = convert_markdown_to_chunks(args.input, chunk_size_tokens=args.chunk_size_tokens)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(produced)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
