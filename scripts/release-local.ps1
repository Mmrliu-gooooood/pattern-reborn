[CmdletBinding()]
param([string]$OutputDirectory, [switch]$Build, [string]$NodeExecutable = "node")
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) { throw "Run scripts\install-local.ps1 first." }
if ($Build) {
    Push-Location (Join-Path $ProjectRoot "web")
    try {
        & $NodeExecutable "node_modules/vite/bin/vite.js" build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
        & $NodeExecutable "scripts/prepare-sites-build.mjs"
        if ($LASTEXITCODE -ne 0) { throw "Frontend packaging failed." }
    } finally { Pop-Location }
}
$Arguments = @((Join-Path $PSScriptRoot "package_local.py"))
if ($OutputDirectory) { $Arguments += @("--output", $OutputDirectory) }
& $VenvPython @Arguments
if ($LASTEXITCODE -ne 0) { throw "Local bundle packaging failed." }
