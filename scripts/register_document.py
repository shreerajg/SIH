#!/usr/bin/env python
"""Register an official BIS/Government document into the verified corpus.

    python scripts/register_document.py \
        --id IS-302-P1 \
        --is-number "IS 302 (Part 1)" \
        --title "Safety of household and similar electrical appliances" \
        --file data/raw/standards/IS-302-P1.pdf \
        --url https://www.services.bis.gov.in/... \
        --type standard

This is the only way a document becomes ``is_verified``. The manifest entry is
validated before it is written, so a synthetic identifier can never be
registered as official, and a verified entry can never lack a source URL.

After registering, ingest it:

    python scripts/ingest_documents.py --file data/raw/standards/IS-302-P1.pdf
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.constants import DocumentType  # noqa: E402
from app.ingestion.manifest import load_manifest, register_document  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Register an official document")
    # Not marked required, so --list works on its own; enforced below instead.
    parser.add_argument("--id", dest="document_id",
                        help="stable identifier, e.g. IS-302-P1")
    parser.add_argument("--is-number", help='e.g. "IS 302 (Part 1)"')
    parser.add_argument("--title")
    parser.add_argument("--file",
                        help="path to the local document, relative to the repo root")
    parser.add_argument("--url", help="official source URL")
    parser.add_argument(
        "--type", default=DocumentType.STANDARD.value,
        choices=[t.value for t in DocumentType],
    )
    parser.add_argument("--retrieved-on", default=date.today().isoformat())
    parser.add_argument("--notes", default="")
    parser.add_argument("--list", action="store_true", help="list the manifest and exit")
    args = parser.parse_args()

    if args.list:
        report = load_manifest()
        print(f"{'document_id':22s} {'verified':9s} {'type':12s} path")
        for entry in report.entries:
            print(
                f"{entry.document_id:22s} {str(entry.is_verified):9s} "
                f"{entry.document_type:12s} {entry.local_path}"
            )
        print(f"\n{report.verified_count} verified, {report.demo_count} demo")
        return 0

    missing = [
        name
        for name, value in (
            ("--id", args.document_id), ("--is-number", args.is_number),
            ("--title", args.title), ("--file", args.file), ("--url", args.url),
        )
        if not value
    ]
    if missing:
        parser.error("the following arguments are required: " + ", ".join(missing))

    local = Path(args.file)
    if not (REPO_ROOT / local).exists():
        print(f"ERROR: {local} does not exist. Put the document there first.")
        return 1

    try:
        entry = register_document(
            document_id=args.document_id,
            title=args.title,
            is_number=args.is_number,
            local_path=local.as_posix(),
            source_url=args.url,
            document_type=args.type,
            retrieved_at=args.retrieved_on,
            notes=args.notes,
        )
    except ValueError as exc:
        print(f"REJECTED: {exc}")
        return 1

    print(f"Registered {entry.document_id} as a verified {entry.document_type}.")
    print(f"  source : {entry.source_url}")
    print(f"  file   : {entry.local_path}")
    print("\nNow ingest it:")
    print(f"  python scripts/ingest_documents.py --file {entry.local_path}")
    print("\nAnd to answer only from official documents:")
    print("  set CORPUS_MODE=VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
