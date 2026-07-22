param([switch]$UseMirror)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
$idx = @()
if ($UseMirror) { $idx = @("-i","https://pypi.tuna.tsinghua.edu.cn/simple") }
& ".venv\Scripts\python.exe" -m pip install --upgrade pip @idx
& ".venv\Scripts\python.exe" -m pip install -r scripts\requirements.txt @idx
Write-Host "tech-pulse deps installed."