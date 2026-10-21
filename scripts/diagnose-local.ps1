[CmdletBinding()]
param([string]$OutputPath)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) { throw "Project .venv is missing; install Python 3.11 x64 with scripts\install-local.ps1 first." }
$Arguments = @((Join-Path $PSScriptRoot "diagnose_local.py"))
if ($OutputPath) { $Arguments += @("--output", $OutputPath) }
& $VenvPython @Arguments
if ($LASTEXITCODE -ne 0) { throw "Diagnostic report could not be written." }
