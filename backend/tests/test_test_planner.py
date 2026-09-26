"""Compliance test planner: the 'testing' tab of the Compliance Twin.

Beyond a flat status list, the planner must connect two things that were
already true separately but never joined up: which standard actually
specifies a test's procedure (from the same relationship records the
knowledge graph draws on), and which uploaded evidence satisfied a test (so a
manufacturer can click straight through to what they supplied).
"""
from __future__ import annotations

import io

import pytest

from app.core.constants import UploadCategory

REPORT_TEXT = """
Test Report No: TR-2026-0413
Model: EWH-15D
Tested by: National Test House, Mumbai
Temperature rise test carried out in accordance with Clause 6.2.1.
Result: PASS
"""


@pytest.fixture()
def water_heater(client):
    response = client.post(
        "/api/products/analyze",
        json={"description": "We manufacture a 15 litre domestic electric storage water "
                             "heater operating at 230 V."},
    )
    return response.json()["product"]


def test_planner_only_lists_test_report_requirements(client, water_heater):
    client.post(f"/api/products/{water_heater['id']}/discover-standards")
    client.post(
        f"/api/products/{water_heater['id']}/compliance/analyze", json={"evidence": []}
    )
    plan = client.get(f"/api/products/{water_heater['id']}/compliance").json()["testing_plan"]

    assert plan, "the water heater standard has test-report requirements"
    codes = {item["requirement_code"] for item in plan}
    # D1-R11 is the known temperature-rise test requirement used elsewhere.
    assert "D1-R11" in codes


def test_planner_states_which_standard_specifies_the_test_procedure(client, water_heater):
    """DEMO-STD-001 defers to DEMO-STD-003 for test methods - the planner must say so."""
    client.post(f"/api/products/{water_heater['id']}/discover-standards")
    client.post(
        f"/api/products/{water_heater['id']}/compliance/analyze", json={"evidence": []}
    )
    plan = client.get(f"/api/products/{water_heater['id']}/compliance").json()["testing_plan"]

    item = next(i for i in plan if i["requirement_code"] == "D1-R11")
    ref = item["test_method_reference"]
    assert ref is not None
    assert ref["standard"] == "DEMO-STD-003"
    assert "test method" in ref["evidence"].lower() or "DEMO-STD-003" in ref["evidence"]


def test_planner_links_a_supported_test_to_its_uploaded_evidence(client, water_heater):
    """A SUPPORTED test item must carry the id of the evidence that supported it,
    not just its name, so the UI can link straight to it."""
    pid = water_heater["id"]
    client.post(f"/api/products/{pid}/discover-standards")

    upload = client.post(
        f"/api/products/{pid}/evidence/upload",
        files={"file": ("report.txt", io.BytesIO(REPORT_TEXT.encode()), "text/plain")},
        data={"category": UploadCategory.TEST_REPORT.value, "name": "Lab report 413"},
    ).json()

    client.post(f"/api/products/{pid}/compliance/analyze", json={})
    plan = client.get(f"/api/products/{pid}/compliance").json()["testing_plan"]

    item = next(i for i in plan if i["requirement_code"] == "D1-R11")
    assert item["status"] == "SUPPORTED"
    assert item["matched_evidence"] == "Lab report 413"
    assert item["evidence_id"] == upload["id"]


def test_planner_items_without_a_test_method_reference_report_none_not_a_guess(client):
    """A standard with no stored references_test_method edge must say so plainly -
    never invent a plausible-looking cross-reference."""
    body = client.post(
        "/api/products/analyze",
        json={"description": "We manufacture a helmet for two wheeler riders."},
    ).json()
    pid = body["product"]["id"]
    client.post(f"/api/products/{pid}/discover-standards")
    client.post(f"/api/products/{pid}/compliance/analyze", json={"evidence": []})
    plan = client.get(f"/api/products/{pid}/compliance").json()["testing_plan"]

    # DEMO-STD-007 (helmets) has no references_test_method edge in the seed data.
    assert plan, "the helmet standard has test-report requirements"
    assert all(item["test_method_reference"] is None for item in plan)
