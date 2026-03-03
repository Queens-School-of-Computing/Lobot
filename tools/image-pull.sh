#!/bin/bash

NAMESPACE="kube-system"
POLL_INTERVAL=10        # seconds between checks

# ==========================================
# Parameter handling
# ==========================================
usage() {
  echo "Usage: $0 -i <image:tag> [-b <batch_size>] [-t <timeout_seconds>] [-e <exclude_nodes>] [-n <node>]"
  echo ""
  echo "  -i  Full image name and tag to pull (required)"
  echo "  -b  Number of nodes to pull simultaneously (default: 3)"
  echo "  -t  Timeout in seconds per node pull (default: 1200 = 20 minutes)"
  echo "  -e  Comma-separated list of nodes to exclude"
  echo "  -n  Target a single specific node only"
  echo ""
  echo "Examples:"
  echo "  $0 -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 -b 3 -t 1200 -e lobot-dev.cs.queensu.ca"
  echo "  $0 -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 -n newcluster-gpunode3"
  exit 1
}

BATCH_SIZE=3
TIMEOUT=1200
EXCLUDE_NODES=""
TARGET_NODE=""

while getopts ":i:b:t:e:n:" opt; do
  case $opt in
    i) PULL_IMAGE="$OPTARG" ;;
    b) BATCH_SIZE="$OPTARG" ;;
    t) TIMEOUT="$OPTARG" ;;
    e) EXCLUDE_NODES="$OPTARG" ;;
    n) TARGET_NODE="$OPTARG" ;;
    *) usage ;;
  esac
done

if [ -z "$PULL_IMAGE" ]; then
  echo "❌ ERROR: Image name is required!"
  usage
fi

if [ -n "$TARGET_NODE" ] && [ -n "$EXCLUDE_NODES" ]; then
  echo "❌ ERROR: Cannot use -n and -e together!"
  usage
fi

IMAGE_SHORT=$(basename $(echo $PULL_IMAGE | cut -d: -f1))
IMAGE_TAG=$(echo $PULL_IMAGE | cut -d: -f2)

# Ensure image has docker.io/ prefix for ctr
if echo "$PULL_IMAGE" | grep -qv "^docker.io/"; then
  CTR_IMAGE="docker.io/$PULL_IMAGE"
else
  CTR_IMAGE="$PULL_IMAGE"
fi

# Set up log file with dual output:
# - terminal gets raw output (ctr progress bars intact)
# - log file gets stripped output (no ANSI codes, no ctr progress lines)
LOG_FILE="pull-results-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee >(sed 's/\x1B\[[0-9;]*[mGKHF]//g' \
  | grep -v "^\s*[└├─|]" \
  | grep -v "fetching\|waiting\|already exists\|elapsed\|saved\|application/vnd" \
  >> $LOG_FILE)) 2>&1

echo "=========================================="
echo " Image Pull - Staggered Batch Run"
echo " $(date)"
echo "=========================================="
echo " Image:      $PULL_IMAGE"
echo " ctr image:  $CTR_IMAGE"
if [ -n "$TARGET_NODE" ]; then
echo " Target:     $TARGET_NODE (single node mode)"
else
echo " Batch size: $BATCH_SIZE nodes at a time"
fi
echo " Timeout:    ${TIMEOUT}s per node"
echo " Log file:   $LOG_FILE"
if [ -n "$EXCLUDE_NODES" ]; then
echo " Excluding:  $(echo $EXCLUDE_NODES | tr ',' ' ')"
fi
echo "=========================================="

# Preflight check - make sure kubectl is working
if ! kubectl get nodes &>/dev/null; then
  echo "❌ ERROR: kubectl cannot reach the cluster!"
  exit 1
fi

# ==========================================
# Build node list
# ==========================================
ALL_NODES=$(kubectl get nodes --no-headers -o custom-columns=":metadata.name")
NODES=""
EXCLUDED_COUNT=0

if [ -n "$TARGET_NODE" ]; then
  # Single node mode - verify it exists
  if ! echo "$ALL_NODES" | grep -q "^${TARGET_NODE}$"; then
    echo "❌ ERROR: Node '$TARGET_NODE' not found in cluster!"
    echo " Available nodes:"
    echo "$ALL_NODES" | while read N; do echo "   $N"; done
    exit 1
  fi
  NODES="$TARGET_NODE"
else
  # Normal mode - all nodes minus exclusions
  for NODE in $ALL_NODES; do
    EXCLUDED=false
    if [ -n "$EXCLUDE_NODES" ]; then
      for EXCL in $(echo $EXCLUDE_NODES | tr ',' ' '); do
        if [ "$NODE" = "$EXCL" ]; then
          EXCLUDED=true
          EXCLUDED_COUNT=$((EXCLUDED_COUNT + 1))
          echo "  ⏭️  Skipping excluded node: $NODE"
          break
        fi
      done
    fi
    if [ "$EXCLUDED" = "false" ]; then
      NODES="$NODES $NODE"
    fi
  done
fi

NODES=$(echo $NODES | xargs)
TOTAL_NODES=$(echo "$NODES" | wc -w)

if [ $TOTAL_NODES -eq 0 ]; then
  echo "❌ ERROR: No nodes remaining after exclusions!"
  exit 1
fi

echo " Total nodes in cluster: $(echo "$ALL_NODES" | wc -l)"
if [ -n "$TARGET_NODE" ]; then
echo " Mode:                   Single node"
else
echo " Excluded nodes:         $EXCLUDED_COUNT"
fi
echo " Nodes to pull:          $TOTAL_NODES"
echo " Total batches:          $(( (TOTAL_NODES + BATCH_SIZE - 1) / BATCH_SIZE ))"
echo "=========================================="

# ==========================================
# Helper: pull image on a single node
# Returns clean pod name only
# ==========================================
pull_on_node() {
  local NODE=$1
  local POD_NAME="image-pull-$(echo $NODE | tr '.' '-' | tr '[:upper:]' '[:lower:]')-$(date +%s)"

  # Truncate pod name to 63 chars (kubernetes limit)
  POD_NAME=$(echo $POD_NAME | cut -c1-63)

  # Redirect ALL kubectl run output to /dev/null so only echo $POD_NAME
  # is captured by the caller
  kubectl run $POD_NAME \
    -n $NAMESPACE \
    --image=alpine:latest \
    --restart=Never \
    --overrides="{
      \"spec\": {
        \"nodeName\": \"$NODE\",
        \"hostPID\": true,
        \"tolerations\": [{\"operator\": \"Exists\"}],
        \"containers\": [{
          \"name\": \"pull\",
          \"image\": \"alpine:latest\",
          \"command\": [\"/bin/sh\", \"-c\",
            \"echo === Pulling $CTR_IMAGE on \$NODE_NAME === && nsenter --mount=/proc/1/ns/mnt -- /usr/bin/ctr --namespace k8s.io images pull $CTR_IMAGE && echo === Pull complete on \$NODE_NAME === || echo === Pull FAILED on \$NODE_NAME ===\"
          ],
          \"securityContext\": {\"privileged\": true, \"runAsUser\": 0, \"runAsGroup\": 0},
          \"env\": [{\"name\": \"NODE_NAME\", \"valueFrom\": {\"fieldRef\": {\"fieldPath\": \"spec.nodeName\"}}}]
        }],
        \"restartPolicy\": \"Never\"
      }
    }" \
    --wait=false > /dev/null 2>&1

  # Only this line is captured by caller - clean pod name
  echo $POD_NAME
}

# ==========================================
# Helper: wait for pod to reach Running state
# ==========================================
wait_for_running() {
  local POD=$1
  local NODE=$2
  local ELAPSED=0

  while [ $ELAPSED -lt 120 ]; do
    STATUS=$(kubectl get pod -n $NAMESPACE $POD -o jsonpath='{.status.phase}' 2>/dev/null)
    case $STATUS in
      Running|Succeeded|Failed)
        return 0
        ;;
    esac
    echo "  ⏳ $NODE - Waiting for pod to start... ${ELAPSED}s"
    sleep 5
    ELAPSED=$((ELAPSED + 5))
  done

  echo "  ❌ $NODE - Pod failed to start after 120s"
  return 1
}

# ==========================================
# Helper: stream logs and wait for completion
# Terminal gets live ctr progress
# Returns 0 on success, 1 on failure, 2 on timeout
# ==========================================
stream_and_wait() {
  local POD=$1
  local NODE=$2
  local ELAPSED=0

  # Wait for pod to be running first
  wait_for_running $POD $NODE || return 1

  # Stream logs to terminal in background
  kubectl logs -n $NAMESPACE $POD -f --pod-running-timeout=30s 2>/dev/null &
  LOG_PID=$!

  # Poll for pod completion silently - let ctr progress own the terminal
  while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(kubectl get pod -n $NAMESPACE $POD -o jsonpath='{.status.phase}' 2>/dev/null)

    if [ "$STATUS" = "Succeeded" ] || [ "$STATUS" = "Failed" ]; then
      # Give log stream a moment to flush final output
      sleep 3
      kill $LOG_PID 2>/dev/null
      wait $LOG_PID 2>/dev/null

      # Check for explicit failure marker in logs
      FAILED=$(kubectl logs -n $NAMESPACE $POD 2>/dev/null | grep -c "Pull FAILED on")
      if [ "$FAILED" -gt "0" ] || [ "$STATUS" = "Failed" ]; then
        echo "  ❌ Pull failed on $NODE"
        return 1
      fi
      return 0
    fi

    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
  done

  # Timeout reached
  kill $LOG_PID 2>/dev/null
  wait $LOG_PID 2>/dev/null
  echo "  ⚠️  TIMED OUT after ${TIMEOUT}s on $NODE"
  return 2
}

# ==========================================
# Helper: cleanup a pod
# ==========================================
cleanup_pod() {
  local POD=$1
  kubectl delete pod -n $NAMESPACE $POD --ignore-not-found=true --wait=false > /dev/null 2>&1
  echo "  🧹 Cleaned up pod $POD"
}

# ==========================================
# MAIN: Batch pull loop
# ==========================================
FAILED_NODES=""
BATCH_NUM=0
NODE_ARRAY=($NODES)
TOTAL=${#NODE_ARRAY[@]}

i=0
while [ $i -lt $TOTAL ]; do
  BATCH_NUM=$((BATCH_NUM + 1))
  BATCH_END=$((i + BATCH_SIZE))
  if [ $BATCH_END -gt $TOTAL ]; then BATCH_END=$TOTAL; fi

  echo ""
  echo "=========================================="
  echo " BATCH $BATCH_NUM: Nodes $((i+1)) to $BATCH_END of $TOTAL"
  echo " $(date)"
  echo "=========================================="

  # Launch all pods in this batch simultaneously
  declare -A BATCH_PODS
  for j in $(seq $i $((BATCH_END - 1))); do
    NODE=${NODE_ARRAY[$j]}
    echo "  🚀 Starting pull on $NODE..."
    POD=$(pull_on_node $NODE)
    BATCH_PODS[$NODE]=$POD
    echo "  📦 Pod $POD launched on $NODE"
  done

  # Wait for all pods in this batch sequentially
  for NODE in "${!BATCH_PODS[@]}"; do
    POD=${BATCH_PODS[$NODE]}
    echo ""
    echo "------------------------------------------"
    echo " Node: $NODE"
    echo "------------------------------------------"
    stream_and_wait $POD $NODE
    RESULT=$?
    cleanup_pod $POD

    if [ $RESULT -ne 0 ]; then
      echo "  ⚠️  $NODE failed — adding to retry list"
      FAILED_NODES="$FAILED_NODES $NODE"
    else
      echo "  ✅ $NODE complete"
    fi
  done

  unset BATCH_PODS
  i=$BATCH_END
done

# ==========================================
# RETRY PASS: failed nodes one at a time
# ==========================================
RETRY_SUCCESS=0
RETRY_FAILED=0

if [ -n "$FAILED_NODES" ]; then
  echo ""
  echo "=========================================="
  echo " RETRY PASS - Failed nodes one at a time"
  echo " $(date)"
  echo "=========================================="

  for NODE in $FAILED_NODES; do
    echo ""
    echo "------------------------------------------"
    echo " Node: $NODE (retry)"
    echo "------------------------------------------"
    echo "  🔄 Retrying $NODE..."
    POD=$(pull_on_node $NODE)
    stream_and_wait $POD $NODE
    RESULT=$?
    cleanup_pod $POD

    if [ $RESULT -eq 0 ]; then
      echo "  ✅ $NODE retry succeeded"
      RETRY_SUCCESS=$((RETRY_SUCCESS + 1))
    else
      echo "  ❌ $NODE retry failed"
      RETRY_FAILED=$((RETRY_FAILED + 1))
    fi
  done
fi

# ==========================================
# SUMMARY
# ==========================================
FAILED_COUNT=$(echo $FAILED_NODES | wc -w)
INITIAL_SUCCESS=$((TOTAL - FAILED_COUNT))

echo ""
echo "=========================================="
echo " SUMMARY - $(date)"
echo "=========================================="
echo " Image:                $PULL_IMAGE"
echo " Total nodes:          $TOTAL"
if [ -n "$TARGET_NODE" ]; then
echo " Mode:                 Single node"
else
echo " ⏭️  Excluded:          $EXCLUDED_COUNT"
fi
echo " ✅ Succeeded:         $INITIAL_SUCCESS"
if [ -n "$FAILED_NODES" ]; then
echo " ⚠️  Initial failures:  $FAILED_COUNT"
echo " ✅ Retry succeeded:   $RETRY_SUCCESS"
echo " ❌ Retry failed:      $RETRY_FAILED"
fi
echo "=========================================="

if [ $RETRY_FAILED -gt 0 ]; then
  echo " ⚠️  Some nodes failed even after retry - review logs above"
  exit 1
fi

echo " 🎉 All nodes pulled successfully!"
exit 0
