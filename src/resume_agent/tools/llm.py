import json
import re
from typing import Any

import anthropic

from resume_agent.config import settings
from resume_agent.errors import LLMResponseError


def call_llm_text(client: anthropic.Anthropic, *, system: str, prompt: str, max_tokens: int) -> str:
    """Call Claude with a system+user prompt and return the response text."""
    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return extract_text(message)
    except ValueError as e:
        raise LLMResponseError(str(e)) from e


def call_llm_json(client: anthropic.Anthropic, *, system: str, prompt: str, max_tokens: int) -> Any:
    """Call Claude with a system+user prompt and parse the response as JSON.

    Retries once with a corrective instruction if the first response isn't
    parseable JSON — Claude occasionally deviates from the requested format.
    """
    last_error: Exception | None = None
    for attempt in range(2):
        current_prompt = (
            prompt
            if attempt == 0
            else prompt
            + "\n\nIMPORTANT: Your previous response was not valid JSON. Return ONLY "
            "the raw JSON object described above — no markdown fences, no other text."
        )
        message = client.messages.create(
            model=settings.claude_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": current_prompt}],
        )
        try:
            return extract_json(message)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e

    raise LLMResponseError(f"LLM did not return valid JSON after 2 attempts: {last_error}")


def extract_text(message: anthropic.types.Message) -> str:
    """Return the first text block's content from a Claude response.

    content[0] isn't reliably the text block — Claude can prepend a
    ThinkingBlock (or other non-text block), so we scan for the first
    TextBlock instead of indexing blindly.
    """
    for block in message.content:
        if block.type == "text":
            return block.text
    block_types = [block.type for block in message.content]
    raise ValueError(
        f"No text block in response (stop_reason={message.stop_reason!r}, "
        f"blocks={block_types!r}) — likely hit max_tokens before any output text; "
        "increase max_tokens for this call."
    )


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def extract_json(message: anthropic.types.Message) -> Any:
    """Parse the response's text block as JSON.

    Despite prompts asking for raw JSON, Claude sometimes wraps the object in
    a ```json ... ``` markdown fence anyway — strip it before parsing.
    """
    text = _FENCE_RE.sub("", extract_text(message).strip())
    return json.loads(text)
