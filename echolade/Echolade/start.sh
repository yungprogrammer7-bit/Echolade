#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Echolade is not set up yet. Run ./setup.sh first."; exit 1; }
exec .venv/bin/python -m backend "$@"
