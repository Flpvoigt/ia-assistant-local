$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

$executable = ".venv\Scripts\ia-assistant.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "Projeto nao instalado. Execute primeiro: .\install.ps1"
}
if (-not (Test-Path -LiteralPath ".env")) {
    throw "Arquivo .env ausente. Execute primeiro: .\install.ps1"
}

$keyLine = Get-Content -LiteralPath ".env" |
    Where-Object { $_ -match "^\s*GROQ_API_KEY\s*=" } |
    Select-Object -First 1
$apiKey = if ($keyLine) { ($keyLine -split "=", 2)[1].Trim() } else { "" }
if (-not $apiKey) {
    throw "GROQ_API_KEY vazia. Crie uma chave em https://console.groq.com/keys e coloque-a no arquivo .env."
}

& $executable
