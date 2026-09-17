param([switch]$SkipBuild)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))

Push-Location $ProjectRoot
try {
    if (-not $SkipBuild) {
        & ".\scripts\windows\build.ps1"
        if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar a versão Windows." }
    }

    $VercelCommand = Get-Command "vercel.cmd" -ErrorAction SilentlyContinue
    $VercelPath = if ($VercelCommand) { $VercelCommand.Source } else { $null }
    if (-not $VercelPath) {
        $Candidate = Join-Path $env:APPDATA "npm\vercel.cmd"
        if (Test-Path -LiteralPath $Candidate) {
            $VercelPath = $Candidate
        }
    }
    if (-not $VercelPath) {
        throw "Vercel CLI não encontrada. Instale com: npm install --global vercel"
    }

    Push-Location "download-site"
    try {
        & $VercelPath deploy --prod --yes
        if ($LASTEXITCODE -ne 0) { throw "Falha ao publicar a versão na Vercel." }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}
