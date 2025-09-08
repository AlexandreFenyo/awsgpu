#!/usr/bin/env python3
"""
Collect all possible French keywords from NDJSON RAG chunks using spaCy.

- Input: NDJSON file (one JSON object per line) with at least:
    {
      "chunk_id": "...",
      "text": "...",
      "headings": {...},
      "heading": {...},
      "full_headings": "...",
      "keywords": ["...", ...],
      "approx_tokens": 123
    }

- Extraction sources:
  - Named entities (spaCy NER)
  - Noun phrases (NPs)
  - 1–3-gram sequences over content tokens (NOUN/PROPN/ADJ)
  - Quoted names: "…", “ … ”, « … »
  - Markdown emphasis: *…*, **…**, _…_, __…__
- Normalization: lowercase + light lemmatization; deduplicated globally.

- Output: all discovered keywords (unique), one per line to stdout.
  By default they are sorted by descending frequency across all chunks, then by length.
  Use --order specificity to sort by the extractor's specificity score instead.

Usage:
  ./src/pipeline-advanced/collect_keywords_from_md.py input.ndjson
  ./src/pipeline-advanced/collect_keywords_from_md.py --order specificity input.ndjson
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Dict, Iterable, List, Tuple


# ----------------------------- Helpers & normalization -----------------------------


def _normalize_tokens(tokens) -> List[str]:
    """
    Normalize tokens: lemma lowercased; drop stops, punctuation, numbers, spaces.
    Prefer content POS (NOUN/PROPN/ADJ), but allow others if is_alpha.
    """
    norm: List[str] = []
    for t in tokens:
        if getattr(t, "is_space", False) or getattr(t, "is_punct", False) or getattr(t, "is_quote", False) or getattr(t, "like_num", False):
            continue
        if getattr(t, "is_stop", False):
            continue
        pos = getattr(t, "pos_", "")
        if not (pos in ("NOUN", "PROPN", "ADJ") or getattr(t, "is_alpha", False)):
            continue
        lemma = (getattr(t, "lemma_", None) or getattr(t, "text", "")).strip().lower()
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


def _extract_quoted_or_markdown_names(text: str, nlp) -> List[str]:
    """
    Extract phrases inside quotes (", “ ”, « ») and Markdown emphasis (*, **, _, __),
    normalize them, and keep up to 1–3 tokens per phrase.
    """
    patterns = [
        r'"([^"\n]{2,})"',
        r'“([^”\n]{2,})”',
        r'«\s*([^»\n]{2,})\s*»',
        r'\*\*([^*\n]{2,})\*\*',
        r'\*([^*\n]{2,})\*',
        r'__([^_\n]{2,})__',
        r'_([^_\n]{2,})_',
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


# ----------------------------- Keyword extraction -----------------------------


def extract_all_keywords_spacy(text: str, nlp, return_scores: bool = False) -> List[str] | List[Tuple[str, float]]:
    """
    Extract as many French keyphrases as possible from text using spaCy.
    If return_scores is True, return a list of (phrase, score) sorted by score desc.
    """
    if not text or not text.strip():
        return []

    doc = nlp(text)

    # Collect candidates with frequency-like weights
    candidates = Counter()

    # Named entities
    for ent in doc.ents:
        toks = _normalize_tokens(ent)
        if 1 <= len(toks) <= 3:
            phrase = " ".join(toks)
            if _valid_phrase(phrase):
                # Slightly stronger weight for product/org/work types
                lbl = (ent.label_ or "").upper()
                weight = 3.0 if lbl in {"ORG", "PRODUCT", "WORK_OF_ART", "MISC"} else 2.0
                candidates[phrase] += weight

    # Noun phrases
    if hasattr(doc, "noun_chunks"):
        for chunk in doc.noun_chunks:
            toks = [t for t in chunk if t.pos_ in ("NOUN", "PROPN", "ADJ") and not (t.is_stop or t.is_punct or t.like_num)]
            toks_norm = _normalize_tokens(toks)
            if not toks_norm:
                continue
            toks_norm = toks_norm[:3]
            if 1 <= len(toks_norm) <= 3:
                phrase = " ".join(toks_norm)
                if _valid_phrase(phrase):
                    candidates[phrase] += 1.5

    # Quoted names and Markdown emphasis
    for phrase in _extract_quoted_or_markdown_names(text, nlp):
        candidates[phrase] += 2.5

    # Frequent 1–3-grams over content tokens
    content_tokens = [t for t in doc if t.pos_ in ("NOUN", "PROPN", "ADJ") and not (t.is_stop or t.is_punct or t.is_space or t.like_num)]
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

    # Return all unique phrases sorted by score desc, then by length
    scored: List[Tuple[str, float]] = []
    for phrase, count in candidates.items():
        length_boost = 0.25 * (len(phrase.split()) - 1)  # prefer bi/tri-grams slightly
        scored.append((phrase, float(count) + length_boost))

    scored.sort(key=lambda x: (x[1], len(x[0])), reverse=True)
    if return_scores:
        return scored
    return [p for p, _ in scored]


# ------------------------------------- CLI ------------------------------------


def _resolve_model_name(choice: str | None) -> str:
    choice = (choice or "").strip().lower()
    if choice in ("lg", "fr_core_news_lg", ""):
        return "fr_core_news_lg"
    if choice in ("md", "fr_core_news_md"):
        return "fr_core_news_md"
    # fallback to lg if unknown
    return "fr_core_news_lg"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect all French keywords from an NDJSON of RAG chunks using spaCy (French)."
    )
    parser.add_argument(
        "input",
        help="Path to input NDJSON file (one JSON object per line).",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="lg",
        choices=["md", "lg", "fr_core_news_md", "fr_core_news_lg"],
        help="spaCy French model to use (default: lg = fr_core_news_lg).",
    )
    parser.add_argument(
        "--order",
        choices=["freq", "specificity"],
        default="freq",
        help="Output order: 'freq' (default, global frequency across chunks) or 'specificity' (highest-scoring phrases first).",
    )
    args = parser.parse_args(argv)

    model_name = _resolve_model_name(args.model)

    try:
        import spacy  # noqa: WPS433
    except Exception:
        print("Error: spaCy is required. Install with: pip install spacy", file=sys.stderr)
        return 2

    try:
        nlp = spacy.load(model_name, disable=[])
    except Exception:
        print(
            f"Error: spaCy model '{model_name}' is not installed.\n"
            f"Install it with: python -m spacy download {model_name}",
            file=sys.stderr,
        )
        return 2

    try:
        inf = open(args.input, "r", encoding="utf-8")
    except Exception as exc:
        print(f"Error: cannot open input file: {exc}", file=sys.stderr)
        return 1

    # Aggregate across all chunks
    global_counter: Counter[str] = Counter()
    best_scores: Dict[str, float] = {}
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
                errors += 1
                continue

            text = obj.get("text", "") or ""
            if not text.strip():
                continue

            if args.order == "freq":
                kws = extract_all_keywords_spacy(text, nlp)
                global_counter.update(kws)
            else:
                # specificity mode: keep the best (highest) score seen per phrase
                scored = extract_all_keywords_spacy(text, nlp, return_scores=True)  # type: ignore[assignment]
                for phrase, score in scored:  # type: ignore[misc]
                    prev = best_scores.get(phrase)
                    if prev is None or score > prev:
                        best_scores[phrase] = float(score)
            processed += 1
    finally:
        inf.close()

    if processed == 0:
        return 1

    # Output unique keywords, one per line
    if args.order == "freq":
        # Sorted by global frequency desc then length
        items: List[Tuple[str, float]] = sorted(
            global_counter.items(),
            key=lambda x: (x[1], len(x[0])),
            reverse=True,
        )
        for phrase, _ in items:
            print(phrase)
    else:
        # Sorted by specificity score desc then length
        items: List[Tuple[str, float]] = sorted(
            best_scores.items(),
            key=lambda x: (x[1], len(x[0])),
            reverse=True,
        )
        for phrase, _ in items:
            print(phrase)

    # Exit 0 even if there were a few malformed lines, as long as we produced output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
