import pytest

from ia_assistant_local.core.actions import command_preview, search_folder_context, validate_folder


def test_folder_search_is_read_only_and_skips_secrets(tmp_path):
    (tmp_path / "documento.md").write_text("Oráculo seguro", encoding="utf-8")
    (tmp_path / ".env").write_text("ORACULO_SECRET=nao-ler", encoding="utf-8")

    assert validate_folder(str(tmp_path)) == tmp_path.resolve()
    results = search_folder_context([str(tmp_path)], "Oráculo")
    assert results == [{"path": "documento.md", "content": "Oráculo seguro"}]
    assert search_folder_context([str(tmp_path)], "ORACULO_SECRET") == []


def test_terminal_preview_only_accepts_exact_allowlist():
    preview = command_preview("git_status")
    assert preview["action"] == "git_status"
    assert "git status" in preview["command"]

    with pytest.raises(PermissionError, match="não permitido"):
        command_preview("git status && comando-perigoso")
