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

Each result line includes:
  { chunk_id, text, distance, approx_tokens, keywords, headings, heading, full_headings, created_at }
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List
import os

import numpy as np
import sentence_transformers
from sentence_transformers import SentenceTransformer

try:
    import weaviate
    from weaviate.classes.query import MetadataQuery
    from weaviate.collections.classes.grpc import QueryNested
except Exception as exc:
    print("Error: weaviate-client is required. Install with: pip install weaviate-client", file=sys.stderr)
    raise


_MODEL_NAME = "paraphrase-xlm-r-multilingual-v1"


def _connect_local():
    # Connect to a local Weaviate (default URL/env). Adjust here if needed.
    weaviate_host = os.environ.get("WEAVIATE_HOST")
    if weaviate_host:
        return weaviate.connect_to_local(host=weaviate_host)
    else:
        # Pas d'URL fournie, on utilise la connexion locale par défaut
        return weaviate.connect_to_local()

    
def _embed_query(text: str) -> List[float]:
    model = SentenceTransformer(_MODEL_NAME)
    vec = model.encode([text], convert_to_numpy=True, show_progress_bar=False)
    if isinstance(vec, list):
        emb = [float(x) for x in vec[0]]
    elif isinstance(vec, np.ndarray):
        emb = vec[0].astype(float).tolist()
    else:
        emb = [float(x) for x in np.array(vec)[0].astype(float).tolist()]
    return emb


def search_weaviate(query: str, limit: int = 50, collection_name: str = "rag_chunks") -> List[Dict[str, Any]]:
    vector = _embed_query(query)

    client = _connect_local()
    try:
        coll = client.collections.get(collection_name)

        results = coll.query.near_vector(
            near_vector=vector,
            limit=limit,
            target_vector="text",
            return_properties=[
                "chunk_id",
                "text",
                "approx_tokens",
                "keywords",
                "created_at",
                QueryNested(name="headings", properties=["h1", "h2", "h3", "h4", "h5", "h6"]),
                QueryNested(name="heading", properties=["h1", "h2", "h3", "h4", "h5", "h6"]),
                "full_headings",
            ],
            return_metadata=MetadataQuery(distance=True),
        )

        out: List[Dict[str, Any]] = []
        for obj in results.objects or []:
            props = obj.properties or {}
            out.append(
                {
                    "chunk_id": props.get("chunk_id"),
                    "text": props.get("text"),
                    "distance": getattr(obj.metadata, "distance", None),
                    "approx_tokens": props.get("approx_tokens"),
                    "keywords": props.get("keywords"),
                    "headings": props.get("headings"),
                    "heading": props.get("heading"),
                    "full_headings": props.get("full_headings"),
                    "created_at": props.get("created_at"),
                }
            )
        return out
    finally:
        client.close()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search nearest chunks in Weaviate using a text query.")
    parser.add_argument("query", help="Text query to search for nearest chunks")
    parser.add_argument(
        "-k",
        "--limit",
        type=int,
        default=50,
        help="Number of nearest chunks to retrieve (default: 50)",
    )
    parser.add_argument(
        "-c",
        "--collection-name",
        default="rag_chunks",
        help='Weaviate collection name to query (default: "rag_chunks")',
    )
    args = parser.parse_args(argv)

    try:
        results = search_weaviate(args.query, limit=args.limit, collection_name=args.collection_name)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for rec in results:
        print(json.dumps(rec, ensure_ascii=False, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
