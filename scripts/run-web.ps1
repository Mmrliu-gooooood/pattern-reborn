[CmdletBinding()]
param(
    [int]$Port = 8510,
    [switch]$Build,
    [string]$NodeExecutable = "node"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "Run scripts\bootstrap.ps1 and install the web extra into .venv first."
}
foreach ($Name in @("TEMP", "TMP")) {
    $LocalTemp = Join-Path $ProjectRoot ".cache\tmp"
    New-Item -ItemType Directory -Force -Path $LocalTemp | Out-Null
    Set-Item -Path "Env:$Name" -Value $LocalTemp
}
if ($Build) {
    Push-Location (Join-Path $ProjectRoot "web")
    try {
        & $NodeExecutable "node_modules/vite/bin/vite.js" build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
        & $NodeExecutable "scripts/prepare-sites-build.mjs"
        if ($LASTEXITCODE -ne 0) { throw "Frontend packaging failed." }
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "web/dist/client/index.html"))) {
    throw "Build the frontend first: install web dependencies, then run this script with -Build."
}
& $VenvPython -m pattern_reborn.web_api --port $Port
exit $LASTEXITCODE
