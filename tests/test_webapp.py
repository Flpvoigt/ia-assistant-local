import threading
from types import SimpleNamespace

import httpx

from ia_assistant_local.memory import MemoryStore
from ia_assistant_local.webapp import AssistantServer


class DummyAgent:
    def ask(self, text, confirm, history=None, memories=None):
        return f"Resposta para: {text}"

    def extract_memories(self, text, existing):
        return ["Memória automática de teste"]


def test_chat_isolation_and_owner_audit(tmp_path):
    memory = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(memory.bootstrap_admins())
    settings = SimpleNamespace(groq_api_key="secret", groq_model="model")
    server = AssistantServer(("127.0.0.1", 0), DummyAgent(), settings, memory)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with httpx.Client(base_url=base_url, trust_env=False) as will:
            login = will.post(
                "/api/login",
                json={"username": "will", "password": credentials["will"]},
            )
            assert login.status_code == 200
            changed = will.post(
                "/api/change-password",
                json={
                    "current_password": credentials["will"],
                    "new_password": "senha-segura-will",
                },
            )
            assert changed.status_code == 200
            chat = will.post("/api/chat", json={"message": "Olá", "chat_id": None})
            assert chat.status_code == 200
            chat_id = chat.json()["chat_id"]
            assert len(will.get("/api/chats").json()["chats"]) == 1
            assert will.get("/api/admin/chats").status_code == 403

        with httpx.Client(base_url=base_url, trust_env=False) as felipe:
            login = felipe.post(
                "/api/login",
                json={"username": "felipe", "password": credentials["felipe"]},
            )
            assert login.json()["user"]["role"] == "owner"
            audit = felipe.get("/api/admin/chats")
            assert audit.status_code == 200
            assert audit.json()["chats"][0]["username"] == "will"
            detail = felipe.get(f"/api/admin/chats/{chat_id}")
            assert detail.status_code == 200
            assert detail.json()["chat"]["display_name"] == "Will"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
