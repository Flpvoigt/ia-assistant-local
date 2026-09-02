from __future__ import annotations

import httpx

from .agent import LocalAgent
from .config import Settings
from .home_assistant import HomeAssistantClient
from .tools import ToolRegistry


def _confirm(message: str) -> bool:
    answer = input(f"\nCONFIRMACAO: {message} [s/N] ").strip().lower()
    return answer in {"s", "sim"}


def main() -> None:
    settings = Settings.from_env()
    home = HomeAssistantClient(
        settings.home_assistant_url,
        settings.home_assistant_token,
        settings.allowed_entities,
    )
    agent = LocalAgent(settings.ollama_url, settings.ollama_model, ToolRegistry(home))
    print(f"IA Assistant Local | modelo: {settings.ollama_model} | /sair para encerrar")
    while True:
        prompt = input("\nVoce: ").strip()
        if prompt.lower() in {"/sair", "sair", "exit", "quit"}:
            break
        if not prompt:
            continue
        try:
            print(f"Assistente: {agent.ask(prompt, _confirm)}")
        except httpx.ConnectError:
            print("Assistente: nao foi possivel conectar ao Ollama.")
        except httpx.HTTPError as exc:
            print(f"Assistente: erro no servico local: {exc}")


if __name__ == "__main__":
    main()
