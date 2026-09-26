"""End-to-end API tests covering the golden demo flow."""
from __future__ import annotations

import pytest

from app.core.constants import ComplianceStatus


def test_health_reports_the_live_stack(client):
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["corpus"]["standards"] >= 8
    assert body["corpus"]["clauses"] > 100
    assert body["corpus"]["requirements"] > 50
    assert body["corpus"]["vectors_clauses"] == body["corpus"]["clauses"]
    assert body["llm"]["available"] is False
    assert body["llm"]["fallback_mode"] is True
    assert "does not issue BIS certification" in body["disclaimer"]


def test_evaluation_endpoint_reports_the_last_recorded_run(client):
    """This never re-runs the (slow) evaluation - it reads whatever
    scripts/evaluate.py last wrote and says plainly if nothing has run."""
    body = client.get("/api/evaluation").json()
    if not body["available"]:
        assert "python scripts/evaluate.py" in body["message"]
        return
    assert body["corpus"] == "demo"
    assert "standard_discovery" in body
    assert "grounding" in body
    assert body["standard_discovery"]["cases"] > 0
    # Every metric is either a real number or an honest null - never a string
    # placeholder like "N/A" standing in for a number that wasn't computed.
    assert isinstance(body["standard_discovery"]["recall_at_1"], (int, float))


def test_corpus_manifest_declares_the_dataset_as_demo(client):
    body = client.get("/api/corpus/manifest").json()
    assert body["available"] is True
    assert body["dataset_status"] == "demo"
    assert body["manifest_version"] == "1.1"

    # Manifest v1.1 carries explicit provenance on every document, demo or not.
    for doc in body["documents"]:
        assert "document_id" in doc and "local_path" in doc
        assert doc["is_demo"] is not doc["is_verified"], (
            f"{doc['document_id']}: a document is either synthetic or official, never both"
        )
        if doc["is_verified"]:
            # An official document must be traceable back to where it came from.
            assert doc["source_url"] and "bis.gov.in" in doc["source_url"]
            assert doc["retrieved_at"]
            assert not doc["document_id"].upper().startswith(("DEMO-", "SAMPLE-"))
        else:
            # A synthetic record must never wear a real-looking identifier.
            assert doc["document_id"].upper().startswith(("DEMO-", "SAMPLE-")) or doc[
                "document_type"
            ] in {"regulatory", "amendment"}


def test_standards_listing_and_detail(client):
    listing = client.get("/api/standards").json()
    assert len(listing) >= 8
    assert all(s["is_mock"] for s in listing), "the demo corpus must be flagged as mock"

    detail = client.get("/api/standards/DEMO-STD-001").json()
    assert detail["standard"]["display_number"] == "DEMO-STD-001"
    assert detail["clauses"]
    assert detail["related"], "normative references should be present"
    assert detail["requirement_categories"]


def test_unknown_standard_returns_404(client):
    assert client.get("/api/standards/NOPE").status_code == 404


def test_source_endpoint_returns_full_clause_text(client):
    detail = client.get("/api/standards/DEMO-STD-001").json()
    chunk_id = detail["clauses"][0]["chunk_id"]

    source = client.get(f"/api/sources/{chunk_id}").json()
    assert source["chunk_id"] == chunk_id
    assert source["text"]
    assert source["standard"]["id"] == "DEMO-STD-001"


def test_unknown_source_returns_404(client):
    assert client.get("/api/sources/does::not::exist").status_code == 404


# ---------------------------------------------------------------------------
# Golden manufacturer flow
# ---------------------------------------------------------------------------

@pytest.fixture()
def water_heater(client):
    response = client.post(
        "/api/products/analyze",
        json={
            "description": "We manufacture a 15 litre domestic electric storage water heater "
                           "operating at 230 V with a 2000 W heating element."
        },
    )
    assert response.status_code == 200
    return response.json()["product"]


def test_product_analysis_builds_a_structured_profile(water_heater):
    assert water_heater["category"] == "water-heater"
    assert water_heater["attributes"]["capacity_litres"] == 15.0
    assert water_heater["attributes"]["voltage_v"] == 230.0
    assert water_heater["attributes"]["application"] == "domestic"
    assert water_heater["profile_source"] == "deterministic"


def test_vague_description_triggers_an_interview_instead_of_a_guess(client):
    body = client.post("/api/products/analyze", json={"description": "We manufacture heaters."}).json()

    assert body["interview_required"] is True
    questions = body["product"]["missing_fields"]
    assert questions, "the platform must ask rather than assume"
    assert any(q["field"] == "heater_type" for q in questions)
    assert all(q["why_it_matters"] for q in questions)


def test_interview_answers_are_normalised_into_attributes(client):
    product = client.post(
        "/api/products/analyze", json={"description": "We manufacture heaters."}
    ).json()["product"]

    body = client.post(
        f"/api/products/{product['id']}/interview",
        json={
            "answers": [
                {"field": "heater_type", "value": "Storage water heater"},
                {"field": "capacity_litres", "value": "15"},
                {"field": "voltage_v", "value": "230 V single phase"},
                {"field": "application", "value": "Domestic / household"},
            ]
        },
    ).json()

    attributes = body["product"]["attributes"]
    assert attributes["capacity_litres"] == 15.0
    assert attributes["voltage_v"] == 230.0
    assert attributes["application"] == "domestic"
    assert body["product"]["name"] == "Storage water heater"

    # Round 1 (what decides which standards apply) is complete, so the only
    # questions left are the round-2 ones that merely sharpen the analysis.
    remaining = body["product"]["missing_fields"]
    assert all(q["priority"] == 2 for q in remaining), (
        "no decisive question should remain once round 1 is answered"
    )
    assert len(remaining) <= 4, "a round must stay short enough to answer"


def test_skipping_the_interview_keeps_answers_and_reports_unknown(client):
    product = client.post(
        "/api/products/analyze", json={"description": "We manufacture heaters."}
    ).json()["product"]

    body = client.post(
        f"/api/products/{product['id']}/interview",
        json={
            "answers": [{"field": "capacity_litres", "value": "25"}],
            "skip_remaining": True,
        },
    ).json()

    assert body["product"]["attributes"]["capacity_litres"] == 25.0
    assert body["product"]["missing_fields"] == []
    assert any("UNKNOWN" in note for note in body["notes"])


def test_ambiguous_product_family_is_asked_about_not_assumed(client):
    body = client.post(
        "/api/products/analyze", json={"description": "We make consumer goods."}
    ).json()

    assert body["product"]["category"] == ""
    fields = [q["field"] for q in body["product"]["missing_fields"]]
    assert "product_family" in fields


def test_standard_discovery_returns_evidenced_matches(client, water_heater):
    body = client.post(f"/api/products/{water_heater['id']}/discover-standards").json()

    matches = body["matches"]
    assert matches
    assert matches[0]["standard"]["id"] == "DEMO-STD-001"
    assert matches[0]["relevance"] == "HIGH"
    assert matches[0]["matched_attributes"], "a match must explain what matched"
    assert matches[0]["scope_evidence"], "a match must cite the scope it relied on"
    assert matches[0]["evidence_clauses"]

    ids = {m["standard"]["id"] for m in matches}
    assert "DEMO-STD-002" in ids, "the general electrical safety standard should be pulled in"
    assert "DEMO-STD-004" not in ids, "a pressure cooker standard is not relevant to a water heater"

    # Regulatory status is present for every match and comes from records.
    for match in matches:
        assert match["regulatory"]["status"] in {"MANDATORY", "VOLUNTARY", "UNABLE_TO_VERIFY"}


def test_discovered_standards_are_persisted(client, water_heater):
    client.post(f"/api/products/{water_heater['id']}/discover-standards")
    body = client.get(f"/api/products/{water_heater['id']}/standards").json()
    assert body["matches"]


def test_match_score_breakdown_survives_a_reload(client, water_heater):
    """The 'how was this ranked' signals must be readable after a GET, not just
    right after the POST that computed them - otherwise the visualisation only
    ever works immediately after a live re-run."""
    live = client.post(f"/api/products/{water_heater['id']}/discover-standards").json()
    live_match = next(m for m in live["matches"] if m["standard"]["id"] == "DEMO-STD-001")
    assert live_match["score"] > 0
    assert isinstance(live_match["signals"].get("semantic"), (int, float))
    assert isinstance(live_match["signals"].get("bm25"), (int, float))
    assert isinstance(live_match["signals"].get("metadata"), (int, float))

    reloaded = client.get(f"/api/products/{water_heater['id']}/standards").json()
    reloaded_match = next(
        m for m in reloaded["matches"] if m["standard"]["id"] == "DEMO-STD-001"
    )
    assert reloaded_match["score"] == pytest.approx(live_match["score"])
    assert reloaded_match["signals"].get("semantic") == live_match["signals"].get("semantic")
    assert reloaded_match["signals"].get("bm25") == live_match["signals"].get("bm25")


def test_compliance_analysis_requires_standards_first(client):
    product = client.post(
        "/api/products/analyze", json={"description": "We manufacture a 10 L storage water heater."}
    ).json()["product"]

    response = client.post(f"/api/products/{product['id']}/compliance/analyze", json={})
    assert response.status_code == 409


def test_gap_analysis_produces_the_full_status_spread(client, water_heater):
    client.post(f"/api/products/{water_heater['id']}/discover-standards")

    body = client.post(
        f"/api/products/{water_heater['id']}/compliance/analyze",
        json={
            "attributes": {
                "max_water_temperature_c": 80,      # exceeds the 75 degC clause limit
                "thermal_cutout_fitted": "Yes",
                "thermal_cutout_reset_type": "manual",
                "earthing_terminal_provided": "Yes",
                "inner_container_material": "Vitreous enamel coated mild steel",
                "pressure_relief_device_fitted": "Yes",
                "protection_class": "I",
            },
            "evidence": [
                {"evidence_type": "test_report", "name": "Temperature rise test report"},
                {"evidence_type": "marking_artwork", "name": "Rating label artwork"},
            ],
        },
    ).json()

    statuses = {r["status"] for r in body["results"]}
    assert ComplianceStatus.SUPPORTED.value in statuses
    assert ComplianceStatus.POTENTIAL_GAP.value in statuses, "80 degC breaches the 75 degC limit"
    assert ComplianceStatus.TEST_REQUIRED.value in statuses
    assert ComplianceStatus.DOCUMENT_REQUIRED.value in statuses

    gap = next(r for r in body["results"] if r["status"] == ComplianceStatus.POTENTIAL_GAP.value)
    assert "80" in gap["reason"] and "75" in gap["reason"]
    assert gap["source"]["clause_number"]

    readiness = body["readiness"]
    assert readiness["label"] == "Pre-Compliance Readiness"
    assert 0 <= readiness["percentage"] <= 100
    assert readiness["supported"] <= readiness["assessable"]


def test_supplied_evidence_flips_a_requirement_to_supported(client, water_heater):
    client.post(f"/api/products/{water_heater['id']}/discover-standards")

    without = client.post(
        f"/api/products/{water_heater['id']}/compliance/analyze", json={"evidence": []}
    ).json()
    with_evidence = client.post(
        f"/api/products/{water_heater['id']}/compliance/analyze",
        json={"evidence": [{"evidence_type": "test_report", "name": "Temperature rise test report"}]},
    ).json()

    def status_of(body, code):
        return next(r["status"] for r in body["results"] if r["requirement_code"] == code)

    assert status_of(without, "D1-R11") == ComplianceStatus.TEST_REQUIRED.value
    assert status_of(with_evidence, "D1-R11") == ComplianceStatus.SUPPORTED.value


def test_licence_requirements_need_official_verification(client, water_heater):
    client.post(f"/api/products/{water_heater['id']}/discover-standards")
    body = client.post(f"/api/products/{water_heater['id']}/compliance/analyze", json={}).json()

    licence = [r for r in body["results"] if r["requirement_code"] == "D8-R07"]
    if licence:
        assert licence[0]["status"] == ComplianceStatus.OFFICIAL_VERIFICATION_REQUIRED.value


def test_compliance_twin_assembles_the_whole_picture(client, water_heater):
    client.post(f"/api/products/{water_heater['id']}/discover-standards")
    client.post(
        f"/api/products/{water_heater['id']}/compliance/analyze",
        json={"evidence": [{"evidence_type": "test_report", "name": "Temperature rise test report"}]},
    )

    twin = client.get(f"/api/products/{water_heater['id']}/compliance").json()

    assert twin["analysis_available"] is True
    assert twin["summary"]["applicable_standards"] >= 3
    assert twin["summary"]["requirements_identified"] > 20
    assert twin["standards"] and twin["results"]
    assert twin["testing_plan"], "a test plan should be derived from test-evidence requirements"
    assert twin["sources"], "every dashboard needs its sources"
    assert twin["graph"]["available"] is True
    assert twin["graph"]["nodes"] and twin["graph"]["edges"]
    assert twin["amendments"], "DEMO-STD-001 has a recorded amendment"

    amendment = twin["amendments"][0]
    assert amendment["diff"]
    assert amendment["potential_impact"].startswith("Potential impact")
    assert amendment["changed_numbers"]


def test_missing_product_returns_404(client):
    assert client.get("/api/products/prd-nope").status_code == 404
    assert client.get("/api/products/prd-nope/compliance").status_code == 404


# ---------------------------------------------------------------------------
# Consumer flow
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", ["DEMO-STD-004", "demo std 4", "DEMO-STD-4"])
def test_consumer_lookup_accepts_code_variants(client, query):
    body = client.post("/api/consumer/lookup", json={"query": query}).json()
    assert body["found"] is True
    assert body["standard"]["id"] == "DEMO-STD-004"
    assert body["what_is_it"]
    assert body["what_it_covers"]
    assert body["why_it_matters"]
    assert body["sources"]


def test_consumer_lookup_for_an_unknown_code_does_not_invent_an_answer(client):
    body = client.post("/api/consumer/lookup", json={"query": "IS 99999"}).json()

    assert body["found"] is False
    assert "is present in the current corpus" in body["message"]
    assert "will not guess" in body["message"]
    assert body["suggestions"], "the user should be offered what is actually available"


def test_consumer_regulatory_line_comes_from_records(client):
    mandatory = client.post("/api/consumer/lookup", json={"query": "DEMO-STD-001"}).json()
    unverifiable = client.post("/api/consumer/lookup", json={"query": "DEMO-STD-002"}).json()

    assert mandatory["regulatory"]["status"] == "MANDATORY"
    assert unverifiable["regulatory"]["status"] == "UNABLE_TO_VERIFY"


def test_consumer_get_endpoint_matches_post(client):
    body = client.get("/api/consumer/standard/DEMO-STD-005").json()
    assert body["found"] is True


def test_consumer_lookup_ranks_suggestions_by_product_description(client):
    """A consumer without a code should get suggestions ranked on what they typed,
    not an arbitrary list of whatever loaded first."""
    body = client.post("/api/consumer/lookup", json={"query": "pressure cooker"}).json()

    assert body["found"] is False
    assert body["suggestions"][0]["id"] == "DEMO-STD-004"
    assert "closest matches" in body["message"].lower()


def test_consumer_lookup_with_no_match_falls_back_to_a_plain_list(client):
    """A query that matches nothing still returns something to browse, not a dead end."""
    body = client.post("/api/consumer/lookup", json={"query": "zzz-no-such-thing-99999"}).json()

    assert body["found"] is False
    assert body["suggestions"], "an empty match must still offer a way forward"
    assert "closest matches" not in body["message"].lower()


def test_consumer_categories_reflect_the_real_corpus(client):
    body = client.get("/api/consumer/categories").json()
    categories = {c["key"]: c for c in body["categories"]}

    # Every category shown has at least one standard, and counts are real.
    assert categories, "the demo corpus has categorised standards"
    for entry in categories.values():
        assert entry["standard_count"] >= 1
        assert entry["label"]

    # Kitchenware is the real corpus category for DEMO-STD-004; the taxonomy's
    # "pressure-cooker" key must never leak into the browsable list as its own
    # category since no standard is actually filed under that literal key.
    assert "kitchenware" in categories
    assert "pressure-cooker" not in categories

    # "electrical-appliance" holds both a water heater and a general
    # appliance-safety standard, so it must keep its general label rather
    # than being narrowed to whichever taxonomy entry happened to map to it
    # first (e.g. "Electric Water Heater").
    assert categories["electrical-appliance"]["standard_count"] == 2
    assert categories["electrical-appliance"]["label"] == "Electrical Appliance (general)"


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------

def test_rag_answers_from_clause_text_with_citations(client):
    body = client.post(
        "/api/rag/query",
        json={"question": "What is the temperature rise test procedure?", "standard_ids": ["DEMO-STD-001"]},
    ).json()

    assert body["answerable"] is True
    assert body["citations"]
    assert body["evidence_shield"]["verified"] is True
    assert body["llm_used"] is False
    assert all(c["standard_id"] == "DEMO-STD-001" for c in body["citations"])


def test_rag_scopes_to_the_standard_named_in_the_question(client):
    body = client.post("/api/rag/query", json={"question": "What does DEMO-STD-007 cover?"}).json()
    assert body["standards_searched"] == ["DEMO-STD-007"]


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Is DEMO-STD-001 mandatory?", "MANDATORY_STATUS"),
        ("What tests are required?", "TEST_REQUIREMENT"),
        ("Has DEMO-STD-001 been amended?", "AMENDMENT_QUERY"),
        ("Do I need a BIS licence?", "CERTIFICATION_QUERY"),
    ],
)
def test_query_classification(client, question, expected):
    body = client.post("/api/rag/query", json={"question": question}).json()
    assert body["query_type"] == expected


def test_rag_abstains_when_the_requested_standards_do_not_exist(client):
    """An explicit filter must not be silently widened to the whole corpus."""
    body = client.post(
        "/api/rag/query",
        json={"question": "What tests are required?", "standard_ids": ["NOT-A-STANDARD"]},
    ).json()

    assert body["answerable"] is False
    assert body["citations"] == []
    assert body["claims"] == []
    assert body["standards_searched"] == []
    assert "are present in this corpus" in body["answer"]


def test_trust_endpoint_describes_enforced_controls(client):
    body = client.get("/api/trust").json()

    assert body["dataset"]["status"] == "demo"
    assert body["dataset"]["standards_without_regulatory_record"] > 0
    names = {c["name"] for c in body["controls"]}
    assert {"Closed candidate list", "Evidence Shield", "Structured regulatory status"} <= names
    assert body["retrieval"]["strategy"] == "two-stage hybrid"
