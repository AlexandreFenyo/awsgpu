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

    pattern = re.compile(rf"^{re.escape(file_name)}-(\d+)$")

    client = _connect_local()
    try:
        coll = client.collections.get(collection_name)

        # Collecter d'abord tous les UUIDs à supprimer (pour éviter les soucis de pagination après suppression)
        to_delete: List[str] = []

        resp = coll.query.fetch_objects(limit=1000, return_properties=["chunk_id"])

        def collect(page) -> None:
            objs = getattr(page, "objects", None) or []
            for obj in objs:
                props = getattr(obj, "properties", None) or {}
                chunk_id = props.get("chunk_id")
                if isinstance(chunk_id, str) and pattern.match(chunk_id):
                    uid = getattr(obj, "uuid", None) or getattr(obj, "id", None)
                    if isinstance(uid, str):
                        to_delete.append(uid)

        collect(resp)

        # Pagination
        while getattr(resp, "has_next_page", False):
            cursor = getattr(resp, "cursor", None) or getattr(resp, "next_cursor", None)
            if not cursor:
                break
            resp = coll.query.fetch_objects(
                limit=1000,
                return_properties=["chunk_id"],
                after=cursor,
            )
            collect(resp)

        # Supprimer
        deleted = 0
        for uid in to_delete:
            try:
                coll.data.delete_by_id(uid)
                deleted += 1
            except Exception:
                # Continuer même si une suppression échoue; on pourrait logger si besoin
                pass

        return deleted
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
