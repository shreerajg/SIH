"""Consumer mode - plain-language explanation of a standard.

A consumer types an IS code off a product label. The lookup is deterministic
(normalisation + database), the explanation is built from the standard's own
scope clause, and the regulatory line still comes from the structured QCO
table. A language model, when configured, only rewrites the explanation into
simpler language - it cannot add a fact that is not in the record.

Two more entry points exist for a consumer who does not have a code to type:
browsing by product type, and typing a plain product name (``search``) that
is ranked against real title/keyword/coverage text rather than an LLM guess.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.constants import DISCLAIMER
from app.core.text_utils import content_tokens, normalize_is_number, truncate
from app.llm.service import LLMService, get_llm
from app.models import Standard, StandardClause
from app.schemas.models import ConsumerStandardResponse, StandardSummary
from app.services.regulatory import resolve_regulatory_status
from app.services.serializers import clause_ref, standard_summary
from app.services.taxonomy import CATEGORY_BY_KEY, CATEGORY_TO_CORPUS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You explain Indian Standards to ordinary consumers who are not engineers. "
    "You are given the standard's title, scope text and the areas it covers. "
    "Rewrite that into plain language a shopper can use. Rules: use only the "
    "information given; do not mention any other standard; do not say whether "
    "the standard is mandatory or voluntary; keep it under 90 words; avoid "
    "jargon and avoid clause numbers."
)


class ConsumerService:
    def __init__(self, llm: Optional[LLMService] = None) -> None:
        self.llm = llm or get_llm()

    def lookup(self, db: Session, query: str) -> ConsumerStandardResponse:
        normalized = normalize_is_number(query)
        standard: Optional[Standard] = None

        if normalized:
            standard = (
                db.query(Standard).filter(Standard.normalized_number == normalized).first()
            )
        if standard is None:
            # Allow a raw corpus id (DEMO-STD-001) or an exact number match.
            cleaned = (query or "").strip().upper()
            standard = db.get(Standard, cleaned) or (
                db.query(Standard).filter(Standard.is_number == cleaned).first()
            )

        if standard is None:
            ranked = self._suggestions(db, query)
            message = (
                f"No standard matching '{query}' is present in the current corpus. "
                "This platform can only answer for documents that have been ingested - "
                "it will not guess what an unknown code means."
            )
            if ranked:
                message += " The closest matches by product description are shown below."
            return ConsumerStandardResponse(
                found=False,
                query=query,
                normalized_query=normalized,
                message=message,
                suggestions=ranked or self._suggestions(db, ""),
                disclaimer=DISCLAIMER,
            )

        scope_clauses: List[StandardClause] = (
            db.query(StandardClause)
            .filter(
                StandardClause.standard_id == standard.id,
                StandardClause.clause_type == "scope",
            )
            .order_by(StandardClause.clause_number)
            .limit(4)
            .all()
        )
        # A BIS Product Manual or QCO has no clause classified as "scope", so
        # without a fallback a consumer looking up a real IS number gets an
        # explanation with nothing under "where this came from". Cite the
        # document's opening clauses instead - real chunks of that document,
        # each carrying its own document_type so the UI can say what it is.
        if not scope_clauses:
            scope_clauses = (
                db.query(StandardClause)
                .filter(
                    StandardClause.standard_id == standard.id,
                    StandardClause.is_table.is_(False),
                )
                .order_by(StandardClause.id)
                .limit(3)
                .all()
            )
        scope_text = " ".join(c.text for c in scope_clauses) or standard.scope

        what_is_it, llm_used = self._explain(standard, scope_text)
        applies_to = self._applies_to(scope_clauses, standard)

        return ConsumerStandardResponse(
            found=True,
            query=query,
            normalized_query=normalized or standard.normalized_number,
            standard=standard_summary(db, standard),
            what_is_it=what_is_it,
            what_it_covers=list(standard.covered_areas or []),
            why_it_matters=self._why_it_matters(standard),
            applies_to=applies_to,
            regulatory=resolve_regulatory_status(db, standard.id),
            sources=[clause_ref(c, standard) for c in scope_clauses],
            llm_used=llm_used,
            disclaimer=DISCLAIMER,
        )

    # ------------------------------------------------------------------
    def _explain(self, standard: Standard, scope_text: str) -> tuple:
        baseline = standard.plain_summary or (
            f"{standard.is_number} is titled '{standard.title}'. "
            + truncate(scope_text, 320)
        )
        if not self.llm.available:
            return baseline, False

        prompt = (
            f"Standard number: {standard.is_number}\n"
            f"Title: {standard.title}\n"
            f"Areas covered: {', '.join(standard.covered_areas or []) or 'not listed'}\n"
            f"Scope text:\n{truncate(scope_text, 1400)}\n\n"
            "Explain this to a consumer."
        )
        text = self.llm.text(SYSTEM_PROMPT, prompt, max_tokens=280, temperature=0.3)
        if not text:
            return baseline, False
        return text.strip(), True

    @staticmethod
    def _applies_to(clauses: List[StandardClause], standard: Standard) -> str:
        for clause in clauses:
            if clause.clause_number.startswith("1.1"):
                return truncate(clause.text, 300)
        return truncate(standard.scope, 300)

    @staticmethod
    def _why_it_matters(standard: Standard) -> str:
        areas = [a.lower() for a in (standard.covered_areas or [])]
        if not areas:
            return (
                "A product built to this standard has been designed against a published "
                "set of requirements rather than to no specification at all."
            )
        readable = ", ".join(areas[:-1]) + (f" and {areas[-1]}" if len(areas) > 1 else areas[0])
        return (
            f"This standard sets out what the product must achieve for {readable}. "
            f"When a product is made and tested against it, those aspects have been "
            f"checked against a published benchmark instead of being left to the "
            f"manufacturer's discretion."
        )

    @staticmethod
    def _suggestions(db: Session, query: str, limit: int = 6) -> List[StandardSummary]:
        """Standards ranked against the query text, or the first N if it is empty.

        Ranking is plain token overlap against title, keywords, covered areas
        and product category - nothing generated, so a mismatch never looks
        like a recommendation the platform is vouching for.
        """
        rows = db.query(Standard).order_by(Standard.is_number).all()
        query_tokens = set(content_tokens(query))
        if not query_tokens:
            return [standard_summary(db, row) for row in rows[:limit]]

        scored = []
        for row in rows:
            haystack = " ".join(
                [
                    row.title,
                    row.product_category or "",
                    " ".join(row.keywords or []),
                    " ".join(row.covered_areas or []),
                ]
            )
            row_tokens = set(content_tokens(haystack))
            overlap = len(query_tokens & row_tokens)
            if overlap:
                scored.append((overlap, row))

        if not scored:
            return []
        scored.sort(key=lambda pair: (-pair[0], pair[1].is_number))
        return [standard_summary(db, row) for _, row in scored[:limit]]

    # ------------------------------------------------------------------
    def browse_categories(self, db: Session) -> List[Dict[str, object]]:
        """Product categories a consumer can browse, built only from standards
        actually present in the corpus - never from the full taxonomy list.
        """
        rows = (
            db.query(Standard.product_category, Standard.id)
            .filter(Standard.product_category != "")
            .all()
        )
        counts: Dict[str, int] = {}
        for category, _id in rows:
            counts[category] = counts.get(category, 0) + 1

        # A taxonomy key (e.g. "water-heater") maps onto one corpus category
        # (e.g. "electrical-appliance"); use it for a friendlier label when it
        # points at a category that actually has standards. A taxonomy key
        # that equals the corpus category itself (e.g. "electrical-appliance"
        # -> "electrical-appliance") is the general label for that whole
        # bucket and always wins over a narrower key that merely happens to
        # map into the same bucket (e.g. "water-heater") - otherwise a
        # category holding several kinds of standard would be mislabelled
        # after just one of them.
        label_by_corpus_category: Dict[str, str] = {}
        for key, corpus_category in CATEGORY_TO_CORPUS.items():
            spec = CATEGORY_BY_KEY.get(key)
            if not spec:
                continue
            exact_match = key == corpus_category
            if exact_match or corpus_category not in label_by_corpus_category:
                label_by_corpus_category[corpus_category] = spec.label

        def _humanise(raw: str) -> str:
            return label_by_corpus_category.get(raw) or raw.replace("-", " ").replace("_", " ").title()

        return [
            {"key": category, "label": _humanise(category), "standard_count": count}
            for category, count in sorted(counts.items(), key=lambda kv: kv[0])
        ]
