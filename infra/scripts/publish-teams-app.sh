#!/usr/bin/env bash
set -euo pipefail

# Publish Veeam Presence Teams app to the org catalog via Microsoft Graph.
# Adapted from daily_planner/mvp/scripts/publish-m365-app-package-graph.sh.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
PACKAGE_PATH="${PACKAGE_PATH:-$ROOT_DIR/appPackage/appPackage.zip}"
MANIFEST_PATH="${MANIFEST_PATH:-$ROOT_DIR/appPackage/manifest.json}"
REQUIRES_REVIEW="${REQUIRES_REVIEW:-false}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' "$ENV_FILE")
  set +a
fi

log() { echo "[publish-teams-app] $*" >&2; }

if [[ ! -f "$PACKAGE_PATH" ]]; then
  echo "App package not found at $PACKAGE_PATH." >&2
  echo "Build it first: cd appPackage && zip -r appPackage.zip manifest.json icon-color.png icon-outline.png" >&2
  exit 1
fi

# Get Graph token with AppCatalog.ReadWrite.All scope.
# Azure CLI's first-party app lacks pre-authorization for AppCatalog scopes,
# so we use MSAL device code flow with the bot app registration instead.
get_graph_token() {
  python3 - <<'PY'
import msal, os, sys

tenant = os.environ.get("AZURE_TENANT_ID", "")
client_id = os.environ.get("BOT_APP_ID", "")
if not tenant or not client_id:
    print("AZURE_TENANT_ID and BOT_APP_ID are required", file=sys.stderr)
    sys.exit(1)

authority = f"https://login.microsoftonline.com/{tenant}"
scopes = ["https://graph.microsoft.com/AppCatalog.ReadWrite.All"]
app = msal.PublicClientApplication(client_id, authority=authority)

# Try silent first (cached token)
accounts = app.get_accounts()
if accounts:
    result = app.acquire_token_silent(scopes, account=accounts[0])
    if result and "access_token" in result:
        print(result["access_token"])
        sys.exit(0)

# Fall back to device code flow
flow = app.initiate_device_flow(scopes)
if "user_code" not in flow:
    print(f"Device flow failed: {flow.get('error_description', 'unknown')}", file=sys.stderr)
    sys.exit(1)

print(flow["message"], file=sys.stderr)
result = app.acquire_token_by_device_flow(flow)
if "access_token" not in result:
    print(f"Auth failed: {result.get('error_description', 'unknown')}", file=sys.stderr)
    sys.exit(1)
print(result["access_token"])
PY
}

GRAPH_TOKEN="$(get_graph_token)"
log "Resolved Microsoft Graph token with AppCatalog.ReadWrite.All"

# Resolve the manifest ID (externalId in the catalog)
resolve_app_package_id() {
  python3 -c "
import json, sys, pathlib
print(json.loads(pathlib.Path(sys.argv[1]).read_text('utf-8'))['id'])
" "$MANIFEST_PATH"
}

# Look up existing catalog entry by externalId
lookup_existing_app() {
  local external_id="$1"
  local lookup_file
  lookup_file="$(mktemp)"
  local lookup_status
  lookup_status="$(curl -sS -o "$lookup_file" -w "%{http_code}" \
    --get "https://graph.microsoft.com/v1.0/appCatalogs/teamsApps" \
    -H "Authorization: Bearer $GRAPH_TOKEN" \
    --data-urlencode "\$filter=externalId eq '$external_id'")"
  if [[ "$lookup_status" -lt 200 || "$lookup_status" -ge 300 ]]; then
    cat "$lookup_file" >&2
    echo "Catalog lookup failed (HTTP $lookup_status)" >&2
    return 1
  fi
  python3 -c "
import json, sys, pathlib
payload = json.loads(pathlib.Path(sys.argv[1]).read_text('utf-8'))
values = payload.get('value', [])
if not values:
    raise SystemExit(1)
entry = values[0]
print(entry.get('id', ''))
" "$lookup_file"
}

# Upload to catalog
response_file="$(mktemp)"
upload_url="https://graph.microsoft.com/v1.0/appCatalogs/teamsApps"
if [[ "$REQUIRES_REVIEW" == "true" ]]; then
  upload_url="${upload_url}?requiresReview=true"
fi

status_code="$(curl -sS -o "$response_file" -w "%{http_code}" \
  -X POST "$upload_url" \
  -H "Authorization: Bearer $GRAPH_TOKEN" \
  -H "Content-Type: application/zip" \
  --data-binary "@$PACKAGE_PATH")"
log "Initial catalog upload returned HTTP $status_code"

if [[ "$status_code" == "409" ]]; then
  log "App already exists in catalog, updating..."
  app_package_id="$(resolve_app_package_id)"
  existing_app_id="$(lookup_existing_app "$app_package_id")"

  if [[ -z "$existing_app_id" ]]; then
    cat "$response_file" >&2
    echo "Could not resolve existing catalog app ID" >&2
    exit 1
  fi

  update_url="https://graph.microsoft.com/v1.0/appCatalogs/teamsApps/${existing_app_id}/appDefinitions"
  if [[ "$REQUIRES_REVIEW" == "true" ]]; then
    update_url="${update_url}?requiresReview=true"
  fi

  update_file="$(mktemp)"
  update_status="$(curl -sS -o "$update_file" -w "%{http_code}" \
    -X POST "$update_url" \
    -H "Authorization: Bearer $GRAPH_TOKEN" \
    -H "Content-Type: application/zip" \
    --data-binary "@$PACKAGE_PATH")"

  if [[ "$update_status" -lt 200 || "$update_status" -ge 300 ]]; then
    if [[ "$update_status" == "409" ]] && grep -q "ManifestVersionAlreadyExists\|manifest version exists" "$update_file" 2>/dev/null; then
      log "Same version already published (no-op)"
      status_code="200"
    else
      cat "$update_file" >&2
      echo "Update failed (HTTP $update_status)" >&2
      exit 1
    fi
  else
    status_code="$update_status"
    log "Updated existing catalog entry (HTTP $status_code)"
  fi
  TEAMS_APP_ID="$existing_app_id"
else
  if [[ "$status_code" -lt 200 || "$status_code" -ge 300 ]]; then
    cat "$response_file" >&2
    echo "Upload failed (HTTP $status_code)" >&2
    exit 1
  fi
  TEAMS_APP_ID="$(python3 -c "
import json, sys, pathlib
body = json.loads(pathlib.Path(sys.argv[1]).read_text('utf-8'))
print(body.get('id', ''))
" "$response_file")"
fi

log "Published to catalog. TEAMS_APP_ID=$TEAMS_APP_ID"
echo "TEAMS_APP_ID=$TEAMS_APP_ID"
