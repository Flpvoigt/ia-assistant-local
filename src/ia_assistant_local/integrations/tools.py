from __future__ import annotations

import platform
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from .home_assistant import HomeAssistantClient


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    confirmation_required: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    ALLOWED_APPLICATIONS: ClassVar[dict[str, list[str]]] = {
        "calculadora": ["calc.exe"],
        "bloco_de_notas": ["notepad.exe"],
    }

    def __init__(self, home: HomeAssistantClient):
        self.home = home
        self.tools = self._build()

    @staticmethod
    def system_info() -> dict[str, str]:
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        }

    @classmethod
    def open_application(cls, application: str) -> dict[str, str]:
        command = cls.ALLOWED_APPLICATIONS.get(application)
        if command is None:
            raise PermissionError(f"Aplicativo nao permitido: {application}")
        subprocess.Popen(command, close_fds=True)
        return {"status": "aberto", "application": application}

    def _build(self) -> dict[str, Tool]:
        entity = {
            "type": "object",
            "properties": {"entity_id": {"type": "string"}},
            "required": ["entity_id"],
        }
        definitions = [
            Tool(
                "system_info",
                "Consulta informacoes basicas do computador.",
                {"type": "object", "properties": {}},
                self.system_info,
            ),
            Tool(
                "open_application",
                "Abre calculadora ou bloco_de_notas.",
                {
                    "type": "object",
                    "properties": {
                        "application": {
                            "type": "string",
                            "enum": sorted(self.ALLOWED_APPLICATIONS),
                        }
                    },
                    "required": ["application"],
                },
                self.open_application,
                True,
            ),
            Tool(
                "get_home_state",
                "Consulta uma entidade permitida do Home Assistant.",
                entity,
                self.home.get_state,
            ),
            Tool(
                "turn_on_home_entity",
                "Liga uma luz ou tomada permitida.",
                entity,
                lambda entity_id: self.home.set_power(entity_id, True),
                True,
            ),
            Tool(
                "turn_off_home_entity",
                "Desliga uma luz ou tomada permitida.",
                entity,
                lambda entity_id: self.home.set_power(entity_id, False),
                True,
            ),
        ]
        return {tool.name: tool for tool in definitions}

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self.tools.values()]

    def execute(self, name: str, arguments: dict, confirm: Callable[[str], bool]) -> Any:
        tool = self.tools.get(name)
        if tool is None:
            raise PermissionError(f"Ferramenta desconhecida: {name}")
        if tool.confirmation_required and not confirm(f"Executar {name} com {arguments}?"):
            return {"status": "cancelado pelo usuario"}
        return tool.handler(**arguments)
