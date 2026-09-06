#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "======================================================================"
echo "   OpenFOAM Studio - Case Generator & Cluster Dispatcher"
echo "======================================================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found. Please install Python 3.9+."
    exit 1
fi

VENV_DIR="$DIR/.venv"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "[*] Creating virtual environment in .venv..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "[*] Checking web dependencies..."
pip install -e ".[web]" --quiet

echo ""
echo "[*] Starting CFD Studio Web Server..."
echo "[*] Browser will open automatically at http://127.0.0.1:8000"
echo ""

python3 -m cfd_gen.web.server
