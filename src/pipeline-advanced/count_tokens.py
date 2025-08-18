#!/usr/bin/env python3
"""
Count tokens for text read from STDIN using the Hugging Face tokenizer
for the openai/gpt-oss-20b model (or another specified model).

Usage examples:
  echo "Bonjour le monde" | python src/pipeline-advanced/count_tokens.py
  echo "Bonjour le monde" | python src/pipeline-advanced/count_tokens.py --model openai/gpt-oss-20b
  echo "Texte" | python src/pipeline-advanced/count_tokens.py --no-special

By default, special tokens (e.g., BOS/EOS) are included in the count.
Use --no-special to exclude them.
"""
from typing import Optional, List
import sys
import argparse

try:
    from transformers import AutoTokenizer  # type: ignore
except Exception as e:  # pragma: no cover
    AutoTokenizer = None  # type: ignore


def _load_tokenizer(model_name: str):
    if AutoTokenizer is None:
        raise RuntimeError(
            "transformers is not installed. Install it with: pip install transformers"
        )
    # trust_remote_code=True to support custom tokenizer logic if provided by the model
    return AutoTokenizer.from_pretrained(
        model_name,
        use_fast=True,
        trust_remote_code=True,
    )


def count_tokens(text: str, model_name: str = "openai/gpt-oss-20b", add_special_tokens: bool = True) -> int:
    tokenizer = _load_tokenizer(model_name)
    # Use encode to directly control add_special_tokens behavior
    input_ids = tokenizer.encode(text, add_special_tokens=add_special_tokens)
    return len(input_ids)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Count tokens from STDIN using a Hugging Face tokenizer (default: openai/gpt-oss-20b)."
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-oss-20b",
        help="Hugging Face model ID to use for tokenization (default: openai/gpt-oss-20b).",
    )
    parser.add_argument(
        "--no-special",
        action="store_true",
        help="Do not include special tokens (like BOS/EOS) in the count.",
    )
    args = parser.parse_args(argv)

    if sys.stdin.isatty():
        sys.stderr.write("No input on STDIN. Pipe text into this program.\n")
        return 2

    data = sys.stdin.read()
    # Normalize line endings; tokenizers are robust to whitespace, but keep as-is otherwise
    add_special = not args.no_special

    try:
        n_tokens = count_tokens(data, model_name=args.model, add_special_tokens=add_special)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    print(n_tokens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
