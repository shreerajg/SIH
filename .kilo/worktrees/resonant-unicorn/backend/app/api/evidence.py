"""Product evidence upload and inspection."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_product
from app.core.constants import UploadCategory
from app.models import Product, ProductEvidence
from app.services.evidence import (
    EvidenceUploadError,
    get_evidence_service,
)

router = APIRouter(prefix="/products", tags=["evidence"])


def _payload(record: ProductEvidence) -> Dict[str, Any]:
    fields = record.extracted_fields_json or {}
    return {
        "id": record.id,
        "name": record.name,
        "evidence_type": record.evidence_type,
        "upload_category": record.upload_category,
        "original_filename": record.original_filename,
        "content_type": record.content_type,
        "size_bytes": record.size_bytes,
        "extraction_status": record.extraction_status,
        "extracted_fields": fields,
        "has_text": bool((record.extracted_text or "").strip()),
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "note": _extraction_note(record),
    }


def _extraction_note(record: ProductEvidence) -> str:
    status = record.extraction_status
    if status == "extracted":
        result = (record.extracted_fields_json or {}).get("result")
        if result:
            return (
                f"Text was read from this document, including the wording '{result}'. "
                "That wording is reported as found; the platform does not assess whether "
                "the requirement is actually met."
            )
        return (
            "Text was read from this document. The platform records that the document "
            "exists; it does not determine whether a requirement is satisfied."
        )
    if status == "pdf_has_no_text_layer":
        return (
            "This PDF has no text layer (it is probably a scan), so nothing could be read "
            "from it. It is still recorded as supplied evidence."
        )
    if status == "image_requires_ocr":
        return "Images are stored as evidence but are not text-extracted here."
    if status == "extraction_failed":
        return "The file could not be read. It is still recorded as supplied evidence."
    return "No text extraction was attempted for this file type."


@router.get("/{product_id}/evidence")
def list_evidence(
    product: Product = Depends(get_product), db: Session = Depends(db_session)
) -> Dict[str, Any]:
    records = (
        db.query(ProductEvidence).filter(ProductEvidence.product_id == product.id).all()
    )
    return {
        "product_id": product.id,
        "evidence": [_payload(r) for r in records],
        "categories": [c.value for c in UploadCategory],
        "note": (
            "Uploaded evidence is stored in its own index, separate from the standards "
            "corpus, so a manufacturer document can never be cited as a clause."
        ),
    }


@router.post("/{product_id}/evidence/upload", status_code=201)
async def upload_evidence(
    file: UploadFile = File(...),
    category: str = Form(default=UploadCategory.OTHER.value),
    name: str = Form(default=""),
    product: Product = Depends(get_product),
    db: Session = Depends(db_session),
) -> Dict[str, Any]:
    """Accept one evidence document (PDF, TXT, PNG or JPEG)."""
    data = await file.read()
    try:
        record = get_evidence_service().store_upload(
            db,
            product,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            data=data,
            category=category,
            display_name=name,
        )
    except EvidenceUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _payload(record)


@router.delete("/{product_id}/evidence/{evidence_id}")
def delete_evidence(
    evidence_id: str,
    product: Product = Depends(get_product),
    db: Session = Depends(db_session),
) -> Response:
    record = (
        db.query(ProductEvidence)
        .filter(
            ProductEvidence.id == evidence_id,
            ProductEvidence.product_id == product.id,
        )
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="No such evidence for this product.")
    get_evidence_service().delete(db, record)
    return Response(status_code=204)


@router.get("/{product_id}/evidence/{evidence_id}")
def get_evidence(
    evidence_id: str,
    product: Product = Depends(get_product),
    db: Session = Depends(db_session),
) -> Dict[str, Any]:
    record = (
        db.query(ProductEvidence)
        .filter(
            ProductEvidence.id == evidence_id,
            ProductEvidence.product_id == product.id,
        )
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="No such evidence for this product.")
    payload = _payload(record)
    payload["extracted_text_preview"] = (record.extracted_text or "")[:4000]
    return payload
