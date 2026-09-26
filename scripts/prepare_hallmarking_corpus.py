"""Prepare the fetched BIS hallmarking sources for ingestion.

The existing ingestion parser reads ``.pdf``, ``.txt`` and ``.md``. The BIS
hallmarking sources are a mix of PDFs (which ingest as-is) and HTML pages
(which do not), so this script:

1. stages the PDFs into ``data/raw/hallmarking/``;
2. converts the FAQ / overview HTML pages into ``.md``, keeping only the page's
   own content - the extractor drops the site chrome so a navigation menu can
   never be quoted back as though it were BIS guidance;
3. registers every document in ``data/source_manifest.json`` with its URL,
   retrieval date and SHA-256, so each one carries provenance before a single
   clause of it can be cited.

Run ``scripts/fetch_hallmarking_sources.py`` first. Then ingest normally::

    python scripts/prepare_hallmarking_corpus.py
    python scripts/ingest_documents.py --input data/raw/hallmarking
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "data" / "raw" / "verified_bis_hallmarking"
OUT_DIR = REPO_ROOT / "data" / "raw" / "hallmarking"
MANIFEST = REPO_ROOT / "data" / "source_manifest.json"
REPORT = SRC_DIR / "download_validation_report.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger("prepare-hallmarking")

#: document_id -> how the corpus should describe it.
CATALOGUE: Dict[str, Dict[str, Any]] = {
    "BIS-HM-BRIEF": {
        "standard_id": "BIS-HM-BRIEF",
        "is_number": "",
        "title": "BIS Brief on the Hallmarking Scheme",
        "document_type": "hallmarking",
        "product_category": "precious-metal",
        "keywords": ["hallmarking", "gold", "silver", "huid", "purity", "fineness", "assaying"],
        "covered_areas": [
            "Hallmarking scheme overview",
            "Hallmark components",
            "Purity and fineness grades",
            "Assaying and hallmarking centres",
        ],
    },
    "BIS-HM-REGULATIONS-2018": {
        "standard_id": "BIS-HM-REGULATIONS-2018",
        "is_number": "",
        "title": "BIS (Hallmarking) Regulations, 2018",
        "document_type": "regulatory",
        "product_category": "precious-metal",
        "keywords": ["hallmarking", "regulations", "jeweller", "assaying"],
        "covered_areas": ["Legal basis for hallmarking", "Obligations of jewellers and centres"],
    },
    "BIS-HM-MANDATORY-ORDER-2020": {
        "standard_id": "BIS-HM-MANDATORY-ORDER-2020",
        "is_number": "",
        "title": "Hallmarking of Gold Jewellery and Gold Artefacts Order, 2020",
        "document_type": "qco",
        "product_category": "precious-metal",
        "keywords": ["hallmarking", "gold", "mandatory", "order"],
        "covered_areas": ["Mandatory hallmarking applicability"],
    },
    "BIS-HM-JEWELLER-REGISTRATION": {
        "standard_id": "BIS-HM-JEWELLER-REGISTRATION",
        "is_number": "",
        "title": "BIS Guide: Procedure to apply for Jeweller Registration",
        "document_type": "hallmarking",
        "product_category": "precious-metal",
        "keywords": ["jeweller registration", "hallmarking", "application"],
        "covered_areas": ["Jeweller registration procedure"],
        "step_pdf": True,
    },
    "BIS-HM-JEWELLER-GUIDELINES": {
        "standard_id": "BIS-HM-JEWELLER-GUIDELINES",
        "is_number": "",
        "title": "BIS Guidelines for Jewellers",
        "document_type": "hallmarking",
        "product_category": "precious-metal",
        "keywords": ["jeweller", "hallmarking", "obligations"],
        "covered_areas": ["Obligations of a registered jeweller"],
    },
    "BIS-HM-AHC-GUIDELINES": {
        "standard_id": "BIS-HM-AHC-GUIDELINES",
        "is_number": "",
        "title": "BIS Guidelines for Assaying and Hallmarking Centres",
        "document_type": "hallmarking",
        "product_category": "precious-metal",
        "keywords": ["assaying", "hallmarking centre", "recognition"],
        "covered_areas": ["A&H centre recognition and operation"],
    },
    "BIS-HM-FAQ-GENERAL": {
        "standard_id": "BIS-HM-FAQ-GENERAL",
        "is_number": "",
        "title": "BIS Hallmarking FAQ - General",
        "document_type": "hallmarking",
        "product_category": "precious-metal",
        "keywords": ["hallmarking", "faq", "purity", "grades", "standards"],
        "covered_areas": ["What hallmarking is", "Indian Standards on hallmarking", "Permitted grades"],
    },
    "BIS-HM-FAQ-CONSUMER": {
        "standard_id": "BIS-HM-FAQ-CONSUMER",
        "is_number": "",
        "title": "BIS Hallmarking FAQ - Consumers",
        "document_type": "hallmarking",
        "product_category": "precious-metal",
        "keywords": ["hallmarking", "consumer", "complaint", "compensation"],
        "covered_areas": ["Consumer rights", "Complaint redressal", "Compensation for purity shortfall"],
    },
    "BIS-HM-CONSUMER-PROTECTION": {
        "standard_id": "BIS-HM-CONSUMER-PROTECTION",
        "is_number": "",
        "title": "BIS Hallmarking - Consumer Protection",
        "document_type": "hallmarking",
        "product_category": "precious-metal",
        "keywords": ["consumer protection", "hallmarking", "grievance"],
        "covered_areas": ["Consumer protection under the hallmarking scheme"],
    },
}

#: Page chrome. A menu item must never become a citable clause.
CHROME = re.compile(
    r"(skip to (main )?content|screen reader|text size|toggle navigation|"
    r"follow us on|subscribe on|sitemap|copyright|last updated|hindi|search)",
    re.I,
)


def _html_to_markdown(path: Path, title: str) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>|<footer.*?</footer>",
                 " ", raw, flags=re.S | re.I)

    # The BIS FAQ body starts at the "Frequently Asked Questions" heading; the
    # overview pages start after the breadcrumb. Take from the first heading so
    # the site menu above it is excluded.
    text = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and len(ln) > 2 and not CHROME.fullmatch(ln)]

    start = 0
    for index, line in enumerate(lines):
        if re.search(r"frequently asked questions|hallmarking", line, re.I) and index > 20:
            start = index
            break
    body = lines[start:]

    # Drop the long menu runs: real content lines are sentences, menu items are
    # short fragments. Keep a short line only when it looks like a numbered Q.
    kept: List[str] = []
    for line in body:
        if len(line) > 60 or re.match(r"^\d+\s*[.)]", line) or line.endswith("?"):
            kept.append(line)
    if not kept:
        kept = body

    deduped: List[str] = []
    for line in kept:
        if not deduped or deduped[-1] != line:
            deduped.append(line)

    return f"# {title}\n\n" + "\n\n".join(deduped) + "\n"


def _steps_to_markdown(path: Path, title: str) -> str:
    """A "Step N:" walkthrough PDF -> numbered clauses.

    Only the numbering is changed: BIS's own wording for each step is kept
    verbatim so a citation quotes the document, not a paraphrase of it.
    """
    import fitz

    document = fitz.open(path)
    text = "\n".join(page.get_text("text") for page in document)
    text = re.sub(r"\(Fig[^)]*\)", " ", text)          # figure captions
    text = re.sub(r"[ \t]+", " ", text)

    parts = re.split(r"(?:^|\n)\s*Step\s+(\d+)\s*:", text)
    lines = [f"# {title}", ""]
    if len(parts) < 3:
        return "\n".join(lines + [re.sub(r"\s+", " ", text).strip()]) + "\n"

    # parts = [preamble, "1", body1, "2", body2, ...]
    for index in range(1, len(parts) - 1, 2):
        number = parts[index].strip()
        body = re.sub(r"\s+", " ", parts[index + 1]).strip()
        if not body:
            continue
        lines.append(f"{number}. Step {number}")
        lines.append("")
        lines.append(body)
        lines.append("")
    return "\n".join(lines) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not REPORT.exists():
        raise SystemExit(
            f"{REPORT} not found. Run scripts/fetch_hallmarking_sources.py first."
        )
    downloads = {r["document_id"]: r for r in json.loads(REPORT.read_text(encoding="utf-8"))}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    staged: List[Dict[str, Any]] = []

    for document_id, meta in CATALOGUE.items():
        download = downloads.get(document_id)
        if download is None or download.get("status") != "OK":
            log.warning("%-30s not downloaded - skipped", document_id)
            continue

        source = SRC_DIR / download["target"]
        if meta.get("step_pdf"):
            # A screenshot walkthrough: real text, but written as "Step 1:"
            # rather than numbered clauses, so the clause parser finds nothing
            # and drops the whole document. Renumbering the steps as clauses
            # keeps the wording exactly as BIS wrote it while making each step
            # individually citable.
            target = OUT_DIR / f"{document_id}.md"
            if not args.dry_run:
                target.write_text(_steps_to_markdown(source, meta["title"]), encoding="utf-8")
        elif source.suffix.lower() == ".pdf":
            target = OUT_DIR / f"{document_id}.pdf"
            if not args.dry_run:
                shutil.copy2(source, target)
        else:
            target = OUT_DIR / f"{document_id}.md"
            if not args.dry_run:
                target.write_text(_html_to_markdown(source, meta["title"]), encoding="utf-8")

        size = target.stat().st_size if target.exists() else 0
        log.info("%-30s -> %-34s %8d bytes", document_id, target.name, size)
        staged.append(
            {
                "document_id": document_id,
                "standard_id": meta["standard_id"],
                "is_number": meta["is_number"],
                "title": meta["title"],
                "document_type": meta["document_type"],
                "source_url": download["url"],
                "source_type": "official",
                "is_verified": True,
                "is_demo": False,
                "retrieved_at": download["retrieved_at"],
                "local_path": f"data/raw/hallmarking/{target.name}",
                "filename": target.name,
                "sha256": download.get("sha256", ""),
                "product_category": meta["product_category"],
                "keywords": meta["keywords"],
                "covered_areas": meta["covered_areas"],
                "notes": (
                    "Official BIS hallmarking source, downloaded from bis.gov.in by "
                    "scripts/fetch_hallmarking_sources.py. Not redistributed with this repository."
                ),
            }
        )

    if args.dry_run:
        log.info("[dry run] %s document(s) would be staged and registered", len(staged))
        return 0

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    key = "documents" if "documents" in payload else "entries"
    existing = {d.get("document_id") for d in payload[key]}
    added = 0
    for entry in staged:
        if entry["document_id"] in existing:
            payload[key] = [
                entry if d.get("document_id") == entry["document_id"] else d for d in payload[key]
            ]
        else:
            payload[key].append(entry)
            added += 1
    MANIFEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info("-" * 60)
    log.info("%s staged in %s; %s new manifest entr(ies)", len(staged), OUT_DIR, added)
    log.info("Next: python scripts/ingest_documents.py --input data/raw/hallmarking")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
