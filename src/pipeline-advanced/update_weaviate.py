#!/usr/bin/env python3
"""
Upload precomputed embeddings into a local Weaviate instance.

- Input: NDJSON file of embeddings (one JSON object per line), with fields:
  { chunk_id, text, embedding: [floats], embeddings: [{"level": "hN", "embedding": [floats]}, ...], model: {name, version}, created_at, approx_tokens, keywords, headings }

- Behavior:
  - Creates a Weaviate collection with a schema that does NOT perform vectorization (vectorizer = none), and enables named multi-vectors: "text" plus "h1".."h6".
  - Inserts each line as an object with all available vectors: the main text embedding under "text", and each heading level embedding under its respective name ("h1".."h6").

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

try:
    import weaviate
    from weaviate.classes.config import Configure, Property, DataType
except Exception as exc:
    print("Error: weaviate-client is required. Install with: pip install weaviate-client", file=sys.stderr)
    raise


def _connect_local():
    # Connect to a local Weaviate (default URL/env). Adjust here if needed.
    return weaviate.connect_to_local()


def _ensure_collection(client, name: str):
    """
    Ensure a collection exists with vectorizer disabled and an appropriate schema.
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
    ]

    # Create if missing, otherwise reuse existing collection.
    try:
        coll = client.collections.get(name)
        return coll
    except Exception:
        pass

    vectors_conf = {
        "text": Configure.VectorIndex.hnsw(),
        "h1": Configure.VectorIndex.hnsw(),
        "h2": Configure.VectorIndex.hnsw(),
        "h3": Configure.VectorIndex.hnsw(),
        "h4": Configure.VectorIndex.hnsw(),
        "h5": Configure.VectorIndex.hnsw(),
        "h6": Configure.VectorIndex.hnsw(),
    }
    coll = client.collections.create(
        name=name,
        properties=props,
        vectorizer_config=Configure.Vectorizer.none(),
        vectors_config=vectors_conf,
    )
    # After creation, fetch a handle to the collection
    return client.collections.get(name)


def _to_float_list(vec: Any) -> Optional[List[float]]:
    if vec is None:
        return None
    try:
        return [float(x) for x in vec]
    except Exception:
        return None


def upload_embeddings_to_weaviate(input_path: str, collection_name: str = "rag_chunks") -> int:
    """
    Read an embeddings NDJSON file and upload objects with their vectors to Weaviate.
    Returns the number of inserted objects.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    client = _connect_local()
    try:
        coll = _ensure_collection(client, collection_name)

        inserted = 0
        # Use dynamic batching for performance
        with coll.batch.dynamic() as batch, src.open("r", encoding="utf-8") as f:
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

                # Build named vectors payload: main "text" + heading level vectors ("h1".."h6") when present.
                vectors: Dict[str, List[float]] = {"text": text_vec}
                heading_list = item.get("embeddings") or []
                if isinstance(heading_list, list):
                    for entry in heading_list:
                        if not isinstance(entry, dict):
                            continue
                        lvl = entry.get("level")
                        vec = _to_float_list(entry.get("embedding"))
                        if isinstance(lvl, str) and lvl in {"h1", "h2", "h3", "h4", "h5", "h6"} and vec:
                            vectors[lvl] = vec

                # Collect properties; keep types simple as defined in schema above.
                props: Dict[str, Any] = {
                    "chunk_id": item.get("chunk_id"),
                    "text": item.get("text"),
                    "approx_tokens": item.get("approx_tokens"),
                    "keywords": item.get("keywords") or [],
                    "created_at": item.get("created_at"),
                    "model": item.get("model") or {},
                    "headings": item.get("headings") or {},
                }

                batch.add_object(properties=props, vectors=vectors)
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
    args = parser.parse_args(argv)

    try:
        count = upload_embeddings_to_weaviate(args.input, collection_name=args.collection_name)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Inserted {count} objects into Weaviate collection '{args.collection_name}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
