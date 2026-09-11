$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    Write-Host "Criando ambiente virtual..."
    python -m venv .venv
}

$python = ".venv\Scripts\python.exe"
& $python -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 'O Oraculo exige Python 3.11, 3.12 ou 3.13.')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Preparando o pip..."
& $python -m ensurepip --upgrade
& $python -m pip install --upgrade pip

Write-Host "Instalando dependencias..."
& $python -m pip install -r requirements.txt
& $python -m pip install -e .

Write-Host "Instalando a voz local Kokoro pm_alex..."
& $python -m ia_assistant_local.core.voice --install
if ($LASTEXITCODE -ne 0) {
    Write-Warning "A voz profissional não foi instalada. O Oráculo usará a voz do navegador até você tentar novamente."
    $global:LASTEXITCODE = 0
}

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Arquivo .env criado."
}

Write-Host ""
Write-Host "Instalacao concluida."
Write-Host "1. Crie sua chave em: https://console.groq.com/keys"
Write-Host "2. Abra o arquivo .env e preencha GROQ_API_KEY."
Write-Host "3. Execute: .\start.ps1"
