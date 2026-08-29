[CmdletBinding()]
param()

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
    (Join-Path $ProjectRoot "models\mobile_sam"),
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

& $VenvPython -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.4.1 torchvision==0.19.1
if ($LASTEXITCODE -ne 0) {
    throw "CPU Torch installation failed with exit code $LASTEXITCODE"
}

& $VenvPython -m pip install "git+https://github.com/ChaoningZhang/MobileSAM.git"
if ($LASTEXITCODE -ne 0) {
    throw "MobileSAM source installation failed with exit code $LASTEXITCODE"
}

$ChecksumPath = Join-Path $PSScriptRoot "mobile_sam_checksum.json"
$CheckpointDir = Join-Path $ProjectRoot "models\mobile_sam"
$CheckpointPath = Join-Path $CheckpointDir "mobile_sam.pt"

& $VenvPython -c @"
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

meta_path = Path(sys.argv[1])
destination = Path(sys.argv[2])
meta = json.loads(meta_path.read_text(encoding='utf-8'))
expected = str(meta['sha256']).lower()
url = str(meta['source_url'])
destination.parent.mkdir(parents=True, exist_ok=True)

def digest_of(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()

if destination.is_file() and digest_of(destination) == expected:
    print('MobileSAM checkpoint already present and verified.')
    raise SystemExit(0)

partial = destination.with_name(destination.name + '.partial')
try:
    urllib.request.urlretrieve(url, partial)
    actual = digest_of(partial)
    if actual != expected:
        partial.unlink(missing_ok=True)
        raise SystemExit(f'Checkpoint SHA-256 mismatch: expected {expected}, got {actual}')
    partial.replace(destination)
    print('MobileSAM checkpoint downloaded and verified.')
except BaseException:
    if partial.exists():
        partial.unlink()
    raise
"@ $ChecksumPath $CheckpointPath
if ($LASTEXITCODE -ne 0) {
    throw "MobileSAM checkpoint verification failed with exit code $LASTEXITCODE"
}
