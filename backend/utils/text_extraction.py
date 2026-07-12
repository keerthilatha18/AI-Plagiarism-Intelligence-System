"""
utils/text_extraction.py
-------------------------
Converts uploaded file bytes → plain text string.
Supported formats: .txt, .docx, .pdf
"""
from __future__ import annotations

import io


def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Dispatch to the appropriate extractor based on the file extension.

    Parameters
    ----------
    file_bytes : raw bytes from the uploaded file
    filename   : original filename (used to detect extension)

    Returns
    -------
    Plain text string.  Never returns None — returns "" on empty input.
    """
    name = filename.lower().strip()

    if name.endswith(".txt"):
        return _extract_txt(file_bytes)
    if name.endswith(".docx"):
        return _extract_docx(file_bytes)
    if name.endswith(".pdf"):
        return _extract_pdf(file_bytes)

    raise ValueError(
        f"Unsupported file type for '{filename}'. "
        "Accepted formats: .txt, .docx, .pdf"
    )


# ── Private helpers ────────────────────────────────────────────────────────────

def _extract_txt(file_bytes: bytes) -> str:
    """Decode UTF-8 (with latin-1 fallback) plain-text files."""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def _extract_docx(file_bytes: bytes) -> str:
    """Extract paragraph text from a .docx file using python-docx."""
    try:
        from docx import Document  # python-docx
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required to process .docx files. "
            "Add it to requirements.txt."
        ) from exc

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF using pdfminer.six."""
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams
    except ImportError as exc:
        raise RuntimeError(
            "pdfminer.six is required to process .pdf files. "
            "Add it to requirements.txt."
        ) from exc

    output = io.StringIO()
    extract_text_to_fp(
        io.BytesIO(file_bytes),
        output,
        laparams=LAParams(),
        output_type="text",
        codec="utf-8",
    )
    return output.getvalue()
