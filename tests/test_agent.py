from unittest.mock import Mock, patch

import pytest

from ia_assistant_local.ai.agent import LocalAgent


def test_groq_chat_uses_server_side_api_key():
    tools = Mock()
    tools.schemas.return_value = []
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Ola!"}}]
    }

    with patch(
        "ia_assistant_local.ai.agent.httpx.post", return_value=response
    ) as post:
        answer = LocalAgent(
            "https://api.groq.com/openai/v1",
            "openai/gpt-oss-120b",
            tools,
            api_key="secret",
        ).ask("Oi", lambda _: False)

    assert answer == "Ola!"
    assert post.call_args.args[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer secret"}


def test_missing_groq_key_is_reported_before_request():
    agent = LocalAgent("https://api.groq.com/openai/v1", "model", Mock())

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        agent.ask("Oi", lambda _: False)


def test_memory_extraction_accepts_only_json_list():
    tools = Mock()
    response = Mock()
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"memories": ["O usuário prefere respostas curtas"]}'
                }
            }
        ]
    }

    with patch("ia_assistant_local.ai.agent.httpx.post", return_value=response):
        memories = LocalAgent(
            "https://api.groq.com/openai/v1",
            "openai/gpt-oss-120b",
            tools,
            api_key="secret",
        ).extract_memories("Prefiro respostas curtas", [])

    assert memories == ["O usuário prefere respostas curtas"]
