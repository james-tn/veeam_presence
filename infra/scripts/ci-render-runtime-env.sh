#!/usr/bin/env bash
set -euo pipefail

OUTPUT_ENV_FILE="${OUTPUT_ENV_FILE:-}"
RELEASE_METADATA_PATH="${RELEASE_METADATA_PATH:-}"

if [[ -z "$OUTPUT_ENV_FILE" ]]; then
  echo "OUTPUT_ENV_FILE is required." >&2
  exit 1
fi

if [[ -z "$RELEASE_METADATA_PATH" ]]; then
  echo "RELEASE_METADATA_PATH is required." >&2
  exit 1
fi

python - <<'PY' "$RELEASE_METADATA_PATH" "$OUTPUT_ENV_FILE"
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

metadata_path = Path(sys.argv[1])
output_env_file = Path(sys.argv[2])

if not metadata_path.exists():
    raise SystemExit(f"Release metadata file not found: {metadata_path}")

metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
for required_key in ("agent_image", "wrapper_image", "git_sha"):
    if not str(metadata.get(required_key, "")).strip():
        raise SystemExit(f"Release metadata is missing '{required_key}'.")

# All keys we allow from the environment
allowed_keys = {
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_RESOURCE_GROUP",
    "AZURE_LOCATION",
    "AZURE_TENANT_ID",
    "ACR_NAME",
    "ACA_ENV_NAME",
    "AGENT_ACA_APP_NAME",
    "WRAPPER_ACA_APP_NAME",
    "AZURE_OPENAI_ACCOUNT_NAME",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",
    "AZURE_OPENAI_API_VERSION",
    "BOT_APP_ID",
    "BOT_APP_PASSWORD",
    "ENV_SUFFIX",
    "KEYVAULT_NAME",
    "KEYVAULT_BOT_APP_PASSWORD_NAME",
    "WRAPPER_BASE_URL",
}

values = OrderedDict()

# Populate from environment
for key in sorted(allowed_keys):
    value = os.environ.get(key, "").strip()
    if value:
        values[key] = value

# Override with release metadata
values["AGENT_IMAGE"] = str(metadata["agent_image"]).strip()
values["WRAPPER_IMAGE"] = str(metadata["wrapper_image"]).strip()
values["DEPLOYMENT_MODE"] = str(metadata.get("deployment_mode", "secure")).strip()

output_env_file.parent.mkdir(parents=True, exist_ok=True)
lines = [f"{k}={v}" for k, v in values.items()]
output_env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
