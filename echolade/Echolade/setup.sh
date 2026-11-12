#!/usr/bin/env bash
# One-time setup for Linux / macOS. Run:  ./setup.sh
set -e
cd "$(dirname "$0")"
PY=""
for c in python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then PY="$c"; break; fi
done
[ -z "$PY" ] && { echo "Python 3.11 or newer is required. Please install it and run setup again."; exit 1; }
echo "Using $($PY --version)"
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo "Downloading and verifying the speech model (internet needed once)..."
python scripts/download_models.py
echo
echo "Setup complete. Start Echolade with:  ./start.sh"
