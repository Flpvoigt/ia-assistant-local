import json
from unittest.mock import Mock, patch

import pytest

from ia_assistant_local.ai.agent import SYSTEM_PROMPT, LocalAgent


def test_groq_chat_uses_server_side_api_key():
    tools = Mock()
    tools.schemas.return_value = []
    response = Mock()
    response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Ola!"}}]
    }

    with patch("ia_assistant_local.ai.agent.httpx.post", return_value=response) as post:
        answer = LocalAgent(
            "https://api.groq.com/openai/v1",
            "openai/gpt-oss-120b",
            tools,
            api_key="secret",
        ).ask("Oi", lambda _: False, reasoning_effort="high")

    assert answer == "Ola!"
    assert post.call_args.args[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer secret"}
    assert post.call_args.kwargs["json"]["reasoning_effort"] == "high"


def test_missing_groq_key_is_reported_before_request():
    agent = LocalAgent("https://api.groq.com/openai/v1", "model", Mock())

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        agent.ask("Oi", lambda _: False)


def test_memory_extraction_accepts_structured_updates():
    tools = Mock()
    response = Mock()
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"upserts":[{"category":"preference",'
                        '"key":"preference.response_style",'
                        '"content":"O usuário prefere respostas curtas."}],'
                        '"forget_keys":[]}'
                    )
                }
            }
        ]
    }

    with patch("ia_assistant_local.ai.agent.httpx.post", return_value=response) as post:
        memories = LocalAgent(
            "https://api.groq.com/openai/v1",
            "openai/gpt-oss-120b",
            tools,
            api_key="secret",
        ).extract_memories(
            "Mano, prefiro respostas curtas",
            [],
            recent_user_messages=["Mano, explica isso", "Mano, resume aí"],
        )

    assert memories == {
        "upserts": [
            {
                "category": "preference",
                "key": "preference.response_style",
                "content": "O usuário prefere respostas curtas.",
            }
        ],
        "forget_keys": [],
    }
    extraction_input = json.loads(
        post.call_args.kwargs["json"]["messages"][1]["content"]
    )
    assert extraction_input["recent_user_messages"] == [
        "Mano, explica isso",
        "Mano, resume aí",
    ]
    assert "mascote" in SYSTEM_PROMPT.casefold()
    assert "primeira mensagem" in SYSTEM_PROMPT.casefold()
    assert "recursos administrativos" in SYSTEM_PROMPT.casefold()
