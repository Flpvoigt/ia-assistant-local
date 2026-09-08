from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
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
}
DEFAULT_ADMIN_PERMISSIONS = {
    "memory_access": True,
    "context_panel": True,
    "system_info": True,
    "open_application": False,
    "home_read": False,
    "home_control": False,
}


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
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    UNIQUE(user_id, content)
                );
                CREATE TABLE IF NOT EXISTS user_permissions (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    permission TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    PRIMARY KEY (user_id, permission)
                );
                CREATE INDEX IF NOT EXISTS chats_user_id ON chats(user_id, updated_at);
                CREATE INDEX IF NOT EXISTS messages_user_id ON messages(user_id, id);
                CREATE INDEX IF NOT EXISTS memories_user_id ON memories(user_id, id);
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(messages)")
            }
            if "chat_id" not in columns:
                connection.execute(
                    "ALTER TABLE messages ADD COLUMN chat_id INTEGER REFERENCES chats(id)"
                )
            connection.execute(
                "UPDATE users SET role = 'owner' WHERE username = 'felipe'"
            )
            connection.execute(
                "UPDATE users SET role = 'admin' WHERE username IN ('will', 'gustavo')"
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
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),)
            )
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

    def create_chat(self, user_id: int, first_message: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO chats (user_id, title) VALUES (?, ?)",
                (user_id, self._chat_title(first_message)),
            )
        return int(cursor.lastrowid)

    def _owns_chat(self, user_id: int, chat_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM chats WHERE id = ? AND user_id = ?",
                (chat_id, user_id),
            ).fetchone()
        return row is not None

    def list_chats(self, user_id: int) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM chats
                WHERE user_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def chat_messages(
        self, user_id: int, chat_id: int, limit: int = 100
    ) -> list[dict[str, str]]:
        if not self._owns_chat(user_id, chat_id):
            raise PermissionError("Conversa não encontrada.")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content
                    FROM messages
                    WHERE user_id = ? AND chat_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id
                """,
                (user_id, chat_id, limit),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def add_message(self, user_id: int, chat_id: int, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("Papel de mensagem inválido.")
        if not self._owns_chat(user_id, chat_id):
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
                      SELECT 1 FROM chats WHERE id = ? AND user_id = ?
                  )
                """,
                (chat_id, chat_id, user_id),
            )
            cursor = connection.execute(
                "DELETE FROM chats WHERE id = ? AND user_id = ?",
                (chat_id, user_id),
            )
        return cursor.rowcount > 0

    def add_memory(self, user_id: int, content: str) -> bool:
        clean = " ".join(content.split())
        if not clean:
            raise ValueError("A memória não pode ficar vazia.")
        if len(clean) > 1000:
            raise ValueError("A memória deve ter no máximo 1000 caracteres.")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO memories (user_id, content) VALUES (?, ?)",
                (user_id, clean),
            )
        return cursor.rowcount > 0

    def list_memories(self, user_id: int, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content, created_at
                FROM memories
                WHERE user_id = ?
                ORDER BY id DESC
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

    def permissions_for_user(self, user_id: int) -> dict[str, bool]:
        with self._connect() as connection:
            user = connection.execute(
                "SELECT role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
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
        return [
            {**dict(row), "permissions": self.permissions_for_user(row["id"])}
            for row in rows
        ]

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
                [
                    (target_user_id, key, int(enabled))
                    for key, enabled in permissions.items()
                ],
            )
        return self.permissions_for_user(target_user_id)

    def _require_owner(self, user_id: int) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
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
                WHERE users.id != ?
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
