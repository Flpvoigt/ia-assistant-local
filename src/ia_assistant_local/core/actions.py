from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MAX_FILE_BYTES = 750_000
MAX_CONTEXT_CHARS = 12_000
SAFE_EXTENSIONS = {
    ".c",
    ".cpp",
    ".css",
    ".csv",
    ".go",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".md",
    ".php",
    ".ps1",
    ".py",
    ".rs",
    ".sql",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
BLOCKED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".env",
}
COMMANDS = {
    "list_files": ("Listar arquivos", ["cmd.exe", "/d", "/c", "dir"]),
    "git_status": ("Git status", ["git", "status", "--short"]),
    "git_diff": ("Resumo do Git diff", ["git", "diff", "--stat"]),
    "git_log": ("Últimos commits", ["git", "log", "-5", "--oneline"]),
    "tests": ("Executar testes", [sys.executable, "-m", "pytest", "-q"]),
    "lint": ("Verificar código", [sys.executable, "-m", "ruff", "check", "."]),
    "python_version": ("Versão do Python", [sys.executable, "--version"]),
}


def validate_folder(raw_path: str) -> Path:
    if not raw_path.strip():
        raise ValueError("Informe uma pasta.")
    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError("Pasta não encontrada ou sem permissão de leitura.") from exc
    if not path.is_dir():
        raise ValueError("O caminho precisa apontar para uma pasta.")
    return path


def search_folder_context(paths: list[str], query: str) -> list[dict[str, str]]:
    terms = [term.casefold() for term in query.split() if len(term) >= 3][:8]
    if not terms:
        return []
    results: list[dict[str, str]] = []
    total_chars = 0
    for raw_path in paths[:5]:
        try:
            root = validate_folder(raw_path)
        except (OSError, ValueError):
            continue
        inspected = 0
        for current, directories, files in os.walk(root):
            directories[:] = [
                name
                for name in directories
                if name not in BLOCKED_PARTS and not name.startswith(".")
            ]
            for filename in files:
                inspected += 1
                if inspected > 500 or len(results) >= 8:
                    break
                file_path = Path(current, filename)
                if (
                    filename.startswith(".")
                    or file_path.suffix.lower() not in SAFE_EXTENSIONS
                    or any(part in BLOCKED_PARTS for part in file_path.parts)
                ):
                    continue
                try:
                    if file_path.stat().st_size > MAX_FILE_BYTES:
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                lowered = content.casefold()
                if not any(term in lowered or term in filename.casefold() for term in terms):
                    continue
                matching_lines = [
                    line.strip()
                    for line in content.splitlines()
                    if any(term in line.casefold() for term in terms)
                ][:8]
                snippet = "\n".join(matching_lines)[:1800]
                if not snippet:
                    snippet = content[:800]
                total_chars += len(snippet)
                if total_chars > MAX_CONTEXT_CHARS:
                    return results
                results.append({"path": str(file_path.relative_to(root)), "content": snippet})
            if inspected > 500 or len(results) >= 8:
                break
    return results


def command_preview(action: str) -> dict[str, str]:
    definition = COMMANDS.get(action)
    if definition is None:
        raise PermissionError("Comando não permitido.")
    label, command = definition
    return {"action": action, "label": label, "command": " ".join(command)}


def execute_command(action: str, working_directory: str) -> dict[str, object]:
    definition = COMMANDS.get(action)
    if definition is None:
        raise PermissionError("Comando não permitido.")
    label, command = definition
    directory = validate_folder(working_directory)
    try:
        completed = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"label": label, "ok": False, "output": str(exc)[:8000]}
    output = (completed.stdout + completed.stderr).strip()[:20_000]
    return {
        "label": label,
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "output": output or "Comando concluído sem saída.",
    }
