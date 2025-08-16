#!/usr/bin/env python3
"""
Convert an input file to Markdown using the MarkItDown library.

- Takes an input filename as a positional argument.
- Produces a Markdown file named "<input>.md" in the same directory.
- Prints the produced output filename to stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from markitdown import MarkItDown


def convert_to_markdown(input_path: str) -> str:
    """
    Convert the given file to Markdown and write it to <input>.md.

    Returns the output file path as a string.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    # Output name is the input filename plus the ".md" suffix
    out_path = f"{input_path}.md"

    md = MarkItDown()
    result = md.convert(str(src))

    # Prefer the markdown text_content if available
    text = getattr(result, "text_content", None)
    if text is None:
        # Fallback: stringify the result
        text = str(result)

    Path(out_path).write_text(text, encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a file to Markdown using MarkItDown."
    )
    parser.add_argument("input", help="Path to the input file")
    args = parser.parse_args(argv)

    try:
        produced = convert_to_markdown(args.input)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(produced)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
