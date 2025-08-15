#!/usr/bin/env python3

import argparse
import sys
import os
from markitdown import MarkItDown
from openai import OpenAI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a document to MarkDown.")
    parser.add_argument("file", help="Path to the file to convert")
    args = parser.parse_args(argv)

    # clé d'API pour conversion des images
    client = OpenAI(api_key=os.environ['OPENAIAPIKEY'])
    md = MarkItDown(llm_client=client, llm_model="gpt-4o")

    result = md.convert(args.file)
    print(result.text_content)

    # Write the rendered document to a .md file
    text_path = args.file + ".md"
    with open(text_path, "w", encoding="utf-8") as fh:
        fh.write(result.text_content)
    # Also print a short message to stderr about chunks and text file locations
    print(f"Text written: {text_path}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

