# Resume Tailoring Agent

A Claude-powered CLI that turns one base resume into a job-specific, one-page
PDF for every posting you apply to. It parses your resume once, then for each
job posting scrapes the description, assesses whether your resume is a strong
enough fit to bother tailoring, and — if so — selects/rewrites bullets to match
and exports a clean ATS-friendly PDF.

Every step is guarded against fabrication: nothing is ever added to your resume
that isn't already there (no invented skills, tools, or metrics, even when the
job description asks for them), and a bad scrape, an unparseable job posting, or
a malformed model response fails with a clear message instead of silently
producing a broken or dishonest resume.

## How it works

1. **Setup (once):** Parse a resume PDF into a structured base template
   (`data/base/resume_base.md`), generating multiple bullet-point variants for
   each experience/project bullet. Also writes a sibling
   `resume_base.suggestions.md` with adjacent-skill suggestions for you to
   review — nothing in it is used until you manually copy an entry into your
   real `## Skills` line.
2. **Edit (optional):** Manually edit your resume after parsing to add
   additional projects, experiences, or points for the tailor step. Run the
   review module to create additional re-writes on each point.
3. **Tailor (per job):** Given a job posting URL, extract the job description,
   assess how well your base resume fits it, and — if it clears the fit bar —
   select/rewrite bullets to match and export a one-page PDF, retrying with
   trim passes if it overflows. A below-threshold fit stops here: no resume is
   generated, so you don't spend tailoring effort on a job you'd pass on.

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

| Variable                    | Default                     | Description                                        |
|------------------------------|------------------------------|-----------------------------------------------------|
| `CLAUDE_MODEL`                | `claude-sonnet-5`            | Model used for all LLM calls                        |
| `DATA_DIR`                    | `data`                       | Root dir for base resume + job descriptions          |
| `OUTPUT_DIR`                  | `output`                     | Where tailored `.md`/`.pdf` files are written        |
| `BASE_RESUME_PATH`            | `data/base/resume_base.md`   | Path to the generated base resume                    |
| `MAX_BULLET_VARIANTS`         | `5`                          | Variants generated per experience bullet             |
| `MAX_PROJECT_BULLET_VARIANTS` | `3`                          | Variants generated per project bullet                |
| `PAGE_TRIM_ATTEMPTS`          | `3`                          | Retries to fit tailored resume on one page           |
| `MIN_FIT_SCORE`               | `0.4`                        | Fit score (0.0–1.0) below which tailoring is skipped |
| `MIN_JD_CHARS`                | `200`                        | Minimum scraped text length to treat as a real posting |

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
result to `data/base/resume_base.md`, plus a `data/base/resume_base.suggestions.md`
file listing any closely-adjacent skills Claude noticed evidence for but that
aren't in your Skills list — review it and copy over anything accurate; nothing
in it is ever used automatically.

The generated markdown is meant to be hand-edited afterward — add/remove
bullets, tweak variants, fix parsing mistakes — before tailoring against jobs.

### `review` — re-sync a hand-edited base resume

```bash
uv run resume-agent review
```

Re-parses `data/base/resume_base.md` after you've manually edited it and
backfills bullet variants for any new/changed bullets, leaving
already-reviewed bullets untouched. Also refreshes
`resume_base.suggestions.md`. Run this after editing the base resume by hand.

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
1. Scrape the job posting and reject it early (with a clear error) if the page
   looks too short or otherwise doesn't look like an actual job description
2. In one combined call, extract structured data from it → `data/jobs/<company>-<role>.md`
   and assess how well your base resume fits it (fit score + reasoning + gaps). If
   the score is below `MIN_FIT_SCORE`, the run stops here — **no resume is
   generated** — so you're not spending tailoring effort on a job you'd pass on
3. Otherwise, rewrite/select bullets tailored to the job, retrying up to
   `PAGE_TRIM_ATTEMPTS` times if the result doesn't fit one page
4. Write `output/<company>-<role>.md` and `output/<company>-<role>.pdf`
5. Review the finished resume against the job description and write
   `output/<company>-<role>.assessment.md` — a post-tailoring fit score, ATS
   keyword coverage, and a per-bullet relevance breakdown (flagging weak bullets
   worth cutting on a future edit). This report is never appended to the resume
   itself — it's a separate file for you to read, not something sent to employers

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
├── errors.py        # Shared exception hierarchy (ResumeAgentError and friends)
├── config/          # Pydantic settings, loaded from .env
├── models/          # Resume, JobDescription data contracts
├── tools/           # PDF read/export, page counting, job-page scraping, LLM call wrapper
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

## Roadmap

Planned/under consideration:

- **Model-agnostic framework** — the pipeline is currently coupled to the
  Anthropic SDK (`tools/llm.py`'s `call_llm_json`/`call_llm_text`, and the
  `CLAUDE_MODEL` setting). Abstracting that call layer behind a provider-neutral
  interface would let every prompt module run against other providers/models
  without touching pipeline or prompt code.
