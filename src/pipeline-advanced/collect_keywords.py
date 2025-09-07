#!/usr/bin/env python3
"""
Rewrite keywords for RAG chunks in an NDJSON file using spaCy (French).

- Input: NDJSON file (one JSON object per line) with fields like:
    {
      "chunk_id": "...",
      "text": "...",
      "headings": {...},
      "heading": {...},
      "full_headings": "...",
      "keywords": ["...", ...],
      "approx_tokens": 123
    }
- Output: NDJSON to stdout (or to a file via -o) with the same objects but
  "keywords" replaced by ~6–8 normalized keyphrases extracted from "text".

Keyphrase extraction:
- Uses spaCy French model (choose: fr_core_news_md or fr_core_news_lg).
- Candidates from:
  - Named entities (doc.ents)
  - Noun phrases (doc.noun_chunks)
  - Quoted names (between "…" or « … »)
  - Frequent 1–3-gram sequences of NOUN/PROPN/ADJ tokens
- Normalization: lowercase + light lemmatization; de-duplicates.

Usage:
  ./src/pipeline-advanced/collect_keywords.py input.ndjson > output.ndjson
  ./src/pipeline-advanced/collect_keywords.py -m lg input.ndjson -o output.ndjson
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Iterable, List, Tuple

# ----------------------------- Keyword extraction -----------------------------


def _normalize_tokens(tokens) -> List[str]:
    """
    Normalize tokens: lemma lowercased; drop stops, punctuation, numbers, spaces.
    Prefer content POS (NOUN/PROPN/ADJ), but allow others if is_alpha.
    """
    norm: List[str] = []
    for t in tokens:
        if t.is_space or t.is_punct or t.is_quote or t.like_num:
            continue
        if t.is_stop:
            continue
        if not (t.pos_ in ("NOUN", "PROPN", "ADJ") or t.is_alpha):
            continue
        lemma = (t.lemma_ or t.text).strip().lower()
        if not lemma:
            continue
        norm.append(lemma)
    return norm


def _sliding_ngrams(tokens: List, n: int) -> Iterable[List]:
    for i in range(0, len(tokens) - n + 1):
        yield tokens[i : i + n]


def _valid_phrase(s: str) -> bool:
    # At least 3 alphabetic chars total; avoid overly short or trivial items
    compact = s.replace(" ", "")
    return len(compact) >= 3


def _extract_quoted_names(text: str, nlp) -> List[str]:
    """
    Extract phrases that appear inside quotes (", “ ”, « »), normalize them,
    and keep up to 1–3 tokens per phrase.
    """
    patterns = [
        r'"([^"\n]{2,})"',
        r'“([^”\n]{2,})”',
        r'«\s*([^»\n]{2,})\s*»',
    ]
    phrases: List[str] = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            raw = (m.group(1) or "").strip()
            if len(raw) < 2:
                continue
            # Use full pipeline to get lemmas/stopwords/pos
            doc = nlp(raw)
            toks_norm = _normalize_tokens(doc)
            if not toks_norm or len(toks_norm) > 3:
                continue
            phrase = " ".join(toks_norm)
            if _valid_phrase(phrase):
                phrases.append(phrase)
    return phrases


def extract_keywords_spacy(text: str, nlp, min_kw: int = 6, max_kw: int = 8) -> List[str]:
    """
    Extract ~min_kw..max_kw French keyphrases from text using spaCy.
    """
    if not text or not text.strip():
        return []

    doc = nlp(text)

    # Seed candidates from named entities and noun chunks
    candidates = Counter()
    ent_set = set()
    np_set = set()

    # Named entities
    for ent in doc.ents:
        toks = _normalize_tokens(ent)
        if 1 <= len(toks) <= 3:
            phrase = " ".join(toks)
            if _valid_phrase(phrase):
                lbl = (ent.label_ or "").upper()
                weight = 3.0 if lbl in {"ORG", "PRODUCT", "WORK_OF_ART", "MISC"} else 2.0
                candidates[phrase] += weight  # stronger weight for product/org-like entities
                ent_set.add(phrase)

    # Noun phrases
    if hasattr(doc, "noun_chunks"):
        for chunk in doc.noun_chunks:
            toks = [t for t in chunk if t.pos_ in ("NOUN", "PROPN", "ADJ") and not (t.is_stop or t.is_punct or t.like_num)]
            toks_norm = _normalize_tokens(toks)
            if not toks_norm:
                continue
            # Limit to 3 tokens
            toks_norm = toks_norm[:3]
            if 1 <= len(toks_norm) <= 3:
                phrase = " ".join(toks_norm)
                if _valid_phrase(phrase):
                    candidates[phrase] += 1.5
                    np_set.add(phrase)

    # Quoted names (e.g., "…", “…”, « … »)
    for phrase in _extract_quoted_names(text, nlp):
        candidates[phrase] += 2.5

    # Frequent 1–3-grams over content tokens
    content_tokens = [t for t in doc if t.pos_ in ("NOUN", "PROPN", "ADJ") and not (t.is_stop or t.is_punct or t.is_space or t.like_num)]
    content_norm = [w for w in _normalize_tokens(content_tokens)]
    for n in (1, 2, 3):
        for win in _sliding_ngrams(content_tokens, n):
            toks_norm = _normalize_tokens(win)
            if not toks_norm:
                continue
            phrase = " ".join(toks_norm)
            if not _valid_phrase(phrase):
                continue
            candidates[phrase] += 1.0  # frequency-driven

    if not candidates:
        return []

    # Final scoring: base count + slight boost for longer phrases
    scored: List[Tuple[str, float]] = []
    for phrase, count in candidates.items():
        length_boost = 0.25 * (len(phrase.split()) - 1)  # prefer bi/tri-grams slightly
        scored.append((phrase, float(count) + length_boost))

    # Sort by score desc, then by length desc for tie-breaking
    scored.sort(key=lambda x: (x[1], len(x[0])), reverse=True)

    # Deduplicate and pick top ~max_kw (ensure >= min_kw if available)
    selected: List[str] = []
    seen = set()
    for phrase, _ in scored:
        if phrase in seen:
            continue
        seen.add(phrase)
        selected.append(phrase)
        if len(selected) >= max_kw:
            break

    # If we have fewer than min_kw and more available, keep adding
    if len(selected) < min_kw:
        for phrase, _ in scored:
            if phrase in seen:
                continue
            seen.add(phrase)
            selected.append(phrase)
            if len(selected) >= min_kw:
                break

    return selected


# ------------------------------------- CLI ------------------------------------


def _resolve_model_name(choice: str) -> str:
    choice = (choice or "").strip().lower()
    if choice in ("lg", "fr_core_news_lg"):
        return "fr_core_news_lg"
    # default to md
    return "fr_core_news_md"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replace 'keywords' in an NDJSON of RAG chunks using spaCy (French)."
    )
    parser.add_argument(
        "input",
        help="Path to input NDJSON file (one JSON object per line).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Path to output NDJSON file (default: stdout).",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="md",
        choices=["md", "lg", "fr_core_news_md", "fr_core_news_lg"],
        help="spaCy French model to use: md (default) or lg.",
    )
    parser.add_argument(
        "--min",
        type=int,
        default=6,
        help="Minimum number of keywords to keep per chunk (default: 6).",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=8,
        help="Maximum number of keywords to keep per chunk (default: 8).",
    )
    args = parser.parse_args(argv)

    model_name = _resolve_model_name(args.model)

    try:
        import spacy  # noqa: WPS433 (import inside function to allow help/--version without deps)
    except Exception as exc:
        print("Error: spaCy is required. Install with: pip install spacy", file=sys.stderr)
        return 2

    try:
        nlp = spacy.load(model_name, disable=[])
    except Exception as exc:
        print(
            f"Error: spaCy model '{model_name}' is not installed.\n"
            f"Install it with: python -m spacy download {model_name}",
            file=sys.stderr,
        )
        return 2

    # Open IO
    out_is_stdout = args.output == "-" or args.output == ""
    try:
        inf = open(args.input, "r", encoding="utf-8")
    except Exception as exc:
        print(f"Error: cannot open input file: {exc}", file=sys.stderr)
        return 1

    outf = sys.stdout if out_is_stdout else open(args.output, "w", encoding="utf-8")

    processed = 0
    errors = 0
    try:
        for line in inf:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                # Skip malformed line but keep going
                errors += 1
                continue

            text = obj.get("text", "") or ""
            kws = extract_keywords_spacy(text, nlp, min_kw=max(0, args.min), max_kw=max(args.min, args.max))
            obj["keywords"] = kws

            outf.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
            processed += 1
    finally:
        inf.close()
        if not out_is_stdout:
            outf.close()

    return 0 if processed > 0 and errors == 0 else (0 if processed > 0 else 1)


if __name__ == "__main__":
    raise SystemExit(main())
