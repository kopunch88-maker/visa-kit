"""OCR service — распознавание документов клиента через LLM Vision."""

from .recognizer import (
    recognize_document,
    classify_document,
    generate_declensions,
    OCRError,
)

__all__ = [
    "recognize_document",
    "classify_document",
    "generate_declensions",
    "OCRError",
]
