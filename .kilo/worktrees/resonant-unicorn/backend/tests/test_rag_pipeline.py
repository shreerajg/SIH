"""LLM abstraction, reranking, multi-turn RAG and the hardened Evidence Shield.

The adversarial cases here are the point of the file: a scripted model is given
every opportunity to smuggle unsupported material through, and each attempt must
be stopped by backend enforcement rather than by prompt wording.
"""
from __future__ import annotations

import json

import pytest

from app.core.constants import CorpusMode, QueryType
from app.llm.service import LLMService
from app.rag import service as rag_module
from app.rag.conversation import ConversationStore, get_conversation_store, is_follow_up
from app.rag.evidence_shield import ABSTENTION_ANSWER, EvidenceShield
from app.search.reranker import (
    LexicalReranker,
    RerankItem,
    backend_name,
    rerank,
)
from app.services import corpus


# ---------------------------------------------------------------------------
# Priority 2 - LLM abstraction and mode labelling
# ---------------------------------------------------------------------------

def test_no_key_reports_retrieval_only_mode():
    from app.llm.service import get_llm

    status = get_llm().status()
    assert status["available"] is False
    assert status["mode"] == "Retrieval-only"
    assert status["fallback_mode"] is True
    assert status["model"] is None
    assert "Retrieval-only" in status["note"]
    # The abstraction still advertises what it could use.
    assert {"openai", "anthropic", "gemini"} <= set(status["supported_providers"])


def test_configured_provider_reports_ai_plus_retrieval(scripted_llm):
    llm = scripted_llm('{"answer": "x", "claims": []}')
    status = llm.status()
    assert status["available"] is True
    assert status["mode"] == "AI + Retrieval"
    assert status["fallback_mode"] is False
    assert status["provider"] == "scripted"


def test_structured_generation_validates_against_the_schema(scripted_llm):
    from pydantic import BaseModel

    class Shape(BaseModel):
        name: str
        count: int

    good = scripted_llm('{"name": "ok", "count": 3}')
    assert good.structured("s", "p", Shape).count == 3

    # Output that cannot be coerced returns None rather than raising into the
    # request path, so callers fall back to their deterministic implementation.
    bad = scripted_llm("not json at all")
    assert bad.structured("s", "p", Shape, retries=0) is None
    assert bad.last_error


def test_provider_failure_never_raises_into_the_caller():
    from app.llm.base import LLMProvider, LLMResult

    class Exploding(LLMProvider):
        name = "exploding"

        @property
        def available(self) -> bool:
            return True

        def generate(self, system, messages, **kwargs):
            return LLMResult("", self.name, "m", error="upstream 500")

    service = LLMService(provider=Exploding("k", "m"))
    assert service.text("s", "p") is None
    assert service.last_error == "upstream 500"


# ---------------------------------------------------------------------------
# Priority 3 - reranking
# ---------------------------------------------------------------------------

def test_reranker_promotes_the_directly_responsive_clause():
    """Retrieval order is deliberately wrong here; reranking must fix it."""
    items = [
        RerankItem(
            id="marking",
            text="The rating label shall carry the manufacturer name and rated voltage.",
            retrieval_score=0.95,          # wrongly ranked first by retrieval
            clause_type="marking",
        ),
        RerankItem(
            id="temp-test",
            text="The appliance shall be operated at 1.06 times rated voltage until "
                 "thermal equilibrium is reached and the temperature rise recorded.",
            retrieval_score=0.55,
            clause_type="test",
        ),
    ]
    ranked = rerank(
        "What temperature rise test is required?", items,
        query_type=QueryType.TEST_REQUIREMENT,
    )
    assert ranked[0].id == "temp-test"
    assert ranked[0].rerank_score > ranked[1].rerank_score


def test_reranker_uses_numeric_overlap():
    items = [
        RerankItem(id="a", text="The limit shall not exceed 90 degC.", clause_type="requirement"),
        RerankItem(id="b", text="The limit shall not exceed 75 degC.", clause_type="requirement"),
    ]
    ranked = rerank("Which clause sets the 75 degC limit?", items)
    assert ranked[0].id == "b", "the clause containing the quoted number should win"


def test_lexical_reranker_is_always_available():
    assert backend_name(), "a reranker backend must always be reported"
    scores = LexicalReranker().score("test", [RerankItem(id="x", text="test clause")])
    assert len(scores) == 1


def test_reranking_never_invents_or_drops_ids():
    items = [RerankItem(id=f"c{i}", text=f"clause {i} about testing") for i in range(5)]
    ranked = rerank("testing", items)
    assert {r.id for r in ranked} <= {i.id for i in items}


# ---------------------------------------------------------------------------
# Priority 3 - multi-turn context
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "question,expected",
    [
        ("Why is that necessary?", True),
        ("And what about marking?", True),
        ("Is it required by law?", True),
        ("What temperature tests apply?", False),
        ("Is DEMO-STD-002 mandatory?", False),
        ("What does the toy standard say about cords?", False),
    ],
)
def test_follow_up_detection(question, expected):
    assert is_follow_up(question) is expected


def test_follow_up_keeps_the_previous_scope(db):
    get_conversation_store().reset()
    rag = rag_module.RAGService()

    first = rag.answer(db, "What temperature rise test is required?",
                       standard_ids=["DEMO-STD-001"])
    assert first.conversation_id
    assert first.standards_searched == ["DEMO-STD-001"]

    follow = rag.answer(db, "Why is that necessary?", conversation_id=first.conversation_id)
    assert follow.follow_up is True
    assert follow.standards_searched == ["DEMO-STD-001"]
    assert "Follow-up" in follow.scope_note
    # The follow-up inherits the intent of the question it refers back to.
    assert follow.query_type is QueryType.TEST_REQUIREMENT


def test_a_new_subject_mid_conversation_is_not_treated_as_a_follow_up(db):
    get_conversation_store().reset()
    rag = rag_module.RAGService()

    first = rag.answer(db, "What temperature rise test is required?",
                       standard_ids=["DEMO-STD-001"])
    second = rag.answer(db, "What does DEMO-STD-007 cover?",
                        conversation_id=first.conversation_id)

    assert second.follow_up is False
    assert second.standards_searched == ["DEMO-STD-007"], (
        "a question that names its own subject must not inherit stale scope"
    )


def test_conversation_state_is_bounded():
    store = ConversationStore()
    state = store.get_or_create(None)
    from app.rag.conversation import MAX_TURNS, Turn

    for i in range(MAX_TURNS + 5):
        state.record(Turn(question=f"q{i}", answer=f"a{i}"))
    assert len(state.turns) == MAX_TURNS, "scrollback must not grow without bound"
    # The summary is a few lines, never the whole transcript.
    assert state.summary.count("\n") <= 6


# ---------------------------------------------------------------------------
# Priority 4 - hardened Evidence Shield (adversarial)
# ---------------------------------------------------------------------------

def test_shield_strips_uncited_prose_even_when_all_claims_validate():
    """The subtle attack: valid claims, plus an extra assertion in the prose.

    Dropping only the citation would leave the assertion on screen.
    """
    shield = EvidenceShield(["chunk-1"])
    result = shield.validate(
        "The appliance must pass a temperature rise test. "
        "It is also certified by BIS under licence 12345.",
        [{"text": "The appliance must pass a temperature rise test.",
          "source_chunk_ids": ["chunk-1"]}],
    )
    assert "certified" not in result.answer
    assert "licence" not in result.answer
    assert result.answer == "The appliance must pass a temperature rise test."


def test_shield_preserves_prose_that_is_fully_covered():
    shield = EvidenceShield(["chunk-1"])
    text = "The appliance must pass a temperature rise test."
    result = shield.validate(text, [{"text": text, "source_chunk_ids": ["chunk-1"]}])
    assert result.answer == text


def test_shield_removes_the_text_of_a_rejected_claim_not_just_its_citation():
    shield = EvidenceShield(["chunk-1"])
    result = shield.validate(
        "A temperature rise test is required. Your product is BIS compliant.",
        [
            {"text": "A temperature rise test is required.", "source_chunk_ids": ["chunk-1"]},
            {"text": "Your product is BIS compliant.", "source_chunk_ids": ["chunk-999"]},
        ],
    )
    assert "compliant" not in result.answer
    assert result.report.supported_claims == 1
    assert result.report.rejected_claims[0]["invalid_chunk_ids"] == ["chunk-999"]


def test_shield_returns_insufficient_evidence_when_nothing_survives():
    shield = EvidenceShield(["chunk-1", "chunk-2"])
    result = shield.validate(
        "IS 4321 makes this mandatory and your product passes.",
        [
            {"text": "IS 4321 makes this mandatory.", "source_chunk_ids": ["chunk-z"]},
            {"text": "Your product passes.", "source_chunk_ids": []},
        ],
    )
    assert result.answerable is False
    assert result.answer == ABSTENTION_ANSWER
    assert result.claims == []
    assert result.report.verified is False
    assert result.report.supported_claims == 0


def test_shield_keeps_only_the_valid_half_of_a_mixed_citation_list():
    shield = EvidenceShield(["chunk-1"])
    result = shield.validate(
        "Both apply.",
        [{"text": "Both apply.", "source_chunk_ids": ["chunk-1", "chunk-nope"]}],
    )
    assert result.claims[0].source_chunk_ids == ["chunk-1"]
    assert result.report.rejected_claims, "the invalid id must still be reported"


def test_end_to_end_a_hostile_model_cannot_get_unsupported_text_on_screen(db, scripted_llm):
    """Full pipeline with a model that fabricates a citation and a conclusion."""
    hostile = scripted_llm(
        json.dumps(
            {
                "answer": "Clause 6.2.1 requires a temperature rise test. "
                          "Your product is therefore fully BIS compliant and needs no licence.",
                "claims": [
                    {
                        "text": "Clause 6.2.1 requires a temperature rise test.",
                        "source_chunk_ids": ["DEMO-STD-001::c6.2.1"],
                    },
                    {
                        "text": "Your product is fully BIS compliant and needs no licence.",
                        "source_chunk_ids": ["chunk-fabricated-999"],
                    },
                ],
            }
        )
    )
    rag = rag_module.RAGService(llm=hostile)
    response = rag.answer(db, "What temperature rise test is required?",
                          standard_ids=["DEMO-STD-001"])

    assert "compliant" not in response.answer.lower()
    assert "needs no licence" not in response.answer.lower()
    assert response.evidence_shield.rejected_claims
    retrieved = set(response.evidence_shield.retrieved_chunk_ids)
    for claim in response.claims:
        assert set(claim.source_chunk_ids) <= retrieved


def test_corpus_mode_starvation_abstains_rather_than_falling_back(db, monkeypatch):
    """VERIFIED mode with no official documents must answer nothing."""
    monkeypatch.setattr(corpus.settings, "corpus_mode", "VERIFIED")
    assert corpus.current_mode() is CorpusMode.VERIFIED

    rag = rag_module.RAGService()
    response = rag.answer(db, "What temperature rise test is required?",
                          standard_ids=["DEMO-STD-001"])

    assert response.answerable is False
    assert response.claims == []
    assert response.citations == []
    assert "no official documents are loaded" in response.answer
