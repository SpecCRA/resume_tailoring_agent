"""Shared fixtures for critique-persona evals.

Unlike tests/unit and tests/integration, these hit the real Anthropic API — see
the `eval` marker (registered in pyproject.toml) for why they're excluded from
the default `pytest` run.
"""

from pathlib import Path

import anthropic
import pytest
from dotenv import dotenv_values

_EVALS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark every test collected from this directory as `eval`, rather
    than requiring `pytestmark = pytest.mark.eval` in each test file — a
    module-level `pytestmark` set here in conftest.py would NOT propagate to
    sibling test modules, so this hook is the reliable way to make sure every
    eval test (including future ones) is excluded from the default run."""
    for item in items:
        if _EVALS_DIR in Path(item.fspath).parents:
            item.add_marker(pytest.mark.eval)


@pytest.fixture(scope="session")
def real_client() -> anthropic.Anthropic:
    """A real Anthropic client, built from the actual .env file rather than
    `settings.anthropic_api_key`.

    tests/conftest.py injects a placeholder ANTHROPIC_API_KEY into the process
    environment so unit/integration tests (which mock every LLM call) can
    import resume_agent.config without a real key present. Environment
    variables take precedence over .env in pydantic-settings, so that
    placeholder would silently shadow the real key here too if we went through
    `settings`. Evals hit the live API, so they need the genuine key — read
    straight from .env, bypassing the already-polluted environment.
    """
    api_key = dotenv_values(".env").get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("No real ANTHROPIC_API_KEY in .env — evals need a live API key.")
    return anthropic.Anthropic(api_key=api_key)
