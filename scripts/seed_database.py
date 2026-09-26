#!/usr/bin/env python
"""Seed structured knowledge (requirements, QCOs, amendments, relationships).

    python scripts/seed_database.py

Assumes documents have already been ingested, because every record here is
attached to a standard that ingestion created. Idempotent.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.db.indexes import ensure_indexes  # noqa: E402
from app.db.mongo import init_client, session_scope  # noqa: E402
from app.db.repositories import standards as standards_repo  # noqa: E402
from app.ingestion.seed import seed_all  # noqa: E402
from app.models import Standard  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")


def main() -> int:
    ensure_indexes(init_client())
    db = session_scope()
    try:
        if standards_repo(db).count() == 0:
            print(
                "No standards found. Run scripts/ingest_documents.py first, "
                "or use scripts/setup_demo.py to do everything at once."
            )
            return 1
        counts = seed_all(db)
    finally:
        # PyMongo pools connections on the client; the Database handle itself
        # has nothing to close.
        pass

    for name, value in counts.items():
        print(f"{name:>16}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
