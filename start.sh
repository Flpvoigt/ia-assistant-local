#!/usr/bin/env bash
set -euo pipefail

project_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$project_root"

executable=".venv/bin/ia-assistant"
if [ ! -x "$executable" ]; then
  echo "Projeto nao instalado. Execute primeiro: bash install.sh"
  exit 1
fi
if [ ! -f ".env" ]; then
  echo "Arquivo .env ausente. Execute primeiro: bash install.sh"
  exit 1
fi
if ! grep -Eq '^[[:space:]]*GROQ_API_KEY[[:space:]]*=[[:space:]]*[^[:space:]#]+' .env; then
  echo "GROQ_API_KEY vazia. Crie uma chave em https://console.groq.com/keys e coloque-a no arquivo .env."
  exit 1
fi

exec "$executable"
