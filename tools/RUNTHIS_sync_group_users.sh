#!/usr/bin/env bash
set -e

# Usage:
#   ./sync_group_users.sh https://lobot.cs.queensu.ca/hub/api
# or:
#   API_URL=https://lobot.cs.queensu.ca/hub/api ./sync_group_users.sh

# 1. Get API_URL from $1 or $API_URL env, with an optional default
API_URL_ARG="$1"
API_URL="${API_URL_ARG:-${API_URL:-https://lobot.cs.queensu.ca/hub/api}}"

if [ -z "$API_URL" ]; then
  echo "Usage: $0 <api-url> [extra ensure_group_users.py args]" >&2
  echo "Example: $0 https://lobot.cs.queensu.ca/hub/api" >&2
  exit 1
fi

# Drop the first arg if it was used for API_URL
if [ -n "$API_URL_ARG" ]; then
  shift
fi

# 2. Fetch token from Kubernetes Secret
TOKEN=$(kubectl get secret group-manager-token -n jhub \
  -o jsonpath='{.data.JUPYTERHUB_API_TOKEN}' | base64 -d)

# 3. Call ensure_group_users.py with api-url and token
python3 ensure_group_users.py \
  --api-url "$API_URL" \
  --token "$TOKEN" \
  "$@"
