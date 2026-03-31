#!/usr/bin/env bash
# Create Azure Bot Service resource and enable Teams channel.
# Follows the same pattern as daily_planner/mvp/infra/scripts/create-azure-bot-resource.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a; source <(sed 's/\r$//' "$PROJECT_ROOT/.env"); set +a
fi
if [[ -f "$PROJECT_ROOT/.env.app-registrations" ]]; then
    set -a; source <(sed 's/\r$//' "$PROJECT_ROOT/.env.app-registrations"); set +a
fi
if [[ -f "$PROJECT_ROOT/.env.outputs" ]]; then
    set -a; source <(sed 's/\r$//' "$PROJECT_ROOT/.env.outputs"); set +a
fi

required_vars=(
    AZURE_SUBSCRIPTION_ID
    AZURE_RESOURCE_GROUP
    BOT_APP_ID
    AZURE_TENANT_ID
)

for var_name in "${required_vars[@]}"; do
    if [[ -z "${!var_name:-}" ]]; then
        echo "$var_name is required." >&2
        exit 1
    fi
done

: "${BOT_RESOURCE_NAME:=presencebot$(echo "$AZURE_SUBSCRIPTION_ID" | cut -c1-5)}"
: "${ENV_SUFFIX:=dev}"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# Auto-resolve wrapper base URL if not set
if [[ -z "${WRAPPER_BASE_URL:-}" ]]; then
    WRAPPER_APP="presence-wrapper-${ENV_SUFFIX}"
    wrapper_fqdn="$(
        az resource show \
            --resource-group "$AZURE_RESOURCE_GROUP" \
            --name "$WRAPPER_APP" \
            --resource-type Microsoft.App/containerApps \
            --query properties.configuration.ingress.fqdn \
            -o tsv 2>/dev/null || true
    )"
    if [[ -n "$wrapper_fqdn" ]]; then
        WRAPPER_BASE_URL="https://$wrapper_fqdn"
    fi
fi

if [[ -z "${WRAPPER_BASE_URL:-}" ]]; then
    echo "WRAPPER_BASE_URL is required." >&2
    exit 1
fi

echo "=== Creating Azure Bot Resource ==="
echo "Bot: $BOT_RESOURCE_NAME"
echo "App ID: $BOT_APP_ID"
echo "Endpoint: $WRAPPER_BASE_URL/api/messages"
echo ""

# Create bot if it doesn't exist
if ! az resource show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$BOT_RESOURCE_NAME" \
    --resource-type Microsoft.BotService/botServices \
    >/dev/null 2>&1; then
    az bot create \
        --resource-group "$AZURE_RESOURCE_GROUP" \
        --name "$BOT_RESOURCE_NAME" \
        --appid "$BOT_APP_ID" \
        --app-type SingleTenant \
        --tenant-id "$AZURE_TENANT_ID" \
        --endpoint "$WRAPPER_BASE_URL/api/messages" \
        --display-name "Veeam Presence Bot" \
        --description "Bot service for Veeam Presence wrapper" \
        --sku F0 \
        >/dev/null
fi

# Update endpoint (idempotent)
az bot update \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$BOT_RESOURCE_NAME" \
    --endpoint "$WRAPPER_BASE_URL/api/messages" \
    >/dev/null

# Enable Teams channel
az bot msteams create \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$BOT_RESOURCE_NAME" \
    >/dev/null 2>&1 || true

cat <<EOF
Azure Bot resource created or updated.
BOT_RESOURCE_NAME=$BOT_RESOURCE_NAME
BOT_APP_ID=$BOT_APP_ID
BOT_ENDPOINT=$WRAPPER_BASE_URL/api/messages
EOF
