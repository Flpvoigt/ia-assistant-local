import sqlite3

import pytest

from ia_assistant_local.core.memory import PERMISSION_LABELS, MemoryStore


def test_three_admins_are_created_with_isolated_memory(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(store.bootstrap_admins())

    assert set(credentials) == {"will", "gustavo", "felipe"}

    token, will = store.login("will", credentials["will"])
    assert will["role"] == "admin"
    assert will["must_change_password"] is True
    assert store.current_user(token)["username"] == "will"

    store.change_password(will["id"], credentials["will"], "senha-nova-segura")
    assert store.current_user(token)["must_change_password"] is False

    chat_id = store.create_chat(will["id"], "Minha mensagem")
    store.add_message(will["id"], chat_id, "user", "Minha mensagem")
    store.add_memory(will["id"], "Prefiro respostas curtas")

    _, gustavo = store.login("gustavo", credentials["gustavo"])
    assert store.list_chats(gustavo["id"]) == []
    assert store.list_memories(gustavo["id"]) == []
    assert store.chat_messages(will["id"], chat_id)[0]["content"] == "Minha mensagem"
    assert store.list_memories(will["id"])[0]["content"] == "Prefiro respostas curtas"

    _, felipe = store.login("felipe", credentials["felipe"])
    assert felipe["role"] == "owner"
    audited = store.audit_chats(felipe["id"])
    assert audited[0]["username"] == "will"
    assert store.audit_messages(felipe["id"], chat_id)["messages"][0]["content"] == (
        "Minha mensagem"
    )

    with pytest.raises(PermissionError, match="administrador-chefe"):
        store.audit_chats(will["id"])


def test_invalid_password_is_rejected(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    store.bootstrap_admins()

    with pytest.raises(PermissionError, match="inválidos"):
        store.login("will", "senha-incorreta")


def test_owner_has_permanent_full_access_and_controls_admin_permissions(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(store.bootstrap_admins())
    _, will = store.login("will", credentials["will"])
    _, felipe = store.login("felipe", credentials["felipe"])

    assert all(store.permissions_for_user(felipe["id"]).values())
    updated = {key: False for key in PERMISSION_LABELS}
    updated["system_info"] = True
    assert store.update_user_permissions(felipe["id"], will["id"], updated) == updated
    assert store.has_permission(will["id"], "system_info")
    assert not store.has_permission(will["id"], "memory_access")

    with pytest.raises(PermissionError, match="não podem ser reduzidas"):
        store.update_user_permissions(felipe["id"], felipe["id"], updated)

    with pytest.raises(PermissionError, match="administrador-chefe"):
        store.update_user_permissions(will["id"], will["id"], updated)


def test_structured_memory_updates_without_duplicates(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(store.bootstrap_admins())
    _, will = store.login("will", credentials["will"])

    assert (
        store.upsert_memory(
            will["id"],
            "preference",
            "preference.response_style",
            "O usuário prefere respostas curtas.",
        )
        == "created"
    )
    assert (
        store.upsert_memory(
            will["id"],
            "preference",
            "response_style",
            "O usuário prefere respostas detalhadas.",
        )
        == "updated"
    )
    memories = store.list_memories(will["id"])
    assert len(memories) == 1
    assert memories[0]["category"] == "preference"
    assert memories[0]["memory_key"] == "preference.response_style"
    assert memories[0]["content"] == "O usuário prefere respostas detalhadas."

    assert store.delete_memory_by_key(will["id"], "preference.response_style")
    assert store.list_memories(will["id"]) == []


def test_legacy_memories_are_migrated_without_data_loss(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(user_id, content)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO memories (user_id, content, created_at)
            VALUES (1, 'Memória antiga', 123)
            """
        )

    store = MemoryStore(database)
    memory = store.list_memories(1)[0]
    assert memory["content"] == "Memória antiga"
    assert memory["category"] == "personal"
    assert memory["memory_key"].startswith("personal.legacy_")
    assert memory["updated_at"] == 123


def test_shared_room_model_preference_search_and_health(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(store.bootstrap_admins())
    _, will = store.login("will", credentials["will"])
    _, gustavo = store.login("gustavo", credentials["gustavo"])

    shared = store.shared_chat(will["id"])
    assert store.shared_chat(gustavo["id"])["id"] == shared["id"]
    store.add_message(will["id"], shared["id"], "user", "Teste compartilhado")
    messages = store.chat_messages(gustavo["id"], shared["id"])
    assert messages[0]["display_name"] == "Will"
    assert messages[0]["content"] == "Teste compartilhado"

    store.set_selected_model(will["id"], "modelo-rapido")
    assert store.selected_model(will["id"], "padrao") == "modelo-rapido"
    assert store.selected_model(gustavo["id"], "padrao") == "padrao"
    assert store.reasoning_effort(will["id"]) == "medium"
    store.set_model_preference(will["id"], "modelo-rapido", "high")
    assert store.reasoning_effort(will["id"]) == "high"

    results = store.search(gustavo["id"], "compartilhado")
    assert results[0]["scope"] == "shared"
    store.record_usage(will["id"], "modelo-rapido", True)
    health = store.health_summary()
    assert health["requests_24h"] == 1
    assert health["errors_24h"] == 0
