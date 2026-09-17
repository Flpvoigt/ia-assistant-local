from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .core.config import APP_DATA_ROOT

MANIFEST_URL = os.getenv(
    "ORACULO_UPDATE_MANIFEST_URL",
    "https://oraculo-desktop.vercel.app/update.json",
)
UPDATE_ROOT = APP_DATA_ROOT / "updates"
PENDING_FILE = UPDATE_ROOT / "pending.json"
PID_FILE = APP_DATA_ROOT / "oraculo.pid"
LOG_FILE = APP_DATA_ROOT / "update.log"
INSTALLER_FLAGS = (
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CLOSEAPPLICATIONS",
    "/FORCECLOSEAPPLICATIONS",
)


def version_key(value: str) -> tuple[int, ...]:
    parts = value.strip().lstrip("v").split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError("Versão de atualização inválida.")
    return tuple(int(part) for part in parts)


def validate_manifest(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("Manifesto de atualização inválido.")
    version = str(payload.get("version", "")).strip()
    url = str(payload.get("url", "")).strip()
    sha256 = str(payload.get("sha256", "")).strip().lower()
    version_key(version)
    if not url.startswith("https://"):
        raise ValueError("O instalador precisa usar HTTPS.")
    if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
        raise ValueError("SHA-256 do instalador inválido.")
    size = int(payload.get("size", 0))
    if size <= 0:
        raise ValueError("Tamanho do instalador inválido.")
    return {
        "version": version,
        "url": url,
        "sha256": sha256,
        "size": size,
        "notes": list(payload.get("notes", [])),
    }


def installer_matches(path: Path, expected_sha256: str, expected_size: int) -> bool:
    if not path.is_file() or path.stat().st_size != expected_size:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower() == expected_sha256.lower()


def _log(message: str) -> None:
    APP_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as stream:
        stream.write(f"[{timestamp}] {message}\n")


def _process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    process_query_limited_information = 0x1000
    still_active = 259
    handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
        process_query_limited_information, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(  # type: ignore[attr-defined]
            handle, ctypes.byref(exit_code)
        ):
            return False
        return exit_code.value == still_active
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]


def app_is_running() -> bool:
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if _process_running(pid):
        return True
    PID_FILE.unlink(missing_ok=True)
    return False


def fetch_manifest() -> dict[str, Any]:
    response = httpx.get(MANIFEST_URL, timeout=25, follow_redirects=True, trust_env=False)
    response.raise_for_status()
    return validate_manifest(response.json())


def _installer_path(version: str) -> Path:
    return UPDATE_ROOT / f"Oraculo-Setup-{version}.exe"


def download_installer(manifest: dict[str, Any]) -> Path:
    UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
    destination = _installer_path(manifest["version"])
    if installer_matches(destination, manifest["sha256"], manifest["size"]):
        return destination
    partial = destination.with_suffix(".part")
    digest = hashlib.sha256()
    total = 0
    try:
        with httpx.stream(
            "GET",
            manifest["url"],
            timeout=120,
            follow_redirects=True,
            trust_env=False,
        ) as response:
            response.raise_for_status()
            with partial.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
        if total != manifest["size"] or digest.hexdigest().lower() != manifest["sha256"]:
            raise ValueError("O instalador baixado não passou na verificação de segurança.")
        os.replace(partial, destination)
        return destination
    finally:
        partial.unlink(missing_ok=True)


def _save_pending(manifest: dict[str, Any], installer: Path) -> None:
    pending = {
        "version": manifest["version"],
        "path": str(installer),
        "sha256": manifest["sha256"],
        "size": manifest["size"],
    }
    PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8")


def _load_pending() -> tuple[dict[str, Any], Path] | None:
    try:
        pending = validate_manifest(
            {
                **json.loads(PENDING_FILE.read_text(encoding="utf-8")),
                "url": "https://local.invalid/installer",
            }
        )
        installer = Path(json.loads(PENDING_FILE.read_text(encoding="utf-8"))["path"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        PENDING_FILE.unlink(missing_ok=True)
        return None
    if not installer_matches(installer, pending["sha256"], pending["size"]):
        PENDING_FILE.unlink(missing_ok=True)
        return None
    return pending, installer


def launch_pending_installer() -> bool:
    loaded = _load_pending()
    if loaded is None:
        return False
    pending, installer = loaded
    if version_key(pending["version"]) <= version_key(__version__):
        PENDING_FILE.unlink(missing_ok=True)
        return False
    subprocess.Popen(
        [str(installer), *INSTALLER_FLAGS],
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    PENDING_FILE.unlink(missing_ok=True)
    _log(f"Instalação silenciosa iniciada para a versão {pending['version']}.")
    return True


def check_for_update() -> str:
    manifest = fetch_manifest()
    if version_key(manifest["version"]) <= version_key(__version__):
        return "up-to-date"
    installer = download_installer(manifest)
    _save_pending(manifest, installer)
    _log(f"Versão {manifest['version']} baixada e verificada.")
    if not app_is_running() and launch_pending_installer():
        return "installing"
    return "pending"


def _spawn_worker(arguments: list[str]) -> None:
    if not getattr(sys, "frozen", False):
        main(["--worker", *arguments])
        return
    UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
    worker = UPDATE_ROOT / "OraculoUpdater-worker.exe"
    try:
        shutil.copy2(Path(sys.executable), worker)
    except PermissionError:
        if not worker.is_file():
            raise
    subprocess.Popen(
        [str(worker), "--worker", *arguments],
        close_fds=True,
        creationflags=(
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        ),
    )


def _wait_for_process(pid: int, timeout_seconds: int = 600) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while _process_running(pid) and time.monotonic() < deadline:
        time.sleep(1)
    return not _process_running(pid)


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--apply-pending", action="store_true")
    parser.add_argument("--wait-pid", type=int, default=0)
    args = parser.parse_args(arguments)
    if not args.worker:
        forwarded = []
        if args.scheduled:
            forwarded.append("--scheduled")
        if args.apply_pending:
            forwarded.append("--apply-pending")
        if args.wait_pid:
            forwarded.extend(("--wait-pid", str(args.wait_pid)))
        _spawn_worker(forwarded)
        return
    try:
        if args.wait_pid and not _wait_for_process(args.wait_pid):
            _log("Atualização adiada porque o Oráculo continuou aberto.")
            return
        if args.apply_pending:
            launch_pending_installer()
            return
        check_for_update()
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        httpx.HTTPError,
        json.JSONDecodeError,
    ) as exc:
        _log(f"Falha ao verificar atualização: {exc}")


if __name__ == "__main__":
    main()
