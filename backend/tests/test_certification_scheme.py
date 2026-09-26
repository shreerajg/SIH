"""BIS certification scheme guidance.

The contract under test is the same one the rest of the platform enforces: a
scheme may only be returned when a stored record names it, and everything else
is an explicit "unable to verify".
"""
from __future__ import annotations

import pytest

from app.core.constants import RegulatoryStatus, SchemeApplicability
from app.db.repositories import qcos as qcos_repo
from app.db.repositories import scheme_products as scheme_products_repo
from app.db.repositories import schemes as schemes_repo
from app.rag.service import classify_query
from app.services import certification

#: The verified BIS pack (Product Manuals + gazette QCOs) is fetched on demand
#: and is not part of data/raw/standards, so a plain `pytest` run has only the
#: demo corpus. Tests that need a verified record skip rather than fail.
VERIFIED_STANDARD = "IS-2082-2018-PM"


def _require_verified(db, standard_id=VERIFIED_STANDARD):
    from app.db.repositories import standards as standards_repo

    if not standards_repo(db).exists(standard_id):
        pytest.skip(f"{standard_id} is not in this corpus (verified BIS pack not ingested)")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_scheme_registry_is_seeded(db):
    schemes = certification.list_schemes(db)
    assert schemes, "the certification scheme registry should be seeded"
    codes = {s.code for s in schemes}
    assert "Scheme-I" in codes


def test_scheme_i_is_verified_and_fully_sourced(db):
    scheme = certification.get_scheme(db, "SCHEME-I")
    assert scheme is not None
    info = certification.to_info(scheme)
    assert info.is_verified is True
    assert info.mark == "ISI Mark"
    assert info.purpose and info.applies_to and info.legal_basis
    assert info.source_url and "bis.gov.in" in info.source_url
    # Everything shown is attributable.
    assert info.field_sources, "a verified scheme must record where its content came from"
    assert info.unavailable_fields == []


def test_unsourced_scheme_reports_its_gaps_rather_than_inventing_them(db):
    """A scheme registered from its BIS URL but not transcribed must name the
    fields it cannot fill, not quietly omit them or make them up."""
    scheme = certification.get_scheme(db, "HALLMARKING")
    assert scheme is not None
    info = certification.to_info(scheme)

    assert info.is_verified is False
    assert info.purpose is None
    assert "purpose" in info.unavailable_fields
    assert info.unavailable_note == certification.UNVERIFIABLE_FIELD
    # The registry entry is still real: it carries an official BIS source.
    assert info.source_url and "bis.gov.in" in info.source_url


def test_scheme_lookup_matches_aliases_but_not_nonsense(db):
    assert certification.find_scheme_by_text(db, "what is scheme i?").id == "SCHEME-I"
    assert certification.find_scheme_by_text(db, "tell me about the ISI mark").id == "SCHEME-I"
    assert certification.find_scheme_by_text(db, "hallmarking rules").id == "HALLMARKING"
    # An unrecognised name resolves to nothing rather than the nearest scheme.
    assert certification.find_scheme_by_text(db, "scheme zeta quantum") is None
    assert certification.find_scheme_by_text(db, "") is None


# ---------------------------------------------------------------------------
# Applicability - the anti-hallucination contract
# ---------------------------------------------------------------------------

def test_verified_standard_resolves_to_scheme_i_with_both_sources(db):
    """IS 2082 has a verified QCO naming Scheme-I *and* appears in the official
    BIS Scheme-I product list, so the answer is APPLICABLE and cites both."""
    _require_verified(db)
    guidance = certification.resolve_for_standard(db, "IS-2082-2018-PM")

    assert guidance.applicability is SchemeApplicability.APPLICABLE
    assert guidance.scheme is not None
    assert guidance.scheme.id == "SCHEME-I"

    kinds = {e.kind for e in guidance.evidence}
    assert kinds == {"qco_record", "scheme_product_list"}
    assert all(e.is_verified for e in guidance.evidence)

    factors = {r.factor for r in guidance.reasons}
    assert "Quality Control Order" in factors
    assert "BIS product list" in factors


def test_mandatory_status_is_delegated_not_re_derived(db):
    """The scheme module must not invent its own mandatory/voluntary answer."""
    _require_verified(db)
    guidance = certification.resolve_for_standard(db, "IS-2082-2018-PM")
    assert guidance.regulatory is not None
    assert guidance.regulatory.status is RegulatoryStatus.MANDATORY

    from app.services.regulatory import resolve_regulatory_status

    assert guidance.regulatory.status is resolve_regulatory_status(db, "IS-2082-2018-PM").status


def test_demo_only_evidence_is_downgraded_to_likely(db):
    """A demo QCO names Scheme-I, but a synthetic record must never be
    presented with the same confidence as a verified one."""
    guidance = certification.resolve_for_standard(db, "DEMO-STD-001")

    assert guidance.applicability is SchemeApplicability.LIKELY
    assert guidance.scheme is not None
    assert not any(e.is_verified for e in guidance.evidence)
    assert "demonstration corpus" in guidance.message


def test_standard_with_no_scheme_record_is_unable_to_verify(db):
    """The core guardrail: no record naming a scheme means no scheme, not a
    guess from the product category."""
    guidance = certification.resolve_for_standard(db, "DEMO-STD-003")

    assert guidance.applicability is SchemeApplicability.UNABLE_TO_VERIFY
    assert guidance.scheme is None
    assert "will not infer" in guidance.message


def test_unknown_standard_is_reported_not_guessed(db):
    guidance = certification.resolve_for_standard(db, "IS-9999-NOT-REAL")
    assert guidance.applicability is SchemeApplicability.UNABLE_TO_VERIFY
    assert guidance.scheme is None


def test_scheme_is_never_inferred_from_the_product_list_alone_when_absent(db):
    """Absence from the BIS list is not evidence of absence.

    A standard that is in no QCO and in no Scheme-I row must abstain - it must
    not be reported as 'not covered by any scheme'.
    """
    guidance = certification.resolve_for_standard(db, "DEMO-STD-003")
    assert guidance.applicability is SchemeApplicability.UNABLE_TO_VERIFY
    # The vocabulary has no way to express "not applicable" at all.
    assert not hasattr(SchemeApplicability, "NOT_APPLICABLE")


def test_scheme_product_index_is_loaded_from_the_official_bis_page(db):
    """The applicability oracle must be the extracted BIS list, carrying its
    own provenance."""
    entry = scheme_products_repo(db).find_one({"normalized_number": "IS-2082"})
    if entry is None:
        pytest.skip("Scheme-I index not built in this checkout")
    assert entry.scheme_id == "SCHEME-I"
    assert entry.is_verified is True
    assert "bis.gov.in" in (entry.source_url or "")
    assert entry.document_id == "BIS-SCHEME-I-INDEX"


# ---------------------------------------------------------------------------
# Product flow: product -> standard -> QCO -> scheme
# ---------------------------------------------------------------------------

def test_product_without_discovery_gets_a_note_not_a_scheme(db):
    from app.models import Product

    product = Product(id="prd-test-noscheme", name="Unanalysed product")
    payload = certification.resolve_for_product(db, product)

    assert payload["primary"] is None
    assert "Run standard discovery first" in payload["note"]


def test_full_chain_product_to_standard_to_qco_to_scheme(db):
    """The end-to-end path the feature exists to serve."""
    from app.models import Product, ProductStandardMatch
    from app.services.regulatory import resolve_regulatory_status

    _require_verified(db)
    product = Product(
        id="prd-test-chain",
        name="Storage water heater",
        matches=[
            ProductStandardMatch(
                id="psm-test-1",
                product_id="prd-test-chain",
                standard_id="IS-2082-2018-PM",
                relevance="HIGH",
            )
        ],
    )
    payload = certification.resolve_for_product(db, product)
    primary = payload["primary"]

    assert primary is not None
    assert primary.standard_id == "IS-2082-2018-PM"
    assert primary.scheme.id == "SCHEME-I"
    assert primary.applicability is SchemeApplicability.APPLICABLE
    # ...and the mandatory/voluntary answer still comes from the QCO engine.
    assert primary.regulatory.status is resolve_regulatory_status(db, "IS-2082-2018-PM").status
    # ...and every claim carries a source.
    assert all(e.source_url or e.document_id for e in primary.evidence)


def test_a_resolvable_standard_outranks_an_unresolvable_one(db):
    """The primary recommendation is the strongest determination available, not
    simply the first standard that was matched."""
    from app.models import Product, ProductStandardMatch

    product = Product(
        id="prd-test-rank",
        name="Mixed product",
        matches=[
            # No scheme record at all - must not become the primary.
            ProductStandardMatch(id="m1", product_id="prd-test-rank", standard_id="DEMO-STD-003"),
            # Has a QCO naming Scheme-I.
            ProductStandardMatch(id="m2", product_id="prd-test-rank", standard_id="DEMO-STD-001"),
        ],
    )
    payload = certification.resolve_for_product(db, product)
    primary = payload["primary"]
    assert primary is not None
    assert primary.standard_id == "DEMO-STD-001"
    assert primary.applicability is SchemeApplicability.LIKELY
    # Both standards are still reported individually.
    assert {g.standard_id for g in payload["per_standard"]} == {"DEMO-STD-001", "DEMO-STD-003"}


def test_verified_evidence_outranks_demo_when_choosing_the_primary(db):
    from app.models import Product, ProductStandardMatch

    _require_verified(db, "IS-4151-2015-PM")
    product = Product(
        id="prd-test-rank-v",
        name="Mixed product",
        matches=[
            ProductStandardMatch(id="m1", product_id="prd-test-rank-v", standard_id="DEMO-STD-001"),
            ProductStandardMatch(id="m2", product_id="prd-test-rank-v", standard_id="IS-4151-2015-PM"),
        ],
    )
    primary = certification.resolve_for_product(db, product)["primary"]
    assert primary is not None
    # The verified standard wins even though the demo one was listed first.
    assert primary.standard_id == "IS-4151-2015-PM"
    assert primary.applicability is SchemeApplicability.APPLICABLE


# ---------------------------------------------------------------------------
# Assistant integration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "question",
    [
        "Which BIS scheme applies to my product?",
        "What is Scheme I?",
        "Do I need BIS certification?",
        "Which certification should I apply for?",
        "Explain Scheme-II",
    ],
)
def test_scheme_questions_route_to_the_certification_intent(question):
    assert classify_query(question).value == "CERTIFICATION_QUERY"


@pytest.mark.parametrize(
    "question,expected",
    [
        # "scheme of inspection and testing" is a clause question, not a
        # certification-scheme question - the pattern must not swallow it.
        ("What does the scheme of inspection and testing say?", "TEST_REQUIREMENT"),
        ("What temperature rise test is required?", "TEST_REQUIREMENT"),
        ("Is IS 2082 mandatory?", "MANDATORY_STATUS"),
        ("What changed in the latest amendment?", "AMENDMENT_QUERY"),
        # Jewellery hallmarking has its own intent; it is not a Conformity
        # Assessment scheme and must not be answered as one.
        ("What is hallmarking?", "HALLMARKING_QUERY"),
        ("What is HUID?", "HALLMARKING_QUERY"),
    ],
)
def test_existing_intents_are_not_hijacked(question, expected):
    assert classify_query(question).value == expected


def test_assistant_answers_what_is_scheme_i_from_the_registry(db):
    from app.rag.service import RAGService

    response = RAGService().answer(db, "What is Scheme I?")

    assert response.query_type.value == "CERTIFICATION_QUERY"
    assert response.answerable is True
    assert response.scheme is not None
    assert response.scheme.id == "SCHEME-I"
    assert "ISI Mark" in response.answer
    # No clause claims were made, so nothing should be fabricated as a citation.
    assert response.claims == []
    assert response.citations == []


def test_assistant_scheme_answer_for_a_scoped_standard_cites_its_evidence(db):
    from app.rag.service import RAGService

    _require_verified(db)
    response = RAGService().answer(
        db, "Which BIS scheme applies?", standard_ids=["IS-2082-2018-PM"]
    )

    assert response.query_type.value == "CERTIFICATION_QUERY"
    assert response.scheme_guidance is not None
    assert response.scheme_guidance.applicability is SchemeApplicability.APPLICABLE
    assert response.scheme_guidance.evidence
    assert "Quality Control Order" in response.answer


def test_assistant_abstains_when_no_scheme_can_be_confirmed(db):
    from app.rag.service import RAGService

    response = RAGService().answer(
        db, "Which certification should I apply for?", standard_ids=["DEMO-STD-003"]
    )

    assert response.answerable is False
    assert response.scheme is None
    assert response.scheme_guidance.applicability is SchemeApplicability.UNABLE_TO_VERIFY


def test_a_model_cannot_invent_a_scheme_because_no_model_is_consulted(db):
    """Scheme answers are built from stored records, so an LLM has no route to
    influence which scheme is returned."""
    from app.rag.service import RAGService

    response = RAGService().answer(db, "What is Scheme I?")
    assert response.llm_used is False


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

def test_api_lists_schemes(client):
    body = client.get("/api/certification/schemes").json()
    assert isinstance(body, list) and body
    assert any(s["code"] == "Scheme-I" for s in body)


def test_api_returns_404_for_an_unknown_scheme(client):
    assert client.get("/api/certification/schemes/SCHEME-NOPE").status_code == 404


def test_api_lookup_rejects_an_unknown_name_rather_than_guessing(client):
    assert client.get("/api/certification/lookup", params={"q": "scheme zeta"}).status_code == 404
    ok = client.get("/api/certification/lookup", params={"q": "ISI mark"})
    assert ok.status_code == 200
    assert ok.json()["id"] == "SCHEME-I"


def test_api_scheme_for_standard(client, db):
    _require_verified(db)
    body = client.get("/api/standards/IS-2082-2018-PM/certification-scheme").json()
    assert body["applicability"] == "APPLICABLE"
    assert body["scheme"]["id"] == "SCHEME-I"
    assert body["regulatory"]["status"] == "MANDATORY"
    assert body["evidence"]


def test_api_scheme_for_a_demo_standard_is_labelled_as_such(client):
    """Always runs: the demo corpus alone must still produce a sourced answer,
    clearly marked as coming from demonstration records."""
    body = client.get("/api/standards/DEMO-STD-001/certification-scheme").json()
    assert body["applicability"] == "LIKELY"
    assert body["scheme"]["id"] == "SCHEME-I"
    assert body["evidence"] and all(e["is_verified"] is False for e in body["evidence"])


def test_api_scheme_for_standard_without_a_record_abstains(client):
    body = client.get("/api/standards/DEMO-STD-003/certification-scheme").json()
    assert body["applicability"] == "UNABLE_TO_VERIFY"
    assert body["scheme"] is None
