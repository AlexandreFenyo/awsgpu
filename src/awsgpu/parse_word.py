#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse a .docx file (python-docx) and print a plain-text representation to stdout.

Behavior:
 - Accept a single positional argument: path to a .docx file.
 - Preserve heading levels (Heading 1 -> "# ", Heading 2 -> "## ", ...).
 - Convert lists to lines prefixed with "- ".
 - Convert tables to text rows with " | " between cells.
 - Strip formatting; output only plain text.
 - Preserve the document reading order.

Usage:
  parse-word.py document.docx
"""
from __future__ import annotations

import argparse
import re
import sys
from typing import Iterator, Union

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
    # Access the document body element and iterate its children so that
    # paragraphs and tables appear in the original order.
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
    Checks paragraph style name and numbering properties (if present).
    """
    style_name = ""
    try:
        style_name = paragraph.style.name or ""
    except Exception:
        style_name = ""
    name = style_name.lower()
    if "list" in name or "bullet" in name or "number" in name:
        return True
    # Try to detect numbering from the underlying XML (may not be present)
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


def render_paragraph(paragraph: Paragraph) -> str:
    """
    Render a paragraph considering style (heading, list, normal).
    """
    text = paragraph.text.strip()
    if not text:
        return ""
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
        return "{} {}".format("#" * level, text)
    # Another heuristic: style name starting with "Titre" (French) + number
    m2 = re.search(r"titre\s*(\d+)", style_name, re.IGNORECASE)
    if m2:
        try:
            level = int(m2.group(1))
            level = max(1, min(6, level))
        except Exception:
            level = 1
        return "{} {}".format("#" * level, text)
    # List detection
    if paragraph_is_list(paragraph):
        return "- " + text
    # Fallback normal paragraph
    return text


def parse_docx_to_text(path: str) -> str:
    """
    Parse the document and return a plain-text representation.
    """
    doc = Document(path)
    parts: list[str] = []
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            rendered = render_paragraph(block)
            if rendered:
                parts.append(rendered)
        elif isinstance(block, Table):
            tbl_text = render_table(block)
            if tbl_text:
                parts.append(tbl_text)
    # Join with double newlines between blocks for readability
    return "\n\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse a .docx file and print plain text.")
    parser.add_argument("docx", help="Path to the .docx file to parse")
    args = parser.parse_args(argv)

    try:
        out = parse_docx_to_text(args.docx)
    except Exception as exc:
        print(f"Error parsing {args.docx}: {exc}", file=sys.stderr)
        return 2

    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
