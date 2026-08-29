[CmdletBinding()]
param(
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Test-Python311 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [string[]]$PrefixArguments = @()
    )

    try {
        $version = & $Executable @PrefixArguments -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        return $LASTEXITCODE -eq 0 -and ((@($version) -join "").Trim() -eq "3.11")
    }
    catch {
        return $false
    }
}

$SelectedPython = $null
$SelectedPythonArguments = @()

if ($PSBoundParameters.ContainsKey("PythonExe")) {
    if (Test-Python311 -Executable $PythonExe) {
        $SelectedPython = $PythonExe
    }
    else {
        throw "The supplied Python executable is not Python 3.11: $PythonExe"
    }
}
else {
    $Probes = @(
        @{ Executable = "py"; PrefixArguments = @("-3.11") },
        @{ Executable = "python"; PrefixArguments = @() }
    )

    foreach ($Probe in $Probes) {
        if (Test-Python311 -Executable $Probe.Executable -PrefixArguments $Probe.PrefixArguments) {
            $SelectedPython = $Probe.Executable
            $SelectedPythonArguments = $Probe.PrefixArguments
            break
        }
    }

    if ($null -eq $SelectedPython) {
        throw "Python 3.11 was not found. Pass -PythonExe with a Python 3.11 executable."
    }
}

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

$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    & $SelectedPython @SelectedPythonArguments -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Virtual environment creation failed with exit code $LASTEXITCODE"
    }
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed with exit code $LASTEXITCODE"
}
& $VenvPython -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "dependency installation failed with exit code $LASTEXITCODE"
}
