"""Index creation.

Replaces the indexes, UNIQUE constraints and ``create_all()`` of the SQL
schema. MongoDB creates collections on first write, so this module only has to
declare indexes - and ``create_index`` is idempotent, so it is safe to run on
every startup.

Each index below is either carried over from the old SQL schema or added
because of a query pattern that actually exists in the codebase; the comments
say which.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.db import repositories as repo

logger = logging.getLogger(__name__)

#: (collection, keys, options). Mirrors the SQL indexes one for one, plus the
#: corpus-mode filters that every retrieval path applies.
INDEXES: List[tuple] = [
    # --- standards ------------------------------------------------------
    (repo.STANDARDS, [("is_number", ASCENDING)], {}),
    (repo.STANDARDS, [("normalized_number", ASCENDING)], {}),
    (repo.STANDARDS, [("product_category", ASCENDING)], {}),
    (repo.STANDARDS, [("document_id", ASCENDING)], {}),
    # is_verified / is_demo were not indexed under SQL, but corpus.apply_mode()
    # filters on them in every discovery, RAG and consumer lookup path.
    (repo.STANDARDS, [("is_verified", ASCENDING)], {}),
    (repo.STANDARDS, [("is_demo", ASCENDING)], {}),
    # --- standard_clauses -----------------------------------------------
    # Was a UNIQUE constraint in SQL; chunk_id is the citation key the
    # Evidence Shield validates against, so uniqueness is load-bearing.
    (repo.STANDARD_CLAUSES, [("chunk_id", ASCENDING)], {"unique": True}),
    (repo.STANDARD_CLAUSES, [("standard_id", ASCENDING)], {}),
    (
        repo.STANDARD_CLAUSES,
        [("standard_id", ASCENDING), ("clause_number", ASCENDING)],
        {},
    ),
    # Health reports a count of table-derived chunks.
    (repo.STANDARD_CLAUSES, [("is_table", ASCENDING)], {}),
    # --- compliance_requirements ----------------------------------------
    (repo.COMPLIANCE_REQUIREMENTS, [("standard_id", ASCENDING)], {}),
    # Amendment impact looks requirements up by code across standards.
    (repo.COMPLIANCE_REQUIREMENTS, [("requirement_code", ASCENDING)], {}),
    # --- qcos ------------------------------------------------------------
    (repo.QCOS, [("standard_id", ASCENDING)], {}),
    (repo.QCOS, [("effective_date", DESCENDING)], {}),
    # --- amendments -------------------------------------------------------
    (repo.AMENDMENTS, [("standard_id", ASCENDING)], {}),
    (repo.AMENDMENTS, [("effective_date", DESCENDING)], {}),
    # --- standard_relationships -------------------------------------------
    # Queried in both directions when building the knowledge graph.
    (repo.STANDARD_RELATIONSHIPS, [("source_standard_id", ASCENDING)], {}),
    (repo.STANDARD_RELATIONSHIPS, [("target_standard_id", ASCENDING)], {}),
    # --- product_evidence ---------------------------------------------------
    (repo.PRODUCT_EVIDENCE, [("product_id", ASCENDING)], {}),
    # --- certification schemes -----------------------------------------------
    (repo.CERTIFICATION_SCHEMES, [("code", ASCENDING)], {}),
    (repo.CERTIFICATION_SCHEMES, [("aliases", ASCENDING)], {}),
    # The applicability lookup: resolved by normalized IS number on every
    # product-to-scheme resolution, so it must be indexed.
    (repo.SCHEME_PRODUCT_INDEX, [("normalized_number", ASCENDING)], {}),
    (repo.SCHEME_PRODUCT_INDEX, [("scheme_id", ASCENDING)], {}),
    (repo.CERTIFICATION_PROCESSES, [("scheme_id", ASCENDING)], {}),
    # --- hallmarking ---------------------------------------------------------
    # Knowledge is always read by kind (purity grades, components, stages...).
    (repo.HALLMARKING_KNOWLEDGE, [("kind", ASCENDING), ("order", ASCENDING)], {}),
    # Centres are browsed by state and city, and filtered by operative status.
    (repo.HALLMARKING_CENTRES, [("state", ASCENDING)], {}),
    (repo.HALLMARKING_CENTRES, [("city", ASCENDING)], {}),
    (repo.HALLMARKING_CENTRES, [("status", ASCENDING)], {}),
]

# products needs no index beyond _id: it is always fetched by id, and its
# matches/results are embedded rather than queried independently.


def ensure_indexes(db: Database) -> Dict[str, Any]:
    """Create every declared index. Idempotent; safe on every startup."""
    created: List[str] = []
    errors: List[str] = []
    for collection, keys, options in INDEXES:
        try:
            name = db[collection].create_index(keys, **options)
            created.append(f"{collection}.{name}")
        except PyMongoError as exc:  # pragma: no cover - server dependent
            errors.append(f"{collection}.{keys}: {exc}")
            logger.error("Index creation failed for %s %s: %s", collection, keys, exc)
    if errors:
        logger.warning("Index creation completed with %s error(s)", len(errors))
    return {"created": created, "errors": errors}


def drop_all(db: Database) -> None:
    """Drop every application collection. Used by --reset and by tests."""
    for collection in (
        repo.STANDARDS,
        repo.STANDARD_CLAUSES,
        repo.COMPLIANCE_REQUIREMENTS,
        repo.QCOS,
        repo.AMENDMENTS,
        repo.STANDARD_RELATIONSHIPS,
        repo.PRODUCTS,
        repo.PRODUCT_EVIDENCE,
        repo.INGESTION_RUNS,
        repo.CERTIFICATION_SCHEMES,
        repo.SCHEME_PRODUCT_INDEX,
        repo.CERTIFICATION_PROCESSES,
        repo.HALLMARKING_KNOWLEDGE,
        repo.HALLMARKING_CENTRES,
    ):
        db.drop_collection(collection)
