from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, timeout=45, check=False
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Falha no Git.").strip())
    return result.stdout.strip()


def update_status(root: Path, check_remote: bool = False) -> dict[str, object]:
    branch = _git(root, "branch", "--show-current") or "detached"
    current = _git(root, "rev-parse", "--short", "HEAD")
    dirty = bool(_git(root, "status", "--porcelain"))
    result: dict[str, object] = {"branch": branch, "current": current, "dirty": dirty, "remote_checked": False, "update_available": None}
    if check_remote:
        remote = _git(root, "ls-remote", "origin", f"refs/heads/{branch}")
        remote_sha = remote.split()[0] if remote else ""
        local_sha = _git(root, "rev-parse", "HEAD")
        result.update({"remote_checked": True, "remote": remote_sha[:7], "update_available": bool(remote_sha and remote_sha != local_sha)})
    return result


def apply_update(root: Path, database_path: Path) -> dict[str, object]:
    status = update_status(root)
    if status["dirty"]:
        return {"ok": False, "error": "Há alterações locais. Faça commit antes de atualizar."}
    before = _git(root, "rev-parse", "HEAD")
    backup = database_path.with_name(f"{database_path.stem}.pre-update-{before[:7]}.db")
    if database_path.exists():
        with sqlite3.connect(database_path) as source, sqlite3.connect(backup) as destination:
            source.backup(destination)
    _git(root, "pull", "--ff-only", "origin", str(status["branch"]))
    after = _git(root, "rev-parse", "HEAD")
    return {"ok": True, "before": before[:7], "after": after[:7], "backup": str(backup) if database_path.exists() else None, "restart_required": before != after}
