#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse a .docx file (python-docx) and print a plain-text representation to stdout.
Additionally, produce a JSONL chunks file next to the input file suitable for
creating embeddings / RAG.

Behavior:
 - Accept a single positional argument: path to a .docx file.
 - Preserve heading levels (Heading 1 -> "# ", Heading 2 -> "## ", ...).
 - Convert lists to lines prefixed with "- ".
 - Convert tables to text rows with " | " between cells.
 - Strip formatting; output only plain text.
 - Preserve the document reading order.
 - Produce a <input>.chunks.jsonl file with one JSON object per chunk:
     { "chunk_id": int, "text": str, "metadata": { "source": str, "headings": [...], "keywords": [...] }, "approx_tokens": int }

Usage:
  parse-word.py document.docx
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from typing import Iterator, List, Tuple, Union

try:
    from docx import Document
    from docx.text.paragraph import Paragraph
    from docx.table import Table
except Exception as exc:  # pragma: no cover - runtime dependency error
    print("Error: python-docx is required. Install with: pip install python-docx", file=sys.stderr)
    print(f"Detail: {exc}", file=sys.stderr)
    raise SystemExit(2)


def iter_block_items(doc: Document) -> Iterator[Union[Paragraph, Table]]:
    """
    Yield Paragraph or Table objects in document order.
    """
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)


_heading_re = re.compile(r"heading\s*(\d+)", re.IGNORECASE)


def paragraph_is_list(paragraph: Paragraph) -> bool:
    """
    Heuristically detect whether a paragraph is part of a list.
    """
    style_name = ""
    try:
        style_name = paragraph.style.name or ""
    except Exception:
        style_name = ""
    name = style_name.lower()
    print(f"XXXXX: {name}", file=sys.stdout)
    if "list" in name or "bullet" in name or "number" in name or "puce" in name:
        return True
    try:
        pPr = getattr(paragraph._p, "pPr", None)
        if pPr is not None and getattr(pPr, "numPr", None) is not None:
            return True
    except Exception:
        pass
    return False


def render_table(tbl: Table) -> str:
    """
    Convert a docx Table to plain text: rows separated by newline,
    cells in a row separated by " | ".
    """
    lines: list[str] = []
    for row in tbl.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def analyze_paragraph(paragraph: Paragraph) -> Tuple[str, str, int]:
    """
    Return (text, style_name, heading_level)
    heading_level is 0 if not a heading.
    """
    text = paragraph.text.strip()
    style_name = ""
    try:
        style_name = paragraph.style.name or ""
    except Exception:
        style_name = ""
    # Heading detection
    m = _heading_re.search(style_name)
    if m:
        try:
            level = int(m.group(1))
            level = max(1, min(6, level))
        except Exception:
            level = 1
        return text, style_name, level
    m2 = re.search(r"titre\s*(\d+)", style_name, re.IGNORECASE)
    if m2:
        try:
            level = int(m2.group(1))
            level = max(1, min(6, level))
        except Exception:
            level = 1
        return text, style_name, level
    if paragraph_is_list(paragraph):
        return text, style_name, 0
    return text, style_name, 0


def parse_docx_to_blocks(path: str) -> List[Tuple[str, str, int]]:
    """
    Parse the document and return a list of blocks.
    Each block is a tuple (kind, text, heading_level) where kind is one of:
      - "paragraph"
      - "table"
      - "heading" (treated as paragraph with heading_level>0)
    """
    doc = Document(path)
    blocks: list[Tuple[str, str, int]] = []
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            text, style_name, level = analyze_paragraph(block)
            if not text:
                continue
            kind = "heading" if level > 0 else "paragraph"
            blocks.append((kind, text, level))
        elif isinstance(block, Table):
            tbl_text = render_table(block)
            if tbl_text:
                blocks.append(("table", tbl_text, 0))
    return blocks


# Small stopword list to get keywords without extra dependencies
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "these", "those",
    "are", "was", "were", "has", "have", "had", "but", "not",
    "you", "your", "yours", "from", "they", "their", "them",
    "a", "an", "in", "on", "of", "to", "is", "it", "as", "be",
    "by", "or", "if", "we", "our", "us"
}


def approx_tokens_for_text(text: str) -> int:
    """
    Approximate number of tokens from number of words.
    Rough heuristic: 1 token ~= 0.75 words => tokens ~= words / 0.75 = words * 1.333
    """
    words = re.findall(r"\w+", text)
    return max(1, int(len(words) * 1.333))


def extract_keywords(text: str, top_n: int = 5) -> List[str]:
    words = [w.lower() for w in re.findall(r"\w+", text) if len(w) > 2]
    filtered = [w for w in words if w not in _STOPWORDS]
    if not filtered:
        return []
    counts = Counter(filtered)
    most = [w for w, _ in counts.most_common(top_n)]
    return most


def build_chunks(blocks: List[Tuple[str, str, int]], source: str, chunk_size_tokens: int = 200) -> List[dict]:
    """
    Build chunks from blocks. A chunk will not cross heading boundaries.
    Each chunk is a dict with keys: chunk_id, text, metadata, approx_tokens
    """
    chunks: list[dict] = []
    current_headings: List[str] = []
    accumulator_lines: List[str] = []
    accumulator_tokens = 0
    chunk_id = 0

    def emit_current_chunk():
        nonlocal chunk_id, accumulator_lines, accumulator_tokens
        if not accumulator_lines:
            return
        text = "\n\n".join(accumulator_lines).strip()
        approx_tokens = approx_tokens_for_text(text)
        keywords = extract_keywords(text, top_n=5)
        metadata = {"source": os.path.basename(source), "headings": list(current_headings), "keywords": keywords}
        chunks.append({
            "chunk_id": chunk_id,
            "text": text,
            "metadata": metadata,
            "approx_tokens": approx_tokens,
            "char_length": len(text)
        })
        chunk_id += 1
        accumulator_lines = []
        accumulator_tokens = 0

    for kind, text, level in blocks:
        if kind == "heading":
            # heading -> start a new chunk boundary (emit previous chunk)
            # update headings stack
            # Pop to level-1 and append current heading
            while len(current_headings) >= level:
                current_headings.pop()
            current_headings.append(text)
            # Emitting previous chunk to ensure chunks don't cross headings
            emit_current_chunk()
            # Optionally we can create a tiny chunk containing the heading itself if desired.
            # Here we'll include heading as context (not emitting single-heading chunk).
            continue

        # For paragraph or table: add to accumulator. If adding exceeds chunk_size_tokens, emit previous chunk first.
        added_tokens = approx_tokens_for_text(text)
        if accumulator_lines and (accumulator_tokens + added_tokens > chunk_size_tokens):
            emit_current_chunk()
        accumulator_lines.append(text)
        accumulator_tokens += added_tokens

    # Emit any remaining
    emit_current_chunk()
    return chunks


def write_chunks_jsonl(chunks: List[dict], outpath: str) -> None:
    with open(outpath, "w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse a .docx file and print plain text and produce chunks JSONL.")
    parser.add_argument("docx", help="Path to the .docx file to parse")
    parser.add_argument("--chunk-size", type=int, default=200, help="Approx target tokens per chunk (default: 200)")
    args = parser.parse_args(argv)

    try:
        # parse into blocks, render text for stdout, and build chunks
        blocks = parse_docx_to_blocks(args.docx)
        out_text = []
        for kind, text, level in blocks:
            if kind == "heading":
                lvl = max(1, min(6, level))
                out_text.append(f"{'#' * lvl} {text}")
            elif kind == "table":
                out_text.append(text)
            else:
                out_text.append(text if not text.startswith("- ") else text)
        full_text = "\n\n".join(out_text)

        # Build chunks and write JSONL file next to input
        chunks = build_chunks(blocks, source=args.docx, chunk_size_tokens=args.chunk_size)
        chunks_path = args.docx + ".chunks.jsonl"
        write_chunks_jsonl(chunks, chunks_path)
    except Exception as exc:
        print(f"Error parsing {args.docx}: {exc}", file=sys.stderr)
        return 2

    # Write the rendered document to a .txt file next to the input (do not print the parsed text to stdout)
    text_path = args.docx + ".txt"
    with open(text_path, "w", encoding="utf-8") as fh:
        fh.write(full_text)
    # Also print a short message to stderr about chunks and text file locations
    print(f"Chunks written: {chunks_path} (count={len(chunks)})", file=sys.stderr)
    print(f"Text written: {text_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
