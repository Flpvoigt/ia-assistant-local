from __future__ import annotations

import hashlib
import json
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path

from .updater import _git as _run_git

MANIFEST = "src/ia_assistant_local/web/release.json"
LOCK = threading.Lock()
PLANS: dict[str, dict] = {}
ALLOWED_ROOT = {
    "README.md",
    "SECURITY.md",
    "requirements.txt",
    "pyproject.toml",
    "start.ps1",
    "install.ps1",
    "start.sh",
    "install.sh",
    ".gitignore",
    ".env.example",
}
SUFFIXES = {".py", ".html", ".js", ".css", ".json", ".md", ".svg", ".webmanifest", ".txt"}
PRIVATE = re.compile(
    r"(^|/)(data|\.git|\.venv|node_modules|__pycache__|\.ssh)(/|$)|\.(db|key|pem|pfx|sqlite)$",
    re.IGNORECASE,
)
SECRET = re.compile(
    r"gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)


def _git(root: Path, *args: str) -> str:
    try:
        return _run_git(root, *args)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "O Git não concluiu a operação. Verifique acesso ao remoto, "
            "identidade de commit e estado do repositório no terminal."
        ) from exc


def release_info(root: Path) -> dict:
    path = root / MANIFEST
    if not path.exists():
        return {"version": "1.0", "published": False, "notes": []}
    return json.loads(path.read_text(encoding="utf-8"))


def next_version(current: str) -> str:
    match = re.fullmatch(r"(\d+)\.(0|5)", current)
    if not match:
        raise ValueError("Versão inválida. Use incrementos de 0.5.")
    major, minor = int(match[1]), int(match[2])
    return f"{major + (minor == 5)}.{5 if minor == 0 else 0}"


def _snapshot(root: Path) -> dict:
    if _git(root, "diff", "--cached", "--name-only"):
        raise ValueError("Há arquivos preparados no Git. Revise o staging antes do lançamento.")
    branch = _git(root, "branch", "--show-current")
    if branch != "main":
        raise ValueError("O lançamento exige a branch main. Mescle suas alterações antes.")
    remote = _git(root, "remote", "get-url", "origin")
    if re.search(r"https?://[^/]*@", remote):
        raise ValueError("Remova credenciais embutidas no endereço do remoto.")
    head = _git(root, "rev-parse", "HEAD")
    remote_head = _git(root, "ls-remote", "origin", "refs/heads/main").split()
    if not remote_head or remote_head[0] != head:
        raise ValueError(
            "A main local e a remota precisam estar sincronizadas antes de lançar. Revise os commits pendentes no Git."
        )
    paths = set(_git(root, "diff", "--name-only", "-z", "HEAD").split("\0"))
    paths.update(_git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
    paths.discard("")
    # Ensure no private file already tracked would travel with the project.
    tracked = _git(root, "ls-files", "-z").split("\0")
    for name in tracked:
        if PRIVATE.search(name) or (Path(name).name.startswith(".env") and name != ".env.example"):
            raise ValueError(
                "Há arquivos privados rastreados. Revise o repositório antes de publicar."
            )
    digest = hashlib.sha256(head.encode())
    for name in sorted(paths):
        if name not in ALLOWED_ROOT and not (
            name.startswith(("src/", "tests/", "docs/")) and Path(name).suffix.lower() in SUFFIXES
        ):
            raise ValueError(f"Arquivo fora da lista de lançamento: {name}. Revise-o manualmente.")
        path = root / name
        if (
            PRIVATE.search(name)
            or path.is_symlink()
            or not path.resolve().is_relative_to(root.resolve())
        ):
            raise ValueError("Arquivo privado ou link não permitido no lançamento.")
        raw = path.read_bytes() if path.exists() else b"<deleted>"
        if len(raw) > 2_000_000:
            raise ValueError(f"Arquivo grande demais para revisão automática: {name}")
        if SECRET.search(raw.decode("utf-8", errors="replace")):
            raise ValueError(f"Possível segredo detectado em {name}. Remova-o antes de lançar.")
        digest.update(name.encode() + b"\0" + raw)
    return {
        "head": head,
        "branch": branch,
        "remote": remote,
        "files": sorted(paths),
        "digest": digest.hexdigest(),
    }


def prepare_release(root: Path, user_id: int, notes: list[str]) -> dict:
    if not isinstance(notes, list) or not notes or len(notes) > 12:
        raise ValueError("Informe de 1 a 12 novidades para o guia.")
    clean = [str(note).strip() for note in notes]
    if any(not note or len(note) > 240 or SECRET.search(note) for note in clean):
        raise ValueError("Cada novidade deve ter até 240 caracteres e não conter segredos.")
    with LOCK:
        plan = _snapshot(root)
        plan.update(
            version=next_version(release_info(root)["version"]),
            notes=clean,
            user_id=user_id,
            created=time.monotonic(),
            root=str(root.resolve()),
        )
        token = secrets.token_urlsafe(24)
        PLANS.clear()
        PLANS[token] = plan
        return {key: plan[key] for key in ("version", "notes", "files", "branch", "remote")} | {
            "token": token
        }


def publish_release(root: Path, user_id: int, token: str) -> dict:
    with LOCK:
        plan = PLANS.pop(token, None)
        if (
            not plan
            or plan["user_id"] != user_id
            or plan["root"] != str(root.resolve())
            or time.monotonic() - plan["created"] > 300
        ):
            raise ValueError("Prévia expirada. Verifique novamente antes de lançar.")
        current = _snapshot(root)
        if current != {key: plan[key] for key in current}:
            raise ValueError("Arquivos ou destino mudaram após a revisão. Gere outra prévia.")
        manifest = root / MANIFEST
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {"version": plan["version"], "published": True, "notes": plan["notes"]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        files = sorted(set(plan["files"]) | {MANIFEST})
        try:
            _git(root, "add", "--", *files)
            _git(root, "commit", "-m", f"Oráculo {plan['version']}")
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                "Não foi possível criar o commit. Revise os arquivos preparados no Git; nada foi enviado."
            ) from exc
        commit = _git(root, "rev-parse", "HEAD")
        try:
            _git(root, "push", "origin", "HEAD:refs/heads/main")
        except (RuntimeError, subprocess.TimeoutExpired):
            return {
                "published": False,
                "version": plan["version"],
                "commit": commit,
                "message": "O commit foi criado, mas o envio não foi confirmado. Não lance outra versão: confira o Git remoto e conclua o push deste commit.",
            }
        return {
            "published": True,
            "version": plan["version"],
            "commit": commit,
            "message": "Versão enviada. A equipe deve atualizar o projeto e reiniciar o Oráculo.",
        }
