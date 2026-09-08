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
    assert store.update_user_permissions(
        felipe["id"], will["id"], updated
    ) == updated
    assert store.has_permission(will["id"], "system_info")
    assert not store.has_permission(will["id"], "memory_access")

    with pytest.raises(PermissionError, match="não podem ser reduzidas"):
        store.update_user_permissions(felipe["id"], felipe["id"], updated)

    with pytest.raises(PermissionError, match="administrador-chefe"):
        store.update_user_permissions(will["id"], will["id"], updated)
