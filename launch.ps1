# Native Windows first-run launcher. Installs Python locally only when needed.
$ErrorActionPreference = 'Stop'
$kitRoot = $PSScriptRoot
$kitArgs = $args
$venvPython = Join-Path $kitRoot '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    & $venvPython (Join-Path $kitRoot 'launch.py') @kitArgs
    exit $LASTEXITCODE
}
foreach ($candidate in @('py', 'python')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        & $candidate -c 'import sys; sys.exit(sys.version_info < (3,11))' 2>$null
        if ($LASTEXITCODE -eq 0) {
            & $candidate (Join-Path $kitRoot 'launch.py') @kitArgs
            exit $LASTEXITCODE
        }
    }
}
$bootstrap = Join-Path $kitRoot '.bootstrap'
$uv = Join-Path $bootstrap 'uv.exe'
if (!(Test-Path $uv)) {
    New-Item -ItemType Directory -Force -Path $bootstrap | Out-Null
    $installer = Join-Path $bootstrap 'install-uv.ps1'
    Invoke-WebRequest -UseBasicParsing 'https://astral.sh/uv/install.ps1' -OutFile $installer
    $env:UV_INSTALL_DIR = $bootstrap
    $env:UV_NO_MODIFY_PATH = '1'
    & $installer
    if ($LASTEXITCODE -ne 0) { throw 'Python bootstrap installation failed. Run the launcher again to retry.' }
}
& $uv run --no-project --python 3.11 (Join-Path $kitRoot 'launch.py') @kitArgs
exit $LASTEXITCODE
