#!/usr/bin/env python
"""One-command demo setup.

    python scripts/setup_demo.py [--reset]

Creates the schema, ingests every document in data/raw/standards, seeds the
structured knowledge (requirements, regulatory records, amendments,
relationships) and builds the vector index. Idempotent - safe to re-run.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.indexes import drop_all, ensure_indexes  # noqa: E402
from app.db.mongo import active_backend, active_url_safe, init_client  # noqa: E402
from app.ingestion.pipeline import ingest_documents  # noqa: E402
from app.ingestion.seed import seed_all  # noqa: E402
from app.search.vector_store import (  # noqa: E402
    ensure_vector_indexes,
    CLAUSES_COLLECTION,
    STANDARDS_COLLECTION,
    get_vector_store,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("setup_demo")


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up the SIH26107 demo corpus")
    parser.add_argument("--reset", action="store_true", help="drop tables and vectors first")
    parser.add_argument(
        "--input", default=str(REPO_ROOT / "data" / "raw" / "standards"),
        help="directory of standard documents to ingest",
    )
    args = parser.parse_args()

    started = time.time()

    db = init_client()

    if args.reset:
        log.info("Resetting database and vector store...")
        try:
            drop_all(db)
        except Exception as exc:
            log.warning("drop_all skipped: %s", exc)
        get_vector_store().reset()

    log.info("Ensuring indexes...")
    index_report = ensure_indexes(db)
    log.info("%s index(es) ensured", len(index_report["created"]))
    log.info("Database backend: %s (%s)", active_backend(), active_url_safe())

    try:
        log.info("Ingesting documents from %s ...", args.input)
        report = ingest_documents(db, Path(args.input))
        if report.documents == 0:
            log.error("No documents ingested. Nothing to demo.")
            return 1
        log.info(
            "Ingested %s documents / %s clauses (embeddings=%s, vectors=%s)",
            report.documents, report.clauses, report.embedding_backend, report.vector_backend,
        )

        log.info("Seeding structured knowledge...")
        counts = seed_all(db)
        log.info(
            "Seeded: %s requirements, %s regulatory records, %s amendments, %s relationships",
            counts["requirements"], counts["regulatory"],
            counts["amendments"], counts["relationships"],
        )
    finally:
        # PyMongo pools connections on the client; the Database handle itself
        # has nothing to close.
        pass

    store = get_vector_store()
    log.info("Creating Atlas vector search indexes...")
    for collection, status in ensure_vector_indexes().items():
        log.info("  %-18s %s", collection, status)
    log.info(
        "Vector index: %s standards, %s clauses (%s, search: %s)",
        store.count(STANDARDS_COLLECTION), store.count(CLAUSES_COLLECTION),
        store.name, store.active_backend(CLAUSES_COLLECTION),
    )
    log.info("Demo setup complete in %.1fs", time.time() - started)
    log.info("Start the API with:  cd backend && uvicorn app.main:app --reload --port 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
