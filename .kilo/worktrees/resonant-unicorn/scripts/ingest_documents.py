#!/usr/bin/env python
"""Ingest standards documents into the database and the vector index.

    python scripts/ingest_documents.py --input ../data/raw/standards
    python scripts/ingest_documents.py --file path/to/IS-XXXX.pdf

Accepts .pdf (PyMuPDF), .txt and .md. Re-running replaces the clauses of any
standard it finds, so a corrected document can simply be dropped back in.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.db.base import create_all, session_scope  # noqa: E402
from app.ingestion.pipeline import ingest_documents  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest standards documents")
    parser.add_argument("--input", help="directory of documents to ingest")
    parser.add_argument("--file", nargs="*", help="individual document paths")
    parser.add_argument("--no-vectors", action="store_true", help="skip embedding (DB rows only)")
    args = parser.parse_args()

    if not args.input and not args.file:
        args.input = str(REPO_ROOT / "data" / "raw" / "standards")

    create_all()
    db = session_scope()
    try:
        report = ingest_documents(
            db,
            directory=Path(args.input) if args.input else None,
            paths=[Path(f) for f in (args.file or [])] or None,
            rebuild_vectors=not args.no_vectors,
        )
    finally:
        db.close()

    print(f"\nDocuments ingested : {report.documents}")
    print(f"Clause chunks      : {report.clauses}")
    print(f"Embedding backend  : {report.embedding_backend or 'skipped'}")
    print(f"Vector backend     : {report.vector_backend or 'skipped'}")
    for skipped in report.skipped:
        print(f"  SKIPPED: {skipped}")
    return 0 if report.documents else 1


if __name__ == "__main__":
    raise SystemExit(main())
