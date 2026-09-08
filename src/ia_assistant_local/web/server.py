from __future__ import annotations

import json
import re
import threading
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

from ..ai.agent import LocalAgent
from ..core.config import Settings
from ..core.memory import MemoryStore
from ..integrations.home_assistant import HomeAssistantClient
from ..integrations.tools import ToolRegistry

HOST = "127.0.0.1"
PORT = 8765
MAX_REQUEST_SIZE = 1_000_000
COOKIE_NAME = "oraculo_session"
EXPLICIT_MEMORY = re.compile(
    r"^\s*(?:lembre(?:-se)?(?: de)? que|memorize que|guarde que)\s+(.+?)\s*$",
    re.IGNORECASE | re.DOTALL,
)


class AssistantServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        agent: LocalAgent,
        settings: Settings,
        memory: MemoryStore,
    ):
        super().__init__(address, AssistantHandler)
        self.agent = agent
        self.settings = settings
        self.memory = memory


class AssistantHandler(BaseHTTPRequestHandler):
    server: AssistantServer

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        cookie: str | None = None,
        clear_cookie: bool = False,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        if cookie:
            self.send_header(
                "Set-Cookie",
                f"{COOKIE_NAME}={cookie}; HttpOnly; SameSite=Strict; Path=/; "
                "Max-Age=2592000",
            )
        if clear_cookie:
            self.send_header(
                "Set-Cookie",
                f"{COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
            )
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise ValueError("O conteúdo deve ser JSON.")
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_REQUEST_SIZE:
            raise ValueError("Tamanho de requisição inválido.")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise TypeError("O corpo da requisição deve ser um objeto.")
        return payload

    def _session_token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(COOKIE_NAME)
        return morsel.value if morsel else None

    def _require_user(self) -> dict:
        user = self.server.memory.current_user(self._session_token())
        if user is None:
            raise PermissionError("Faça login para continuar.")
        return user

    def do_GET(self) -> None:
        if self.path == "/":
            body = Path(__file__).with_name("interface.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/status":
            user = self.server.memory.current_user(self._session_token())
            self._send_json(
                200,
                {
                    "online": bool(self.server.settings.groq_api_key),
                    "provider": "Groq",
                    "model": self.server.settings.groq_model,
                    "user": user,
                },
            )
            return
        if self.path == "/api/me":
            try:
                self._send_json(200, {"user": self._require_user()})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if self.path == "/api/chats":
            try:
                user = self._require_user()
                self._send_json(200, {"chats": self.server.memory.list_chats(user["id"])})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if self.path.startswith("/api/chats/"):
            try:
                user = self._require_user()
                chat_id = int(self.path.removeprefix("/api/chats/"))
                messages = self.server.memory.chat_messages(user["id"], chat_id)
                self._send_json(200, {"chat_id": chat_id, "messages": messages})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            except ValueError:
                self._send_json(400, {"error": "Conversa inválida."})
            return
        if self.path == "/api/admin/chats":
            try:
                user = self._require_user()
                self._send_json(
                    200, {"chats": self.server.memory.audit_chats(user["id"])}
                )
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        if self.path.startswith("/api/admin/chats/"):
            try:
                user = self._require_user()
                chat_id = int(self.path.removeprefix("/api/admin/chats/"))
                result = self.server.memory.audit_messages(user["id"], chat_id)
                self._send_json(200, result)
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            except ValueError:
                self._send_json(400, {"error": "Conversa inválida."})
            return
        if self.path == "/api/memories":
            try:
                user = self._require_user()
                memories = self.server.memory.list_memories(user["id"])
                self._send_json(200, {"memories": memories})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        self._send_json(404, {"error": "Rota não encontrada."})

    def do_POST(self) -> None:
        try:
            if self.path == "/api/login":
                payload = self._read_json()
                token, user = self.server.memory.login(
                    str(payload.get("username", "")),
                    str(payload.get("password", "")),
                )
                self._send_json(200, {"user": user}, cookie=token)
                return
            if self.path == "/api/logout":
                self.server.memory.logout(self._session_token())
                self._send_json(200, {"ok": True}, clear_cookie=True)
                return
            if self.path == "/api/change-password":
                user = self._require_user()
                payload = self._read_json()
                self.server.memory.change_password(
                    user["id"],
                    str(payload.get("current_password", "")),
                    str(payload.get("new_password", "")),
                )
                user = self.server.memory.current_user(self._session_token())
                self._send_json(200, {"user": user})
                return
            if self.path == "/api/memories":
                user = self._require_user()
                payload = self._read_json()
                created = self.server.memory.add_memory(
                    user["id"], str(payload.get("content", ""))
                )
                self._send_json(201 if created else 200, {"created": created})
                return
            if self.path == "/api/chat":
                self._handle_chat()
                return
            self._send_json(404, {"error": "Rota não encontrada."})
        except PermissionError as exc:
            self._send_json(401, {"error": str(exc)})
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})
        except httpx.HTTPError as exc:
            self._send_json(502, {"error": f"Erro no Groq: {exc}"})
        except RuntimeError as exc:
            self._send_json(502, {"error": str(exc)})

    def _handle_chat(self) -> None:
        user = self._require_user()
        if user["must_change_password"]:
            self._send_json(403, {"error": "Troque a senha temporária antes de conversar."})
            return
        payload = self._read_json()
        message = payload.get("message", "")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Mensagem vazia.")
        message = message.strip()
        raw_chat_id = payload.get("chat_id")
        if raw_chat_id is None:
            chat_id = self.server.memory.create_chat(user["id"], message)
            history = []
        else:
            chat_id = int(raw_chat_id)
            history = self.server.memory.chat_messages(user["id"], chat_id)
        memory_rows = self.server.memory.list_memories(user["id"])
        explicit = EXPLICIT_MEMORY.match(message)
        if explicit:
            self.server.memory.add_memory(user["id"], explicit.group(1))
            memory_rows = self.server.memory.list_memories(user["id"])
        reply = self.server.agent.ask(
            message,
            lambda _: False,
            history=history,
            memories=[item["content"] for item in memory_rows],
        )
        self.server.memory.add_message(user["id"], chat_id, "user", message)
        self.server.memory.add_message(user["id"], chat_id, "assistant", reply)
        existing = [item["content"] for item in memory_rows]
        threading.Thread(
            target=self._learn_from_message,
            args=(user["id"], message, existing),
            daemon=True,
        ).start()
        chats = self.server.memory.list_chats(user["id"])
        title = next(item["title"] for item in chats if item["id"] == chat_id)
        self._send_json(
            200,
            {
                "reply": reply,
                "chat_id": chat_id,
                "chat_title": title,
                "memory_saved": bool(explicit),
            },
        )

    def _learn_from_message(
        self, user_id: int, message: str, existing: list[str]
    ) -> None:
        try:
            for memory in self.server.agent.extract_memories(message, existing):
                self.server.memory.add_memory(user_id, memory)
        except (httpx.HTTPError, RuntimeError, TypeError, ValueError):
            return

    def do_DELETE(self) -> None:
        try:
            user = self._require_user()
            if self.path.startswith("/api/memories/"):
                memory_id = int(self.path.removeprefix("/api/memories/"))
                deleted = self.server.memory.delete_memory(user["id"], memory_id)
            elif self.path.startswith("/api/chats/"):
                chat_id = int(self.path.removeprefix("/api/chats/"))
                deleted = self.server.memory.delete_chat(user["id"], chat_id)
            else:
                self._send_json(404, {"error": "Rota não encontrada."})
                return
            self._send_json(200, {"deleted": deleted})
        except PermissionError as exc:
            self._send_json(401, {"error": str(exc)})
        except ValueError:
            self._send_json(400, {"error": "Identificador inválido."})

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def run_server() -> None:
    settings = Settings.from_env()
    memory = MemoryStore(settings.database_path)
    created_admins = memory.bootstrap_admins()
    home = HomeAssistantClient(
        settings.home_assistant_url,
        settings.home_assistant_token,
        settings.allowed_entities,
    )
    agent = LocalAgent(
        settings.groq_url,
        settings.groq_model,
        ToolRegistry(home),
        api_key=settings.groq_api_key,
    )
    server = AssistantServer((HOST, PORT), agent, settings, memory)
    url = f"http://{HOST}:{PORT}"
    print(f"IA Assistant | Groq: {settings.groq_model}")
    if created_admins:
        print("\nCONTAS ADMINISTRATIVAS CRIADAS")
        print("Anote as senhas temporárias; elas não serão exibidas novamente.")
        for username, password in created_admins:
            print(f"  {username}: {password}")
        print()
    print(f"Interface: {url}")
    print("Pressione Ctrl+C para encerrar.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        server.server_close()
