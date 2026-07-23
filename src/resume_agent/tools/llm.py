import json
import re
from typing import Any

import anthropic


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
