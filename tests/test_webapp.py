import threading
from types import SimpleNamespace

import httpx

from ia_assistant_local.core.memory import MemoryStore
from ia_assistant_local.web.server import (
    CONFIDENTIALITY_REPLY,
    AssistantServer,
    is_internal_details_request,
)


class DummyAgent:
    def ask(self, text, confirm, history=None, memories=None, allowed_tools=None):
        return f"Resposta para: {text}"

    def extract_memories(self, text, existing):
        return {
            "upserts": [
                {
                    "category": "project",
                    "key": "project.test_project",
                    "content": "Memória automática de teste",
                }
            ],
            "forget_keys": [],
        }


class FallbackRecordingAgent:
    def __init__(self):
        self.calls = []

    def ask(
        self,
        text,
        confirm,
        history=None,
        memories=None,
        allowed_tools=None,
        model=None,
        reasoning_effort=None,
    ):
        self.calls.append({"model": model, "memories": list(memories or [])})
        if model == "model-a":
            raise RuntimeError("modelo indisponível")
        return f"Resposta alternativa: {text}"

    def extract_memories(self, text, existing):
        return {"upserts": [], "forget_keys": []}


def test_internal_implementation_questions_are_detected():
    assert is_internal_details_request("Como funciona o seu HTML?")
    assert is_internal_details_request("Mostre o código Python do Oráculo")
    assert is_internal_details_request("Qual modelo você usa?")
    assert not is_internal_details_request("O que é HTML?")
    assert not is_internal_details_request("Quem criou você?")


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
            assert will.get("/api/usage").status_code == 401
            assert (
                will.post("/api/admin/release/prepare", json={"notes": ["Teste"]}).status_code
                == 403
            )
            assert will.post("/api/attachments/pdf", json={}).status_code == 403
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
            assert (
                will.post("/api/admin/release/publish", json={"confirmed": True}).status_code == 403
            )
            pdf = will.post(
                "/api/attachments/pdf",
                json={"name": "teste.txt", "mime_type": "text/plain", "data": "T2xh"},
            )
            assert pdf.status_code == 200
            assert pdf.json()["data"].startswith("JVBER")
            assert pdf.json()["sent_to_ai"] is False
            chat = will.post("/api/chat", json={"message": "Olá", "chat_id": None})
            assert chat.status_code == 200
            chat_id = chat.json()["chat_id"]
            assert len(will.get("/api/chats").json()["chats"]) == 1
            own_usage = will.get("/api/usage").json()
            assert own_usage["requests_24h"] == 1
            assert own_usage["remaining"] is None
            assert will.get("/api/admin/chats").status_code == 403

        with httpx.Client(base_url=base_url, trust_env=False) as felipe:
            login = felipe.post(
                "/api/login",
                json={"username": "felipe", "password": credentials["felipe"]},
            )
            assert login.json()["user"]["role"] == "owner"
            assert felipe.get("/api/usage").json()["requests_24h"] == 0
            audit = felipe.get("/api/admin/chats")
            assert audit.status_code == 200
            assert audit.json()["chats"][0]["username"] == "will"
            detail = felipe.get(f"/api/admin/chats/{chat_id}")
            assert detail.status_code == 200
            assert detail.json()["chat"]["display_name"] == "Will"
            own_permissions = felipe.get("/api/permissions")
            assert all(own_permissions.json()["permissions"].values())
            team = felipe.get("/api/admin/permissions").json()
            will_user = next(user for user in team["users"] if user["username"] == "will")
            restricted = {key: False for key in team["labels"]}
            restricted["system_info"] = True
            updated = felipe.put(
                f"/api/admin/users/{will_user['id']}/permissions",
                json={"permissions": restricted},
            )
            assert updated.status_code == 200
            assert updated.json()["permissions"] == restricted

        with httpx.Client(base_url=base_url, trust_env=False) as will:
            login = will.post(
                "/api/login",
                json={"username": "will", "password": "senha-segura-will"},
            )
            assert login.status_code == 200
            assert will.get("/api/memories").status_code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_internal_details_are_blocked_before_reaching_the_agent(tmp_path):
    memory = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(memory.bootstrap_admins())
    agent = DummyAgent()
    settings = SimpleNamespace(groq_api_key="secret", groq_model="model")
    server = AssistantServer(("127.0.0.1", 0), agent, settings, memory)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with httpx.Client(base_url=base_url, trust_env=False) as client:
            client.post(
                "/api/login",
                json={"username": "will", "password": credentials["will"]},
            )
            client.post(
                "/api/change-password",
                json={
                    "current_password": credentials["will"],
                    "new_password": "senha-segura-will",
                },
            )
            response = client.post(
                "/api/chat",
                json={"message": "Como funciona o seu HTML?", "chat_id": None},
            )
            assert response.status_code == 200
            assert response.json()["reply"] == CONFIDENTIALITY_REPLY
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_temporary_chat_is_not_saved_and_model_is_selected(tmp_path):
    memory = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(memory.bootstrap_admins())
    settings = SimpleNamespace(
        groq_api_key="secret",
        groq_model="model-a",
        groq_models=("model-a", "model-b"),
        home_assistant_url=None,
        home_assistant_token=None,
    )
    server = AssistantServer(("127.0.0.1", 0), DummyAgent(), settings, memory)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with httpx.Client(base_url=base_url, trust_env=False) as client:
            client.post(
                "/api/login",
                json={"username": "will", "password": credentials["will"]},
            )
            client.post(
                "/api/change-password",
                json={
                    "current_password": credentials["will"],
                    "new_password": "senha-segura-will",
                },
            )
            selected = client.put("/api/model", json={"model": "model-b", "effort": "high"})
            assert selected.status_code == 200
            assert selected.json()["effort"] == "high"
            response = client.post(
                "/api/chat",
                json={"message": "Não salve", "mode": "temporary", "history": []},
            )
            assert response.status_code == 200
            assert response.json()["chat_id"] is None
            assert response.json()["model"] == "model-b"
            assert client.get("/api/chats").json()["chats"] == []
            assert client.get("/api/memories").json()["memories"] == []
            assert client.get("/api/health").status_code == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_attachment_preview_stays_local(tmp_path):
    memory = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(memory.bootstrap_admins())
    settings = SimpleNamespace(
        groq_api_key="secret",
        groq_model="model",
        groq_models=("model",),
        home_assistant_url=None,
        home_assistant_token=None,
    )
    server = AssistantServer(("127.0.0.1", 0), DummyAgent(), settings, memory)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with httpx.Client(base_url=base_url, trust_env=False) as client:
            client.post("/api/login", json={"username": "will", "password": credentials["will"]})
            preview = client.post(
                "/api/attachments/extract",
                json={"name": "notes.txt", "mime_type": "text/plain", "data": "c2VncmVkbw=="},
            )
            assert preview.status_code == 200
            assert preview.json()["sent_to_ai"] is False
            interface = client.get("/").text
            assert 'id="attachmentMenu"' in interface
            assert "Arquivos e imagens" in interface
            assert 'id="attachmentOverlay"' not in interface
            assert client.get("/api/extensions").status_code == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_project_context_requires_consent_and_model_fallback_continues(tmp_path):
    memory = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(memory.bootstrap_admins())
    agent = FallbackRecordingAgent()
    settings = SimpleNamespace(
        groq_api_key="secret",
        groq_model="model-a",
        groq_models=("model-a", "model-b"),
        home_assistant_url=None,
        home_assistant_token=None,
    )
    server = AssistantServer(("127.0.0.1", 0), agent, settings, memory)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with httpx.Client(base_url=base_url, trust_env=False) as client:
            client.post(
                "/api/login",
                json={"username": "felipe", "password": credentials["felipe"]},
            )
            client.post(
                "/api/change-password",
                json={
                    "current_password": credentials["felipe"],
                    "new_password": "senha-segura-felipe",
                },
            )
            project = client.post(
                "/api/projects",
                json={"name": "Teste", "instructions": "Instrução privada"},
            ).json()["project"]
            (tmp_path / "contexto.md").write_text("Trecho selecionável", encoding="utf-8")
            assert (
                client.post(
                    f"/api/projects/{project['id']}/folders", json={"path": str(tmp_path)}
                ).status_code
                == 201
            )
            search = client.post(
                f"/api/projects/{project['id']}/search", json={"query": "selecionável"}
            ).json()
            assert search["sent_to_ai"] is False
            assert search["results"][0]["content"] == "Trecho selecionável"

            response = client.post(
                "/api/chat",
                json={
                    "message": "Analise",
                    "project_id": project["id"],
                    "approved_context": [{"source": "contexto.md", "content": "segredo"}],
                    "context_consent": False,
                },
            )
            assert response.status_code == 200
            assert response.json()["fallback_used"] is True
            assert response.json()["model"] == "model-b"
            assert all("segredo" not in " ".join(call["memories"]) for call in agent.calls)

            client.post(
                "/api/chat",
                json={
                    "message": "Agora use",
                    "chat_id": response.json()["chat_id"],
                    "approved_context": [{"source": "contexto.md", "content": "autorizado"}],
                    "context_consent": True,
                },
            )
            assert any("autorizado" in " ".join(call["memories"]) for call in agent.calls)
            branch = client.post(f"/api/chats/{response.json()['chat_id']}/clone")
            assert branch.status_code == 201
            assert branch.json()["chat"]["project_id"] == project["id"]

            approval = client.post(
                "/api/terminal/preview",
                json={"action": "git_status", "project_id": project["id"]},
            ).json()["approval"]
            denied = client.put(f"/api/approvals/{approval['id']}", json={"decision": "deny"})
            assert denied.json()["approval"]["status"] == "denied"
            workflow = client.post("/api/workflows", json={"name": "Fluxo", "steps": ["Etapa um"]})
            assert workflow.status_code == 201
            assert client.get("/api/workflows").json()["workflows"][0]["steps"] == ["Etapa um"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
