#!/usr/bin/env bash
# Build and deploy the M365 wrapper service to Azure Container Apps.
# Wrapper always uses external ingress (Teams Bot Framework must reach /api/messages).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a; source "$PROJECT_ROOT/.env"; set +a
fi
if [[ -f "$PROJECT_ROOT/.env.outputs" ]]; then
    set -a; source "$PROJECT_ROOT/.env.outputs"; set +a
fi
if [[ -f "$PROJECT_ROOT/.env.app-registrations" ]]; then
    set -a; source "$PROJECT_ROOT/.env.app-registrations"; set +a
fi

: "${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID}"
: "${AZURE_RESOURCE_GROUP:=presence-dev}"
: "${ACR_NAME:?Set ACR_NAME}"
: "${ACA_ENV_NAME:?Set ACA_ENV_NAME}"
: "${BOT_APP_ID:?Set BOT_APP_ID}"
: "${BOT_APP_PASSWORD:?Set BOT_APP_PASSWORD}"
: "${AZURE_TENANT_ID:?Set AZURE_TENANT_ID}"
: "${ENV_SUFFIX:=dev}"

IMAGE_NAME="presence-wrapper"
IMAGE_TAG="${IMAGE_TAG:-latest}"
APP_NAME="${WRAPPER_ACA_APP_NAME:-presence-wrapper-${ENV_SUFFIX}}"

# Resolve agent internal URL from the ACA environment
AGENT_APP_NAME="${AGENT_ACA_APP_NAME:-presence-agent-${ENV_SUFFIX}}"
AGENT_FQDN=$(az containerapp show --name "$AGENT_APP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "localhost:8000")
PRESENCE_SERVICE_BASE_URL="https://${AGENT_FQDN}"

echo "=== Deploying M365 Wrapper ==="
echo "ACR: $ACR_NAME"
echo "Image: $IMAGE_NAME:$IMAGE_TAG"
echo "Agent URL: $PRESENCE_SERVICE_BASE_URL"
echo ""

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)

# If WRAPPER_IMAGE is set, skip ACR build and use the pre-built image.
if [[ -n "${WRAPPER_IMAGE:-}" ]]; then
    FULL_IMAGE="$WRAPPER_IMAGE"
    echo "Using pre-built image: $FULL_IMAGE"
else
    FULL_IMAGE="${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}"
    echo "Building image in ACR: $FULL_IMAGE"
    az acr build \
        --registry "$ACR_NAME" \
        --image "${IMAGE_NAME}:${IMAGE_TAG}" \
        --file "$PROJECT_ROOT/m365_wrapper/Dockerfile" \
        "$PROJECT_ROOT"
fi

# Deploy to ACA
echo "--- Deploying to Container Apps..."

COMMON_ENV_VARS=(
    "BOT_APP_ID=$BOT_APP_ID"
    "AZURE_TENANT_ID=$AZURE_TENANT_ID"
    "PRESENCE_SERVICE_BASE_URL=$PRESENCE_SERVICE_BASE_URL"
)

# Check if app already exists
if az containerapp show --name "$APP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "  Updating existing app..."
    # Update secret first
    az containerapp secret set \
        --name "$APP_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --secrets "bot-app-password=$BOT_APP_PASSWORD" \
        --output none
    az containerapp update \
        --name "$APP_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --image "$FULL_IMAGE" \
        --set-env-vars "${COMMON_ENV_VARS[@]}" "BOT_APP_PASSWORD=secretref:bot-app-password" \
        --output none
else
    echo "  Creating new app..."
    az containerapp create \
        --name "$APP_NAME" \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --environment "$ACA_ENV_NAME" \
        --image "$FULL_IMAGE" \
        --target-port 3978 \
        --ingress external \
        --min-replicas 1 \
        --max-replicas 3 \
        --cpu 0.5 --memory 1.0Gi \
        --secrets "bot-app-password=$BOT_APP_PASSWORD" \
        --env-vars "${COMMON_ENV_VARS[@]}" "BOT_APP_PASSWORD=secretref:bot-app-password" \
        --registry-server "$ACR_LOGIN_SERVER" \
        --registry-identity system \
        --output none
fi

FQDN=$(az containerapp show --name "$APP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "N/A")

# Write wrapper URL to env outputs
if [[ "$FQDN" != "N/A" ]]; then
    echo "WRAPPER_BASE_URL=https://$FQDN" >> "$PROJECT_ROOT/.env.outputs"
    echo "WRAPPER_ENDPOINT=https://$FQDN/api/messages" >> "$PROJECT_ROOT/.env.outputs"
fi

echo ""
echo "=== Done! Wrapper deployed ==="
echo "  External URL: https://$FQDN"
echo "  Teams messaging endpoint: https://$FQDN/api/messages"
