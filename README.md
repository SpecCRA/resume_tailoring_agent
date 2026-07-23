# Resume Tailoring Agent

A Claude-powered CLI that turns one base resume into a job-specific, one-page
PDF for every posting you apply to. It parses your resume once, then for each
job posting scrapes the description, scores your fit, rewrites bullets to
match, and exports a clean ATS-friendly PDF.

## How it works

1. **Setup (once):** Parse a resume PDF into a structured base template
   (`data/base/resume_base.md`), generating multiple bullet-point variants for
   each experience/project bullet.
2. **Tailor (per job):** Given a job posting URL, extract the job description,
   score how well your base resume fits it, select/rewrite bullets to match,
   and export a one-page PDF — retrying with trim passes if it overflows.

## Requirements

- Python >= 3.10
- An [Anthropic API key](https://console.anthropic.com/)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
git clone <this-repo>
cd resume_tailoring_agent
uv sync
```

WeasyPrint (PDF export) has native dependencies (Pango, cairo, etc.) — see the
[WeasyPrint install docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)
if PDF export fails on your OS.

## Configuration

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Optional settings (defaults shown) — see
[src/resume_agent/config/config.py](src/resume_agent/config/config.py):

| Variable              | Default                     | Description                                  |
|------------------------|------------------------------|-----------------------------------------------|
| `CLAUDE_MODEL`          | `claude-sonnet-5`            | Model used for all LLM calls                  |
| `DATA_DIR`              | `data`                       | Root dir for base resume + job descriptions   |
| `OUTPUT_DIR`            | `output`                     | Where tailored `.md`/`.pdf` files are written |
| `BASE_RESUME_PATH`      | `data/base/resume_base.md`   | Path to the generated base resume             |
| `MAX_BULLET_VARIANTS`   | `5`                          | Variants generated per experience bullet      |
| `PAGE_TRIM_ATTEMPTS`    | `3`                          | Retries to fit tailored resume on one page    |

## CLI usage

The package installs a `resume-agent` command (see `[project.scripts]` in
[pyproject.toml](pyproject.toml)). Run it via `uv run resume-agent ...`, or
activate the venv and call `resume-agent ...` directly.

### `setup` — one-time resume parsing

```bash
uv run resume-agent setup data/input/resume.pdf
```

Extracts text from the PDF, has Claude parse it into structured sections, and
generates bullet-point variants for each experience/project entry. Writes the
result to `data/base/resume_base.md`.

The generated markdown is meant to be hand-edited afterward — add/remove
bullets, tweak variants, fix parsing mistakes — before tailoring against jobs.

### `review` — re-sync a hand-edited base resume

```bash
uv run resume-agent review
```

Re-parses `data/base/resume_base.md` after you've manually edited it and
backfills bullet variants for any new/changed bullets, leaving
already-reviewed bullets untouched. Run this after editing the base resume by
hand.

### `tailor` — generate a job-specific resume

```bash
uv run resume-agent tailor "https://jobs.example.com/posting/123" \
  --company "Acme Corp" --role "Senior Data Engineer"
```

| Argument/Option     | Required | Description                    |
|----------------------|----------|---------------------------------|
| `url`                 | yes      | Job posting URL to scrape      |
| `--company` / `-c`    | yes      | Company name (used in filenames)|
| `--role` / `-r`       | yes      | Job title (used in filenames)  |

This will:
1. Scrape and extract structured data from the job posting →
   `data/jobs/<company>-<role>.md`
2. Score fit against your base resume (0.0–1.0, with notes) — warns if the
   score is below 0.4
3. Rewrite/select bullets tailored to the job, retrying up to
   `PAGE_TRIM_ATTEMPTS` times if the result doesn't fit one page
4. Write `output/<company>-<role>.md` and `output/<company>-<role>.pdf`

## Typical workflow

```bash
# 1. One-time: parse your resume
uv run resume-agent setup data/input/resume.pdf

# 2. (Optional) hand-edit data/base/resume_base.md, then re-sync
uv run resume-agent review

# 3. For each job you apply to:
uv run resume-agent tailor "<job-url>" -c "Company" -r "Role Title"
```

## Project layout

```
src/resume_agent/
├── main.py          # CLI entrypoint (typer) — setup / review / tailor
├── config/          # Pydantic settings, loaded from .env
├── models/          # Resume, JobDescription data contracts
├── tools/           # PDF read/export, page counting, job-page scraping
├── prompts/         # LLM prompt builders for each pipeline step
└── pipelines/       # setup.py and tailor.py orchestration
```

## Development

```bash
uv sync --dev
uv run pytest              # run tests
uv run ruff check .        # lint
uv run mypy .              # type check
```
