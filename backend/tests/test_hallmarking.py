"""BIS hallmarking guidance.

The contract under test is the platform's usual one, applied to a domain where
getting it wrong is expensive: a consumer must never be told that a piece of
jewellery is genuine, and a jeweller must never be told they are registered,
on the strength of anything this platform has not actually checked.
"""
from __future__ import annotations

import pytest

from app.core.constants import VerificationState
from app.db.repositories import hallmarking as hallmarking_repo
from app.db.repositories import hallmarking_centres as centres_repo
from app.rag.service import RAGService, classify_query
from app.services import hallmarking as hm

#: The official BIS hallmarking documents are fetched on demand, so a plain
#: checkout has no hallmarking corpus. Those tests skip rather than fail.
def _require_corpus(db):
    if not hm.corpus_available(db):
        pytest.skip("BIS hallmarking corpus not ingested in this checkout")


# ---------------------------------------------------------------------------
# Intent routing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "question",
    [
        "What is hallmarking?",
        "What is HUID?",
        "How can I check my gold jewellery?",
        "What does 22K916 mean?",
        "How do I get jewellery hallmarked?",
        "How do I register as a jeweller?",
        "What is an assaying centre?",
        "I am buying a 22K gold ring. What should I check?",
        "What marks should I look for on gold jewellery?",
        "Is this jewellery BIS hallmarked?",
        "silver fineness grades",
    ],
)
def test_hallmarking_questions_route_to_the_hallmarking_intent(question):
    assert classify_query(question).value == "HALLMARKING_QUERY"


@pytest.mark.parametrize(
    "question,expected",
    [
        # The false positives that matter: product marking clauses are a
        # completely different subject from jewellery hallmarking. Routing
        # these to hallmarking would answer a water-heater question with
        # gold-purity guidance.
        ("marking requirements under IS 2082", "MARKING_REQUIREMENT"),
        ("product marking clause", "MARKING_REQUIREMENT"),
        ("What does the marking clause say?", "MARKING_REQUIREMENT"),
        ("What are the labelling requirements?", "MARKING_REQUIREMENT"),
        ("Which BIS scheme applies to my product?", "CERTIFICATION_QUERY"),
        ("What is Scheme I?", "CERTIFICATION_QUERY"),
        ("How do I get certified?", "CERTIFICATION_QUERY"),
        ("Is IS 2082 mandatory?", "MANDATORY_STATUS"),
        ("What temperature rise test is required?", "TEST_REQUIREMENT"),
    ],
)
def test_non_hallmarking_questions_are_not_hijacked(question, expected):
    assert classify_query(question).value == expected


def test_standard_mark_question_is_not_jewellery_hallmarking():
    """"Standard mark" is the ISI mark on a product, not a jewellery hallmark."""
    assert classify_query("What is the standard mark?").value != "HALLMARKING_QUERY"


@pytest.mark.parametrize("question", ["What does 916 mean?", "silver 925 purity", "585 fineness"])
def test_a_bare_fineness_routes_to_hallmarking(question):
    assert classify_query(question).value == "HALLMARKING_QUERY"


@pytest.mark.parametrize("question", ["What is IS 916?", "IS 916 requirements", "IS 916:2000 scope"])
def test_is_916_is_not_treated_as_gold_fineness(question):
    """A real number clash worth guarding.

    916 is the fineness of 22-carat gold, but IS 916 in this corpus is "Square
    Tins for Solid Products". Answering a tin question with gold-purity
    guidance would be exactly the confident-but-wrong failure the platform
    exists to avoid.
    """
    assert classify_query(question).value != "HALLMARKING_QUERY"


def test_consumer_jewellery_question_is_not_routed_to_the_trade_journey(db):
    """"my gold jewellery" must not match the "jeweller" prefix.

    Regression: the jeweller pattern lacked a trailing word boundary, so a
    consumer asking what to check was handed the trade registration journey.
    """
    _require_corpus(db)
    response = RAGService().answer(db, "How can I check my gold jewellery?")
    assert response.query_type.value == "HALLMARKING_QUERY"
    assert "Getting jewellery hallmarked" not in response.answer, (
        "a consumer question was answered with the jeweller journey"
    )
    # It should be the consumer explanation: the marks to look for.
    assert "BIS Mark" in response.answer or "hallmarked gold article carries" in response.answer


# ---------------------------------------------------------------------------
# Corpus and provenance
# ---------------------------------------------------------------------------

def test_hallmarking_knowledge_is_seeded(db):
    records = hallmarking_repo(db).find()
    if not records:
        pytest.skip("hallmarking knowledge not seeded in this checkout")
    kinds = {r.kind for r in records}
    assert {"purity_grade", "hallmark_component", "process_stage", "huid"} <= kinds


def test_knowledge_records_store_no_quoted_clause_text(db):
    """Evidence is resolved live. Quoted text in the record could drift from
    the document it claims to cite."""
    for record in hallmarking_repo(db).find():
        payload = record.payload or {}
        assert "clause_text" not in payload
        assert "excerpt" not in payload
        assert "quote" not in payload


# ---------------------------------------------------------------------------
# Purity grades - values must be stored, never computed
# ---------------------------------------------------------------------------

def test_purity_grades_come_from_stored_verified_records(db):
    _require_corpus(db)
    grades = hm.purity_grades(db, "gold")
    assert grades, "gold purity grades should be available"

    by_carat = {g.carat: g for g in grades if g.carat}
    # The three grades the mandatory order names.
    for carat, fineness in (("22K", "916"), ("18K", "750"), ("14K", "585")):
        assert carat in by_carat, f"{carat} missing"
        grade = by_carat[carat]
        assert grade.fineness == fineness
        assert grade.mandatory_order_covered is True
        assert grade.state is VerificationState.VERIFIED
        assert grade.evidence is not None


def test_no_invented_purity_grade_is_returned(db):
    """Only grades present in the stored records may appear."""
    _require_corpus(db)
    stored = {
        (r.payload or {}).get("carat")
        for r in hallmarking_repo(db).find({"kind": "purity_grade"})
    }
    for grade in hm.purity_grades(db):
        assert grade.carat in stored


def test_every_shown_purity_grade_cites_a_clause_containing_it(db):
    """A grade's citation must literally contain the grade's own marking."""
    from app.db.repositories import clauses as clauses_repo

    _require_corpus(db)
    checked = 0
    for grade in hm.purity_grades(db, "gold"):
        if grade.evidence is None or not grade.permitted_marking:
            continue
        clause = clauses_repo(db).find_one({"chunk_id": grade.evidence.chunk_id})
        assert clause is not None
        assert grade.permitted_marking.lower() in (clause.text or "").lower(), (
            f"{grade.id} cites a clause that does not contain {grade.permitted_marking}"
        )
        checked += 1
    assert checked >= 3


def test_silver_grades_are_separate_from_gold(db):
    _require_corpus(db)
    silver = hm.purity_grades(db, "silver")
    assert silver
    assert all(g.material == "silver" for g in silver)
    assert all(g.carat is None for g in silver), "silver is graded by fineness, not carat"


# ---------------------------------------------------------------------------
# HUID - the strictest guardrail
# ---------------------------------------------------------------------------

def test_huid_guidance_never_claims_live_verification(db):
    _require_corpus(db)
    guidance = hm.huid_guidance(db)
    assert guidance.live_verification_available is False
    assert "not connected" in guidance.verification_note.lower()


def test_describing_a_huid_is_not_verifying_it(db):
    """A well-formed code must still be reported as unchecked."""
    _require_corpus(db)
    result = hm.describe_huid_format(db, "ABC123")

    # The structured contract is what callers act on. Scanning the prose is the
    # wrong test here: the disclaimer necessarily discusses genuineness in order
    # to deny it ("cannot tell you whether a HUID is genuine").
    assert result["checked_against_bis"] is False
    assert result["state"] == VerificationState.UNABLE_TO_VERIFY.value

    # No field may carry an affirmative verdict under any name.
    for key, value in result.items():
        if key in ("matches_documented_format", "checked_against_bis"):
            continue
        assert not (
            isinstance(value, bool) and value
        ), f"{key} is a truthy flag that a UI could read as a verdict"

    # ...and the denial must actually reach the caller.
    note = result["verification_note"].lower()
    assert "not checked" in note or "not connected" in note
    assert "cannot tell you" in note


def test_a_perfectly_formatted_huid_is_still_unverified(db):
    _require_corpus(db)
    result = hm.describe_huid_format(db, "AB12CD")
    assert result["matches_documented_format"] is True
    # Matching the format is not the same as being genuine.
    assert result["checked_against_bis"] is False
    assert result["state"] == VerificationState.UNABLE_TO_VERIFY.value


def test_empty_huid_is_handled_without_a_verdict(db):
    _require_corpus(db)
    result = hm.describe_huid_format(db, "")
    assert result["checked_against_bis"] is False
    assert result["matches_documented_format"] is False


# ---------------------------------------------------------------------------
# Consumer guide
# ---------------------------------------------------------------------------

def test_consumer_guide_is_fully_cited(db):
    _require_corpus(db)
    guide = hm.consumer_guide(db, "gold")

    assert guide.available is True
    assert guide.components, "hallmark components should be listed"
    assert guide.checks, "consumer checks should be listed"
    assert guide.facts_with_evidence > 0
    for component in guide.components:
        assert component.evidence is not None or component.state is VerificationState.UNABLE_TO_VERIFY


def test_consumer_guide_states_it_cannot_verify_an_item(db):
    _require_corpus(db)
    guide = hm.consumer_guide(db, "gold")
    assert guide.huid is not None
    assert guide.huid.live_verification_available is False


def test_hallmark_components_cite_the_hallmarking_corpus_only(db):
    """A hallmarking fact must never borrow a clause from a product standard
    that happens to use the word "marking"."""
    _require_corpus(db)
    for component in hm.hallmark_components(db, "gold"):
        if component.evidence is None:
            continue
        assert component.evidence.standard_id in hm.HALLMARKING_DOCUMENT_IDS


# ---------------------------------------------------------------------------
# Jeweller journey
# ---------------------------------------------------------------------------

def test_jeweller_journey_is_ordered_and_cited(db):
    _require_corpus(db)
    guide = hm.jeweller_guide(db)

    assert guide.available is True
    orders = [s.order for s in guide.stages]
    assert orders == sorted(orders)
    assert orders[0] == 1, "the journey should start at step 1"
    assert guide.stages_with_evidence > 0


def test_every_jeweller_stage_is_evidenced_or_says_it_is_not(db):
    _require_corpus(db)
    for stage in hm.jeweller_guide(db).stages:
        if stage.evidence is None:
            assert stage.state is VerificationState.UNABLE_TO_VERIFY
            assert stage.evidence_note


def test_no_stage_claims_a_jeweller_is_registered(db):
    _require_corpus(db)
    blob = " ".join(
        f"{s.title} {s.summary} {' '.join(s.what_you_do)}" for s in hm.jeweller_guide(db).stages
    ).lower()
    for forbidden in ("you are registered", "your registration is valid", "you are bis registered"):
        assert forbidden not in blob


# ---------------------------------------------------------------------------
# A&H centres
# ---------------------------------------------------------------------------

def test_centre_directory_summary_carries_its_retrieval_date(db):
    summary = hm.centre_summary(db)
    if not summary.available:
        assert "No verified Assaying & Hallmarking Centre directory" in summary.note
        return
    assert summary.total > 0
    assert summary.retrieved_at, "a snapshot must say when it was taken"
    assert summary.source_url


def test_centre_search_absence_is_not_a_negative_finding(db):
    """A centre missing from the snapshot means the snapshot lacks it, not that
    it is unrecognised."""
    summary = hm.centre_summary(db)
    if not summary.available:
        pytest.skip("centre directory not seeded in this checkout")

    result = hm.search_centres(db, state="Atlantis")
    assert result.total_matching == 0
    assert "does not list one" in result.message
    assert "not that none exists" in result.message


def test_suspended_centres_are_not_silently_hidden(db):
    summary = hm.centre_summary(db)
    if not summary.available:
        pytest.skip("centre directory not seeded in this checkout")
    # The unfiltered directory holds more than just operative centres.
    assert centres_repo(db).count() >= summary.operative
    everything = hm.search_centres(db, limit=200)
    assert everything.summary.total == summary.total


def test_operative_filter_only_narrows(db):
    summary = hm.centre_summary(db)
    if not summary.available:
        pytest.skip("centre directory not seeded in this checkout")
    all_in_state = hm.search_centres(db, state=summary.states[0])
    operative = hm.search_centres(db, state=summary.states[0], operative_only=True)
    assert operative.total_matching <= all_in_state.total_matching


# ---------------------------------------------------------------------------
# Assistant integration - the three demo scenarios
# ---------------------------------------------------------------------------

def test_consumer_scenario_answers_with_citations(db):
    _require_corpus(db)
    response = RAGService().answer(
        db, "I am buying a 22K gold ring. What should I check before buying?"
    )

    assert response.query_type.value == "HALLMARKING_QUERY"
    assert response.answerable is True
    assert response.citations, "a consumer answer must cite the BIS source"
    assert all(c.standard_id in hm.HALLMARKING_DOCUMENT_IDS for c in response.citations)
    assert response.llm_used is False


def test_huid_scenario_explains_without_verifying(db):
    _require_corpus(db)
    response = RAGService().answer(db, "What is HUID and how do I verify it?")

    assert response.query_type.value == "HALLMARKING_QUERY"
    lowered = response.answer.lower()
    assert "six" in lowered
    assert "not connected" in lowered or "not checked" in lowered
    for forbidden in ("this huid is valid", "your jewellery is genuine"):
        assert forbidden not in lowered


def test_jeweller_scenario_returns_the_journey(db):
    _require_corpus(db)
    response = RAGService().answer(
        db, "I manufacture gold jewellery. How do I get it hallmarked?"
    )

    assert response.query_type.value == "HALLMARKING_QUERY"
    assert "register" in response.answer.lower()
    assert response.citations


def test_assistant_answer_introduces_no_unsupported_purity_grade(db):
    """The generated answer may only name grades that exist in stored records."""
    import re

    _require_corpus(db)
    stored = {
        (g.permitted_marking or "").lower()
        for g in hm.purity_grades(db)
        if g.permitted_marking
    }
    response = RAGService().answer(db, "What does 22K916 mean? What purity grades exist?")
    # Every NNKNNN-style token in the answer must be a stored marking.
    for token in re.findall(r"\b\d{2}k\d{3}\b", response.answer.lower()):
        assert token in stored, f"answer introduced unsupported grade {token!r}"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_api_consumer_guide(client, db):
    _require_corpus(db)
    body = client.get("/api/hallmarking/consumer-guide").json()
    assert body["available"] is True
    assert body["components"]
    assert body["huid"]["live_verification_available"] is False


def test_api_purity_grades_are_material_filtered(client, db):
    _require_corpus(db)
    gold = client.get("/api/hallmarking/purity-grades", params={"material": "gold"}).json()
    assert gold and all(g["material"] == "gold" for g in gold)


def test_api_huid_describe_never_reports_verification(client, db):
    _require_corpus(db)
    body = client.get("/api/hallmarking/huid/describe", params={"code": "AB12CD"}).json()
    assert body["checked_against_bis"] is False
    assert body["state"] == "UNABLE_TO_VERIFY"


def test_api_jeweller_guide(client, db):
    _require_corpus(db)
    body = client.get("/api/hallmarking/jeweller-guide").json()
    assert body["available"] is True
    assert body["stages"][0]["order"] == 1


def test_api_centres_reports_snapshot_provenance(client):
    body = client.get("/api/hallmarking/centres/summary").json()
    if not body["available"]:
        assert body["note"]
        return
    assert body["retrieved_at"]
    assert body["total"] >= body["operative"]
