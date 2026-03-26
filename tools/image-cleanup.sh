#!/bin/bash

NAMESPACE="kube-system"
LABEL="name=image-cleanup"
DAEMONSET_FILE="image-cleanup-ds.yaml"
POLL_INTERVAL=10
TIMEOUT=600
DS_READY_TIMEOUT=120

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
#TO_EMAIL="aaron@cs.queensu.ca"

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
import smtplib, socket
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
msg["From"]    = f"{socket.getfqdn()} <{from_email}>"
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
      <p style="margin: 5px 0 0 0; color: #9e9e9e;">image-cleanup.sh &mdash; $(date)</p>
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
# Parameter handling
# ==========================================
usage() {
  echo "Usage: $0 -i <image:tag> [-i <image:tag> ...] [-e <exclude_nodes>] [-n <node>] [--dry-run] [--yes]"
  echo ""
  echo "  -i        Full image name and tag to KEEP (repeatable; all other tags will be removed)"
  echo "  -e        Comma-separated list of nodes to exclude"
  echo "  -n        Target a single specific node only"
  echo "  --dry-run  Report what would be removed without actually removing anything"
  echo "  --yes      Skip the confirmation prompt before removing images"
  echo "  --noemail  Skip email notification (useful for testing)"
  echo ""
  echo "Examples:"
  echo "  $0 -i queensschoolofcomputingdocker/gpu-jupyter-latest:tag -e lobot-dev.cs.queensu.ca"
  echo "  $0 -i queensschoolofcomputingdocker/gpu-jupyter-latest:tag -n newcluster-gpunode3 --dry-run"
  exit 1
}

INVOCATION="$0 $*"
EXCLUDE_NODES=""
TARGET_NODE=""
DRY_RUN=false
AUTO_YES=false
KEEP_IMAGES=()

ARGS=()
for arg in "$@"; do
  case $arg in
    --dry-run)  DRY_RUN=true ;;
    --yes)      AUTO_YES=true ;;
    --noemail)  EMAIL_ENABLED=false ;;
    *) ARGS+=("$arg") ;;
  esac
done

while getopts ":i:e:n:" opt "${ARGS[@]}"; do
  case $opt in
    i) KEEP_IMAGES+=("$OPTARG") ;;
    e) EXCLUDE_NODES="$OPTARG" ;;
    n) TARGET_NODE="$OPTARG" ;;
    *) usage ;;
  esac
done

if [ ${#KEEP_IMAGES[@]} -eq 0 ]; then
  echo "❌ ERROR: At least one image (-i) is required!"
  usage
fi

if [ -n "$TARGET_NODE" ] && [ -n "$EXCLUDE_NODES" ]; then
  echo "❌ ERROR: Cannot use -n and -e together!"
  usage
fi

IMAGE_SHORT=$(basename $(echo ${KEEP_IMAGES[0]} | cut -d: -f1))

KEEP_IMAGES_FULL=""
for IMG in "${KEEP_IMAGES[@]}"; do
  IMAGE_NAME=$(echo $IMG | cut -d: -f1)
  IMAGE_TAG=$(echo $IMG | cut -d: -f2)
  KEEP_IMAGES_FULL="$KEEP_IMAGES_FULL docker.io/${IMAGE_NAME}:${IMAGE_TAG}"
done
KEEP_IMAGES_FULL=$(echo $KEEP_IMAGES_FULL | xargs)

LOG_FILE="cleanup-results-$(date +%Y%m%d-%H%M%S).log"
if [ "$DRY_RUN" = "true" ]; then
  LOG_FILE="cleanup-dryrun-$(date +%Y%m%d-%H%M%S).log"
fi

exec > >(tee -a $LOG_FILE) 2>&1
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
echo " Image Cleanup - DRY RUN (no changes will be made)"
else
echo " Image Cleanup - Full Run"
fi
echo " $(date)"
echo "=========================================="
for FULL_IMG in $KEEP_IMAGES_FULL; do
echo " Keeping:   $FULL_IMG"
done
echo " Removing:  Unused old tags of $IMAGE_SHORT (except above)"
echo " Log file:  $LOG_FILE"
echo " Invoked:   $INVOCATION"
if [ "$DRY_RUN" = "true" ]; then
echo " Mode:      🔍 DRY RUN - no images will be removed"
fi
if [ -n "$TARGET_NODE" ]; then
echo " Target:    $TARGET_NODE (single node mode)"
elif [ -n "$EXCLUDE_NODES" ]; then
echo " Excluding: $(echo $EXCLUDE_NODES | tr ',' ' ')"
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
echo " ⏭️  Control-plane (skipped): $CP_COUNT"
fi
if [ "$OFFLINE_COUNT" -gt 0 ] 2>/dev/null; then
echo " ⚠️  Offline (skipped):   $OFFLINE_COUNT"
fi
echo " Nodes to clean:         $TOTAL_NODES"

# ==========================================
# STEP 0: Scan in-use images per node
# ==========================================
echo ""
echo "=========================================="
echo " STEP 0: Scanning in-use images per node"
echo "=========================================="

IN_USE_TMPFILE=$(mktemp)
kubectl get pods --all-namespaces \
  -o jsonpath='{range .items[*]}{.spec.nodeName}{"|"}{.metadata.namespace}{"|"}{.metadata.name}{"|"}{range .status.containerStatuses[*]}{.image}{" "}{end}{"\n"}{end}' \
  > $IN_USE_TMPFILE

echo " In-use image scan complete"

get_inuse_tags_for_node() {
  local NODE=$1
  grep "^$NODE|" $IN_USE_TMPFILE | while IFS='|' read -r NODENAME NS POD IMAGES; do
    for IMG in $IMAGES; do
      if echo "$IMG" | grep -q "$IMAGE_SHORT"; then
        echo "$IMG|$NS|$POD"
      fi
    done
  done | sort -u
}

get_inuse_imagetags_for_node() {
  local NODE=$1
  get_inuse_tags_for_node $NODE | cut -d'|' -f1
}

for NODE in $NODES; do
  INUSE=$(get_inuse_tags_for_node $NODE)
  if [ -n "$INUSE" ]; then
    echo ""
    echo "  Node: $NODE"
    echo "  In-use $IMAGE_SHORT tags:"
    echo "$INUSE" | while IFS='|' read -r IMG NS POD; do
      echo "    ⚠️  $IMG"
      echo "       └─ pod: $NS/$POD"
    done
  fi
done

# ==========================================
# DRY RUN
# ==========================================
if [ "$DRY_RUN" = "true" ]; then
  echo ""
  echo "=========================================="
  echo " DRY RUN: Checking images on each node"
  echo "=========================================="

  for NODE in $NODES; do
    echo ""
    echo " Node: $NODE"
    echo "------------------------------------------"

    INUSE_TAGS=$(get_inuse_imagetags_for_node $NODE)

    CHECK_POD="dry-run-check-$(echo $NODE | tr '.' '-' | tr '[:upper:]' '[:lower:]')-$(date +%s)"
    CHECK_POD=$(echo $CHECK_POD | cut -c1-63)

    kubectl run $CHECK_POD \
      -n $NAMESPACE \
      --image=alpine:latest \
      --restart=Never \
      --overrides="{
        \"spec\": {
          \"nodeName\": \"$NODE\",
          \"hostPID\": true,
          \"tolerations\": [{\"operator\": \"Exists\"}],
          \"containers\": [{
            \"name\": \"check\",
            \"image\": \"alpine:latest\",
            \"command\": [\"/bin/sh\", \"-c\",
              \"nsenter --mount=/proc/1/ns/mnt -- /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | grep '$IMAGE_SHORT' | awk '{print \\\$1}'\"
            ],
            \"securityContext\": {\"privileged\": true, \"runAsUser\": 0}
          }],
          \"restartPolicy\": \"Never\"
        }
      }" \
      --wait=true \
      -i \
      --quiet 2>/dev/null | while read IMAGE_REF; do
        [ -z "$IMAGE_REF" ] && continue

        SHOULD_KEEP=false
        for KEEP_IMG in $KEEP_IMAGES_FULL; do
          [ "$IMAGE_REF" = "$KEEP_IMG" ] && SHOULD_KEEP=true && break
        done
        if [ "$SHOULD_KEEP" = "true" ]; then
          echo "  ✅ Would keep:   $IMAGE_REF"
          continue
        fi

        SKIP=false
        for INUSE_TAG in $INUSE_TAGS; do
          if [ "$IMAGE_REF" = "$INUSE_TAG" ]; then
            SKIP=true
            break
          fi
        done

        if [ "$SKIP" = "true" ]; then
          echo "  ⚠️  Would skip:   $IMAGE_REF (in use by running pod)"
        else
          echo "  🗑️  Would remove: $IMAGE_REF"
        fi
      done

    kubectl delete pod $CHECK_POD -n $NAMESPACE --ignore-not-found=true --wait=false > /dev/null 2>&1
  done

  echo ""
  echo "=========================================="
  echo " DRY RUN SUMMARY - $(date)"
  echo "=========================================="
  for FULL_IMG in $KEEP_IMAGES_FULL; do
  echo " Image kept:    $FULL_IMG"
  done
  echo " Total nodes:   $TOTAL_NODES"
  if [ -n "$TARGET_NODE" ]; then
  echo " Mode:          Single node"
  else
  echo " ⏭️  Excluded:   $EXCLUDED_COUNT"
  fi
  if [ "$CP_COUNT" -gt 0 ] 2>/dev/null; then
  echo " ⏭️  Control-plane (skipped): $CP_COUNT"
  fi
  if [ "$OFFLINE_COUNT" -gt 0 ] 2>/dev/null; then
  echo " ⚠️  Offline (skipped): $OFFLINE_COUNT"
  fi
  echo " No changes were made."
  SCRIPT_END=$(date +%s)
  TOTAL_ELAPSED=$((SCRIPT_END - SCRIPT_START))
  echo " ⏱️  Total elapsed:  $(format_elapsed $TOTAL_ELAPSED)"
  echo "=========================================="

  rm -f $IN_USE_TMPFILE

  # Flush log before emailing
  sleep 2

  BODY_TMPFILE=$(mktemp)
  build_email_body "$LOG_FILE" "success" > "$BODY_TMPFILE"
  send_email "🔍 [DRY RUN] image-cleanup.sh | $IMAGE_SHORT | $TOTAL_NODES node(s) checked" "$BODY_TMPFILE"

  exit 0
fi

# ==========================================
# Confirmation prompt
# ==========================================
if [ "$AUTO_YES" != "true" ]; then
  echo ""
  printf " Proceed with cleanup on $TOTAL_NODES node(s)? [y/N] "
  read -r CONFIRM
  if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo " Aborted."
    exit 0
  fi
fi

# ==========================================
# STEP 1: Generate DaemonSet yaml
# ==========================================
echo ""
echo "=========================================="
echo " STEP 1: Generating DaemonSet with image"
echo "=========================================="

CONFIGMAP_DATA=""
for NODE in $NODES; do
  INUSE=$(get_inuse_imagetags_for_node $NODE)
  if [ -n "$INUSE" ]; then
    ENCODED=$(echo "$INUSE" | base64 -w0)
    CONFIGMAP_DATA="$CONFIGMAP_DATA
  $NODE: \"$ENCODED\""
  fi
done

cat <<CMEOF | kubectl apply -f - > /dev/null 2>&1
apiVersion: v1
kind: ConfigMap
metadata:
  name: image-cleanup-inuse
  namespace: kube-system
data:$CONFIGMAP_DATA
CMEOF

{
cat <<DSEOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: image-cleanup
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: image-cleanup
  template:
    metadata:
      labels:
        name: image-cleanup
    spec:
      hostPID: true
      tolerations:
      - operator: Exists
DSEOF

if [ -n "$TARGET_NODE" ]; then
  echo "      affinity:"
  echo "        nodeAffinity:"
  echo "          requiredDuringSchedulingIgnoredDuringExecution:"
  echo "            nodeSelectorTerms:"
  echo "            - matchExpressions:"
  echo "              - key: kubernetes.io/hostname"
  echo "                operator: In"
  echo "                values:"
  echo "                - \"$TARGET_NODE\""
else
  COMBINED_EXCL=$(echo "$EXCLUDE_NODES $OFFLINE_NODES $CONTROL_PLANE_NODES" | tr ',' ' ' | xargs)
  if [ -n "$COMBINED_EXCL" ]; then
  echo "      affinity:"
  echo "        nodeAffinity:"
  echo "          requiredDuringSchedulingIgnoredDuringExecution:"
  echo "            nodeSelectorTerms:"
  echo "            - matchExpressions:"
  echo "              - key: kubernetes.io/hostname"
  echo "                operator: NotIn"
  echo "                values:"
  for EXCL in $COMBINED_EXCL; do
    echo "                - \"$EXCL\""
  done
  fi
fi

cat <<DSEOF2
      containers:
      - name: cleanup
        image: alpine:latest
        securityContext:
          privileged: true
          runAsUser: 0
          runAsGroup: 0
        command:
        - /bin/sh
        - -c
        - |
          echo "=== Node: \$NODE_NAME ==="

          KEEP_IMAGES_FULL="${KEEP_IMAGES_FULL}"

          INUSE_TAGS=""
          ENCODED=\$(cat /etc/image-cleanup-inuse/\$NODE_NAME 2>/dev/null)
          if [ -n "\$ENCODED" ]; then
            INUSE_TAGS=\$(echo "\$ENCODED" | base64 -d)
            echo "=== In-use tags on \$NODE_NAME (will NOT be removed) ==="
            for TAG in \$INUSE_TAGS; do
              echo "  ⚠️  \$TAG is in use by a running pod - skipping"
            done
          fi

          echo "=== Disk space before cleanup ==="
          nsenter --mount=/proc/1/ns/mnt -- df -h /var/lib/containerd
          nsenter --mount=/proc/1/ns/mnt -- du -sh /var/lib/containerd

          echo "=== Images before cleanup ==="
          nsenter --mount=/proc/1/ns/mnt -- \
            /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | grep "${IMAGE_SHORT}"

          echo "=== Removing unused old tags ==="
          nsenter --mount=/proc/1/ns/mnt -- \
            /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | \
            grep "${IMAGE_SHORT}" | \
            awk '{print \$1}' | \
            while read IMAGE_REF; do

              SHOULD_KEEP=false
              for KEEP_IMG in \$KEEP_IMAGES_FULL; do
                [ "\$IMAGE_REF" = "\$KEEP_IMG" ] && SHOULD_KEEP=true && break
              done
              if [ "\$SHOULD_KEEP" = "true" ]; then
                echo "  Keeping: \$IMAGE_REF"
                continue
              fi

              SKIP=false
              for INUSE_TAG in \$INUSE_TAGS; do
                if [ "\$IMAGE_REF" = "\$INUSE_TAG" ]; then
                  echo "  ⚠️  \$IMAGE_REF is in use by a running pod - skipping"
                  SKIP=true
                  break
                fi
              done
              [ "\$SKIP" = "true" ] && continue

              MANIFEST_DIGEST=\$(nsenter --mount=/proc/1/ns/mnt -- \
                /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | \
                grep "^\$IMAGE_REF " | awk '{print \$3}')

              echo "  Removing: \$IMAGE_REF"
              nsenter --mount=/proc/1/ns/mnt -- \
                /usr/bin/ctr --namespace k8s.io images rm "\$IMAGE_REF" 2>&1

              if [ -n "\$MANIFEST_DIGEST" ]; then
                nsenter --mount=/proc/1/ns/mnt -- \
                  /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | \
                  grep "\$MANIFEST_DIGEST" | \
                  awk '{print \$1}' | \
                  while read DIGEST_REF; do
                    DIGEST_MATCHES_KEEP=false
                    for KIMG in \$KEEP_IMAGES_FULL; do
                      KEEP_DIGEST=\$(nsenter --mount=/proc/1/ns/mnt -- \
                        /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | \
                        grep "^\$KIMG " | awk '{print \$3}')
                      if [ "\$MANIFEST_DIGEST" = "\$KEEP_DIGEST" ]; then
                        DIGEST_MATCHES_KEEP=true
                        break
                      fi
                    done
                    if [ "\$DIGEST_MATCHES_KEEP" = "true" ]; then
                      echo "  Keeping digest ref: \$DIGEST_REF (belongs to keep image)"
                      continue
                    fi
                    echo "  Removing digest ref: \$DIGEST_REF"
                    nsenter --mount=/proc/1/ns/mnt -- \
                      /usr/bin/ctr --namespace k8s.io images rm "\$DIGEST_REF" 2>&1
                  done
              fi
            done

          echo "=== Images after cleanup ==="
          nsenter --mount=/proc/1/ns/mnt -- \
            /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | grep "${IMAGE_SHORT}"

          echo "=== Disk space after cleanup ==="
          nsenter --mount=/proc/1/ns/mnt -- df -h /var/lib/containerd
          nsenter --mount=/proc/1/ns/mnt -- du -sh /var/lib/containerd

          echo "=== Cleanup complete on \$NODE_NAME ==="
          sleep 3600
        env:
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        volumeMounts:
        - name: inuse-config
          mountPath: /etc/image-cleanup-inuse
      volumes:
      - name: inuse-config
        configMap:
          name: image-cleanup-inuse
          optional: true
      restartPolicy: Always
DSEOF2
} > $DAEMONSET_FILE

echo "✅ DaemonSet yaml generated successfully"

# ==========================================
# STEP 2: Apply the DaemonSet
# ==========================================
echo ""
echo "=========================================="
echo " STEP 2: Applying DaemonSet"
echo "=========================================="
kubectl apply -f $DAEMONSET_FILE
if [ $? -ne 0 ]; then
  echo "❌ ERROR: Failed to apply DaemonSet!"
  kubectl delete configmap image-cleanup-inuse -n kube-system > /dev/null 2>&1
  rm -f $IN_USE_TMPFILE
  exit 1
fi
echo "✅ DaemonSet applied successfully"

# ==========================================
# STEP 3: Wait for pods to be scheduled
# ==========================================
echo ""
echo "=========================================="
echo " STEP 3: Waiting for pods to be scheduled"
echo "=========================================="
ELAPSED=0
while [ $ELAPSED -lt $DS_READY_TIMEOUT ]; do
  DESIRED=$(kubectl get daemonset -n $NAMESPACE image-cleanup -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null)
  READY=$(kubectl get daemonset -n $NAMESPACE image-cleanup -o jsonpath='{.status.numberReady}' 2>/dev/null)

  echo " Desired: $DESIRED / Ready: $READY - elapsed ${ELAPSED}s"

  if [ -n "$DESIRED" ] && [ "$DESIRED" -gt 0 ] && [ "$DESIRED" = "$READY" ]; then
    echo "✅ All $READY pods scheduled and running"
    break
  fi

  sleep $POLL_INTERVAL
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

if [ $ELAPSED -ge $DS_READY_TIMEOUT ]; then
  echo "⚠️  WARNING: Not all pods became ready within ${DS_READY_TIMEOUT}s - proceeding anyway"
fi

# ==========================================
# STEP 4: Collect logs from all nodes
# ==========================================
echo ""
echo "=========================================="
echo " STEP 4: Collecting logs - All Nodes"
echo "=========================================="

PODS=$(kubectl get pods -n $NAMESPACE -l $LABEL -o jsonpath='{.items[*].metadata.name}')

if [ -z "$PODS" ]; then
  echo "❌ ERROR: No image-cleanup pods found!"
  kubectl delete -f $DAEMONSET_FILE > /dev/null 2>&1
  kubectl delete configmap image-cleanup-inuse -n kube-system > /dev/null 2>&1
  rm -f $IN_USE_TMPFILE
  exit 1
fi

TOTAL=0
SUCCESS=0
FAILED=0
TIMEOUT_COUNT=0

for POD in $PODS; do
  TOTAL=$((TOTAL + 1))
  NODE=$(kubectl get pod -n $NAMESPACE $POD -o jsonpath='{.spec.nodeName}')

  echo ""
  echo "------------------------------------------"
  echo " Pod:    $POD"
  echo " Node:   $NODE"
  echo " $(date)"
  echo "------------------------------------------"
  echo " Waiting for cleanup to complete..."
  NODE_START=$(date +%s)

  ELAPSED=0
  STATUS=""
  while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(kubectl get pod -n $NAMESPACE $POD -o jsonpath='{.status.phase}')

    if [ "$STATUS" = "Succeeded" ] || [ "$STATUS" = "Failed" ]; then
      break
    fi

    COMPLETE=$(kubectl logs -n $NAMESPACE $POD 2>/dev/null | grep -c "Cleanup complete on")
    if [ "$COMPLETE" -gt "0" ]; then
      STATUS="Succeeded"
      break
    fi

    echo " Status: $STATUS - elapsed ${ELAPSED}s, checking again in ${POLL_INTERVAL}s..."
    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
  done

  if [ $ELAPSED -ge $TIMEOUT ]; then
    NODE_END=$(date +%s)
    NODE_ELAPSED=$((NODE_END - NODE_START))
    echo "⚠️  TIMED OUT after ${TIMEOUT}s on node $NODE ($(format_elapsed $NODE_ELAPSED))"
    TIMEOUT_COUNT=$((TIMEOUT_COUNT + 1))
    NODE_TIMING="${NODE_TIMING}\n  ⏱️ $NODE — $(format_elapsed $NODE_ELAPSED) (timed out)"
    echo " --- Partial logs ---"
    kubectl logs -n $NAMESPACE $POD
    continue
  fi

  echo " Status: $STATUS"
  kubectl logs -n $NAMESPACE $POD
  NODE_END=$(date +%s)
  NODE_ELAPSED=$((NODE_END - NODE_START))

  if [ "$STATUS" = "Succeeded" ]; then
    SUCCESS=$((SUCCESS + 1))
    NODE_TIMING="${NODE_TIMING}\n  ✅ $NODE — $(format_elapsed $NODE_ELAPSED)"
  else
    FAILED=$((FAILED + 1))
    NODE_TIMING="${NODE_TIMING}\n  ❌ $NODE — $(format_elapsed $NODE_ELAPSED) (failed)"
  fi
done

# ==========================================
# STEP 5: Delete the DaemonSet and ConfigMap
# ==========================================
echo ""
echo "=========================================="
echo " STEP 5: Cleaning up DaemonSet"
echo "=========================================="
kubectl delete -f $DAEMONSET_FILE > /dev/null 2>&1
kubectl delete configmap image-cleanup-inuse -n kube-system > /dev/null 2>&1
echo "✅ DaemonSet and ConfigMap deleted successfully"

# ==========================================
# SUMMARY
# ==========================================
echo ""
echo "=========================================="
echo " SUMMARY - $(date)"
echo "=========================================="
for FULL_IMG in $KEEP_IMAGES_FULL; do
echo " Image kept:     $FULL_IMG"
done
echo " Total nodes:    $TOTAL"
if [ -n "$TARGET_NODE" ]; then
echo " Mode:           Single node"
else
echo " ⏭️  Excluded:    $EXCLUDED_COUNT"
fi
if [ "$CP_COUNT" -gt 0 ] 2>/dev/null; then
echo " ⏭️  Control-plane (skipped): $CP_COUNT"
fi
if [ "$OFFLINE_COUNT" -gt 0 ] 2>/dev/null; then
echo " ⚠️  Offline (skipped): $OFFLINE_COUNT"
fi
echo " ✅ Succeeded:   $SUCCESS"
echo " ❌ Failed:      $FAILED"
echo " ⚠️  Timed out:  $TIMEOUT_COUNT"
SCRIPT_END=$(date +%s)
TOTAL_ELAPSED=$((SCRIPT_END - SCRIPT_START))
echo " ⏱️  Total elapsed: $(format_elapsed $TOTAL_ELAPSED)"

INUSE_FOUND=false
while IFS='|' read -r NODE NS POD IMAGES; do
  IS_EXCLUDED=false
  for EXCL in $(echo $EXCLUDE_NODES | tr ',' ' '); do
    [ "$NODE" = "$EXCL" ] && IS_EXCLUDED=true && break
  done
  [ "$IS_EXCLUDED" = "true" ] && continue
  if [ -n "$TARGET_NODE" ] && [ "$NODE" != "$TARGET_NODE" ]; then continue; fi
  for IMG in $IMAGES; do
    IS_KEPT=false
    for FULL_IMG in $KEEP_IMAGES_FULL; do
      [ "$IMG" = "$FULL_IMG" ] && IS_KEPT=true && break
    done
    if echo "$IMG" | grep -q "$IMAGE_SHORT" && [ "$IS_KEPT" = "false" ]; then
      if [ "$INUSE_FOUND" = "false" ]; then
        echo ""
        echo " ⚠️  Images skipped because they are in use by running pods:"
        INUSE_FOUND=true
      fi
      echo "  $IMG"
      echo "    └─ node: $NODE"
      echo "    └─ pod:  $NS/$POD"
    fi
  done
done < "$IN_USE_TMPFILE"

rm -f $IN_USE_TMPFILE

echo "=========================================="
if [ -n "$NODE_TIMING" ]; then
echo " Node timing:"
printf "$NODE_TIMING\n"
echo "=========================================="
fi

# Flush log before emailing
sleep 2

if [ $((FAILED + TIMEOUT_COUNT)) -gt 0 ]; then
  echo " ⚠️  Some nodes had issues - review logs above"
  BODY_TMPFILE=$(mktemp)
  build_email_body "$LOG_FILE" "failure" > "$BODY_TMPFILE"
  send_email "❌ image-cleanup.sh FAILED | $IMAGE_SHORT | ${FAILED} failed, ${TIMEOUT_COUNT} timed out" "$BODY_TMPFILE"
else
  echo " 🎉 All nodes cleaned up successfully!"
  BODY_TMPFILE=$(mktemp)
  build_email_body "$LOG_FILE" "success" > "$BODY_TMPFILE"
  send_email "✅ image-cleanup.sh complete | $IMAGE_SHORT | ${SUCCESS} node(s) cleaned" "$BODY_TMPFILE"
fi

exit $( [ $((FAILED + TIMEOUT_COUNT)) -gt 0 ] && echo 1 || echo 0 )
