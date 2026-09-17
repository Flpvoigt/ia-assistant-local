param([switch]$SkipInstaller)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Icon = Join-Path $ProjectRoot "build\windows\oraculo.ico"
$SourceRoot = Join-Path $ProjectRoot "src"
$WebAssets = Join-Path $ProjectRoot "src\ia_assistant_local\web"
$EnvExample = Join-Path $ProjectRoot ".env.example"
$DesktopEntry = Join-Path $ProjectRoot "packaging\windows\entrypoints\desktop.py"
$UpdaterEntry = Join-Path $ProjectRoot "packaging\windows\entrypoints\updater.py"
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
        "--specpath", "build\windows\specs", "--workpath", "build\pyinstaller",
        "--name", "Oraculo", "--icon", $Icon, "--paths", $SourceRoot,
        "--add-data", "$WebAssets;ia_assistant_local\web",
        "--add-data", "$EnvExample;.", "--collect-all", "webview",
        "--collect-all", "kokoro_onnx", "--collect-all", "espeakng_loader",
        "--collect-all", "phonemizer", "--collect-all", "onnxruntime",
        "--hidden-import", "webview.platforms.edgechromium",
        "--hidden-import", "clr", $DesktopEntry
    )
    & $Python -m PyInstaller @PyInstallerArgs
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o aplicativo." }

    $UpdaterArgs = @(
        "--noconfirm", "--clean", "--windowed", "--onefile",
        "--specpath", "build\windows\specs", "--workpath", "build\pyinstaller",
        "--name", "OraculoUpdater", "--icon", $Icon, "--paths", $SourceRoot,
        $UpdaterEntry
    )
    & $Python -m PyInstaller @UpdaterArgs
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o atualizador." }
    Copy-Item "dist\OraculoUpdater.exe" "dist\Oraculo\OraculoUpdater.exe" -Force

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
    & $InnoCompiler "packaging\windows\oraculo.iss"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador." }

    $Installer = Join-Path $ProjectRoot "dist\installer\Oraculo-Setup.exe"
    $DownloadDirectory = Join-Path $ProjectRoot "download-site\public\downloads"
    $ManifestPath = Join-Path $ProjectRoot "download-site\public\update.json"
    $Version = (& $Python -c "from ia_assistant_local import __version__; print(__version__)").Trim()
    $InstallerFileName = "Oraculo-Setup-$Version.exe"
    $DownloadInstaller = Join-Path $DownloadDirectory $InstallerFileName
    $InstallerHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Installer).Hash.ToLowerInvariant()
    $InstallerSize = (Get-Item -LiteralPath $Installer).Length
    $Manifest = [ordered]@{
        version = $Version
        url = "https://oraculo-desktop.vercel.app/downloads/$InstallerFileName"
        sha256 = $InstallerHash
        size = $InstallerSize
        notes = @(
            "Perfil local com acesso direto, sem cadastro ou senha"
            "Área administrativa opcional com autenticação preservada"
            "Atualizações automáticas em segundo plano"
            "Verificação SHA-256 antes da instalação"
            "Instalação silenciosa quando o Oráculo estiver fechado"
        )
    }
    New-Item -ItemType Directory -Path $DownloadDirectory -Force | Out-Null
    Get-ChildItem -LiteralPath $DownloadDirectory -Filter "Oraculo-Setup*.exe" -File |
        Remove-Item -Force
    Copy-Item -LiteralPath $Installer -Destination $DownloadInstaller -Force
    $ManifestJson = $Manifest | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText(
        $ManifestPath,
        $ManifestJson + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Instalador gerado em dist\installer\Oraculo-Setup.exe"
    Write-Host "Manifesto de atualização gerado em download-site\public\update.json"
} finally {
    Pop-Location
}
