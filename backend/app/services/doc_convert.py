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


# ============================================================================
# Pack 60.2 — конвертация ЦЕЛОГО архива (ZIP) в один формат.
# docx→pdf делается ОДНИМ вызовом soffice (батч) — иначе на ~18 документах
# последовательные вызовы упрутся в таймаут запроса.
# ============================================================================

def _batch_docx_to_pdf(named_docx, timeout_sec: int = 180) -> dict:
    """[(name, docx_bytes), ...] → {name: pdf_bytes}. Один вызов soffice на все."""
    if not named_docx:
        return {}
    result = {}
    with tempfile.TemporaryDirectory(prefix="vk_pkg_") as tmp:
        # уникальные безопасные имена (имена в ZIP — кириллица/повторы недопустимы для soffice)
        mapping = []  # (name, stem)
        for idx, (name, data) in enumerate(named_docx):
            stem = f"d{idx:03d}"
            with open(os.path.join(tmp, stem + ".docx"), "wb") as f:
                f.write(data)
            mapping.append((name, stem))
        cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp]
        cmd += [os.path.join(tmp, stem + ".docx") for _, stem in mapping]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout_sec)
        except FileNotFoundError:
            raise RuntimeError("LibreOffice (soffice) не найден в PATH.")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"LibreOffice превысил {timeout_sec} сек при батч docx→pdf.")
        if r.returncode != 0:
            raise RuntimeError("LibreOffice батч docx→pdf: " + r.stderr.decode("utf-8", "replace")[:500])
        for name, stem in mapping:
            p = os.path.join(tmp, stem + ".pdf")
            if not os.path.exists(p):
                raise RuntimeError(f"PDF не появился для {name} (батч).")
            with open(p, "rb") as f:
                result[name] = f.read()
    return result


def _write_pdf_pages(zf, folder: str, leaf_base: str, pdf_bytes: bytes, dpi: int = 170, quality: int = 85):
    """Растеризует PDF постранично прямо в открытый ZipFile: folder/leaf_base_стрNN.jpg"""
    import fitz  # PyMuPDF
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        n = doc.page_count
        pad = max(2, len(str(n)))
        for i in range(n):
            pix = doc.load_page(i).get_pixmap(matrix=mat)
            jpg = pix.tobytes("jpeg", jpg_quality=quality)
            zf.writestr(f"{folder}{leaf_base}_стр{str(i + 1).zfill(pad)}.jpg", jpg)
    finally:
        doc.close()


def convert_package_zip(zip_bytes: bytes, target_fmt: str) -> bytes:
    """
    Постобработка готового ZIP-архива пакета.
      native        → как есть
      pdf           → docx→PDF (батч soffice); pdf-формы остаются PDF
      docx (Word)   → docx остаются; pdf-формы остаются PDF (нет Word-исходника)
      jpeg          → каждый документ → подпапка со страницами-картинками
    """
    t = (target_fmt or "").lower()
    if t in ("jpg", "image", "images"):
        t = "jpeg"
    if t in ("", "native"):
        return zip_bytes
    if t == "docx":
        return zip_bytes  # docx уже docx, pdf-формы не конвертируются → без изменений

    zin = zipfile.ZipFile(io.BytesIO(zip_bytes))
    entries = [(i.filename, zin.read(i.filename)) for i in zin.infolist() if not i.filename.endswith("/")]

    # docx→pdf одним батчем (нужно и для pdf, и для jpeg)
    docx_named = [(n, d) for n, d in entries if n.lower().endswith(".docx")]
    pdf_of = _batch_docx_to_pdf(docx_named) if docx_named else {}

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            low = name.lower()
            base = name[:-5] if low.endswith(".docx") else (name[:-4] if low.endswith(".pdf") else name)
            leaf = base.split("/")[-1]
            if t == "pdf":
                if low.endswith(".docx"):
                    zf.writestr(base + ".pdf", pdf_of[name])
                else:
                    zf.writestr(name, data)
            elif t == "jpeg":
                if low.endswith(".docx"):
                    _write_pdf_pages(zf, base + "/", leaf, pdf_of[name])
                elif low.endswith(".pdf"):
                    _write_pdf_pages(zf, base + "/", leaf, data)
                else:
                    zf.writestr(name, data)
    return out.getvalue()
