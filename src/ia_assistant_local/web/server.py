from __future__ import annotations

import inspect
import json
import re
import threading
import time
import unicodedata
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from ..ai.agent import LocalAgent
from ..core.config import Settings
from ..core.memory import PERMISSION_LABELS, MemoryStore
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
INTERNAL_DETAIL_TERMS = (
    "api",
    "arquitetura",
    "arquivo",
    "backend",
    "banco de dados",
    "codigo",
    "configuracao",
    "css",
    "endpoint",
    "env",
    "frontend",
    "html",
    "implementacao",
    "instrucao interna",
    "javascript",
    "memoria interna",
    "modelo",
    "pasta",
    "prompt",
    "python",
    "rota",
    "servidor",
    "sistema interno",
)
INTERNAL_SUBJECT_RE = re.compile(
    r"\b(?:seu|sua|seus|suas|voce|oraculo|assistente|interface|dele|dela)\b"
)
CONFIDENTIALITY_REPLY = (
    "Não posso fornecer detalhes internos sobre como o Oráculo foi construído. "
    "A implementação do projeto é confidencial. Posso ajudar você a usar as "
    "funções disponíveis."
)
TOOL_PERMISSIONS = {
    "system_info": "system_info",
    "open_application": "open_application",
    "get_home_state": "home_read",
    "turn_on_home_entity": "home_control",
    "turn_off_home_entity": "home_control",
}


def is_internal_details_request(message: str) -> bool:
    normalized = unicodedata.normalize("NFKD", message.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    has_internal_term = any(term in normalized for term in INTERNAL_DETAIL_TERMS)
    return has_internal_term and bool(INTERNAL_SUBJECT_RE.search(normalized))


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
        self.started_at = time.time()


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
                f"{COOKIE_NAME}={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000",
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

    def _require_permission(self, user: dict, permission: str) -> None:
        if not self.server.memory.has_permission(user["id"], permission):
            label = PERMISSION_LABELS[permission]
            raise PermissionError(f"Seu usuário não possui permissão para: {label}.")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            body = Path(__file__).with_name("interface.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/status":
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
        if path == "/api/me":
            try:
                self._send_json(200, {"user": self._require_user()})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/models":
            try:
                user = self._require_user()
                models = self._available_models()
                selected = self.server.memory.selected_model(
                    user["id"], self.server.settings.groq_model
                )
                if selected not in models:
                    selected = self.server.settings.groq_model
                self._send_json(
                    200,
                    {
                        "models": [
                            {
                                "id": model,
                                "label": self._model_label(model, index),
                                "reasoning": model.startswith("openai/gpt-oss-"),
                            }
                            for index, model in enumerate(models)
                        ],
                        "selected": selected,
                        "effort": self.server.memory.reasoning_effort(user["id"]),
                    },
                )
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/permissions":
            try:
                user = self._require_user()
                permissions = self.server.memory.permissions_for_user(user["id"])
                self._send_json(200, {"permissions": permissions})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/chats":
            try:
                user = self._require_user()
                self._send_json(200, {"chats": self.server.memory.list_chats(user["id"])})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/shared":
            try:
                user = self._require_user()
                chat = self.server.memory.shared_chat(user["id"])
                messages = self.server.memory.chat_messages(user["id"], chat["id"])
                self._send_json(200, {"chat": chat, "messages": messages})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/search":
            try:
                user = self._require_user()
                query = parse_qs(parsed.query).get("q", [""])[0]
                self._send_json(200, {"results": self.server.memory.search(user["id"], query)})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            return
        if path == "/api/health":
            try:
                self._require_user()
                summary = self.server.memory.health_summary()
                self._send_json(
                    200,
                    {
                        "groq": bool(self.server.settings.groq_api_key),
                        "database": True,
                        "home_assistant": bool(
                            self.server.settings.home_assistant_url
                            and self.server.settings.home_assistant_token
                        ),
                        "uptime_seconds": int(time.time() - self.server.started_at),
                        **summary,
                    },
                )
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            except OSError as exc:
                self._send_json(503, {"error": f"Banco indisponível: {exc}"})
            return
        if path.startswith("/api/chats/"):
            try:
                user = self._require_user()
                chat_id = int(path.removeprefix("/api/chats/"))
                messages = self.server.memory.chat_messages(user["id"], chat_id)
                self._send_json(200, {"chat_id": chat_id, "messages": messages})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            except ValueError:
                self._send_json(400, {"error": "Conversa inválida."})
            return
        if path == "/api/admin/chats":
            try:
                user = self._require_user()
                self._send_json(200, {"chats": self.server.memory.audit_chats(user["id"])})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        if path == "/api/admin/permissions":
            try:
                user = self._require_user()
                users = self.server.memory.permission_users(user["id"])
                self._send_json(
                    200,
                    {"labels": PERMISSION_LABELS, "users": users},
                )
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        if path.startswith("/api/admin/chats/"):
            try:
                user = self._require_user()
                chat_id = int(path.removeprefix("/api/admin/chats/"))
                result = self.server.memory.audit_messages(user["id"], chat_id)
                self._send_json(200, result)
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            except ValueError:
                self._send_json(400, {"error": "Conversa inválida."})
            return
        if path == "/api/memories":
            try:
                user = self._require_user()
                self._require_permission(user, "memory_access")
                memories = self.server.memory.list_memories(user["id"])
                self._send_json(200, {"memories": memories})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        if path == "/favicon.ico":
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
                self._require_permission(user, "memory_access")
                payload = self._read_json()
                created = self.server.memory.add_memory(user["id"], str(payload.get("content", "")))
                self._send_json(201 if created else 200, {"created": created})
                return
            if self.path == "/api/chat":
                self._handle_chat()
                return
            self._send_json(404, {"error": "Rota não encontrada."})
        except PermissionError as exc:
            status = 401 if self.path == "/api/login" else 403
            self._send_json(status, {"error": str(exc)})
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})
        except httpx.HTTPError as exc:
            self._send_json(502, {"error": f"Erro no Groq: {exc}"})
        except RuntimeError as exc:
            self._send_json(502, {"error": str(exc)})

    def do_PUT(self) -> None:
        try:
            if self.path == "/api/model":
                user = self._require_user()
                payload = self._read_json()
                model = str(payload.get("model", ""))
                effort = str(payload.get("effort", "medium"))
                if model not in self._available_models():
                    raise ValueError("Modelo não permitido.")
                self.server.memory.set_model_preference(user["id"], model, effort)
                self._send_json(200, {"model": model, "effort": effort})
                return
            match = re.fullmatch(r"/api/admin/users/(\d+)/permissions", self.path)
            if match is None:
                self._send_json(404, {"error": "Rota não encontrada."})
                return
            user = self._require_user()
            payload = self._read_json()
            permissions = payload.get("permissions")
            if not isinstance(permissions, dict):
                raise TypeError("Permissões inválidas.")
            updated = self.server.memory.update_user_permissions(
                user["id"], int(match.group(1)), permissions
            )
            self._send_json(200, {"permissions": updated})
        except PermissionError as exc:
            self._send_json(403, {"error": str(exc)})
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})

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
        mode = str(payload.get("mode", "private"))
        if mode not in {"private", "temporary", "shared"}:
            raise ValueError("Modo de conversa inválido.")
        model = self.server.memory.selected_model(user["id"], self.server.settings.groq_model)
        if model not in self._available_models():
            model = self.server.settings.groq_model
        reasoning_effort = self.server.memory.reasoning_effort(user["id"])
        raw_chat_id = payload.get("chat_id")
        if mode == "temporary":
            chat_id = None
            raw_history = payload.get("history", [])
            if not isinstance(raw_history, list):
                raise TypeError("Histórico temporário inválido.")
            history = [
                {"role": item["role"], "content": str(item["content"])[:12000]}
                for item in raw_history[-40:]
                if isinstance(item, dict)
                and item.get("role") in {"user", "assistant"}
                and isinstance(item.get("content"), str)
            ]
        elif mode == "shared":
            shared = self.server.memory.shared_chat(user["id"])
            chat_id = shared["id"]
            rows = self.server.memory.chat_messages(user["id"], chat_id)
            history = [
                {
                    "role": item["role"],
                    "content": (
                        f"[{item['display_name']}]: {item['content']}"
                        if item["role"] == "user"
                        else item["content"]
                    ),
                }
                for item in rows
            ]
        elif raw_chat_id is None:
            chat_id = self.server.memory.create_chat(user["id"], message)
            history = []
        else:
            chat_id = int(raw_chat_id)
            history = [
                {"role": item["role"], "content": item["content"]}
                for item in self.server.memory.chat_messages(user["id"], chat_id)
            ]
        permissions = self.server.memory.permissions_for_user(user["id"])
        memory_enabled = permissions["memory_access"] and mode == "private"
        memory_rows = self.server.memory.list_memories(user["id"]) if memory_enabled else []
        explicit = EXPLICIT_MEMORY.match(message) if memory_enabled else None
        if explicit:
            self.server.memory.add_memory(user["id"], explicit.group(1))
            memory_rows = self.server.memory.list_memories(user["id"])
        blocked_internal_request = is_internal_details_request(message)
        if blocked_internal_request:
            reply = CONFIDENTIALITY_REPLY
        else:
            allowed_tools = frozenset(
                tool for tool, permission in TOOL_PERMISSIONS.items() if permissions[permission]
            )
            ask_kwargs = {
                "history": history,
                "memories": [f"[{item['category']}] {item['content']}" for item in memory_rows],
                "allowed_tools": allowed_tools,
            }
            if "model" in inspect.signature(self.server.agent.ask).parameters:
                ask_kwargs["model"] = model
            if "reasoning_effort" in inspect.signature(self.server.agent.ask).parameters:
                ask_kwargs["reasoning_effort"] = reasoning_effort
            try:
                reply = self.server.agent.ask(message, lambda _: False, **ask_kwargs)
                self.server.memory.record_usage(user["id"], model, True)
            except (httpx.HTTPError, RuntimeError, TypeError, ValueError):
                self.server.memory.record_usage(user["id"], model, False)
                raise
        if mode != "temporary":
            self.server.memory.add_message(user["id"], chat_id, "user", message)
            self.server.memory.add_message(user["id"], chat_id, "assistant", reply)
        existing = memory_rows
        if not blocked_internal_request and memory_enabled:
            threading.Thread(
                target=self._learn_from_message,
                args=(user["id"], message, existing),
                daemon=True,
            ).start()
        if mode == "temporary":
            title = "Chat temporário"
        elif mode == "shared":
            title = "Sala da equipe"
        else:
            chats = self.server.memory.list_chats(user["id"])
            title = next(item["title"] for item in chats if item["id"] == chat_id)
        self._send_json(
            200,
            {
                "reply": reply,
                "chat_id": chat_id,
                "chat_title": title,
                "memory_saved": bool(explicit),
                "mode": mode,
                "model": model,
            },
        )

    def _available_models(self) -> tuple[str, ...]:
        configured = getattr(self.server.settings, "groq_models", ())
        models = tuple(dict.fromkeys((self.server.settings.groq_model, *configured)))
        return models

    @staticmethod
    def _model_label(model: str, index: int) -> str:
        lowered = model.lower()
        if "20b" in lowered or "8b" in lowered:
            suffix = "Rápido"
        elif "120b" in lowered:
            suffix = "Potente"
        else:
            suffix = "Equilibrado"
        return f"Oráculo 1.{index} · {suffix}"

    def _learn_from_message(self, user_id: int, message: str, existing: list[dict]) -> None:
        try:
            changes = self.server.agent.extract_memories(message, existing)
            for memory_key in changes["forget_keys"]:
                self.server.memory.delete_memory_by_key(user_id, memory_key)
            for memory in changes["upserts"]:
                self.server.memory.upsert_memory(
                    user_id,
                    memory["category"],
                    memory["key"],
                    memory["content"],
                )
        except (httpx.HTTPError, RuntimeError, TypeError, ValueError):
            return

    def do_DELETE(self) -> None:
        try:
            user = self._require_user()
            if self.path.startswith("/api/memories/"):
                self._require_permission(user, "memory_access")
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
            self._send_json(403, {"error": str(exc)})
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
