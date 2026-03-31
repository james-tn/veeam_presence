#!/usr/bin/env bash
# Deploy foundation infrastructure for Veeam Presence.
# Creates: resource group, Log Analytics, Key Vault, ACR, VNet (secure), ACA Environment, Azure OpenAI.
# Usage: DEPLOYMENT_MODE=secure bash deploy-foundation.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load .env if present
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a; source "$PROJECT_ROOT/.env"; set +a
fi

: "${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID}"
: "${AZURE_RESOURCE_GROUP:=presence-dev}"
: "${AZURE_LOCATION:=eastus2}"
: "${AZURE_TENANT_ID:?Set AZURE_TENANT_ID}"
: "${ENV_SUFFIX:=dev}"

DEPLOYMENT_MODE="${DEPLOYMENT_MODE:-secure}"
SECURE_MODE="false"
if [[ "$DEPLOYMENT_MODE" == "secure" ]]; then
    SECURE_MODE="true"
fi

NAME_PREFIX="${NAME_PREFIX:-presence}"
AOAI_NAME="${AZURE_OPENAI_ACCOUNT_NAME:-${NAME_PREFIX}openai}"
AOAI_MODEL="${AZURE_OPENAI_CHAT_DEPLOYMENT_NAME:-gpt-5.3-chat}"
AOAI_MODEL_VERSION="${AZURE_OPENAI_MODEL_VERSION:-2025-03-01}"
AOAI_SKU="${AZURE_OPENAI_DEPLOYMENT_SKU_NAME:-GlobalStandard}"
AOAI_CAPACITY="${AZURE_OPENAI_DEPLOYMENT_CAPACITY:-30}"
ACA_ENV_NAME="${ACA_ENV_NAME:-${NAME_PREFIX}-env-${ENV_SUFFIX}}"

echo "=== Veeam Presence Foundation Deploy ==="
echo "Subscription: $AZURE_SUBSCRIPTION_ID"
echo "Resource Group: $AZURE_RESOURCE_GROUP"
echo "Location: $AZURE_LOCATION"
echo "Mode: $DEPLOYMENT_MODE (secure=$SECURE_MODE)"
echo ""

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# 1. Resource Group
echo "--- Creating resource group..."
az group create \
    --name "$AZURE_RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" \
    --output none

# 2. Bicep deployment (Log Analytics, Key Vault, ACR, VNet + DNS zones if secure)
echo "--- Deploying foundation Bicep (secureDeployment=$SECURE_MODE)..."
DEPLOY_OUTPUT=$(az deployment group create \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --template-file "$SCRIPT_DIR/../bicep/foundation.bicep" \
    --parameters \
        location="$AZURE_LOCATION" \
        envSuffix="$ENV_SUFFIX" \
        namePrefix="$NAME_PREFIX" \
        secureDeployment="$SECURE_MODE" \
    --output json)

LOG_WORKSPACE_ID=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.logWorkspaceId.value')
LOG_WORKSPACE_NAME=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.logWorkspaceName.value')
KV_NAME=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.keyVaultName.value')
KV_ID=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.keyVaultId.value')
ACR_NAME=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.acrName.value')
ACR_LOGIN_SERVER=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.acrLoginServer.value')
ACA_SUBNET_ID=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.acaSubnetId.value')
PE_SUBNET_ID=$(echo "$DEPLOY_OUTPUT" | jq -r '.properties.outputs.privateEndpointSubnetId.value')

echo "  Log Analytics: $LOG_WORKSPACE_NAME"
echo "  Key Vault: $KV_NAME"
echo "  ACR: $ACR_NAME ($ACR_LOGIN_SERVER)"
if [[ "$SECURE_MODE" == "true" ]]; then
    echo "  VNet ACA Subnet: $ACA_SUBNET_ID"
    echo "  VNet PE Subnet: $PE_SUBNET_ID"
fi

# 3. ACA Environment
echo "--- Creating Container Apps Environment..."
if [[ "$SECURE_MODE" == "true" ]]; then
    az containerapp env create \
        --name "$ACA_ENV_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --location "$AZURE_LOCATION" \
        --infrastructure-subnet-resource-id "$ACA_SUBNET_ID" \
        --logs-workspace-id "$(az monitor log-analytics workspace show --resource-group "$AZURE_RESOURCE_GROUP" --workspace-name "$LOG_WORKSPACE_NAME" --query customerId -o tsv)" \
        --logs-workspace-key "$(az monitor log-analytics workspace get-shared-keys --resource-group "$AZURE_RESOURCE_GROUP" --workspace-name "$LOG_WORKSPACE_NAME" --query primarySharedKey -o tsv)" \
        --output none 2>/dev/null || echo "  (ACA env may already exist)"
else
    az containerapp env create \
        --name "$ACA_ENV_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --location "$AZURE_LOCATION" \
        --logs-workspace-id "$(az monitor log-analytics workspace show --resource-group "$AZURE_RESOURCE_GROUP" --workspace-name "$LOG_WORKSPACE_NAME" --query customerId -o tsv)" \
        --logs-workspace-key "$(az monitor log-analytics workspace get-shared-keys --resource-group "$AZURE_RESOURCE_GROUP" --workspace-name "$LOG_WORKSPACE_NAME" --query primarySharedKey -o tsv)" \
        --output none 2>/dev/null || echo "  (ACA env may already exist)"
fi
echo "  ACA Environment: $ACA_ENV_NAME"

# 4. Azure OpenAI
echo "--- Creating Azure OpenAI account: $AOAI_NAME..."

# Handle soft-delete: try to purge if exists
DELETED=$(az cognitiveservices account list-deleted --query "[?name=='$AOAI_NAME']" -o tsv 2>/dev/null || true)
if [[ -n "$DELETED" ]]; then
    echo "  Purging soft-deleted AOAI account..."
    az cognitiveservices account purge \
        --name "$AOAI_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --location "$AZURE_LOCATION" 2>/dev/null || true
    # Wait for purge
    for _ in {1..30}; do
        if [[ -z "$(az cognitiveservices account list-deleted --query "[?name=='$AOAI_NAME']" -o tsv 2>/dev/null || true)" ]]; then
            break
        fi
        sleep 5
    done
fi

az cognitiveservices account create \
    --name "$AOAI_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" \
    --kind OpenAI \
    --sku S0 \
    --custom-domain "$AOAI_NAME" \
    --yes \
    --output none 2>/dev/null || echo "  (AOAI account may already exist)"

AOAI_ENDPOINT=$(az cognitiveservices account show \
    --name "$AOAI_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --query "properties.endpoint" -o tsv)
AOAI_RESOURCE_ID=$(az cognitiveservices account show \
    --name "$AOAI_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --query "id" -o tsv)

echo "  AOAI: $AOAI_NAME ($AOAI_ENDPOINT)"

# 5. Model deployment
echo "--- Deploying model $AOAI_MODEL (SKU: $AOAI_SKU, capacity: $AOAI_CAPACITY)..."
az cognitiveservices account deployment create \
    --name "$AOAI_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --deployment-name "$AOAI_MODEL" \
    --model-name "$AOAI_MODEL" \
    --model-version "$AOAI_MODEL_VERSION" \
    --model-format OpenAI \
    --sku-capacity "$AOAI_CAPACITY" \
    --sku-name "$AOAI_SKU" \
    --output none 2>/dev/null || echo "  (model deployment may already exist)"

echo "  Model deployment: $AOAI_MODEL"

# 6. Private Endpoints (secure mode only)
if [[ "$SECURE_MODE" == "true" ]]; then
    echo "--- Setting up private endpoints..."

    # Disable public access on Azure OpenAI
    az resource update \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --name "$AOAI_NAME" \
        --resource-type "Microsoft.CognitiveServices/accounts" \
        --set properties.publicNetworkAccess=Disabled \
        --output none

    # Azure OpenAI private endpoint
    ensure_private_endpoint() {
        local pe_name="$1"
        local resource_id="$2"
        local group_id="$3"
        local dns_zone_name="$4"

        if ! az network private-endpoint show -g "$AZURE_RESOURCE_GROUP" -n "$pe_name" >/dev/null 2>&1; then
            echo "  Creating PE: $pe_name..."
            az network private-endpoint create \
                --resource-group "$AZURE_RESOURCE_GROUP" \
                --name "$pe_name" \
                --location "$AZURE_LOCATION" \
                --subnet "$PE_SUBNET_ID" \
                --private-connection-resource-id "$resource_id" \
                --group-id "$group_id" \
                --connection-name "${pe_name}-connection" \
                --output none
        else
            echo "  PE exists: $pe_name"
        fi

        # DNS zone group
        local dns_zone_id
        dns_zone_id="$(az network private-dns zone show \
            --resource-group "$AZURE_RESOURCE_GROUP" \
            --name "$dns_zone_name" \
            --query id -o tsv)"

        if ! az network private-endpoint dns-zone-group show \
            --resource-group "$AZURE_RESOURCE_GROUP" \
            --endpoint-name "$pe_name" \
            --name default >/dev/null 2>&1; then
            az network private-endpoint dns-zone-group create \
                --resource-group "$AZURE_RESOURCE_GROUP" \
                --endpoint-name "$pe_name" \
                --name default \
                --private-dns-zone "$dns_zone_id" \
                --zone-name "$dns_zone_name" \
                --output none
        fi
    }

    ensure_private_endpoint "${AOAI_NAME}-pe" "$AOAI_RESOURCE_ID" "account" "privatelink.openai.azure.com"
    ensure_private_endpoint "${KV_NAME}-pe" "$KV_ID" "vault" "privatelink.vaultcore.azure.net"

    echo "  Private endpoints configured."
fi

# 7. Write outputs
OUTPUTS_FILE="$PROJECT_ROOT/.env.outputs"
cat > "$OUTPUTS_FILE" << EOF
# Generated by deploy-foundation.sh — $(date -u +"%Y-%m-%dT%H:%M:%SZ")
DEPLOYMENT_MODE=$DEPLOYMENT_MODE
SECURE_DEPLOYMENT=$SECURE_MODE
AZURE_RESOURCE_GROUP=$AZURE_RESOURCE_GROUP
AZURE_LOCATION=$AZURE_LOCATION
LOG_WORKSPACE_NAME=$LOG_WORKSPACE_NAME
KEY_VAULT_NAME=$KV_NAME
ACR_NAME=$ACR_NAME
ACR_LOGIN_SERVER=$ACR_LOGIN_SERVER
ACA_ENV_NAME=$ACA_ENV_NAME
ACA_SUBNET_ID=$ACA_SUBNET_ID
PE_SUBNET_ID=$PE_SUBNET_ID
AZURE_OPENAI_ACCOUNT_NAME=$AOAI_NAME
AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT
AZURE_OPENAI_RESOURCE_ID=$AOAI_RESOURCE_ID
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=$AOAI_MODEL
EOF

# Also update .env with the new endpoint
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    # Update AZURE_OPENAI_ENDPOINT in .env
    if grep -q "^AZURE_OPENAI_ENDPOINT=" "$PROJECT_ROOT/.env"; then
        sed -i "s|^AZURE_OPENAI_ENDPOINT=.*|AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT|" "$PROJECT_ROOT/.env"
    fi
    if grep -q "^ACA_ENV_NAME=" "$PROJECT_ROOT/.env"; then
        sed -i "s|^ACA_ENV_NAME=.*|ACA_ENV_NAME=$ACA_ENV_NAME|" "$PROJECT_ROOT/.env"
    else
        echo "ACA_ENV_NAME=$ACA_ENV_NAME" >> "$PROJECT_ROOT/.env"
    fi
fi

echo ""
echo "=== Done! Outputs written to .env.outputs ==="
echo "  AOAI Endpoint: $AOAI_ENDPOINT"
echo "  ACA Env: $ACA_ENV_NAME"
if [[ "$SECURE_MODE" == "true" ]]; then
    echo "  VNet: presence-vnet (secure mode)"
    echo "  Private Endpoints: ${AOAI_NAME}-pe, ${KV_NAME}-pe"
fi
