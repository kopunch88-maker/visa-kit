# -*- coding: utf-8 -*-
"""
Pack 60.0 — конвертация готового документа в формат скачивания.

Источник (docx | pdf) → docx | pdf | jpeg(zip).
  - docx→pdf  : LibreOffice (soffice --headless --convert-to pdf) — уже на сервере (Pack 52).
  - *→jpeg    : PDF растеризуется постранично через PyMuPDF (fitz); каждая страница = JPEG; всё в ZIP.
  - pdf→docx  : НЕ поддерживается (у нативных PDF нет Word-исходника) → ValueError.
"""
import io
import os
import subprocess
import tempfile
import zipfile

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MEDIA = "application/pdf"
ZIP_MEDIA = "application/zip"


def docx_to_pdf(docx_bytes: bytes, timeout_sec: int = 90) -> bytes:
    """DOCX → PDF через LibreOffice headless (тот же путь, что у выписки, Pack 52)."""
    with tempfile.TemporaryDirectory(prefix="vk_conv_") as tmp:
        src = os.path.join(tmp, "doc.docx")
        with open(src, "wb") as f:
            f.write(docx_bytes)
        try:
            result = subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, src],
                capture_output=True, timeout=timeout_sec,
            )
        except FileNotFoundError:
            raise RuntimeError("LibreOffice (soffice) не найден в PATH.")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"LibreOffice превысил {timeout_sec} сек при docx→pdf.")
        if result.returncode != 0:
            raise RuntimeError("LibreOffice docx→pdf: " + result.stderr.decode("utf-8", "replace")[:500])
        pdf_path = os.path.join(tmp, "doc.pdf")
        if not os.path.exists(pdf_path):
            raise RuntimeError("PDF не появился после конвертации docx→pdf.")
        with open(pdf_path, "rb") as f:
            return f.read()


def pdf_to_jpeg_zip(pdf_bytes: bytes, base_name: str, dpi: int = 170, quality: int = 85) -> bytes:
    """PDF → ZIP постраничных JPEG. Каждая страница: <base_name>_стр01.jpg ..."""
    import fitz  # PyMuPDF
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    out = io.BytesIO()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        n = doc.page_count
        pad = max(2, len(str(n)))
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(n):
                pix = doc.load_page(i).get_pixmap(matrix=mat)
                jpg = pix.tobytes("jpeg", jpg_quality=quality)
                zf.writestr(f"{base_name}_стр{str(i + 1).zfill(pad)}.jpg", jpg)
    finally:
        doc.close()
    return out.getvalue()


def convert(content: bytes, src_fmt: str, target_fmt: str, base_name: str):
    """
    Возвращает (bytes, filename, media_type).
    src_fmt / target_fmt ∈ {'docx','pdf','jpeg'} (+ синонимы jpg/image/images).
    base_name — без расширения.
    """
    src_fmt = (src_fmt or "").lower()
    t = (target_fmt or "").lower()
    if t in ("jpg", "image", "images"):
        t = "jpeg"

    if t in ("", "native", src_fmt):
        media = DOCX_MEDIA if src_fmt == "docx" else PDF_MEDIA
        return content, f"{base_name}.{src_fmt}", media

    if t == "pdf":
        if src_fmt == "docx":
            return docx_to_pdf(content), f"{base_name}.pdf", PDF_MEDIA
        raise ValueError("PDF из этого источника недоступен")

    if t == "docx":
        if src_fmt == "docx":
            return content, f"{base_name}.docx", DOCX_MEDIA
        raise ValueError("Word недоступен: у документа нет Word-исходника (он изначально PDF)")

    if t == "jpeg":
        pdf = content if src_fmt == "pdf" else docx_to_pdf(content)
        return pdf_to_jpeg_zip(pdf, base_name), f"{base_name}_images.zip", ZIP_MEDIA

    raise ValueError(f"Неизвестный формат: {target_fmt}")
