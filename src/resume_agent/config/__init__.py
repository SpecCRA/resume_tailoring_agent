"""Re-exports `Settings`/`settings` so callers can `from resume_agent.config import
settings` rather than reaching into the `config.config` submodule."""

from resume_agent.config.config import Settings, settings

__all__ = ["Settings", "settings"]
