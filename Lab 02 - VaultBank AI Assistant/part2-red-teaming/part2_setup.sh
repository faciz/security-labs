#!/bin/bash
# Part 2 setup: provision a Microsoft Foundry project for the AI Red Teaming Agent.
#
# The red-teaming agent needs its OWN Foundry project in a region that supports
# AI red teaming (NOT the eastus Azure OpenAI account from Part 1). It scans
# VaultBot remotely over a callback, so VaultBot can keep running on eastus.
#
# Already have a Foundry project? Skip provisioning:
#     AZURE_AI_PROJECT="https://<acct>.services.ai.azure.com/api/projects/<proj>" ./part2_setup.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/.env"
SUPPORTED="eastus2 francecentral swedencentral switzerlandwest northcentralus"
REGION="${REGION:-eastus2}"

echo "== VaultBot Part 2: AI Red Teaming Agent setup =="

# If the user already has a Foundry project, just record it and stop.
if [ -n "$AZURE_AI_PROJECT" ]; then
  echo "Using provided AZURE_AI_PROJECT."
  cat > "$ENV_FILE" <<EOF
AZURE_AI_PROJECT=$AZURE_AI_PROJECT
VAULTBOT_URL=${VAULTBOT_URL:-http://localhost:3000}
EOF
  echo "Wrote $ENV_FILE"
  exit 0
fi

# The red-teaming agent is region-limited — fail early on an unsupported region.
case " $SUPPORTED " in
  *" $REGION "*) : ;;
  *)
    echo "Region '$REGION' does not support AI red teaming."
    echo "Choose one of: $SUPPORTED"
    echo "Re-run with:  REGION=eastus2 ./part2_setup.sh"
    exit 1
    ;;
esac

command -v az  >/dev/null 2>&1 || { echo "Azure CLI not found: https://aka.ms/installazurecli"; exit 1; }
command -v azd >/dev/null 2>&1 || { echo "Azure Developer CLI not found: https://aka.ms/azure-dev/install"; exit 1; }
az account show >/dev/null 2>&1 || { echo "Run 'az login' first."; exit 1; }

PROJECT_DIR="$SCRIPT_DIR/.foundry-project"
ENV_NAME="vaultbot-redteam"

echo "Provisioning a Foundry project in $REGION."
echo "This takes 5-10 minutes and creates billable Azure resources."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

if [ ! -f "azure.yaml" ]; then
  # azd stages template files with Git. Initialize outside this repository
  # because .foundry-project is intentionally ignored by the parent repo.
  INIT_DIR="$(mktemp -d)"
  trap 'rm -rf "$INIT_DIR"' EXIT
  (
    cd "$INIT_DIR"
    AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
      azd init -t Azure-Samples/azd-ai-starter-basic \
      -e "$ENV_NAME" --no-prompt
  )
  cp -a "$INIT_DIR/." "$PROJECT_DIR/"
  rm -rf "$INIT_DIR"
  trap - EXIT
fi
if [ -d ".azure/$ENV_NAME" ]; then
  AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
    azd env select "$ENV_NAME" --no-prompt
else
  AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
    azd env new "$ENV_NAME" \
    --subscription "$(az account show --query id -o tsv)" \
    --location "$REGION" --no-prompt
fi
AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
  azd env set AZURE_LOCATION "$REGION" --no-prompt || \
  AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
    azd config set defaults.location "$REGION"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision --no-prompt

ENDPOINT="$(AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env get-values | sed -n 's/^AZURE_AI_PROJECT_ENDPOINT=//p' | tr -d '"')"
if [ -z "$ENDPOINT" ]; then
  echo "Could not read AZURE_AI_PROJECT_ENDPOINT from azd."
  echo "Inspect 'azd env get-values' and set AZURE_AI_PROJECT in .env manually."
  exit 1
fi

cat > "$ENV_FILE" <<EOF
AZURE_AI_PROJECT=$ENDPOINT
VAULTBOT_URL=${VAULTBOT_URL:-http://localhost:3000}
EOF

echo "Wrote $ENV_FILE"
echo "Done. Start VaultBot (Part 1), then run ./run.sh"
echo "Tear down later with:  (cd .foundry-project && azd down)"
