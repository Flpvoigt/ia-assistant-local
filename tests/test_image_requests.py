import threading
from types import SimpleNamespace

import httpx

from ia_assistant_local.core.memory import MemoryStore
from ia_assistant_local.web.server import AssistantServer


class ImageAgent:
    def __init__(self):
        self.calls = []
        self.limited = False

    def ask(
        self,
        text,
        confirm,
        history=None,
        memories=None,
        allowed_tools=None,
        model=None,
        reasoning_effort=None,
        images=None,
    ):
        self.calls.append((text, images))
        if self.limited:
            response = httpx.Response(
                429,
                headers={"retry-after": "12"},
                request=httpx.Request("POST", "https://example.test/chat"),
            )
            response.raise_for_status()
        return "Imagem recebida"


def test_image_without_text_and_rate_limit(tmp_path):
    memory = MemoryStore(tmp_path / "test.db")
    credentials = dict(memory.bootstrap_admins())
    agent = ImageAgent()
    server = AssistantServer(
        ("127.0.0.1", 0), agent, SimpleNamespace(groq_api_key="test", groq_model="test"), memory
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", trust_env=False
        ) as client:
            client.post("/api/login", json={"username": "will", "password": credentials["will"]})
            client.post(
                "/api/change-password",
                json={
                    "current_password": credentials["will"],
                    "new_password": "test-password-safe",
                },
            )
            payload = {
                "message": "",
                "mode": "temporary",
                "image_consent": True,
                "approved_images": ["data:image/png;base64,iVBORw0KGgo="],
            }
            assert client.post("/api/chat", json=payload).status_code == 200
            assert agent.calls[-1][0] == "Descreva esta imagem."
            assert agent.calls[-1][1]
            assert client.post("/api/chat", json={"message": ""}).status_code == 400
            assert (
                client.post("/api/chat", json={**payload, "image_consent": False}).status_code
                == 400
            )
            agent.limited = True
            count = len(agent.calls)
            response = client.post("/api/chat", json=payload)
            assert response.status_code == 429
            assert response.json()["retry_after"] == 12
            assert response.json()["code"] == "groq_rate_limit"
            assert len(agent.calls) == count + 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
