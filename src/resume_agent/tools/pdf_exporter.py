"""Renders tailored resume markdown to a PDF via `markdown` + `weasyprint`, using
a minimal single-column, table-free stylesheet chosen specifically to stay
ATS-parseable (plain headers, no multi-column layout, real selectable text — not
a rasterized image).
"""

import re
from pathlib import Path

import markdown
import weasyprint

# Minimal ATS-safe CSS — clean serif-free layout, letter-size
_CSS = """
@page { size: letter; margin: 0.6in 0.7in; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 10pt; line-height: 1.4; color: #000; }
h1   { font-size: 16pt; margin: 0 0 2pt; }
h2   { font-size: 11pt; border-bottom: 1px solid #000; margin: 8pt 0 3pt; text-transform: uppercase; letter-spacing: 0.5pt; }
h3   { font-size: 10pt; margin: 4pt 0 1pt; display: flex; justify-content: space-between; align-items: baseline; gap: 8pt; }
h3 .entry-date { font-style: italic; font-weight: normal; white-space: nowrap; flex-shrink: 0; }
p    { margin: 1pt 0; }
ul   { margin: 1pt 0; padding-left: 14pt; }
li   { margin-bottom: 1pt; }
a    { color: #000; text-decoration: none; }
"""

# Matches a standalone date line, e.g. "Jun 2022 - Present", "Sep 2021 - Oct 2021",
# "Jul 2026" (single month/year, as used for project entries).
_DATE_LINE_RE = re.compile(
    r"^[A-Za-z]{3,9}\.?\s+\d{4}"
    r"(\s*[-–—]\s*(Present|[A-Za-z]{3,9}\.?\s+\d{4}))?"
    r"(\s*\|\s*GPA:\s*[\d.]+)?$"
)


def _is_date_line(text: str) -> bool:
    return bool(_DATE_LINE_RE.match(text.strip()))


def _merge_title_date_lines(md_text: str) -> str:
    """Pull the date/meta line directly under each '### ' entry header onto the
    same line as an inline span, so the CSS above can lay the title out flush
    left and the date flush right on one row. Done as a markdown-text rewrite
    (not touching the model layer) so it applies uniformly to base and
    LLM-generated tailored markdown alike.
    """
    lines = md_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if line.startswith("### "):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                candidate = lines[j].strip()
                is_emph = len(candidate) > 2 and candidate.startswith("*") and candidate.endswith("*")
                text = candidate[1:-1].strip() if is_emph else candidate
                if is_emph or _is_date_line(text):
                    out[-1] = f'{line} <span class="entry-date">{text}</span>'
                    i = j
        i += 1
    return "\n".join(out)


def markdown_to_pdf(md_text: str, output_path: str | Path) -> Path:
    """Convert a markdown string to a PDF file."""
    html_body = markdown.markdown(_merge_title_date_lines(md_text), extensions=["extra"])
    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{html_body}</body></html>"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(str(output_path))
    return output_path