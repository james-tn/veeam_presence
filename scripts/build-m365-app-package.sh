#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
APP_PACKAGE_DIR="$ROOT_DIR/appPackage"
BUILD_DIR="$APP_PACKAGE_DIR/build"
TEMPLATE_PATH="$APP_PACKAGE_DIR/manifest.template.json"
MANIFEST_PATH="$BUILD_DIR/manifest.json"
ZIP_PATH="$BUILD_DIR/veeam-presence-m365.zip"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' "$ENV_FILE")
  set +a
fi

mkdir -p "$BUILD_DIR"

WRAPPER_BASE_URL="${WRAPPER_BASE_URL:-}"
BOT_APP_ID="${BOT_APP_ID:-}"
if [[ -z "$BOT_APP_ID" ]]; then
  echo "BOT_APP_ID is required in $ENV_FILE or the environment." >&2
  exit 1
fi

M365_APP_PACKAGE_ID="${M365_APP_PACKAGE_ID:-2e28219d-9a4d-4540-b5e2-d0318aacf19e}"
APP_VERSION="${APP_VERSION:-1.0.0}"
M365_APP_SHORT_NAME="${M365_APP_SHORT_NAME:-Veeam Presence}"
M365_APP_FULL_NAME="${M365_APP_FULL_NAME:-Veeam Presence — Office Attendance Intelligence}"
M365_APP_SHORT_DESCRIPTION="${M365_APP_SHORT_DESCRIPTION:-Office attendance intelligence for leadership}"
M365_APP_FULL_DESCRIPTION="${M365_APP_FULL_DESCRIPTION:-I track daily attendance across every Veeam office worldwide. Ask me about headcounts, leaderboards, trends, cross-office travel, team coordination, manager impact, and individual patterns. 18 offices, ~3,000 people, refreshed daily.}"
M365_APP_ACCENT_COLOR="${M365_APP_ACCENT_COLOR:-#005f4b}"
M365_DEVELOPER_NAME="${M365_DEVELOPER_NAME:-Veeam Revenue Intelligence}"
M365_DEVELOPER_WEBSITE_URL="${M365_DEVELOPER_WEBSITE_URL:-https://www.veeam.com}"
M365_PRIVACY_URL="${M365_PRIVACY_URL:-https://www.veeam.com/privacy-policy.html}"
M365_TERMS_URL="${M365_TERMS_URL:-https://www.veeam.com/eula.html}"

if [[ -n "$WRAPPER_BASE_URL" ]]; then
  WRAPPER_VALID_DOMAIN="$(python - <<'PY' "$WRAPPER_BASE_URL"
import sys
from urllib.parse import urlparse
print(urlparse(sys.argv[1]).netloc)
PY
)"
else
  WRAPPER_VALID_DOMAIN="presence-wrapper-dev.orangepond-a43b118f.eastus2.azurecontainerapps.io"
fi

# Render manifest from template
python - <<'PY' "$TEMPLATE_PATH" "$MANIFEST_PATH" \
  "$APP_VERSION" \
  "$M365_APP_PACKAGE_ID" \
  "$M365_DEVELOPER_NAME" \
  "$M365_DEVELOPER_WEBSITE_URL" \
  "$M365_PRIVACY_URL" \
  "$M365_TERMS_URL" \
  "$M365_APP_SHORT_NAME" \
  "$M365_APP_FULL_NAME" \
  "$M365_APP_SHORT_DESCRIPTION" \
  "$M365_APP_FULL_DESCRIPTION" \
  "$M365_APP_ACCENT_COLOR" \
  "$BOT_APP_ID" \
  "$WRAPPER_VALID_DOMAIN"
import json
import re
import sys
from pathlib import Path

template_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
keys = [
    "APP_VERSION",
    "M365_APP_PACKAGE_ID",
    "M365_DEVELOPER_NAME",
    "M365_DEVELOPER_WEBSITE_URL",
    "M365_PRIVACY_URL",
    "M365_TERMS_URL",
    "M365_APP_SHORT_NAME",
    "M365_APP_FULL_NAME",
    "M365_APP_SHORT_DESCRIPTION",
    "M365_APP_FULL_DESCRIPTION",
    "M365_APP_ACCENT_COLOR",
    "BOT_APP_ID",
    "WRAPPER_VALID_DOMAIN",
]
values = dict(zip(keys, sys.argv[3:], strict=True))
template = template_path.read_text(encoding="utf-8")

pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")

def replace(match):
    key = match.group(1)
    return values.get(key, "")

rendered = pattern.sub(replace, template)
data = json.loads(rendered)
manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY

# Package manifest + icons into zip
python - <<'PY' "$ZIP_PATH" "$MANIFEST_PATH" "$APP_PACKAGE_DIR/icon-color.png" "$APP_PACKAGE_DIR/icon-outline.png"
import sys
import zipfile
from pathlib import Path

zip_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
color_icon_path = Path(sys.argv[3])
outline_icon_path = Path(sys.argv[4])

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(manifest_path, arcname="manifest.json")
    archive.write(color_icon_path, arcname="icon-color.png")
    archive.write(outline_icon_path, arcname="icon-outline.png")
PY

echo "Manifest written to: $MANIFEST_PATH"
echo "App package written to: $ZIP_PATH"
