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
from pymongo.database import Database

from app.core.config import settings
from app.core.constants import DISCLAIMER, QueryType, RegulatoryStatus
from app.core.text_utils import content_tokens, extract_is_numbers
from app.db.repositories import products as products_repo
from app.db.repositories import standards as standards_repo
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
#: A certification question asking *how*, rather than *which scheme*.
_PROCESS_RE = re.compile(
    r"\b(process|procedure|steps?|how do i|how to|how can i|what do i (?:need to )?do|"
    r"journey|get certified|obtain (?:a )?licen[cs]e|apply for)\b",
    re.I,
)

CLASSIFIER_RULES: List[Tuple[QueryType, re.Pattern]] = [
    (QueryType.MANDATORY_STATUS, re.compile(
        r"\b(mandator\w*|compulsor\w*|voluntar\w*|qco|quality control order|"
        r"legally required|required by law|is it required)", re.I)),
    # Jewellery hallmarking. Placed before CERTIFICATION_QUERY because
    # "hallmarking scheme" and "jeweller registration" would otherwise be
    # swallowed by the certification pattern.
    #
    # Deliberately NOT matched: a bare "marking", "standard mark" or "marking
    # requirements under IS 2082". Those are product marking-clause questions,
    # a completely different subject, and routing them here would answer a
    # water-heater question with gold-purity guidance.
    (QueryType.HALLMARKING_QUERY, re.compile(
        r"\b(hallmark\w*|huid|assay\w*|jewell\w*|"
        r"(?:gold|silver)\s+(?:purity|fineness|jewel\w*|ornament\w*|article\w*|ring|chain|"
        r"bangle|necklace|coin)|"
        r"\d{2}\s*k\s*\d{3}|"                     # 22K916, 18K750
        r"(?:22|18|14|20|23|24)\s*(?:k|carat|karat)\b|"
        # A bare documented fineness (916, 750, 585 gold; 990..800 silver),
        # but NOT when it follows "IS" - IS 916 in this corpus is "Square Tins
        # for Solid Products", a genuine number clash with 22-carat gold.
        r"(?<!is )(?<!is-)\b(?:916|750|585|990|970|925|900|835|800)\b|"
        r"carat\w*|karat\w*|fineness)\b", re.I)),
    (QueryType.CERTIFICATION_QUERY, re.compile(
        r"\b(certif\w*|licen[cs]\w*|isi mark|conformity mark|registration|bis mark|"
        # A named scheme: "Scheme I", "Scheme-II", "Scheme X", "Scheme 1".
        # Deliberately not \bscheme\b, which would swallow "scheme of
        # inspection and testing" - a clause-retrieval question, not this one.
        r"scheme[\s-]?(?:i{1,3}|x|\d+)\b|"
        r"(?:which|what|applicable|recommended|right)\s+(?:bis\s+)?(?:certification\s+)?scheme\b|"
        r"certification scheme|bis scheme|hallmark\w*|\bcrs\b|\bfmcs\b)", re.I)),
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
        db: Database,
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

        # Hallmarking is answered from the ingested BIS hallmarking documents
        # and the structured records built from them, not from clause retrieval
        # over the product corpus - "What is HUID?" names no standard at all.
        if query_type is QueryType.HALLMARKING_QUERY:
            hallmark_answer = self._answer_hallmarking(db, question)
            if hallmark_answer is not None:
                state.record(
                    Turn(
                        question=question,
                        answer=hallmark_answer.answer,
                        query_type=query_type.value,
                        answerable=hallmark_answer.answerable,
                    )
                )
                return hallmark_answer

        # Certification-scheme questions are answered from stored scheme and QCO
        # records, not from clause retrieval, so they are handled before the
        # corpus is scoped - "What is Scheme I?" names no standard at all and
        # would otherwise abstain for lack of one.
        if query_type is QueryType.CERTIFICATION_QUERY:
            scheme_answer = self._answer_certification(
                db, question, product_id=product_id, standard_ids=standard_ids, state=state
            )
            if scheme_answer is not None:
                state.record(
                    Turn(
                        question=question,
                        answer=scheme_answer.answer,
                        query_type=query_type.value,
                        standard_ids=list(scheme_answer.standards_searched),
                        answerable=scheme_answer.answerable,
                    )
                )
                return scheme_answer

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
    # ------------------------------------------------------------------
    def _answer_hallmarking(self, db: Database, question: str) -> Optional[RAGResponse]:
        """Answer a hallmarking question from the BIS hallmarking corpus.

        Four shapes, in order of specificity: HUID, purity/marking, the
        jeweller journey, and the general consumer explanation. Every answer
        carries the clauses its facts were resolved to, so the citations the UI
        shows are the same clauses the guide used.

        Returns None only when the hallmarking corpus is not loaded, so the
        caller falls back to ordinary retrieval rather than this path asserting
        something it has no source for.
        """
        from app.services import hallmarking as hm

        if not hm.corpus_available(db):
            return None

        lowered = (question or "").lower()
        citations: List[ClauseRef] = []
        lines: List[str] = []

        asks_huid = "huid" in lowered or "six digit" in lowered or "six-digit" in lowered
        # The trailing \b on jewell?er is load-bearing: without it "my gold
        # jewellery" matches on the "jeweller" prefix, and a consumer asking
        # what to check before buying is handed the trade journey instead.
        asks_jeweller = bool(
            re.search(r"\b(jewell?ers?\b|register|registration|get .* hallmarked|"
                      r"assay\w* centre|a\s*&\s*h|manufactur)", lowered)
        )
        asks_purity = bool(
            re.search(r"\b(\d{2}\s*k\s*\d{3}|purity|fineness|carat|karat|916|750|585|925)\b", lowered)
        )

        if asks_huid:
            guidance = hm.huid_guidance(db)
            lines.append("HUID (Hallmark Unique Identification)")
            if guidance.description:
                lines.append(guidance.description)
            if guidance.in_force_from:
                lines.append(f"In force from: {guidance.in_force_from}.")
            lines.append("")
            lines.append(guidance.verification_note)
            if guidance.official_verification_url:
                lines.append(f"Official BIS hallmarking pages: {guidance.official_verification_url}")
            if guidance.evidence:
                citations.append(guidance.evidence)

        elif asks_jeweller:
            guide = hm.jeweller_guide(db)
            lines.append(guide.title)
            lines.append(guide.summary)
            lines.append("")
            for stage in guide.stages:
                marker = ""
                if stage.evidence is not None:
                    marker = f" [{stage.evidence.standard_id} clause {stage.evidence.clause_number}]"
                    citations.append(stage.evidence)
                elif stage.state.value == "UNABLE_TO_VERIFY":
                    marker = " [unable to verify from available BIS data]"
                lines.append(f"{stage.order}. {stage.title}{marker}")
                lines.append(f"   {stage.summary}")
            summary = guide.centre_summary
            lines.append("")
            if summary.available:
                lines.append(
                    f"Assaying & Hallmarking Centres: {summary.total} listed in a snapshot taken "
                    f"on {summary.retrieved_at}, of which {summary.operative} are operative."
                )
            else:
                lines.append(summary.note)
            lines.append(guide.message)

        else:
            guide = hm.consumer_guide(db, "gold")
            if guide.overview is not None and guide.overview.summary:
                lines.append(guide.overview.summary)
                if guide.overview.evidence:
                    citations.append(guide.overview.evidence)
            if guide.components:
                lines.append("")
                lines.append("A hallmarked gold article carries:")
                for component in guide.components:
                    lines.append(f"  - {component.name}: {component.description}")
                    if component.evidence:
                        citations.append(component.evidence)
            if asks_purity and guide.purity_grades:
                lines.append("")
                lines.append("Permitted gold purity grades:")
                for grade in guide.purity_grades:
                    if grade.permitted_marking:
                        covered = "covered by the mandatory order" if grade.mandatory_order_covered else "permitted grade"
                        lines.append(f"  - {grade.carat} / {grade.fineness} marked {grade.permitted_marking} ({covered})")
                    elif grade.note:
                        lines.append(f"  - {grade.carat}: {grade.note}")
                    if grade.evidence:
                        citations.append(grade.evidence)
            if guide.checks:
                lines.append("")
                lines.append("What to check:")
                for index, check in enumerate(guide.checks, start=1):
                    lines.append(f"  {index}. {check.text}")
                    if check.evidence:
                        citations.append(check.evidence)
            if guide.huid is not None:
                lines.append("")
                lines.append(guide.huid.verification_note)

        # De-duplicate citations, preserving order.
        seen: set = set()
        unique: List[ClauseRef] = []
        for citation in citations:
            if citation.chunk_id in seen:
                continue
            seen.add(citation.chunk_id)
            unique.append(citation)

        shield = build_abstention(
            [c.chunk_id for c in unique],
            "Answered from the official BIS hallmarking documents ingested into this corpus; "
            "each point was resolved to a clause before being shown.",
        )
        return RAGResponse(
            question=question,
            query_type=QueryType.HALLMARKING_QUERY,
            answer="\n".join(lines).strip(),
            answerable=bool(unique),
            claims=[],
            citations=unique,
            evidence_shield=shield.report,
            standards_searched=sorted({c.standard_id for c in unique}),
            llm_used=False,
            disclaimer=DISCLAIMER,
        )

    # ------------------------------------------------------------------
    def _answer_certification(
        self,
        db: Database,
        question: str,
        *,
        product_id: Optional[str],
        standard_ids: Optional[Sequence[str]],
        state,
    ) -> Optional[RAGResponse]:
        """Answer a certification-scheme question from stored records.

        Three shapes are handled, in order:

        1. **Definitional** - "What is Scheme I?" names a scheme, so the
           registry answers it directly with its BIS source.
        2. **Product-scoped** - "Which scheme applies to my product?" resolves
           through the product's matched standards.
        3. **Standard-scoped** - a named or already-scoped standard.

        Returns None when the question is about certification but none of these
        can be resolved, so the caller falls through to ordinary clause
        retrieval rather than this path swallowing the question.
        """
        from app.services import certification, certification_process

        # 0. Process: "how do I get certified?" asks for the journey, not for
        # which scheme applies. Needs a standard to resolve against, so it
        # falls through to the scheme paths when there is nothing to scope to.
        if _PROCESS_RE.search(question or ""):
            target = self._scope_for_scheme(db, question, product_id, standard_ids, state)
            if target is not None:
                guidance = certification_process.resolve_for_standard(db, target)
                if guidance.available:
                    return self._process_response(question, guidance)

        # 1. Definitional: the question names a scheme.
        named = certification.find_scheme_by_text(db, question)
        asks_definition = bool(re.search(r"\b(what|explain|tell me about|describe)\b", question, re.I))
        if named is not None and asks_definition:
            info = certification.to_info(named)
            return self._scheme_response(
                question,
                answer=self._describe_scheme(info),
                guidance=None,
                scheme=info,
                standards=[],
            )

        # 2. Product-scoped.
        pid = product_id or (state.selected_product_id if state else None)
        if pid:
            product = products_repo(db).get(pid)
            if product is not None:
                payload = certification.resolve_for_product(db, product)
                primary = payload.get("primary")
                if primary is not None:
                    return self._scheme_response(
                        question,
                        answer=self._describe_guidance(primary),
                        guidance=primary,
                        scheme=primary.scheme,
                        standards=[primary.standard_id] if primary.standard_id else [],
                    )
                return self._scheme_response(
                    question,
                    answer=(
                        payload.get("note")
                        or certification.UNABLE_MESSAGE
                    ),
                    guidance=None,
                    scheme=None,
                    standards=[],
                    answerable=False,
                )

        # 3. Standard-scoped.
        scoped = list(standard_ids or []) or (state.selected_standard_ids if state else [])
        if not scoped:
            mentioned = extract_is_numbers(question)
            if mentioned:
                rows = standards_repo(db).find({"normalized_number": {"$in": list(mentioned)}})
                scoped = [r.id for r in rows]
        if scoped:
            guidance = certification.resolve_for_standard(db, scoped[0])
            return self._scheme_response(
                question,
                answer=self._describe_guidance(guidance),
                guidance=guidance,
                scheme=guidance.scheme,
                standards=[guidance.standard_id] if guidance.standard_id else [],
                answerable=guidance.scheme is not None,
            )

        # A bare "do I need BIS certification?" with nothing to scope it to.
        if named is not None:
            info = certification.to_info(named)
            return self._scheme_response(
                question,
                answer=self._describe_scheme(info),
                guidance=None,
                scheme=info,
                standards=[],
            )
        return None

    def _scope_for_scheme(
        self, db: Database, question: str, product_id, standard_ids, state
    ) -> Optional[str]:
        """The standard a certification question is about, or None."""
        pid = product_id or (state.selected_product_id if state else None)
        if pid:
            product = products_repo(db).get(pid)
            if product is not None:
                from app.services import certification

                primary = certification.resolve_for_product(db, product).get("primary")
                if primary is not None and primary.standard_id:
                    return primary.standard_id
        scoped = list(standard_ids or []) or (state.selected_standard_ids if state else [])
        if scoped:
            return scoped[0]
        mentioned = extract_is_numbers(question)
        if mentioned:
            rows = standards_repo(db).find({"normalized_number": {"$in": list(mentioned)}})
            if rows:
                return rows[0].id
        return None

    def _process_response(self, question: str, guidance) -> RAGResponse:
        """A process answer: the ordered journey, each step with its citation."""
        lines = [guidance.title, guidance.summary, ""]
        for stage in guidance.stages:
            citation = ""
            if stage.evidence is not None:
                citation = (
                    f" [{stage.evidence.display_number} clause "
                    f"{stage.evidence.clause_number}]"
                )
            elif stage.external:
                citation = " [not in this corpus - see the official BIS page]"
            lines.append(f"{stage.order}. {stage.title}{citation}")
            lines.append(f"   {stage.summary}")
        if guidance.timeline.available:
            lines.append("")
            lines.append("Implementation dates:")
            for deadline in guidance.timeline.deadlines:
                lines.append(f"   - {deadline.enterprise_category}: {deadline.date}")
        lines.append("")
        lines.append(guidance.message)

        shield = build_abstention(
            [s.evidence.chunk_id for s in guidance.stages if s.evidence is not None],
            "Each step cites a clause from the documents held for this standard; steps with no "
            "such clause are marked unevidenced rather than described from elsewhere.",
        )
        return RAGResponse(
            question=question,
            query_type=QueryType.CERTIFICATION_QUERY,
            answer="\n".join(lines),
            answerable=True,
            claims=[],
            citations=[s.evidence for s in guidance.stages if s.evidence is not None],
            evidence_shield=shield.report,
            process_guidance=guidance,
            standards_searched=[guidance.standard_id] if guidance.standard_id else [],
            llm_used=False,
            disclaimer=DISCLAIMER,
        )

    @staticmethod
    def _describe_scheme(info) -> str:
        """Plain-language description built only from sourced fields."""
        parts = [f"{info.name}."]
        if info.purpose:
            parts.append(info.purpose)
        if info.applies_to:
            parts.append(f"It applies to: {info.applies_to}")
        if info.mark:
            parts.append(f"Mark: {info.mark}.")
        if info.legal_basis:
            parts.append(f"Legal basis: {info.legal_basis}.")
        if info.unavailable_fields:
            parts.append(
                f"({info.unavailable_note} for: {', '.join(info.unavailable_fields)}.)"
            )
        if not info.is_verified:
            parts.append(
                "This scheme is registered from its official BIS page, but its details have "
                "not been transcribed into the platform's verified corpus."
            )
        return " ".join(parts)

    def _describe_guidance(self, guidance) -> str:
        """Plain-language answer for a resolved (or unresolved) determination."""
        if guidance.scheme is None:
            return guidance.message
        lines = [guidance.message]
        for reason in guidance.reasons:
            lines.append(f"- {reason.factor}: {reason.detail}")
        if guidance.regulatory is not None:
            lines.append(f"Regulatory status: {guidance.regulatory.status.value}.")
        lines.append(self._describe_scheme(guidance.scheme))
        return "\n".join(lines)

    @staticmethod
    def _scheme_response(
        question: str,
        *,
        answer: str,
        guidance,
        scheme,
        standards: Sequence[str],
        answerable: bool = True,
    ) -> RAGResponse:
        """A scheme answer carries no clause claims, so the Evidence Shield has
        nothing to strip - its report says so explicitly rather than being
        omitted, keeping the response shape identical to every other answer."""
        shield = build_abstention(
            [],
            "Answered from stored certification scheme and Quality Control Order records "
            "rather than clause retrieval, so no clause claims were generated to verify.",
        )
        return RAGResponse(
            question=question,
            query_type=QueryType.CERTIFICATION_QUERY,
            answer=answer,
            answerable=answerable,
            claims=[],
            citations=[],
            evidence_shield=shield.report,
            regulatory=guidance.regulatory if guidance is not None else None,
            scheme_guidance=guidance,
            scheme=scheme,
            standards_searched=list(standards),
            llm_used=False,
            disclaimer=DISCLAIMER,
        )

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
        self, db: Database, question: str,
        standard_ids: Optional[Sequence[str]], product_id: Optional[str],
        *, state: Optional[ConversationState] = None, follow_up: bool = False,
    ) -> Tuple[List[str], str]:
        if standard_ids:
            valid = corpus.filter_ids(
                db,
                [
                    s.id
                    for s in standards_repo(db).find({"_id": {"$in": list(standard_ids)}})
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
            rows = standards_repo(db).find(
                {"normalized_number": {"$in": list(mentioned)}}
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

        product = products_repo(db).get(product_id) if product_id else None

        if product is not None:
            # Matches are embedded in the product document.
            valid = corpus.filter_ids(db, [m.standard_id for m in product.matches])
            if valid:
                return valid, "Scoped to the product's matched standards."

        # Corpus-wide: run stage 1 on the question itself.
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
    def _citations(db: Database, hits: Sequence[ClauseHit]) -> List[ClauseRef]:
        standards: Dict[str, Standard] = {}
        out: List[ClauseRef] = []
        for hit in hits:
            standard = standards.get(hit.clause.standard_id)
            if standard is None:
                standard = standards_repo(db).get(hit.clause.standard_id)
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
