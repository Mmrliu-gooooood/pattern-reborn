[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$ArchivePath, [Parameter(Mandatory = $true)][string]$Destination)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) { throw "Run this from an installed Python 3.11 workspace." }
& $VenvPython (Join-Path $PSScriptRoot "upgrade_local.py") $ArchivePath $Destination
if ($LASTEXITCODE -ne 0) { throw "Upgrade stopped. The previous installation and its data remain intact; inspect the new folder if one was created." }
Write-Output "Copied to a new application folder. Install its local dependencies there, then start and verify it. Keep the previous folder as your rollback backup."
