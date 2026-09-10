import sqlite3
import time

import pytest

from ia_assistant_local.core.background_tasks import TaskManager
from ia_assistant_local.core.memory import MemoryStore
from ia_assistant_local.core.vault import decrypt_secret, encrypt_secret


def test_vault_uses_authenticated_encryption_and_isolated_metadata(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(store.bootstrap_admins())
    _, will = store.login("will", credentials["will"])
    _, gustavo = store.login("gustavo", credentials["gustavo"])

    salt, nonce, ciphertext = encrypt_secret("senha-muito-segura", "segredo privado")
    item_id = store.create_vault_item(will["id"], "Laboratório", salt, nonce, ciphertext)

    item = store.vault_item(will["id"], item_id)
    assert (
        decrypt_secret("senha-muito-segura", item["salt"], item["nonce"], item["ciphertext"])
        == "segredo privado"
    )
    assert store.list_vault_items(gustavo["id"]) == []
    with pytest.raises(PermissionError):
        store.vault_item(gustavo["id"], item_id)
    with pytest.raises(ValueError, match="incorreta"):
        decrypt_secret("senha-totalmente-errada", salt, nonce, ciphertext)

    with sqlite3.connect(tmp_path / "oraculo.db") as connection:
        raw = connection.execute(
            "SELECT ciphertext FROM vault_items WHERE id = ?", (item_id,)
        ).fetchone()[0]
    assert "segredo privado" not in raw


def test_memory_conflict_requires_an_explicit_choice(tmp_path):
    store = MemoryStore(tmp_path / "oraculo.db")
    credentials = dict(store.bootstrap_admins())
    _, will = store.login("will", credentials["will"])
    _, gustavo = store.login("gustavo", credentials["gustavo"])
    store.upsert_memory(will["id"], "preference", "theme", "Prefiro tema escuro")

    conflict_id = store.create_memory_conflict(
        will["id"],
        "preference",
        "theme",
        "Prefiro tema escuro",
        "Prefiro tema claro",
    )
    assert store.memory_for_key(will["id"], "preference", "theme")["content"] == (
        "Prefiro tema escuro"
    )
    assert store.list_memory_conflicts(gustavo["id"]) == []
    assert store.resolve_memory_conflict(will["id"], conflict_id, "new")
    assert store.memory_for_key(will["id"], "preference", "theme")["content"] == (
        "Prefiro tema claro"
    )
    assert store.list_memory_conflicts(will["id"]) == []


def test_background_tasks_report_progress_and_isolate_users():
    manager = TaskManager(workers=1)
    try:
        task = manager.create(
            1,
            "extract",
            "documento.pdf",
            lambda cancel, progress: progress(70) or {"content": "resultado"},
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            current = manager.get(1, task["id"])
            if current["status"] == "completed":
                break
            time.sleep(0.01)
        assert current["progress"] == 100
        assert current["result"]["content"] == "resultado"
        with pytest.raises(PermissionError):
            manager.get(2, task["id"])
    finally:
        manager.shutdown()
