from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    ollama_url: str
    ollama_model: str
    home_assistant_url: str | None
    home_assistant_token: str | None
    allowed_entities: frozenset[str]

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv()
        entities = os.getenv("HOME_ASSISTANT_ALLOWED_ENTITIES", "")
        return cls(
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
            home_assistant_url=(os.getenv("HOME_ASSISTANT_URL") or "").rstrip("/") or None,
            home_assistant_token=os.getenv("HOME_ASSISTANT_TOKEN") or None,
            allowed_entities=frozenset(
                item.strip() for item in entities.split(",") if item.strip()
            ),
        )
