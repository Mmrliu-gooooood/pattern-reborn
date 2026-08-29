[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

$Runtime = @{
    PIP_CACHE_DIR = Join-Path $ProjectRoot ".cache\pip"
    HF_HOME = Join-Path $ProjectRoot ".cache\huggingface"
    TORCH_HOME = Join-Path $ProjectRoot ".cache\torch"
    XDG_CACHE_HOME = Join-Path $ProjectRoot ".cache\xdg"
    TEMP = Join-Path $ProjectRoot ".cache\tmp"
    TMP = Join-Path $ProjectRoot ".cache\tmp"
}
$MutableDirectories = @(
    $Runtime.PIP_CACHE_DIR,
    $Runtime.HF_HOME,
    $Runtime.TORCH_HOME,
    $Runtime.XDG_CACHE_HOME,
    $Runtime.TEMP,
    $Runtime.TMP,
    (Join-Path $ProjectRoot "models"),
    (Join-Path $ProjectRoot "workspace"),
    (Join-Path $ProjectRoot "outputs")
)

foreach ($Directory in $MutableDirectories) {
    New-Item -ItemType Directory -Force -Path $Directory | Out-Null
}
foreach ($Variable in $Runtime.Keys) {
    Set-Item -Path "Env:$Variable" -Value $Runtime[$Variable]
}

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "Project virtual environment is missing. Run scripts\bootstrap.ps1 first."
}

$App = Join-Path $ProjectRoot "app.py"
& $VenvPython -m streamlit run $App @Arguments
exit $LASTEXITCODE
