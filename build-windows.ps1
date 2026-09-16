param([switch]$SkipInstaller)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Icon = Join-Path $ProjectRoot "build\windows\oraculo.ico"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Ambiente virtual não encontrado. Execute .\install.ps1 primeiro."
}

Push-Location $ProjectRoot
try {
    & $Python -m pip install -e ".[windows,build]"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências de build." }
    & $Python "tools\create_windows_icon.py" $Icon
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ícone." }

    $PyInstallerArgs = @(
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "Oraculo", "--icon", $Icon, "--paths", "src",
        "--add-data", "src\ia_assistant_local\web;ia_assistant_local\web",
        "--add-data", ".env.example;.", "--collect-all", "webview",
        "--collect-all", "kokoro_onnx", "--collect-all", "espeakng_loader",
        "--collect-all", "phonemizer", "--collect-all", "onnxruntime",
        "--hidden-import", "webview.platforms.edgechromium",
        "--hidden-import", "clr", "oraculo_desktop.py"
    )
    & $Python -m PyInstaller @PyInstallerArgs
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o aplicativo." }
    if ($SkipInstaller) {
        Write-Host "Aplicativo gerado em dist\Oraculo\Oraculo.exe"
        exit 0
    }

    $CompilerCandidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$([Environment]::GetFolderPath('ProgramFilesX86'))\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $InnoCompiler = $CompilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $InnoCompiler) { throw "Inno Setup 6 não encontrado. Instale-o ou use -SkipInstaller." }
    & $InnoCompiler "installer\oraculo.iss"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador." }
    Write-Host "Instalador gerado em dist\installer\Oraculo-Setup.exe"
} finally {
    Pop-Location
}
