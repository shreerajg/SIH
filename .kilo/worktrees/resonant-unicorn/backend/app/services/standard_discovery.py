"""StandardDiscoveryService - product profile in, evidenced standard matches out.

The anti-hallucination contract of this module:

* Retrieval produces a CLOSED candidate list of standard IDs that exist in the
  corpus.
* Only that list is shown to the model, and the prompt says so explicitly.
* Every ID the model returns is validated against the candidate list. An ID
  that is not in the list is dropped and recorded in ``rejected_ids`` - it can
  never reach the API response.
* If the model is unavailable or its output is rejected, the deterministic
  explanation built from keyword and scope evidence is used instead.

Discovery also expands into referenced horizontal standards (general safety,
test methods, marking) using StandardRelationship edges, each of which cites
the clause that states the relationship.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.constants import Relevance
from app.core.text_utils import content_tokens
from app.llm.service import LLMService, get_llm
from app.models import (
    Product,
    ProductStandardMatch,
    Standard,
    StandardClause,
    StandardRelationship,
)
from app.schemas.models import MatchedAttribute, StandardMatch
from app.search.hybrid import StandardCandidate, get_retriever
from app.services.regulatory import resolve_regulatory_status
from app.services.serializers import clause_ref, standard_summary
from app.services.taxonomy import CATEGORY_TO_CORPUS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a BIS standards analyst. You are given a structured product profile "
    "and a CLOSED list of candidate standards retrieved from a verified corpus.\n"
    "RULES YOU MUST FOLLOW:\n"
    "1. You may select ONLY from the provided candidate standard_id values. "
    "Do not create, infer, recall or suggest any standard that is not in the list.\n"
    "2. Base every explanation on the candidate's own scope text that is shown to you.\n"
    "3. Do not state whether a standard is mandatory, voluntary or certified - "
    "regulatory status is resolved elsewhere from structured records.\n"
    "4. If a candidate does not genuinely fit the product, give it LOW relevance "
    "and say why, rather than inventing a justification."
)

HIGH_THRESHOLD = 0.50
MEDIUM_THRESHOLD = 0.22

#: Below this a match carries no usable signal and is dropped rather than
#: shown as a weak result the user has to evaluate.
MIN_INCLUSION_SCORE = 0.06


class _LLMRanking(BaseModel):
    standard_id: str
    relevance: str = Field(description="HIGH, MEDIUM or LOW")
    reason: str = Field(description="One or two sentences grounded in the scope text shown")


class _LLMDiscovery(BaseModel):
    rankings: List[_LLMRanking] = Field(default_factory=list)


class StandardDiscoveryService:
    def __init__(self, llm: Optional[LLMService] = None) -> None:
        self.llm = llm or get_llm()
        self.retriever = get_retriever()

    # ------------------------------------------------------------------
    def discover(self, db: Session, product: Product, limit: int = 6) -> Dict[str, Any]:
        attributes = dict(product.attributes_json or {})
        query_text = self._build_query(product, attributes)
        category_hint = CATEGORY_TO_CORPUS.get(product.category or "", "")

        candidates = self.retriever.discover_standards(
            db, query_text,
            profile_tokens=content_tokens(query_text),
            category_hint=category_hint,
        )
        notes: List[str] = []
        if not candidates:
            return {
                "matches": [],
                "candidates_considered": 0,
                "llm_used": False,
                "notes": [
                    "No standard in the current corpus matched this product description. "
                    "Add more product detail, or ingest the relevant standards documents."
                ],
            }

        candidate_ids = {c.standard.id for c in candidates}
        llm_rankings, rejected_ids, llm_used = self._llm_rank(product, attributes, candidates)
        if rejected_ids:
            notes.append(
                f"Evidence Shield: the model referenced {len(rejected_ids)} standard "
                f"identifier(s) that are not in the retrieved candidate list "
                f"({', '.join(sorted(rejected_ids))}). They were discarded."
            )
            logger.warning("Rejected out-of-corpus standard IDs: %s", rejected_ids)

        matches: List[Dict[str, Any]] = []
        for candidate in candidates:
            deterministic = self._explain(db, product, attributes, candidate)
            ranking = llm_rankings.get(candidate.standard.id)
            if ranking is not None:
                relevance = self._coerce_relevance(ranking.relevance, deterministic["relevance"])
                reason = ranking.reason.strip() or deterministic["reason"]
                source = "llm"
            else:
                relevance = deterministic["relevance"]
                reason = deterministic["reason"]
                source = "deterministic"
            matches.append(
                {
                    "standard": candidate.standard,
                    "relevance": relevance,
                    "reason": reason,
                    "matched_attributes": deterministic["matched_attributes"],
                    "scope_evidence": deterministic["scope_evidence"],
                    "evidence_clauses": deterministic["evidence_clauses"],
                    "score": candidate.score,
                    "explanation_source": source,
                    "signals": {
                        "semantic": candidate.semantic_score,
                        "bm25": candidate.bm25_score,
                        "metadata": candidate.metadata_score,
                        **candidate.signals,
                    },
                }
            )

        # A product-specific standard from another family that only scraped in
        # on generic words is noise, not a weak match - drop it entirely.
        matches = [
            m for m in matches
            if not (
                m["relevance"] == Relevance.LOW
                and (
                    m["signals"].get("cross_family_penalised")
                    or m["score"] < MIN_INCLUSION_SCORE
                )
            )
        ]
        matches.sort(key=lambda m: (_relevance_rank(m["relevance"]), -m["score"]))
        matches = matches[:limit]

        self._apply_relationships(db, matches, limit)

        self._persist(db, product, matches)
        return {
            "matches": matches,
            "candidates_considered": len(candidates),
            "llm_used": llm_used,
            "notes": notes,
            "rejected_ids": sorted(rejected_ids),
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _build_query(product: Product, attributes: Dict[str, Any]) -> str:
        bits = [product.name or "", product.description or "", product.category or ""]
        for key, value in attributes.items():
            if value in (None, "", []):
                continue
            readable = key.replace("_", " ")
            bits.append(f"{readable} {value}")
        return " ".join(b for b in bits if b).strip()

    # ------------------------------------------------------------------
    def _explain(
        self, db: Session, product: Product, attributes: Dict[str, Any],
        candidate: StandardCandidate,
    ) -> Dict[str, Any]:
        standard = candidate.standard
        matched: List[MatchedAttribute] = []
        keywords = [k.lower() for k in (standard.keywords or [])]
        blob = f"{product.name} {product.description}".lower()

        for keyword in candidate.matched_keywords[:8]:
            matched.append(
                MatchedAttribute(
                    attribute=keyword,
                    product_value="present in product description",
                    matched_on="standard keyword",
                    note=f"'{keyword}' appears in both the product description and the scope keywords of {standard.is_number}.",
                )
            )

        for key, value in attributes.items():
            if value in (None, "", []) or len(matched) >= 10:
                continue
            readable = str(value).lower()
            if readable and any(readable in kw or kw in readable for kw in keywords):
                matched.append(
                    MatchedAttribute(
                        attribute=key.replace("_", " "),
                        product_value=str(value),
                        matched_on="standard keyword",
                        note=f"Declared {key.replace('_', ' ')} matches the scope vocabulary of {standard.is_number}.",
                    )
                )

        corpus_category = CATEGORY_TO_CORPUS.get(product.category or "", "")
        if corpus_category and corpus_category == (standard.product_category or ""):
            matched.append(
                MatchedAttribute(
                    attribute="product category",
                    product_value=product.category or "",
                    matched_on="standard product_category",
                    note=f"The product family maps to the '{standard.product_category}' family this standard covers.",
                )
            )

        scope_clauses = (
            db.query(StandardClause)
            .filter(
                StandardClause.standard_id == standard.id,
                StandardClause.clause_type == "scope",
            )
            .order_by(StandardClause.clause_number)
            .limit(3)
            .all()
        )
        # A BIS Product Manual or a Quality Control Order has no clause the
        # parser classifies as "scope" - that is a feature of full standards.
        # Without a fallback those documents are matched with no citation at
        # all, so "Why this standard?" would show a verified official document
        # backed by nothing. Cite its opening clauses instead: real retrievable
        # chunks of that document, each carrying its own document_type so they
        # are never presented as standard scope text.
        supporting_clauses = scope_clauses
        if not supporting_clauses:
            supporting_clauses = (
                db.query(StandardClause)
                .filter(
                    StandardClause.standard_id == standard.id,
                    StandardClause.is_table.is_(False),
                )
                .order_by(StandardClause.id)
                .limit(3)
                .all()
            )
        scope_evidence = (
            scope_clauses[0].text
            if scope_clauses
            else (standard.scope or (supporting_clauses[0].text if supporting_clauses else ""))
        )
        evidence_clauses = [clause_ref(c, standard) for c in supporting_clauses]

        if candidate.score >= HIGH_THRESHOLD or (
            len(candidate.matched_keywords) >= 3 and candidate.signals.get("category_match")
        ):
            relevance = Relevance.HIGH
        elif candidate.score >= MEDIUM_THRESHOLD:
            relevance = Relevance.MEDIUM
        else:
            relevance = Relevance.LOW
        if not scope_clauses and relevance == Relevance.HIGH:
            relevance = Relevance.NEEDS_VERIFICATION

        reason = self._deterministic_reason(standard, candidate, matched, blob)
        return {
            "relevance": relevance,
            "reason": reason,
            "matched_attributes": matched,
            "scope_evidence": scope_evidence,
            "evidence_clauses": evidence_clauses,
        }

    @staticmethod
    def _deterministic_reason(
        standard: Standard, candidate: StandardCandidate,
        matched: Sequence[MatchedAttribute], blob: str,
    ) -> str:
        del blob
        if matched:
            factors = ", ".join(m.attribute for m in matched[:4])
            return (
                f"{standard.is_number} covers {standard.title.lower()}. The product matched "
                f"on {factors}. Retrieval combined keyword and semantic similarity against "
                f"the scope text of this standard."
            )
        return (
            f"{standard.is_number} was retrieved by semantic similarity to the product "
            f"description. No explicit keyword overlap was found, so this match needs "
            f"review against the scope text shown."
        )

    # ------------------------------------------------------------------
    def _llm_rank(
        self, product: Product, attributes: Dict[str, Any],
        candidates: Sequence[StandardCandidate],
    ) -> Tuple[Dict[str, _LLMRanking], set, bool]:
        if not self.llm.available:
            return {}, set(), False

        candidate_ids = {c.standard.id for c in candidates}
        lines = []
        for c in candidates:
            lines.append(
                f"- standard_id: {c.standard.id}\n"
                f"  number: {c.standard.is_number}\n"
                f"  title: {c.standard.title}\n"
                f"  category: {c.standard.product_category}\n"
                f"  scope: {(c.standard.scope or '')[:700]}"
            )
        prompt = (
            "PRODUCT PROFILE\n"
            f"name: {product.name}\n"
            f"category: {product.category}\n"
            f"description: {product.description[:1200]}\n"
            f"attributes: {attributes}\n\n"
            "CANDIDATE STANDARDS (the ONLY ids you may use)\n"
            + "\n".join(lines)
            + "\n\nRank the candidates for this product. Use only the standard_id values above."
        )
        result = self.llm.structured(SYSTEM_PROMPT, prompt, _LLMDiscovery)
        if result is None:
            return {}, set(), False

        accepted: Dict[str, _LLMRanking] = {}
        rejected = set()
        for ranking in result.rankings:
            sid = (ranking.standard_id or "").strip()
            if sid in candidate_ids:
                accepted[sid] = ranking
            else:
                rejected.add(sid or "<empty>")
        return accepted, rejected, True

    @staticmethod
    def _coerce_relevance(value: str, fallback: Relevance) -> Relevance:
        try:
            return Relevance((value or "").strip().upper())
        except ValueError:
            return fallback

    # ------------------------------------------------------------------
    def _apply_relationships(
        self, db: Session, matches: List[Dict[str, Any]], limit: int
    ) -> None:
        """Bring in - or promote - standards the matched standards reference.

        A horizontal standard such as the marking standard often scores low on
        its own, because a product description does not talk like a marking
        clause. It becomes relevant because a matched product standard cites it
        as a normative reference, and that citation is real evidence, so the
        match is promoted and the citing clause is given as the reason.
        """
        by_id = {m["standard"].id: m for m in matches}
        primary_ids = [
            m["standard"].id for m in matches
            if m["relevance"] in (Relevance.HIGH, Relevance.MEDIUM)
        ]
        if not primary_ids:
            return

        edges = (
            db.query(StandardRelationship)
            .filter(StandardRelationship.source_standard_id.in_(primary_ids))
            .all()
        )
        added = 0
        for edge in edges:
            target = db.get(Standard, edge.target_standard_id)
            if target is None:
                continue
            source = db.get(Standard, edge.source_standard_id)
            source_number = source.is_number if source else "a matched standard"
            reason = (
                f"{target.is_number} is brought into scope by {source_number}: {edge.evidence}"
            )
            attribute = MatchedAttribute(
                attribute="normative reference",
                product_value=source_number,
                matched_on=edge.relationship_type.replace("_", " "),
                note=edge.evidence,
            )

            existing = by_id.get(target.id)
            if existing is not None:
                if existing["relevance"] == Relevance.LOW:
                    existing["relevance"] = Relevance.MEDIUM
                    existing["reason"] = reason
                    existing["explanation_source"] = "relationship_graph"
                if not any(
                    a.attribute == "normative reference" for a in existing["matched_attributes"]
                ):
                    existing["matched_attributes"].insert(0, attribute)
                existing["signals"]["via_relationship"] = edge.relationship_type
                continue

            if added >= limit:
                continue
            scope_clauses = (
                db.query(StandardClause)
                .filter(
                    StandardClause.standard_id == target.id,
                    StandardClause.clause_type == "scope",
                )
                .order_by(StandardClause.clause_number)
                .limit(2)
                .all()
            )
            entry = {
                "standard": target,
                "relevance": Relevance.MEDIUM,
                "reason": reason,
                "matched_attributes": [attribute],
                "scope_evidence": scope_clauses[0].text if scope_clauses else (target.scope or ""),
                "evidence_clauses": [clause_ref(c, target) for c in scope_clauses],
                "score": 0.0,
                "explanation_source": "relationship_graph",
                "signals": {"via_relationship": edge.relationship_type},
            }
            matches.append(entry)
            by_id[target.id] = entry
            added += 1

        matches.sort(key=lambda m: (_relevance_rank(m["relevance"]), -m["score"]))

    # ------------------------------------------------------------------
    def _persist(self, db: Session, product: Product, matches: List[Dict[str, Any]]) -> None:
        db.query(ProductStandardMatch).filter(
            ProductStandardMatch.product_id == product.id
        ).delete(synchronize_session=False)
        for match in matches:
            db.add(
                ProductStandardMatch(
                    id=f"psm-{uuid.uuid4().hex[:12]}",
                    product_id=product.id,
                    standard_id=match["standard"].id,
                    relevance=match["relevance"].value,
                    score=float(match["score"]),
                    reason=match["reason"],
                    matched_attributes_json=[m.model_dump() for m in match["matched_attributes"]],
                    scope_evidence=match["scope_evidence"],
                    evidence_chunk_ids=[c.chunk_id for c in match["evidence_clauses"]],
                    explanation_source=match["explanation_source"],
                    signals_json=match["signals"],
                )
            )
        db.commit()

    # ------------------------------------------------------------------
    def to_schema(self, db: Session, matches: List[Dict[str, Any]]) -> List[StandardMatch]:
        out: List[StandardMatch] = []
        for match in matches:
            standard = match["standard"]
            out.append(
                StandardMatch(
                    standard=standard_summary(db, standard),
                    relevance=match["relevance"],
                    reason=match["reason"],
                    matched_attributes=match["matched_attributes"],
                    scope_evidence=match["scope_evidence"],
                    evidence_clauses=match["evidence_clauses"],
                    regulatory=resolve_regulatory_status(db, standard.id),
                    explanation_source=match["explanation_source"],
                    score=float(match["score"]),
                    signals=match["signals"],
                )
            )
        return out

    def load_saved(self, db: Session, product: Product) -> List[StandardMatch]:
        rows = (
            db.query(ProductStandardMatch)
            .filter(ProductStandardMatch.product_id == product.id)
            .all()
        )
        out: List[StandardMatch] = []
        for row in rows:
            standard = db.get(Standard, row.standard_id)
            if standard is None:
                continue
            clauses = (
                db.query(StandardClause)
                .filter(StandardClause.chunk_id.in_(row.evidence_chunk_ids or []))
                .all()
            )
            out.append(
                StandardMatch(
                    standard=standard_summary(db, standard),
                    relevance=Relevance(row.relevance),
                    reason=row.reason,
                    matched_attributes=[
                        MatchedAttribute(**m) for m in (row.matched_attributes_json or [])
                    ],
                    scope_evidence=row.scope_evidence or "",
                    evidence_clauses=[clause_ref(c, standard) for c in clauses],
                    regulatory=resolve_regulatory_status(db, standard.id),
                    explanation_source=row.explanation_source or "deterministic",
                    score=row.score,
                    # Rows saved before signals_json existed have no breakdown on
                    # file; the frontend degrades to an explanatory note rather
                    # than fabricating bars for them.
                    signals=row.signals_json or {},
                )
            )
        out.sort(key=lambda m: _relevance_rank(m.relevance))
        return out


def _relevance_rank(relevance: Relevance) -> int:
    """Ordering for the match list.

    NEEDS_VERIFICATION sits directly below HIGH rather than below MEDIUM,
    because of what it actually means: the document scored highly but has no
    scope clause to *prove* it applies. That is a strong-but-unproven match,
    not a weak one, and it stays labelled as needing verification either way.

    Ordering it below MEDIUM had a concrete cost: an official BIS Product
    Manual has no "Scope" clause in the sense a standard does, so the single
    most relevant verified document for a product was pushed beneath weaker
    synthetic matches.
    """
    return {
        Relevance.HIGH: 0,
        Relevance.NEEDS_VERIFICATION: 1,
        Relevance.MEDIUM: 2,
        Relevance.LOW: 3,
    }.get(relevance, 4)
