"""Shared exception hierarchy for anticipated, user-facing pipeline failures.

Pipelines raise these instead of letting a raw `httpx`/`pydantic`/`json` exception
bubble up, so `main.py` can catch one common base class and print a clean message.
An error that isn't one of these represents an unanticipated bug and is left to
surface as a normal traceback.
"""


class ResumeAgentError(Exception):
    """Base class for anticipated, user-facing pipeline failures."""


class ScrapingError(ResumeAgentError):
    """Fetching the job posting failed."""


class InvalidJobDescriptionError(ResumeAgentError):
    """The fetched content doesn't look like an actual job description."""


class LLMResponseError(ResumeAgentError):
    """An LLM call returned output that couldn't be parsed or validated."""


class MarkdownFileNotFoundError(ResumeAgentError):
    """A given markdown resume path doesn't exist."""


class PageLimitExceededError(ResumeAgentError):
    """The exported PDF doesn't fit on a single page."""
