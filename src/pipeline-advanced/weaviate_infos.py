#!/usr/bin/env python3
"""
Interroge Weaviate pour:
- afficher le nombre total d'objets dans la collection (par défaut: "rag_chunks"),
- lister les différents noms de fichiers (dérivés de chunk_id "<fichier>-<index>")
  avec, entre parenthèses, le nombre de chunks associés.

Exemple de chunk_id:
"CCTP.docx.html.md.converted-6" -> fichier: "CCTP.docx.html.md.converted"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from typing import Dict, Optional, Tuple

try:
    import weaviate
except Exception:
    print("Erreur: weaviate-client est requis. Installez-le avec: pip install weaviate-client", file=sys.stderr)
    raise


def _connect_local():
    """
    Connexion à une instance Weaviate locale.
    Peut utiliser la variable d'environnement WEAVIATE_HOST si fournie.
    """
    weaviate_host = os.environ.get("WEAVIATE_HOST")
    if weaviate_host:
        return weaviate.connect_to_local(host=weaviate_host)
    else:
        return weaviate.connect_to_local()


_CHUNK_ID_RE = re.compile(r"^(?P<file>.+)-(?P<index>\d+)$")


def _file_from_chunk_id(chunk_id: str) -> Optional[str]:
    """
    Extrait le nom de fichier à partir d'un chunk_id du type "<fichier>-<index>".
    Retourne None si le format ne correspond pas.
    """
    m = _CHUNK_ID_RE.match(chunk_id)
    if not m:
        return None
    return m.group("file")


def collect_counts(collection_name: str) -> Tuple[int, Dict[str, int]]:
    """
    Récupère tous les objets et agrège:
    - total d'objets,
    - nombre de chunks par nom de fichier (dérivé de chunk_id).
    """
    client = _connect_local()
    try:
        coll = client.collections.get(collection_name)

        total = 0
        per_file = defaultdict(int)

        limit = 1000
        cursor = None

        while True:
            resp = coll.query.fetch_objects(
                limit=limit,
                return_properties=["chunk_id"],
                after=cursor,
            )
            objs = getattr(resp, "objects", None) or []
            for obj in objs:
                props = getattr(obj, "properties", None) or {}
                chunk_id = props.get("chunk_id")
                if isinstance(chunk_id, str):
                    fname = _file_from_chunk_id(chunk_id)
                    if fname:
                        per_file[fname] += 1
                total += 1

            next_cursor = (
                getattr(resp, "cursor", None)
                or getattr(resp, "next_cursor", None)
                or getattr(getattr(resp, "page_info", None), "end_cursor", None)
            )

            if not next_cursor or len(objs) < limit:
                break
            cursor = next_cursor

        return total, dict(per_file)
    finally:
        client.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Affiche le total d'objets et la répartition par fichier (d'après chunk_id) dans une collection Weaviate."
    )
    parser.add_argument(
        "-c",
        "--collection-name",
        default="rag_chunks",
        help='Nom de la collection Weaviate (défaut: "rag_chunks")',
    )
    args = parser.parse_args(argv)

    try:
        total, per_file = collect_counts(args.collection_name)
    except Exception as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1

    print(f"Total d'objets dans '{args.collection_name}': {total}")
    for fname in sorted(per_file.keys()):
        print(f"{fname} ({per_file[fname]})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
