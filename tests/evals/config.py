"""Model list for critique-persona prompt-quality evals.

Deliberately separate from `resume_agent.config.settings.eval_model` — that
setting picks the single model the production `critique` pipeline runs on,
whereas the question these tests answer ("is this persona prompt any good,
and on which models") only makes sense checked across several models at once.
So this is driven by its own env var, not the app's runtime setting.

Set EVAL_MODELS to a comma-separated list to check more than one model, e.g.:

    EVAL_MODELS=claude-sonnet-5,claude-haiku-4-5-20251001 pytest -m eval tests/evals

Defaults to a single model (the app's configured eval model) if unset, so the
suite still runs meaningfully with zero extra configuration.
"""

import os

from resume_agent.config import settings

EVAL_MODELS = [
    m.strip() for m in os.environ.get("EVAL_MODELS", settings.eval_model).split(",") if m.strip()
]
