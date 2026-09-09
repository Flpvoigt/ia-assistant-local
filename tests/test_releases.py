import json
import subprocess

import pytest

from ia_assistant_local.core.releases import (
    MANIFEST,
    next_version,
    prepare_release,
    publish_release,
)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


@pytest.fixture
def release_repo(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Release test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "README.md").write_text("Initial\n")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "Initial")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "origin", "main")
    return root


def test_release_is_reviewed_and_increments(release_repo):
    root = release_repo
    (root / "README.md").write_text("New features\n")
    plan = prepare_release(root, 1, ["Guia de teste"])
    assert plan["version"] == "1.5"
    assert git(root, "log", "-1", "--format=%s") == "Initial"
    result = publish_release(root, 1, plan["token"])
    assert result["published"]
    assert json.loads((root / MANIFEST).read_text(encoding="utf-8"))["version"] == "1.5"
    assert git(root, "ls-remote", "origin", "refs/heads/main").split()[0] == result["commit"]
    assert prepare_release(root, 1, ["Outra melhoria"])["version"] == "2.0"
    assert next_version("2.0") == "2.5"
    with pytest.raises(ValueError):
        publish_release(root, 1, plan["token"])


def test_rejects_changes_after_review_and_wrong_user(release_repo):
    root = release_repo
    plan = prepare_release(root, 1, ["Revisão"])
    with pytest.raises(ValueError):
        publish_release(root, 2, plan["token"])
    plan = prepare_release(root, 1, ["Revisão"])
    (root / "README.md").write_text("Changed after review\n")
    with pytest.raises(ValueError):
        publish_release(root, 1, plan["token"])
    assert git(root, "log", "-1", "--format=%s") == "Initial"


def test_blocks_secrets_and_staging(release_repo):
    root = release_repo
    (root / "README.md").write_text("gsk_" + "a" * 25)
    with pytest.raises(ValueError, match="segredo"):
        prepare_release(root, 1, ["Teste"])
    (root / "README.md").write_text("Safe\n")
    git(root, "add", "README.md")
    with pytest.raises(ValueError, match="preparados"):
        prepare_release(root, 1, ["Teste"])
