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
- List blocks are kept intact (never split across chunks), even if that exceeds the token budget.
- Additionally, if a list block immediately follows a paragraph within the same heading level, that preceding paragraph is merged with the list into the same chunk.
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


def _is_list_item_start(line: str) -> bool:
    return bool(re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", line))

def _is_indented_continuation(line: str) -> bool:
    return bool(re.match(r"^\s{2,}\S", line)) or line.startswith("\t")

def _parse_list_block(lines: List[str], start_idx: int) -> Tuple[str, int]:
    """
    Parse a contiguous Markdown list block starting at start_idx.
    Keeps all list items (and their indented continuations) together.
    Returns (block_text, next_index).
    """
    i = start_idx
    collected: List[str] = []
    if i >= len(lines) or not _is_list_item_start(lines[i]):
        return "", i

    while i < len(lines):
        ln = lines[i]
        if _is_list_item_start(ln) or _is_indented_continuation(ln):
            collected.append(ln)
            i += 1
            continue
        if not ln.strip():
            # Blank line: include it only if the following line continues the list.
            if i + 1 < len(lines) and (_is_list_item_start(lines[i + 1]) or _is_indented_continuation(lines[i + 1])):
                collected.append(ln)
                i += 1
                continue
            break
        break

    return "\n".join(collected), i


def _collect_previous_paragraph(lines: List[str], list_start_idx: int) -> Tuple[Optional[List[str]], int]:
    """
    If a list block at list_start_idx is immediately preceded (ignoring blank lines)
    by a regular paragraph within the same heading (i.e., no intervening heading),
    return (para_lines, gap_blank_count). Otherwise return (None, 0).
    """
    # Move to previous non-blank line
    j = list_start_idx - 1
    gap_blank_count = 0
    while j >= 0 and lines[j].strip() == "":
        gap_blank_count += 1
        j -= 1

    if j < 0:
        return None, 0

    # If the previous non-blank line is a heading or a list start, do not include it.
    if _heading_re.match(lines[j]) or _is_list_item_start(lines[j]):
        return None, 0

    # Collect the contiguous paragraph lines up to the previous blank line (or file start).
    para_end = j
    k = para_end - 1
    while k >= 0 and lines[k].strip() != "":
        k -= 1
    para_start = k + 1

    para_lines = lines[para_start : para_end + 1]
    return para_lines, gap_blank_count


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
    buffer_blocks: List[str] = []

    def current_headings_meta() -> Dict[str, str]:
        # Build an ordered dict-like mapping h1..h6 for metadata
        meta: Dict[str, str] = {}
        for lvl in sorted(headings.keys()):
            meta[f"h{lvl}"] = headings[lvl]
        return meta

    def emit_buffer_as_chunks():
        nonlocal buffer_blocks
        if not buffer_blocks:
            return

        # Pack blocks (list blocks or single lines) into chunks without splitting list blocks.
        out_blocks: List[str] = []
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

        for block in buffer_blocks:
            block_tokens = estimate_tokens(block)
            # If adding this block would exceed the budget and we already have content, flush first.
            if out_blocks and (approx + block_tokens) > chunk_size_tokens:
                finalize_one("\n".join(out_blocks).strip())
                out_blocks = []
                approx = 0

            # Always add the whole block (may exceed budget), especially for list blocks.
            out_blocks.append(block)
            approx += block_tokens

        if out_blocks:
            finalize_one("\n".join(out_blocks).strip())

        buffer_blocks = []

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
            buffer_blocks.append(table_text)
            i = next_i
            continue
        
        # List block?
        if _is_list_item_start(line):
            list_text, next_i = _parse_list_block(lines, i)
            if list_text:
                # Try to include the immediately preceding paragraph in the same chunk,
                # as long as there is no intervening heading (to avoid spanning headings).
                para_lines, gap_blanks = _collect_previous_paragraph(lines, i)
                if para_lines:
                    # Remove the paragraph lines (and trailing blanks) that were already buffered.
                    popped_blanks = 0
                    while buffer_blocks and buffer_blocks[-1].strip() == "":
                        buffer_blocks.pop()
                        popped_blanks += 1

                    idx_end = len(buffer_blocks)
                    if idx_end >= len(para_lines) and buffer_blocks[idx_end - len(para_lines) : idx_end] == para_lines:
                        del buffer_blocks[idx_end - len(para_lines) : idx_end]
                        # Build a combined block so it can't be split across chunks.
                        separator = "\n\n" if gap_blanks > 0 else "\n"
                        combined = "\n".join(para_lines) + separator + list_text
                        buffer_blocks.append(combined)
                        i = next_i
                        continue
                    else:
                        # Restore popped blanks; fall back to regular list handling.
                        buffer_blocks.extend([""] * popped_blanks)

                buffer_blocks.append(list_text)
                i = next_i
                continue

        # Regular text line
        buffer_blocks.append(line)
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
