"""Amendment impact intelligence.

The difference between the old and the new clause is computed deterministically
with difflib - a model is never asked what changed. Numeric limits that moved
are extracted so the UI can show "75 degC -> 70 degC" rather than a wall of
highlighted text.

The narrative is always framed as POTENTIAL impact. The platform never tells a
manufacturer that their product has become non-compliant.
"""
from __future__ import annotations

import difflib
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.core.constants import AmendmentRelevance
from app.core.text_utils import display_is_number
from app.llm.service import LLMService, get_llm
from app.models import (
    Amendment,
    ComplianceRequirement,
    ComplianceResult,
    Product,
    ProductStandardMatch,
    Standard,
)
from app.schemas.models import (
    AmendmentImpact,
    AmendmentInfo,
    DiffSegment,
    ProductAmendmentImpact,
)

logger = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([a-zA-Z%]{0,12})")

SYSTEM_PROMPT = (
    "You explain the potential impact of a standards amendment on a product. "
    "You are given the exact old and new clause text and the computed textual "
    "difference. Describe only what the difference implies. Never say a product "
    "is compliant or non-compliant, never invent a date, and never mention any "
    "clause other than the one shown."
)


def _fmt(value) -> Optional[str]:
    return value.date().isoformat() if value else None


def to_info(standard: Standard, amendment: Amendment) -> AmendmentInfo:
    return AmendmentInfo(
        id=amendment.id,
        standard_id=amendment.standard_id,
        is_number=standard.is_number,
        display_number=display_is_number(standard.normalized_number) or standard.is_number,
        amendment_number=amendment.amendment_number,
        publication_date=_fmt(amendment.publication_date),
        effective_date=_fmt(amendment.effective_date),
        affected_clause=amendment.affected_clause,
        summary=amendment.summary,
        old_text=amendment.old_text,
        new_text=amendment.new_text,
        is_verified=bool(amendment.is_verified),
        is_mock=bool(amendment.is_mock),
        source_url=amendment.source_url or None,
    )


def compute_diff(old_text: str, new_text: str) -> List[DiffSegment]:
    """Word-level diff, collapsed into contiguous runs for readable rendering."""
    old_words = re.findall(r"\S+\s*", old_text or "")
    new_words = re.findall(r"\S+\s*", new_text or "")
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    segments: List[DiffSegment] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segments.append(DiffSegment(op="equal", text="".join(old_words[i1:i2])))
        elif tag == "delete":
            segments.append(DiffSegment(op="delete", text="".join(old_words[i1:i2])))
        elif tag == "insert":
            segments.append(DiffSegment(op="insert", text="".join(new_words[j1:j2])))
        else:  # replace
            segments.append(DiffSegment(op="delete", text="".join(old_words[i1:i2])))
            segments.append(DiffSegment(op="insert", text="".join(new_words[j1:j2])))
    return [s for s in segments if s.text.strip()]


def changed_numbers(old_text: str, new_text: str) -> List[Dict[str, Any]]:
    """Pair up numeric limits that moved between the two wordings."""
    old_nums = [(m.group(1), m.group(2).strip()) for m in _NUMBER_RE.finditer(old_text or "")]
    new_nums = [(m.group(1), m.group(2).strip()) for m in _NUMBER_RE.finditer(new_text or "")]
    out: List[Dict[str, Any]] = []

    by_unit_old: Dict[str, List[str]] = {}
    by_unit_new: Dict[str, List[str]] = {}
    for value, unit in old_nums:
        by_unit_old.setdefault(unit.lower(), []).append(value)
    for value, unit in new_nums:
        by_unit_new.setdefault(unit.lower(), []).append(value)

    for unit in set(by_unit_old) | set(by_unit_new):
        olds = by_unit_old.get(unit, [])
        news = by_unit_new.get(unit, [])
        for index in range(max(len(olds), len(news))):
            old_value = olds[index] if index < len(olds) else None
            new_value = news[index] if index < len(news) else None
            if old_value != new_value:
                out.append(
                    {
                        "unit": unit or None,
                        "old": old_value,
                        "new": new_value,
                        "direction": _direction(old_value, new_value),
                    }
                )
    return out


def _direction(old_value: Optional[str], new_value: Optional[str]) -> str:
    if old_value is None:
        return "added"
    if new_value is None:
        return "removed"
    try:
        return "tightened" if float(new_value) < float(old_value) else "relaxed"
    except ValueError:
        return "changed"


class AmendmentService:
    def __init__(self, llm: Optional[LLMService] = None) -> None:
        self.llm = llm or get_llm()

    def assess_for_product(
        self,
        db: Session,
        amendment: Amendment,
        product: Optional[Product],
        affected_requirements: Sequence[str],
    ) -> ProductAmendmentImpact:
        """How this amendment relates to one specific product.

        Deliberately cautious. The platform can see whether the amended clause
        backs a requirement this product is actually assessed against, and
        whether evidence already exists for it - but it never concludes that a
        product has become non-compliant. That is a determination only a
        conformity assessment can make.
        """
        if product is None:
            return ProductAmendmentImpact(
                relevance=AmendmentRelevance.UNABLE_TO_VERIFY,
                reason="No product context was supplied, so relevance cannot be assessed.",
            )

        applies = (
            db.query(ProductStandardMatch)
            .filter(
                ProductStandardMatch.product_id == product.id,
                ProductStandardMatch.standard_id == amendment.standard_id,
            )
            .first()
        )
        if applies is None:
            return ProductAmendmentImpact(
                relevance=AmendmentRelevance.NO_DIRECT_MATCH_FOUND,
                reason=(
                    f"{amendment.standard_id} is not among the standards matched to this "
                    "product, so this amendment does not appear to reach it."
                ),
            )

        codes = sorted(affected_requirements)
        if not codes:
            return ProductAmendmentImpact(
                relevance=AmendmentRelevance.REQUIRES_REVIEW,
                reason=(
                    f"The amended Clause {amendment.affected_clause} belongs to a standard "
                    "that applies to this product, but it does not map to any structured "
                    "requirement currently being assessed. Review it manually."
                ),
            )

        results = (
            db.query(ComplianceResult, ComplianceRequirement)
            .join(
                ComplianceRequirement,
                ComplianceResult.requirement_id == ComplianceRequirement.id,
            )
            .filter(
                ComplianceResult.product_id == product.id,
                ComplianceRequirement.requirement_code.in_(codes),
            )
            .all()
        )
        supported = sorted(
            requirement.requirement_code
            for result, requirement in results
            if result.status == "SUPPORTED"
        )

        if supported:
            reason = (
                f"Clause {amendment.affected_clause} backs requirement(s) "
                f"{', '.join(supported)}, which this product currently reports as "
                "supported. Evidence produced against the previous wording should be "
                "reviewed against the amended wording."
            )
        else:
            reason = (
                f"Clause {amendment.affected_clause} backs requirement(s) "
                f"{', '.join(codes)}, which apply to this product. The amended wording "
                "should be taken into account when that evidence is prepared."
            )

        return ProductAmendmentImpact(
            relevance=AmendmentRelevance.LIKELY_RELEVANT,
            reason=reason,
            affected_requirement_codes=codes,
            supported_requirement_codes=supported,
        )

    def for_standards(
        self,
        db: Session,
        standard_ids: Sequence[str],
        product_context: str = "",
        product: Optional[Product] = None,
    ) -> List[AmendmentImpact]:
        if not standard_ids:
            return []
        rows = (
            db.query(Amendment)
            .filter(Amendment.standard_id.in_(list(standard_ids)))
            # MySQL has no NULLS LAST - see the note in services/regulatory.py.
            .order_by(Amendment.effective_date.is_(None), Amendment.effective_date.desc())
            .all()
        )
        out: List[AmendmentImpact] = []
        for amendment in rows:
            standard = db.get(Standard, amendment.standard_id)
            if standard is None:
                continue
            diff = compute_diff(amendment.old_text, amendment.new_text)
            numbers = changed_numbers(amendment.old_text, amendment.new_text)
            affected = [
                r.requirement_code
                for r in db.query(ComplianceRequirement)
                .filter(
                    ComplianceRequirement.standard_id == amendment.standard_id,
                    ComplianceRequirement.source_clause_number.startswith(
                        amendment.affected_clause
                    ),
                )
                .all()
            ]
            impact, source = self._impact_text(amendment, numbers, product_context)
            out.append(
                AmendmentImpact(
                    amendment=to_info(standard, amendment),
                    diff=diff,
                    changed_numbers=numbers,
                    potential_impact=impact,
                    impact_source=source,
                    affected_requirements=affected,
                    product_impact=self.assess_for_product(db, amendment, product, affected),
                )
            )
        return out

    # ------------------------------------------------------------------
    def _impact_text(
        self, amendment: Amendment, numbers: List[Dict[str, Any]], product_context: str
    ) -> tuple:
        deterministic = self._deterministic_impact(amendment, numbers)
        if not self.llm.available:
            return deterministic, "deterministic"

        prompt = (
            f"Clause {amendment.affected_clause} of a standard has been amended "
            f"({amendment.amendment_number}).\n\n"
            f"OLD TEXT:\n{amendment.old_text}\n\nNEW TEXT:\n{amendment.new_text}\n\n"
            f"Numeric changes detected: {numbers}\n"
            + (f"Product context: {product_context}\n" if product_context else "")
            + "\nIn 2-3 sentences, describe the POTENTIAL impact on a manufacturer of such a "
              "product. Begin with what changed. Do not state compliance or non-compliance."
        )
        text = self.llm.text(SYSTEM_PROMPT, prompt, max_tokens=320)
        if not text:
            return deterministic, "deterministic"
        return text.strip(), "llm"

    @staticmethod
    def _deterministic_impact(amendment: Amendment, numbers: List[Dict[str, Any]]) -> str:
        parts = [
            f"Potential impact: Clause {amendment.affected_clause} was changed by "
            f"{amendment.amendment_number}."
        ]
        for change in numbers:
            unit = f" {change['unit']}" if change.get("unit") else ""
            if change["direction"] == "tightened":
                parts.append(
                    f"The limit moved from {change['old']}{unit} to {change['new']}{unit}, "
                    f"which is tighter than before."
                )
            elif change["direction"] == "relaxed":
                parts.append(
                    f"The limit moved from {change['old']}{unit} to {change['new']}{unit}, "
                    f"which is less restrictive than before."
                )
            elif change["direction"] == "added":
                parts.append(f"A new value of {change['new']}{unit} was introduced.")
            else:
                parts.append(f"A value of {change['old']}{unit} was removed.")
        if amendment.effective_date:
            parts.append(
                f"The amended wording takes effect from "
                f"{amendment.effective_date.date().isoformat()}."
            )
        parts.append(
            "Review the affected design values and any test evidence issued against the "
            "previous wording. This is an indication, not a compliance determination."
        )
        return " ".join(parts)
