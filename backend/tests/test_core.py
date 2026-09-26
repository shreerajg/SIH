"""Deterministic building blocks: IS-code handling, extraction, parsing, rules."""
from __future__ import annotations

import pytest

from app.compliance.gap_analyzer import evaluate_rule, match_evidence
from app.core.constants import ComplianceStatus
from app.core.text_utils import (
    display_is_number,
    extract_is_numbers,
    extract_numeric_attributes,
    normalize_is_number,
)
from app.ingestion.parser import parse_document
from app.models import ComplianceRequirement, ProductEvidence
from app.services.amendments import changed_numbers, compute_diff
from app.services.taxonomy import detect_category


# ---------------------------------------------------------------------------
# IS code normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("IS 302", "IS-302"),
        ("IS302", "IS-302"),
        ("is-302", "IS-302"),
        ("  is 302  ", "IS-302"),
        ("IS 302 : 1979", "IS-302"),
        ("IS 302 (Part 2)", "IS-302-P2"),
        ("IS 302 (Part 2) Sec 1", "IS-302-P2-S1"),
        ("Indian Standard 4151", "IS-4151"),
        ("DEMO-STD-001", "DEMO-STD-001"),
        ("demo std 1", "DEMO-STD-001"),
    ],
)
def test_is_number_normalisation(raw, expected):
    assert normalize_is_number(raw) == expected


@pytest.mark.parametrize("raw", ["", "helmet", "water heater", "a product"])
def test_non_standard_input_normalises_to_empty(raw):
    assert normalize_is_number(raw) == ""


def test_display_round_trip():
    assert display_is_number(normalize_is_number("IS 302 (Part 2)")) == "IS 302 (Part 2)"
    assert display_is_number(normalize_is_number("IS302")) == "IS 302"


@pytest.mark.parametrize(
    "identifier",
    [
        "QCO-PRESSURE-COOKER-2020",
        "QCO-HELMET-2020",
        "QCO-WATER-HEATING-2025",
        "QCO-TRANSITION-FACILITATION-2026",
        "BIS-SCHEME-I-INDEX",
    ],
)
def test_a_non_standard_document_id_is_never_dressed_up_as_an_is_number(identifier):
    """The corpus holds Quality Control Orders and gazette notifications, which
    are not Indian Standards. Formatting their identifiers as IS numbers
    invents a standard that does not exist - 'QCO-PRESSURE-COOKER-2020' once
    rendered as 'IS QCO (Part RESSURE)'.
    """
    rendered = display_is_number(identifier)
    assert rendered == identifier
    assert not rendered.startswith("IS "), (
        f"{identifier} was presented as the IS number {rendered!r}"
    )


def test_extract_is_numbers_from_free_text():
    found = extract_is_numbers("Refer to IS 302 (Part 2) and also DEMO-STD-004 for details.")
    assert found == ["IS-302-P2", "DEMO-STD-004"]


# ---------------------------------------------------------------------------
# Quantity extraction
# ---------------------------------------------------------------------------

def test_numeric_attribute_extraction():
    attrs = extract_numeric_attributes(
        "15 litre domestic electric storage water heater at 230 V drawing 2000 W"
    )
    assert attrs["capacity_litres"] == 15.0
    assert attrs["voltage_v"] == 230.0
    assert attrs["power_w"] == 2000.0


def test_kilowatt_is_converted_to_watts():
    assert extract_numeric_attributes("a 2.5 kW heater")["power_w"] == 2500.0


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("15 litre electric storage water heater", "water-heater"),
        ("aluminium pressure cooker with vent weight", "pressure-cooker"),
        ("soft toys and rattles for children", "toy"),
        ("full face motorcycle helmet", "helmet"),
    ],
)
def test_category_detection(text, expected):
    assert detect_category(text)["category"] == expected


def test_category_detection_handles_plurals():
    assert detect_category("We manufacture heaters.")["category"] == "water-heater"


def test_unrecognisable_product_has_no_category():
    assert detect_category("We make widgets and sprockets")["category"] == ""


# ---------------------------------------------------------------------------
# Clause parsing
# ---------------------------------------------------------------------------

def test_parser_produces_clause_structure_with_lineage():
    from app.core.config import REPO_ROOT

    doc = parse_document(REPO_ROOT / "data" / "raw" / "standards" / "DEMO-STD-001.txt")

    assert doc.metadata["standard-id"] == "DEMO-STD-001"
    assert len(doc.clauses) > 30

    by_number = {c.clause_number: c for c in doc.clauses}
    assert "6.2.1" in by_number
    # A sub-clause inherits the meaning of its parents.
    assert by_number["6.2.1"].clause_type == "test"
    assert "Temperature rise test" in by_number["6.2.1"].breadcrumb
    assert by_number["1.1"].clause_type == "scope"
    assert by_number["7.1"].clause_type == "marking"


def test_parser_chunks_stay_within_the_size_budget():
    from app.core.config import REPO_ROOT
    from app.ingestion.parser import MAX_CHUNK_CHARS

    doc = parse_document(REPO_ROOT / "data" / "raw" / "standards" / "DEMO-STD-002.txt")
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in doc.clauses)


# ---------------------------------------------------------------------------
# Requirement rule evaluation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "rule,attributes,expected",
    [
        ({"attribute": "t", "operator": "lte", "value": 75}, {"t": 72}, True),
        ({"attribute": "t", "operator": "lte", "value": 75}, {"t": 80}, False),
        ({"attribute": "t", "operator": "gte", "value": 2}, {"t": 2}, True),
        ({"attribute": "t", "operator": "between", "value": [200, 250]}, {"t": 230}, True),
        ({"attribute": "t", "operator": "between", "value": [200, 250]}, {"t": 415}, False),
        ({"attribute": "t", "operator": "is_true"}, {"t": True}, True),
        ({"attribute": "t", "operator": "is_true"}, {"t": "No"}, False),
        ({"attribute": "t", "operator": "in", "value": ["manual", "tool"]}, {"t": "Manual"}, True),
        ({"attribute": "t", "operator": "in", "value": ["manual"]}, {"t": "automatic"}, False),
        ({"attribute": "t", "operator": "not_empty"}, {"t": "steel"}, True),
    ],
)
def test_rule_evaluation(rule, attributes, expected):
    passed, explanation = evaluate_rule(rule, attributes)
    assert passed is expected
    assert explanation


def test_undeclared_attribute_is_unknown_not_a_pass():
    passed, explanation = evaluate_rule(
        {"attribute": "voltage_v", "operator": "lte", "value": 250}, {}
    )
    assert passed is None
    assert "not been declared" in explanation


def test_non_numeric_value_against_a_numeric_limit_is_unknown():
    passed, _ = evaluate_rule({"attribute": "t", "operator": "lte", "value": 75}, {"t": "warm"})
    assert passed is None


# ---------------------------------------------------------------------------
# Evidence matching
# ---------------------------------------------------------------------------

def _requirement(evidence_type: str, keywords):
    return ComplianceRequirement(
        id="r1",
        standard_id="DEMO-STD-001",
        requirement_code="R1",
        category="testing",
        requirement_text="x",
        evidence_type=evidence_type,
        severity="major",
        check_rule_json={"match_keywords": keywords},
        applies_when_json={},
        source_clause_number="6.2.1",
    )


def test_evidence_matched_by_keyword_and_type():
    requirement = _requirement("test_report", ["temperature rise"])
    evidence = [
        ProductEvidence(id="e1", product_id="p", evidence_type="test_report", name="Drop test report", value=""),
        ProductEvidence(id="e2", product_id="p", evidence_type="test_report", name="Temperature rise test report", value=""),
    ]
    assert match_evidence(requirement, evidence).id == "e2"


def test_evidence_of_the_wrong_type_does_not_match():
    requirement = _requirement("test_report", ["temperature rise"])
    evidence = [
        ProductEvidence(id="e1", product_id="p", evidence_type="marking_artwork",
                        name="Temperature rise label", value="")
    ]
    assert match_evidence(requirement, evidence) is None


def test_evidence_can_declare_the_requirements_it_covers():
    requirement = _requirement("test_report", [])
    evidence = [
        ProductEvidence(id="e1", product_id="p", evidence_type="test_report", name="Combined report",
                        value="", metadata_json={"covers": ["R1"]})
    ]
    assert match_evidence(requirement, evidence).id == "e1"


# ---------------------------------------------------------------------------
# Amendment diffing
# ---------------------------------------------------------------------------

def test_diff_marks_only_the_changed_words():
    diff = compute_diff("shall not exceed 75 degC.", "shall not exceed 70 degC.")
    ops = {segment.op for segment in diff}
    assert ops == {"equal", "delete", "insert"}
    assert any(s.op == "delete" and "75" in s.text for s in diff)
    assert any(s.op == "insert" and "70" in s.text for s in diff)


def test_changed_numbers_detects_direction():
    changes = changed_numbers("not exceed 75 degC", "not exceed 70 degC")
    assert changes[0]["old"] == "75"
    assert changes[0]["new"] == "70"
    assert changes[0]["direction"] == "tightened"


def test_relaxed_limits_are_labelled_relaxed():
    changes = changed_numbers("at least 200 mm", "at least 220 mm")
    assert changes[0]["direction"] == "relaxed"


# ---------------------------------------------------------------------------
# Readiness maths
# ---------------------------------------------------------------------------

def test_readiness_excludes_not_applicable_from_the_denominator():
    from app.compliance.gap_analyzer import build_readiness
    from app.schemas.models import ClauseRef, RequirementResult

    def make(status: ComplianceStatus, code: str) -> RequirementResult:
        return RequirementResult(
            requirement_id=code, requirement_code=code, requirement_text="x",
            category="safety", severity="major", evidence_type="document",
            status=status, reason="", source=ClauseRef(
                chunk_id=f"c{code}", standard_id="s", is_number="s", display_number="s",
                clause_number="1", excerpt="",
            ),
        )

    results = [
        make(ComplianceStatus.SUPPORTED, "a"),
        make(ComplianceStatus.SUPPORTED, "b"),
        make(ComplianceStatus.TEST_REQUIRED, "c"),
        make(ComplianceStatus.NOT_APPLICABLE, "d"),
    ]
    readiness = build_readiness(results)

    assert readiness.total_requirements == 4
    assert readiness.assessable == 3
    assert readiness.supported == 2
    assert readiness.percentage == 67
    assert "not an official BIS certification result" in readiness.tooltip
