#!/usr/bin/env bash
# Planwerk: one-time Azure setup without Terraform, for Azure Cloud Shell (Bash).
# Open https://portal.azure.com, click the Cloud Shell icon (>_) at the top, choose Bash, then run:
#   curl -fsSL https://raw.githubusercontent.com/Parsaka/planwerk/main/infra/azure/cloudshell_setup.sh | bash
#
# Creates, in an allowed EU region of Azure for Students (swedencentral):
#   - resource group rg-planwerk
#   - Azure OpenAI account with Entra ID sign-in only (no API keys) and one small chat model
#     (gpt-4o-mini, or a newer one if Azure refuses it) capped at 30k tokens per minute
#   - an app registration that GitHub Actions of Parsaka/planwerk (environment "eval") can use via
#     OIDC, with the role "Cognitive Services OpenAI User" on that account only
# Prints seven values at the end. None of them is a secret. Safe to run twice.
set -euo pipefail

LOC="${LOC:-swedencentral}"
RG="${RG:-rg-planwerk}"
REPO="${REPO:-Parsaka/planwerk}"
# Models are tried in this order. gpt-4o-mini is the model this setup was first deployed with; Microsoft
# lists it and gpt-4.1-mini as deprecated (retirement 14 April 2027) and says subscriptions without an
# earlier deployment may be refused, so the GA models gpt-5-mini and gpt-5-nano follow as fallback.
# Override with MODELS="name:version ..." if needed.
MODELS="${MODELS:-gpt-4o-mini:2024-07-18 gpt-4.1-mini:2025-04-14 gpt-5-mini:2025-08-07 gpt-5-nano:2025-08-07}"
# thousand tokens per minute; a hard throughput cap, not a price (billing is per token)
CAPACITIES="${CAPACITIES:-30 10}"
APP_NAME="${APP_NAME:-planwerk-github-eval}"

SUB=$(az account show --query id -o tsv)
TENANT=$(az account show --query tenantId -o tsv)
echo "Subscription: $(az account show --query name -o tsv)"

az provider register --namespace Microsoft.CognitiveServices --wait >/dev/null
az group create -n "$RG" -l "$LOC" --tags project=planwerk data=simulated -o none

# One OpenAI account per subscription; reuse it when the script runs again.
AOAI=$(az cognitiveservices account list -g "$RG" --query "[?kind=='OpenAI'].name | [0]" -o tsv)
if [ -z "$AOAI" ]; then
  AOAI="aoai-planwerk-$(tr -dc 'a-z0-9' </dev/urandom | head -c 6)"
  az cognitiveservices account create -n "$AOAI" -g "$RG" -l "$LOC" --kind OpenAI --sku S0 \
    --custom-domain "$AOAI" --tags project=planwerk -o none
fi
# Entra ID only: API keys are switched off
az resource update -g "$RG" -n "$AOAI" --resource-type Microsoft.CognitiveServices/accounts \
  --set properties.disableLocalAuth=true -o none
AOAI_ID=$(az cognitiveservices account show -n "$AOAI" -g "$RG" --query id -o tsv)
ENDPOINT=$(az cognitiveservices account show -n "$AOAI" -g "$RG" --query properties.endpoint -o tsv)

# Reuse the deployment of an earlier run of this script, whatever it is called.
EXISTING=$(az cognitiveservices account deployment list -n "$AOAI" -g "$RG" --query "[0].name" -o tsv 2>/dev/null || true)
DEPLOYMENT="${DEPLOYMENT:-${EXISTING:-planwerk-chat}}"

# EU data zone first; student subscriptions sometimes only offer the global or regional SKU.
if ! az cognitiveservices account deployment show -n "$AOAI" -g "$RG" --deployment-name "$DEPLOYMENT" -o none 2>/dev/null; then
  CREATED=""
  for M in $MODELS; do
    for SKU in DataZoneStandard GlobalStandard Standard; do
      for CAP in $CAPACITIES; do
        if ERR=$(az cognitiveservices account deployment create -n "$AOAI" -g "$RG" --deployment-name "$DEPLOYMENT" \
             --model-name "${M%%:*}" --model-version "${M##*:}" --model-format OpenAI \
             --sku-name "$SKU" --sku-capacity "$CAP" -o none 2>&1); then
          echo "Deployment $DEPLOYMENT created: model ${M%%:*} (${M##*:}), SKU $SKU, ${CAP}k tokens per minute"
          CREATED=1; break 3
        fi
        LAST_ERR="$ERR"
      done
    done
    echo "Model ${M%%:*} is not available to this subscription here, trying the next one"
  done
  if [ -z "$CREATED" ]; then
    echo "ERROR: no model could be deployed in $LOC. Last message from Azure:" >&2
    echo "$LAST_ERR" >&2
    echo "Check the quota under Azure AI Foundry > Quotas, or run again with another region: LOC=<region> bash ..." >&2
    exit 1
  fi
fi
SKU_USED=$(az cognitiveservices account deployment show -n "$AOAI" -g "$RG" --deployment-name "$DEPLOYMENT" --query sku.name -o tsv)
MODEL_USED=$(az cognitiveservices account deployment show -n "$AOAI" -g "$RG" --deployment-name "$DEPLOYMENT" --query properties.model.name -o tsv)

# You yourself may call the model too (for local tests with az login)
ME=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)
if [ -n "$ME" ]; then
  az role assignment create --assignee-object-id "$ME" --assignee-principal-type User \
    --role "Cognitive Services OpenAI User" --scope "$AOAI_ID" -o none 2>/dev/null || true
fi

# GitHub Actions via OIDC (no stored secret)
CLIENT_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)
if [ -z "$CLIENT_ID" ]; then
  CLIENT_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
fi
az ad sp show --id "$CLIENT_ID" -o none 2>/dev/null || az ad sp create --id "$CLIENT_ID" -o none
# GitHub signs the token with a subject. Repositories created, renamed or transferred after
# 15 July 2026 send the immutable form with the numeric owner and repository ids
# ("repo:owner@123/name@456:environment:eval"); older ones send "repo:owner/name:environment:eval"
# unless they opted in. Entra ID matches the subject literally, so both are registered. Without
# the right one the login fails with AADSTS700213.
GH_JSON=$(curl -fsSL "https://api.github.com/repos/${REPO}" 2>/dev/null || true)
OWNER_ID="${GITHUB_OWNER_ID:-$(printf '%s' "$GH_JSON" | jq -r '.owner.id // empty' 2>/dev/null || true)}"
REPO_ID="${GITHUB_REPO_ID:-$(printf '%s' "$GH_JSON" | jq -r '.id // empty' 2>/dev/null || true)}"
add_subject() {  # name, subject
  if ! az ad app federated-credential list --id "$CLIENT_ID" --query "[?subject=='$2'].name" -o tsv | grep -q .; then
    az ad app federated-credential create --id "$CLIENT_ID" --parameters "{
      \"name\": \"$1\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"$2\",
      \"audiences\": [\"api://AzureADTokenExchange\"]
    }" -o none
  fi
}
add_subject github-planwerk-eval "repo:${REPO}:environment:eval"
if [ -n "$OWNER_ID" ] && [ -n "$REPO_ID" ]; then
  add_subject github-planwerk-eval-immutable "repo:${REPO%%/*}@${OWNER_ID}/${REPO##*/}@${REPO_ID}:environment:eval"
else
  echo "WARNING: could not read the ids of ${REPO} from api.github.com; if the workflow fails with" >&2
  echo "AADSTS700213, run again with GITHUB_OWNER_ID=<id> GITHUB_REPO_ID=<id> (both are in the error text)." >&2
fi
SP_ID=$(az ad sp show --id "$CLIENT_ID" --query id -o tsv)
az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" --scope "$AOAI_ID" -o none 2>/dev/null || true

echo
echo "===== Planwerk Azure setup done. Copy everything between the lines and send it back. ====="
echo "AZURE_OPENAI_ENDPOINT=$ENDPOINT"
echo "AZURE_OPENAI_DEPLOYMENT=$DEPLOYMENT"
echo "AZURE_OPENAI_MODEL=$MODEL_USED"
echo "AZURE_OPENAI_SKU=$SKU_USED"
echo "AZURE_CLIENT_ID=$CLIENT_ID"
echo "AZURE_TENANT_ID=$TENANT"
echo "AZURE_SUBSCRIPTION_ID=$SUB"
echo "=========================================================================================="
