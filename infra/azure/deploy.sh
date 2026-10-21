#!/usr/bin/env bash
# Deploy Football Intelligence OS to Azure.
#   ./infra/azure/deploy.sh <resource-group> <location>
# Reads Azure OpenAI / Speech / Document Intelligence settings from backend/.env and stores the keys in
# Key Vault — no secret is ever written into an image or a Bicep parameter file.
set -euo pipefail
RG=${1:?resource group}
LOC=${2:-eastus}
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
set -a; source "$ROOT/backend/.env"; set +a
MONGO_PW=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)Aa1

az group create -n "$RG" -l "$LOC" -o none

# 1) bootstrap: registry + vault (first pass with placeholder images)
PLACEHOLDER=mcr.microsoft.com/azuredocs/containerapps-helloworld:latest
az deployment group create -g "$RG" -f "$ROOT/infra/azure/main.bicep" -o none \
  -p backendImage=$PLACEHOLDER frontendImage=$PLACEHOLDER openAiEndpoint="$AZURE_OPENAI_ENDPOINT" \
     openAiDeployment="$AZURE_OPENAI_DEPLOYMENT" speechRegion="${AZURE_SPEECH_REGION:-eastus}" \
     docIntelEndpoint="${AZURE_DOC_INTEL_ENDPOINT:-}" mongoAdminPassword="$MONGO_PW" || true

OUT=$(az deployment group show -g "$RG" -n main --query properties.outputs -o json)
KV=$(echo "$OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['keyVaultName']['value'])")
ACR=$(echo "$OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['acrName']['value'])")
MONGO_CS=$(echo "$OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['mongoHost']['value'])")
MONGO_URI=${MONGO_CS/<user>/fiosadmin}; MONGO_URI=${MONGO_URI/<password>/$MONGO_PW}

# 2) secrets → Key Vault (caller needs 'Key Vault Secrets Officer' on the vault)
az keyvault secret set --vault-name "$KV" -n openai-key --value "$AZURE_OPENAI_API_KEY" -o none
az keyvault secret set --vault-name "$KV" -n speech-key --value "${AZURE_SPEECH_KEY:-unset}" -o none
az keyvault secret set --vault-name "$KV" -n docintel-key --value "${AZURE_DOC_INTEL_KEY:-unset}" -o none
az keyvault secret set --vault-name "$KV" -n mongo-uri --value "$MONGO_URI" -o none

# 3) build images in ACR (no local Docker needed)
TAG=$(date +%Y%m%d%H%M)
az acr build -r "$ACR" -t fios-api:$TAG "$ROOT/backend" -o none
az acr build -r "$ACR" -t fios-web:$TAG "$ROOT/frontend" -o none

# 4) final deployment with real images
az deployment group create -g "$RG" -f "$ROOT/infra/azure/main.bicep" -o table \
  -p backendImage="$ACR.azurecr.io/fios-api:$TAG" frontendImage="$ACR.azurecr.io/fios-web:$TAG" \
     openAiEndpoint="$AZURE_OPENAI_ENDPOINT" openAiDeployment="$AZURE_OPENAI_DEPLOYMENT" \
     speechRegion="${AZURE_SPEECH_REGION:-eastus}" docIntelEndpoint="${AZURE_DOC_INTEL_ENDPOINT:-}" mongoAdminPassword="$MONGO_PW"

az deployment group show -g "$RG" -n main --query properties.outputs.webUrl.value -o tsv
