#!/bin/bash

NAMESPACE="kube-system"
POLL_INTERVAL=10        # seconds between checks

# ==========================================
# Email configuration
# ==========================================
EMAIL_ENABLED=true
SMTP_SERVER="innovate.cs.queensu.ca"
SMTP_PORT=25
SMTP_USE_TLS=false
SMTP_USERNAME=""
SMTP_PASSWORD=""
FROM_EMAIL="lobot@cs.queensu.ca"
TO_EMAIL="aaron@cs.queensu.ca,whb1@queensu.ca"

# ==========================================
# Email helper - reads body from temp file
# ==========================================
send_email() {
  local SUBJECT="$1"
  local BODY_FILE="$2"

  if [ "$EMAIL_ENABLED" != "true" ]; then
    rm -f "$BODY_FILE"
    return 0
  fi

  python3 <<PYEOF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

smtp_server = "${SMTP_SERVER}"
smtp_port   = ${SMTP_PORT}
use_tls     = "${SMTP_USE_TLS}" in ("true", "True", "1")
username    = "${SMTP_USERNAME}"
password    = "${SMTP_PASSWORD}"
from_email  = "${FROM_EMAIL}"
to_emails   = [a.strip() for a in "${TO_EMAIL}".split(",")]

with open("${BODY_FILE}", "r") as f:
    body = f.read()

msg = MIMEMultipart("alternative")
msg["Subject"] = """${SUBJECT}"""
msg["From"]    = f"Lobot Cluster <{from_email}>"
msg["To"]      = ", ".join(to_emails)
msg.attach(MIMEText(body, "html"))

try:
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.sendmail(from_email, to_emails, msg.as_string())
    print("ok")
except Exception as e:
    print(f"error: {e}")
    exit(1)
PYEOF

  if [ $? -eq 0 ]; then
    echo " 📧 Email notification sent to $TO_EMAIL"
  else
    echo " ⚠️  Email notification failed to send"
  fi

  rm -f "$BODY_FILE"
}

# ==========================================
# HTML email body builder
# Writes directly to stdout - redirect to file at call site
# ==========================================
build_email_body() {
  local LOG="$1"
  local STATUS="$2"

  if [ "$STATUS" = "success" ]; then
    STATUS_COLOR="#2e7d32"
    STATUS_LABEL="✅ Completed Successfully"
  else
    STATUS_COLOR="#c62828"
    STATUS_LABEL="❌ Completed With Errors"
  fi

  LOG_CONTENT=$(cat "$LOG" | \
    sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g' | \
    sed 's/✅/<span style="color:#2e7d32">✅/g' | \
    sed 's/❌/<span style="color:#c62828">❌/g' | \
    sed 's/⚠️/<span style="color:#f57f17">⚠️/g' | \
    sed 's/🚀/<span style="color:#1565c0">🚀/g' | \
    sed 's/⏭️/<span style="color:#6a1e99">⏭️/g' | \
    awk '{print $0"</span><br>"}')

  cat <<BODYEOF
<html>
<body style="font-family: monospace; background-color: #1e1e1e; color: #d4d4d4; padding: 20px;">
  <div style="max-width: 900px; margin: 0 auto;">
    <div style="background-color: #2d2d2d; border-left: 5px solid ${STATUS_COLOR}; padding: 15px 20px; margin-bottom: 20px; border-radius: 4px;">
      <h2 style="margin: 0; color: ${STATUS_COLOR}; font-family: monospace;">${STATUS_LABEL}</h2>
      <p style="margin: 5px 0 0 0; color: #9e9e9e;">image-pull.sh &mdash; $(date)</p>
    </div>
    <div style="background-color: #2d2d2d; padding: 20px; border-radius: 4px; line-height: 1.6;">
${LOG_CONTENT}
    </div>
    <div style="margin-top: 15px; color: #616161; font-size: 0.85em;">
      Sent by Lobot Cluster Management &mdash; ${SMTP_SERVER}
    </div>
  </div>
</body>
</html>
BODYEOF
}

# ==========================================
# Helper: finalize log and send email
# Cleans raw capture into log file then emails
# ==========================================
finalize_and_email() {
  local SUBJECT="$1"
  local STATUS="$2"

  # Close the raw capture by redirecting back to terminal
  # then generate the clean log synchronously
  exec >/dev/tty 2>&1

  sed 's/\x1B\[[0-9;]*[mGKHF]//g' "$RAW_TMPFILE" \
    | grep -v "^\s*[└├─|]" \
    | grep -v "fetching\|waiting\|already exists\|elapsed\|saved\|application/vnd" \
    > "$LOG_FILE"

  BODY_TMPFILE=$(mktemp)
  build_email_body "$LOG_FILE" "$STATUS" > "$BODY_TMPFILE"
  send_email "$SUBJECT" "$BODY_TMPFILE"

  rm -f "$RAW_TMPFILE"
}

# ==========================================
# Parameter handling
# ==========================================
usage() {
  echo "Usage: $0 -i <image:tag> [-i <image:tag> ...] [-b <batch_size>] [-t <timeout>] [-e <exclude>] [-n <node>] [--dry-run]"
  echo ""
  echo "  -i        Full image name and tag to pull (required, repeatable)"
  echo "  -b        Number of nodes pulling simultaneously (default: 3)"
  echo "  -t        Timeout in seconds per node (default: 1200)"
  echo "  -e        Comma-separated list of nodes to exclude"
  echo "  -n        Target a single specific node only"
  echo "  --dry-run Report what would be pulled without actually pulling"
  echo ""
  echo "Examples:"
  echo "  $0 -i queensschoolofcomputingdocker/gpu-jupyter-latest:tag -b 3 -e lobot-dev.cs.queensu.ca"
  echo "  $0 -i queensschoolofcomputingdocker/gpu-jupyter-latest:tag -n newcluster-gpunode3 --dry-run"
  exit 1
}

BATCH_SIZE=3
TIMEOUT=1200
EXCLUDE_NODES=""
TARGET_NODE=""
DRY_RUN=false
PULL_IMAGES=()

ARGS=()
for arg in "$@"; do
  case $arg in
    --dry-run) DRY_RUN=true ;;
    *) ARGS+=("$arg") ;;
  esac
done

while getopts ":i:b:t:e:n:" opt "${ARGS[@]}"; do
  case $opt in
    i) PULL_IMAGES+=("$OPTARG") ;;
    b) BATCH_SIZE="$OPTARG" ;;
    t) TIMEOUT="$OPTARG" ;;
    e) EXCLUDE_NODES="$OPTARG" ;;
    n) TARGET_NODE="$OPTARG" ;;
    *) usage ;;
  esac
done

if [ ${#PULL_IMAGES[@]} -eq 0 ]; then
  echo "❌ ERROR: At least one image (-i) is required!"
  usage
fi

if [ -n "$TARGET_NODE" ] && [ -n "$EXCLUDE_NODES" ]; then
  echo "❌ ERROR: Cannot use -n and -e together!"
  usage
fi

IMAGE_SHORT=$(basename $(echo ${PULL_IMAGES[0]} | cut -d: -f1))

CTR_IMAGES=()
for IMG in "${PULL_IMAGES[@]}"; do
  if echo "$IMG" | grep -qv "^docker.io/"; then
    CTR_IMAGES+=("docker.io/$IMG")
  else
    CTR_IMAGES+=("$IMG")
  fi
done
CTR_IMAGES_STR="${CTR_IMAGES[*]}"

LOG_FILE="pull-results-$(date +%Y%m%d-%H%M%S).log"
if [ "$DRY_RUN" = "true" ]; then
  LOG_FILE="pull-dryrun-$(date +%Y%m%d-%H%M%S).log"
fi

# Capture raw output to temp file - clean log generated at end
RAW_TMPFILE=$(mktemp)
exec > >(tee "$RAW_TMPFILE") 2>&1
SCRIPT_START=$(date +%s)
NODE_TIMING=""

# ==========================================
# Helper: format seconds as Xm YYs or Xh YYm YYs
# ==========================================
format_elapsed() {
  local SECS=$1
  local H=$((SECS / 3600))
  local M=$(( (SECS % 3600) / 60 ))
  local S=$((SECS % 60))
  if [ $H -gt 0 ]; then
    printf "%dh %02dm %02ds" $H $M $S
  else
    printf "%dm %02ds" $M $S
  fi
}

echo "=========================================="
if [ "$DRY_RUN" = "true" ]; then
echo " Image Pull - DRY RUN (no changes will be made)"
else
echo " Image Pull - Staggered Batch Run"
fi
echo " $(date)"
echo "=========================================="
if [ ${#PULL_IMAGES[@]} -eq 1 ]; then
echo " Image:      ${PULL_IMAGES[0]}"
echo " ctr image:  ${CTR_IMAGES[0]}"
else
echo " Images (${#PULL_IMAGES[@]}):"
for IMG in "${PULL_IMAGES[@]}"; do
echo "   $IMG"
done
fi
if [ -n "$TARGET_NODE" ]; then
echo " Target:     $TARGET_NODE (single node mode)"
else
echo " Batch size: $BATCH_SIZE nodes at a time"
fi
echo " Timeout:    ${TIMEOUT}s per node"
echo " Log file:   $LOG_FILE"
if [ "$DRY_RUN" = "true" ]; then
echo " Mode:       🔍 DRY RUN - no pods will be launched"
fi
if [ -n "$EXCLUDE_NODES" ]; then
echo " Excluding:  $(echo $EXCLUDE_NODES | tr ',' ' ')"
fi
echo "=========================================="

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
  if ! echo "$ALL_NODES" | grep -q "^${TARGET_NODE}$"; then
    echo "❌ ERROR: Node '$TARGET_NODE' not found in cluster!"
    echo " Available nodes:"
    echo "$ALL_NODES" | while read N; do echo "   $N"; done
    exit 1
  fi
  NODES="$TARGET_NODE"
else
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

# ==========================================
# Pre-flight: skip NotReady and control-plane nodes
# ==========================================
OFFLINE_NODES=""
CONTROL_PLANE_NODES=""
READY_NODES=""
for NODE in $NODES; do
  READY=$(kubectl get node $NODE -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
  IS_CP=$(kubectl get node $NODE -o jsonpath='{.metadata.labels}' 2>/dev/null | grep -c 'control-plane')
  if [ "$READY" != "True" ]; then
    echo "  ⚠️  $NODE — NotReady, skipping"
    OFFLINE_NODES="$OFFLINE_NODES $NODE"
  elif [ "$IS_CP" -gt 0 ] && [ "$NODE" != "$TARGET_NODE" ]; then
    echo "  ⏭️  $NODE — control-plane, auto-excluded (use -n to target explicitly)"
    CONTROL_PLANE_NODES="$CONTROL_PLANE_NODES $NODE"
  else
    READY_NODES="$READY_NODES $NODE"
  fi
done
NODES=$(echo $READY_NODES | xargs)
OFFLINE_COUNT=$(echo $OFFLINE_NODES | wc -w | tr -d ' ')
CP_COUNT=$(echo $CONTROL_PLANE_NODES | wc -w | tr -d ' ')
TOTAL_NODES=$(echo "$NODES" | wc -w)

if [ $TOTAL_NODES -eq 0 ]; then
  echo "❌ ERROR: No Ready worker nodes remaining!"
  exit 1
fi

echo " Total nodes in cluster: $(echo "$ALL_NODES" | wc -l)"
if [ -n "$TARGET_NODE" ]; then
echo " Mode:                   Single node"
else
echo " Excluded nodes:         $EXCLUDED_COUNT"
fi
if [ "$CP_COUNT" -gt 0 ] 2>/dev/null; then
echo " ⏭️  Control-plane:       $CP_COUNT"
fi
if [ "$OFFLINE_COUNT" -gt 0 ] 2>/dev/null; then
echo " ⚠️  Offline (skipped):   $OFFLINE_COUNT"
fi
echo " Nodes to pull:          $TOTAL_NODES"
echo " Total batches:          $(( (TOTAL_NODES + BATCH_SIZE - 1) / BATCH_SIZE ))"
echo "=========================================="

# ==========================================
# DRY RUN
# ==========================================
if [ "$DRY_RUN" = "true" ]; then
  echo ""
  echo "=========================================="
  echo " DRY RUN: Checking image status per node"
  echo "=========================================="

  NODE_ARRAY=($NODES)
  TOTAL=${#NODE_ARRAY[@]}
  BATCH_NUM=0

  i=0
  while [ $i -lt $TOTAL ]; do
    BATCH_NUM=$((BATCH_NUM + 1))
    BATCH_END=$((i + BATCH_SIZE))
    if [ $BATCH_END -gt $TOTAL ]; then BATCH_END=$TOTAL; fi

    echo ""
    echo " BATCH $BATCH_NUM: Nodes $((i+1)) to $BATCH_END of $TOTAL"
    echo "------------------------------------------"

    for j in $(seq $i $((BATCH_END - 1))); do
      NODE=${NODE_ARRAY[$j]}
      echo "  🔍 Checking $NODE..."

      CHECK_OUTPUT=$(kubectl run dry-run-check-$(date +%s) \
        -n $NAMESPACE \
        --image=alpine:latest \
        --restart=Never \
        --rm \
        --overrides="{
          \"spec\": {
            \"nodeName\": \"$NODE\",
            \"hostPID\": true,
            \"tolerations\": [{\"operator\": \"Exists\"}],
            \"containers\": [{
              \"name\": \"check\",
              \"image\": \"alpine:latest\",
              \"command\": [\"/bin/sh\", \"-c\",
                \"for IMG in \$CTR_IMAGES ; do COUNT=\$(nsenter --mount=/proc/1/ns/mnt -- /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | grep -c \$IMG || echo 0) ; if [ \$COUNT -gt 0 ] ; then echo PRESENT:\$IMG ; else echo MISSING:\$IMG ; fi ; done\"
              ],
              \"securityContext\": {\"privileged\": true, \"runAsUser\": 0},
              \"env\": [{\"name\": \"CTR_IMAGES\", \"value\": \"$CTR_IMAGES_STR\"}]
            }],
            \"restartPolicy\": \"Never\"
          }
        }" \
        --wait=true \
        -i \
        --quiet 2>/dev/null)

      while IFS= read -r LINE; do
        case "$LINE" in
          PRESENT:*) echo "  ✅ $NODE — ${LINE#PRESENT:} already present, pull would be skipped" ;;
          MISSING:*) echo "  📥 $NODE — image NOT present, would pull: ${LINE#MISSING:}" ;;
        esac
      done <<< "$CHECK_OUTPUT"
    done

    i=$BATCH_END
  done

  echo ""
  echo "=========================================="
  echo " DRY RUN SUMMARY - $(date)"
  echo "=========================================="
  if [ ${#PULL_IMAGES[@]} -eq 1 ]; then
  echo " Image:        ${PULL_IMAGES[0]}"
  else
  echo " Images (${#PULL_IMAGES[@]}):"
  for IMG in "${PULL_IMAGES[@]}"; do
  echo "   $IMG"
  done
  fi
  echo " Total nodes:  $TOTAL_NODES"
  echo " Batch size:   $BATCH_SIZE"
  if [ -n "$TARGET_NODE" ]; then
  echo " Mode:         Single node"
  else
  echo " ⏭️  Excluded:  $EXCLUDED_COUNT"
  fi
  echo " No changes were made."
  SCRIPT_END=$(date +%s)
  TOTAL_ELAPSED=$((SCRIPT_END - SCRIPT_START))
  echo " ⏱️  Total elapsed:  $(format_elapsed $TOTAL_ELAPSED)"
  echo "=========================================="

  finalize_and_email "🔍 [DRY RUN] image-pull.sh | $IMAGE_SHORT | $TOTAL_NODES node(s) checked" "success"
  exit 0
fi

# ==========================================
# Helper: pull image on a single node
# ==========================================
pull_on_node() {
  local NODE=$1
  local POD_NAME="image-pull-$(echo $NODE | tr '.' '-' | tr '[:upper:]' '[:lower:]')-$(date +%s)"
  POD_NAME=$(echo $POD_NAME | cut -c1-63)
  local CTR_IMAGES_STR="${CTR_IMAGES[*]}"

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
            \"echo === Node: \$NODE_NAME === ; echo === Disk space before pull === ; nsenter --mount=/proc/1/ns/mnt -- df -h /var/lib/containerd ; nsenter --mount=/proc/1/ns/mnt -- du -sh /var/lib/containerd ; OVERALL_RC=0 ; for IMG in \$CTR_IMAGES ; do echo === Pulling \$IMG === ; nsenter --mount=/proc/1/ns/mnt -- /usr/bin/ctr --namespace k8s.io images pull \$IMG ; [ \$? -ne 0 ] && OVERALL_RC=1 ; done ; echo === Disk space after pull === ; nsenter --mount=/proc/1/ns/mnt -- df -h /var/lib/containerd ; nsenter --mount=/proc/1/ns/mnt -- du -sh /var/lib/containerd ; if [ \$OVERALL_RC -eq 0 ] ; then echo === Pull complete on \$NODE_NAME === ; else echo === Pull FAILED on \$NODE_NAME === ; fi\"
          ],
          \"securityContext\": {\"privileged\": true, \"runAsUser\": 0, \"runAsGroup\": 0},
          \"env\": [
            {\"name\": \"NODE_NAME\", \"valueFrom\": {\"fieldRef\": {\"fieldPath\": \"spec.nodeName\"}}},
            {\"name\": \"CTR_IMAGES\", \"value\": \"$CTR_IMAGES_STR\"}
          ]
        }],
        \"restartPolicy\": \"Never\"
      }
    }" \
    --wait=false > /dev/null 2>&1

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
      Running|Succeeded|Failed) return 0 ;;
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
# ==========================================
stream_and_wait() {
  local POD=$1
  local NODE=$2
  local ELAPSED=0

  wait_for_running $POD $NODE || return 1

  kubectl logs -n $NAMESPACE $POD -f --pod-running-timeout=30s 2>/dev/null &
  LOG_PID=$!

  while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(kubectl get pod -n $NAMESPACE $POD -o jsonpath='{.status.phase}' 2>/dev/null)

    if [ "$STATUS" = "Succeeded" ] || [ "$STATUS" = "Failed" ]; then
      sleep 3
      kill $LOG_PID 2>/dev/null
      wait $LOG_PID 2>/dev/null

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

  declare -A BATCH_PODS
  for j in $(seq $i $((BATCH_END - 1))); do
    NODE=${NODE_ARRAY[$j]}
    echo "  🚀 Starting pull on $NODE..."
    POD=$(pull_on_node $NODE)
    BATCH_PODS[$NODE]=$POD
    echo "  📦 Pod $POD launched on $NODE"
  done

  for NODE in "${!BATCH_PODS[@]}"; do
    POD=${BATCH_PODS[$NODE]}
    echo ""
    echo "------------------------------------------"
    echo " Node: $NODE"
    echo " $(date)"
    echo "------------------------------------------"
    NODE_START=$(date +%s)
    stream_and_wait $POD $NODE
    RESULT=$?
    NODE_END=$(date +%s)
    NODE_ELAPSED=$((NODE_END - NODE_START))
    cleanup_pod $POD

    if [ $RESULT -ne 0 ]; then
      echo "  ⚠️  $NODE failed — adding to retry list ($(format_elapsed $NODE_ELAPSED))"
      FAILED_NODES="$FAILED_NODES $NODE"
      NODE_TIMING="${NODE_TIMING}\n  ❌ $NODE — $(format_elapsed $NODE_ELAPSED) (failed)"
    else
      echo "  ✅ $NODE complete ($(format_elapsed $NODE_ELAPSED))"
      NODE_TIMING="${NODE_TIMING}\n  ✅ $NODE — $(format_elapsed $NODE_ELAPSED)"
    fi
  done

  unset BATCH_PODS
  i=$BATCH_END
done

# ==========================================
# RETRY PASS
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
    echo " $(date)"
    echo "------------------------------------------"
    echo "  🔄 Retrying $NODE..."
    POD=$(pull_on_node $NODE)
    NODE_START=$(date +%s)
    stream_and_wait $POD $NODE
    RESULT=$?
    NODE_END=$(date +%s)
    NODE_ELAPSED=$((NODE_END - NODE_START))
    cleanup_pod $POD

    if [ $RESULT -eq 0 ]; then
      echo "  ✅ $NODE retry succeeded ($(format_elapsed $NODE_ELAPSED))"
      RETRY_SUCCESS=$((RETRY_SUCCESS + 1))
      NODE_TIMING="${NODE_TIMING}\n  ✅ $NODE — $(format_elapsed $NODE_ELAPSED) (retry)"
    else
      echo "  ❌ $NODE retry failed ($(format_elapsed $NODE_ELAPSED))"
      RETRY_FAILED=$((RETRY_FAILED + 1))
      NODE_TIMING="${NODE_TIMING}\n  ❌ $NODE — $(format_elapsed $NODE_ELAPSED) (retry failed)"
    fi
  done
fi

# ==========================================
# SUMMARY
# ==========================================
FAILED_COUNT=$(echo $FAILED_NODES | wc -w)
INITIAL_SUCCESS=$((TOTAL - FAILED_COUNT))
SCRIPT_END=$(date +%s)
TOTAL_ELAPSED=$((SCRIPT_END - SCRIPT_START))

echo ""
echo "=========================================="
echo " SUMMARY - $(date)"
echo "=========================================="
if [ ${#PULL_IMAGES[@]} -eq 1 ]; then
echo " Image:                ${PULL_IMAGES[0]}"
else
echo " Images (${#PULL_IMAGES[@]}):"
for IMG in "${PULL_IMAGES[@]}"; do
echo "   $IMG"
done
fi
echo " Total nodes:          $TOTAL"
if [ -n "$TARGET_NODE" ]; then
echo " Mode:                 Single node"
else
echo " ⏭️  Excluded:          $EXCLUDED_COUNT"
fi
if [ "$OFFLINE_COUNT" -gt 0 ] 2>/dev/null; then
echo " ⚠️  Offline (skipped): $OFFLINE_COUNT"
fi
echo " ✅ Succeeded:         $INITIAL_SUCCESS"
if [ -n "$FAILED_NODES" ]; then
echo " ⚠️  Initial failures:  $FAILED_COUNT"
echo " ✅ Retry succeeded:   $RETRY_SUCCESS"
echo " ❌ Retry failed:      $RETRY_FAILED"
fi
echo " ⏱️  Total elapsed:     $(format_elapsed $TOTAL_ELAPSED)"
echo "=========================================="
if [ -n "$NODE_TIMING" ]; then
echo " Node timing:"
printf "$NODE_TIMING\n"
echo "=========================================="
fi

if [ $RETRY_FAILED -gt 0 ]; then
  echo " ⚠️  Some nodes failed even after retry - review logs above"
  finalize_and_email "❌ image-pull.sh FAILED | $IMAGE_SHORT | ${RETRY_FAILED} node(s) failed" "failure"
else
  echo " 🎉 All nodes pulled successfully!"
  finalize_and_email "✅ image-pull.sh complete | $IMAGE_SHORT | ${TOTAL} node(s) pulled" "success"
fi

exit $( [ $RETRY_FAILED -gt 0 ] && echo 1 || echo 0 )
