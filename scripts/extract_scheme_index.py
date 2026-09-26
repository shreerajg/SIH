"""Extract the BIS Scheme-I product list into a structured seed file.

The source is the official BIS "Scheme-I (ISI Mark Scheme) - Products under
Compulsory Certification" index page, registered in ``data/source_manifest.json``
as ``BIS-SCHEME-I-INDEX`` and downloaded into the verified pack. That page is an
HTML table rather than a clause-structured document, so the normal ingestion
parser skips it; this script turns it into records the certification service can
query.

Why this matters: it makes scheme applicability a **lookup against an official
BIS list**, not a guess. If a standard is not in the extracted list, the service
says so rather than inferring a scheme from the product category.

Output: ``data/seed/certification_scheme_index.json``

Usage::

    python scripts/extract_scheme_index.py
    python scripts/extract_scheme_index.py --dry-run
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.text_utils import normalize_is_number  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger("scheme-index")

MANIFEST = REPO_ROOT / "data" / "source_manifest.json"
OUT = REPO_ROOT / "data" / "seed" / "certification_scheme_index.json"
DOCUMENT_ID = "BIS-SCHEME-I-INDEX"

#: The scheme every row on this page belongs to.
SCHEME_ID = "SCHEME-I"

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_SR = re.compile(r"^\d+\.?$")
_IS = re.compile(r"IS\s*\d", re.I)


def _text(fragment: str) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", fragment))).strip()


def _manifest_entry() -> Dict[str, Any]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in payload.get("documents") or payload.get("entries") or []:
        if entry.get("document_id") == DOCUMENT_ID:
            return entry
    raise SystemExit(
        f"{DOCUMENT_ID} is not registered in {MANIFEST}. The extractor refuses to "
        "read a document that has no provenance record."
    )


def extract(source: Path) -> List[Dict[str, Any]]:
    raw = source.read_text(encoding="utf-8", errors="ignore")
    tables = re.findall(r"<table.*?</table>", raw, re.S | re.I)
    if not tables:
        raise SystemExit("No table found in the Scheme-I page - the layout may have changed.")

    entries: List[Dict[str, Any]] = []
    seen: set = set()
    # The page renders the same table twice (desktop / mobile); the first is enough.
    rows = re.findall(r"<tr.*?</tr>", tables[0], re.S | re.I)
    current_group = ""

    for row in rows:
        cells = [c for c in (_text(c) for c in re.findall(r"<t[dh].*?</t[dh]>", row, re.S | re.I)) if c]
        if not cells:
            continue
        # A single-cell row is a product-group heading ("Cement (any variety ...)").
        if len(cells) == 1 and not _SR.match(cells[0]):
            current_group = cells[0]
            continue
        if len(cells) < 3 or not _SR.match(cells[0]) or not _IS.search(cells[1]):
            continue

        is_no = cells[1]
        normalized = normalize_is_number(is_no) or ""
        key = (normalized, cells[2])
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "scheme_id": SCHEME_ID,
                "is_number": is_no,
                "normalized_number": normalized,
                "product": cells[2],
                "product_group": current_group,
                "notification": cells[3] if len(cells) > 3 else "",
            }
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    entry = _manifest_entry()
    source = REPO_ROOT / entry["local_path"]
    if not source.exists():
        raise SystemExit(
            f"{source} is not present. Official BIS documents are fetched on demand "
            "and are not committed to this repository."
        )

    entries = extract(source)
    with_number = [e for e in entries if e["normalized_number"]]
    log.info("Parsed %s product rows (%s with a parseable IS number)", len(entries), len(with_number))

    payload = {
        "scheme_id": SCHEME_ID,
        "document_id": entry["document_id"],
        "source_url": entry["source_url"],
        "retrieved_at": entry.get("retrieved_at"),
        "is_verified": bool(entry.get("is_verified")),
        "note": (
            "Extracted from the official BIS Scheme-I index page. Presence in this list is "
            "what the platform treats as evidence that a standard is covered by Scheme-I; "
            "absence is reported as 'unable to verify', never as 'not covered'."
        ),
        "entries": entries,
    }

    if args.dry_run:
        log.info("[dry run] would write %s entries to %s", len(entries), OUT)
        for e in entries[:5]:
            log.info("   %s | %s", e["is_number"], e["product"][:60])
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s entries to %s", len(entries), OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
