#!/usr/bin/env bash
set -euo pipefail

# Install Veeam Presence Teams app for the signed-in user via Microsoft Graph.
# Adapted from daily_planner/mvp/scripts/install-m365-app-for-self-graph.sh.
# Run publish-teams-app.sh first to upload to the catalog.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
MANIFEST_PATH="${MANIFEST_PATH:-$ROOT_DIR/appPackage/manifest.json}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' "$ENV_FILE")
  set +a
fi

log() { echo "[install-teams-app] $*" >&2; }

# Resolve manifest ID
if [[ -z "${M365_APP_PACKAGE_ID:-}" ]]; then
  M365_APP_PACKAGE_ID="$(python3 -c "
import json, sys, pathlib
print(json.loads(pathlib.Path(sys.argv[1]).read_text('utf-8'))['id'])
" "$MANIFEST_PATH")"
fi

# Get Graph token
GRAPH_TOKEN="$(az account get-access-token --resource-type ms-graph --query accessToken -o tsv)"
log "Resolved Microsoft Graph token"

# Look up catalog entry
response_file="$(mktemp)"
status_code="$(curl -sS -o "$response_file" -w "%{http_code}" \
  --get "https://graph.microsoft.com/v1.0/appCatalogs/teamsApps" \
  -H "Authorization: Bearer $GRAPH_TOKEN" \
  --data-urlencode "\$filter=externalId eq '$M365_APP_PACKAGE_ID'")"

if [[ "$status_code" -lt 200 || "$status_code" -ge 300 ]]; then
  cat "$response_file" >&2
  echo "Catalog lookup failed (HTTP $status_code)" >&2
  exit 1
fi

teams_app_id="$(python3 -c "
import json, sys, pathlib
body = json.loads(pathlib.Path(sys.argv[1]).read_text('utf-8'))
values = body.get('value', [])
if values:
    print(values[0].get('id', ''))
" "$response_file")"

if [[ -z "$teams_app_id" ]]; then
  echo "No catalog entry found for externalId=$M365_APP_PACKAGE_ID." >&2
  echo "Run publish-teams-app.sh first." >&2
  exit 2
fi
log "Found catalog app: $teams_app_id"

# Resolve current user
me_file="$(mktemp)"
me_status="$(curl -sS -o "$me_file" -w "%{http_code}" \
  "https://graph.microsoft.com/v1.0/me" \
  -H "Authorization: Bearer $GRAPH_TOKEN")"

if [[ "$me_status" -lt 200 || "$me_status" -ge 300 ]]; then
  cat "$me_file" >&2
  echo "Failed to resolve signed-in user (HTTP $me_status)" >&2
  exit 1
fi

user_id="$(python3 -c "
import json, sys, pathlib
print(json.loads(pathlib.Path(sys.argv[1]).read_text('utf-8'))['id'])
" "$me_file")"
user_name="$(python3 -c "
import json, sys, pathlib
print(json.loads(pathlib.Path(sys.argv[1]).read_text('utf-8')).get('userPrincipalName', ''))
" "$me_file")"
log "Installing for user: $user_name ($user_id)"

# Install for user
install_body='{"teamsApp@odata.bind":"https://graph.microsoft.com/v1.0/appCatalogs/teamsApps/'"$teams_app_id"'"}'
install_response="$(mktemp)"
install_status="$(curl -sS -o "$install_response" -w "%{http_code}" \
  -X POST "https://graph.microsoft.com/v1.0/users/$user_id/teamwork/installedApps" \
  -H "Authorization: Bearer $GRAPH_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$install_body")"

if [[ "$install_status" == "409" ]]; then
  log "App already installed for user (no-op)"
  exit 0
fi

if [[ "$install_status" -lt 200 || "$install_status" -ge 300 ]]; then
  cat "$install_response" >&2
  echo "Install failed (HTTP $install_status)" >&2
  exit 1
fi

log "Installed Teams app for $user_name"
