"""ComplianceGapAnalyzer - requirement-by-requirement pre-compliance assessment.

The analyzer never asks a model "is this product compliant?". It walks the
structured requirements of every applicable standard and, for each one:

1. checks whether the requirement applies to this product at all,
2. looks for product evidence of the right kind,
3. evaluates any machine-checkable rule against the declared attributes,
4. assigns one of the seven closed statuses,
5. records the reason and the clause citation that produced it.

A language model may only rewrite the *reason* text. It cannot change a status,
and any status it returns is validated against the closed enumeration before it
is used - so the assessment stays reproducible.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pymongo.database import Database

from app.core.constants import ASSESSABLE_STATUSES, ComplianceStatus
from app.core.text_utils import coerce_number
from app.db.repositories import clauses as clauses_repo
from app.db.repositories import evidence as evidence_repo
from app.db.repositories import products as products_repo
from app.db.repositories import requirements as requirements_repo
from app.db.repositories import standards as standards_repo
from app.llm.service import LLMService, get_llm
from app.models import (
    ComplianceRequirement,
    ComplianceResult,
    Product,
    ProductEvidence,
    ProductStandardMatch,
    Standard,
    StandardClause,
)
from app.schemas.models import ClauseRef, ReadinessSummary, RequirementResult
from app.services.serializers import clause_ref

logger = logging.getLogger(__name__)

READINESS_TOOLTIP = (
    "This score reflects the proportion of identified requirements that currently "
    "have supporting information on file. It is a preparation indicator, not an "
    "official BIS certification result, and it does not assess whether the "
    "evidence itself would be accepted by a certifying body."
)

#: Evidence kinds that a missing item should be reported as.
MISSING_STATUS_BY_EVIDENCE = {
    "test_report": ComplianceStatus.TEST_REQUIRED,
    "document": ComplianceStatus.DOCUMENT_REQUIRED,
    "material_certificate": ComplianceStatus.DOCUMENT_REQUIRED,
    "marking_artwork": ComplianceStatus.DOCUMENT_REQUIRED,
    "inspection": ComplianceStatus.OFFICIAL_VERIFICATION_REQUIRED,
    "declared_value": ComplianceStatus.UNKNOWN,
}


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

def _truthy(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "yes", "y", "1", "fitted", "provided", "present"):
        return True
    if text in ("false", "no", "n", "0", "not fitted", "absent", "none"):
        return False
    return None


def evaluate_rule(rule: Dict[str, Any], attributes: Dict[str, Any]) -> Tuple[Optional[bool], str]:
    """Evaluate a machine-checkable rule.

    Returns (passed, explanation). ``passed`` is None when the attribute the
    rule depends on has not been declared - that is an UNKNOWN, never a pass.
    """
    attribute = rule.get("attribute")
    operator = (rule.get("operator") or "").lower()
    expected = rule.get("value")
    unit = rule.get("unit") or ""
    if not attribute or not operator:
        return None, "No machine-checkable rule is attached to this requirement."

    if attribute not in attributes or attributes.get(attribute) in (None, "", []):
        return None, f"'{attribute.replace('_', ' ')}' has not been declared for this product."

    actual = attributes[attribute]
    shown = f"{actual}{(' ' + unit) if unit else ''}"

    if operator == "not_empty":
        ok = str(actual).strip() != ""
        return ok, (
            f"Declared value '{actual}' is present."
            if ok else f"'{attribute.replace('_', ' ')}' is empty."
        )

    if operator == "is_true":
        flag = _truthy(actual)
        if flag is None:
            return None, f"Declared value '{actual}' could not be read as yes/no."
        return flag, (
            f"Declared as present ('{actual}')."
            if flag else f"Declared as NOT present ('{actual}')."
        )

    if operator == "in":
        options = [str(o).strip().lower() for o in (expected or [])]
        ok = str(actual).strip().lower() in options
        return ok, (
            f"Declared value '{actual}' is one of the accepted options."
            if ok
            else f"Declared value '{actual}' is not one of {expected}."
        )

    if operator == "equals":
        ok = str(actual).strip().lower() == str(expected).strip().lower()
        return ok, f"Declared '{actual}' vs required '{expected}'."

    actual_num = coerce_number(actual)
    if actual_num is None:
        return None, f"Declared value '{actual}' is not numeric, so the limit cannot be checked."

    if operator == "between":
        low, high = float(expected[0]), float(expected[1])
        ok = low <= actual_num <= high
        return ok, f"Declared {shown} against the permitted range {low}-{high} {unit}.".strip()

    limit = coerce_number(expected)
    if limit is None:
        return None, "The requirement limit could not be interpreted."

    comparisons = {
        "lte": (actual_num <= limit, "must not exceed"),
        "lt": (actual_num < limit, "must be below"),
        "gte": (actual_num >= limit, "must be at least"),
        "gt": (actual_num > limit, "must be above"),
    }
    if operator not in comparisons:
        return None, f"Unsupported rule operator '{operator}'."
    ok, phrase = comparisons[operator]
    return ok, f"Declared {shown} against the limit that it {phrase} {limit} {unit}.".strip()


def rule_applies(rule: Dict[str, Any], attributes: Dict[str, Any]) -> Optional[bool]:
    """Evaluate an applies_when condition. None = cannot tell."""
    if not rule:
        return True
    passed, _ = evaluate_rule(rule, attributes)
    return passed


# ---------------------------------------------------------------------------
# Evidence matching
# ---------------------------------------------------------------------------

#: Evidence of these kinds can satisfy a requirement asking for the key kind.
EVIDENCE_EQUIVALENTS = {
    "test_report": {"test_report"},
    "document": {"document", "test_report", "material_certificate"},
    "material_certificate": {"material_certificate", "document"},
    "marking_artwork": {"marking_artwork", "document"},
    "declared_value": {"declared_value", "document"},
    "inspection": {"inspection"},
}


def match_evidence(
    requirement: ComplianceRequirement, evidence: Sequence[ProductEvidence]
) -> Optional[ProductEvidence]:
    """Find evidence of the right kind whose subject matches the requirement.

    Text extracted from an uploaded document is searched too, so a report whose
    filename says nothing useful still matches on its contents.
    """
    keywords = [
        k.lower()
        for k in (requirement.check_rule_json or {}).get("match_keywords", [])
        if k
    ]
    accepted_types = EVIDENCE_EQUIVALENTS.get(requirement.evidence_type, {requirement.evidence_type})

    best: Optional[ProductEvidence] = None
    best_score = 0
    for item in evidence:
        if item.evidence_type not in accepted_types:
            continue
        haystack = " ".join(
            [
                item.name or "",
                item.value or "",
                item.original_filename or "",
                (item.extracted_text or "")[:20000],
            ]
        ).lower()
        covers = (item.metadata_json or {}).get("covers") or []
        if isinstance(covers, list) and requirement.requirement_code in covers:
            return item
        score = sum(1 for keyword in keywords if keyword in haystack)
        if score > best_score:
            best, best_score = item, score
    return best


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class ComplianceGapAnalyzer:
    def __init__(self, llm: Optional[LLMService] = None) -> None:
        self.llm = llm or get_llm()

    # ------------------------------------------------------------------
    def analyze(
        self, db: Database, product: Product, standard_ids: Optional[Sequence[str]] = None
    ) -> Dict[str, Any]:
        if not standard_ids:
            # Matches are embedded in the product document.
            standard_ids = [m.standard_id for m in product.matches]
        if not standard_ids:
            return {"results": [], "standard_ids": [], "note": "No standards matched yet."}

        requirements = requirements_repo(db).find(
            {"standard_id": {"$in": list(standard_ids)}}
        )
        evidence = evidence_repo(db).find({"product_id": product.id})
        attributes = dict(product.attributes_json or {})

        results: List[Dict[str, Any]] = []
        saved: List[ComplianceResult] = []
        for requirement in requirements:
            outcome = self._assess(requirement, attributes, evidence)
            results.append({"requirement": requirement, **outcome})
            saved.append(
                ComplianceResult(
                    id=f"cr-{uuid.uuid4().hex[:12]}",
                    product_id=product.id,
                    requirement_id=requirement.id,
                    status=outcome["status"].value,
                    reason=outcome["reason"],
                    evidence_id=outcome["evidence"].id if outcome["evidence"] else None,
                    confidence=outcome["confidence"],
                    recommended_action=outcome["recommended_action"],
                    decided_by=outcome["decided_by"],
                )
            )
        # One atomic replacement of the whole result set, rather than the SQL
        # DELETE-then-INSERT which could leave a partial assessment on failure.
        product.results = saved
        products_repo(db).update_fields(
            product.id, {"results": [r.to_doc() for r in saved]}
        )
        return {
            "results": results,
            "standard_ids": list(standard_ids),
            "evidence_count": len(evidence),
        }

    # ------------------------------------------------------------------
    def _assess(
        self,
        requirement: ComplianceRequirement,
        attributes: Dict[str, Any],
        evidence: Sequence[ProductEvidence],
    ) -> Dict[str, Any]:
        rule = dict(requirement.check_rule_json or {})
        applies_when = dict(requirement.applies_when_json or {})

        # 1. Does the requirement apply to this product at all?
        if applies_when:
            applicable = rule_applies(applies_when, attributes)
            if applicable is False:
                return self._outcome(
                    ComplianceStatus.NOT_APPLICABLE,
                    f"This requirement is conditional and the condition is not met for this "
                    f"product ({applies_when.get('attribute', '')} "
                    f"{applies_when.get('operator', '')} {applies_when.get('value', '')}).",
                    confidence=0.9,
                )
            if applicable is None:
                return self._outcome(
                    ComplianceStatus.UNKNOWN,
                    f"Whether this requirement applies depends on "
                    f"'{applies_when.get('attribute', '')}', which has not been declared.",
                    recommended_action=(
                        f"Declare '{applies_when.get('attribute', '')}' so applicability can "
                        f"be decided."
                    ),
                    confidence=0.4,
                )

        # 2. Requirements that only an accredited body / regulator can settle.
        if rule.get("official_verification_required"):
            return self._outcome(
                ComplianceStatus.OFFICIAL_VERIFICATION_REQUIRED,
                "This requirement depends on a licence or approval issued by the "
                "certifying authority, which this platform cannot verify.",
                recommended_action="Confirm the licence status with the certifying authority.",
                confidence=0.95,
            )

        matched = match_evidence(requirement, evidence)

        # 3. Machine-checkable limits against declared values.
        has_rule = bool(rule.get("attribute") and rule.get("operator"))
        if has_rule:
            passed, explanation = evaluate_rule(rule, attributes)
            numeric = (rule.get("operator") or "").lower() in {"lte", "lt", "gte", "gt", "between"}
            satisfied = "satisfies the clause limit" if numeric else "satisfies the clause"
            violated = "does not satisfy the clause limit" if numeric else "does not satisfy the clause"
            if passed is True:
                return self._outcome(
                    ComplianceStatus.SUPPORTED,
                    f"{explanation} The declared value {satisfied}.",
                    evidence=matched,
                    confidence=0.85,
                )
            if passed is False:
                return self._outcome(
                    ComplianceStatus.POTENTIAL_GAP,
                    f"{explanation} The declared value {violated}.",
                    recommended_action=(
                        "Re-check the declared value, or change the design so the clause "
                        "limit is met."
                    ),
                    evidence=matched,
                    confidence=0.85,
                )
            # passed is None -> the attribute is undeclared. Evidence may still help.
            if matched is not None:
                return self._outcome(
                    ComplianceStatus.SUPPORTED,
                    f"{explanation} Supporting evidence '{matched.name}' was supplied for "
                    f"this requirement.",
                    evidence=matched,
                    confidence=0.6,
                )
            return self._outcome(
                MISSING_STATUS_BY_EVIDENCE.get(
                    requirement.evidence_type, ComplianceStatus.UNKNOWN
                ),
                explanation,
                recommended_action=self._action_for(requirement),
                confidence=0.5,
            )

        # 4. Evidence-only requirements.
        if matched is not None:
            reason = (
                f"'{matched.name}' was supplied and is of the required kind "
                f"({requirement.evidence_type.replace('_', ' ')})."
            )
            stated = (matched.extracted_fields_json or {}).get("result")
            if stated:
                # Report the document's own wording, and be explicit that
                # reading it is not the same as assessing it.
                reason += (
                    f" The document states '{stated}'; that wording was read from the "
                    f"file, not assessed by this platform."
                )
            else:
                reason += (
                    " This platform records that evidence exists; it does not assess "
                    "the evidence itself."
                )
            return self._outcome(
                ComplianceStatus.SUPPORTED,
                reason,
                evidence=matched,
                confidence=0.7,
            )

        status = MISSING_STATUS_BY_EVIDENCE.get(
            requirement.evidence_type, ComplianceStatus.UNKNOWN
        )
        return self._outcome(
            status,
            f"No {requirement.evidence_type.replace('_', ' ')} covering this requirement was "
            f"found in the evidence supplied for this product.",
            recommended_action=self._action_for(requirement),
            confidence=0.8,
        )

    @staticmethod
    def _action_for(requirement: ComplianceRequirement) -> str:
        kind = requirement.evidence_type
        clause = requirement.source_clause_number
        if kind == "test_report":
            return (
                f"Arrange the test described in Clause {clause} at a laboratory competent "
                f"for the method, and upload the report."
            )
        if kind == "material_certificate":
            return f"Obtain the material certificate required by Clause {clause} from the supplier."
        if kind == "marking_artwork":
            return f"Provide the label/marking artwork that satisfies Clause {clause}."
        if kind == "declared_value":
            return f"Declare the design value that Clause {clause} constrains."
        return f"Prepare the document required by Clause {clause} and add it to the technical file."

    @staticmethod
    def _outcome(
        status: ComplianceStatus,
        reason: str,
        *,
        recommended_action: str = "",
        evidence: Optional[ProductEvidence] = None,
        confidence: float = 0.5,
        decided_by: str = "rule_engine",
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "reason": reason,
            "recommended_action": recommended_action,
            "evidence": evidence,
            "confidence": confidence,
            "decided_by": decided_by,
        }

    # ------------------------------------------------------------------
    def to_schema(self, db: Database, results: Sequence[Dict[str, Any]]) -> List[RequirementResult]:
        out: List[RequirementResult] = []
        standards: Dict[str, Standard] = {}
        for row in results:
            requirement: ComplianceRequirement = row["requirement"]
            standard = standards.get(requirement.standard_id)
            if standard is None:
                standard = standards_repo(db).get(requirement.standard_id)
                standards[requirement.standard_id] = standard
            clause = (
                clauses_repo(db).get(requirement.clause_id) if requirement.clause_id else None
            )
            if clause is not None and standard is not None:
                source = clause_ref(clause, standard)
            else:
                source = ClauseRef(
                    chunk_id=f"{requirement.standard_id}::c{requirement.source_clause_number}",
                    standard_id=requirement.standard_id,
                    is_number=standard.is_number if standard else requirement.standard_id,
                    display_number=standard.is_number if standard else requirement.standard_id,
                    clause_number=requirement.source_clause_number,
                    heading="",
                    excerpt=requirement.requirement_text,
                    is_verified=bool(standard.is_verified) if standard else False,
                )
            out.append(
                RequirementResult(
                    requirement_id=requirement.id,
                    requirement_code=requirement.requirement_code,
                    requirement_text=requirement.requirement_text,
                    category=requirement.category,
                    severity=requirement.severity,
                    evidence_type=requirement.evidence_type,
                    status=row["status"],
                    reason=row["reason"],
                    recommended_action=row.get("recommended_action", ""),
                    confidence=row.get("confidence", 0.0),
                    decided_by=row.get("decided_by", "rule_engine"),
                    matched_evidence=row["evidence"].name if row.get("evidence") else None,
                    matched_evidence_id=row["evidence"].id if row.get("evidence") else None,
                    source=source,
                )
            )
        return out

    def load_saved(self, db: Database, product: Product) -> List[RequirementResult]:
        requirements = requirements_repo(db)
        evidence = evidence_repo(db)
        payload: List[Dict[str, Any]] = []
        for row in product.results:
            requirement = requirements.get(row.requirement_id)
            if requirement is None:
                continue
            payload.append(
                {
                    "requirement": requirement,
                    "status": ComplianceStatus(row.status),
                    "reason": row.reason,
                    "recommended_action": row.recommended_action,
                    "evidence": evidence.get(row.evidence_id) if row.evidence_id else None,
                    "confidence": row.confidence,
                    "decided_by": row.decided_by,
                }
            )
        return self.to_schema(db, payload)


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------

def build_readiness(results: Sequence[RequirementResult]) -> ReadinessSummary:
    by_status: Dict[str, int] = {}
    by_category: Dict[str, Dict[str, int]] = {}
    supported = 0
    assessable = 0

    for result in results:
        by_status[result.status.value] = by_status.get(result.status.value, 0) + 1
        category = by_category.setdefault(result.category, {})
        category[result.status.value] = category.get(result.status.value, 0) + 1
        if result.status in ASSESSABLE_STATUSES:
            assessable += 1
            if result.status == ComplianceStatus.SUPPORTED:
                supported += 1

    percentage = int(round((supported / assessable) * 100)) if assessable else 0
    return ReadinessSummary(
        percentage=percentage,
        supported=supported,
        assessable=assessable,
        total_requirements=len(results),
        tooltip=READINESS_TOOLTIP,
        by_status=by_status,
        by_category=by_category,
    )
