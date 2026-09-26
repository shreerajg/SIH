"""RAGService - grounded question answering over the standards corpus.

Pipeline:

    question
      -> query classification (deterministic rules, LLM only as a tie-break)
      -> standard scoping (explicit ids / IS numbers in the question /
         the product's matched standards / corpus-wide discovery)
      -> stage-2 clause retrieval restricted to those standards
      -> context construction with explicit chunk ids
      -> structured generation (claims + citations)  [or extractive fallback]
      -> Evidence Shield validation
      -> answer + citations

Regulatory questions are short-circuited to the structured QCO table: the model
is never the source of a mandatory/voluntary answer.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import DISCLAIMER, QueryType, RegulatoryStatus
from app.core.text_utils import content_tokens, extract_is_numbers
from app.llm.service import LLMService, get_llm
from app.models import Product, ProductStandardMatch, Standard, StandardClause
from app.rag.conversation import (
    ConversationState,
    Turn,
    get_conversation_store,
    is_follow_up,
)
from app.rag.evidence_shield import (
    EvidenceShield,
    build_abstention,
    extractive_claims,
)
from app.schemas.models import ClauseRef, RAGResponse
from app.search.hybrid import ClauseHit, get_retriever
from app.search.reranker import RerankItem, backend_name as reranker_backend, rerank
from app.services import corpus
from app.services.regulatory import resolve_regulatory_status
from app.services.serializers import clause_ref
from app.services.taxonomy import CATEGORY_TO_CORPUS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a BIS standards analyst answering from retrieved clause text only.\n"
    "HARD RULES:\n"
    "1. Use ONLY the numbered EVIDENCE blocks provided. Do not use prior knowledge "
    "about any standard, and do not mention a standard that is not in the evidence.\n"
    "2. Decompose your answer into claims. Every claim MUST cite the chunk_id of "
    "the evidence block that supports it, copied exactly.\n"
    "3. Never invent a chunk_id. If the evidence does not answer the question, "
    "return an empty claims list.\n"
    "4. Do not state whether anything is mandatory, voluntary or certified.\n"
    "5. Do not tell a manufacturer their product is compliant."
)


class _LLMClaim(BaseModel):
    text: str = Field(description="One self-contained factual sentence")
    source_chunk_ids: List[str] = Field(
        default_factory=list,
        description="chunk_id values, copied exactly from the evidence blocks",
    )


class _LLMAnswer(BaseModel):
    answer: str = Field(default="", description="The full answer in plain language")
    claims: List[_LLMClaim] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Query classification
# ---------------------------------------------------------------------------

#: Ordered most-specific first. Patterns are prefix friendly (\w* rather than a
#: trailing \b) so "mandatory" is caught by the stem "mandator".
CLASSIFIER_RULES: List[Tuple[QueryType, re.Pattern]] = [
    (QueryType.MANDATORY_STATUS, re.compile(
        r"\b(mandator\w*|compulsor\w*|voluntar\w*|qco|quality control order|"
        r"legally required|required by law|is it required)", re.I)),
    (QueryType.CERTIFICATION_QUERY, re.compile(
        r"\b(certif\w*|licen[cs]\w*|isi mark|conformity mark|registration|bis mark)", re.I)),
    (QueryType.AMENDMENT_QUERY, re.compile(
        r"\b(amend\w*|revision|revised|changed|latest version|superseded|updated)", re.I)),
    (QueryType.PRODUCT_GAP_ANALYSIS, re.compile(
        r"\b(gap|gaps|missing|what do i need|am i ready|shortfall|non[- ]conform\w*)", re.I)),
    (QueryType.RELATED_STANDARD, re.compile(
        r"\b(related standard\w*|referenced standard\w*|normative reference\w*|"
        r"other standards|which other)", re.I)),
    (QueryType.MARKING_REQUIREMENT, re.compile(
        r"\b(marking\w*|label\w*|rating plate|nameplate|warning\w*|printed on|"
        r"engrav\w*|packaging)", re.I)),
    (QueryType.TEST_REQUIREMENT, re.compile(
        r"\b(test\w*|type test|laborator\w*|measurement method)", re.I)),
    (QueryType.CLAUSE_LOOKUP, re.compile(
        r"\b(clause|section|para(graph)?)\s*\d|\bclause\b", re.I)),
    (QueryType.STANDARD_DISCOVERY, re.compile(
        r"\b(which standard|what standard|applicable standard|standards apply|"
        r"which is code)", re.I)),
    (QueryType.STANDARD_EXPLANATION, re.compile(
        r"\b(what is|explain|meaning of|covers what|scope of)", re.I)),
]


def classify_query(question: str) -> QueryType:
    for query_type, pattern in CLASSIFIER_RULES:
        if pattern.search(question or ""):
            return query_type
    return QueryType.GENERAL_STANDARD_QA


class RAGService:
    def __init__(self, llm: Optional[LLMService] = None) -> None:
        self.llm = llm or get_llm()
        self.retriever = get_retriever()

    # ------------------------------------------------------------------
    def answer(
        self,
        db: Session,
        question: str,
        *,
        standard_ids: Optional[Sequence[str]] = None,
        product_id: Optional[str] = None,
        query_type: Optional[QueryType] = None,
        conversation_id: Optional[str] = None,
    ) -> RAGResponse:
        state = get_conversation_store().get_or_create(conversation_id, product_id=product_id)
        follow_up = is_follow_up(question) and bool(state.turns)

        query_type = query_type or classify_query(question)
        if follow_up and state.last_turn and query_type is QueryType.GENERAL_STANDARD_QA:
            # "Why is that needed?" inherits the intent of what it refers back to.
            try:
                query_type = QueryType(state.last_turn.query_type)
            except ValueError:
                pass

        # The corpus mode can leave nothing to answer from at all.
        starvation = corpus.starvation_note(db)
        if starvation:
            return self._abstain(
                question, query_type, starvation,
                "The active corpus mode has no usable documents.", conversation_id=state.id,
            )

        scoped_ids, scope_note = self._scope_standards(
            db, question, standard_ids, product_id, state=state, follow_up=follow_up
        )

        if not scoped_ids:
            unknown_ids = scope_note == "unknown_standard_ids"
            return self._abstain(
                question,
                query_type,
                (
                    "None of the standards requested are present in this corpus, so there is "
                    "nothing to answer from."
                    if unknown_ids
                    else "I could not identify a standard in the current corpus that this "
                         "question relates to. Try naming a standard, or run product analysis "
                         "first."
                ),
                (
                    "The requested standards are not in the corpus."
                    if unknown_ids
                    else "No standard in the corpus could be scoped to this question."
                ),
                conversation_id=state.id,
            )

        # Retrieve wide for recall, then rerank for precision.
        retrieval_k = max(settings.clause_top_k * 2, 12)
        hits = self.retriever.retrieve_clauses(db, question, scoped_ids, k=retrieval_k)
        hits = self._rerank(question, hits, query_type)
        citations = self._citations(db, hits)
        retrieved_ids = [h.chunk_id for h in hits]

        regulatory = None
        if query_type in (QueryType.MANDATORY_STATUS, QueryType.CERTIFICATION_QUERY):
            regulatory = resolve_regulatory_status(db, scoped_ids[0])

        # A retrieval where nothing scored is the "no lexical or semantic signal"
        # fallback path. Quoting arbitrary clauses at that point would look like
        # an answer without being one, so the platform abstains instead.
        if not hits or all(hit.score <= 0 for hit in hits):
            shield = build_abstention(
                [h.chunk_id for h in hits],
                "No clause in the scoped standards matched this question.",
            )
            response = RAGResponse(
                question=question,
                query_type=query_type,
                answer=(
                    "No clause in the standards searched is relevant to that question. "
                    "Try rephrasing it, or name the standard you mean."
                ),
                answerable=False,
                claims=[],
                citations=citations if regulatory is not None else [],
                evidence_shield=shield.report,
                regulatory=regulatory,
                standards_searched=list(scoped_ids),
                llm_used=False,
                conversation_id=state.id,
                disclaimer=DISCLAIMER,
            )
            self._record(state, response)
            return response

        shield = EvidenceShield(retrieved_ids)
        llm_used = False

        if self.llm.available:
            generated = self._generate(
                question, hits, query_type,
                history=state.summary if follow_up else "",
            )
            if generated is not None:
                llm_used = True
                result = shield.validate(
                    generated.answer,
                    [c.model_dump() for c in generated.claims],
                )
            else:
                result = shield.validate(
                    "", extractive_claims([(h.chunk_id, h.clause.text) for h in hits])
                )
        else:
            result = shield.validate(
                "", extractive_claims([(h.chunk_id, h.clause.text) for h in hits])
            )

        answer = result.answer
        if not llm_used and result.answerable:
            answer = (
                "Retrieved directly from the standards corpus (no language model is "
                "configured, so the clause text is quoted rather than paraphrased):\n\n"
                + answer
            )

        if regulatory is not None:
            answer = self._prepend_regulatory(answer, regulatory)

        cited = set(shield.cited_chunk_ids(result.claims))
        ordered_citations = [c for c in citations if c.chunk_id in cited] + [
            c for c in citations if c.chunk_id not in cited
        ]

        response = RAGResponse(
            question=question,
            query_type=query_type,
            answer=answer,
            answerable=result.answerable,
            claims=result.claims,
            citations=ordered_citations,
            evidence_shield=result.report,
            regulatory=regulatory,
            standards_searched=list(scoped_ids),
            llm_used=llm_used,
            conversation_id=state.id,
            follow_up=follow_up,
            scope_note=scope_note,
            reranker=reranker_backend(),
            disclaimer=DISCLAIMER,
        )
        self._record(state, response)
        return response

    # ------------------------------------------------------------------
    def _abstain(
        self, question: str, query_type: QueryType, answer: str, reason: str,
        *, conversation_id: Optional[str] = None,
    ) -> RAGResponse:
        shield = build_abstention([], reason)
        return RAGResponse(
            question=question,
            query_type=query_type,
            answer=answer,
            answerable=False,
            claims=[],
            citations=[],
            evidence_shield=shield.report,
            standards_searched=[],
            llm_used=False,
            conversation_id=conversation_id,
            disclaimer=DISCLAIMER,
        )

    @staticmethod
    def _record(state: ConversationState, response: RAGResponse) -> None:
        state.record(
            Turn(
                question=response.question,
                answer=response.answer,
                query_type=response.query_type.value,
                standard_ids=list(response.standards_searched),
                chunk_ids=[c.chunk_id for c in response.citations],
                answerable=response.answerable,
            )
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _rerank(
        question: str, hits: List[ClauseHit], query_type: QueryType
    ) -> List[ClauseHit]:
        """Reorder for precision, then cut to the context budget."""
        if not hits:
            return hits
        items = [
            RerankItem(
                id=hit.chunk_id,
                text=f"{hit.clause.heading}. {hit.clause.text}",
                retrieval_score=hit.score,
                clause_type=hit.clause.clause_type,
            )
            for hit in hits
        ]
        ranked = rerank(question, items, query_type=query_type, top_k=settings.clause_top_k)
        by_id = {hit.chunk_id: hit for hit in hits}
        out: List[ClauseHit] = []
        for result in ranked:
            hit = by_id.get(result.id)
            if hit is None:
                continue
            hit.score = result.score
            out.append(hit)
        return out

    # ------------------------------------------------------------------
    def _scope_standards(
        self, db: Session, question: str,
        standard_ids: Optional[Sequence[str]], product_id: Optional[str],
        *, state: Optional[ConversationState] = None, follow_up: bool = False,
    ) -> Tuple[List[str], str]:
        if standard_ids:
            valid = corpus.filter_ids(
                db,
                [
                    s.id
                    for s in db.query(Standard).filter(Standard.id.in_(list(standard_ids))).all()
                ],
            )
            if valid:
                return valid, "Scoped to the standards selected by the user."
            # The caller asked for specific standards and none of them exist
            # (or the corpus mode excludes them). Silently widening the search
            # to the whole corpus would answer a different question.
            return [], "unknown_standard_ids"

        mentioned = extract_is_numbers(question)
        if mentioned:
            rows = (
                db.query(Standard).filter(Standard.normalized_number.in_(mentioned)).all()
            )
            valid = corpus.filter_ids(db, [r.id for r in rows])
            if valid:
                return valid, "Scoped to the standard(s) named in the question."

        # A follow-up stays inside the scope the user is already working in,
        # rather than being re-matched against the whole corpus.
        if follow_up and state is not None and state.selected_standard_ids:
            carried = corpus.filter_ids(db, state.selected_standard_ids)
            if carried:
                return carried, "Follow-up: kept the scope of the previous question."

        if not product_id and state is not None and state.selected_product_id:
            product_id = state.selected_product_id

        if product_id:
            rows = (
                db.query(ProductStandardMatch)
                .filter(ProductStandardMatch.product_id == product_id)
                .all()
            )
            valid = corpus.filter_ids(db, [r.standard_id for r in rows])
            if valid:
                return valid, "Scoped to the product's matched standards."

        # Corpus-wide: run stage 1 on the question itself.
        product = db.get(Product, product_id) if product_id else None
        category_hint = CATEGORY_TO_CORPUS.get((product.category if product else "") or "", "")
        candidates = self.retriever.discover_standards(
            db, question, profile_tokens=content_tokens(question),
            category_hint=category_hint, limit=3,
        )
        if candidates:
            return (
                [c.standard.id for c in candidates],
                "No standard was named, so the question was matched against the whole corpus.",
            )
        return [], ""

    # ------------------------------------------------------------------
    @staticmethod
    def _boost_by_type(hits: List[ClauseHit], query_type: QueryType) -> List[ClauseHit]:
        """Nudge clause types that answer this kind of question to the top."""
        preferred = {
            QueryType.TEST_REQUIREMENT: {"test", "table"},
            QueryType.MARKING_REQUIREMENT: {"marking", "documentation"},
            QueryType.CLAUSE_LOOKUP: {"requirement", "test", "marking"},
            QueryType.STANDARD_EXPLANATION: {"scope", "definition"},
            QueryType.CONSUMER_LOOKUP: {"scope"},
            QueryType.RELATED_STANDARD: {"reference"},
        }.get(query_type)
        if not preferred:
            return hits
        return sorted(
            hits, key=lambda h: (0 if h.clause.clause_type in preferred else 1, -h.score)
        )

    @staticmethod
    def _citations(db: Session, hits: Sequence[ClauseHit]) -> List[ClauseRef]:
        standards: Dict[str, Standard] = {}
        out: List[ClauseRef] = []
        for hit in hits:
            standard = standards.get(hit.clause.standard_id)
            if standard is None:
                standard = db.get(Standard, hit.clause.standard_id)
                standards[hit.clause.standard_id] = standard
            if standard is None:
                continue
            out.append(clause_ref(hit.clause, standard, score=hit.score))
        return out

    # ------------------------------------------------------------------
    def _generate(
        self, question: str, hits: Sequence[ClauseHit], query_type: QueryType,
        *, history: str = "",
    ) -> Optional[_LLMAnswer]:
        blocks = []
        for hit in hits:
            clause = hit.clause
            blocks.append(
                f"[chunk_id: {clause.chunk_id}]\n"
                f"standard: {clause.standard_id}\n"
                f"clause: {clause.clause_number}  ({clause.heading})\n"
                f"text: {clause.text}"
            )
        prompt = (
            f"QUESTION ({query_type.value}):\n{question}\n\n"
            "EVIDENCE (the only material you may use):\n\n"
            + "\n\n".join(blocks)
            + "\n\nAnswer the question. Every claim must cite one or more chunk_id values "
              "copied exactly from above. If the evidence does not answer the question, "
              "return an empty claims list."
        )
        return self.llm.structured(SYSTEM_PROMPT, prompt, _LLMAnswer, max_tokens=1800)

    # ------------------------------------------------------------------
    @staticmethod
    def _prepend_regulatory(answer: str, regulatory) -> str:
        if regulatory.status == RegulatoryStatus.UNABLE_TO_VERIFY:
            header = (
                "Regulatory status: UNABLE TO VERIFY. " + regulatory.message
            )
        else:
            header = (
                f"Regulatory status: {regulatory.status.value}. "
                f"Source: {regulatory.source}"
                + (f" ({regulatory.notification_number})" if regulatory.notification_number else "")
                + ". "
                + regulatory.message
            )
        return f"{header}\n\n{answer}".strip()


_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    global _service
    if _service is None:
        _service = RAGService()
    return _service


def reset_rag_service(service: Optional[RAGService] = None) -> None:
    global _service
    _service = service
    get_conversation_store().reset()
