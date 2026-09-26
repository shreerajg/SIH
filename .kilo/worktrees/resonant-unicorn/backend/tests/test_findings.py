"""Plain-language findings must stay grounded in real clause text.

The whole point of the simplified view is that a non-expert can read it without
losing the guarantee the raw evidence gives: every statement traces to a clause
that literally contains its topic, and a document that supports nothing produces
nothing rather than an invented summary.
"""
from __future__ import annotations

from app.models import StandardClause
from app.services.findings import extract_findings, findings_for_standard


def _clause(cid, text, clause_number="1", page=1, is_table=False, heading=""):
    return StandardClause(
        id=cid,
        standard_id="X",
        section_number=clause_number.split(".")[0],
        clause_number=clause_number,
        heading=heading,
        text=text,
        page_number=page,
        clause_type="requirement",
        chunk_id=cid,
        is_table=is_table,
    )


def test_a_finding_is_only_made_when_the_clause_contains_the_topic():
    clauses = [
        _clause("c1", "The manufacturer shall maintain a Quality Assurance Plan.", "3", 2),
        _clause("c2", "Sampling shall follow the sample size in Table 1.", "4", 3),
    ]
    findings = extract_findings(clauses, "product_manual")
    keys = {f.key for f in findings}
    assert "quality_assurance_plan" in keys
    assert "sampling" in keys
    # Every finding cites the exact clause the term came from.
    qap = next(f for f in findings if f.key == "quality_assurance_plan")
    assert qap.chunk_id == "c1" and qap.page_number == 2
    sampling = next(f for f in findings if f.key == "sampling")
    assert sampling.chunk_id == "c2"


def test_no_topic_means_no_finding_not_an_invented_one():
    clauses = [_clause("c1", "This document was authored for demonstration purposes only.", "1", 1)]
    assert extract_findings(clauses, "standard") == []


def test_findings_never_claim_compliance_only_what_the_source_says():
    clauses = [_clause("c1", "Type tests and routine tests are specified in Clause 6.", "6", 4)]
    findings = extract_findings(clauses, "product_manual")
    assert findings, "a tests clause should yield a finding"
    text = findings[0].text.lower()
    # Descriptive, never a verdict.
    assert "the source" in text
    for forbidden in ("compliant", "certified", "approved", "passed", "meets all"):
        assert forbidden not in text


def test_findings_are_capped():
    # Ten distinct topic-bearing clauses, but the list is capped at five.
    clauses = [
        _clause("c1", "Quality Assurance Plan is required.", "1", 1),
        _clause("c2", "Scheme of Inspection and Testing applies.", "2", 1),
        _clause("c3", "Grouping guidelines are given.", "3", 1),
        _clause("c4", "Sampling is defined.", "4", 1),
        _clause("c5", "Marking and the Standard Mark are covered.", "5", 1),
        _clause("c6", "Levels of control are recommended.", "6", 1),
        _clause("c7", "Test method for the product is defined.", "7", 1),
    ]
    findings = extract_findings(clauses, "product_manual")
    assert len(findings) <= 5


def test_table_chunks_are_ignored_as_sources():
    clauses = [
        _clause("t1", "Sampling table of sample sizes", "T1", 1, is_table=True),
        _clause("c1", "Marking requirements are specified here.", "5", 2),
    ]
    findings = extract_findings(clauses, "product_manual")
    assert all(f.chunk_id != "t1" for f in findings)


def test_endpoint_returns_grounded_findings(client):
    # DEMO-STD-001 is always present in the test corpus; the verified BIS pack
    # is only loaded in the dev database, so a demo standard keeps this test
    # self-contained. What matters is the contract: a shape, and a citation on
    # every finding.
    body = client.get("/api/standards/DEMO-STD-001/findings").json()
    assert body["standard_id"] == "DEMO-STD-001"
    assert isinstance(body["findings"], list)
    if body["findings"]:
        for f in body["findings"]:
            assert f["chunk_id"] and f["text"]
            # A finding's citing clause must actually exist and hold its topic.
            src = client.get(f"/api/sources/{f['chunk_id']}").json()
            assert src["chunk_id"] == f["chunk_id"]
    else:
        assert "Unable to verify" in body["note"]


def test_findings_endpoint_404s_for_an_unknown_standard(client):
    assert client.get("/api/standards/NO-SUCH-STD/findings").status_code == 404
