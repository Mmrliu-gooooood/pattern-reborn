[CmdletBinding()]
param([string]$PythonExe, [switch]$Offline, [string]$Wheelhouse, [switch]$CheckOnly)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
function Test-LocalPython {
    param([string]$Executable, [string[]]$Prefix = @())
    try {
        & $Executable @Prefix -c "import sys,struct; raise SystemExit(0 if sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8 else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}
if ($CheckOnly) {
    if (-not (Test-Path -LiteralPath $VenvPython) -or -not (Test-LocalPython $VenvPython)) { throw "Requires project .venv with Python 3.11 x64." }
    & $VenvPython -c "import pattern_reborn.web_api,cv2,PIL,numpy,pydantic,fastapi,uvicorn"
    if ($LASTEXITCODE -ne 0) { throw "Local web dependencies are incomplete." }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "web/dist/client/index.html"))) { throw "Built frontend is missing." }
    & $VenvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Dependency conflict detected." }
    Write-Output "Local installation checks passed (no install or downloads)."
    exit 0
}
if (-not (Test-Path -LiteralPath $VenvPython)) {
    $SelectedPython = $PythonExe
    $Prefix = @()
    if ($SelectedPython) {
        if (-not (Test-LocalPython $SelectedPython)) { throw "PythonExe must be Python 3.11 x64." }
    } elseif (Test-LocalPython "py" @("-3.11")) { $SelectedPython = "py"; $Prefix = @("-3.11")
    } elseif (Test-LocalPython "python") { $SelectedPython = "python"
    } else { throw "Install Python 3.11 x64 or pass -PythonExe. Global Python packages will not be changed." }
    & $SelectedPython @Prefix -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Project virtual environment creation failed." }
}
if (-not (Test-LocalPython $VenvPython)) { throw "Existing .venv must use Python 3.11 x64; it was preserved. Choose a fresh application folder." }
foreach ($Name in @("pip", "tmp", "huggingface", "torch", "xdg")) { New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot ".cache/$Name") | Out-Null }
$env:PIP_CACHE_DIR = Join-Path $ProjectRoot ".cache/pip"
$env:TEMP = Join-Path $ProjectRoot ".cache/tmp"
$env:TMP = $env:TEMP
$env:HF_HOME = Join-Path $ProjectRoot ".cache/huggingface"
$env:TORCH_HOME = Join-Path $ProjectRoot ".cache/torch"
$env:XDG_CACHE_HOME = Join-Path $ProjectRoot ".cache/xdg"
$PipOptions = @()
if ($Offline) {
    if (-not $Wheelhouse -or -not (Test-Path -LiteralPath $Wheelhouse -PathType Container)) { throw "Offline installation requires -Wheelhouse with compatible dependency and build wheels." }
    $PipOptions += @("--no-index", "--find-links", (Resolve-Path -LiteralPath $Wheelhouse).Path)
}
if (Test-Path -LiteralPath "requirements-release.txt") {
    & $VenvPython -m pip install @PipOptions -r requirements-release.txt
    if ($LASTEXITCODE -ne 0) { throw "Pinned dependency installation failed; existing data is preserved." }
    & $VenvPython -m pip install @PipOptions --no-deps -e .
} else { & $VenvPython -m pip install @PipOptions -e ".[web]" }
if ($LASTEXITCODE -ne 0) { throw "Local installation failed; existing data is preserved." }
& $VenvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependency conflict detected." }
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "web/dist/client/index.html"))) { throw "Install succeeded but the frontend must be built or supplied from the local source bundle." }
$Launcher = '@echo off' + "`r`n" + 'cd /d "%~dp0"' + "`r`n" + 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1"' + "`r`n" + 'if errorlevel 1 pause' + "`r`n"
$LauncherPath = Join-Path $ProjectRoot "Start-Workspace.cmd"
if (-not (Test-Path -LiteralPath $LauncherPath)) { [IO.File]::WriteAllText($LauncherPath, $Launcher, [Text.Encoding]::ASCII) }
Write-Output "Installed in project .venv. Double-click Start-Workspace.cmd to start."
