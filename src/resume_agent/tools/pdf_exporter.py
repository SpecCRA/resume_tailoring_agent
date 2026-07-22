from pathlib import Path

import markdown
import weasyprint

# Minimal ATS-safe CSS — clean serif-free layout, letter-size
_CSS = """
@page { size: letter; margin: 0.6in 0.7in; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 10pt; line-height: 1.4; color: #000; }
h1   { font-size: 16pt; margin: 0 0 2pt; }
h2   { font-size: 11pt; border-bottom: 1px solid #000; margin: 8pt 0 3pt; text-transform: uppercase; letter-spacing: 0.5pt; }
h3   { font-size: 10pt; margin: 4pt 0 1pt; }
p    { margin: 1pt 0; }
ul   { margin: 1pt 0; padding-left: 14pt; }
li   { margin-bottom: 1pt; }
a    { color: #000; text-decoration: none; }
"""


def markdown_to_pdf(md_text: str, output_path: str | Path) -> Path:
    """Convert a markdown string to a PDF file."""
    html_body = markdown.markdown(md_text, extensions=["extra"])
    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{html_body}</body></html>"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(str(output_path))
    return output_path