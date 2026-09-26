"""Standard browsing, source inspection, RAG and consumer endpoints."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.constants import DISCLAIMER
from app.models import ComplianceRequirement, Standard, StandardClause, StandardRelationship
from app.rag.service import get_rag_service
from app.schemas.models import (
    AmendmentImpact,
    ConsumerLookupRequest,
    ConsumerStandardResponse,
    RAGRequest,
    RAGResponse,
    SourceDetail,
    StandardDetail,
    StandardSummary,
)
from app.services.amendments import AmendmentService, to_info
from app.services.consumer import ConsumerService
from app.services.regulatory import (
    regulatory_history,
    regulatory_overview,
    resolve_regulatory_status,
)
from app.services.serializers import clause_ref, standard_summary

router = APIRouter(tags=["standards"])


@router.get("/standards", response_model=List[StandardSummary])
def list_standards(
    category: str = Query(default=""),
    db: Session = Depends(db_session),
) -> List[StandardSummary]:
    query = db.query(Standard)
    if category:
        query = query.filter(Standard.product_category == category)
    return [standard_summary(db, s) for s in query.order_by(Standard.is_number).all()]


@router.get("/standards/graph")
def standards_graph(
    category: str = Query(default=""),
    focus: str = Query(default=""),
    regulatory: bool = Query(default=True),
    db: Session = Depends(db_session),
) -> Dict[str, Any]:
    """The corpus-wide standards knowledge graph, built from stored records only.

    ``category`` limits the view to one product category; ``focus`` returns one
    standard plus its one-hop neighbourhood. Registered before the
    ``/standards/{standard_id}`` route so "graph" is never read as an id.
    """
    from app.services.graph import get_graph_service

    return get_graph_service().build(
        db, category=category, focus=focus, include_regulatory=regulatory
    )


@router.get("/standards/{standard_id}", response_model=StandardDetail)
def get_standard(standard_id: str, db: Session = Depends(db_session)) -> StandardDetail:
    standard = db.get(Standard, standard_id)
    if standard is None:
        raise HTTPException(status_code=404, detail=f"No standard with id '{standard_id}'.")

    clauses = (
        db.query(StandardClause)
        .filter(StandardClause.standard_id == standard_id)
        .order_by(StandardClause.clause_number)
        .all()
    )
    categories: Dict[str, int] = {}
    for requirement in (
        db.query(ComplianceRequirement)
        .filter(ComplianceRequirement.standard_id == standard_id)
        .all()
    ):
        categories[requirement.category] = categories.get(requirement.category, 0) + 1

    related: List[Dict[str, Any]] = []
    for edge in (
        db.query(StandardRelationship)
        .filter(StandardRelationship.source_standard_id == standard_id)
        .all()
    ):
        target = db.get(Standard, edge.target_standard_id)
        if target is None:
            continue
        related.append(
            {
                "standard_id": target.id,
                "is_number": target.is_number,
                "title": target.title,
                "relationship_type": edge.relationship_type,
                "evidence": edge.evidence,
            }
        )

    amendments = [
        to_info(standard, a) for a in sorted(standard.amendments, key=lambda x: x.amendment_number)
    ]

    return StandardDetail(
        standard=standard_summary(db, standard),
        scope=standard.scope or "",
        plain_summary=standard.plain_summary or "",
        regulatory=resolve_regulatory_status(db, standard_id),
        clauses=[clause_ref(c, standard, excerpt_chars=2000) for c in clauses],
        requirement_categories=categories,
        related=related,
        amendments=amendments,
    )


@router.get("/standards/{standard_id}/findings")
def standard_findings(standard_id: str, db: Session = Depends(db_session)) -> Dict[str, Any]:
    """Plain-language, source-grounded findings for one document.

    Deterministic: each finding cites a clause that literally contains its
    topic term. No LLM, no invention — a document that supports nothing yields
    an empty list and an honest note.
    """
    from app.services.findings import findings_for_standard

    standard = db.get(Standard, standard_id)
    if standard is None:
        raise HTTPException(status_code=404, detail=f"No standard with id '{standard_id}'.")
    return findings_for_standard(db, standard_id, standard.document_type or "standard")


@router.get("/standards/{standard_id}/requirements")
def standard_requirements(standard_id: str, db: Session = Depends(db_session)) -> Dict[str, Any]:
    """The stored structured requirements for one document, grouped by category.

    Read-only listing of ``ComplianceRequirement`` rows — the same records the
    gap analyzer assesses against a product's declared values and evidence.
    Shown here without a product context, so no status is attached; only what
    the requirement asks for and where it comes from.
    """
    standard = db.get(Standard, standard_id)
    if standard is None:
        raise HTTPException(status_code=404, detail=f"No standard with id '{standard_id}'.")
    rows = (
        db.query(ComplianceRequirement)
        .filter(ComplianceRequirement.standard_id == standard_id)
        .order_by(ComplianceRequirement.category, ComplianceRequirement.requirement_code)
        .all()
    )
    return {
        "standard_id": standard_id,
        "requirements": [
            {
                "id": r.id,
                "requirement_code": r.requirement_code,
                "category": r.category,
                "requirement_text": r.requirement_text,
                "evidence_type": r.evidence_type,
                "severity": r.severity,
                "source_clause_number": r.source_clause_number,
            }
            for r in rows
        ],
    }


@router.get("/standards/{standard_id}/amendments", response_model=List[AmendmentImpact])
def standard_amendments(
    standard_id: str, db: Session = Depends(db_session)
) -> List[AmendmentImpact]:
    if db.get(Standard, standard_id) is None:
        raise HTTPException(status_code=404, detail=f"No standard with id '{standard_id}'.")
    return AmendmentService().for_standards(db, [standard_id])


@router.get("/standards/{standard_id}/regulatory")
def standard_regulatory(standard_id: str, db: Session = Depends(db_session)) -> Dict[str, Any]:
    """The regulatory position plus every stored record behind it.

    This is what the "View regulatory evidence" control opens. It exists so a
    status is never a bare word - the notification, dates and scheme that
    produced it are always one click away.
    """
    if db.get(Standard, standard_id) is None:
        raise HTTPException(status_code=404, detail=f"No standard with id '{standard_id}'.")
    status = resolve_regulatory_status(db, standard_id)
    return {
        "standard_id": standard_id,
        "status": status.model_dump(),
        "history": [record.model_dump() for record in regulatory_history(db, standard_id)],
        "note": (
            "Regulatory status is read from structured records only. A standard with "
            "no record is reported as UNABLE_TO_VERIFY, never as voluntary."
        ),
    }


@router.get("/sources/{chunk_id:path}", response_model=SourceDetail)
def get_source(chunk_id: str, db: Session = Depends(db_session)) -> SourceDetail:
    """Full text of one cited clause, plus its neighbours for context."""
    clause = db.query(StandardClause).filter(StandardClause.chunk_id == chunk_id).first()
    if clause is None:
        raise HTTPException(status_code=404, detail=f"No source with chunk id '{chunk_id}'.")
    standard = db.get(Standard, clause.standard_id)
    if standard is None:
        raise HTTPException(status_code=404, detail="The standard for this source is missing.")

    siblings = (
        db.query(StandardClause)
        .filter(
            StandardClause.standard_id == clause.standard_id,
            StandardClause.section_number == clause.section_number,
        )
        .order_by(StandardClause.clause_number)
        .all()
    )
    neighbours = [
        clause_ref(c, standard) for c in siblings if c.chunk_id != clause.chunk_id
    ][:6]

    return SourceDetail(
        chunk_id=clause.chunk_id,
        standard=standard_summary(db, standard),
        clause_number=clause.clause_number,
        heading=clause.heading or "",
        page_number=clause.page_number,
        text=clause.text,
        neighbours=neighbours,
    )


@router.post("/rag/query", response_model=RAGResponse)
def rag_query(payload: RAGRequest, db: Session = Depends(db_session)) -> RAGResponse:
    return get_rag_service().answer(
        db,
        payload.question,
        standard_ids=payload.standard_ids,
        product_id=payload.product_id,
        query_type=payload.query_type,
        conversation_id=payload.conversation_id,
    )


@router.get("/consumer/categories")
def consumer_categories(db: Session = Depends(db_session)) -> Dict[str, Any]:
    """Product types a consumer can browse without knowing an IS code.

    Built only from categories that actually have standards in the corpus -
    never from the full taxonomy, so nothing shown here is a dead end.
    """
    return {
        "categories": ConsumerService().browse_categories(db),
        "note": "Each entry reflects standards actually present in this corpus.",
    }


@router.post("/consumer/scan")
async def consumer_scan(
    file: UploadFile = File(...), db: Session = Depends(db_session)
) -> Dict[str, Any]:
    """Read a photographed label and look up whatever standard reference is on it.

    OCR only extracts candidate text - it never decides what standard a
    product is made to. Every candidate is run through the same lookup a
    consumer typing a code by hand would get, so a misread character comes
    back as "not found, closest matches shown", never as a fabricated answer.
    """
    from app.core.config import settings
    from app.services.ocr import OcrUploadError, get_ocr_service, validate_image

    data = await file.read()
    try:
        validate_image(data, settings.max_upload_mb)
    except OcrUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scan = get_ocr_service().scan(data, file.content_type or "")

    consumer_service = ConsumerService()
    result = None
    for candidate in scan.candidates:
        attempt = consumer_service.lookup(db, candidate)
        if attempt.found:
            result = attempt
            break
    if result is None and scan.raw_text:
        # No exact code recognised in the image - run the raw OCR text through
        # the same ranked, description-style match a typed product name gets.
        result = consumer_service.lookup(db, scan.raw_text[:120])

    return {
        "ocr_available": scan.available,
        "status": scan.status,
        "raw_text": scan.raw_text,
        "candidates": scan.candidates,
        "note": scan.note,
        "result": result.model_dump() if result else None,
        "disclaimer": DISCLAIMER,
    }


@router.get("/consumer/standard/{is_number:path}", response_model=ConsumerStandardResponse)
def consumer_lookup(is_number: str, db: Session = Depends(db_session)) -> ConsumerStandardResponse:
    return ConsumerService().lookup(db, is_number)


@router.post("/consumer/lookup", response_model=ConsumerStandardResponse)
def consumer_lookup_post(
    payload: ConsumerLookupRequest, db: Session = Depends(db_session)
) -> ConsumerStandardResponse:
    return ConsumerService().lookup(db, payload.query)


@router.get("/trust")
def trust_summary(db: Session = Depends(db_session)) -> Dict[str, Any]:
    """What the platform does to avoid inventing standards information."""
    from app.core.config import settings
    from app.llm.service import get_llm

    total_standards = db.query(Standard).count()
    verified = db.query(Standard).filter(Standard.is_verified.is_(True)).count()
    with_qco = (
        db.query(Standard.id)
        .join(Standard.qcos)
        .distinct()
        .count()
    )
    return {
        "dataset": {
            "standards": total_standards,
            "verified": verified,
            "demo": total_standards - verified,
            "standards_with_regulatory_record": with_qco,
            "standards_without_regulatory_record": total_standards - with_qco,
            "status": "demo" if verified < total_standards else "verified",
        },
        "controls": [
            {
                "name": "Closed candidate list",
                "what": "Standard discovery shows the model only the IDs retrieved from the corpus, and rejects any ID it returns that is not on that list.",
                "enforced_in": "app/services/standard_discovery.py",
            },
            {
                "name": "Evidence Shield",
                "what": "Every generated claim must cite a chunk_id that was actually in the retrieved context. Claims citing anything else are dropped; if nothing survives the answer becomes an explicit abstention.",
                "enforced_in": "app/rag/evidence_shield.py",
            },
            {
                "name": "Structured regulatory status",
                "what": "Mandatory / voluntary is read from the QCO table only. Absence of a record returns UNABLE_TO_VERIFY - never 'voluntary'.",
                "enforced_in": "app/services/regulatory.py",
            },
            {
                "name": "Closed status vocabulary",
                "what": "Gap analysis statuses come from a fixed enumeration produced by a rule engine. A model can rewrite a reason, never a status.",
                "enforced_in": "app/compliance/gap_analyzer.py",
            },
            {
                "name": "Deterministic amendment diff",
                "what": "Clause changes are computed with difflib against the stored old and new wording, not described from memory.",
                "enforced_in": "app/services/amendments.py",
            },
            {
                "name": "Provenance on every record",
                "what": "Each standard, clause, QCO and amendment carries source_type, is_verified and is_mock, and the UI labels demo data as such.",
                "enforced_in": "app/models/entities.py",
            },
        ],
        "retrieval": {
            "strategy": "two-stage hybrid",
            "stage_1": "standard discovery over title/scope/keywords (BM25 + dense + metadata affinity)",
            "stage_2": "clause retrieval restricted to the standards selected in stage 1",
            "weights": {
                "semantic": settings.weight_semantic,
                "bm25": settings.weight_bm25,
                "metadata": settings.weight_metadata,
            },
        },
        "llm": get_llm().status(),
        "disclaimer": DISCLAIMER,
    }
