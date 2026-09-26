"""Amendment impact: deterministic diff plus cautious product relevance.

The diff must never come from a model, and the relevance verdict must never
become a compliance verdict.
"""
from __future__ import annotations

import pytest

from app.core.constants import AmendmentRelevance
from app.models import Amendment, Product
from app.services.amendments import AmendmentService, changed_numbers, compute_diff


# ---------------------------------------------------------------------------
# Deterministic diffing
# ---------------------------------------------------------------------------

def test_diff_is_computed_not_generated():
    diff = compute_diff(
        "shall not exceed 75 degC.", "shall not exceed 70 degC."
    )
    assert any(s.op == "delete" and "75" in s.text for s in diff)
    assert any(s.op == "insert" and "70" in s.text for s in diff)
    assert any(s.op == "equal" for s in diff), "unchanged text must stay unchanged"


def test_numeric_direction_is_labelled():
    tightened = changed_numbers("not exceed 75 degC", "not exceed 70 degC")[0]
    assert tightened["direction"] == "tightened"
    relaxed = changed_numbers("at least 200 mm", "at least 220 mm")[0]
    assert relaxed["direction"] == "relaxed"


def test_the_narrative_never_declares_non_compliance(db):
    impacts = AmendmentService().for_standards(db, ["DEMO-STD-001"])
    assert impacts
    text = impacts[0].potential_impact.lower()
    assert "non-compliant" not in text
    assert "you are in breach" not in text
    assert impacts[0].potential_impact.startswith("Potential impact")


# ---------------------------------------------------------------------------
# Product-specific relevance
# ---------------------------------------------------------------------------

@pytest.fixture()
def analysed_water_heater(client):
    product = client.post(
        "/api/products/analyze",
        json={"description": "We manufacture a 15 litre domestic electric storage water "
                             "heater operating at 230 V."},
    ).json()["product"]
    client.post(f"/api/products/{product['id']}/discover-standards")
    client.post(
        f"/api/products/{product['id']}/compliance/analyze",
        json={"attributes": {"max_water_temperature_c": 72}, "evidence": []},
    )
    return product


def test_an_amendment_touching_an_assessed_requirement_is_likely_relevant(
    client, analysed_water_heater
):
    twin = client.get(f"/api/products/{analysed_water_heater['id']}/compliance").json()
    amendment = next(
        a for a in twin["amendments"] if a["amendment"]["standard_id"] == "DEMO-STD-001"
    )
    impact = amendment["product_impact"]

    assert impact["relevance"] == AmendmentRelevance.LIKELY_RELEVANT.value
    assert "D1-R06" in impact["affected_requirement_codes"]
    # 72 degC satisfies the current 75 degC limit, so it is supported today -
    # and that is exactly why the amendment to 70 degC deserves attention.
    assert "D1-R06" in impact["supported_requirement_codes"]
    assert "reviewed against the amended wording" in impact["reason"]
    # The verdict stays a relevance judgement, not a compliance one.
    assert "non-compliant" not in impact["reason"].lower()


def test_an_amendment_to_an_unmatched_standard_is_no_direct_match(db):
    """The toy amendment must not be reported as relevant to a water heater."""
    product = db.query(Product).filter(Product.category == "water-heater").first()
    if product is None:
        pytest.skip("no analysed water heater in the session database")

    toy_amendment = (
        db.query(Amendment).filter(Amendment.standard_id == "DEMO-STD-005").first()
    )
    assert toy_amendment is not None

    impact = AmendmentService().assess_for_product(db, toy_amendment, product, ["D5-R05"])
    assert impact.relevance is AmendmentRelevance.NO_DIRECT_MATCH_FOUND
    assert "not among the standards matched" in impact.reason


def test_no_product_context_is_unable_to_verify(db):
    amendment = db.query(Amendment).first()
    impact = AmendmentService().assess_for_product(db, amendment, None, [])
    assert impact.relevance is AmendmentRelevance.UNABLE_TO_VERIFY
    assert impact.affected_requirement_codes == []


def test_a_clause_with_no_structured_requirement_requires_review(db):
    product = db.query(Product).filter(Product.category == "water-heater").first()
    if product is None:
        pytest.skip("no analysed water heater in the session database")
    amendment = (
        db.query(Amendment).filter(Amendment.standard_id == "DEMO-STD-001").first()
    )
    impact = AmendmentService().assess_for_product(db, amendment, product, [])
    assert impact.relevance is AmendmentRelevance.REQUIRES_REVIEW
    assert "Review it manually" in impact.reason


def test_every_relevance_value_is_from_the_closed_vocabulary(client, analysed_water_heater):
    twin = client.get(f"/api/products/{analysed_water_heater['id']}/compliance").json()
    allowed = {r.value for r in AmendmentRelevance}
    for amendment in twin["amendments"]:
        assert amendment["product_impact"]["relevance"] in allowed
