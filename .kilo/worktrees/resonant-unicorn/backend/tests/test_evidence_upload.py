"""Product evidence upload, extraction and matching.

The rule this file defends: **a document existing is not a requirement being
satisfied.** The platform may report what a document says; it may never turn
that into a compliance conclusion of its own.
"""
from __future__ import annotations

import io

import pytest

from app.core.constants import UploadCategory
from app.models import ComplianceRequirement, ProductEvidence
from app.services.evidence import (
    EvidenceAssessment,
    EvidenceMatchingService,
    EvidenceUploadError,
    extract_fields,
    _safe_suffix,
)

REPORT_TEXT = """
Test Report No: TR-2026-0413
Model: EWH-15D
Tested by: National Test House, Mumbai
Date: 2026-04-13
Temperature rise test carried out in accordance with Clause 6.2.1.
Rated voltage: 230 V
Rated power: 2000 W
Handle temperature rise = 28 K
Result: PASS
"""


@pytest.fixture()
def product(client):
    return client.post(
        "/api/products/analyze",
        json={"description": "We manufacture a 15 litre domestic electric storage water "
                             "heater operating at 230 V."},
    ).json()["product"]


def _upload(client, product_id, content: bytes, filename: str, category: str,
            content_type: str = "text/plain", name: str = ""):
    return client.post(
        f"/api/products/{product_id}/evidence/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
        data={"category": category, "name": name},
    )


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_extraction_reads_structured_fields_from_a_report():
    fields = extract_fields(REPORT_TEXT)
    assert fields.model == "EWH-15D"
    assert fields.report_number == "TR-2026-0413"
    assert "National Test House" in (fields.laboratory or "")
    assert fields.issued_on == "2026-04-13"
    assert "temperature rise" in fields.test_names
    assert fields.result == "pass"
    assert fields.ratings["voltage_v"] == 230.0
    assert fields.ratings["power_w"] == 2000.0
    labels = {r["label"] for r in fields.numeric_results}
    assert "handle temperature rise" in labels


def test_extraction_of_empty_text_is_empty_not_invented():
    fields = extract_fields("")
    assert fields.model is None
    assert fields.result is None
    assert fields.test_names == []
    assert fields.numeric_results == []


def test_only_known_test_names_are_extracted():
    fields = extract_fields("We performed a flux capacitor alignment test. Result: pass.")
    assert fields.test_names == [], "extraction stays inside a closed vocabulary"
    assert fields.result == "pass"


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------

def test_upload_stores_and_extracts(client, product):
    response = _upload(
        client, product["id"], REPORT_TEXT.encode(), "report.txt",
        UploadCategory.TEST_REPORT.value, name="Temperature rise test report",
    )
    assert response.status_code == 201
    body = response.json()

    assert body["evidence_type"] == "test_report"
    assert body["upload_category"] == "test_report"
    assert body["extraction_status"] == "extracted"
    assert body["extracted_fields"]["model"] == "EWH-15D"
    assert body["has_text"] is True
    # The note must be explicit that reading is not judging.
    assert "does not assess" in body["note"]


@pytest.mark.parametrize(
    "category,expected_type",
    [
        ("test_report", "test_report"),
        ("product_label", "marking_artwork"),
        ("certificate", "material_certificate"),
        ("datasheet", "document"),
    ],
)
def test_upload_category_maps_to_the_evidence_type(client, product, category, expected_type):
    body = _upload(
        client, product["id"], b"some evidence text", f"{category}.txt", category
    ).json()
    assert body["evidence_type"] == expected_type


def test_an_executable_is_refused(client, product):
    response = _upload(
        client, product["id"], b"MZ\x90\x00binary", "payload.exe",
        UploadCategory.OTHER.value, content_type="application/x-msdownload",
    )
    assert response.status_code == 400
    assert "PDF, TXT, PNG and JPEG" in response.json()["detail"]


def test_an_empty_file_is_refused(client, product):
    response = _upload(client, product["id"], b"", "empty.txt", UploadCategory.OTHER.value)
    assert response.status_code == 400


def test_magic_bytes_win_over_a_lying_extension():
    """A PDF renamed to .txt is still stored as a PDF."""
    assert _safe_suffix("evidence.txt", "text/plain", b"%PDF-1.7") == ".pdf"
    assert _safe_suffix("evidence.txt", "text/plain", b"plain text") == ".txt"


def test_a_crafted_filename_cannot_escape_the_upload_directory(client, product):
    body = _upload(
        client, product["id"], b"content", "../../../etc/passwd.txt",
        UploadCategory.OTHER.value,
    ).json()
    # The original name is recorded, but the stored path is generated.
    assert body["id"].startswith("ev-")
    assert "/" not in body["original_filename"] and "\\" not in body["original_filename"]


def test_upload_list_and_delete_round_trip(client, product):
    created = _upload(
        client, product["id"], REPORT_TEXT.encode(), "r.txt", UploadCategory.TEST_REPORT.value
    ).json()

    listing = client.get(f"/api/products/{product['id']}/evidence").json()
    assert any(e["id"] == created["id"] for e in listing["evidence"])
    assert "never be cited as a clause" in listing["note"]

    detail = client.get(
        f"/api/products/{product['id']}/evidence/{created['id']}"
    ).json()
    assert "Temperature rise test" in detail["extracted_text_preview"]

    assert client.delete(
        f"/api/products/{product['id']}/evidence/{created['id']}"
    ).status_code == 204
    assert client.get(
        f"/api/products/{product['id']}/evidence/{created['id']}"
    ).status_code == 404


# ---------------------------------------------------------------------------
# Matching: presence is not satisfaction
# ---------------------------------------------------------------------------

def _requirement(evidence_type: str, keywords, code="R1") -> ComplianceRequirement:
    return ComplianceRequirement(
        id=code, standard_id="DEMO-STD-001", requirement_code=code, category="testing",
        requirement_text="x", evidence_type=evidence_type, severity="major",
        check_rule_json={"match_keywords": keywords}, applies_when_json={},
        source_clause_number="6.2.1",
    )


def _evidence(**kwargs) -> ProductEvidence:
    defaults = dict(
        id="e1", product_id="p1", evidence_type="test_report", name="Report",
        value="", extracted_text="", extracted_fields_json={}, metadata_json={},
        original_filename="",
    )
    defaults.update(kwargs)
    return ProductEvidence(**defaults)


def test_matching_uses_extracted_text_not_just_the_filename():
    """A file called scan_001.pdf still matches on what is inside it."""
    requirement = _requirement("test_report", ["temperature rise"])
    item = _evidence(
        name="scan_001", original_filename="scan_001.pdf", extracted_text=REPORT_TEXT
    )
    assessment = EvidenceMatchingService().assess(requirement, [item])
    assert assessment.document_present is True
    assert assessment.evidence is item
    assert "temperature rise" in assessment.matched_terms


def test_document_presence_is_reported_without_a_verdict():
    requirement = _requirement("test_report", ["temperature rise"])
    item = _evidence(
        name="Temperature rise test report",
        extracted_fields_json={"result": "pass"},
        extracted_text=REPORT_TEXT,
    )
    assessment = EvidenceMatchingService().assess(requirement, [item])

    assert assessment.document_present is True
    assert assessment.stated_result == "pass"
    # The wording is attributed to the document, never adopted as a conclusion.
    assert "read from the file, not assessed by this platform" in assessment.note


def test_the_matcher_refuses_to_answer_whether_a_requirement_is_satisfied():
    assessment = EvidenceAssessment(evidence=None)
    with pytest.raises(NotImplementedError) as excinfo:
        _ = assessment.satisfied
    assert "not requirement satisfaction" in str(excinfo.value)


def test_evidence_of_the_wrong_kind_does_not_match():
    requirement = _requirement("test_report", ["temperature rise"])
    item = _evidence(evidence_type="marking_artwork", name="Temperature rise label")
    assert EvidenceMatchingService().assess(requirement, [item]).document_present is False


def test_a_report_with_no_stated_result_says_so():
    requirement = _requirement("test_report", ["temperature rise"])
    item = _evidence(name="Temperature rise measurements", extracted_fields_json={})
    assessment = EvidenceMatchingService().assess(requirement, [item])
    assert assessment.stated_result is None
    assert "does not determine whether the requirement is met" in assessment.note


# ---------------------------------------------------------------------------
# End to end through the gap analyzer
# ---------------------------------------------------------------------------

def test_an_uploaded_report_moves_a_requirement_off_test_required(client, product):
    client.post(f"/api/products/{product['id']}/discover-standards")

    before = client.post(
        f"/api/products/{product['id']}/compliance/analyze", json={"evidence": []}
    ).json()
    status_before = next(
        r["status"] for r in before["results"] if r["requirement_code"] == "D1-R11"
    )
    assert status_before == "TEST_REQUIRED"

    _upload(
        client, product["id"], REPORT_TEXT.encode(), "scan.txt",
        UploadCategory.TEST_REPORT.value, name="Lab report 413",
    )

    after = client.post(
        f"/api/products/{product['id']}/compliance/analyze", json={}
    ).json()
    result = next(r for r in after["results"] if r["requirement_code"] == "D1-R11")

    assert result["status"] == "SUPPORTED"
    assert result["matched_evidence"] == "Lab report 413"
    # Even when the document says PASS, the platform reports the wording as the
    # document's, not as its own finding.
    assert "not assessed by this platform" in result["reason"]
    assert "compliant" not in result["reason"].lower()


def test_declared_evidence_run_does_not_delete_an_upload(client, product):
    """Re-running the declared-evidence form must not wipe a file upload.

    Declared (checkbox) evidence is file-less; uploads are file-backed. A run
    that submits declared evidence should replace only the declared rows.
    """
    client.post(f"/api/products/{product['id']}/discover-standards")

    upload = _upload(
        client, product["id"], REPORT_TEXT.encode(), "scan.txt",
        UploadCategory.TEST_REPORT.value, name="Lab report 413",
    ).json()

    # A subsequent run that submits a *declared* piece of evidence.
    client.post(
        f"/api/products/{product['id']}/compliance/analyze",
        json={"evidence": [
            {"evidence_type": "document", "name": "User manual", "value": ""}
        ]},
    )

    listing = client.get(f"/api/products/{product['id']}/evidence").json()
    ids = {e["id"] for e in listing["evidence"]}
    assert upload["id"] in ids, "the uploaded file must survive a declared-evidence run"
