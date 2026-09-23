#!/bin/bash
# Runs the AI Red Teaming Agent scan against VaultBot.
# Requires ./part2_setup.sh to have been run first (creates .env).
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".env" ]; then
  echo "Missing .env. Run ./part2_setup.sh first (or copy .env.example to .env)."
  exit 1
fi

# PyRIT currently supports Python 3.10-3.13, not Python 3.14.
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3.10; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.10-3.13 is required by the AI red teaming dependencies."
  exit 1
fi

# Recreate the generated environment if it uses an unsupported interpreter.
if [ -x ".venv/bin/python" ] && ! .venv/bin/python -c \
  'import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] <= (3, 13)))'; then
  echo "Rebuilding .venv with $($PYTHON_BIN --version 2>&1)."
  rm -rf .venv
fi
if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

python redteam_vaultbot.py "$@"
