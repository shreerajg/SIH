"""Corpus provenance, PDF/table ingestion, and corpus-mode enforcement.

These replace the manual PDF check done during development: the sample PDF in
``data/raw/samples/`` is ingested by the real pipeline here, so the
PDF -> text -> clause -> table -> database -> vector path is covered by CI
rather than by having a stray test document sit in the production corpus.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import REPO_ROOT
from app.core.constants import CorpusMode
from app.db.mongo import session_scope
from app.db.repositories import clauses as clauses_repo
from app.db.repositories import standards as standards_repo
from app.ingestion.manifest import (
    load_manifest,
    looks_like_demo_identifier,
    validate_entry,
)
from app.ingestion.parser import extract_pdf_tables, parse_document
from app.ingestion.pipeline import ingest_documents
from app.models import Standard, StandardClause
from app.services import corpus

SAMPLE_PDF = REPO_ROOT / "data" / "raw" / "samples" / "SAMPLE-PDF-001.pdf"


# ---------------------------------------------------------------------------
# Manifest validation - the rule that keeps synthetic data out of "verified"
# ---------------------------------------------------------------------------

def test_shipped_manifest_validates_cleanly():
    report = load_manifest()
    assert report.entries, "the manifest should describe the shipped corpus"
    assert report.errors == [], f"manifest validation errors: {report.errors}"
    assert report.demo_count + report.verified_count == len(report.entries)


def test_no_official_document_binary_ships_with_the_repository():
    """The manifest may describe official BIS documents, but the files
    themselves are downloaded on demand and must never be committed here.

    This is the rule the old ``verified_count == 0`` assertion was really
    protecting: it stopped being about *entries* the moment the verified pack
    was registered, but it is still exactly right about *files*.
    """
    import subprocess

    report = load_manifest()
    verified = [e for e in report.entries if e.is_verified]
    if not verified:
        pytest.skip("no verified documents registered in this checkout")

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    tracked_set = {line.strip() for line in tracked}

    for entry in verified:
        assert entry.local_path not in tracked_set, (
            f"{entry.document_id}: the official document {entry.local_path} is committed to "
            "the repository. Official BIS documents are fetched from bis.gov.in on demand, "
            "not redistributed from here."
        )


def test_every_verified_entry_carries_real_provenance():
    """A verified entry must be traceable to an official source, and can never
    wear a synthetic identifier."""
    report = load_manifest()
    for entry in report.entries:
        if not entry.is_verified:
            continue
        assert entry.source_url, f"{entry.document_id}: verified without a source_url"
        assert entry.source_url.startswith("https://"), entry.document_id
        assert "bis.gov.in" in entry.source_url, (
            f"{entry.document_id}: verified source is not an official BIS URL"
        )
        assert entry.retrieved_at, f"{entry.document_id}: verified without retrieved_at"
        assert entry.is_demo is False
        assert not entry.document_id.upper().startswith(("DEMO-", "SAMPLE-", "TEST-"))


def test_a_product_manual_is_not_recorded_as_a_standard():
    """The corpus holds BIS Product Manuals and QCOs, not full Indian Standard
    texts. Their document_type must say so, or a manual's text could be read as
    standard clause text."""
    report = load_manifest()
    verified = [e for e in report.entries if e.is_verified]
    if not verified:
        pytest.skip("no verified documents registered in this checkout")
    for entry in verified:
        assert entry.document_type in {
            "product_manual", "qco", "amendment", "regulatory", "gazette",
            "scheme_of_inspection_and_testing",
            # Official BIS hallmarking material: a scheme brief, FAQs and
            # jeweller / A&H centre guidance. Still not an Indian Standard.
            "hallmarking",
        }, (
            f"{entry.document_id} is typed '{entry.document_type}'. No document in the "
            "verified pack is a full Indian Standard, so none may be typed 'standard'."
        )


def test_a_demo_identifier_can_never_be_marked_verified():
    entry, errors = validate_entry(
        {
            "document_id": "DEMO-STD-001",
            "standard_id": "DEMO-STD-001",
            "is_number": "DEMO-STD-001",
            "is_verified": True,
            "is_demo": False,
            "source_url": "https://example.gov.in/doc.pdf",
            "retrieved_at": "2026-01-01",
        }
    )
    assert errors, "claiming a DEMO-* identifier is verified must be rejected"
    assert any("cannot be marked verified" in e for e in errors)
    # The entry is forced back to demo rather than trusted.
    assert entry.is_verified is False
    assert entry.is_demo is True


def test_verified_entry_requires_a_source_url_and_retrieval_date():
    _, errors = validate_entry(
        {
            "document_id": "IS-302",
            "standard_id": "IS-302",
            "is_number": "IS 302",
            "is_verified": True,
            "is_demo": False,
        }
    )
    assert any("source_url" in e for e in errors)
    assert any("retrieved_at" in e for e in errors)


def test_a_synthetic_record_must_use_a_demo_prefix():
    _, errors = validate_entry(
        {
            "document_id": "IS-4321",
            "standard_id": "IS-4321",
            "is_number": "IS 4321",
            "is_verified": False,
            "is_demo": True,
        }
    )
    assert any("DEMO-* prefix" in e for e in errors), (
        "a synthetic record wearing a real-looking IS number is exactly the "
        "failure the manifest exists to prevent"
    )


@pytest.mark.parametrize(
    "value,expected",
    [("DEMO-STD-001", True), ("SAMPLE-PDF-001", True), ("IS 302", False), ("", False)],
)
def test_demo_identifier_detection(value, expected):
    assert looks_like_demo_identifier(value) is expected


# ---------------------------------------------------------------------------
# PDF + table ingestion
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample PDF not present")
def test_pdf_parses_into_clauses_with_page_numbers():
    doc = parse_document(SAMPLE_PDF)

    assert doc.clauses, "the PDF text layer should yield clauses"
    assert all(c.page_number == 1 for c in doc.clauses), "page numbers must be captured"
    numbers = {c.clause_number for c in doc.clauses}
    assert "1.1" in numbers and "6.1.1" in numbers
    by_number = {c.clause_number: c for c in doc.clauses}
    assert by_number["1.1"].clause_type == "scope"
    assert by_number["6.1.1"].clause_type == "test"


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample PDF not present")
def test_tables_are_extracted_with_structure_and_searchable_text():
    tables, warnings = extract_pdf_tables(SAMPLE_PDF)

    assert tables, f"expected a table in the sample PDF (warnings: {warnings})"
    table = tables[0]
    assert table.headers == ["Part", "Metal (K)", "Moulded (K)"]
    assert len(table.rows) == 2
    assert table.page_number == 1
    assert "Table 2" in table.caption

    # Both representations are kept: structure for display, flattened for search.
    searchable = table.searchable_text
    assert "Metal (K): 30" in searchable, "numeric limits must survive into search text"
    assert "Handles held continuously" in searchable


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample PDF not present")
def test_table_extraction_failure_is_a_warning_not_a_crash(tmp_path):
    """A file that is not a usable PDF must not take the pipeline down."""
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 this is not a real pdf")

    tables, warnings = extract_pdf_tables(broken)
    assert tables == []
    assert warnings, "the failure should be reported rather than silently swallowed"


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample PDF not present")
def test_full_pdf_ingestion_persists_clauses_tables_and_provenance():
    """PDF -> parse -> table -> database -> vector index, through the real pipeline."""
    db = session_scope()
    try:
        report = ingest_documents(db, paths=[SAMPLE_PDF])

        assert report.documents == 1
        assert report.clauses >= 3
        assert report.tables == 1, "the table should be persisted as its own chunk"
        assert report.verified_documents == 0
        assert report.demo_documents == 1

        standard = standards_repo(db).get("SAMPLE-PDF-001")
        assert standard is not None
        # Provenance came from the manifest, not from the (header-less) PDF.
        assert standard.is_demo is True
        assert standard.is_verified is False
        assert standard.document_id == "SAMPLE-PDF-001"

        clauses = clauses_repo(db).find({"standard_id": "SAMPLE-PDF-001"})
        table_chunks = [c for c in clauses if c.is_table]
        assert len(table_chunks) == 1
        payload = table_chunks[0].table_json
        assert payload["headers"] == ["Part", "Metal (K)", "Moulded (K)"]
        assert payload["rows"][0][1] == "30"
        assert table_chunks[0].page_number == 1
    finally:
        pass  # PyMongo pools connections on the client


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample PDF not present")
def test_table_content_is_retrievable(client):
    """A number that only exists inside a table must be findable."""
    db = session_scope()
    try:
        ingest_documents(db, paths=[SAMPLE_PDF])
    finally:
        pass  # PyMongo pools connections on the client

    body = client.post(
        "/api/rag/query",
        json={
            "question": "What is the temperature rise limit for handles held continuously?",
            "standard_ids": ["SAMPLE-PDF-001"],
        },
    ).json()

    chunk_ids = set(body["evidence_shield"]["retrieved_chunk_ids"])
    assert any(cid.endswith("::t1") for cid in chunk_ids), (
        "the table chunk should be retrievable for a question about its contents"
    )


# ---------------------------------------------------------------------------
# Corpus mode enforcement
# ---------------------------------------------------------------------------

def test_demo_mode_returns_only_demo_documents(monkeypatch):
    monkeypatch.setattr(corpus.settings, "corpus_mode", "DEMO")
    db = session_scope()
    try:
        assert corpus.current_mode() is CorpusMode.DEMO
        ids = corpus.allowed_standard_ids(db)
        assert ids, "the demo corpus should be usable in DEMO mode"
        rows = standards_repo(db).find({"_id": {"$in": list(ids)}})
        assert all(s.is_demo for s in rows)
    finally:
        pass  # PyMongo pools connections on the client


def test_verified_mode_excludes_demo_documents(monkeypatch):
    """With no official documents loaded, VERIFIED mode must return nothing.

    Falling back to synthetic data here would be the single worst failure the
    platform could have: a demo record presented as an official standard.
    """
    monkeypatch.setattr(corpus.settings, "corpus_mode", "VERIFIED")
    db = session_scope()
    try:
        assert corpus.current_mode() is CorpusMode.VERIFIED
        assert corpus.allowed_standard_ids(db) == []

        state = corpus.status(db)
        assert state.starved is True
        assert "no official documents are loaded" in state.message
        assert corpus.starvation_note(db)
    finally:
        pass  # PyMongo pools connections on the client


def test_mixed_mode_allows_both_and_prefers_verified(monkeypatch):
    monkeypatch.setattr(corpus.settings, "corpus_mode", "MIXED")
    db = session_scope()
    try:
        assert corpus.current_mode() is CorpusMode.MIXED
        assert corpus.allowed_standard_ids(db), "MIXED must include the demo corpus"

        demo = standards_repo(db).find_one({"is_demo": True})
        assert corpus.ranking_bonus(demo) == 0.0

        # A verified document would be preferred in ranking.
        demo.is_verified = True
        assert corpus.ranking_bonus(demo) == corpus.VERIFIED_PREFERENCE_BONUS
        demo.is_verified = False
    finally:
        pass  # PyMongo pools connections on the client


def test_retrieval_honours_the_corpus_mode(monkeypatch, db):
    """The mode narrows the whole application, not just one endpoint."""
    from app.search.hybrid import get_retriever

    retriever = get_retriever()

    monkeypatch.setattr(corpus.settings, "corpus_mode", "MIXED")
    mixed = retriever.discover_standards(db, "domestic electric storage water heater")
    assert mixed, "MIXED mode should find the demo water heater standard"

    monkeypatch.setattr(corpus.settings, "corpus_mode", "VERIFIED")
    verified = retriever.discover_standards(db, "domestic electric storage water heater")
    assert verified == [], "VERIFIED mode must not fall back to demo documents"

    clauses = retriever.retrieve_clauses(db, "temperature rise", ["DEMO-STD-001"])
    assert clauses == [], "clause retrieval must respect the mode too"


def test_unknown_corpus_mode_falls_back_to_mixed(monkeypatch):
    monkeypatch.setattr(corpus.settings, "corpus_mode", "NONSENSE")
    assert corpus.current_mode() is CorpusMode.MIXED


def test_corpus_status_reports_live_counts():
    db = session_scope()
    try:
        state = corpus.status(db, CorpusMode.MIXED)
        payload = state.as_dict()
        assert payload["label"] == "Mixed Corpus"
        assert payload["demo_standards"] >= 8
        assert payload["verified_standards"] == 0
        assert payload["usable_standards"] == payload["demo_standards"]
    finally:
        pass  # PyMongo pools connections on the client


# ---------------------------------------------------------------------------
# Content mode: what the corpus holds, as distinct from what policy allows
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "verified,demo,expected",
    [
        (0, 8, "DEMO"),
        (9, 0, "VERIFIED"),
        (9, 8, "MIXED"),
        (0, 0, None),
    ],
)
def test_content_mode_describes_what_is_actually_loaded(verified, demo, expected):
    """The configured CORPUS_MODE is a policy control, not a description of the
    corpus. A corpus of nothing but synthetic documents must not describe
    itself as "Mixed" merely because MIXED is the default setting.
    """
    mode = corpus.content_mode(verified, demo)
    assert (mode.value if mode else None) == expected


def test_content_mode_is_reported_separately_from_the_policy_mode(monkeypatch):
    """Both facts are exposed, and they are allowed to disagree."""
    monkeypatch.setattr(corpus.settings, "corpus_mode", "MIXED")
    db = session_scope()
    try:
        payload = corpus.status(db).as_dict()
        # Policy stays whatever it is configured to be...
        assert payload["mode"] == "MIXED"
        # ...while the content label reflects the documents on hand. The test
        # corpus ingests only the synthetic documents.
        assert payload["content_mode"] == "DEMO"
        assert payload["content_label"] == "Demo Corpus"
    finally:
        pass  # PyMongo pools connections on the client


# ---------------------------------------------------------------------------
# Bilingual gazette handling: one language in the index, not two
# ---------------------------------------------------------------------------

def test_hindi_rendering_of_a_bilingual_order_is_not_indexed():
    """BIS gazette orders are published in Hindi and English, and the parser
    emits both as separate chunks. Indexing both stores one document twice and
    quotes the Hindi rendering back to an English-speaking reader."""
    from app.core.text_utils import is_predominantly_devanagari

    hindi = "संक्षिप्त शीर्षक और प्रारंभ-(1) इस आदेश का संक्षिप्त नाम"
    english = "(2) It shall come into force with effect from 01st June 2021."
    assert is_predominantly_devanagari(hindi) is True
    assert is_predominantly_devanagari(english) is False


def test_a_mixed_chunk_keeps_its_english_instead_of_being_dropped():
    """A bilingual heading carries both scripts on one line. Dropping the whole
    chunk would throw the English away, so the Hindi run is stripped instead."""
    from app.core.text_utils import strip_devanagari

    mixed = "लाइसेंस का दायरा / Scope of the Licence : Licence is granted to use Standard Mark"
    cleaned = strip_devanagari(mixed)
    assert cleaned.startswith("Scope of the Licence")
    assert not any("ऀ" <= c <= "ॿ" for c in cleaned)


def test_stripping_never_reduces_a_hindi_only_chunk_to_punctuation():
    from app.core.text_utils import strip_devanagari

    hindi_only = "संक्षिप्त शीर्षक और प्रारंभ"
    assert strip_devanagari(hindi_only) == hindi_only


def test_the_indexed_corpus_carries_no_devanagari():
    """The end state: with INGEST_ENGLISH_ONLY on, nothing in the clause index
    is in a script the reader did not ask for."""
    from app.core.text_utils import devanagari_ratio

    db = session_scope()
    try:
        offending = [
            c.chunk_id for c in clauses_repo(db).find()
            if devanagari_ratio(c.text) > 0
        ]
        assert offending == [], f"non-English text indexed in: {offending[:5]}"
    finally:
        pass  # PyMongo pools connections on the client
