from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path | None = None) -> None:
    path = path or PROJECT_ROOT / ".env"
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
    groq_api_key: str | None
    groq_url: str
    groq_model: str
    database_path: Path
    home_assistant_url: str | None
    home_assistant_token: str | None
    allowed_entities: frozenset[str]

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv()
        entities = os.getenv("HOME_ASSISTANT_ALLOWED_ENTITIES", "")
        database_path = Path(
            os.getenv("ORACULO_DATABASE_PATH", str(PROJECT_ROOT / "data" / "oraculo.db"))
        )
        if not database_path.is_absolute():
            database_path = PROJECT_ROOT / database_path
        return cls(
            groq_api_key=os.getenv("GROQ_API_KEY") or None,
            groq_url=os.getenv("GROQ_URL", "https://api.groq.com/openai/v1").rstrip("/"),
            groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            database_path=database_path,
            home_assistant_url=(os.getenv("HOME_ASSISTANT_URL") or "").rstrip("/") or None,
            home_assistant_token=os.getenv("HOME_ASSISTANT_TOKEN") or None,
            allowed_entities=frozenset(
                item.strip() for item in entities.split(",") if item.strip()
            ),
        )
