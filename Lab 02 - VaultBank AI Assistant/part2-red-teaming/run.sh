#!/usr/bin/env bash
set -euo pipefail

main() {
  local script_dir lab_dir argument lightweight=false
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  lab_dir="$(dirname "${script_dir}")"
  if ! command -v uv >/dev/null 2>&1; then
    printf 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/\n' >&2
    return 2
  fi
  for argument in "$@"; do
    case "${argument}" in
      --help|-h|--check|--summary|--configure) lightweight=true ;;
    esac
  done
  if [[ "${lightweight}" == true ]]; then
    exec uv run --project "${lab_dir}" --locked \
      python "${script_dir}/redteam_vaultbot.py" "$@"
  fi
  exec uv run --project "${lab_dir}" --locked --extra redteam \
    python "${script_dir}/redteam_vaultbot.py" "$@"
}

main "$@"
