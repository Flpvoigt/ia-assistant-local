$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    Write-Host "Criando ambiente virtual..."
    python -m venv .venv
}

$python = ".venv\Scripts\python.exe"
Write-Host "Preparando o pip..."
& $python -m ensurepip --upgrade
& $python -m pip install --upgrade pip

Write-Host "Instalando dependencias..."
& $python -m pip install -r requirements.txt
& $python -m pip install -e .

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Arquivo .env criado."
}

Write-Host ""
Write-Host "Instalacao concluida."
Write-Host "1. Crie sua chave em: https://console.groq.com/keys"
Write-Host "2. Abra o arquivo .env e preencha GROQ_API_KEY."
Write-Host "3. Execute: .\start.ps1"
