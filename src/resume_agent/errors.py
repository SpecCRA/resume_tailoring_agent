class ResumeAgentError(Exception):
    """Base class for anticipated, user-facing pipeline failures."""


class ScrapingError(ResumeAgentError):
    """Fetching the job posting failed."""


class InvalidJobDescriptionError(ResumeAgentError):
    """The fetched content doesn't look like an actual job description."""


class LLMResponseError(ResumeAgentError):
    """An LLM call returned output that couldn't be parsed or validated."""
