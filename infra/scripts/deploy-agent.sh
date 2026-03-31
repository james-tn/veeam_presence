#!/usr/bin/env bash
# Build and deploy the Presence agent service to Azure Container Apps.
# Agent always uses internal ingress (only reachable from within VNet/ACA env).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a; source "$PROJECT_ROOT/.env"; set +a
fi
if [[ -f "$PROJECT_ROOT/.env.outputs" ]]; then
    set -a; source "$PROJECT_ROOT/.env.outputs"; set +a
fi

: "${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID}"
: "${AZURE_RESOURCE_GROUP:=presence-dev}"
: "${ACR_NAME:?Set ACR_NAME (from .env.outputs)}"
: "${ACA_ENV_NAME:?Set ACA_ENV_NAME (from .env.outputs)}"
: "${AZURE_OPENAI_ENDPOINT:?Set AZURE_OPENAI_ENDPOINT}"
: "${AZURE_OPENAI_ACCOUNT_NAME:?Set AZURE_OPENAI_ACCOUNT_NAME (from .env.outputs)}"
: "${ENV_SUFFIX:=dev}"

IMAGE_NAME="presence-agent"
IMAGE_TAG="${IMAGE_TAG:-latest}"
APP_NAME="${AGENT_ACA_APP_NAME:-presence-agent-${ENV_SUFFIX}}"

echo "=== Deploying Presence Agent ==="
echo "ACR: $ACR_NAME"
echo "ACA App: $APP_NAME"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)

# If AGENT_IMAGE is set, skip ACR build and use the pre-built image.
if [[ -n "${AGENT_IMAGE:-}" ]]; then
    FULL_IMAGE="$AGENT_IMAGE"
    echo "Using pre-built image: $FULL_IMAGE"
else
    FULL_IMAGE="${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}"
    echo "Building image in ACR: $FULL_IMAGE"
    az acr build \
        --registry "$ACR_NAME" \
        --image "${IMAGE_NAME}:${IMAGE_TAG}" \
        --file "$PROJECT_ROOT/agent/Dockerfile" \
        "$PROJECT_ROOT"
fi

# Deploy to ACA
echo "--- Deploying to Container Apps..."

COMMON_ENV_VARS=(
    "AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT"
    "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=${AZURE_OPENAI_CHAT_DEPLOYMENT_NAME:-gpt-5.3-chat}"
    "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION:-2024-12-01-preview}"
)

# Check if app already exists
if az containerapp show --name "$APP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "  Updating existing app..."
    az containerapp update \
        --name "$APP_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --image "$FULL_IMAGE" \
        --set-env-vars "${COMMON_ENV_VARS[@]}" \
        --output none
else
    echo "  Creating new app..."
    az containerapp create \
        --name "$APP_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --environment "$ACA_ENV_NAME" \
        --image "$FULL_IMAGE" \
        --target-port 8000 \
        --ingress internal \
        --min-replicas 1 \
        --max-replicas 3 \
        --cpu 1.0 --memory 2.0Gi \
        --env-vars "${COMMON_ENV_VARS[@]}" \
        --registry-server "$ACR_LOGIN_SERVER" \
        --registry-identity system \
        --output none
fi

# Assign system managed identity
echo "--- Assigning system managed identity..."
az containerapp identity assign \
    --name "$APP_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --system-assigned \
    --output none 2>/dev/null || true

# Get the managed identity principal ID
PRINCIPAL_ID=$(az containerapp show \
    --name "$APP_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --query identity.principalId -o tsv 2>/dev/null || true)

# Assign Cognitive Services OpenAI User role
if [[ -n "$PRINCIPAL_ID" ]]; then
    OPENAI_RESOURCE_ID=$(az cognitiveservices account show \
        --name "$AZURE_OPENAI_ACCOUNT_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --query id -o tsv)

    echo "--- Assigning Cognitive Services OpenAI User role..."
    az role assignment create \
        --assignee-object-id "$PRINCIPAL_ID" \
        --assignee-principal-type ServicePrincipal \
        --role "Cognitive Services OpenAI User" \
        --scope "$OPENAI_RESOURCE_ID" \
        --output none 2>/dev/null || echo "  (role may already be assigned)"
fi

FQDN=$(az containerapp show --name "$APP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "N/A")
echo ""
echo "=== Done! Agent deployed ==="
echo "  Internal URL: https://$FQDN"
echo "  Managed Identity Principal: ${PRINCIPAL_ID:-N/A}"
