#!/usr/bin/env python3
"""
Supprime de Weaviate tous les objets de la collection (par défaut: "rag_chunks")
dont le chunk_id correspond à un fichier donné.

Format attendu de chunk_id: "<fichier>-<index>"
Exemple: "CCTP.docx.html.md.converted-6" -> fichier: "CCTP.docx.html.md.converted"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Optional

try:
    import weaviate
    from weaviate.classes.query import Filter
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


def purge_by_filename(file_name: str, collection_name: str = "rag_chunks") -> int:
    """
    Supprime tous les objets dont chunk_id est de la forme "<file_name>-<nombre>".
    Retourne le nombre d'objets supprimés.
    """
    if not file_name:
        raise ValueError("file_name ne doit pas être vide")

    client = _connect_local()
    try:
        coll = client.collections.get(collection_name)

        # Construire un filtre "like" pour tous les chunk_id commençant par "<file_name>-"
        where_filter = Filter.by_property("chunk_id").like(f"{file_name}-*")

        # Compter le nombre de correspondances via pagination filtrée
        total_match = 0
        resp = coll.query.fetch_objects(
            limit=1000,
            return_properties=["chunk_id"],
            where=where_filter,
        )

        def consume(page) -> None:
            nonlocal total_match
            objs = getattr(page, "objects", None) or []
            total_match += len(objs)

        consume(resp)

        while getattr(resp, "has_next_page", False):
            cursor = getattr(resp, "cursor", None) or getattr(resp, "next_cursor", None)
            if not cursor:
                break
            resp = coll.query.fetch_objects(
                limit=1000,
                return_properties=["chunk_id"],
                after=cursor,
                where=where_filter,
            )
            consume(resp)

        if total_match == 0:
            return 0

        # Suppression en masse avec le même filtre
        coll.data.delete_many(where=where_filter)

        return total_match
    finally:
        client.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Supprime de Weaviate tous les objets d'une collection dont chunk_id est associé à un nom de fichier donné."
    )
    parser.add_argument(
        "file_name",
        help='Nom du fichier correspondant au préfixe des chunk_id (ex: "CCTP.docx.html.md.converted")',
    )
    parser.add_argument(
        "-c",
        "--collection-name",
        default="rag_chunks",
        help='Nom de la collection Weaviate (défaut: "rag_chunks")',
    )
    args = parser.parse_args(argv)

    try:
        deleted = purge_by_filename(args.file_name, collection_name=args.collection_name)
    except Exception as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1

    if deleted == 0:
        print(f"Aucun objet à supprimer pour '{args.file_name}' dans la collection '{args.collection_name}'.")
    else:
        print(f"Supprimé {deleted} objet(s) pour '{args.file_name}' dans la collection '{args.collection_name}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
