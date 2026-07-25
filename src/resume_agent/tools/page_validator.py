"""Page-count check for the tailoring pipeline's one-page constraint.
`pipelines/tailor.py._tailor_with_page_limit` renders each tailoring attempt to a
temp PDF and calls `is_one_page` to decide whether to accept it or retry with a
trim pass.
"""

from pathlib import Path

import pdfplumber


def count_pages(pdf_path: str | Path) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def is_one_page(pdf_path: str | Path) -> bool:
    return count_pages(pdf_path) == 1