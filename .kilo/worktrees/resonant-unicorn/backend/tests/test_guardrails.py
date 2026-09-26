"""The three critical anti-hallucination tests.

These are the tests that make the platform's trust claims falsifiable:

1. A standard ID the model invents cannot reach the API response.
2. A claim citing evidence that was not retrieved is rejected.
3. The absence of a regulatory record is never reported as "voluntary".
"""
from __future__ import annotations

import json

import pytest

from app.core.constants import ComplianceStatus, RegulatoryStatus
from app.models import QCO, Product, Standard
from app.rag.evidence_shield import ABSTENTION_ANSWER, EvidenceShield
from app.services.product_understanding import ProductUnderstandingService
from app.services.regulatory import resolve_regulatory_status
from app.services.standard_discovery import StandardDiscoveryService


# ---------------------------------------------------------------------------
# 1. Closed candidate list
# ---------------------------------------------------------------------------

def test_llm_cannot_introduce_a_standard_outside_the_candidate_list(db, scripted_llm):
    """The model returns STD-999. It must never appear in the result."""
    payload = json.dumps(
        {
            "rankings": [
                {
                    "standard_id": "STD-999",
                    "relevance": "HIGH",
                    "reason": "This standard definitely applies to your product.",
                },
                {
                    "standard_id": "IS 4321",
                    "relevance": "HIGH",
                    "reason": "An IS number recalled from training data.",
                },
                {
                    "standard_id": "DEMO-STD-001",
                    "relevance": "HIGH",
                    "reason": "Scope covers domestic electric storage water heaters.",
                },
            ]
        }
    )
    llm = scripted_llm(payload)
    assert llm.available, "the scripted provider must look available to exercise the LLM path"

    understanding = ProductUnderstandingService(llm=llm)
    profile = understanding.analyze(
        "We manufacture a 15 litre domestic electric storage water heater at 230 V."
    )
    product = understanding.persist(db, profile)

    service = StandardDiscoveryService(llm=llm)
    result = service.discover(db, product)

    returned_ids = {m["standard"].id for m in result["matches"]}
    assert "STD-999" not in returned_ids
    assert "IS 4321" not in returned_ids
    assert returned_ids, "the legitimate candidate should still be returned"
    assert returned_ids <= {s.id for s in db.query(Standard).all()}

    # The rejection is reported rather than silently swallowed.
    assert "STD-999" in result["rejected_ids"]
    assert "IS 4321" in result["rejected_ids"]
    assert any("Evidence Shield" in note for note in result["notes"])

    # And nothing bogus was persisted.
    schema = service.to_schema(db, result["matches"])
    assert all(match.standard.id in returned_ids for match in schema)


def test_discovery_falls_back_to_deterministic_when_llm_output_is_unusable(db, scripted_llm):
    llm = scripted_llm("this is not JSON at all")
    understanding = ProductUnderstandingService(llm=llm)
    product = understanding.persist(
        db, understanding.analyze("We make 5 litre aluminium domestic pressure cookers.")
    )
    result = StandardDiscoveryService(llm=llm).discover(db, product)

    assert result["matches"], "discovery must still work when the model fails"
    assert all(m["explanation_source"] != "llm" for m in result["matches"])


# ---------------------------------------------------------------------------
# 2. Evidence Shield
# ---------------------------------------------------------------------------

def test_evidence_shield_rejects_a_claim_citing_unretrieved_evidence():
    shield = EvidenceShield(["chunk-1", "chunk-2"])
    result = shield.validate(
        "The appliance must pass a temperature rise test and be certified.",
        [
            {"text": "The appliance must pass a temperature rise test.", "source_chunk_ids": ["chunk-1"]},
            {"text": "The appliance is certified by BIS.", "source_chunk_ids": ["chunk-999"]},
        ],
    )

    kept = [c.text for c in result.claims]
    assert "The appliance must pass a temperature rise test." in kept
    assert all("certified" not in text for text in kept)
    assert "certified" not in result.answer

    assert result.report.supported_claims == 1
    assert result.report.total_claims == 2
    assert result.report.rejected_claims[0]["invalid_chunk_ids"] == ["chunk-999"]


def test_evidence_shield_abstains_when_no_claim_survives():
    shield = EvidenceShield(["chunk-1"])
    result = shield.validate(
        "IS 12345 makes this mandatory.",
        [{"text": "IS 12345 makes this mandatory.", "source_chunk_ids": ["chunk-fabricated"]}],
    )

    assert result.answerable is False
    assert result.answer == ABSTENTION_ANSWER
    assert result.claims == []
    assert result.report.verified is False


def test_evidence_shield_rejects_a_claim_with_no_citation_at_all():
    shield = EvidenceShield(["chunk-1"])
    result = shield.validate("Something confident.", [{"text": "Something confident.", "source_chunk_ids": []}])
    assert result.answerable is False
    assert result.report.rejected_claims[0]["reason"] == "claim carried no supporting evidence"


def test_rag_endpoint_only_cites_chunks_that_exist(client):
    response = client.post(
        "/api/rag/query",
        json={"question": "What temperature rise test is required?", "standard_ids": ["DEMO-STD-001"]},
    )
    assert response.status_code == 200
    body = response.json()

    retrieved = set(body["evidence_shield"]["retrieved_chunk_ids"])
    for claim in body["claims"]:
        assert claim["source_chunk_ids"], "every displayed claim must carry a citation"
        assert set(claim["source_chunk_ids"]) <= retrieved


# ---------------------------------------------------------------------------
# 3. Regulatory status
# ---------------------------------------------------------------------------

def test_absence_of_a_qco_record_is_unable_to_verify_not_voluntary(db):
    """DEMO-STD-002 deliberately has no regulatory record."""
    assert db.query(QCO).filter(QCO.standard_id == "DEMO-STD-002").count() == 0

    status = resolve_regulatory_status(db, "DEMO-STD-002")

    assert status.status == RegulatoryStatus.UNABLE_TO_VERIFY
    assert status.status != RegulatoryStatus.VOLUNTARY
    assert status.verified is False
    assert "does not mean the standard is voluntary" in status.message.lower()


def test_present_qco_record_is_reported_from_the_database(db):
    status = resolve_regulatory_status(db, "DEMO-STD-001")
    assert status.status == RegulatoryStatus.MANDATORY
    assert status.source == "QCO record"
    assert status.notification_number
    # The demo corpus is not verified, and the message must say so.
    assert status.is_mock is True
    assert "demonstration dataset" in status.message


def test_unknown_standard_regulatory_status_is_unable_to_verify(db):
    status = resolve_regulatory_status(db, "NOT-A-REAL-STANDARD")
    assert status.status == RegulatoryStatus.UNABLE_TO_VERIFY


def test_llm_cannot_override_regulatory_status(db, scripted_llm, monkeypatch):
    """Even if a model insists a standard is voluntary, the DB answer wins."""
    from app.rag import service as rag_module

    llm = scripted_llm(
        json.dumps(
            {
                "answer": "This standard is voluntary and no licence is needed.",
                "claims": [
                    {
                        "text": "This standard is voluntary.",
                        "source_chunk_ids": ["DEMO-STD-002::c1.1"],
                    }
                ],
            }
        )
    )
    rag = rag_module.RAGService(llm=llm)
    monkeypatch.setattr(rag_module, "get_rag_service", lambda: rag)

    response = rag.answer(db, "Is DEMO-STD-002 mandatory?")

    assert response.regulatory is not None
    assert response.regulatory.status == RegulatoryStatus.UNABLE_TO_VERIFY
    assert response.answer.startswith("Regulatory status: UNABLE TO VERIFY")


# ---------------------------------------------------------------------------
# Closed status vocabulary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", list(ComplianceStatus))
def test_every_compliance_status_is_a_known_member(status):
    assert ComplianceStatus(status.value) is status


def test_gap_analysis_only_emits_known_statuses(client, db):
    product = db.query(Product).first()
    if product is None:
        pytest.skip("no product produced by earlier tests")
    response = client.get(f"/api/products/{product.id}/compliance")
    assert response.status_code == 200
    allowed = {s.value for s in ComplianceStatus}
    for result in response.json()["results"]:
        assert result["status"] in allowed
