[CmdletBinding()]
param([int]$Port = 8510)
$ErrorActionPreference = "Stop"
if ($Port -lt 1024 -or $Port -gt 65535) { throw "Port must be between 1024 and 65535." }
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Write-Output "Open http://127.0.0.1:$Port in your browser. Keep this window open; Ctrl+C stops the workspace."
& (Join-Path $PSScriptRoot "run-web.ps1") -Port $Port
exit $LASTEXITCODE
