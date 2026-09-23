#!/bin/bash
# Starts the VaultBot vulnerable chatbot locally.
# Requires ./lab02_setup.sh to have been run first (creates .env + .secrets/).

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".env" ] || [ ! -f ".secrets/vault_data.json" ]; then
  echo "Missing generated config. Run the setup script first:"
  echo "    cd '../' && ./lab02_setup.sh"
  exit 1
fi

# Use a virtual environment so dependencies stay isolated.
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "Starting VaultBot on http://localhost:3000 ..."
python app.py
