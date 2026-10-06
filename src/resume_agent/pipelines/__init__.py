"""The pipelines the CLI drives: `setup.py` (build/maintain the base resume,
once), `tailor.py` (scrape -> assess -> tailor -> review -> refine -> export,
per job), `export.py` (re-export an existing markdown resume to PDF, no LLM
calls), and `critique.py` (opt-in, five-persona review of a tailored resume)."""
