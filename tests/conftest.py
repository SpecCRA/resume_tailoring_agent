import os

# Settings() is instantiated at import time in resume_agent.config, so the
# required ANTHROPIC_API_KEY env var must be set before that module is first
# imported anywhere in the test session.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
