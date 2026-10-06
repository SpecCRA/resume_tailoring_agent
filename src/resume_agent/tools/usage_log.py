"""A running CSV history of every `tailor` invocation — one row per run, whether
it was screened out (PASS, most fields blank) or fully tailored: date, company,
role, verdict, and every assessment number produced. Pure file I/O, no LLM calls,
so it lives alongside the other `tools/` persistence helpers rather than inside
`pipelines/tailor.py` itself.
"""

import csv
from pathlib import Path
from typing import Any

from resume_agent.config import settings

USAGE_LOG_FIELDS = [
    "date",
    "company",
    "role",
    "verdict",
    "screening_fit_score",
    "final_fit_score",
    "ats_keywords_found",
    "ats_keywords_total",
    "remaining_gaps",
    "low_relevance_bullets",
    "refine_rounds",
]


def append_usage_log(row: dict[str, Any]) -> None:
    """Append one row to `<data_dir>/usage_log.csv`. Writes the header only once,
    the first time the file is created, so the log is append-only and safe to
    re-run across jobs. Lives under `settings.data_dir` (like the scraped-JD
    directory) rather than its own setting, so redirecting data_dir — as tests
    already do — redirects this too.

    If a log from before a column was added already exists, its on-disk header is
    migrated to `USAGE_LOG_FIELDS` first (old rows backfilled with blanks for the
    new column) — otherwise new rows would have more fields than the stale header,
    silently misaligning every column after the first schema change.
    """
    log_path = Path(settings.data_dir) / "usage_log.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if log_path.exists():
        with log_path.open(newline="") as f:
            existing_rows = list(csv.DictReader(f))
        if existing_rows and list(existing_rows[0].keys()) != USAGE_LOG_FIELDS:
            with log_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=USAGE_LOG_FIELDS)
                writer.writeheader()
                writer.writerows(existing_rows)

    is_new = not log_path.exists()
    with log_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=USAGE_LOG_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
