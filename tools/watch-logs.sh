#!/usr/bin/env bash
set -e

POD="$1"
NAMESPACE="${2:-jhub}"
CONTAINER="${3:-notebook}"

if [ -z "$POD" ]; then
  echo "Usage: $0 <pod-name> [namespace] [container]" >&2
  exit 1
fi

echo "[watch-logs] Watching logs for pod=$POD ns=$NAMESPACE container=$CONTAINER"

while true; do
  # Try to attach; if it fails (e.g. PodInitializing), retry
  if kubectl logs -n "$NAMESPACE" "$POD" -c "$CONTAINER" -f; then
    # logs exited normally (container finished); break
    break
  else
    echo "[watch-logs] Pod or container not ready yet, retrying in 2s..."
    sleep 2
  fi
done
