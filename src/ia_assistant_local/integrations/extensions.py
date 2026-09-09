from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Extension:
    id: str
    name: str
    description: str
    status: str
    configured: bool
    capabilities: tuple[str, ...]

    def public(self) -> dict:
        payload = asdict(self)
        payload["capabilities"] = list(self.capabilities)
        return payload


def extension_catalog(home_assistant_configured: bool) -> list[dict]:
    extensions = (
        Extension(
            "core",
            "Núcleo local",
            "Informações do sistema e aplicativos permitidos.",
            "active",
            True,
            ("Sistema", "Aplicativos"),
        ),
        Extension(
            "home_assistant",
            "Home Assistant",
            "Consulta de estados e controle de luzes e tomadas autorizadas.",
            "active" if home_assistant_configured else "setup_required",
            home_assistant_configured,
            ("Estados", "Luzes", "Tomadas"),
        ),
    )
    return [extension.public() for extension in extensions]
