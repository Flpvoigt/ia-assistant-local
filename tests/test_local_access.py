import threading
from types import SimpleNamespace

import httpx
import pytest

from ia_assistant_local.core.memory import MemoryStore
from ia_assistant_local.web.server import AssistantServer


def test_local_profile_is_stable_and_has_no_admin_access(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    user = store.bootstrap_local_user()
    store.add_memory(user["id"], "Prefiro respostas curtas")

    assert store.bootstrap_local_user()["id"] == user["id"]
    assert store.local_user() == user
    assert user["role"] == "member"
    assert user["admin_access"] is False
    assert user["must_change_password"] is False
    assert len(store.list_memories(user["id"])) == 1
    assert store.permissions_for_user(user["id"])["memory_access"] is True
    assert store.permissions_for_user(user["id"])["terminal_access"] is False


def test_app_opens_without_login_and_team_login_remains_optional(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    local = store.bootstrap_local_user()
    credentials = dict(store.bootstrap_admins())
    settings = SimpleNamespace(groq_api_key="secret", groq_model="model")
    server = AssistantServer(("127.0.0.1", 0), object(), settings, store, local_access=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", trust_env=False
        ) as client:
            assert client.get("/api/me").json()["user"] == local
            assert client.get("/api/status").json()["user"] == local
            assert client.get("/api/chats").status_code == 200
            assert client.get("/api/admin/chats").status_code == 403
            blocked = client.post(
                "/api/login",
                json={"username": "will", "password": credentials["will"]},
                headers={"Origin": "https://evil.example"},
            )
            assert blocked.status_code == 403
            assert client.get("/api/me", headers={"Host": "evil.example"}).status_code == 403
            login = client.post(
                "/api/login", json={"username": "will", "password": credentials["will"]}
            )
            assert login.status_code == 200
            assert client.get("/api/me").json()["user"]["username"] == "will"
            assert client.get("/api/admin/chats").status_code == 200
            assert client.post("/api/logout").status_code == 200
            assert client.get("/api/me").json()["user"] == local
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_passwordless_profile_cannot_be_exposed_on_network(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    with pytest.raises(ValueError, match="somente local"):
        AssistantServer(("0.0.0.0", 0), object(), object(), store, local_access=True)
