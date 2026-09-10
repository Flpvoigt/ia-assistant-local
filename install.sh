#!/usr/bin/env bash
set -euo pipefail

project_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$project_root"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 nao encontrado. Instale Python 3.11 ou superior em https://www.python.org/downloads/macos/"
  exit 1
fi

python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else "O Oraculo exige Python 3.11 ou superior.")'

if [ ! -x ".venv/bin/python" ]; then
  echo "Criando ambiente virtual..."
  python3 -m venv .venv
fi

python_bin=".venv/bin/python"
echo "Preparando o pip..."
"$python_bin" -m ensurepip --upgrade
"$python_bin" -m pip install --upgrade pip

echo "Instalando dependencias..."
"$python_bin" -m pip install -r requirements.txt
"$python_bin" -m pip install -e .

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Arquivo .env criado sem sobrescrever configuracoes existentes."
fi

echo
echo "Instalacao concluida."
echo "1. Crie sua chave em: https://console.groq.com/keys"
echo "2. Abra o arquivo .env e preencha GROQ_API_KEY."
echo "3. Execute: bash start.sh"
