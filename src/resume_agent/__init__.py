"""Resume tailoring agent: a Claude-powered pipeline that turns one base resume
into a job-specific, ATS-ready PDF for a given job posting.

Two entry points (see `main.py`): `setup`/`review` (pipelines/setup.py) build and
maintain the base resume once; `tailor` (pipelines/tailor.py) runs the per-job
scrape -> assess -> tailor -> export flow.
"""
