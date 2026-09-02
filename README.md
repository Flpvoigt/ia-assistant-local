# IA Assistant Local

Assistente local para controlar, com seguranca, o computador e uma casa conectada.
O modelo roda no Ollama; toda acao passa por uma lista explicita de ferramentas,
validacao de argumentos e confirmacao humana.

> Projeto inicial. Nao use para fechaduras, alarmes, cameras, compras ou operacoes criticas.

## Objetivos do MVP

- conversar pelo terminal usando um modelo local;
- consultar informacoes basicas do computador;
- abrir somente aplicativos previamente permitidos;
- consultar e controlar somente entidades permitidas do Home Assistant;
- pedir confirmacao antes de qualquer acao que altere o ambiente;
- testar automaticamente as regras de seguranca.

## Requisitos

- Python 3.11 ou superior;
- Ollama em execucao;
- Home Assistant e token de longa duracao somente para integrar a casa.

## Instalacao no Windows

```powershell
git clone https://github.com/Flpvoigt/ia-assistant-local.git
cd ia-assistant-local
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
ollama pull qwen3:8b
ia-assistant
```

O `.env` nunca deve ser enviado ao Git. Sem os dados do Home Assistant, as
ferramentas da casa permanecem indisponiveis.

## Desenvolvimento

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Leia `CONTRIBUTING.md`, `docs/ARCHITECTURE.md` e `SECURITY.md` antes de
adicionar ferramentas.
