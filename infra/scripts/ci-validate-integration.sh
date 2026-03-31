#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-}"

if [[ -z "$ENV_FILE" ]]; then
  echo "ENV_FILE is required." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ENV_FILE does not exist: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source <(sed 's/\r$//' "$ENV_FILE")
set +a

if [[ -z "${WRAPPER_BASE_URL:-}" ]]; then
  echo "WRAPPER_BASE_URL is required for validation." >&2
  exit 1
fi

echo "Checking wrapper health endpoint..."
curl -fsS "${WRAPPER_BASE_URL%/}/health"
echo
echo "Wrapper health check passed."

# The wrapper verifies agent connectivity on startup (lifespan health check).
# If wrapper is healthy, agent is reachable.
echo "Agent connectivity verified via wrapper startup health check."
