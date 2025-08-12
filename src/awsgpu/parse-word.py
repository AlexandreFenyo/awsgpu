#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Placeholder for src/awsgpu/parse-word.py

This file is currently a stub. Please tell me what the script should do.
Common options I can implement:
 - extract text from .docx files (python-docx or zip+xml fallback)
 - convert .docx to plain text or JSON paragraphs
 - process multiple files in a directory
 - support stdin/stdout, --out, --format flags

Reply with the desired behavior and I'll implement it.

For now this script prints a short help message and exits with a non-zero code
to indicate it's not yet implemented.
"""
from __future__ import annotations

import sys

def main(argv: list[str] | None = None) -> int:
    print("src/awsgpu/parse-word.py is a stub. Please tell me what to implement.", file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print("  - extract text from a .docx file to stdout", file=sys.stderr)
    print("  - write paragraphs as JSON with --format json", file=sys.stderr)
    print("  - process a directory of .docx files", file=sys.stderr)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
