#!/bin/bash
# apply-config.sh
# Pulls the latest config template from GitHub, extracts secrets from the
# existing local config.yaml, and writes a new config.yaml ready for helm.
#
# Usage: sudo bash /opt/Lobot/tools/apply-config.sh
#
# Run on:
#   prod:  lobot.cs.queensu.ca    -> config.yaml.bk + config-prod.yaml.bk
#   dev:   lobot-dev.cs.queensu.ca -> config.yaml.bk + config-dev.yaml.bk

set -euo pipefail

LOCAL_CONFIG="/opt/Lobot/config.yaml"
OUTPUT="/opt/Lobot/config.yaml"
OUTPUT_ENV="/opt/Lobot/config-env.yaml"
BACKUP_DIR="/opt/Lobot/previousconfig"
TMPFILE=$(mktemp /tmp/config_template.XXXXXX.yaml)

# ── Detect cluster ────────────────────────────────────────────────────────────
FQDN=$(hostname)
if [[ "$FQDN" == *"lobot-dev"* ]]; then
    CLUSTER="dev"
    CONFIG_BK_ENV="config-dev.yaml.bk"
else
    CLUSTER="prod"
    CONFIG_BK_ENV="config-prod.yaml.bk"
fi
CONFIG_BK="config.yaml.bk"
REPO_RAW="https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/newcluster"

echo "[apply-config] Cluster:  $CLUSTER"
echo "[apply-config] Base template:     $CONFIG_BK"
echo "[apply-config] Env override:      $CONFIG_BK_ENV"

# ── Check local config exists ─────────────────────────────────────────────────
if [[ ! -f "$LOCAL_CONFIG" ]]; then
    echo "[apply-config] ERROR: $LOCAL_CONFIG not found — cannot extract secrets." >&2
    exit 1
fi

# ── Backup existing config ────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/config_${CLUSTER}_${TIMESTAMP}.yaml"
cp "$LOCAL_CONFIG" "$BACKUP_FILE"
echo "[apply-config] Backed up existing config to $BACKUP_FILE"

# ── Extract secrets from existing config.yaml ────────────────────────────────
extract() {
    # Usage: extract <label> <pattern>
    # Pattern should capture the value in group 1
    python3 -c "
import re, sys
content = open('$LOCAL_CONFIG').read()
m = re.search(r'$2', content)
if not m:
    sys.stderr.write('Could not extract: $1\n')
    sys.exit(1)
print(m.group(1))
"
}

echo "[apply-config] Extracting secrets from $LOCAL_CONFIG..."
CLIENT_ID=$(extract 'client_id'       'client_id:\s*(\S+)')
CLIENT_SECRET=$(extract 'client_secret' 'client_secret:\s*(\S+)')
API_TOKEN=$(extract 'api_token'         'api_token["\s:]+([a-f0-9]{10,})')
PROXY_TOKEN=$(extract 'secretToken'     'secretToken:\s*"([^"]*)"')

echo "[apply-config] Secrets extracted."

# ── Pull base template from GitHub ───────────────────────────────────────────
echo "[apply-config] Fetching $REPO_RAW/$CONFIG_BK ..."
curl -fsSL "$REPO_RAW/$CONFIG_BK" -o "$TMPFILE"
echo "[apply-config] Base template downloaded."

# ── Substitute placeholders ───────────────────────────────────────────────────
echo "[apply-config] Applying secrets..."
python3 - <<EOF
import re

with open('$TMPFILE') as f:
    content = f.read()

content = re.sub(r'(client_id:\s*)xxx', r'\g<1>$CLIENT_ID', content)
content = re.sub(r'(client_secret:\s*)xxx', r'\g<1>$CLIENT_SECRET', content)
content = re.sub(r'(api_token["\s:]+)xxx', r'\g<1>$API_TOKEN', content)
content = re.sub(r'(secretToken:\s*")[^"]*(")', r'\g<1>$PROXY_TOKEN\g<2>', content)

with open('$OUTPUT', 'w') as f:
    f.write(content)
EOF

# ── Pull env override from GitHub ─────────────────────────────────────────────
echo "[apply-config] Fetching $REPO_RAW/$CONFIG_BK_ENV ..."
curl -fsSL "$REPO_RAW/$CONFIG_BK_ENV" -o "$OUTPUT_ENV"
echo "[apply-config] Env override written to $OUTPUT_ENV"

rm -f "$TMPFILE"
echo "[apply-config] Done. Config written to $OUTPUT"
echo ""
echo "Review, then apply with:"
echo "  cd /opt/Lobot && RELEASE=jhub ; NAMESPACE=jhub ; helm upgrade --cleanup-on-fail \$RELEASE jupyterhub/jupyterhub --namespace \$NAMESPACE --version=4.0.0-beta.2 --values config.yaml --values config-env.yaml --timeout=60m"
