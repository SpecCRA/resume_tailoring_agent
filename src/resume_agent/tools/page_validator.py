from pathlib import Path
import pdfplumber


def count_pages(pdf_path: str | Path) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def is_one_page(pdf_path: str | Path) -> bool:
    return count_pages(pdf_path) == 1