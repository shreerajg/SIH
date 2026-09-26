"""One-way data migration: the ChromaDB vector store -> MongoDB.

Reads the persisted Chroma collections and writes their vectors, documents and
metadata into MongoDB's ``vectors_*`` collections, then creates the Atlas
vector search indexes.

The embeddings are copied as they are, **not recomputed**. Re-embedding would
be slower, would need the model present, and - if the model or its version ever
differed - would silently produce a different corpus. Copying keeps the vectors
bit-identical to the ones retrieval was measured against.

Properties:

* **Non-destructive.** The Chroma directory is only read. Nothing is deleted.
* **Idempotent.** Vectors are upserted by their existing id.
* **Identifiers preserved.** A clause vector keeps its ``chunk_id`` as ``_id``.

Usage::

    python scripts/migrate_chroma_to_mongo.py --dry-run
    python scripts/migrate_chroma_to_mongo.py
    python scripts/migrate_chroma_to_mongo.py --chroma backend/storage/chroma
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from pymongo import ReplaceOne  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.mongo import init_client, safe_uri  # noqa: E402
from app.search.vector_store import (  # noqa: E402
    ALL_COLLECTIONS,
    EMBEDDING_DIMENSIONS,
    ensure_vector_indexes,
    mongo_collection_name,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger("migrate-vectors")

DEFAULT_CHROMA = Path(__file__).resolve().parents[1] / "backend" / "storage" / "chroma"


def _scalar(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in (meta or {}).items() if v is not None}


def migrate(chroma_path: Path, *, dry_run: bool = False) -> int:
    if not chroma_path.exists():
        raise SystemExit(f"No Chroma store at {chroma_path}")

    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
    except ImportError:
        raise SystemExit(
            "chromadb is not installed. Install it temporarily to run this one-off "
            "migration: pip install chromadb"
        )

    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
    )
    db = init_client()
    log.info("Source : %s (read-only)", chroma_path)
    log.info("Target : %s / %s", safe_uri(), settings.mongo_db_name)

    existing = {c.name for c in client.list_collections()}
    total = 0

    for collection in ALL_COLLECTIONS:
        if collection not in existing:
            log.warning("  %-18s not present in Chroma - skipped", collection)
            continue
        col = client.get_collection(collection)
        count = col.count()
        if count == 0:
            log.info("  %-18s empty - skipped", collection)
            continue

        got = col.get(include=["embeddings", "documents", "metadatas"], limit=count)
        ids: List[str] = got["ids"]
        embeddings = got["embeddings"]
        documents = got["documents"] or [""] * len(ids)
        metadatas = got["metadatas"] or [{}] * len(ids)

        if embeddings is None or len(embeddings) == 0:
            log.warning("  %-18s no embeddings returned - skipped", collection)
            continue
        dim = len(embeddings[0])
        if dim != EMBEDDING_DIMENSIONS:
            raise SystemExit(
                f"{collection}: vectors are {dim}-dimensional but the index expects "
                f"{EMBEDDING_DIMENSIONS}. Refusing to import a mismatched corpus."
            )

        operations = []
        for i, vector_id in enumerate(ids):
            meta = _scalar(metadatas[i])
            operations.append(
                ReplaceOne(
                    {"_id": vector_id},
                    {
                        "_id": vector_id,
                        "embedding": [float(x) for x in embeddings[i]],
                        "document": documents[i] or "",
                        "standard_id": meta.get("standard_id", ""),
                        "metadata": meta,
                    },
                    upsert=True,
                )
            )

        if dry_run:
            log.info("  %-18s %4d vector(s), dim=%d [dry run]", collection, len(operations), dim)
        else:
            db[mongo_collection_name(collection)].bulk_write(operations, ordered=False)
            log.info("  %-18s %4d vector(s), dim=%d", collection, len(operations), dim)
        total += len(operations)

    if dry_run:
        log.info("-" * 52)
        log.info("Vectors counted: %s (nothing written)", total)
        return total

    log.info("-" * 52)
    log.info("Vectors written: %s", total)

    log.info("Creating Atlas vector search indexes...")
    for collection, status in ensure_vector_indexes().items():
        log.info("  %-18s %s", collection, status)
    log.info(
        "Index builds are asynchronous. Until they report 'queryable', search uses the "
        "brute-force cosine path over the same vectors."
    )
    log.info("The Chroma directory was only read and has not been modified.")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chroma", default=str(DEFAULT_CHROMA), help="source Chroma directory")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    migrate(Path(args.chroma), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
