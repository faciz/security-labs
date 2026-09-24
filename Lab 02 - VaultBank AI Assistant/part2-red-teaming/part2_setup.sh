#!/usr/bin/env bash
set -euo pipefail

main() {
  local script_dir lab_dir project_dir region env_name subscription endpoint
  local provision=false approved=false argument
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  lab_dir="$(dirname "${script_dir}")"
  project_dir="${script_dir}/.foundry-project"
  region="${REGION:-eastus2}"
  env_name="${ENV_NAME:-vaultbot-redteam}"
  for argument in "$@"; do
    case "${argument}" in
      --provision) provision=true ;;
      --yes) approved=true ;;
      --help|-h)
        printf 'Usage: ./part2_setup.sh [--provision --yes]\n'
        printf 'Default: save AZURE_AI_PROJECT or preserve existing settings.\n'
        printf 'Provisioning creates billable resources. REGION defaults to eastus2.\n'
        return 0 ;;
      *) printf 'Unknown argument: %s\n' "${argument}" >&2; return 2 ;;
    esac
  done
  if [[ -f "${script_dir}/.env" ]]; then
    printf 'Existing Foundry connection preserved. No resources created.\n'
    return 0
  fi
  command -v uv >/dev/null 2>&1 || { printf 'Install uv first.\n' >&2; return 2; }
  if [[ -n "${AZURE_AI_PROJECT:-}" ]]; then
    exec uv run --project "${lab_dir}" --locked \
      python "${script_dir}/redteam_vaultbot.py" --configure
  fi
  if [[ "${provision}" != true || "${approved}" != true ]]; then
    printf 'Set AZURE_AI_PROJECT for an existing project, or use --provision --yes.\n' >&2
    printf 'Provisioning creates billable resources; review the Part 2 guide first.\n' >&2
    return 2
  fi
  command -v az >/dev/null 2>&1 || { printf 'Azure CLI is required.\n' >&2; return 2; }
  command -v azd >/dev/null 2>&1 || { printf 'Azure Developer CLI is required.\n' >&2; return 2; }
  subscription="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
  printf 'Approved Foundry provisioning in %s. Check current preview regional support.\n' "${region}"
  mkdir -p "${project_dir}"
  if [[ ! -f "${project_dir}/azure.yaml" ]]; then
    local init_dir
    init_dir="$(mktemp -d)"
    trap 'rm -rf -- "${init_dir}"' EXIT
    cd "${init_dir}"
    azd init -t Azure-Samples/azd-ai-starter-basic -e "${env_name}" --no-prompt
    cp -a "${init_dir}/." "${project_dir}/"
    cd "${project_dir}"
    rm -rf -- "${init_dir}"
    trap - EXIT
  else
    cd "${project_dir}"
  fi
  if [[ -d ".azure/${env_name}" ]]; then
    azd env select "${env_name}" --no-prompt
  else
    azd env new "${env_name}" --subscription "${subscription}" \
      --location "${region}" --no-prompt
  fi
  azd env set AZURE_LOCATION "${region}"
  azd provision --no-prompt
  endpoint="$(azd env get-value AZURE_AI_PROJECT_ENDPOINT)"
  if [[ -z "${endpoint}" ]]; then
    printf 'Provisioning did not return a project endpoint. Inspect the azd environment.\n' >&2
    return 1
  fi
  AZURE_AI_PROJECT="${endpoint}" uv run --project "${lab_dir}" --locked \
    python "${script_dir}/redteam_vaultbot.py" --configure
  printf 'Setup complete. Run ./run.sh --check before an approved scan.\n'
  printf 'Cleanup: run azd down inside the generated Foundry project directory.\n'
}

main "$@"
