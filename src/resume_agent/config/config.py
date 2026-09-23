"""Runtime configuration, loaded from environment variables / a local `.env` file.

`settings` (a module-level `Settings` instance) is the single source of truth for
the Anthropic API key/model, file paths, and every pipeline tuning knob (bullet
variant counts, page-trim attempts, the fit-score and JD-length gates). Imported
directly wherever a pipeline needs a value, e.g. `from resume_agent.config import
settings`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    anthropic_api_key: str
    claude_model: str = "claude-opus-5-5"
    # Model used for the (opt-in) multi-perspective critique pipeline — deliberately
    # a separate setting from claude_model so the critique personas can run on a
    # different model than the one that wrote the tailored resume, avoiding
    # correlated blind spots between generator and evaluator.
    eval_model: str = "claude-sonnet-5"

    # Paths
    data_dir: str = "data"
    output_dir: str = "output"
    base_resume_path: str = "data/base/resume_base.md"

    # Tuning
    max_bullet_variants: int = 5
    max_project_bullet_variants: int = 3
    page_trim_attempts: int = 3
    min_fit_score: float = 0.4
    min_jd_chars: int = 200

    def __repr__(self):
        return self.model_dump(exclude={"anthropic_api_key"}, mode="json")

    def __str__(self):
        fields = self.model_dump(exclude={"anthropic_api_key"})
        lines = "\n".join(f"  {key}: {value}" for key, value in fields.items())
        return f"Settings(\n{lines}\n)"


settings = Settings()
