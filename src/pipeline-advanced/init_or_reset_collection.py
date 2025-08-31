#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import os

try:
    import weaviate
    from weaviate.classes.config import Configure, Property, DataType
except Exception as exc:
    print("Error: weaviate-client is required. Install with: pip install weaviate-client", file=sys.stderr)
    raise


def _connect_local():
    # Connect to a local Weaviate (default URL/env). Adjust here if needed.
    weaviate_host = os.environ.get("WEAVIATE_HOST")
    if weaviate_host:
        return weaviate.connect_to_local(host=weaviate_host)
    else:
        # Pas d'URL fournie, on utilise la connexion locale par défaut
        return weaviate.connect_to_local()


def _ensure_collection(client, name: str):
    """
    Ensure a collection exists with vectorizer disabled and an appropriate schema.

    If recreate is True, delete any existing collection and create it fresh with the expected schema.
    If recreate is False, attempt to use the existing collection; if it doesn't exist, create it.
    """
    props = [
        Property(name="chunk_id", data_type=DataType.TEXT),
        Property(name="text", data_type=DataType.TEXT),
        Property(name="approx_tokens", data_type=DataType.INT),
        Property(name="keywords", data_type=DataType.TEXT_ARRAY),
        Property(name="created_at", data_type=DataType.TEXT),
        Property(
            name="model",
            data_type=DataType.OBJECT,
            nested_properties=[
                Property(name="name", data_type=DataType.TEXT),
                Property(name="version", data_type=DataType.TEXT),
            ],
        ),
        Property(
            name="headings",
            data_type=DataType.OBJECT,
            nested_properties=[
                Property(name="h1", data_type=DataType.TEXT),
                Property(name="h2", data_type=DataType.TEXT),
                Property(name="h3", data_type=DataType.TEXT),
                Property(name="h4", data_type=DataType.TEXT),
                Property(name="h5", data_type=DataType.TEXT),
                Property(name="h6", data_type=DataType.TEXT),
            ],
        ),
        Property(
            name="heading",
            data_type=DataType.OBJECT,
            nested_properties=[
                Property(name="h1", data_type=DataType.TEXT),
                Property(name="h2", data_type=DataType.TEXT),
                Property(name="h3", data_type=DataType.TEXT),
                Property(name="h4", data_type=DataType.TEXT),
                Property(name="h5", data_type=DataType.TEXT),
                Property(name="h6", data_type=DataType.TEXT),
            ],
        ),
        Property(name="full_headings", data_type=DataType.TEXT),
    ]

    vectors_conf = [
        {
            "name": "text",
            "vectorizer": Configure.Vectorizer.none(),
            "vector_index_config": Configure.VectorIndex.hnsw(),
        },
    ]

    try:
        client.collections.delete(name)
    except Exception:
        # Ignore if it doesn't exist yet
        pass
    client.collections.create(
        name=name,
        properties=props,
        vector_config=vectors_conf,
    )

def _to_float_list(vec: Any) -> Optional[List[float]]:
    if vec is None:
        return None
    try:
        return [float(x) for x in vec]
    except Exception:
        return None


def do_job(collection_name: str = "rag_chunks"):
    client = _connect_local()
    try:
        _ensure_collection(client, collection_name)
    finally:
        client.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Init or reset a Weaviate instance."
    )
    parser.add_argument(
        "-c",
        "--collection-name",
        default="rag_chunks",
        help='Weaviate collection name to use/create (default: "rag_chunks")',
    )
    args = parser.parse_args(argv)

    try:
        do_job(
            collection_name=args.collection_name,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
