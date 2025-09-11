#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reads an NDJSON file of RAG chunks from a file path or stdin, calls an Ollama model to
extract 20 keywords from each chunk's "text", replaces the "keywords" field with
the extracted list, and writes the updated NDJSON to stdout.

- Ollama host is taken from the environment variable OLLAMA_HOST (hostname or IP).
- The model used is "gpt-oss:20b".
- The prompt is exactly: "Fournis 20 mot-clés à partir du texte suivant: " + text
- The input source file is not modified; output is printed to stdout.
- If the "text" field is empty or only whitespace, no request is made to Ollama and "keywords" is set to [].

Usage:
  python3 src/pipeline-advanced/update_keywords_with_llm.py path/to/input.ndjson > output.ndjson
  # or read from stdin:
  cat input.ndjson | python3 src/pipeline-advanced/update_keywords_with_llm.py > output.ndjson
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import typing as t
from urllib import request, error, parse


MODEL_NAME = "gpt-oss:20b"


def _compute_base_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        host = "localhost"

    # If OLLAMA_HOST already includes a scheme, use it as base.
    if host.startswith("http://") or host.startswith("https://"):
        base = host
    else:
        # Assume default Ollama port
        base = f"http://{host}:11434"

    return base.rstrip("/")


def _ollama_generate(base_url: str, prompt: str, model: str = MODEL_NAME, tries: int = 3, timeout: int = 300) -> str:
    """
    Call Ollama /api/generate with stream=false and return the 'response' text.
    Retries with exponential backoff on temporary failures.
    """
    url = f"{base_url}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "update_keywords_with_llm/1.0",
    }

    last_err: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            try:
                sys.stderr.write(f"voici la requête: {prompt}\n")
            except Exception:
                # Best-effort logging; avoid crashing on encoding issues
                sys.stderr.write("voici la requête: [unprintable]\n")
            req = request.Request(url, data=data, headers=headers, method="POST")
            with request.urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                raw = resp.read().decode(charset, errors="replace")
                obj = json.loads(raw)
                # Expected: {"model": "...", "created_at": "...", "response": "...", ...}
                response_text = t.cast(str, obj.get("response", "")) or ""
                try:
                    sys.stderr.write(f"voici la réponse d'ollama: {response_text}\n")
                except Exception:
                    # Best-effort logging; avoid crashing on encoding issues
                    sys.stderr.write("voici la réponse d'ollama: [unprintable]\n")
                return response_text
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < tries:
                # Exponential backoff with jitter
                time.sleep(min(2 ** (attempt - 1), 8) + (0.1 * attempt))
            else:
                break

    # If all retries failed, surface a clear message on stderr and return empty response.
    sys.stderr.write(f"[update_keywords_with_llm] Ollama request failed after {tries} attempt(s): {last_err}\n")
    return ""


_bullet_or_index_re = re.compile(r"^\s*(?:\d+[\.\)]\s*|[-–•●·]\s*)")
_label_prefix_re = re.compile(r"(?i)^\s*(?:mots?-?\s*clés?|keywords?)\s*:\s*")


def _try_parse_json_array(text: str) -> t.Optional[t.List[str]]:
    """
    Parse the response as a JSON array string of keywords.
    Only accepts responses that are exactly a JSON array (ignoring surrounding whitespace).
    """
    text = text.strip()
    try:
        arr = json.loads(text)
        if isinstance(arr, list):
            return [str(x) for x in arr]
    except json.JSONDecodeError:
        pass
    return None


def _normalize_keyword(s: str) -> str:
    s = s.strip()
    # Remove label like "Mots-clés: " at start if present
    s = _label_prefix_re.sub("", s)
    # Remove bullet/index prefixes like "1. ", "- ", "• "
    s = _bullet_or_index_re.sub("", s)
    # Strip surrounding quotes and common trailing punctuation
    s = s.strip().strip(" \t\r\n\"'.,;:()[]{}")
    # Collapse inner whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def _extract_keywords_from_response(resp_text: str, max_keywords: int = 20) -> t.List[str]:
    """
    Parse the LLM response strictly as a JSON array string into up to max_keywords keywords.
    """
    if not resp_text:
        return []

    # 1) Try JSON array
    arr = _try_parse_json_array(resp_text)
    if arr is not None:
        items = arr
    else:
        # Not a JSON array; return empty list
        items = []

    cleaned: t.List[str] = []
    seen: set[str] = set()
    for raw in items:
        kw = _normalize_keyword(str(raw))
        if not kw:
            continue
        low = kw.lower()
        if low in seen:
            continue
        seen.add(low)
        cleaned.append(kw)
        if len(cleaned) >= max_keywords:
            break

    return cleaned


def _build_prompt(text: str) -> str:
    return f"Fournis 20 mot-clés, chacun au format 'chaîne de caractères d'un tableau JSON', extraits du texte suivant, chacun étant composé de un à trois mots qui se suivent dans ce texte, sans modification, et s'il y a un article au début de ces trois mots, ne l'affiche pas : {text}"


def _process_obj(obj: dict, base_url: str) -> dict:
    text = obj.get("text", "")
    if not isinstance(text, str):
        text = str(text)

    # If text is empty or whitespace, do not call Ollama; set empty keywords.
    if not text.strip():
        obj["keywords"] = []
        return obj

    prompt = _build_prompt(text)
    resp = _ollama_generate(base_url, prompt)
    keywords = _extract_keywords_from_response(resp, max_keywords=20)

    # Replace keywords unconditionally (clear previous then set)
    obj["keywords"] = keywords
    return obj


def _iter_lines(fp: io.TextIOBase) -> t.Iterator[str]:
    for line in fp:
        yield line


def main(argv: t.List[str]) -> int:
    base_url = _compute_base_url()

    # Input: file path argument or stdin if none.
    if len(argv) >= 2 and argv[1] != "-":
        in_path = argv[1]
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                for line in _iter_lines(f):
                    if not line.strip():
                        # Preserve blank lines if present
                        sys.stdout.write(line)
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            updated = _process_obj(obj, base_url)
                            sys.stdout.write(json.dumps(updated, ensure_ascii=False) + "\n")
                        else:
                            # Not an object, pass through unchanged
                            sys.stdout.write(line)
                    except json.JSONDecodeError:
                        # Not valid JSON line, pass through unchanged
                        sys.stdout.write(line)
        except FileNotFoundError:
            sys.stderr.write(f"[update_keywords_with_llm] File not found: {in_path}\n")
            return 1
        except OSError as e:
            sys.stderr.write(f"[update_keywords_with_llm] Could not read file {in_path}: {e}\n")
            return 1
    else:
        # Read from stdin
        data_in = sys.stdin
        for line in _iter_lines(data_in):
            if not line.strip():
                sys.stdout.write(line)
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    updated = _process_obj(obj, base_url)
                    sys.stdout.write(json.dumps(updated, ensure_ascii=False) + "\n")
                else:
                    sys.stdout.write(line)
            except json.JSONDecodeError:
                sys.stdout.write(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
