# Native Windows first-run launcher. Installs Python locally only when needed.
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$kitRoot = $PSScriptRoot
$kitArgs = $args
$venvPython = Join-Path $kitRoot '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    & $venvPython (Join-Path $kitRoot 'launch.py') @kitArgs
    exit $LASTEXITCODE
}
foreach ($candidate in @('py', 'python')) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd -and ($cmd.Source -notlike "*WindowsApps\python*.exe")) {
        try {
            $prevEA = $ErrorActionPreference
            $ErrorActionPreference = 'SilentlyContinue'
            & $candidate -c 'import sys; sys.exit(sys.version_info < (3,11))' 2>$null
            $ok = ($LASTEXITCODE -eq 0)
        } catch {
            $ok = $false
        } finally {
            $ErrorActionPreference = $prevEA
        }
        if ($ok) {
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
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
    if ($LASTEXITCODE -ne 0) { throw 'Python bootstrap installation failed. Run the launcher again to retry.' }
}
& $uv run --no-project --python 3.11 (Join-Path $kitRoot 'launch.py') @kitArgs
exit $LASTEXITCODE

