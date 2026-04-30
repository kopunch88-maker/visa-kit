"""OCR service — распознавание документов клиента через LLM Vision."""

from .recognizer import recognize_document, OCRError

__all__ = ["recognize_document", "OCRError"]
