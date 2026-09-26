"""Plain-language, source-grounded findings for a document.

This turns the clause text of a standard or Product Manual into a handful of
short statements a non-expert can read — "the source defines a Quality
Assurance Plan", "the source specifies marking requirements" — without an LLM,
and without ever asserting anything the text does not contain.

The rule that keeps this honest: a finding is only produced when a clause
*literally contains* the topic term, and that clause is attached to the finding
as its citation (chunk id + page). The wording is deliberately descriptive
("the source defines / includes / specifies …") rather than a compliance
verdict — the platform reports what the document says, never that a requirement
is met. A document that matches no topic yields no findings, and the caller
says so rather than inventing any.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from pymongo import ASCENDING
from pymongo.database import Database

from app.db.repositories import clauses as clauses_repo
from app.models import StandardClause


@dataclass(frozen=True)
class Topic:
    key: str
    #: Any of these substrings, found in a clause, supports the finding.
    keywords: tuple
    #: The plain-language statement. Descriptive, never a compliance claim.
    statement: str


# A closed, ordered vocabulary. Order is priority: the most specific,
# certification-relevant topics come first so the capped list is the useful one.
TOPICS: List[Topic] = [
    Topic(
        "quality_assurance_plan",
        ("quality assurance plan", "quality assurance", "qap"),
        "The source sets out a Quality Assurance Plan for the manufacturer.",
    ),
    Topic(
        "inspection_and_testing",
        ("scheme of inspection and testing", "inspection and testing", "scheme of testing"),
        "The source includes a Scheme of Inspection and Testing for the product.",
    ),
    Topic(
        "grouping",
        ("grouping", "group of models", "grouping guidelines"),
        "The source defines how products are grouped for certification (for example, by capacity or type).",
    ),
    Topic(
        "sampling",
        ("sampling", "sample size", "number of samples", "sample quantity"),
        "The source defines sampling guidelines for certification.",
    ),
    Topic(
        "marking",
        ("standard mark", "marking", "labelling", "labeling", "bis mark"),
        "The source specifies marking and labelling requirements, including use of the BIS Standard Mark.",
    ),
    Topic(
        "levels_of_control",
        ("levels of control", "level of control", "control unit"),
        "The source defines recommended levels of control for the manufacturer.",
    ),
    Topic(
        "tests",
        ("test method", "type test", "acceptance test", "routine test", "testing"),
        "The source specifies tests to be performed on the product.",
    ),
    Topic(
        "materials",
        ("raw material", "material requirement", "grade of material"),
        "The source states requirements for the materials used in the product.",
    ),
]

MAX_FINDINGS = 5


@dataclass
class Finding:
    key: str
    text: str
    chunk_id: str
    clause_number: str
    page_number: int | None
    document_type: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "text": self.text,
            "chunk_id": self.chunk_id,
            "clause_number": self.clause_number,
            "page_number": self.page_number,
            "document_type": self.document_type,
        }


def _first_clause_matching(clauses: List[StandardClause], keywords: tuple) -> StandardClause | None:
    for clause in clauses:
        haystack = f"{clause.heading} {clause.text}".lower()
        for kw in keywords:
            # Word-ish boundary so "material" does not fire on "immaterial".
            if re.search(rf"(?<![a-z]){re.escape(kw)}", haystack):
                return clause
    return None


def extract_findings(clauses: List[StandardClause], document_type: str) -> List[Finding]:
    """Deterministic topic scan over a document's real clauses.

    Non-table clauses only; each surviving finding cites the first clause that
    literally contains the topic term.
    """
    body = [c for c in clauses if not c.is_table and (c.text or "").strip()]
    findings: List[Finding] = []
    for topic in TOPICS:
        clause = _first_clause_matching(body, topic.keywords)
        if clause is None:
            continue
        findings.append(
            Finding(
                key=topic.key,
                text=topic.statement,
                chunk_id=clause.chunk_id,
                clause_number=clause.clause_number,
                page_number=clause.page_number,
                document_type=document_type,
            )
        )
        if len(findings) >= MAX_FINDINGS:
            break
    return findings


def findings_for_standard(db: Database, standard_id: str, document_type: str) -> Dict[str, Any]:
    clauses = clauses_repo(db).find(
        {"standard_id": standard_id}, sort=[("_id", ASCENDING)]
    )
    findings = extract_findings(clauses, document_type)
    return {
        "standard_id": standard_id,
        "document_type": document_type,
        "findings": [f.as_dict() for f in findings],
        "note": (
            "Each statement is drawn from a clause that literally contains the topic; it reports "
            "what the source document says, not that any requirement has been met."
            if findings
            else "Unable to verify additional product-specific requirements from the currently "
            "loaded verified source."
        ),
    }
