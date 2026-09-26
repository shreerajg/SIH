"""Optical character recognition for consumer label scanning.

A consumer photographs the standards mark printed on a product and the
platform reads whatever text is on it. This module's only job is turning
pixels into text and pulling out anything that looks like a standard
reference; it never decides what the product is or whether the mark is
genuine - that stays the job of :class:`ConsumerService`, which is the same
lookup a consumer typing a code by hand goes through. So a *misread* label
degrades to "not found, closest matches shown", exactly like a typo would -
it can never look like a fabricated standard.

If no OCR engine is available in this environment, that is reported honestly
(``available: False``) rather than silently returning nothing extracted; the
caller is responsible for showing that to the user instead of pretending the
scan happened.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.core.text_utils import extract_is_numbers

logger = logging.getLogger(__name__)

#: Where a Windows install of UB-Mannheim's Tesseract build usually lands.
#: Checked only when TESSERACT_CMD is not set; never overrides an explicit
#: setting.
_COMMON_WINDOWS_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

ALLOWED_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg"}

#: Magic bytes, checked because a content-type header is caller-supplied.
_MAGIC = (b"\x89PNG", b"\xff\xd8\xff")


class OcrUploadError(ValueError):
    """Raised for an image the platform will not attempt to scan."""


def validate_image(data: bytes, max_mb: int) -> None:
    """Reject anything that is not a small, genuine PNG/JPEG before it is scanned."""
    if not data:
        raise OcrUploadError("The uploaded image is empty.")
    limit = max_mb * 1024 * 1024
    if len(data) > limit:
        raise OcrUploadError(f"Image is larger than the {max_mb} MB limit.")
    if not any(data.startswith(magic) for magic in _MAGIC):
        raise OcrUploadError("Only PNG and JPEG photos are accepted.")


@dataclass
class OcrResult:
    available: bool
    #: Raw text as read by the OCR engine - shown to the user so a bad read
    #: is visible as a bad read, not hidden behind a wrong answer.
    raw_text: str = ""
    #: Standard references found in that text (IS numbers, DEMO-STD ids),
    #: deduplicated and in the order they appeared.
    candidates: List[str] = field(default_factory=list)
    status: str = "unavailable"  # unavailable | extracted | no_text_found | failed
    note: str = ""


class OcrService:
    """Wraps pytesseract; degrades honestly when no engine is installed."""

    def __init__(self) -> None:
        self._checked = False
        self._available = False
        self._pytesseract = None

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        self._ensure_checked()
        return self._available

    def _ensure_checked(self) -> None:
        if self._checked:
            return
        self._checked = True
        if settings.ocr_backend == "off":
            return
        try:
            import pytesseract
        except ImportError:
            logger.info("OCR unavailable: pytesseract is not installed.")
            return

        cmd = settings.tesseract_cmd.strip()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        elif not _on_path(pytesseract):
            for candidate in _COMMON_WINDOWS_PATHS:
                if Path(candidate).exists():
                    pytesseract.pytesseract.tesseract_cmd = candidate
                    break

        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.info("OCR unavailable: tesseract engine not reachable (%s).", exc)
            return

        self._pytesseract = pytesseract
        self._available = True

    # ------------------------------------------------------------------
    def scan(self, data: bytes, content_type: str = "") -> OcrResult:
        """Read text out of an uploaded label photo and pull out any standard
        references. Never raises for a bad/unreadable image - that comes back
        as ``status="failed"``, not an exception, since a blurry photo is an
        expected input, not a bug.
        """
        if not self.available:
            return OcrResult(
                available=False,
                status="unavailable",
                note=(
                    "OCR is not available in this environment (no Tesseract engine "
                    "found). Type the code from the label instead."
                ),
            )

        try:
            from io import BytesIO

            from PIL import Image

            image = Image.open(BytesIO(data))
            image.load()
        except Exception as exc:
            logger.info("OCR: could not open the uploaded image (%s).", exc)
            return OcrResult(
                available=True,
                status="failed",
                note="The uploaded file could not be read as an image.",
            )

        try:
            text = self._pytesseract.image_to_string(image) or ""
        except Exception as exc:  # pragma: no cover - engine dependent
            logger.warning("OCR extraction failed: %s", exc)
            return OcrResult(
                available=True,
                status="failed",
                note="The OCR engine could not process this image.",
            )

        candidates = extract_is_numbers(text)
        if not text.strip():
            return OcrResult(
                available=True,
                status="no_text_found",
                note="No text could be read from this image. Try a clearer, well-lit photo.",
            )
        return OcrResult(
            available=True,
            raw_text=text.strip()[:2000],
            candidates=candidates,
            status="extracted",
            note=(
                f"Found what looks like {len(candidates)} standard reference(s) in the "
                "image text."
                if candidates
                else "Text was read from the image, but nothing in it matched the shape "
                "of a standard number (e.g. 'IS 302')."
            ),
        )


def _on_path(pytesseract_module) -> bool:
    """True if the bare 'tesseract' command already resolves without a full path."""
    import shutil

    return shutil.which(pytesseract_module.pytesseract.tesseract_cmd) is not None


_service: Optional[OcrService] = None


def get_ocr_service() -> OcrService:
    global _service
    if _service is None:
        _service = OcrService()
    return _service
