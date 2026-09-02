from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from .tools import ToolRegistry

SYSTEM_PROMPT = """Voce e um assistente local em portugues brasileiro.
Use somente as ferramentas fornecidas e nunca invente que uma acao foi executada.
Se uma ferramenta falhar ou for negada, explique claramente. Seja breve e seguro."""


class LocalAgent:
    def __init__(self, url: str, model: str, tools: ToolRegistry):
        self.url = url
        self.model = model
        self.tools = tools
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def ask(self, text: str, confirm: Callable[[str], bool]) -> str:
        self.messages.append({"role": "user", "content": text})
        for _ in range(5):
            message = self._chat()
            self.messages.append(message)
            calls = message.get("tool_calls") or []
            if not calls:
                return message.get("content") or "Sem resposta."
            for call in calls:
                function = call.get("function", {})
                name = function.get("name", "")
                arguments = function.get("arguments") or {}
                try:
                    result = self.tools.execute(name, arguments, confirm)
                except (OSError, RuntimeError, TypeError, ValueError, httpx.HTTPError) as exc:
                    result = {"error": str(exc)}
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        return "Limite de chamadas de ferramentas atingido."

    def _chat(self) -> dict:
        response = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "messages": self.messages,
                "tools": self.tools.schemas(),
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]
