from pathlib import Path

import pdfplumber


def extract_text(pdf_path: str | Path) -> str:
    """Extract plain text from a PDF, page by page."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n\n".join(pages).strip()