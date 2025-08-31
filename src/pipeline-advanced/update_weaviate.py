#!/usr/bin/env python3
"""
Upload precomputed embeddings into a local Weaviate instance.

- Input: NDJSON file of embeddings (one JSON object per line), with fields:
  { chunk_id, text, embedding: [floats], model: {name, version}, created_at, approx_tokens, keywords, headings, heading, full_headings }

- Behavior:
  - Creates a Weaviate collection with a schema that does NOT perform vectorization (vectorizer = none), and enables named multi-vectors: "text" plus "h1".."h6".
  - Inserts each line as an object with the main text embedding under "text".

Notes:
- Requires: weaviate-client (v4)
- Connects to a local Weaviate (http://localhost:8080) using default weaviate-client settings.
"""

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


def _ensure_collection(client, name: str, recreate: bool = True):
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

    if recreate:
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
        return client.collections.get(name)

    # No recreation: try to use existing collection; create only if missing.
    try:
        return client.collections.get(name)
    except Exception:
        client.collections.create(
            name=name,
            properties=props,
            vector_config=vectors_conf,
        )
        return client.collections.get(name)


def _to_float_list(vec: Any) -> Optional[List[float]]:
    if vec is None:
        return None
    try:
        return [float(x) for x in vec]
    except Exception:
        return None


def upload_embeddings_to_weaviate(input_path: str, collection_name: str = "rag_chunks", recreate: bool = True) -> int:
    """
    Read an embeddings NDJSON file and upload objects with their vectors to Weaviate.
    Returns the number of inserted objects.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    client = _connect_local()
    try:
        coll = _ensure_collection(client, collection_name, recreate=recreate)

        inserted = 0
        # Insert one by one using data.insert to support named vectors across client versions.
        with src.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item: Dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue

                text_vec = _to_float_list(item.get("embedding"))
                if not text_vec:
                    # Skip if no main text vector
                    continue

                # Build named vectors payload: main "text" only.
                vectors: Dict[str, List[float]] = {"text": text_vec}

                # Collect properties; keep types simple as defined in schema above.
                props: Dict[str, Any] = {
                    "chunk_id": item.get("chunk_id"),
                    "text": item.get("text"),
                    "approx_tokens": item.get("approx_tokens"),
                    "keywords": item.get("keywords") or [],
                    "created_at": item.get("created_at"),
                    "model": item.get("model") or {},
                }
                # Only include 'headings' if it's a non-empty object (Weaviate OBJECT cannot be empty)
                headings_val = item.get("headings")
                if isinstance(headings_val, dict):
                    hv = {k: v for k, v in headings_val.items() if isinstance(v, str) and v}
                    if hv:
                        props["headings"] = hv

                # Only include 'heading' if it's a non-empty object
                heading_val = item.get("heading")
                if isinstance(heading_val, dict):
                    hv2 = {k: v for k, v in heading_val.items() if isinstance(v, str) and v}
                    if hv2:
                        props["heading"] = hv2

                # Include 'full_headings' when present and non-empty
                full_headings_val = item.get("full_headings")
                if isinstance(full_headings_val, str) and full_headings_val:
                    props["full_headings"] = full_headings_val

                coll.data.insert(properties=props, vector=vectors)
                inserted += 1

        return inserted
    finally:
        client.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upload NDJSON embeddings into a local Weaviate instance (no re-embedding)."
    )
    parser.add_argument(
        "input",
        help="Path to the input embeddings NDJSON file",
    )
    parser.add_argument(
        "-c",
        "--collection-name",
        default="rag_chunks",
        help='Weaviate collection name to use/create (default: "rag_chunks")',
    )
    parser.add_argument(
        "-n",
        "--no-recreate",
        action="store_true",
        help="Ne pas recréer la collection et son schéma s'ils existent déjà.",
    )
    args = parser.parse_args(argv)

    try:
        count = upload_embeddings_to_weaviate(
            args.input,
            collection_name=args.collection_name,
            recreate=(not args.no_recreate),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Inserted {count} objects into Weaviate collection '{args.collection_name}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
