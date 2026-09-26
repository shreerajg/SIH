"""DB entity -> API schema conversion."""
from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.text_utils import display_is_number, truncate
from app.models import ComplianceRequirement, Standard, StandardClause
from app.schemas.models import ClauseRef, ProductProfile, StandardSummary


def standard_summary(db: Session, standard: Standard) -> StandardSummary:
    clause_count = (
        db.query(func.count(StandardClause.id))
        .filter(StandardClause.standard_id == standard.id)
        .scalar()
        or 0
    )
    requirement_count = (
        db.query(func.count(ComplianceRequirement.id))
        .filter(ComplianceRequirement.standard_id == standard.id)
        .scalar()
        or 0
    )
    return StandardSummary(
        id=standard.id,
        is_number=standard.is_number,
        display_number=display_is_number(standard.normalized_number) or standard.is_number,
        title=standard.title,
        year=standard.year,
        version=standard.version,
        product_category=standard.product_category or "",
        covered_areas=list(standard.covered_areas or []),
        keywords=list(standard.keywords or []),
        source_type=standard.source_type or "demo",
        source_url=standard.source_url or None,
        is_verified=bool(standard.is_verified),
        is_mock=bool(standard.is_mock),
        document_type=standard.document_type or "standard",
        retrieved_at=standard.retrieved_at.date().isoformat() if standard.retrieved_at else None,
        clause_count=int(clause_count),
        requirement_count=int(requirement_count),
    )


def clause_ref(
    clause: StandardClause,
    standard: Standard,
    *,
    score: Optional[float] = None,
    excerpt_chars: int = 480,
) -> ClauseRef:
    return ClauseRef(
        chunk_id=clause.chunk_id,
        standard_id=standard.id,
        is_number=standard.is_number,
        display_number=display_is_number(standard.normalized_number) or standard.is_number,
        version=standard.version,
        clause_number=clause.clause_number,
        heading=clause.heading or "",
        page_number=clause.page_number,
        clause_type=clause.clause_type,
        excerpt=truncate(clause.text, excerpt_chars),
        source_url=standard.source_url or None,
        is_verified=bool(standard.is_verified),
        document_type=standard.document_type or "standard",
        document_title=standard.title or "",
        relevance_score=round(score, 4) if score is not None else None,
    )


def clause_refs(
    db: Session, clauses: Iterable[StandardClause], scores: Optional[dict] = None
) -> List[ClauseRef]:
    scores = scores or {}
    standards = {}
    out: List[ClauseRef] = []
    for clause in clauses:
        standard = standards.get(clause.standard_id)
        if standard is None:
            standard = db.get(Standard, clause.standard_id)
            standards[clause.standard_id] = standard
        if standard is None:
            continue
        out.append(clause_ref(clause, standard, score=scores.get(clause.chunk_id)))
    return out


def product_profile(product) -> ProductProfile:
    from app.schemas.models import MissingField

    missing = []
    for item in product.missing_fields_json or []:
        if isinstance(item, dict):
            missing.append(MissingField(**item))
    return ProductProfile(
        id=product.id,
        name=product.name,
        description=product.description or "",
        category=product.category or "",
        attributes=dict(product.attributes_json or {}),
        missing_fields=missing,
        profile_source=product.profile_source or "deterministic",
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
