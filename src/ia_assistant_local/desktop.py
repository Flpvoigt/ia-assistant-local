from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

import httpx

from .core.config import APP_DATA_ROOT, BUNDLE_ROOT, ENV_PATH
from .core.voice import install_voice_assets, voice_status, warm_voice
from .web.server import HOST, PORT, create_server

PID_FILE = APP_DATA_ROOT / "oraculo.pid"


def _read_env_value(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.strip().startswith(f"{key}="):
            return raw_line.split("=", 1)[1].strip()
    return ""


def _write_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    replacement = f"{key}={value}"
    updated = False
    output: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            output.append(replacement)
            updated = True
        else:
            output.append(line)
    if not updated:
        output.append(replacement)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _prepare_user_config() -> None:
    APP_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    (APP_DATA_ROOT / "data").mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists():
        template = BUNDLE_ROOT / ".env.example"
        if template.is_file():
            shutil.copyfile(template, ENV_PATH)
        else:
            ENV_PATH.write_text(
                "GROQ_API_KEY=\n"
                "GROQ_URL=https://api.groq.com/openai/v1\n"
                "GROQ_MODEL=openai/gpt-oss-120b\n",
                encoding="utf-8",
            )


def _validate_key(key: str) -> tuple[bool, str]:
    if not key.startswith("gsk_") or len(key) < 30:
        return False, "A chave deve começar com gsk_."
    url = _read_env_value(ENV_PATH, "GROQ_URL") or "https://api.groq.com/openai/v1"
    try:
        response = httpx.get(
            url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=20,
            trust_env=False,
        )
    except httpx.HTTPError:
        return True, ""
    if response.status_code == 200:
        return True, ""
    if response.status_code == 401:
        return False, "A Groq recusou essa chave. Crie uma chave nova e tente novamente."
    return False, f"A Groq respondeu com HTTP {response.status_code}."


def _require_personal_groq_key() -> bool:
    current = _read_env_value(ENV_PATH, "GROQ_API_KEY")
    if current:
        valid, reason = _validate_key(current)
        if valid:
            os.environ["GROQ_API_KEY"] = current
            return True
    else:
        reason = ""
    root = tk.Tk()
    root.withdraw()
    try:
        if reason:
            messagebox.showwarning("Chave Groq", reason, parent=root)
        while True:
            key = simpledialog.askstring(
                "Configuração do Oráculo",
                "Insira sua chave pessoal da Groq.\n"
                "Crie gratuitamente em https://console.groq.com/keys\n\n"
                "A chave ficará salva somente neste computador.",
                show="•",
                parent=root,
            )
            if key is None:
                return False
            key = key.strip()
            valid, reason = _validate_key(key)
            if valid:
                _write_env_value(ENV_PATH, "GROQ_API_KEY", key)
                os.environ["GROQ_API_KEY"] = key
                return True
            messagebox.showerror("Chave inválida", reason, parent=root)
    finally:
        root.destroy()


def _show_created_accounts(accounts: list[tuple[str, str]]) -> None:
    if not accounts:
        return
    root = tk.Tk()
    root.title("Contas locais do Oráculo")
    root.geometry("560x360")
    root.resizable(False, False)
    root.configure(bg="#100d16")
    title = tk.Label(
        root,
        text="Acesso opcional da equipe",
        bg="#100d16",
        fg="#f4edff",
        font=("Segoe UI", 16, "bold"),
    )
    title.pack(pady=(24, 8))
    note = tk.Label(
        root,
        text=(
            "O Oráculo abre sem login. Guarde estas credenciais somente se você "
            "for usar a área administrativa."
        ),
        bg="#100d16",
        fg="#aaa1b5",
        font=("Segoe UI", 9),
        wraplength=500,
    )
    note.pack(pady=(0, 16))
    credentials = "\n".join(f"{username}: {password}" for username, password in accounts)
    text = tk.Text(
        root,
        height=8,
        width=58,
        bg="#09070d",
        fg="#7ee9f5",
        insertbackground="#ffffff",
        relief="flat",
        font=("Consolas", 11),
        padx=14,
        pady=12,
    )
    text.insert("1.0", credentials)
    text.configure(state="disabled")
    text.pack(padx=24)

    def copy_and_close() -> None:
        root.clipboard_clear()
        root.clipboard_append(credentials)
        root.update()
        root.destroy()

    button = tk.Button(
        root,
        text="Copiar e continuar",
        command=copy_and_close,
        bg="#7136a8",
        fg="#ffffff",
        activebackground="#8744c2",
        activeforeground="#ffffff",
        relief="flat",
        padx=18,
        pady=8,
        font=("Segoe UI", 10, "bold"),
    )
    button.pack(pady=20)
    root.protocol("WM_DELETE_WINDOW", copy_and_close)
    root.mainloop()


def _prepare_voice() -> None:
    try:
        if not voice_status()["ready"]:
            install_voice_assets()
        warm_voice()
    except (OSError, RuntimeError, ValueError):
        return


def _run_desktop() -> None:
    _prepare_user_config()
    if not _require_personal_groq_key():
        return
    try:
        server, created_accounts = create_server()
    except OSError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Oráculo",
            f"Não foi possível iniciar o serviço local: {exc}",
            parent=root,
        )
        root.destroy()
        return
    _show_created_accounts(created_accounts)
    server_thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="oraculo-local-server",
    )
    server_thread.start()
    threading.Thread(
        target=_prepare_voice,
        daemon=True,
        name="oraculo-voice-setup",
    ).start()

    # Import dynamically so static analyzers do not require pywebview in the
    # environment used to inspect the package.
    import importlib

    webview = importlib.import_module("webview")

    url = f"http://{HOST}:{PORT}"
    webview.create_window(
        "Oráculo",
        url,
        width=1360,
        height=860,
        min_size=(960, 640),
        background_color="#08060d",
        confirm_close=True,
    )
    try:
        webview.start(
            private_mode=False,
            storage_path=str(APP_DATA_ROOT / "webview"),
        )
    finally:
        server.shutdown()
        server.server_close()


def _start_updater(*arguments: str) -> None:
    updater = Path(sys.executable).with_name("OraculoUpdater.exe")
    if not getattr(sys, "frozen", False) or not updater.is_file():
        return
    try:
        subprocess.Popen(
            [str(updater), *arguments],
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return


def main() -> None:
    APP_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    _start_updater("--scheduled")
    try:
        _run_desktop()
    finally:
        try:
            if PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        _start_updater("--apply-pending", "--wait-pid", str(os.getpid()))


if __name__ == "__main__":
    main()
