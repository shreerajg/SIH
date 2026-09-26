"""Product understanding, interview, discovery and compliance endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.api.deps import db_session, get_product
from app.compliance.gap_analyzer import ComplianceGapAnalyzer, build_readiness
from app.core.constants import DISCLAIMER, ComplianceStatus
from app.core.text_utils import display_is_number
from app.models import (
    Product,
    ProductEvidence,
    ProductStandardMatch,
    Standard,
    StandardRelationship,
)
from app.schemas.models import (
    ComplianceAnalyzeRequest,
    ComplianceResponse,
    ComplianceTwinResponse,
    DiscoverStandardsResponse,
    InterviewRequest,
    ProductAnalyzeRequest,
    ProductAnalyzeResponse,
    ProductProfile,
)
from app.db.repositories import evidence as evidence_repo
from app.db.repositories import products as products_repo
from app.db.repositories import relationships as relationships_repo
from app.db.repositories import standards as standards_repo
from app.services.amendments import AmendmentService
from app.services.product_interview import (
    PRODUCT_FAMILY_FIELD,
    ProductInterviewService,
)
from app.services.product_understanding import (
    ProductUnderstandingService,
    normalise_answer,
)
from app.services.serializers import product_profile, standard_summary
from app.services.standard_discovery import StandardDiscoveryService
from app.services.taxonomy import CATEGORY_BY_KEY

router = APIRouter(prefix="/products", tags=["products"])


@router.post("/analyze", response_model=ProductAnalyzeResponse)
def analyze_product(
    payload: ProductAnalyzeRequest, db: Database = Depends(db_session)
) -> ProductAnalyzeResponse:
    service = ProductUnderstandingService()
    profile = service.analyze(payload.description, payload.name)
    product = service.persist(db, profile)
    return ProductAnalyzeResponse(
        product=product_profile(product),
        interview_required=bool(product.missing_fields_json),
        notes=profile.get("notes", []),
        llm_used=profile.get("llm_used", False),
    )


@router.get("/{product_id}", response_model=ProductProfile)
def get_product_profile(product: Product = Depends(get_product)) -> ProductProfile:
    return product_profile(product)


@router.post("/{product_id}/interview", response_model=ProductAnalyzeResponse)
def answer_interview(
    payload: InterviewRequest,
    product: Product = Depends(get_product),
    db: Database = Depends(db_session),
) -> ProductAnalyzeResponse:
    attributes: Dict[str, Any] = dict(product.attributes_json or {})
    notes: List[str] = []

    for answer in payload.answers:
        if answer.field == PRODUCT_FAMILY_FIELD:
            key = ProductInterviewService.resolve_family_answer(answer.value)
            if key:
                product.category = key
                spec = CATEGORY_BY_KEY[key]
                for attr, value in spec.implied_attributes.items():
                    attributes.setdefault(attr, value)
                notes.append(f"Product family set to '{spec.label}'.")
            else:
                notes.append(f"'{answer.value}' did not match a known product family.")
            continue
        field, value = normalise_answer(answer.field, answer.value)
        if value is None:
            continue
        attributes[field] = value

    product.attributes_json = attributes
    if payload.skip_remaining:
        product.missing_fields_json = []
        notes.append(
            "Continuing with the information available. Requirements that depend on the "
            "undeclared values will be reported as UNKNOWN rather than assumed."
        )
    else:
        product.missing_fields_json = ProductInterviewService().build_questions(
            product.category or "", attributes
        )
    refined = _refine_name(product.category, attributes)
    if refined:
        product.name = refined
    product.updated_at = datetime.utcnow()
    products_repo(db).save(product)

    return ProductAnalyzeResponse(
        product=product_profile(product),
        interview_required=bool(product.missing_fields_json),
        notes=notes,
        llm_used=False,
    )


@router.post("/{product_id}/discover-standards", response_model=DiscoverStandardsResponse)
def discover_standards(
    product: Product = Depends(get_product), db: Database = Depends(db_session)
) -> DiscoverStandardsResponse:
    service = StandardDiscoveryService()
    result = service.discover(db, product)
    return DiscoverStandardsResponse(
        product_id=product.id,
        matches=service.to_schema(db, result["matches"]),
        candidates_considered=result["candidates_considered"],
        llm_used=result.get("llm_used", False),
        notes=result.get("notes", []),
        disclaimer=DISCLAIMER,
    )


@router.get("/{product_id}/standards", response_model=DiscoverStandardsResponse)
def get_product_standards(
    product: Product = Depends(get_product), db: Database = Depends(db_session)
) -> DiscoverStandardsResponse:
    service = StandardDiscoveryService()
    matches = service.load_saved(db, product)
    return DiscoverStandardsResponse(
        product_id=product.id,
        matches=matches,
        candidates_considered=len(matches),
        llm_used=False,
        notes=[] if matches else ["Standards have not been discovered for this product yet."],
        disclaimer=DISCLAIMER,
    )


@router.post("/{product_id}/compliance/analyze", response_model=ComplianceResponse)
def run_compliance_analysis(
    payload: ComplianceAnalyzeRequest,
    product: Product = Depends(get_product),
    db: Database = Depends(db_session),
) -> ComplianceResponse:
    if payload.attributes:
        attributes = dict(product.attributes_json or {})
        for key, value in payload.attributes.items():
            field, coerced = normalise_answer(key, value)
            if coerced is not None:
                attributes[field] = coerced
        product.attributes_json = attributes
        product.updated_at = datetime.utcnow()
        products_repo(db).update_fields(
            product.id,
            {"attributes_json": attributes, "updated_at": product.updated_at},
        )

    if payload.evidence:
        # Replace only *declared* (checkbox) evidence. Uploaded documents are
        # file-backed and must survive a re-run of the declared-evidence form,
        # otherwise ticking a box would silently delete a manufacturer's upload.
        evidence_repo(db).delete_many(
            {
                "product_id": product.id,
                "$or": [{"file_path": ""}, {"file_path": None}],
            }
        )
        evidence_repo(db).save_many(
            ProductEvidence(
                id=f"ev-{uuid.uuid4().hex[:12]}",
                product_id=product.id,
                evidence_type=item.evidence_type,
                name=item.name,
                value=item.value,
                metadata_json=item.metadata,
            )
            for item in payload.evidence
        )

    # Matches are embedded in the product document.
    standard_ids = payload.standard_ids or [m.standard_id for m in product.matches]
    if not standard_ids:
        raise HTTPException(
            status_code=409,
            detail=(
                "No applicable standards are on file for this product. "
                "Run standard discovery before the pre-compliance analysis."
            ),
        )

    analyzer = ComplianceGapAnalyzer()
    raw = analyzer.analyze(db, product, standard_ids)
    results = analyzer.to_schema(db, raw["results"])
    standards = [
        standard_summary(db, s)
        for s in standards_repo(db).find({"_id": {"$in": list(standard_ids)}})
    ]
    evidence = _evidence_payload(db, product)
    return ComplianceResponse(
        product_id=product.id,
        product_name=product.name,
        generated_at=product.updated_at,
        standards=standards,
        results=results,
        readiness=build_readiness(results),
        evidence_provided=evidence,
        llm_used=False,
        disclaimer=DISCLAIMER,
    )


@router.get("/{product_id}/compliance", response_model=ComplianceTwinResponse)
def compliance_twin(
    product: Product = Depends(get_product), db: Database = Depends(db_session)
) -> ComplianceTwinResponse:
    discovery = StandardDiscoveryService()
    matches = discovery.load_saved(db, product)
    analyzer = ComplianceGapAnalyzer()
    results = analyzer.load_saved(db, product)
    readiness = build_readiness(results)
    standard_ids = [m.standard.id for m in matches]

    amendments = AmendmentService().for_standards(
        db,
        standard_ids,
        product_context=f"{product.name}: {product.description[:400]}",
        product=product,
    )

    summary = {
        "applicable_standards": len(matches),
        "requirements_identified": len(results),
        "supported": readiness.by_status.get(ComplianceStatus.SUPPORTED.value, 0),
        "potential_gaps": readiness.by_status.get(ComplianceStatus.POTENTIAL_GAP.value, 0),
        "test_evidence_required": readiness.by_status.get(
            ComplianceStatus.TEST_REQUIRED.value, 0
        ),
        "document_required": readiness.by_status.get(
            ComplianceStatus.DOCUMENT_REQUIRED.value, 0
        ),
        "unknown": readiness.by_status.get(ComplianceStatus.UNKNOWN.value, 0),
        "official_verification_required": readiness.by_status.get(
            ComplianceStatus.OFFICIAL_VERIFICATION_REQUIRED.value, 0
        ),
        "not_applicable": readiness.by_status.get(ComplianceStatus.NOT_APPLICABLE.value, 0),
        "amendment_alerts": len(amendments),
        "mandatory_standards": sum(
            1 for m in matches if m.regulatory.status.value == "MANDATORY"
        ),
        "unverified_regulatory": sum(
            1 for m in matches if m.regulatory.status.value == "UNABLE_TO_VERIFY"
        ),
    }

    return ComplianceTwinResponse(
        product=product_profile(product),
        summary=summary,
        readiness=readiness,
        standards=matches,
        results=results,
        testing_plan=_testing_plan(db, results),
        evidence=_evidence_payload(db, product),
        amendments=amendments,
        graph=_graph(db, product, matches),
        sources=_sources(matches, results),
        analysis_available=bool(results),
        disclaimer=DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Attributes that name the product better than the original sentence does.
_NAMING_ATTRIBUTES = {
    "water-heater": "heater_type",
    "helmet": "helmet_type",
    "electrical-appliance": "appliance_type",
}


def _refine_name(category: str, attributes: Dict[str, Any]) -> str:
    """Use an answered type attribute as the product name once it is known."""
    key = _NAMING_ATTRIBUTES.get(category or "")
    value = attributes.get(key) if key else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    spec = CATEGORY_BY_KEY.get(category or "")
    return spec.label if spec else ""


def _evidence_payload(db: Database, product: Product) -> List[Dict[str, Any]]:
    rows = evidence_repo(db).find({"product_id": product.id})
    return [
        {
            "id": row.id,
            "evidence_type": row.evidence_type,
            "name": row.name,
            "value": row.value,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def _test_method_references(
    db: Database, standard_ids: set
) -> Dict[str, Dict[str, Any]]:
    """For each standard, the standard it defers to for test procedure (if any).

    Read from the same StandardRelationship records the knowledge graph draws
    on - a test standard is never guessed, only reported when the corpus
    actually states one standard's test methods live in another.
    """
    if not standard_ids:
        return {}
    edges = relationships_repo(db).find(
        {
            "source_standard_id": {"$in": list(standard_ids)},
            "relationship_type": "references_test_method",
        }
    )
    if not edges:
        return {}
    target_ids = {e.target_standard_id for e in edges}
    targets = {
        s.id: s for s in standards_repo(db).find({"_id": {"$in": list(target_ids)}})
    }

    by_source: Dict[str, Dict[str, Any]] = {}
    for edge in edges:
        # First edge wins per source standard - deterministic, and the seed
        # corpus never gives one standard two test-method references anyway.
        by_source.setdefault(
            edge.source_standard_id,
            {
                "standard_id": edge.target_standard_id,
                "standard": (
                    display_is_number(targets[edge.target_standard_id].normalized_number)
                    or targets[edge.target_standard_id].is_number
                    if edge.target_standard_id in targets
                    else edge.target_standard_id
                ),
                "evidence": edge.evidence,
            },
        )
    return by_source


def _testing_plan(db: Database, results) -> List[Dict[str, Any]]:
    """A concrete test checklist derived from requirements needing test evidence.

    Each item carries a link to the specific evidence that satisfied it (when
    one exists, from either an upload or a declared checkbox) and, when the
    corpus states it, which standard actually specifies the test procedure -
    so "what do I test against" is answered alongside "what do I test".
    """
    test_requirements = [r for r in results if r.evidence_type == "test_report"]
    method_refs = _test_method_references(
        db, {r.source.standard_id for r in test_requirements}
    )

    plan: List[Dict[str, Any]] = []
    for result in test_requirements:
        plan.append(
            {
                "requirement_code": result.requirement_code,
                "test": result.requirement_text,
                "standard": result.source.display_number,
                "clause": result.source.clause_number,
                "status": result.status.value,
                "severity": result.severity,
                "action": result.recommended_action
                or "Evidence on file - retain the report in the technical file.",
                "chunk_id": result.source.chunk_id,
                "matched_evidence": result.matched_evidence,
                "evidence_id": result.matched_evidence_id,
                "test_method_reference": method_refs.get(result.source.standard_id),
            }
        )
    order = {
        ComplianceStatus.TEST_REQUIRED.value: 0,
        ComplianceStatus.POTENTIAL_GAP.value: 1,
        ComplianceStatus.UNKNOWN.value: 2,
        ComplianceStatus.SUPPORTED.value: 3,
    }
    plan.sort(key=lambda p: (order.get(p["status"], 4), p["requirement_code"]))
    return plan


def _graph(db: Database, product: Product, matches) -> Dict[str, Any]:
    """Knowledge graph built only from real relationship and QCO records."""
    if not matches:
        return {"nodes": [], "edges": [], "available": False}

    nodes: List[Dict[str, Any]] = [
        {"id": f"product:{product.id}", "type": "product", "label": product.name}
    ]
    edges: List[Dict[str, Any]] = []
    standard_ids = [m.standard.id for m in matches]

    for match in matches:
        node_id = f"standard:{match.standard.id}"
        nodes.append(
            {
                "id": node_id,
                "type": "standard",
                "label": match.standard.display_number,
                "title": match.standard.title,
                "relevance": match.relevance.value,
                "regulatory": match.regulatory.status.value,
            }
        )
        edges.append(
            {
                "source": f"product:{product.id}",
                "target": node_id,
                "type": "applicable_standard",
                "label": match.relevance.value,
            }
        )
        if match.regulatory.status.value == "MANDATORY":
            qco_id = f"qco:{match.standard.id}"
            nodes.append(
                {
                    "id": qco_id,
                    "type": "qco",
                    "label": match.regulatory.notification_number or "QCO",
                    "title": match.regulatory.qco_name or "",
                }
            )
            edges.append(
                {"source": node_id, "target": qco_id, "type": "regulated_by", "label": "QCO"}
            )

    for edge in relationships_repo(db).find(
        {"source_standard_id": {"$in": list(standard_ids)}}
    ):
        if f"standard:{edge.target_standard_id}" not in {n["id"] for n in nodes}:
            continue
        edges.append(
            {
                "source": f"standard:{edge.source_standard_id}",
                "target": f"standard:{edge.target_standard_id}",
                "type": edge.relationship_type,
                "label": edge.relationship_type.replace("_", " "),
                "evidence": edge.evidence,
            }
        )

    seen = set()
    unique_nodes = []
    for node in nodes:
        if node["id"] in seen:
            continue
        seen.add(node["id"])
        unique_nodes.append(node)
    return {"nodes": unique_nodes, "edges": edges, "available": True}


def _sources(matches, results) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for match in matches:
        for clause in match.evidence_clauses:
            if clause.chunk_id in seen:
                continue
            seen.add(clause.chunk_id)
            out.append(clause.model_dump())
    for result in results:
        if result.source.chunk_id in seen:
            continue
        seen.add(result.source.chunk_id)
        out.append(result.source.model_dump())
    return out
