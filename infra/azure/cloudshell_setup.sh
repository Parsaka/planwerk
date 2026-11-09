#!/usr/bin/env bash
# Planwerk: one-time Azure setup without Terraform, for Azure Cloud Shell (Bash).
# Open https://portal.azure.com, click the Cloud Shell icon (>_) at the top, choose Bash, then run:
#   curl -fsSL https://raw.githubusercontent.com/Parsaka/planwerk/main/infra/azure/cloudshell_setup.sh | bash
#
# Creates, in an allowed EU region of Azure for Students (swedencentral):
#   - resource group rg-planwerk
#   - Azure OpenAI account with Entra ID sign-in only (no API keys) and one small chat model
#     (gpt-5-mini if available) capped at 30k tokens per minute
#   - an app registration that GitHub Actions of Parsaka/planwerk (environment "eval") can use via
#     OIDC, with the role "Cognitive Services OpenAI User" on that account only
# Prints seven values at the end. None of them is a secret. Safe to run twice.
set -euo pipefail

LOC="${LOC:-swedencentral}"
RG="${RG:-rg-planwerk}"
REPO="${REPO:-Parsaka/planwerk}"
# Models are tried in this order. gpt-4o-mini and gpt-4.1-mini are "Deprecated" in Azure since 2026:
# a subscription that has never deployed them cannot deploy them any more, so they come last and
# only work on older subscriptions. Override with MODELS="name:version ..." if needed.
MODELS="${MODELS:-gpt-5-mini:2025-08-07 gpt-5-nano:2025-08-07 gpt-4.1-mini:2025-04-14 gpt-4o-mini:2024-07-18}"
DEPLOYMENT="${DEPLOYMENT:-planwerk-chat}"
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
SUBJECT="repo:${REPO}:environment:eval"
if ! az ad app federated-credential list --id "$CLIENT_ID" --query "[?subject=='$SUBJECT'].name" -o tsv | grep -q .; then
  az ad app federated-credential create --id "$CLIENT_ID" --parameters "{
    \"name\": \"github-planwerk-eval\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"$SUBJECT\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
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
