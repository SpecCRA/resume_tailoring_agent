# Resume Tailoring Agent

A Claude-powered CLI that turns one base resume into a job-specific, one-page
PDF for every posting you apply to. It parses your resume once, then for each
job posting scrapes the description, assesses whether your resume is a strong
enough fit to bother tailoring, and — if so — selects/rewrites bullets to
match, iteratively refines the result against its own review feedback, and
exports a clean ATS-friendly PDF.

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
   `review` command to backfill variants for anything new.
3. **Tailor (per job):** Given a job posting URL, scrape and extract the job
   description, assess how well your base resume fits it, and — if it clears
   the fit bar — select/rewrite bullets to match, review the result against the
   posting, refine it using that review's own findings until fit stops
   improving, and export a one-page PDF. A below-threshold fit stops here: no
   resume is generated, so you don't spend tailoring effort on a job you'd pass
   on.

Every `tailor` run — screened out or fully tailored — is logged to
`data/usage_log.csv`, and every job description's raw scraped text is saved to
`data/jobs/<slug>.raw.txt`, so you have a running history and something to
inspect when a scrape goes wrong.

## Requirements

- Python >= 3.10
- An [Anthropic API key](https://console.anthropic.com/)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
git clone <this-repo>
cd resume_tailoring_agent
uv sync
uv run playwright install chromium
```

WeasyPrint (PDF export) has native dependencies (Pango, cairo, etc.) — see the
[WeasyPrint install docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)
if PDF export fails on your OS.

The `playwright install chromium` step is a one-time browser download used as
a scraping fallback for job postings that are pure client-rendered JavaScript
apps with no server-side fallback (see **Scraping strategy** below) — skipping
it just means that fallback quietly does nothing instead of erroring, so
`tailor` still works for every other posting.

## Configuration

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Optional settings (defaults shown) — see
[src/resume_agent/config/config.py](src/resume_agent/config/config.py):

| Variable                      | Default                     | Description                                             |
|--------------------------------|------------------------------|----------------------------------------------------------|
| `CLAUDE_MODEL`                 | `claude-opus-5-5`            | Model used for the main setup/tailor pipeline            |
| `EVAL_MODEL`                   | `claude-sonnet-5.5`          | Model used for the `critique` command's five personas — deliberately overridable to differ from `CLAUDE_MODEL`, so the evaluator isn't the same model that wrote the resume |
| `ALWAYS_INCLUDE_EXPERIENCE_TITLE` | *(unset)*                 | When set, tailoring always keeps the Experience entry with this exact title (capped to one short bullet), regardless of JD relevance |
| `DATA_DIR`                     | `data`                       | Root dir for base resume, scraped job descriptions, and the usage log |
| `OUTPUT_DIR`                   | `output`                     | Where tailored `.md`/`.pdf`/assessment files are written |
| `BASE_RESUME_PATH`             | `data/base/resume_base.md`   | Path to the generated base resume                         |
| `MAX_BULLET_VARIANTS`          | `5`                          | Variants generated per experience bullet                  |
| `MAX_PROJECT_BULLET_VARIANTS`  | `3`                          | Variants generated per project bullet                     |
| `PAGE_TRIM_ATTEMPTS`           | `3`                          | Retries to fit a tailor/refine pass on one page            |
| `MIN_FIT_SCORE`                | `0.4`                        | Fit score (0.0–1.0) below which tailoring is skipped       |
| `MIN_JD_CHARS`                 | `200`                        | Minimum scraped text length to treat as a real posting     |
| `MAX_REFINE_ATTEMPTS`          | `2`                          | Extra tailor+review rounds tried after the first, each folding the previous round's own feedback back in; stops early once a round stops improving. `0` disables refinement |

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

| Argument/Option     | Required | Description                      |
|----------------------|----------|-----------------------------------|
| `url`                | yes      | Job posting URL to scrape         |
| `--company` / `-c`   | yes      | Company name (used in filenames)  |
| `--role` / `-r`      | yes      | Job title (used in filenames)     |

This will:
1. **Scrape** the posting (see **Scraping strategy** below), saving the raw
   text to `data/jobs/<slug>.raw.txt` (even on a too-short scrape — useful for
   diagnosing one), and reject it early if the page looks too short or
   doesn't look like an actual job description
2. **Extract + assess**, in one call: structured data → `data/jobs/<slug>.md`,
   plus a fit score/reasoning/gaps for your base resume against it. Below
   `MIN_FIT_SCORE`, the run stops here — **no resume is generated** — so you
   don't spend tailoring effort on a job you'd pass on
3. **Tailor**: select/rewrite bullets for the job, retrying with trim passes
   up to `PAGE_TRIM_ATTEMPTS` times until it fits one page
4. **Review** the tailored output against the JD — a fit score, a per-bullet
   relevance breakdown (each with a one-line reason), ATS keyword coverage,
   and suggestions for improving fit/ATS coverage grounded only in content
   already present elsewhere in your full base resume (an unused bullet
   variant, a skill demonstrated but not listed) — never anything invented
5. **Refine**: feed that review's own remaining gaps and suggestions back into
   another tailor+review round, repeating (up to `MAX_REFINE_ATTEMPTS` times)
   until a round fails to beat the best fit score found so far — the output
   keeps improving instead of stopping at the first attempt
6. **Export**: write `output/<slug>.md`, `output/<slug>.pdf`, and
   `output/<slug>.assessment.md` (the final review from step 4/5 — never
   appended into the resume itself, just a separate file for you to read)

Every run (PASS or APPLY) also appends one row to `data/usage_log.csv` — date,
company, role, verdict, and every assessment number produced (screening fit
score, and, once tailoring runs, final fit score, ATS keyword coverage,
remaining gaps, low-relevance bullet count, and refinement rounds accepted) —
a running history across every job you've pointed this at, not just the
latest one.

### `export` — re-export an existing markdown resume to PDF

```bash
uv run resume-agent export output/acme-corp-senior-data-engineer.md
```

| Argument/Option   | Required | Description                                          |
|--------------------|----------|--------------------------------------------------------|
| `markdown`         | yes      | Path to an existing markdown resume                    |
| `--output` / `-o`  | no       | Output PDF path (defaults next to the input file)       |

No LLM calls — just re-renders a markdown file (the base resume, a previously
tailored resume, or anything else you've hand-edited) to PDF, enforcing the
same one-page limit as `tailor`. Since there's no LLM in the loop to trim and
retry here, a page-count violation is raised as an error instead of
auto-corrected — trim the source markdown and re-run.

### `critique` — multi-perspective review of a tailored resume (opt-in)

```bash
uv run resume-agent critique acme-corp-senior-data-engineer
```

| Argument | Required | Description                                                    |
|----------|----------|------------------------------------------------------------------|
| `slug`   | yes      | The `<slug>` from an already-tailored `output/<slug>.md` (i.e. `company-role`) |

Runs five independent persona reviews, concurrently, against an
already-tailored resume — each scoped to a distinct failure mode the
automatic tailor-step review doesn't check:

- **ATS Parser Simulation** — structural parseability (headers, dates,
  formatting), not keyword presence
- **Recruiter 6-Second Skim** — prominence/ordering: is the strongest
  qualification visible without scrolling
- **Hiring Manager Technical Depth** — is each bullet's claimed scope/impact
  specific and credible, or vague/buzzword-only
- **Integrity Auditor** — an independent fabrication check, run without the
  job description so it can't rationalize a claim just because the JD wants it
- **Narrative Coherence** — does the sequence of roles/projects read as a
  deliberate throughline

Writes `output/<slug>.critique.md`, including a "Cross-Persona Agreement"
section when two or more personas independently flag the same spot. Not run
automatically by `tailor` — it's five extra LLM calls and purely advisory, so
it's a separate command you run only when you want the extra scrutiny. Runs on
`EVAL_MODEL`, not `CLAUDE_MODEL` (see Configuration above).

## Scraping strategy

Job postings are hosted on wildly different platforms, so `fetch_job_text`
(in `tools/web_scraper.py`) tries progressively more expensive techniques,
escalating only when a cheaper one comes up short (below `MIN_JD_CHARS`):

1. A plain HTTP GET, with boilerplate tags (nav/footer/script/etc.) stripped
2. A small registry of known ATS-embed-widget redirects (e.g. a career page
   embedding Ashby's job-board widget) to that platform's own hosted URL for
   the same posting — fast and reliable when recognized
3. Extracting a `schema.org JobPosting` block from a `<script
   type="application/ld+json">` tag, if present — many ATS-hosted pages don't
   render the posting into the visible DOM at all, but keep this block for
   Google for Jobs indexing
4. A full headless-browser render (Playwright + Chromium), reading whichever
   frame on the rendered page has the most text — the general fallback for
   client-rendered SPAs with no server-side shortcut, checking every iframe
   since a third-party widget's content commonly lives in one. Fails soft (no
   crash) if Playwright/Chromium isn't installed.

## Typical workflow

```bash
# 1. One-time: parse your resume
uv run resume-agent setup data/input/resume.pdf

# 2. (Optional) hand-edit data/base/resume_base.md, then re-sync
uv run resume-agent review

# 3. For each job you apply to:
uv run resume-agent tailor "<job-url>" -c "Company" -r "Role Title"

# 4. (Optional) extra scrutiny on the result:
uv run resume-agent critique company-role-title
```

## Project layout

```
src/resume_agent/
├── main.py          # CLI entrypoint (typer) — setup / review / tailor / export / critique
├── errors.py        # Shared exception hierarchy (ResumeAgentError and friends)
├── config/          # Pydantic settings, loaded from .env
├── models/          # Resume, JobDescription, review, critique data contracts
├── tools/           # LLM call wrapper, PDF read/export, page counting, job-page
│                     scraping, the Resume<->markdown round-trip, ATS keyword
│                     matching, the usage log — no pipeline logic or prompt text
├── prompts/         # LLM prompt builders for each pipeline step
└── pipelines/       # setup.py, tailor.py, export.py, critique.py orchestration
```

Each pipeline step has its own prompt module under `prompts/`:

| Prompt module                | Used by              | Purpose                                                        |
|-------------------------------|-----------------------|------------------------------------------------------------------|
| `parse_resume.py`             | `setup`               | PDF text → structured `Resume`                                   |
| `rewrite_bullets.py`          | `setup`/`review`      | Generate phrasing variants per bullet                             |
| `suggest_adjacent_skills.py`  | `setup`/`review`      | Propose evidenced-but-unlisted skills for manual review            |
| `extract_and_assess.py`       | `tailor` (step 2)     | JD text → structured `JobDescription` + fit score                  |
| `tailor_resume.py`            | `tailor` (step 3)     | Select/rewrite bullets for the JD (the core anti-fabrication rules) |
| `review_output.py`            | `tailor` (step 4/5)   | Score the tailored output + per-bullet reasons + improvement suggestions |
| `refine_resume.py`            | `tailor` (step 5)     | Re-tailor using the previous review's own feedback                  |
| `critique.py`                 | `critique`            | Five independent persona reviews                                   |

## Development

```bash
uv sync --dev
uv run pytest              # run unit + integration tests (mocked LLM calls, no API key needed)
uv run ruff check .        # lint
uv run mypy .              # type check
```

`tests/evals/` is a separate suite that hits the real Anthropic API to check
the `critique` personas' prompt quality (recall/precision against hand-built
fixtures with planted defects) — it costs money and isn't run by default:

```bash
uv run pytest -m eval tests/evals --no-cov

# Check more than one model at once (comma-separated):
EVAL_MODELS=claude-sonnet-5,claude-haiku-4-5-20251001 uv run pytest -m eval tests/evals --no-cov
```

## Roadmap

Planned/under consideration:

- **Model-agnostic framework** — the pipeline is currently coupled to the
  Anthropic SDK (`tools/llm.py`'s `call_llm_json`/`call_llm_text`, and the
  `CLAUDE_MODEL` setting). Abstracting that call layer behind a provider-neutral
  interface would let every prompt module run against other providers/models
  without touching pipeline or prompt code.
