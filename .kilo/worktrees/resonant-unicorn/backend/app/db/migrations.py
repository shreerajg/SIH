"""Safe, additive schema migrations.

``create_all()`` creates missing *tables* but never missing *columns*, so a
database created before an upgrade keeps working right up until something
selects a new column and fails. This module closes that gap.

Design rules, in order of importance:

* **Never destructive.** Only ``ADD COLUMN`` is emitted. Nothing is dropped,
  renamed or retyped, so running this against a populated production database
  cannot lose data.
* **Idempotent.** Existing columns are detected and skipped, so it is safe to
  run on every startup.
* **Portable.** The SQL is the intersection of what SQLite and MySQL 8 accept.

Anything beyond adding a column (a real rename, a type change, a backfill with
business logic) should become an Alembic revision instead - Alembic is already
a dependency for exactly that case.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.base import init_engine

logger = logging.getLogger(__name__)


@dataclass
class ColumnSpec:
    name: str
    #: DDL type per dialect; falls back to ``default_type``.
    default_type: str
    mysql_type: Optional[str] = None
    default_value: Optional[str] = None

    def ddl_type(self, dialect: str) -> str:
        if dialect == "mysql" and self.mysql_type:
            return self.mysql_type
        return self.default_type


#: Columns introduced after the first release, per table.
ADDED_COLUMNS: Dict[str, List[ColumnSpec]] = {
    "standards": [
        ColumnSpec("document_id", "VARCHAR(96)", default_value="''"),
        ColumnSpec("document_type", "VARCHAR(48)", default_value="'standard'"),
        ColumnSpec("retrieved_at", "DATETIME"),
        ColumnSpec("is_demo", "BOOLEAN", mysql_type="TINYINT(1)", default_value="1"),
    ],
    "standard_clauses": [
        ColumnSpec("table_json", "TEXT", mysql_type="JSON"),
        ColumnSpec("is_table", "BOOLEAN", mysql_type="TINYINT(1)", default_value="0"),
    ],
    "qcos": [
        ColumnSpec("scheme", "VARCHAR(256)", default_value="''"),
        ColumnSpec("document_id", "VARCHAR(96)", default_value="''"),
        ColumnSpec("retrieved_at", "DATETIME"),
        ColumnSpec("is_demo", "BOOLEAN", mysql_type="TINYINT(1)", default_value="1"),
    ],
    "amendments": [
        ColumnSpec("document_id", "VARCHAR(96)", default_value="''"),
        ColumnSpec("retrieved_at", "DATETIME"),
        ColumnSpec("is_demo", "BOOLEAN", mysql_type="TINYINT(1)", default_value="1"),
    ],
    "product_standard_matches": [
        ColumnSpec("signals_json", "TEXT", mysql_type="JSON"),
    ],
    "product_evidence": [
        ColumnSpec("original_filename", "VARCHAR(256)", default_value="''"),
        ColumnSpec("content_type", "VARCHAR(128)", default_value="''"),
        ColumnSpec("size_bytes", "INTEGER", default_value="0"),
        ColumnSpec("upload_category", "VARCHAR(48)", default_value="'other'"),
        ColumnSpec("extracted_text", "TEXT"),
        ColumnSpec("extracted_fields_json", "TEXT", mysql_type="JSON"),
        ColumnSpec("extraction_status", "VARCHAR(32)", default_value="'none'"),
    ],
}

#: Backfills that keep old rows consistent with the new columns. Each entry is
#: (table, SQL) and must be safe to run repeatedly.
BACKFILLS: List[tuple] = [
    # Rows predating is_demo inherit it from the legacy is_mock flag.
    ("standards", "UPDATE standards SET is_demo = is_mock WHERE is_demo IS NULL"),
    ("standards", "UPDATE standards SET document_id = id WHERE document_id IS NULL OR document_id = ''"),
    ("qcos", "UPDATE qcos SET is_demo = is_mock WHERE is_demo IS NULL"),
    ("amendments", "UPDATE amendments SET is_demo = is_mock WHERE is_demo IS NULL"),
    ("standard_clauses", "UPDATE standard_clauses SET is_table = 0 WHERE is_table IS NULL"),
]


@dataclass
class MigrationReport:
    added: List[str] = field(default_factory=list)
    backfilled: List[str] = field(default_factory=list)
    skipped_tables: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.backfilled)

    def summary(self) -> str:
        if self.errors:
            return f"{len(self.added)} column(s) added, {len(self.errors)} error(s)"
        if not self.changed:
            return "schema already up to date"
        return f"{len(self.added)} column(s) added, {len(self.backfilled)} backfill(s) applied"


def run_migrations(engine: Optional[Engine] = None) -> MigrationReport:
    """Add any missing columns to an existing database. Never drops anything."""
    engine = engine or init_engine()
    dialect = engine.dialect.name
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    report = MigrationReport()

    with engine.begin() as conn:
        for table, specs in ADDED_COLUMNS.items():
            if table not in existing_tables:
                # Nothing to migrate - create_all() will build it fresh.
                report.skipped_tables.append(table)
                continue

            present = {c["name"] for c in inspector.get_columns(table)}
            for spec in specs:
                if spec.name in present:
                    continue
                clause = f"ALTER TABLE {table} ADD COLUMN {spec.name} {spec.ddl_type(dialect)}"
                if spec.default_value is not None:
                    clause += f" DEFAULT {spec.default_value}"
                try:
                    conn.execute(text(clause))
                    report.added.append(f"{table}.{spec.name}")
                    logger.info("Migration: added %s.%s", table, spec.name)
                except Exception as exc:  # pragma: no cover - dialect dependent
                    report.errors.append(f"{table}.{spec.name}: {exc}")
                    logger.error("Migration failed for %s.%s: %s", table, spec.name, exc)

        for table, sql in BACKFILLS:
            if table not in existing_tables:
                continue
            try:
                result = conn.execute(text(sql))
                if (result.rowcount or 0) > 0:
                    report.backfilled.append(f"{table}: {result.rowcount} row(s)")
            except Exception as exc:  # pragma: no cover
                # A backfill referencing a column that never existed on this
                # database is not an error worth failing startup over.
                logger.debug("Backfill skipped (%s): %s", table, exc)

    if report.errors:
        logger.warning("Migrations completed with errors: %s", report.errors)
    return report
