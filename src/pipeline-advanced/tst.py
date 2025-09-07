#!/usr/bin/env python3
"""
Search nearest chunks in Weaviate using a text query.

- Connects to a local Weaviate instance (gRPC + REST).
- Embeds the input text query with sentence-transformers
  ('paraphrase-xlm-r-multilingual-v1').
- Runs a vector search against the stored embeddings (vectorizer = none).
- Prints results to stdout, one JSON object per line.

Usage:
  ./src/pipeline-advanced/search_chunks.py "your query text"
  ./src/pipeline-advanced/search_chunks.py -k 25 -c rag_chunks "contrat de maintenance"
  ./src/pipeline-advanced/search_chunks.py -l 2 "recherche sur les titres H2"

Each result line includes:
  { chunk_id, text, distance, approx_tokens, keywords, headings, created_at }
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

import numpy as np
import sentence_transformers
from sentence_transformers import SentenceTransformer

