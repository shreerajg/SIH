"""Structure-aware document parsing.

Standards are not prose - they are numbered clause trees. Cutting them every
500 characters destroys the one thing that makes a citation useful. This parser
walks the numbered structure instead:

    1 Scope
    4 Requirements
    4.1 Material
    4.1.1 The inner container shall ...

Each clause becomes one chunk carrying its full lineage (section, clause,
heading, page). Over-long clauses are split into parts that keep the parent
metadata so a citation still resolves to a real clause number.

Supported inputs: .txt / .md (demo corpus and pasted text) and .pdf (PyMuPDF),
so real BIS PDFs can be dropped into data/raw/standards without code changes.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 1400
MIN_CHUNK_CHARS = 40

#: "4.1.1 Heading text" / "4 Requirements"
CLAUSE_RE = re.compile(r"^\s{0,6}(\d{1,2}(?:\.\d{1,3}){0,4})[\.\)]?\s+(\S.*)$")
#: Lines that are page furniture in real BIS PDFs.
NOISE_RE = re.compile(
    r"^\s*(page\s+\d+(\s+of\s+\d+)?|bureau of indian standards|\d+\s*)\s*$", re.IGNORECASE
)

HEADER_KEYS = {
    "standard-id", "is-number", "title", "year", "version", "category",
    "source-type", "source-url", "verified", "mock", "keywords",
    "covered-areas", "plain-summary", "document-type",
}


@dataclass
class ParsedClause:
    clause_number: str
    section_number: str
    heading: str
    text: str
    page_number: Optional[int] = None
    clause_type: str = "requirement"
    part: int = 0
    total_parts: int = 1
    #: Headings of every ancestor clause, outermost first. This is what lets a
    #: bare sub-clause such as "6.2.1" be understood (and cited) as
    #: "Tests > Temperature rise test".
    heading_path: List[str] = field(default_factory=list)

    @property
    def display_heading(self) -> str:
        return self.heading or (self.heading_path[-1] if self.heading_path else "")

    @property
    def breadcrumb(self) -> str:
        parts = list(self.heading_path) + ([self.heading] if self.heading else [])
        return " > ".join(p for p in parts if p)


@dataclass
class ParsedTable:
    """A table lifted out of a PDF page.

    Standards put their real numbers in tables - temperature limits, migration
    limits, cord cross-sections. Losing them to a flat text dump loses the
    substance of the clause, so each table is kept twice: a structured payload
    for display, and a flattened searchable rendering so retrieval can find it.
    """

    page_number: Optional[int]
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    caption: str = ""
    nearest_clause: str = ""

    @property
    def searchable_text(self) -> str:
        parts: List[str] = []
        if self.caption:
            parts.append(self.caption)
        if self.headers:
            parts.append(" | ".join(self.headers))
        for row in self.rows:
            if not self.headers or len(row) != len(self.headers):
                parts.append(" | ".join(c for c in row if c))
                continue
            # "Header: value" reads better to a lexical index than a bare grid.
            parts.append(
                "; ".join(
                    f"{header}: {cell}"
                    for header, cell in zip(self.headers, row)
                    if cell
                )
            )
        return ". ".join(p for p in parts if p.strip())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "caption": self.caption,
            "headers": self.headers,
            "rows": self.rows,
            "page_number": self.page_number,
            "nearest_clause": self.nearest_clause,
        }


@dataclass
class ParsedDocument:
    metadata: Dict[str, str] = field(default_factory=dict)
    clauses: List[ParsedClause] = field(default_factory=list)
    tables: List[ParsedTable] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_path: str = ""

    @property
    def standard_id(self) -> str:
        return self.metadata.get("standard-id", "")


def classify_clause(heading_context: str, text: str) -> str:
    """Coarse clause typing used for filtering and requirement extraction.

    ``heading_context`` is the clause heading joined with every ancestor
    heading, so that "6.2.1" inherits the meaning of "6 Tests".
    """
    headings = heading_context.lower()
    blob = f"{heading_context} {text}".lower()
    if re.search(r"\bscope\b", headings):
        return "scope"
    if re.search(r"\breferences?\b", headings):
        return "reference"
    if re.search(r"\b(terminolog|definitions?)\b", headings):
        return "definition"
    if re.search(r"\b(test|method|conditioning|sampling|analytical)\b", headings):
        return "test"
    if re.search(r"\b(marking|labelling|label|warning)\b", headings):
        return "marking"
    if re.search(r"\b(instruction|documentation|technical file|record)\b", headings):
        return "documentation"
    if re.search(r"\b(material|construction|classification)\b", headings):
        return "requirement"
    if re.search(r"\bshall\b", blob):
        return "requirement"
    return "informative"


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def _read_text_file(path: Path) -> List[Tuple[str, Optional[int]]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [(line, None) for line in lines]


def _read_pdf(path: Path) -> List[Tuple[str, Optional[int]]]:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyMuPDF is required to ingest PDF documents") from exc

    out: List[Tuple[str, Optional[int]]] = []
    with fitz.open(path) as doc:
        for page_index, page in enumerate(doc, start=1):
            for line in page.get_text("text").splitlines():
                out.append((line, page_index))
    return out


_CAPTION_RE = re.compile(r"(table\s+\d+[^\r\n]{0,120})", re.IGNORECASE)


def extract_pdf_tables(path: Path) -> Tuple[List[ParsedTable], List[str]]:
    """Best-effort table extraction. Never fatal - warnings are collected.

    PyMuPDF gained find_tables() in 1.23; older builds simply yield no tables
    and ingestion continues on the text layer alone.
    """
    tables: List[ParsedTable] = []
    warnings: List[str] = []
    try:
        import fitz
    except ImportError:
        return tables, ["PyMuPDF not installed - table extraction skipped"]

    try:
        with fitz.open(path) as doc:
            for page_index, page in enumerate(doc, start=1):
                finder = getattr(page, "find_tables", None)
                if finder is None:
                    warnings.append(
                        "This PyMuPDF build has no find_tables(); tables were left in the "
                        "text layer only."
                    )
                    break
                try:
                    found = finder()
                except Exception as exc:
                    warnings.append(f"page {page_index}: table detection failed ({exc})")
                    continue

                page_text = page.get_text("text")
                caption_match = _CAPTION_RE.search(page_text or "")
                caption = caption_match.group(1).strip() if caption_match else ""

                for table in getattr(found, "tables", []) or []:
                    try:
                        grid = table.extract()
                    except Exception as exc:
                        warnings.append(f"page {page_index}: table extract failed ({exc})")
                        continue
                    grid = [
                        [re.sub(r"\s+", " ", (cell or "")).strip() for cell in row]
                        for row in grid
                        if any((cell or "").strip() for cell in row)
                    ]
                    if len(grid) < 2:
                        continue  # a single row is not a table worth keeping
                    headers, rows = grid[0], grid[1:]
                    if not any(headers):
                        headers, rows = [], grid
                    tables.append(
                        ParsedTable(
                            page_number=page_index,
                            headers=headers,
                            rows=rows,
                            caption=caption,
                        )
                    )
    except Exception as exc:  # pragma: no cover - depends on the document
        warnings.append(f"table extraction aborted: {exc}")

    return tables, warnings


def read_document_lines(path: Path) -> List[Tuple[str, Optional[int]]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix in (".txt", ".md", ".text"):
        return _read_text_file(path)
    raise ValueError(f"Unsupported document type: {path.suffix}")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_header(lines: List[Tuple[str, Optional[int]]]) -> Tuple[Dict[str, str], int]:
    metadata: Dict[str, str] = {}
    index = 0
    for index, (line, _) in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if metadata:
                continue
            continue
        if ":" in stripped:
            key = stripped.split(":", 1)[0].strip().lower()
            if key in HEADER_KEYS:
                metadata[key] = stripped.split(":", 1)[1].strip()
                continue
        break
    return metadata, index


def parse_document(path: Path) -> ParsedDocument:
    lines = read_document_lines(path)
    metadata, body_start = _parse_header(lines)
    doc = ParsedDocument(metadata=metadata, source_path=str(path))

    current: Optional[ParsedClause] = None
    buffer: List[str] = []
    #: clause-number prefix -> heading, used to build each clause's lineage.
    heading_index: Dict[str, str] = {}

    def flush() -> None:
        nonlocal current, buffer
        if current is None:
            return
        body = " ".join(b.strip() for b in buffer if b.strip())
        current.text = re.sub(r"\s+", " ", f"{current.heading} {body}").strip()
        if len(current.text) >= MIN_CHUNK_CHARS:
            current.clause_type = classify_clause(
                " ".join(current.heading_path + [current.heading]), body
            )
            doc.clauses.append(current)
        current, buffer = None, []

    for line, page in lines[body_start:]:
        raw = line.rstrip()
        if not raw.strip() or NOISE_RE.match(raw):
            continue
        match = CLAUSE_RE.match(raw)
        if match:
            flush()
            number = match.group(1)
            rest = match.group(2).strip()
            # A short trailing fragment is a heading; a long one is body text
            # that happens to start with the clause number.
            if len(rest) <= 90 and not rest.endswith("."):
                heading, first_body = rest, ""
            else:
                heading, first_body = "", rest
            if heading:
                heading_index[number] = heading
            bits = number.split(".")
            ancestors = [
                heading_index[prefix]
                for prefix in (".".join(bits[: i + 1]) for i in range(len(bits) - 1))
                if prefix in heading_index
            ]
            current = ParsedClause(
                clause_number=number,
                section_number=bits[0],
                heading=heading,
                text="",
                page_number=page,
                heading_path=ancestors,
            )
            buffer = [first_body] if first_body else []
        elif current is not None:
            buffer.append(raw)
        # Text before the first numbered clause is preamble and is dropped.
    flush()

    doc.clauses = _split_long_clauses(doc.clauses)

    if path.suffix.lower() == ".pdf":
        tables, warnings = extract_pdf_tables(path)
        doc.tables = tables
        doc.warnings.extend(warnings)
        _attach_nearest_clause(doc)

    return doc


def _attach_nearest_clause(doc: "ParsedDocument") -> None:
    """Give each table the clause number it sits closest to on the page."""
    by_page: Dict[int, List[ParsedClause]] = {}
    for clause in doc.clauses:
        if clause.page_number is not None:
            by_page.setdefault(clause.page_number, []).append(clause)
    for table in doc.tables:
        candidates = by_page.get(table.page_number or -1) or []
        if candidates:
            table.nearest_clause = candidates[-1].clause_number


def _split_long_clauses(clauses: List[ParsedClause]) -> List[ParsedClause]:
    """Split oversized clauses while preserving parent metadata."""
    out: List[ParsedClause] = []
    for clause in clauses:
        if len(clause.text) <= MAX_CHUNK_CHARS:
            out.append(clause)
            continue
        sentences = re.split(r"(?<=[.;])\s+", clause.text)
        parts: List[str] = []
        buf = ""
        for sentence in sentences:
            if len(buf) + len(sentence) + 1 > MAX_CHUNK_CHARS and buf:
                parts.append(buf.strip())
                buf = sentence
            else:
                buf = f"{buf} {sentence}".strip()
        if buf:
            parts.append(buf.strip())
        for i, part_text in enumerate(parts):
            out.append(
                ParsedClause(
                    clause_number=clause.clause_number,
                    section_number=clause.section_number,
                    heading=clause.heading,
                    text=part_text,
                    page_number=clause.page_number,
                    clause_type=clause.clause_type,
                    part=i,
                    total_parts=len(parts),
                )
            )
    return out


def parse_directory(directory: Path) -> List[ParsedDocument]:
    docs: List[ParsedDocument] = []
    if not directory.exists():
        return docs
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in (".txt", ".md", ".text", ".pdf"):
            continue
        try:
            doc = parse_document(path)
        except Exception as exc:
            logger.error("Failed to parse %s: %s", path.name, exc)
            continue
        if not doc.clauses:
            logger.warning("No clauses recognised in %s - skipped", path.name)
            continue
        docs.append(doc)
    return docs
