"""Certification process guidance.

The contract: a step may only cite text that really says what the step is
about, a step with no such text is marked unevidenced rather than described
from elsewhere, and no process is produced at all for a standard whose scheme
could not be confirmed.
"""
from __future__ import annotations

import pytest

from app.db.repositories import processes as processes_repo
from app.rag.service import RAGService, _PROCESS_RE, classify_query
from app.services import certification_process as process

VERIFIED_STANDARD = "IS-2082-2018-PM"


def _require_verified(db, standard_id=VERIFIED_STANDARD):
    from app.db.repositories import standards as standards_repo

    if not standards_repo(db).exists(standard_id):
        pytest.skip(f"{standard_id} is not in this corpus (verified BIS pack not ingested)")


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

def test_process_template_is_seeded(db):
    template = processes_repo(db).find_one({"scheme_id": "SCHEME-I"})
    assert template is not None
    assert template.stages, "the Scheme-I journey should have stages"
    orders = [int(s["order"]) for s in template.stages]
    assert orders == sorted(orders), "stages should be declared in order"


def test_template_stores_no_quoted_source_text(db):
    """Evidence is resolved live against the corpus. If the template carried
    quoted clause text it could drift from the documents it claims to cite."""
    template = processes_repo(db).find_one({"scheme_id": "SCHEME-I"})
    for stage in template.stages:
        assert "clause_text" not in stage
        assert "excerpt" not in stage
        assert "quote" not in stage


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def test_no_confirmed_scheme_means_no_process(db):
    """The central guardrail: a process is only described for a scheme that
    was actually confirmed from stored BIS records."""
    guidance = process.resolve_for_standard(db, "DEMO-STD-003")

    assert guidance.available is False
    assert guidance.stages == []
    assert "no certification scheme could be confirmed" in guidance.message.lower()


def test_unknown_standard_is_reported_not_guessed(db):
    guidance = process.resolve_for_standard(db, "IS-0000-NOT-REAL")
    assert guidance.available is False
    assert guidance.stages == []


def test_demo_standard_with_a_scheme_still_gets_a_process(db):
    """DEMO-STD-001 has a (demo) QCO naming Scheme-I, so the journey is shown -
    the steps are real even though the corpus backing them is synthetic."""
    guidance = process.resolve_for_standard(db, "DEMO-STD-001")

    assert guidance.available is True
    assert guidance.scheme_id == "SCHEME-I"
    assert len(guidance.stages) >= 5
    assert [s.order for s in guidance.stages] == sorted(s.order for s in guidance.stages)


def test_every_cited_clause_really_contains_the_step_topic(db):
    """The anti-hallucination rule, checked directly: a stage's citation must
    literally contain one of that stage's keywords."""
    from app.db.repositories import clauses as clauses_repo

    template = processes_repo(db).find_one({"scheme_id": "SCHEME-I"})
    keywords_by_stage = {
        s["id"]: [k.lower() for k in (s.get("clause_keywords") or [])] for s in template.stages
    }

    guidance = process.resolve_for_standard(db, "DEMO-STD-001")
    checked = 0
    for stage in guidance.stages:
        if stage.evidence is None:
            continue
        clause = clauses_repo(db).find_one({"chunk_id": stage.evidence.chunk_id})
        assert clause is not None, f"{stage.id} cites a chunk that does not exist"
        haystack = f"{clause.heading} {clause.text}".lower()
        assert any(k in haystack for k in keywords_by_stage[stage.id]), (
            f"{stage.id} cites a clause that does not contain any of its keywords"
        )
        checked += 1
    assert checked > 0, "expected at least one evidenced stage"


def test_unevidenced_stage_says_so_instead_of_inventing_text(db):
    guidance = process.resolve_for_standard(db, "DEMO-STD-001")
    for stage in guidance.stages:
        if stage.evidence is None:
            assert stage.evidence_note, f"{stage.id} has neither evidence nor a note"


def test_external_stage_is_marked_and_never_clause_cited(db):
    """BIS application mechanics are not in this corpus, so that stage must
    link out and must not borrow a citation from an unrelated clause."""
    guidance = process.resolve_for_standard(db, "DEMO-STD-001")
    external = [s for s in guidance.stages if s.external]

    assert external, "the BIS application stage should be marked external"
    for stage in external:
        assert stage.evidence is None
        assert stage.external_url and "bis.gov.in" in stage.external_url
        assert stage.evidence_note


def test_stages_with_evidence_count_matches_the_stages(db):
    guidance = process.resolve_for_standard(db, "DEMO-STD-001")
    actual = sum(1 for s in guidance.stages if s.evidence is not None)
    assert guidance.stages_with_evidence == actual


def test_verified_standard_cites_its_own_product_manual(db):
    """Citations must come from the documents held for *this* standard."""
    _require_verified(db)
    guidance = process.resolve_for_standard(db, VERIFIED_STANDARD)

    assert guidance.available is True
    assert guidance.stages_with_evidence >= 5
    cited = {s.evidence.standard_id for s in guidance.stages if s.evidence is not None}
    # Either the Product Manual itself or the QCO gazette that names it.
    assert VERIFIED_STANDARD in cited


def test_marking_step_cites_the_marking_clause_not_a_passing_mention(db):
    """Regression: selecting the first clause that merely contains "Standard
    Mark" cited the Quality Assurance Plan clause instead of the marking one."""
    _require_verified(db)
    guidance = process.resolve_for_standard(db, VERIFIED_STANDARD)
    marking = next(s for s in guidance.stages if s.id == "apply-standard-mark")

    assert marking.evidence is not None
    excerpt = (marking.evidence.excerpt or "").lower()
    assert "marking" in excerpt[:80], (
        f"expected the marking clause, got: {excerpt[:120]!r}"
    )


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def test_timeline_reads_enterprise_categories_from_the_qco_table(db):
    """MSMEs get later implementation dates than other enterprises, and the
    platform must surface that rather than a single generalised date."""
    _require_verified(db)
    guidance = process.resolve_for_standard(db, VERIFIED_STANDARD)
    timeline = guidance.timeline

    assert timeline.available is True
    categories = {d.enterprise_category for d in timeline.deadlines}
    assert "Micro enterprises" in categories
    assert "Small enterprises" in categories
    # Read from a real table, so it carries a citation.
    assert timeline.evidence is not None
    assert all(d.date for d in timeline.deadlines)


def test_timeline_absence_is_reported_not_faked(db):
    guidance = process.resolve_for_standard(db, "DEMO-STD-001")
    if not guidance.timeline.available:
        assert guidance.timeline.note
        assert guidance.timeline.deadlines == []


# ---------------------------------------------------------------------------
# Product flow
# ---------------------------------------------------------------------------

def test_product_without_a_scheme_gets_no_process(db):
    from app.models import Product

    guidance = process.resolve_for_product(db, Product(id="prd-no-proc", name="Unanalysed"))
    assert guidance.available is False
    assert guidance.stages == []


def test_full_chain_product_to_process(db):
    from app.models import Product, ProductStandardMatch

    product = Product(
        id="prd-proc-chain",
        name="Water heater",
        matches=[
            ProductStandardMatch(
                id="m1", product_id="prd-proc-chain", standard_id="DEMO-STD-001"
            )
        ],
    )
    guidance = process.resolve_for_product(db, product)
    assert guidance.available is True
    assert guidance.standard_id == "DEMO-STD-001"
    assert guidance.stages


# ---------------------------------------------------------------------------
# Assistant integration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "question",
    [
        "How do I get certified?",
        "What is the certification process?",
        "What are the steps to get the ISI mark?",
        "How to apply for a BIS licence?",
    ],
)
def test_process_questions_are_certification_queries(question):
    assert classify_query(question).value == "CERTIFICATION_QUERY"
    assert _PROCESS_RE.search(question)


def test_which_scheme_is_not_treated_as_a_process_question():
    """"Which scheme applies" must still get the scheme answer, not the journey."""
    assert not _PROCESS_RE.search("Which BIS scheme applies to my product?")
    assert not _PROCESS_RE.search("What is Scheme I?")


def test_assistant_returns_the_journey_with_citations(db):
    response = RAGService().answer(
        db, "How do I get certified?", standard_ids=["DEMO-STD-001"]
    )

    assert response.query_type.value == "CERTIFICATION_QUERY"
    assert response.process_guidance is not None
    assert response.process_guidance.available is True
    assert response.answerable is True
    # Citations are the stage evidence, so every one resolves to a real chunk.
    assert len(response.citations) == response.process_guidance.stages_with_evidence
    assert response.llm_used is False


def test_assistant_refuses_to_describe_a_process_without_a_scheme(db):
    response = RAGService().answer(
        db, "How do I get certified?", standard_ids=["DEMO-STD-003"]
    )
    assert response.process_guidance is None
    assert response.answerable is False


def test_assistant_scheme_question_is_not_hijacked_by_the_process_branch(db):
    response = RAGService().answer(
        db, "Which BIS scheme applies?", standard_ids=["DEMO-STD-001"]
    )
    assert response.process_guidance is None
    assert response.scheme is not None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_api_process_for_standard(client):
    body = client.get("/api/standards/DEMO-STD-001/certification-process").json()
    assert body["available"] is True
    assert body["scheme_id"] == "SCHEME-I"
    assert len(body["stages"]) >= 5
    assert body["stages"][0]["order"] == 1


def test_api_process_without_a_scheme_is_unavailable_not_empty(client):
    body = client.get("/api/standards/DEMO-STD-003/certification-process").json()
    assert body["available"] is False
    assert body["message"]
    assert body["stages"] == []


def test_api_process_stage_shape(client):
    body = client.get("/api/standards/DEMO-STD-001/certification-process").json()
    for stage in body["stages"]:
        assert stage["id"] and stage["title"] and stage["summary"]
        assert stage["actor"] in {"manufacturer", "bis", "both"}
        # Either it cites something, or it explains why it does not.
        assert stage["evidence"] is not None or stage["evidence_note"]
