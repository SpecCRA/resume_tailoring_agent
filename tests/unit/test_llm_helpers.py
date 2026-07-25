from unittest.mock import MagicMock

import pytest

from resume_agent.errors import LLMResponseError
from resume_agent.tools.llm import call_llm_json


def _fake_message(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def test_call_llm_json_retries_once_on_invalid_json_then_succeeds():
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_message("not valid json at all"),
        _fake_message('{"ok": true}'),
    ]

    result = call_llm_json(fake_client, system="sys", prompt="prompt", max_tokens=100)

    assert result == {"ok": True}
    assert fake_client.messages.create.call_count == 2
    # The retry call should include a corrective instruction.
    retry_content = fake_client.messages.create.call_args_list[1].kwargs["messages"][0]["content"]
    assert "not valid JSON" in retry_content


def test_call_llm_json_raises_llm_response_error_after_two_failures():
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [
        _fake_message("still not json"),
        _fake_message("also not json"),
    ]

    with pytest.raises(LLMResponseError):
        call_llm_json(fake_client, system="sys", prompt="prompt", max_tokens=100)

    assert fake_client.messages.create.call_count == 2
