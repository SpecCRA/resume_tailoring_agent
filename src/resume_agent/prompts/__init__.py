"""Prompt templates for every Claude call in the pipeline. Each module exports a
`SYSTEM` string and a `build(...)` function that returns the user-turn prompt text;
callers pass both straight to `tools/llm.py`'s `call_llm_json`/`call_llm_text`.
No module here calls the API itself — that's left to the pipelines.
"""
