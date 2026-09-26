"""One-way data migration: the old SQL database -> MongoDB.

Reads the SQL database directly with the stdlib ``sqlite3`` driver (or, with
``--mysql-url``, through SQLAlchemy if it is still installed), transforms every
row into its MongoDB document shape and writes it to the database named by
``MONGO_URI`` / ``MONGO_DB_NAME``.

Properties that matter:

* **Non-destructive.** The SQL database is opened read-only and is never
  written to or deleted. Re-running is safe.
* **Idempotent.** Every document is upserted by its existing ``_id``, so a
  partial run can simply be repeated.
* **Identifiers are preserved exactly.** ``DEMO-STD-001``, ``prd-1a2b3c``,
  ``IS-2082-2018-PM::c4.5.2`` all become ``_id`` verbatim. This is not
  cosmetic: the vector collections are keyed by these same strings, so
  renaming them would silently break retrieval.
* **Orphans are reported, not guessed.** A row whose parent is missing is
  skipped and counted; nothing is invented to fill the gap.
* **product_standard_matches and compliance_results are folded** into their
  parent product document, matching the MongoDB schema.

Usage::

    python scripts/migrate_sqlite_to_mongo.py                     # default SQLite file
    python scripts/migrate_sqlite_to_mongo.py --sqlite path/to.db
    python scripts/migrate_sqlite_to_mongo.py --dry-run           # report only
    python scripts/migrate_sqlite_to_mongo.py --drop              # clear target first
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.indexes import drop_all, ensure_indexes  # noqa: E402
from app.db.mongo import init_client, safe_uri  # noqa: E402
from app.db import repositories as repo  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger("migrate")

DEFAULT_SQLITE = Path(__file__).resolve().parents[1] / "backend" / "storage" / "sih26107.db"

#: Columns holding JSON. SQLite stored them as TEXT; MySQL as native JSON.
JSON_COLUMNS = {
    "standards": ["keywords", "covered_areas"],
    "standard_clauses": ["table_json"],
    "products": ["attributes_json", "missing_fields_json"],
    "product_standard_matches": [
        "matched_attributes_json",
        "evidence_chunk_ids",
        "signals_json",
    ],
    "compliance_requirements": ["check_rule_json", "applies_when_json"],
    "product_evidence": ["extracted_fields_json", "metadata_json"],
}

#: Columns holding datetimes, stored by SQLite as ISO-ish strings.
DATE_COLUMNS = {
    "standards": ["retrieved_at", "created_at"],
    "products": ["created_at", "updated_at"],
    "product_standard_matches": ["created_at"],
    "compliance_results": ["created_at"],
    "product_evidence": ["created_at"],
    "qcos": ["notification_date", "effective_date", "retrieved_at"],
    "amendments": ["publication_date", "effective_date", "retrieved_at"],
    "ingestion_runs": ["started_at", "finished_at"],
}

BOOL_COLUMNS = {
    "standards": ["is_verified", "is_demo", "is_mock"],
    "standard_clauses": ["is_table"],
    "qcos": ["is_verified", "is_demo", "is_mock"],
    "amendments": ["is_verified", "is_demo", "is_mock"],
}


class Report:
    def __init__(self) -> None:
        self.written: Dict[str, int] = {}
        self.skipped: List[str] = []
        self.warnings: List[str] = []

    def record(self, collection: str, count: int) -> None:
        self.written[collection] = self.written.get(collection, 0) + count

    def skip(self, message: str) -> None:
        self.skipped.append(message)


def _parse_json(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed is not None else fallback


def _parse_date(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _row_to_doc(table: str, row: sqlite3.Row) -> Dict[str, Any]:
    """One SQL row -> one MongoDB document, with `id` renamed to `_id`."""
    doc: Dict[str, Any] = dict(row)
    for column in JSON_COLUMNS.get(table, []):
        if column in doc:
            # A list-valued column must never degrade into {} and vice versa.
            fallback: Any = [] if column in (
                "keywords", "covered_areas", "missing_fields_json",
                "matched_attributes_json", "evidence_chunk_ids",
            ) else {}
            doc[column] = _parse_json(doc[column], fallback)
    for column in DATE_COLUMNS.get(table, []):
        if column in doc:
            doc[column] = _parse_date(doc[column])
    for column in BOOL_COLUMNS.get(table, []):
        if column in doc:
            doc[column] = bool(doc[column]) if doc[column] is not None else False
    if "id" in doc:
        doc["_id"] = doc.pop("id")
    return doc


def _fetch(conn: sqlite3.Connection, table: str) -> List[sqlite3.Row]:
    try:
        return list(conn.execute(f"SELECT * FROM {table}"))
    except sqlite3.OperationalError as exc:
        log.warning("Table %s not readable (%s) - skipped", table, exc)
        return []


def _upsert(collection, docs: Iterable[Dict[str, Any]], report: Report, name: str) -> None:
    count = 0
    for doc in docs:
        if not doc.get("_id"):
            report.skip(f"{name}: a row without an id was skipped")
            continue
        collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        count += 1
    report.record(name, count)
    log.info("  %-26s %5d document(s)", name, count)


def migrate(sqlite_path: Path, *, dry_run: bool = False, drop: bool = False) -> Report:
    report = Report()

    if not sqlite_path.exists():
        raise SystemExit(f"No SQL database at {sqlite_path}")

    # Opened read-only: this script must never be able to modify the source.
    conn = sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    db = init_client()
    log.info("Source : %s (read-only)", sqlite_path)
    log.info("Target : %s / %s", safe_uri(), settings.mongo_db_name)

    if drop and not dry_run:
        log.warning("Dropping existing collections in %s", settings.mongo_db_name)
        drop_all(db)

    if not dry_run:
        ensure_indexes(db)

    # ---- corpus collections, one table per collection ------------------
    simple = [
        ("standards", repo.STANDARDS),
        ("standard_clauses", repo.STANDARD_CLAUSES),
        ("compliance_requirements", repo.COMPLIANCE_REQUIREMENTS),
        ("qcos", repo.QCOS),
        ("amendments", repo.AMENDMENTS),
        ("standard_relationships", repo.STANDARD_RELATIONSHIPS),
        ("product_evidence", repo.PRODUCT_EVIDENCE),
        ("ingestion_runs", repo.INGESTION_RUNS),
    ]

    standard_ids = {r["id"] for r in _fetch(conn, "standards")}
    product_ids = {r["id"] for r in _fetch(conn, "products")}

    log.info("Migrating collections:")
    for table, collection_name in simple:
        rows = _fetch(conn, table)
        docs = []
        for row in rows:
            doc = _row_to_doc(table, row)
            # Referential checks the SQL FKs used to make. A dangling row is
            # reported rather than carried over pointing at nothing.
            parent = doc.get("standard_id")
            if table in ("standard_clauses", "compliance_requirements", "qcos", "amendments"):
                if parent and parent not in standard_ids:
                    report.skip(f"{table} {doc['_id']}: unknown standard {parent}")
                    continue
            if table == "standard_relationships":
                src, tgt = doc.get("source_standard_id"), doc.get("target_standard_id")
                if src not in standard_ids or tgt not in standard_ids:
                    report.skip(f"{table} {doc['_id']}: dangling edge {src} -> {tgt}")
                    continue
            if table == "product_evidence" and doc.get("product_id") not in product_ids:
                report.skip(f"{table} {doc['_id']}: unknown product {doc.get('product_id')}")
                continue
            docs.append(doc)
        if dry_run:
            report.record(collection_name, len(docs))
            log.info("  %-26s %5d document(s) [dry run]", collection_name, len(docs))
        else:
            _upsert(db[collection_name], docs, report, collection_name)

    # ---- products, with matches and results embedded -------------------
    matches_by_product: Dict[str, List[Dict[str, Any]]] = {}
    for row in _fetch(conn, "product_standard_matches"):
        doc = _row_to_doc("product_standard_matches", row)
        pid = doc.get("product_id")
        if pid not in product_ids:
            report.skip(f"match {doc['_id']}: unknown product {pid}")
            continue
        if doc.get("standard_id") not in standard_ids:
            report.skip(f"match {doc['_id']}: unknown standard {doc.get('standard_id')}")
            continue
        matches_by_product.setdefault(pid, []).append(doc)

    results_by_product: Dict[str, List[Dict[str, Any]]] = {}
    for row in _fetch(conn, "compliance_results"):
        doc = _row_to_doc("compliance_results", row)
        pid = doc.get("product_id")
        if pid not in product_ids:
            report.skip(f"result {doc['_id']}: unknown product {pid}")
            continue
        results_by_product.setdefault(pid, []).append(doc)

    # The SQL UNIQUE constraints become structural once embedded, so enforce
    # them here rather than importing duplicates into the array.
    def _dedupe(items: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        seen, out = set(), []
        for item in items:
            marker = item.get(key)
            if marker in seen:
                report.skip(f"duplicate {key}={marker} dropped while embedding")
                continue
            seen.add(marker)
            out.append(item)
        return out

    product_docs = []
    for row in _fetch(conn, "products"):
        doc = _row_to_doc("products", row)
        pid = doc["_id"]
        doc["matches"] = _dedupe(matches_by_product.get(pid, []), "standard_id")
        doc["results"] = _dedupe(results_by_product.get(pid, []), "requirement_id")
        product_docs.append(doc)

    if dry_run:
        report.record(repo.PRODUCTS, len(product_docs))
        log.info("  %-26s %5d document(s) [dry run]", repo.PRODUCTS, len(product_docs))
    else:
        _upsert(db[repo.PRODUCTS], product_docs, report, repo.PRODUCTS)

    embedded_matches = sum(len(d["matches"]) for d in product_docs)
    embedded_results = sum(len(d["results"]) for d in product_docs)
    log.info(
        "  (embedded %s match(es) and %s result(s) inside products)",
        embedded_matches,
        embedded_results,
    )

    conn.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE), help="source SQLite file")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument(
        "--drop", action="store_true", help="drop target collections before importing"
    )
    args = parser.parse_args()

    report = migrate(Path(args.sqlite), dry_run=args.dry_run, drop=args.drop)

    total = sum(report.written.values())
    log.info("-" * 52)
    log.info("Documents %s: %s", "counted" if args.dry_run else "written", total)
    if report.skipped:
        log.warning("Skipped %s row(s):", len(report.skipped))
        for message in report.skipped[:20]:
            log.warning("  - %s", message)
        if len(report.skipped) > 20:
            log.warning("  ... and %s more", len(report.skipped) - 20)
    log.info("The SQL database was opened read-only and has not been modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
