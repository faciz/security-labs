#!/usr/bin/env bash
set -euo pipefail

main() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if ! command -v uv >/dev/null 2>&1; then
    printf 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/\n' >&2
    return 2
  fi
  exec uv run --project "${script_dir}" --locked \
    python "${script_dir}/vaultbot/setup_lab.py" "$@"
}

main "$@"
