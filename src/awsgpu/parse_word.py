#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# GOALS: parse a docx file. AI

# Je veux parser un Docx pour créer des chunks et les utiliser pour du RAG. Les chunks ont une taille d'environ 200 tokens.
# Un fichier Docx est parsé comme ceci :
# - Les différents niveaux de titres et sections sont présentes dans les metadata de contexte des chunks.
# - Les mots clés importants du chunk sont présentes dans les metadata de contexte des chunks.
# - Un chunk n'est jamais à cheval entre plusieurs niveaux de titres ou sections.
# - Les listes sont transformées en listes à tirets.
# - Les tableaux sont transformés en un texte qui correspond au même contenu.
# - Les mises en forme sont supprimées.
# Je ne veux pas d'autres raffinements.
# Je veux utiliser python-docx, avec tiktoken et keybert, pour programmer cela.

"""
Placeholder for src/awsgpu/parse-word.py

poetry run parse-word --help

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
