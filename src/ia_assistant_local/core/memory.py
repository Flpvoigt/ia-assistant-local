from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import unicodedata
from pathlib import Path

ADMIN_ACCOUNTS = {
    "will": ("Will", "admin"),
    "gustavo": ("Gustavo", "admin"),
    "felipe": ("Felipe", "owner"),
}
USERNAME_RE = re.compile(r"^[a-z0-9_-]{3,32}$")
SESSION_SECONDS = 60 * 60 * 24 * 30
PERMISSION_LABELS = {
    "memory_access": "Memórias pessoais",
    "context_panel": "Painel de contexto",
    "system_info": "Informações do computador",
    "open_application": "Abrir aplicativos",
    "home_read": "Consultar Home Assistant",
    "home_control": "Controlar Home Assistant",
    "project_access": "Projetos e pastas locais",
    "terminal_access": "Terminal controlado",
}
DEFAULT_ADMIN_PERMISSIONS = {
    "memory_access": True,
    "context_panel": True,
    "system_info": True,
    "open_application": False,
    "home_read": False,
    "home_control": False,
    "project_access": True,
    "terminal_access": False,
}
MEMORY_CATEGORIES = frozenset({"personal", "preference", "project", "goal"})


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash BLOB NOT NULL,
                    password_salt BLOB NOT NULL,
                    role TEXT NOT NULL DEFAULT 'admin',
                    must_change_password INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL DEFAULT 'Nova conversa',
                    scope TEXT NOT NULL DEFAULT 'private',
                    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    category TEXT NOT NULL DEFAULT 'personal',
                    memory_key TEXT,
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    UNIQUE(user_id, content)
                );
                CREATE TABLE IF NOT EXISTS user_permissions (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    permission TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    PRIMARY KEY (user_id, permission)
                );
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    selected_model TEXT,
                    reasoning_effort TEXT NOT NULL DEFAULT 'medium'
                );
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    model TEXT NOT NULL,
                    success INTEGER NOT NULL CHECK (success IN (0, 1)),
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                );
                CREATE TABLE IF NOT EXISTS memory_events (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    memory_id INTEGER,
                    action TEXT NOT NULL CHECK (action IN ('learned', 'updated', 'forgotten')),
                    category TEXT NOT NULL,
                    memory_key TEXT,
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    instructions TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    UNIQUE(user_id, name)
                );
                CREATE TABLE IF NOT EXISTS project_folders (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    UNIQUE(project_id, path)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result TEXT,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    resolved_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    UNIQUE(user_id, name)
                );
                CREATE INDEX IF NOT EXISTS chats_user_id ON chats(user_id, updated_at);
                CREATE INDEX IF NOT EXISTS messages_user_id ON messages(user_id, id);
                CREATE INDEX IF NOT EXISTS memories_user_id ON memories(user_id, id);
                CREATE INDEX IF NOT EXISTS memory_events_user_id
                    ON memory_events(user_id, created_at);
                CREATE INDEX IF NOT EXISTS approvals_user_id
                    ON approvals(user_id, status, created_at);
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(messages)")}
            if "chat_id" not in columns:
                connection.execute(
                    "ALTER TABLE messages ADD COLUMN chat_id INTEGER REFERENCES chats(id)"
                )
            memory_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(memories)")
            }
            if "category" not in memory_columns:
                connection.execute(
                    "ALTER TABLE memories ADD COLUMN category TEXT NOT NULL DEFAULT 'personal'"
                )
            if "memory_key" not in memory_columns:
                connection.execute("ALTER TABLE memories ADD COLUMN memory_key TEXT")
            if "updated_at" not in memory_columns:
                connection.execute("ALTER TABLE memories ADD COLUMN updated_at INTEGER")
            chat_columns = {row["name"] for row in connection.execute("PRAGMA table_info(chats)")}
            if "scope" not in chat_columns:
                connection.execute(
                    "ALTER TABLE chats ADD COLUMN scope TEXT NOT NULL DEFAULT 'private'"
                )
            if "project_id" not in chat_columns:
                connection.execute(
                    "ALTER TABLE chats ADD COLUMN project_id INTEGER REFERENCES projects(id)"
                )
            if "parent_chat_id" not in chat_columns:
                connection.execute(
                    "ALTER TABLE chats ADD COLUMN parent_chat_id INTEGER REFERENCES chats(id)"
                )
            preference_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(user_preferences)")
            }
            if "reasoning_effort" not in preference_columns:
                connection.execute(
                    "ALTER TABLE user_preferences ADD COLUMN reasoning_effort TEXT "
                    "NOT NULL DEFAULT 'medium'"
                )
            connection.execute(
                """
                UPDATE memories
                SET memory_key = 'personal.legacy_' || id
                WHERE memory_key IS NULL OR memory_key = ''
                """
            )
            connection.execute(
                "UPDATE memories SET updated_at = created_at WHERE updated_at IS NULL"
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS memories_user_key
                ON memories(user_id, memory_key)
                """
            )
            connection.execute("UPDATE users SET role = 'owner' WHERE username = 'felipe'")
            connection.execute(
                "UPDATE users SET role = 'admin' WHERE username IN ('will', 'gustavo')"
            )
            event_count = connection.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
            if event_count == 0:
                connection.execute(
                    """
                    INSERT INTO memory_events
                        (user_id, memory_id, action, category, memory_key, content, created_at)
                    SELECT user_id, id, 'learned', category, memory_key, content, created_at
                    FROM memories
                    """
                )
            connection.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS memories_timeline_insert
                AFTER INSERT ON memories
                BEGIN
                    INSERT INTO memory_events
                        (user_id, memory_id, action, category, memory_key, content)
                    VALUES
                        (NEW.user_id, NEW.id, 'learned', NEW.category,
                         NEW.memory_key, NEW.content);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_timeline_update
                AFTER UPDATE OF category, memory_key, content ON memories
                BEGIN
                    INSERT INTO memory_events
                        (user_id, memory_id, action, category, memory_key, content)
                    VALUES
                        (NEW.user_id, NEW.id, 'updated', NEW.category,
                         NEW.memory_key, NEW.content);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_timeline_delete
                BEFORE DELETE ON memories
                BEGIN
                    INSERT INTO memory_events
                        (user_id, memory_id, action, category, memory_key, content)
                    VALUES
                        (OLD.user_id, OLD.id, 'forgotten', OLD.category,
                         OLD.memory_key, OLD.content);
                END;
                """
            )
            legacy_users = connection.execute(
                "SELECT DISTINCT user_id FROM messages WHERE chat_id IS NULL"
            ).fetchall()
            for row in legacy_users:
                cursor = connection.execute(
                    "INSERT INTO chats (user_id, title) VALUES (?, ?)",
                    (row["user_id"], "Conversa anterior"),
                )
                connection.execute(
                    "UPDATE messages SET chat_id = ? WHERE user_id = ? AND chat_id IS NULL",
                    (cursor.lastrowid, row["user_id"]),
                )

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 10:
            raise ValueError("A senha deve ter pelo menos 10 caracteres.")
        if len(password) > 256:
            raise ValueError("A senha é longa demais.")

    def bootstrap_admins(self) -> list[tuple[str, str]]:
        created: list[tuple[str, str]] = []
        with self._connect() as connection:
            for username, (display_name, role) in ADMIN_ACCOUNTS.items():
                exists = connection.execute(
                    "SELECT 1 FROM users WHERE username = ?", (username,)
                ).fetchone()
                if exists:
                    continue
                temporary_password = secrets.token_urlsafe(14)
                salt = secrets.token_bytes(16)
                password_hash = self._password_hash(temporary_password, salt)
                connection.execute(
                    """
                    INSERT INTO users
                        (username, display_name, password_hash, password_salt, role)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (username, display_name, password_hash, salt, role),
                )
                created.append((username, temporary_password))
        return created

    def login(self, username: str, password: str) -> tuple[str, dict]:
        normalized = username.strip().lower()
        if not USERNAME_RE.fullmatch(normalized):
            raise PermissionError("Usuário ou senha inválidos.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username = ?", (normalized,)
            ).fetchone()
            if row is None:
                raise PermissionError("Usuário ou senha inválidos.")
            candidate = self._password_hash(password, row["password_salt"])
            if not hmac.compare_digest(candidate, row["password_hash"]):
                raise PermissionError("Usuário ou senha inválidos.")
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, row["id"], int(time.time()) + SESSION_SECONDS),
            )
        return token, self._public_user(row)

    def current_user(self, token: str | None) -> dict | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.*
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, int(time.time())),
            ).fetchone()
        return self._public_user(row) if row else None

    def logout(self, token: str | None) -> None:
        if not token:
            return
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def change_password(self, user_id: int, current: str, new: str) -> None:
        self._validate_password(new)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_hash, password_salt FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                raise PermissionError("Conta não encontrada.")
            candidate = self._password_hash(current, row["password_salt"])
            if not hmac.compare_digest(candidate, row["password_hash"]):
                raise PermissionError("Senha atual incorreta.")
            salt = secrets.token_bytes(16)
            password_hash = self._password_hash(new, salt)
            connection.execute(
                """
                UPDATE users
                SET password_hash = ?, password_salt = ?, must_change_password = 0
                WHERE id = ?
                """,
                (password_hash, salt, user_id),
            )

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "must_change_password": bool(row["must_change_password"]),
        }

    @staticmethod
    def _chat_title(text: str) -> str:
        clean = " ".join(text.split())
        return clean[:48] + ("…" if len(clean) > 48 else "")

    def create_chat(self, user_id: int, first_message: str, project_id: int | None = None) -> int:
        if project_id is not None:
            self.project(user_id, project_id)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO chats (user_id, title, project_id) VALUES (?, ?, ?)",
                (user_id, self._chat_title(first_message), project_id),
            )
        return int(cursor.lastrowid)

    def shared_chat(self, user_id: int) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, title, created_at, updated_at, scope FROM chats "
                "WHERE scope = 'shared' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    "INSERT INTO chats (user_id, title, scope) VALUES (?, ?, 'shared')",
                    (user_id, "Sala da equipe"),
                )
                row = connection.execute(
                    "SELECT id, title, created_at, updated_at, scope FROM chats WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
        return dict(row)

    def _owns_chat(self, user_id: int, chat_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM chats WHERE id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
        return row is not None

    def _can_access_chat(self, user_id: int, chat_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM chats WHERE id = ? AND (user_id = ? OR scope = 'shared')",
                (chat_id, user_id),
            ).fetchone()
        return row is not None

    def list_chats(self, user_id: int) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chats.id, chats.title, chats.created_at, chats.updated_at,
                       chats.scope, chats.project_id, chats.parent_chat_id,
                       projects.name AS project_name
                FROM chats
                LEFT JOIN projects ON projects.id = chats.project_id
                WHERE chats.user_id = ? AND chats.scope = 'private'
                ORDER BY chats.updated_at DESC, chats.id DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def chat_messages(self, user_id: int, chat_id: int, limit: int = 100) -> list[dict[str, str]]:
        if not self._can_access_chat(user_id, chat_id):
            raise PermissionError("Conversa não encontrada.")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content, display_name FROM (
                    SELECT messages.id, messages.role, messages.content,
                           users.display_name
                    FROM messages
                    JOIN users ON users.id = messages.user_id
                    WHERE chat_id = ?
                    ORDER BY messages.id DESC
                    LIMIT ?
                ) ORDER BY id
                """,
                (chat_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_message(self, user_id: int, chat_id: int, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("Papel de mensagem inválido.")
        if not self._can_access_chat(user_id, chat_id):
            raise PermissionError("Conversa não encontrada.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (user_id, chat_id, role, content)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, chat_id, role, content),
            )
            connection.execute(
                "UPDATE chats SET updated_at = unixepoch() WHERE id = ?",
                (chat_id,),
            )

    def delete_chat(self, user_id: int, chat_id: int) -> bool:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM messages
                WHERE chat_id = ?
                  AND EXISTS (
                      SELECT 1 FROM chats
                      WHERE id = ? AND user_id = ? AND scope = 'private'
                  )
                """,
                (chat_id, chat_id, user_id),
            )
            cursor = connection.execute(
                "DELETE FROM chats WHERE id = ? AND user_id = ? AND scope = 'private'",
                (chat_id, user_id),
            )
        return cursor.rowcount > 0

    def clone_chat(self, user_id: int, chat_id: int) -> dict:
        with self._connect() as connection:
            source = connection.execute(
                """
                SELECT id, title, project_id FROM chats
                WHERE id = ? AND user_id = ? AND scope = 'private'
                """,
                (chat_id, user_id),
            ).fetchone()
            if source is None:
                raise PermissionError("Conversa não encontrada.")
            title = self._chat_title(f"Ramificação · {source['title']}")
            cursor = connection.execute(
                """
                INSERT INTO chats (user_id, title, project_id, parent_chat_id)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, title, source["project_id"], chat_id),
            )
            new_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO messages (user_id, chat_id, role, content, created_at)
                SELECT ?, ?, role, content, created_at
                FROM messages WHERE chat_id = ? ORDER BY id
                """,
                (user_id, new_id, chat_id),
            )
        return {
            "id": new_id,
            "title": title,
            "project_id": source["project_id"],
            "parent_chat_id": chat_id,
        }

    def referenced_chat(self, user_id: int, chat_id: int, limit: int = 20) -> dict:
        with self._connect() as connection:
            chat = connection.execute(
                """
                SELECT id, title FROM chats
                WHERE id = ? AND (user_id = ? OR scope = 'shared')
                """,
                (chat_id, user_id),
            ).fetchone()
        if chat is None:
            raise PermissionError("Conversa referenciada não encontrada.")
        return {
            "chat": dict(chat),
            "messages": self.chat_messages(user_id, chat_id, limit=limit),
        }

    def selected_model(self, user_id: int, default: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT selected_model FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return row["selected_model"] if row and row["selected_model"] else default

    def set_selected_model(self, user_id: int, model: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_preferences (user_id, selected_model) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET selected_model = excluded.selected_model
                """,
                (user_id, model),
            )

    def reasoning_effort(self, user_id: int) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT reasoning_effort FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        effort = row["reasoning_effort"] if row else "medium"
        return effort if effort in {"low", "medium", "high"} else "medium"

    def set_model_preference(self, user_id: int, model: str, effort: str) -> None:
        if effort not in {"low", "medium", "high"}:
            raise ValueError("Nível de raciocínio inválido.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_preferences (user_id, selected_model, reasoning_effort)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    selected_model = excluded.selected_model,
                    reasoning_effort = excluded.reasoning_effort
                """,
                (user_id, model, effort),
            )

    def record_usage(self, user_id: int, model: str, success: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO usage_events (user_id, model, success) VALUES (?, ?, ?)",
                (user_id, model, int(success)),
            )

    def health_summary(self) -> dict:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()
            usage = connection.execute(
                """
                SELECT COUNT(*) AS requests,
                       SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS errors
                FROM usage_events WHERE created_at >= unixepoch('now', '-1 day')
                """
            ).fetchone()
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM chats) AS chats, "
                "(SELECT COUNT(*) FROM messages) AS messages, "
                "(SELECT COUNT(*) FROM memories) AS memories"
            ).fetchone()
        return {
            **dict(counts),
            "requests_24h": usage["requests"],
            "errors_24h": usage["errors"] or 0,
        }

    def search(self, user_id: int, query: str, limit: int = 40) -> list[dict]:
        clean = " ".join(query.split())
        if len(clean) < 2:
            raise ValueError("Digite ao menos 2 caracteres para pesquisar.")
        pattern = f"%{clean}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT 'message' AS kind, messages.chat_id, chats.title,
                       messages.content, messages.created_at AS result_created_at,
                       users.display_name, chats.scope
                FROM messages
                JOIN chats ON chats.id = messages.chat_id
                JOIN users ON users.id = messages.user_id
                WHERE messages.content LIKE ? COLLATE NOCASE
                  AND (chats.user_id = ? OR chats.scope = 'shared')
                UNION ALL
                SELECT 'memory', NULL, 'Memória pessoal', memories.content,
                       memories.updated_at AS result_created_at, '', 'private'
                FROM memories
                WHERE memories.user_id = ? AND memories.content LIKE ? COLLATE NOCASE
                ORDER BY result_created_at DESC
                LIMIT ?
                """,
                (pattern, user_id, user_id, pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def memory_timeline(self, user_id: int, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, memory_id, action, category, memory_key, content, created_at
                FROM memory_events WHERE user_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _clean_name(value: str, label: str) -> str:
        clean = " ".join(value.split())
        if not clean or len(clean) > 80:
            raise ValueError(f"{label} deve ter entre 1 e 80 caracteres.")
        return clean

    def create_project(self, user_id: int, name: str, instructions: str = "") -> dict:
        clean_name = self._clean_name(name, "O nome do projeto")
        clean_instructions = instructions.strip()[:6000]
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO projects (user_id, name, instructions)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, clean_name, clean_instructions),
                )
            return self.project(user_id, int(cursor.lastrowid))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Já existe um projeto com esse nome.") from exc

    def project(self, user_id: int, project_id: int) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, instructions, created_at, updated_at
                FROM projects WHERE id = ? AND user_id = ?
                """,
                (project_id, user_id),
            ).fetchone()
            if row is None:
                raise PermissionError("Projeto não encontrado.")
            folders = connection.execute(
                "SELECT id, path FROM project_folders WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
        result = dict(row)
        result["folders"] = [dict(folder) for folder in folders]
        return result

    def list_projects(self, user_id: int) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT projects.id, projects.name, projects.instructions,
                       projects.created_at, projects.updated_at,
                       COUNT(DISTINCT project_folders.id) AS folder_count,
                       COUNT(DISTINCT chats.id) AS chat_count
                FROM projects
                LEFT JOIN project_folders ON project_folders.project_id = projects.id
                LEFT JOIN chats ON chats.project_id = projects.id
                WHERE projects.user_id = ?
                GROUP BY projects.id ORDER BY projects.updated_at DESC, projects.id DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_project(self, user_id: int, project_id: int, name: str, instructions: str) -> dict:
        clean_name = self._clean_name(name, "O nome do projeto")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects SET name = ?, instructions = ?, updated_at = unixepoch()
                WHERE id = ? AND user_id = ?
                """,
                (clean_name, instructions.strip()[:6000], project_id, user_id),
            )
            if not cursor.rowcount:
                raise PermissionError("Projeto não encontrado.")
        return self.project(user_id, project_id)

    def add_project_folder(self, user_id: int, project_id: int, path: str) -> dict:
        self.project(user_id, project_id)
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO project_folders (project_id, path) VALUES (?, ?)",
                    (project_id, path),
                )
            return {"id": int(cursor.lastrowid), "path": path}
        except sqlite3.IntegrityError as exc:
            raise ValueError("Essa pasta já está autorizada no projeto.") from exc

    def remove_project_folder(self, user_id: int, folder_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM project_folders WHERE id = ? AND project_id IN (
                    SELECT id FROM projects WHERE user_id = ?
                )
                """,
                (folder_id, user_id),
            )
        return cursor.rowcount > 0

    def delete_project(self, user_id: int, project_id: int) -> bool:
        with self._connect() as connection:
            connection.execute(
                "UPDATE chats SET project_id = NULL WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            cursor = connection.execute(
                "DELETE FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            )
        return cursor.rowcount > 0

    def create_approval(self, user_id: int, kind: str, payload: dict) -> dict:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO approvals (user_id, kind, payload) VALUES (?, ?, ?)",
                (user_id, kind, json.dumps(payload, ensure_ascii=False)),
            )
        return self.approval(user_id, int(cursor.lastrowid))

    def approval(self, user_id: int, approval_id: int) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE id = ? AND user_id = ?",
                (approval_id, user_id),
            ).fetchone()
        if row is None:
            raise PermissionError("Aprovação não encontrada.")
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
        return result

    def list_approvals(self, user_id: int, limit: int = 50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM approvals WHERE user_id = ?
                ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            item["result"] = json.loads(item["result"]) if item["result"] else None
            results.append(item)
        return results

    def resolve_approval(
        self, user_id: int, approval_id: int, status: str, result: dict | None = None
    ) -> dict:
        if status not in {"approved", "denied", "failed"}:
            raise ValueError("Estado de aprovação inválido.")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE approvals SET status = ?, result = ?, resolved_at = unixepoch()
                WHERE id = ? AND user_id = ? AND status = 'pending'
                """,
                (
                    status,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    approval_id,
                    user_id,
                ),
            )
            if not cursor.rowcount:
                raise ValueError("Essa aprovação não está mais pendente.")
        return self.approval(user_id, approval_id)

    def create_workflow(self, user_id: int, name: str, steps: list[str]) -> dict:
        clean_name = self._clean_name(name, "O nome do fluxo")
        clean_steps = [" ".join(step.split())[:1000] for step in steps if step.strip()][:12]
        if not clean_steps:
            raise ValueError("Adicione pelo menos uma etapa ao fluxo.")
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO workflows (user_id, name, steps) VALUES (?, ?, ?)",
                    (user_id, clean_name, json.dumps(clean_steps, ensure_ascii=False)),
                )
            return self.workflow(user_id, int(cursor.lastrowid))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Já existe um fluxo com esse nome.") from exc

    def workflow(self, user_id: int, workflow_id: int) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflows WHERE id = ? AND user_id = ?",
                (workflow_id, user_id),
            ).fetchone()
        if row is None:
            raise PermissionError("Fluxo não encontrado.")
        result = dict(row)
        result["steps"] = json.loads(result["steps"])
        return result

    def list_workflows(self, user_id: int) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workflows WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
        return [{**dict(row), "steps": json.loads(row["steps"])} for row in rows]

    def delete_workflow(self, user_id: int, workflow_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM workflows WHERE id = ? AND user_id = ?",
                (workflow_id, user_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _clean_memory_content(content: str) -> str:
        clean = " ".join(content.split())
        if not clean:
            raise ValueError("A memória não pode ficar vazia.")
        if len(clean) > 1000:
            raise ValueError("A memória deve ter no máximo 1000 caracteres.")
        return clean

    @staticmethod
    def _canonical_memory_key(category: str, key: str) -> tuple[str, str]:
        normalized_category = category.strip().lower()
        if normalized_category not in MEMORY_CATEGORIES:
            raise ValueError("Categoria de memória inválida.")
        normalized_key = unicodedata.normalize("NFKD", key.strip().lower())
        normalized_key = "".join(char for char in normalized_key if not unicodedata.combining(char))
        if normalized_key.startswith(normalized_category + "."):
            normalized_key = normalized_key.split(".", 1)[1]
        normalized_key = re.sub(r"[^a-z0-9]+", "_", normalized_key).strip("_")[:64]
        if not normalized_key:
            raise ValueError("Chave de memória inválida.")
        return normalized_category, f"{normalized_category}.{normalized_key}"

    def upsert_memory(self, user_id: int, category: str, key: str, content: str) -> str:
        clean = self._clean_memory_content(content)
        category, memory_key = self._canonical_memory_key(category, key)
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT id, category, content
                FROM memories
                WHERE user_id = ? AND memory_key = ?
                """,
                (user_id, memory_key),
            ).fetchone()
            if current:
                if current["category"] == category and current["content"] == clean:
                    return "unchanged"
                duplicate = connection.execute(
                    """
                    SELECT id FROM memories
                    WHERE user_id = ? AND lower(content) = lower(?) AND id != ?
                    """,
                    (user_id, clean, current["id"]),
                ).fetchone()
                if duplicate:
                    connection.execute("DELETE FROM memories WHERE id = ?", (duplicate["id"],))
                connection.execute(
                    """
                    UPDATE memories
                    SET category = ?, content = ?, updated_at = unixepoch()
                    WHERE id = ?
                    """,
                    (category, clean, current["id"]),
                )
                return "updated"
            duplicate = connection.execute(
                """
                SELECT id FROM memories
                WHERE user_id = ? AND lower(content) = lower(?)
                """,
                (user_id, clean),
            ).fetchone()
            if duplicate:
                connection.execute(
                    """
                    UPDATE memories
                    SET category = ?, memory_key = ?, updated_at = unixepoch()
                    WHERE id = ?
                    """,
                    (category, memory_key, duplicate["id"]),
                )
                return "updated"
            connection.execute(
                """
                INSERT INTO memories (user_id, category, memory_key, content)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, category, memory_key, clean),
            )
        return "created"

    def add_memory(self, user_id: int, content: str) -> bool:
        clean = self._clean_memory_content(content)
        digest = hashlib.sha256(clean.casefold().encode("utf-8")).hexdigest()[:16]
        return self.upsert_memory(user_id, "personal", f"explicit_{digest}", clean) != "unchanged"

    def list_memories(self, user_id: int, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, category, memory_key, content, created_at, updated_at
                FROM memories
                WHERE user_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_memory(self, user_id: int, memory_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            )
        return cursor.rowcount > 0

    def delete_memory_by_key(self, user_id: int, memory_key: str) -> bool:
        category, separator, key = memory_key.partition(".")
        if not separator:
            return False
        _, canonical_key = self._canonical_memory_key(category, key)
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memories WHERE user_id = ? AND memory_key = ?",
                (user_id, canonical_key),
            )
        return cursor.rowcount > 0

    def permissions_for_user(self, user_id: int) -> dict[str, bool]:
        with self._connect() as connection:
            user = connection.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
            if user is None:
                raise PermissionError("Conta não encontrada.")
            if user["role"] == "owner":
                return {key: True for key in PERMISSION_LABELS}
            rows = connection.execute(
                "SELECT permission, enabled FROM user_permissions WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        permissions = dict(DEFAULT_ADMIN_PERMISSIONS)
        for row in rows:
            if row["permission"] in permissions:
                permissions[row["permission"]] = bool(row["enabled"])
        return permissions

    def has_permission(self, user_id: int, permission: str) -> bool:
        if permission not in PERMISSION_LABELS:
            return False
        return self.permissions_for_user(user_id)[permission]

    def permission_users(self, owner_id: int) -> list[dict]:
        self._require_owner(owner_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, username, display_name, role
                FROM users
                WHERE role != 'owner'
                ORDER BY display_name
                """
            ).fetchall()
        return [{**dict(row), "permissions": self.permissions_for_user(row["id"])} for row in rows]

    def update_user_permissions(
        self, owner_id: int, target_user_id: int, permissions: dict[str, bool]
    ) -> dict[str, bool]:
        self._require_owner(owner_id)
        unknown = set(permissions) - set(PERMISSION_LABELS)
        if unknown:
            raise ValueError("Permissão desconhecida.")
        if set(permissions) != set(PERMISSION_LABELS):
            raise ValueError("Envie todas as permissões disponíveis.")
        if not all(isinstance(value, bool) for value in permissions.values()):
            raise TypeError("Cada permissão deve ser verdadeira ou falsa.")
        with self._connect() as connection:
            target = connection.execute(
                "SELECT role FROM users WHERE id = ?", (target_user_id,)
            ).fetchone()
            if target is None:
                raise ValueError("Usuário não encontrado.")
            if target["role"] == "owner":
                raise PermissionError("As permissões do dev-chefe não podem ser reduzidas.")
            connection.executemany(
                """
                INSERT INTO user_permissions (user_id, permission, enabled)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, permission)
                DO UPDATE SET enabled = excluded.enabled
                """,
                [(target_user_id, key, int(enabled)) for key, enabled in permissions.items()],
            )
        return self.permissions_for_user(target_user_id)

    def _require_owner(self, user_id: int) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or row["role"] != "owner":
            raise PermissionError("Acesso exclusivo do administrador-chefe.")

    def audit_chats(self, owner_id: int) -> list[dict]:
        self._require_owner(owner_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chats.id, chats.title, chats.updated_at,
                       users.username, users.display_name
                FROM chats
                JOIN users ON users.id = chats.user_id
                WHERE users.id != ? AND chats.scope = 'private'
                ORDER BY chats.updated_at DESC, chats.id DESC
                """,
                (owner_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def audit_messages(self, owner_id: int, chat_id: int) -> dict:
        self._require_owner(owner_id)
        with self._connect() as connection:
            chat = connection.execute(
                """
                SELECT chats.id, chats.title, users.username, users.display_name
                FROM chats
                JOIN users ON users.id = chats.user_id
                WHERE chats.id = ? AND users.id != ?
                """,
                (chat_id, owner_id),
            ).fetchone()
            if chat is None:
                raise PermissionError("Conversa de auditoria não encontrada.")
            messages = connection.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY id
                """,
                (chat_id,),
            ).fetchall()
        return {"chat": dict(chat), "messages": [dict(row) for row in messages]}
