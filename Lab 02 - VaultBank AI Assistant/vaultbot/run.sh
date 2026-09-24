#!/usr/bin/env bash
set -euo pipefail

main() {
  local script_dir lab_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  lab_dir="$(dirname "${script_dir}")"
  if [[ "${1:-}" == "--help" ]]; then
    printf 'Usage: ./vaultbot/run.sh\nOptional environment: PORT, HOST, VAULTBOT_OFFLINE=1\n'
    return 0
  fi
  if (( $# > 0 )); then
    printf 'Unknown argument. Use --help.\n' >&2
    return 2
  fi
  if ! command -v uv >/dev/null 2>&1; then
    printf 'Install uv, then run ./lab02_setup.sh.\n' >&2
    return 2
  fi
  if [[ ! -f "${VAULTBOT_DATA_PATH:-${script_dir}/.secrets/vault_data.json}" ]]; then
    printf 'Training data is missing. Run ./lab02_setup.sh first.\n' >&2
    return 2
  fi
  printf 'Starting VaultBank: intentionally vulnerable, loopback-only by default.\n'
  exec uv run --project "${lab_dir}" --locked python "${script_dir}/app.py"
}

main "$@"
