"""Consumer label scanning (OCR).

The rule this file defends: OCR only ever produces *candidate text* for the
same lookup a typed code goes through. A misread character must degrade to
"not found", never to a fabricated standard - so the tests that exercise a
real scan check the lookup honours what was actually read, and the tests that
don't need a real engine check the degrade path on its own.
"""
from __future__ import annotations

import io

import pytest

from app.services.ocr import OcrUploadError, get_ocr_service, validate_image

OCR_AVAILABLE = get_ocr_service().available


def _label_image(lines: list[str]) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (640, 90 * len(lines) + 40), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except Exception:
        font = ImageFont.load_default()
    for i, line in enumerate(lines):
        draw.text((20, 20 + i * 90), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Upload validation - runs regardless of whether an OCR engine is installed.
# ---------------------------------------------------------------------------

def test_an_empty_image_is_refused():
    with pytest.raises(OcrUploadError):
        validate_image(b"", max_mb=10)


def test_a_non_image_is_refused_even_with_an_image_extension():
    with pytest.raises(OcrUploadError):
        validate_image(b"not actually a png", max_mb=10)


def test_an_oversized_image_is_refused():
    payload = b"\x89PNG" + b"0" * (2 * 1024 * 1024)
    with pytest.raises(OcrUploadError):
        validate_image(payload, max_mb=1)


def test_scan_endpoint_rejects_a_non_image_upload(client):
    response = client.post(
        "/api/consumer/scan",
        files={"file": ("note.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 400
    assert "PNG and JPEG" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Degrade path - must hold even when no engine is configured.
# ---------------------------------------------------------------------------

def test_unavailable_engine_is_reported_honestly_not_silently():
    from app.services.ocr import OcrService

    svc = OcrService()
    svc._checked = True
    svc._available = False  # simulate no tesseract in this environment

    result = svc.scan(b"\x89PNG" + b"0" * 100, "image/png")
    assert result.available is False
    assert result.status == "unavailable"
    assert result.candidates == []
    assert "not available" in result.note.lower()


# ---------------------------------------------------------------------------
# Real OCR - skipped where no engine is installed, so the suite stays
# portable, but exercised in full wherever Tesseract is present.
# ---------------------------------------------------------------------------

pytestmark_real = pytest.mark.skipif(not OCR_AVAILABLE, reason="no OCR engine installed")


@pytestmark_real
def test_scan_reads_a_clean_demo_code_off_a_label():
    png = _label_image(["DEMO-STD-004"])
    result = get_ocr_service().scan(png, "image/png")

    assert result.available is True
    assert result.status == "extracted"
    assert "DEMO-STD-004" in result.candidates


@pytestmark_real
def test_scan_reads_multiple_references_off_one_label():
    png = _label_image(["DEMO-STD-004", "IS 4250 : 2018"])
    result = get_ocr_service().scan(png, "image/png")

    assert "DEMO-STD-004" in result.candidates
    assert "IS-4250" in result.candidates


@pytestmark_real
def test_scan_of_a_blank_image_finds_no_text():
    from PIL import Image

    img = Image.new("RGB", (200, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    result = get_ocr_service().scan(buf.getvalue(), "image/png")
    assert result.status == "no_text_found"
    assert result.candidates == []


@pytestmark_real
def test_scan_endpoint_matches_a_real_standard_end_to_end(client):
    """The full path: photograph -> OCR -> the same lookup a typed code gets."""
    png = _label_image(["DEMO-STD-004"])
    response = client.post(
        "/api/consumer/scan",
        files={"file": ("label.png", io.BytesIO(png), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["ocr_available"] is True
    assert "DEMO-STD-004" in body["candidates"]
    assert body["result"]["found"] is True
    assert body["result"]["standard"]["id"] == "DEMO-STD-004"
    # The response never hides what was actually read.
    assert "DEMO-STD-004" in body["raw_text"]


@pytestmark_real
def test_scan_of_an_unreadable_code_does_not_fabricate_a_standard(client):
    """A garbled read must come back as not-found, never as an invented match."""
    png = _label_image(["XQZ 999999 NONSENSE CODE"])
    response = client.post(
        "/api/consumer/scan",
        files={"file": ("label.png", io.BytesIO(png), "image/png")},
    )
    body = response.json()

    assert body["result"] is None or body["result"]["found"] is False
