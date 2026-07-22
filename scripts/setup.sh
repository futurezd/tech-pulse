#!/usr/bin/env bash
# Cross-platform setup (macOS / Linux / Git Bash).
# Windows PowerShell users: run scripts/setup.ps1 instead.
set -e
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv

if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY=".venv/Scripts/python.exe"   # Git Bash on Windows
fi

IDX=()
[ "${USE_MIRROR:-0}" = "1" ] && IDX=(-i https://pypi.tuna.tsinghua.edu.cn/simple)

"$PY" -m pip install --upgrade pip "${IDX[@]}"
"$PY" -m pip install -r scripts/requirements.txt "${IDX[@]}"
echo "tech-pulse deps installed. Run scripts with: $PY scripts/fetch.py ..."
