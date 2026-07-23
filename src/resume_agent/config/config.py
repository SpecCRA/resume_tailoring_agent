from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-5"

    # Paths
    data_dir: str = "data"
    output_dir: str = "output"
    base_resume_path: str = "data/base/resume_base.md"

    # Tuning
    max_bullet_variants: int = 5
    page_trim_attempts: int = 3

    def __repr__(self):
        return self.model_dump(exclude={"anthropic_api_key"}, mode="json")

    def __str__(self):
        fields = self.model_dump(exclude={"anthropic_api_key"})
        lines = "\n".join(f"  {key}: {value}" for key, value in fields.items())
        return f"Settings(\n{lines}\n)"

    class Config:
        env_file = ".env"


settings = Settings()
