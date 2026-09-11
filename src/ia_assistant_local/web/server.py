from __future__ import annotations

import base64
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
from ..core.actions import command_preview, execute_command, search_folder_context, validate_folder
from ..core.attachments import extract_attachment, validate_image
from ..core.background_tasks import TaskManager
from ..core.config import PROJECT_ROOT, Settings
from ..core.memory import PERMISSION_LABELS, MemoryStore
from ..core.ocr import extract_image_text, ocr_available
from ..core.pdf_export import convert_to_pdf
from ..core.releases import prepare_release, publish_release, release_info
from ..core.updater import apply_update, update_status
from ..core.vault import decrypt_secret, encrypt_secret
from ..core.voice import synthesize_voice, synthesize_voice_chunks, voice_status, warm_voice
from ..integrations.extensions import extension_catalog
from ..integrations.home_assistant import HomeAssistantClient
from ..integrations.tools import ToolRegistry

HOST = "127.0.0.1"
PORT = 8765
MAX_REQUEST_SIZE = 12_000_000
VISION_MODEL = "qwen/qwen3.6-27b"
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
        self.tasks = TaskManager()
        self.started_at = time.time()

    def server_close(self) -> None:
        self.tasks.shutdown()
        super().server_close()


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
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # O navegador pode cancelar uma síntese de voz enquanto ela ainda
            # está sendo gerada. A resposta deixa de ser necessária nesse caso.
            return

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

    def _send_voice_stream(self, chunks) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self._security_headers()
        self.end_headers()
        model_variant = voice_status().get("model_variant", "local")
        try:
            for index, audio in enumerate(chunks):
                line = (
                    json.dumps(
                        {
                            "index": index,
                            "audio": base64.b64encode(audio).decode("ascii"),
                            "mime_type": "audio/wav",
                            "voice": "pm_alex",
                            "model": model_variant,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")
                    + b"\n"
                )
                self.wfile.write(line)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass
        finally:
            self.close_connection = True

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

    @staticmethod
    def _require_owner(user: dict) -> None:
        if user.get("role") != "owner":
            raise PermissionError("Acesso exclusivo do dev-chefe.")

    def _send_static(self, name: str, content_type: str) -> None:
        body = Path(__file__).with_name(name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        if name == "service-worker.js":
            self.send_header("Service-Worker-Allowed", "/")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

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
        static_files = {
            "/profile.js": ("profile.js", "application/javascript; charset=utf-8"),
            "/release-ui.js": ("release-ui.js", "application/javascript; charset=utf-8"),
            "/attachments-ui.js": ("attachments-ui.js", "application/javascript; charset=utf-8"),
            "/features-ui.js": ("features-ui.js", "application/javascript; charset=utf-8"),
            "/voice-ui.js": ("voice-ui.js", "application/javascript; charset=utf-8"),
            "/features-ui.css": ("features-ui.css", "text/css; charset=utf-8"),
            "/mascot.js": ("mascot.js", "application/javascript; charset=utf-8"),
            "/desktop-ui.css": ("desktop-ui.css", "text/css; charset=utf-8"),
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
            "/service-worker.js": ("service-worker.js", "application/javascript; charset=utf-8"),
            "/icon.svg": ("icon.svg", "image/svg+xml"),
        }
        if path in static_files:
            self._send_static(*static_files[path])
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
        if path == "/api/voice/status":
            try:
                self._require_user()
                self._send_json(200, voice_status())
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/release":
            try:
                self._require_user()
                self._send_json(200, release_info(PROJECT_ROOT))
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/usage":
            try:
                user = self._require_user()
                self._send_json(200, self.server.memory.user_usage(user["id"]))
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/models":
            try:
                user = self._require_user()
                models = self._available_models()
                current_version = str(release_info(PROJECT_ROOT).get("version", "1.0"))
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
                                "label": self._model_label(model, current_version),
                                "reasoning": model.startswith("openai/gpt-oss-"),
                            }
                            for index, model in enumerate(models)
                        ],
                        "version": current_version,
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
        if path == "/api/memory-timeline":
            try:
                user = self._require_user()
                self._require_permission(user, "memory_access")
                self._send_json(200, {"events": self.server.memory.memory_timeline(user["id"])})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        if path == "/api/projects":
            try:
                user = self._require_user()
                self._require_permission(user, "project_access")
                self._send_json(200, {"projects": self.server.memory.list_projects(user["id"])})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        project_match = re.fullmatch(r"/api/projects/(\d+)", path)
        if project_match:
            try:
                user = self._require_user()
                self._require_permission(user, "project_access")
                project = self.server.memory.project(user["id"], int(project_match.group(1)))
                self._send_json(200, {"project": project})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        if path == "/api/approvals":
            try:
                user = self._require_user()
                self._send_json(200, {"approvals": self.server.memory.list_approvals(user["id"])})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/workflows":
            try:
                user = self._require_user()
                self._send_json(200, {"workflows": self.server.memory.list_workflows(user["id"])})
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
        if path == "/api/extensions":
            try:
                self._require_user()
                configured = bool(
                    self.server.settings.home_assistant_url
                    and self.server.settings.home_assistant_token
                )
                self._send_json(200, {"extensions": extension_catalog(configured)})
            except PermissionError as exc:
                self._send_json(401, {"error": str(exc)})
            return
        if path == "/api/admin/update/status":
            try:
                user = self._require_user()
                self._require_owner(user)
                check_remote = parse_qs(parsed.query).get("remote", ["0"])[0] == "1"
                self._send_json(200, {"update": update_status(PROJECT_ROOT, check_remote)})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            except RuntimeError as exc:
                self._send_json(502, {"error": str(exc)})
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
        if path == "/api/memory-conflicts":
            try:
                user = self._require_user()
                self._require_permission(user, "memory_access")
                self._send_json(
                    200, {"conflicts": self.server.memory.list_memory_conflicts(user["id"])}
                )
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        if path == "/api/vault":
            try:
                user = self._require_user()
                self._send_json(200, {"items": self.server.memory.list_vault_items(user["id"])})
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        if path == "/api/tasks":
            try:
                user = self._require_user()
                self._send_json(
                    200,
                    {"tasks": self.server.tasks.list(user["id"]), "ocr_available": ocr_available()},
                )
            except PermissionError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        task_match = re.fullmatch(r"/api/tasks/([A-Za-z0-9_-]+)", path)
        if task_match:
            try:
                user = self._require_user()
                self._send_json(
                    200, {"task": self.server.tasks.get(user["id"], task_match.group(1))}
                )
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
            if self.path == "/api/voice/synthesize":
                self._require_user()
                payload = self._read_json()
                try:
                    audio = synthesize_voice(str(payload.get("text", "")))
                except RuntimeError as exc:
                    self._send_json(503, {"error": str(exc), "fallback": "browser"})
                    return
                self._send_json(
                    200,
                    {
                        "audio": base64.b64encode(audio).decode("ascii"),
                        "mime_type": "audio/wav",
                        "engine": "kokoro-onnx",
                        "voice": "pm_alex",
                    },
                )
                return
            if self.path == "/api/voice/stream":
                self._require_user()
                payload = self._read_json()
                try:
                    chunks = synthesize_voice_chunks(str(payload.get("text", "")))
                except RuntimeError as exc:
                    self._send_json(503, {"error": str(exc), "fallback": "browser"})
                    return
                self._send_voice_stream(chunks)
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
            if self.path == "/api/vault":
                user = self._require_user()
                payload = self._read_json()
                salt, nonce, ciphertext = encrypt_secret(
                    str(payload.get("passphrase", "")), str(payload.get("content", ""))
                )
                item_id = self.server.memory.create_vault_item(
                    user["id"], str(payload.get("label", "")), salt, nonce, ciphertext
                )
                self._send_json(201, {"id": item_id})
                return
            vault_unlock = re.fullmatch(r"/api/vault/(\d+)/unlock", self.path)
            if vault_unlock:
                user = self._require_user()
                payload = self._read_json()
                item = self.server.memory.vault_item(user["id"], int(vault_unlock.group(1)))
                content = decrypt_secret(
                    str(payload.get("passphrase", "")),
                    item["salt"],
                    item["nonce"],
                    item["ciphertext"],
                )
                self._send_json(200, {"content": content, "included_in_ai": False})
                return
            if self.path == "/api/tasks":
                user = self._require_user()
                payload = self._read_json()
                kind = str(payload.get("kind", ""))
                name = Path(str(payload.get("name", "anexo"))).name[:180]
                mime_type = str(payload.get("mime_type", ""))
                data = str(payload.get("data", ""))
                if kind == "extract":

                    def work(cancel, progress):
                        progress(30)
                        return extract_attachment(name, mime_type, data)
                elif kind == "ocr":
                    image_url = f"data:{mime_type};base64,{data}"
                    validate_image(image_url)

                    def work(cancel, progress):
                        progress(25)
                        return {
                            "name": name,
                            "kind": "text",
                            "content": extract_image_text(data),
                            "truncated": False,
                            "source": "ocr",
                        }
                else:
                    raise ValueError("Tipo de tarefa desconhecido.")
                task = self.server.tasks.create(user["id"], kind, name, work)
                self._send_json(202, {"task": task})
                return
            if self.path == "/api/attachments/pdf":
                self._require_user()
                payload = self._read_json()
                result = convert_to_pdf(
                    str(payload.get("name", "anexo")),
                    str(payload.get("mime_type", "")),
                    str(payload.get("data", "")),
                )
                self._send_json(
                    200, {"data": base64.b64encode(result).decode("ascii"), "sent_to_ai": False}
                )
                return
            if self.path == "/api/attachments/extract":
                self._require_user()
                payload = self._read_json()
                result = extract_attachment(
                    str(payload.get("name", "anexo")),
                    str(payload.get("mime_type", "")),
                    str(payload.get("data", "")),
                )
                self._send_json(200, {"attachment": result, "sent_to_ai": False})
                return
            if self.path in {"/api/admin/release/prepare", "/api/admin/release/publish"}:
                user = self._require_user()
                self._require_owner(user)
                if user.get("username") != "felipe" or user.get("must_change_password"):
                    raise PermissionError(
                        "Lançamento exclusivo da conta Felipe com senha definitiva."
                    )
                payload = self._read_json()
                if self.path.endswith("/prepare"):
                    result = prepare_release(PROJECT_ROOT, user["id"], payload.get("notes", []))
                else:
                    if payload.get("confirmed") is not True:
                        raise ValueError("Confirme a revisão antes de publicar.")
                    result = publish_release(
                        PROJECT_ROOT, user["id"], str(payload.get("token", ""))
                    )
                self._send_json(200, result)
                return
            if self.path == "/api/admin/update/prepare":
                user = self._require_user()
                self._require_owner(user)
                status = update_status(PROJECT_ROOT, True)
                if status["dirty"]:
                    raise ValueError("Há alterações locais. Faça commit antes de atualizar.")
                approval = self.server.memory.create_approval(
                    user["id"],
                    "project_update",
                    {
                        "label": "Atualizar o Oráculo pelo Git com avanço rápido",
                        "branch": status["branch"],
                        "current": status["current"],
                        "remote": status.get("remote"),
                        "backup_database": True,
                    },
                )
                self._send_json(201, {"approval": approval})
                return
            if self.path == "/api/projects":
                user = self._require_user()
                self._require_permission(user, "project_access")
                payload = self._read_json()
                project = self.server.memory.create_project(
                    user["id"],
                    str(payload.get("name", "")),
                    str(payload.get("instructions", "")),
                )
                self._send_json(201, {"project": project})
                return
            folder_match = re.fullmatch(r"/api/projects/(\d+)/folders", self.path)
            if folder_match:
                user = self._require_user()
                self._require_permission(user, "project_access")
                payload = self._read_json()
                folder = validate_folder(str(payload.get("path", "")))
                created = self.server.memory.add_project_folder(
                    user["id"], int(folder_match.group(1)), str(folder)
                )
                self._send_json(201, {"folder": created})
                return
            search_match = re.fullmatch(r"/api/projects/(\d+)/search", self.path)
            if search_match:
                user = self._require_user()
                self._require_permission(user, "project_access")
                payload = self._read_json()
                project = self.server.memory.project(user["id"], int(search_match.group(1)))
                results = search_folder_context(
                    [folder["path"] for folder in project["folders"]],
                    str(payload.get("query", "")),
                )
                self._send_json(200, {"results": results, "sent_to_ai": False})
                return
            clone_match = re.fullmatch(r"/api/chats/(\d+)/clone", self.path)
            if clone_match:
                user = self._require_user()
                chat = self.server.memory.clone_chat(user["id"], int(clone_match.group(1)))
                self._send_json(201, {"chat": chat})
                return
            if self.path == "/api/terminal/preview":
                user = self._require_user()
                self._require_permission(user, "terminal_access")
                payload = self._read_json()
                action = str(payload.get("action", ""))
                preview = command_preview(action)
                project_id = payload.get("project_id")
                working_directory = str(PROJECT_ROOT)
                if project_id is not None:
                    project = self.server.memory.project(user["id"], int(project_id))
                    if project["folders"]:
                        working_directory = project["folders"][0]["path"]
                approval = self.server.memory.create_approval(
                    user["id"],
                    "terminal",
                    {**preview, "working_directory": working_directory},
                )
                self._send_json(201, {"approval": approval})
                return
            if self.path == "/api/workflows":
                user = self._require_user()
                payload = self._read_json()
                steps = payload.get("steps", [])
                if not isinstance(steps, list):
                    raise TypeError("Etapas inválidas.")
                workflow = self.server.memory.create_workflow(
                    user["id"], str(payload.get("name", "")), steps
                )
                self._send_json(201, {"workflow": workflow})
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
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                retry = exc.response.headers.get("retry-after", "")
                delay = int(retry) if retry.isdecimal() and len(retry) < 10 else None
                wait = (
                    f" Aguarde {delay} segundos antes de tentar novamente."
                    if delay
                    else (" Aguarde a renovação do limite e tente novamente.")
                )
                self._send_json(
                    429,
                    {
                        "error": "A Groq atingiu o limite de uso para esta solicitação."
                        + wait
                        + " A conversão /pdf continua disponível porque é local.",
                        "code": "groq_rate_limit",
                        "retry_after": delay,
                    },
                )
            else:
                self._send_json(
                    502,
                    {
                        "error": "A Groq não conseguiu processar a solicitação "
                        f"(HTTP {exc.response.status_code})."
                    },
                )
        except httpx.HTTPError as exc:
            self._send_json(502, {"error": f"Erro no Groq: {exc}"})
        except RuntimeError as exc:
            self._send_json(502, {"error": str(exc)})

    def do_PUT(self) -> None:
        try:
            conflict_match = re.fullmatch(r"/api/memory-conflicts/(\d+)", self.path)
            if conflict_match:
                user = self._require_user()
                self._require_permission(user, "memory_access")
                payload = self._read_json()
                resolved = self.server.memory.resolve_memory_conflict(
                    user["id"], int(conflict_match.group(1)), str(payload.get("choice", ""))
                )
                self._send_json(200, {"resolved": resolved})
                return
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
            project_match = re.fullmatch(r"/api/projects/(\d+)", self.path)
            if project_match:
                user = self._require_user()
                self._require_permission(user, "project_access")
                payload = self._read_json()
                project = self.server.memory.update_project(
                    user["id"],
                    int(project_match.group(1)),
                    str(payload.get("name", "")),
                    str(payload.get("instructions", "")),
                )
                self._send_json(200, {"project": project})
                return
            approval_match = re.fullmatch(r"/api/approvals/(\d+)", self.path)
            if approval_match:
                user = self._require_user()
                payload = self._read_json()
                approval_id = int(approval_match.group(1))
                decision = str(payload.get("decision", ""))
                approval = self.server.memory.approval(user["id"], approval_id)
                if decision == "deny":
                    resolved = self.server.memory.resolve_approval(
                        user["id"], approval_id, "denied"
                    )
                elif decision == "approve":
                    if approval["kind"] == "terminal":
                        self._require_permission(user, "terminal_access")
                        result = execute_command(
                            approval["payload"]["action"],
                            approval["payload"]["working_directory"],
                        )
                    elif approval["kind"] == "assistant_tool":
                        tool_name = str(approval["payload"].get("name", ""))
                        permission = TOOL_PERMISSIONS.get(tool_name)
                        if permission is None:
                            raise ValueError("Ferramenta de aprovação desconhecida.")
                        self._require_permission(user, permission)
                        arguments = approval["payload"].get("arguments", {})
                        if not isinstance(arguments, dict):
                            raise TypeError("Argumentos da ferramenta inválidos.")
                        tools = getattr(self.server.agent, "tools", None)
                        if tools is None:
                            raise RuntimeError("Ferramentas indisponíveis.")
                        output = tools.execute(
                            tool_name,
                            arguments,
                            lambda _request: True,
                            allowed=frozenset({tool_name}),
                        )
                        result = {"ok": True, "output": output}
                    elif approval["kind"] == "project_update":
                        self._require_owner(user)
                        result = apply_update(PROJECT_ROOT, self.server.settings.database_path)
                    else:
                        raise ValueError("Tipo de aprovação desconhecido.")
                    resolved = self.server.memory.resolve_approval(
                        user["id"],
                        approval_id,
                        "approved" if result["ok"] else "failed",
                        result,
                    )
                else:
                    raise ValueError("Decisão inválida.")
                self._send_json(200, {"approval": resolved})
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
        if not isinstance(message, str):
            raise TypeError("A mensagem deve ser texto.")
        message = message.strip()
        mode = str(payload.get("mode", "private"))
        if mode not in {"private", "temporary", "shared"}:
            raise ValueError("Modo de conversa inválido.")
        model = self.server.memory.selected_model(user["id"], self.server.settings.groq_model)
        if model not in self._available_models():
            model = self.server.settings.groq_model
        reasoning_effort = self.server.memory.reasoning_effort(user["id"])
        approved_images: list[str] = []
        raw_images = payload.get("approved_images", [])
        if payload.get("image_consent") is True and isinstance(raw_images, list):
            for image in raw_images[:1]:
                approved_images.append(validate_image(image))
        if approved_images:
            model = VISION_MODEL
            if not message:
                message = "Descreva esta imagem."
        if not message:
            raise ValueError("Envie uma mensagem ou uma imagem.")
        raw_project_id = payload.get("project_id")
        project_id = (
            int(raw_project_id) if raw_project_id not in {None, ""} and mode == "private" else None
        )
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
            chat_id = self.server.memory.create_chat(user["id"], message, project_id)
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
        approved_context: list[str] = []
        raw_context = payload.get("approved_context", [])
        if payload.get("context_consent") is True and isinstance(raw_context, list):
            remaining_context = 60_000
            for item in raw_context[:50]:
                if not isinstance(item, dict):
                    continue
                source = " ".join(str(item.get("source", "Contexto")).split())[:160]
                content = str(item.get("content", "")).strip()[: min(12_000, remaining_context)]
                remaining_context -= len(content)
                if content:
                    approved_context.append(f"Contexto autorizado ({source}):\n{content}")
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
                "memories": [
                    *[f"[{item['category']}] {item['content']}" for item in memory_rows],
                    *approved_context,
                ],
                "allowed_tools": allowed_tools,
            }
            if approved_images:
                if "images" not in inspect.signature(self.server.agent.ask).parameters:
                    raise RuntimeError("O agente atual não aceita imagens.")
                ask_kwargs["images"] = approved_images

            def request_approval(request: dict) -> bool:
                if not isinstance(request, dict):
                    return False
                tool_name = str(request.get("name", ""))
                if tool_name not in allowed_tools:
                    return False
                arguments = request.get("arguments", {})
                if not isinstance(arguments, dict):
                    return False
                self.server.memory.create_approval(
                    user["id"],
                    "assistant_tool",
                    {
                        "name": tool_name,
                        "label": str(request.get("description", tool_name))[:200],
                        "arguments": arguments,
                    },
                )
                return False

            ask_kwargs["confirm"] = request_approval
            if "reasoning_effort" in inspect.signature(self.server.agent.ask).parameters:
                ask_kwargs["reasoning_effort"] = reasoning_effort
            reply, used_model, fallback_used = self._ask_with_fallback(
                user["id"], message, model, ask_kwargs
            )
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
                "model": used_model if not blocked_internal_request else model,
                "fallback_used": fallback_used if not blocked_internal_request else False,
            },
        )

    def _ask_with_fallback(
        self, user_id: int, message: str, primary_model: str, ask_kwargs: dict
    ) -> tuple[str, str, bool]:
        models = [primary_model]
        if not ask_kwargs.get("images"):
            models.extend(model for model in self._available_models() if model != primary_model)
        last_error: Exception | None = None
        supports_model = "model" in inspect.signature(self.server.agent.ask).parameters
        for candidate in models[:2]:
            candidate_kwargs = dict(ask_kwargs)
            if supports_model:
                candidate_kwargs["model"] = candidate
            try:
                confirm = candidate_kwargs.pop("confirm", lambda _request: False)
                reply = self.server.agent.ask(message, confirm, **candidate_kwargs)
                self.server.memory.record_usage(user_id, candidate, True)
                return reply, candidate, candidate != primary_model
            except (httpx.HTTPError, RuntimeError, TypeError, ValueError) as exc:
                self.server.memory.record_usage(user_id, candidate, False)
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    raise
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("Nenhum modelo disponível.")

    def _available_models(self) -> tuple[str, ...]:
        configured = getattr(self.server.settings, "groq_models", ())
        models = tuple(dict.fromkeys((self.server.settings.groq_model, *configured)))
        return models

    @staticmethod
    def _model_label(model: str, version: str) -> str:
        lowered = model.lower()
        if "120b" in lowered:
            suffix = "Potente"
        elif "20b" in lowered or "8b" in lowered:
            suffix = "Rápido"
        else:
            suffix = "Equilibrado"
        return f"Oráculo {version} · {suffix}"

    def _learn_from_message(self, user_id: int, message: str, existing: list[dict]) -> None:
        try:
            changes = self.server.agent.extract_memories(message, existing)
            for memory_key in changes["forget_keys"]:
                self.server.memory.delete_memory_by_key(user_id, memory_key)
            for memory in changes["upserts"]:
                current = self.server.memory.memory_for_key(
                    user_id, memory["category"], memory["key"]
                )
                clean = self.server.memory._clean_memory_content(memory["content"])
                if current and current["content"].casefold() != clean.casefold():
                    self.server.memory.create_memory_conflict(
                        user_id, memory["category"], memory["key"], current["content"], clean
                    )
                else:
                    self.server.memory.upsert_memory(
                        user_id, memory["category"], memory["key"], clean
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
            elif self.path.startswith("/api/vault/"):
                item_id = int(self.path.removeprefix("/api/vault/"))
                deleted = self.server.memory.delete_vault_item(user["id"], item_id)
            elif self.path.startswith("/api/tasks/"):
                task_id = self.path.removeprefix("/api/tasks/")
                self.server.tasks.cancel(user["id"], task_id)
                deleted = True
            elif self.path.startswith("/api/chats/"):
                chat_id = int(self.path.removeprefix("/api/chats/"))
                deleted = self.server.memory.delete_chat(user["id"], chat_id)
            elif self.path.startswith("/api/project-folders/"):
                self._require_permission(user, "project_access")
                folder_id = int(self.path.removeprefix("/api/project-folders/"))
                deleted = self.server.memory.remove_project_folder(user["id"], folder_id)
            elif self.path.startswith("/api/projects/"):
                self._require_permission(user, "project_access")
                project_id = int(self.path.removeprefix("/api/projects/"))
                deleted = self.server.memory.delete_project(user["id"], project_id)
            elif self.path.startswith("/api/workflows/"):
                workflow_id = int(self.path.removeprefix("/api/workflows/"))
                deleted = self.server.memory.delete_workflow(user["id"], workflow_id)
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
    if voice_status()["ready"]:
        variant = voice_status().get("model_variant", "local")
        print(f"Voz local: Kokoro {variant} pm_alex (preparando em segundo plano)")
        threading.Thread(target=warm_voice, daemon=True, name="oraculo-voice-warmup").start()
    print("Pressione Ctrl+C para encerrar.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        server.server_close()
