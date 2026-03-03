#!/bin/bash

NAMESPACE="kube-system"
LABEL="name=image-cleanup"
DAEMONSET_FILE="image-cleanup-ds.yaml"
POLL_INTERVAL=10        # seconds between checks
TIMEOUT=600             # max seconds to wait per pod (10 min)
DS_READY_TIMEOUT=120    # max seconds to wait for DaemonSet to be ready

# ==========================================
# Parameter handling
# ==========================================
usage() {
  echo "Usage: $0 -i <image:tag> [-e <exclude_nodes>] [-n <node>]"
  echo ""
  echo "  -i  Full image name and tag to KEEP (all other tags will be removed)"
  echo "  -e  Comma-separated list of nodes to exclude"
  echo "  -n  Target a single specific node only"
  echo ""
  echo "Examples:"
  echo "  $0 -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 -e lobot-dev.cs.queensu.ca"
  echo "  $0 -i queensschoolofcomputingdocker/gpu-jupyter-latest:13.0.2cudnn-2.20.0tf-matlab-ollama-claude-qsc-u24.04-20260302 -n newcluster-gpunode3"
  exit 1
}

EXCLUDE_NODES=""
TARGET_NODE=""

while getopts ":i:e:n:" opt; do
  case $opt in
    i) KEEP_IMAGE="$OPTARG" ;;
    e) EXCLUDE_NODES="$OPTARG" ;;
    n) TARGET_NODE="$OPTARG" ;;
    *) usage ;;
  esac
done

if [ -z "$KEEP_IMAGE" ]; then
  echo "❌ ERROR: Image name is required!"
  usage
fi

if [ -n "$TARGET_NODE" ] && [ -n "$EXCLUDE_NODES" ]; then
  echo "❌ ERROR: Cannot use -n and -e together!"
  usage
fi

# Parse image name and tag from the parameter
IMAGE_NAME=$(echo $KEEP_IMAGE | cut -d: -f1)
IMAGE_TAG=$(echo $KEEP_IMAGE | cut -d: -f2)
IMAGE_SHORT=$(basename $IMAGE_NAME)

# Full docker.io reference for exact string matching inside the container
KEEP_IMAGE_FULL="docker.io/${IMAGE_NAME}:${IMAGE_TAG}"

# Set up log file - output goes to both terminal and log file
LOG_FILE="cleanup-results-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a $LOG_FILE) 2>&1

echo "=========================================="
echo " Image Cleanup - Full Run"
echo " $(date)"
echo "=========================================="
echo " Keeping:   $KEEP_IMAGE_FULL"
echo " Removing:  Unused old tags of $IMAGE_SHORT"
echo " Log file:  $LOG_FILE"
if [ -n "$TARGET_NODE" ]; then
echo " Target:    $TARGET_NODE (single node mode)"
elif [ -n "$EXCLUDE_NODES" ]; then
echo " Excluding: $(echo $EXCLUDE_NODES | tr ',' ' ')"
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
echo " Nodes to clean:         $TOTAL_NODES"

# ==========================================
# STEP 0: Build in-use image list per node
# Format: nodename|namespace|podname|image
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

# Helper: get in-use tags of IMAGE_SHORT on a specific node
# Returns lines of format: image|namespace|podname
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

# Helper: get just the image refs (for ConfigMap encoding)
get_inuse_imagetags_for_node() {
  local NODE=$1
  get_inuse_tags_for_node $NODE | cut -d'|' -f1
}

# Print summary of in-use images per node
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
# STEP 1: Generate DaemonSet yaml
# ==========================================
echo ""
echo "=========================================="
echo " STEP 1: Generating DaemonSet with image"
echo "=========================================="

# Build ConfigMap data with in-use image refs per node
CONFIGMAP_DATA=""
for NODE in $NODES; do
  INUSE=$(get_inuse_imagetags_for_node $NODE)
  if [ -n "$INUSE" ]; then
    ENCODED=$(echo "$INUSE" | base64 -w0)
    CONFIGMAP_DATA="$CONFIGMAP_DATA
  $NODE: \"$ENCODED\""
  fi
done

# Create ConfigMap with in-use tags per node
cat <<CMEOF | kubectl apply -f - > /dev/null 2>&1
apiVersion: v1
kind: ConfigMap
metadata:
  name: image-cleanup-inuse
  namespace: kube-system
data:$CONFIGMAP_DATA
CMEOF

# Build DaemonSet yaml
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

# Add nodeAffinity - either target a single node or exclude nodes
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
elif [ -n "$EXCLUDE_NODES" ]; then
  echo "      affinity:"
  echo "        nodeAffinity:"
  echo "          requiredDuringSchedulingIgnoredDuringExecution:"
  echo "            nodeSelectorTerms:"
  echo "            - matchExpressions:"
  echo "              - key: kubernetes.io/hostname"
  echo "                operator: NotIn"
  echo "                values:"
  for EXCL in $(echo $EXCLUDE_NODES | tr ',' ' '); do
    echo "                - \"$EXCL\""
  done
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

          # The image we must always keep - full docker.io reference
          KEEP_IMAGE_FULL="${KEEP_IMAGE_FULL}"

          # Load in-use image refs from ConfigMap for this node
          INUSE_TAGS=""
          ENCODED=\$(cat /etc/image-cleanup-inuse/\$NODE_NAME 2>/dev/null)
          if [ -n "\$ENCODED" ]; then
            INUSE_TAGS=\$(echo "\$ENCODED" | base64 -d)
            echo "=== In-use tags on \$NODE_NAME (will NOT be removed) ==="
            for TAG in \$INUSE_TAGS; do
              echo "  ⚠️  \$TAG is in use by a running pod - skipping"
            done
          fi

          echo "=== Images before cleanup ==="
          nsenter --mount=/proc/1/ns/mnt -- \
            /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | grep "${IMAGE_SHORT}"

          echo "=== Removing unused old tags ==="
          nsenter --mount=/proc/1/ns/mnt -- \
            /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | \
            grep "${IMAGE_SHORT}" | \
            awk '{print \$1}' | \
            while read IMAGE_REF; do

              # Skip the image we explicitly want to keep - plain string match
              if [ "\$IMAGE_REF" = "\$KEEP_IMAGE_FULL" ]; then
                echo "  Keeping: \$IMAGE_REF"
                continue
              fi

              # Skip any images in use by running pods - plain string match
              SKIP=false
              for INUSE_TAG in \$INUSE_TAGS; do
                if [ "\$IMAGE_REF" = "\$INUSE_TAG" ]; then
                  echo "  ⚠️  \$IMAGE_REF is in use by a running pod - skipping"
                  SKIP=true
                  break
                fi
              done
              [ "\$SKIP" = "true" ] && continue

              # Get the manifest digest for this image ref so we can also
              # remove any digest refs pointing to the same content
              MANIFEST_DIGEST=\$(nsenter --mount=/proc/1/ns/mnt -- \
                /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | \
                grep "^\$IMAGE_REF " | awk '{print \$3}')

              # Remove the named tag
              echo "  Removing: \$IMAGE_REF"
              nsenter --mount=/proc/1/ns/mnt -- \
                /usr/bin/ctr --namespace k8s.io images rm "\$IMAGE_REF" 2>&1

              # Also remove any digest refs pointing to the same manifest
              # These are the sha256: refs that prevent blob GC
              if [ -n "\$MANIFEST_DIGEST" ]; then
                nsenter --mount=/proc/1/ns/mnt -- \
                  /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | \
                  grep "\$MANIFEST_DIGEST" | \
                  awk '{print \$1}' | \
                  while read DIGEST_REF; do
                    # Never remove a digest ref that belongs to the keep image
                    KEEP_DIGEST=\$(nsenter --mount=/proc/1/ns/mnt -- \
                      /usr/bin/ctr --namespace k8s.io images ls 2>/dev/null | \
                      grep "^\$KEEP_IMAGE_FULL " | awk '{print \$3}')
                    if [ "\$MANIFEST_DIGEST" = "\$KEEP_DIGEST" ]; then
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
# STEP 3: Wait for all pods to be scheduled
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

# Counters for summary
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
  echo "------------------------------------------"
  echo " Waiting for cleanup to complete..."

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
    echo "⚠️  TIMED OUT after ${TIMEOUT}s on node $NODE"
    TIMEOUT_COUNT=$((TIMEOUT_COUNT + 1))
    echo " --- Partial logs ---"
    kubectl logs -n $NAMESPACE $POD
    continue
  fi

  echo " Status: $STATUS"
  kubectl logs -n $NAMESPACE $POD

  if [ "$STATUS" = "Succeeded" ]; then
    SUCCESS=$((SUCCESS + 1))
  else
    FAILED=$((FAILED + 1))
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

# Cleanup temp file
rm -f $IN_USE_TMPFILE

# ==========================================
# SUMMARY
# ==========================================
echo ""
echo "=========================================="
echo " SUMMARY - $(date)"
echo "=========================================="
echo " Image kept:     $KEEP_IMAGE_FULL"
echo " Total nodes:    $TOTAL"
if [ -n "$TARGET_NODE" ]; then
echo " Mode:           Single node"
else
echo " ⏭️  Excluded:    $EXCLUDED_COUNT"
fi
echo " ✅ Succeeded:   $SUCCESS"
echo " ❌ Failed:      $FAILED"
echo " ⚠️  Timed out:  $TIMEOUT_COUNT"

# Report any in-use images that were skipped with pod details
INUSE_FOUND=false
while IFS='|' read -r NODE NS POD IMAGES; do
  IS_EXCLUDED=false
  for EXCL in $(echo $EXCLUDE_NODES | tr ',' ' '); do
    [ "$NODE" = "$EXCL" ] && IS_EXCLUDED=true && break
  done
  [ "$IS_EXCLUDED" = "true" ] && continue
  if [ -n "$TARGET_NODE" ] && [ "$NODE" != "$TARGET_NODE" ]; then continue; fi
  for IMG in $IMAGES; do
    if echo "$IMG" | grep -q "$IMAGE_SHORT" && [ "$IMG" != "$KEEP_IMAGE_FULL" ]; then
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
done < <(kubectl get pods --all-namespaces \
  -o jsonpath='{range .items[*]}{.spec.nodeName}{"|"}{.metadata.namespace}{"|"}{.metadata.name}{"|"}{range .status.containerStatuses[*]}{.image}{" "}{end}{"\n"}{end}')

echo "=========================================="

if [ $((FAILED + TIMEOUT_COUNT)) -gt 0 ]; then
  echo " ⚠️  Some nodes had issues - review logs above"
  exit 1
fi

echo " 🎉 All nodes cleaned up successfully!"
exit 0
