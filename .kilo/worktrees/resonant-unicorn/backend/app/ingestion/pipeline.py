"""Document ingestion: parsed clauses -> relational rows -> vector index.

The pipeline is idempotent. Re-running it on the same directory replaces the
clauses of each standard it finds and re-embeds them, so a corrected document
can simply be dropped back into data/raw/standards.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.text_utils import (
    is_predominantly_devanagari,
    normalize_is_number,
    strip_devanagari,
    truncate,
)
from app.ingestion.manifest import ManifestEntry, index_by_filename, load_manifest
from app.ingestion.parser import ParsedDocument, parse_directory, parse_document
from app.models import IngestionRun, Standard, StandardClause
from app.search.bm25 import get_bm25_index
from app.search.embeddings import get_embedding_backend
from app.search.vector_store import CLAUSES_COLLECTION, STANDARDS_COLLECTION, get_vector_store

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    documents: int = 0
    standards: int = 0
    clauses: int = 0
    tables: int = 0
    #: Chunks dropped as the non-English rendering of bilingual gazette text.
    skipped_non_english: int = 0
    verified_documents: int = 0
    demo_documents: int = 0
    skipped: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    embedding_backend: str = ""
    vector_backend: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "documents": self.documents,
            "standards": self.standards,
            "clauses": self.clauses,
            "tables": self.tables,
            "skipped_non_english": self.skipped_non_english,
            "verified_documents": self.verified_documents,
            "demo_documents": self.demo_documents,
            "skipped": self.skipped,
            "warnings": self.warnings,
            "embedding_backend": self.embedding_backend,
            "vector_backend": self.vector_backend,
        }


def _bool(value: Optional[str], default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _split_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def _standard_document_text(standard: Standard) -> str:
    """The text embedded for stage-1 (standard discovery) retrieval."""
    return " \n".join(
        filter(
            None,
            [
                standard.is_number,
                standard.title,
                standard.product_category,
                ", ".join(standard.keywords or []),
                standard.scope,
                standard.plain_summary,
            ],
        )
    )


def upsert_standard_from_document(
    db: Session, doc: ParsedDocument, entry: Optional[ManifestEntry] = None
) -> Standard:
    """Create/refresh the Standard row.

    Provenance comes from the source manifest when an entry exists, because a
    PDF has no header block to declare where it came from. The manifest is
    authoritative for verification status: a document is only ``is_verified``
    if a validated manifest entry says so.
    """
    meta = doc.metadata
    # A PDF carries no header block, so its identity comes from the validated
    # manifest entry when one exists; otherwise it falls back to the filename.
    # Without this an official document would be keyed by its filename stem.
    manifest_id = (entry.standard_id or entry.document_id) if entry is not None else ""
    standard_id = (
        meta.get("standard-id")
        or manifest_id
        or meta.get("is-number")
        or Path(doc.source_path).stem
    )
    is_number = meta.get("is-number") or (entry.is_number if entry is not None else "") or standard_id

    # The scope text is quoted back to the user in "Why this standard?" and in
    # consumer explanations, so it must come from the same language-filtered
    # clauses the rest of ingestion keeps - otherwise a bilingual gazette
    # quotes its Hindi rendering while every indexed chunk is English.
    usable = [
        c for c in doc.clauses
        if not (settings.ingest_english_only and is_predominantly_devanagari(c.text))
    ]
    scope_source = " ".join(
        c.text for c in usable if c.clause_type == "scope"
    ) or truncate(usable[0].text if usable else "", 400)
    scope_text = (
        strip_devanagari(scope_source) if settings.ingest_english_only else scope_source
    )

    standard = db.get(Standard, standard_id)
    if standard is None:
        standard = Standard(id=standard_id)
        db.add(standard)

    standard.is_number = is_number
    standard.normalized_number = normalize_is_number(is_number) or is_number.upper()
    standard.title = meta.get("title", standard_id)
    standard.year = int(meta["year"]) if (meta.get("year") or "").isdigit() else None
    standard.version = meta.get("version", "")
    standard.scope = scope_text
    standard.plain_summary = meta.get("plain-summary", "")
    standard.product_category = meta.get("category", "")
    standard.keywords = _split_list(meta.get("keywords"))
    standard.covered_areas = [a.strip() for a in (meta.get("covered-areas") or "").split(",") if a.strip()]
    standard.source_url = meta.get("source-url", "")
    standard.source_type = meta.get("source-type", "demo")
    standard.document_id = standard_id
    standard.document_type = meta.get("document-type", "standard")
    standard.document_path = str(Path(doc.source_path).as_posix())
    standard.is_verified = _bool(meta.get("verified"), False)
    standard.is_demo = _bool(meta.get("mock"), True)

    if entry is not None:
        # The manifest overrides inline metadata - it is the record that was
        # validated, and it is the only thing that can grant verified status.
        standard.document_id = entry.document_id or standard_id
        standard.document_type = entry.document_type or standard.document_type
        standard.source_url = entry.source_url or standard.source_url
        standard.source_type = entry.source_type or standard.source_type
        standard.is_verified = bool(entry.is_verified)
        standard.is_demo = bool(entry.is_demo)
        if entry.title and not meta.get("title"):
            standard.title = entry.title
        if entry.is_number and not meta.get("is-number"):
            standard.is_number = entry.is_number
            standard.normalized_number = (
                normalize_is_number(entry.is_number) or entry.is_number.upper()
            )
        if entry.retrieved_at:
            try:
                standard.retrieved_at = datetime.fromisoformat(entry.retrieved_at)
            except ValueError:
                standard.retrieved_at = None
        # Cataloguing metadata, applied only where the document itself carried
        # none. Without it a PDF has no category or keywords and can never be
        # matched to a product by the metadata leg of hybrid retrieval.
        if entry.product_category and not meta.get("category"):
            standard.product_category = entry.product_category
        if entry.keywords and not meta.get("keywords"):
            standard.keywords = list(entry.keywords)
        if entry.covered_areas and not meta.get("covered-areas"):
            standard.covered_areas = list(entry.covered_areas)

    # A verified document can never also be demo, and vice versa.
    if standard.is_verified:
        standard.is_demo = False
    standard.is_mock = standard.is_demo
    return standard


def _english(text: str) -> str:
    """Text as it should be stored when the corpus is English-only."""
    return strip_devanagari(text) if settings.ingest_english_only else text


def _chunk_id(standard_id: str, clause: Any, seen: Optional[set] = None) -> str:
    """A stable, unique id for one clause chunk.

    Real BIS documents restart numbering inside annexes, so "1" can legitimately
    occur several times in one document. The clause number alone is therefore
    not unique; repeats get an occurrence suffix rather than colliding on the
    ``chunk_id`` unique constraint. Deterministic: the same document always
    produces the same ids, so re-ingestion stays idempotent.
    """
    suffix = f"-p{clause.part}" if clause.total_parts > 1 else ""
    base = f"{standard_id}::c{clause.clause_number}{suffix}"
    if seen is None:
        return base
    candidate = base
    occurrence = 2
    while candidate in seen:
        candidate = f"{base}-n{occurrence}"
        occurrence += 1
    seen.add(candidate)
    return candidate


def ingest_documents(
    db: Session,
    directory: Optional[Path] = None,
    paths: Optional[Sequence[Path]] = None,
    *,
    rebuild_vectors: bool = True,
) -> IngestionReport:
    report = IngestionReport()

    if paths:
        docs = []
        for path in paths:
            doc = parse_document(Path(path))
            if doc.clauses:
                docs.append(doc)
            else:
                report.skipped.append(f"{Path(path).name}: no clauses recognised")
    else:
        docs = parse_directory(Path(directory))

    if not docs:
        logger.warning("No ingestible documents found.")
        return report

    manifest = load_manifest()
    provenance = index_by_filename(manifest)
    report.warnings.extend(manifest.errors)
    report.warnings.extend(manifest.warnings)

    store = get_vector_store()
    report.embedding_backend = get_embedding_backend().name
    report.vector_backend = store.name

    standard_ids: List[str] = []
    standard_docs: List[str] = []
    standard_meta: List[Dict[str, Any]] = []

    clause_ids: List[str] = []
    clause_docs: List[str] = []
    clause_meta: List[Dict[str, Any]] = []

    for doc in docs:
        entry = provenance.get(Path(doc.source_path).name.lower())
        standard = upsert_standard_from_document(db, doc, entry)
        db.flush()
        #: chunk ids already used by this document, so repeated clause numbers
        #: (common across annexes in real BIS PDFs) cannot collide.
        used_chunk_ids: set = set()
        report.documents += 1
        report.standards += 1
        report.warnings.extend(f"{standard.id}: {w}" for w in doc.warnings)
        if standard.is_verified:
            report.verified_documents += 1
        else:
            report.demo_documents += 1

        # Replace this standard's clauses so re-ingestion is idempotent.
        db.query(StandardClause).filter(
            StandardClause.standard_id == standard.id
        ).delete(synchronize_session=False)
        db.flush()

        for clause in doc.clauses:
            # A bilingual gazette carries the same order twice, Hindi then
            # English. Keeping both indexes one document as two, and quotes the
            # Hindi rendering back to an English-speaking reader.
            if settings.ingest_english_only and is_predominantly_devanagari(clause.text):
                report.skipped_non_english += 1
                continue
            chunk_id = _chunk_id(standard.id, clause, used_chunk_ids)
            clause_text = _english(clause.text)
            row = StandardClause(
                id=chunk_id,
                standard_id=standard.id,
                section_number=clause.section_number,
                clause_number=clause.clause_number,
                heading=_english(clause.breadcrumb or clause.display_heading),
                text=clause_text,
                page_number=clause.page_number,
                clause_type=clause.clause_type,
                chunk_id=chunk_id,
                token_estimate=max(1, len(clause_text) // 4),
                table_json={},
                is_table=False,
            )
            db.add(row)
            report.clauses += 1

            clause_ids.append(chunk_id)
            clause_docs.append(
                f"{standard.is_number} {standard.title}. Clause {clause.clause_number}. "
                f"{_english(clause.breadcrumb)}. {clause_text}"
            )
            clause_meta.append(
                {
                    "chunk_id": chunk_id,
                    "standard_id": standard.id,
                    "is_number": standard.is_number,
                    "version": standard.version or "",
                    "section": clause.section_number,
                    "clause": clause.clause_number,
                    "heading": clause.breadcrumb,
                    "page": clause.page_number if clause.page_number is not None else -1,
                    # The real document type, not a blanket "standard": a
                    # Product Manual or QCO chunk must stay distinguishable
                    # from full Indian Standard text everywhere it surfaces.
                    "document_type": standard.document_type or "standard",
                    "clause_type": clause.clause_type,
                    "source_url": standard.source_url or "",
                    "is_verified": bool(standard.is_verified),
                }
            )

        for index, table in enumerate(doc.tables, start=1):
            searchable = table.searchable_text
            if not searchable.strip():
                continue
            if settings.ingest_english_only and is_predominantly_devanagari(searchable):
                report.skipped_non_english += 1
                continue
            chunk_id = f"{standard.id}::t{index}"
            while chunk_id in used_chunk_ids:  # pragma: no cover - defensive
                index += 1
                chunk_id = f"{standard.id}::t{index}"
            used_chunk_ids.add(chunk_id)
            clause_number = table.nearest_clause or f"T{index}"
            searchable = _english(searchable)
            heading = _english(table.caption) or f"Table {index}"
            db.add(
                StandardClause(
                    id=chunk_id,
                    standard_id=standard.id,
                    section_number=clause_number.split(".")[0],
                    clause_number=clause_number,
                    heading=heading,
                    text=searchable,
                    page_number=table.page_number,
                    clause_type="table",
                    chunk_id=chunk_id,
                    token_estimate=max(1, len(searchable) // 4),
                    table_json=table.as_dict(),
                    is_table=True,
                )
            )
            report.tables += 1
            report.clauses += 1
            clause_ids.append(chunk_id)
            clause_docs.append(
                f"{standard.is_number} {standard.title}. {heading}. {searchable}"
            )
            clause_meta.append(
                {
                    "chunk_id": chunk_id,
                    "standard_id": standard.id,
                    "is_number": standard.is_number,
                    "version": standard.version or "",
                    "section": clause_number.split(".")[0],
                    "clause": clause_number,
                    "heading": heading,
                    "page": table.page_number if table.page_number is not None else -1,
                    "document_type": standard.document_type or "standard",
                    "clause_type": "table",
                    "source_url": standard.source_url or "",
                    "is_verified": bool(standard.is_verified),
                }
            )

        standard_ids.append(standard.id)
        standard_docs.append(_standard_document_text(standard))
        standard_meta.append(
            {
                "standard_id": standard.id,
                "is_number": standard.is_number,
                "title": standard.title,
                "category": standard.product_category,
                "document_type": "standard_summary",
                "is_verified": bool(standard.is_verified),
            }
        )

    db.commit()

    if rebuild_vectors:
        logger.info("Embedding %s standards and %s clauses...", len(standard_ids), len(clause_ids))
        store.upsert(STANDARDS_COLLECTION, standard_ids, standard_docs, standard_meta)
        store.upsert(CLAUSES_COLLECTION, clause_ids, clause_docs, clause_meta)

    get_bm25_index().invalidate()

    run = IngestionRun(
        id=str(uuid.uuid4()),
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        documents=report.documents,
        chunks=report.clauses,
        embedding_backend=report.embedding_backend,
        vector_backend=report.vector_backend,
        notes=f"directory={directory}",
    )
    db.add(run)
    db.commit()

    logger.info("Ingestion complete: %s", report.as_dict())
    return report
