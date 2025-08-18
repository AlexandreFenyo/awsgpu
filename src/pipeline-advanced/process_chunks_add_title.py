#!/usr/bin/env python3
"""
Process an NDJSON file of chunks and, for each line, prefix the text field
with the deepest available heading (h1..h6) followed by a blank line delimiter.

- Input: path to an NDJSON file where each line is a JSON object with at least:
    - "text": the chunk text
    - "headings": an object possibly containing keys "h1".."h6"
- Output: a new NDJSON file written to: <input_path> + ".embeddings.ndjson"
- The script prints the output file path on stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional


DELIMITER = "\n\n"


def _deepest_heading_text(headings: Any) -> Optional[str]:
    """
    Given a headings mapping like {"h1": "...", "h3": "...", ...},
    return the text for the deepest heading (largest numeric suffix).
    If no valid heading is found, return None.
    """
    if not isinstance(headings, dict):
        return None

    best_level = -1
    best_text: Optional[str] = None

    for key, value in headings.items():
        if not isinstance(key, str):
            continue
        if not key.startswith("h"):
            continue
        try:
            level = int(key[1:])
        except (ValueError, TypeError):
            continue
        if 1 <= level <= 6 and isinstance(value, str) and value.strip():
            if level > best_level:
                best_level = level
                best_text = value.strip()

    return best_text


def process_file(input_path: str) -> str:
    """
    Read NDJSON from input_path, modify each JSON object by prefixing "text"
    with the deepest heading + DELIMITER if a heading exists, and write the
    result to input_path + ".embeddings.ndjson". Return the output path.
    """
    output_path = input_path + ".embeddings.ndjson"

    with open(input_path, "r", encoding="utf-8") as fin, open(
        output_path, "w", encoding="utf-8", newline="\n"
    ) as fout:
        for line in fin:
            # Preserve empty/whitespace-only lines as-is
            if not line.strip():
                fout.write(line)
                continue

            try:
                obj: Dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                # If a line is not valid JSON, pass it through unchanged
                fout.write(line)
                continue

            text = obj.get("text")
            headings = obj.get("headings")
            deepest = _deepest_heading_text(headings)

            if isinstance(text, str) and deepest:
                obj["text"] = f"{deepest}{DELIMITER}{text}"

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    return output_path


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prefix each chunk text with its deepest heading and write to <input>.embeddings.ndjson"
    )
    parser.add_argument("input_path", help="Path to the input NDJSON file")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    out = process_file(args.input_path)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
