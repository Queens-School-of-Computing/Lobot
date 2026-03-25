#!/bin/bash
# lv-manage.sh — Display information about a Longhorn persistent volume, and
#                optionally expand it.
#
# Usage:
#   lv-manage.sh <pv-name|pvc-name|pod-name> [namespace] [--expand SIZE]
#
# SIZE format: number followed by M, G, or T  (MiB / GiB / TiB)
#   e.g.  --expand 100G   --expand 500M   --expand 2T
#
# Accepts a PV name (cluster-scoped), PVC name, or pod name. Resolution order:
#   PV → PVC → Pod
# If a PVC or pod name is given without a namespace, all namespaces are searched.
# If a pod has multiple PVCs, info is shown for each; expansion is not allowed
# when a pod is used as the input (specify the PVC directly instead).
#
# Expansion is blocked if the requested size would push the Worst-Case Headroom
# (Disk Total − 2 × Disk Scheduled) below zero on any replica.
#
# Requires: kubectl, jq

set -euo pipefail

# ==========================================
# Helpers
# ==========================================

RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

header() {
  echo ""
  echo -e "${BOLD}${CYAN}=== $1 ===${RESET}"
}

divider() {
  echo ""
  echo -e "${DIM}────────────────────────────────────────────────────────────────${RESET}"
}

field() {
  printf "  %-22s %s\n" "$1:" "$2"
}

die() {
  echo -e "${RED}Error: $1${RESET}" >&2
  exit 1
}

# Converts bytes to human-readable string. Handles negative values.
bytes_to_human() {
  local bytes="$1"
  if [ -z "$bytes" ] || [ "$bytes" = "null" ]; then
    echo "unknown"
    return
  fi
  awk -v b="$bytes" 'BEGIN {
    split("B KiB MiB GiB TiB", s, " ")
    sign = (b < 0) ? "-" : ""
    v = (b < 0) ? -b : b+0
    i = 1
    while (v >= 1024 && i < 5) { v /= 1024; i++ }
    printf "%s%.2f %s\n", sign, v, s[i]
  }'
}

# Parses a size string (e.g. "50G", "200M", "1T") to bytes using awk
# to avoid bash integer overflow on large values.
parse_size_to_bytes() {
  local input="${1^^}"   # uppercase
  local num unit
  num=$(echo "$input" | sed 's/[MGT]$//')
  unit=$(echo "$input" | sed 's/^[0-9]*//')
  case "$unit" in
    M) awk -v n="$num" 'BEGIN { printf "%.0f\n", n * 1024 * 1024 }' ;;
    G) awk -v n="$num" 'BEGIN { printf "%.0f\n", n * 1024 * 1024 * 1024 }' ;;
    T) awk -v n="$num" 'BEGIN { printf "%.0f\n", n * 1024 * 1024 * 1024 * 1024 }' ;;
    *) die "Invalid size unit '$unit'. Use M, G, or T." ;;
  esac
}

# Converts a size string to a Kubernetes quantity (e.g. "50G" → "50Gi")
size_to_k8s() {
  local input="${1^^}"
  local num unit
  num=$(echo "$input" | sed 's/[MGT]$//')
  unit=$(echo "$input" | sed 's/^[0-9]*//')
  case "$unit" in
    M) echo "${num}Mi" ;;
    G) echo "${num}Gi" ;;
    T) echo "${num}Ti" ;;
  esac
}

# ==========================================
# Display function for a single volume
# Args: PV_NAME  PVC_NAME  PVC_NAMESPACE
# PVC_NAME and PVC_NAMESPACE may be empty if input was a bare PV with no claim.
# ==========================================

show_volume_info() {
  local PV_NAME="$1"
  local PVC_NAME="$2"
  local PVC_NAMESPACE="$3"

  local PV_JSON PVC_JSON LH_VOLUME LH_VOL_JSON REPLICAS_JSON

  PV_JSON=$(kubectl get pv "$PV_NAME" -o json 2>/dev/null || true)
  if [ -z "$PV_JSON" ] || ! echo "$PV_JSON" | jq -e '.metadata.name' &>/dev/null; then
    echo -e "  ${RED}PV '$PV_NAME' not found.${RESET}"
    return
  fi

  # Longhorn volume name = CSI volumeHandle (falls back to PV name)
  LH_VOLUME=$(echo "$PV_JSON" | jq -r '.spec.csi.volumeHandle // .metadata.name')

  # ------------------------------------------
  # PVC section
  # ------------------------------------------
  header "PVC Information"
  if [ -n "$PVC_NAME" ] && [ -n "$PVC_NAMESPACE" ]; then
    PVC_JSON=$(kubectl get pvc "$PVC_NAME" -n "$PVC_NAMESPACE" -o json 2>/dev/null || true)
    if [ -n "$PVC_JSON" ] && echo "$PVC_JSON" | jq -e '.metadata.name' &>/dev/null; then
      field "Name"          "$PVC_NAME"
      field "Namespace"     "$PVC_NAMESPACE"
      field "Status"        "$(echo "$PVC_JSON" | jq -r '.status.phase                    // "unknown"')"
      field "Requested"     "$(echo "$PVC_JSON" | jq -r '.spec.resources.requests.storage // "unknown"')"
      field "Capacity"      "$(echo "$PVC_JSON" | jq -r '.status.capacity.storage         // "unknown"')"
      field "Storage Class" "$(echo "$PVC_JSON" | jq -r '.spec.storageClassName           // "unknown"')"
      field "Access Mode"   "$(echo "$PVC_JSON" | jq -r '.spec.accessModes[0]            // "unknown"')"
    else
      echo "  (PVC '$PVC_NAME' not found in namespace '$PVC_NAMESPACE')"
    fi
  else
    echo "  (no PVC bound to this PV)"
  fi

  # ------------------------------------------
  # PV section
  # ------------------------------------------
  header "PV Information"
  field "Name"           "$PV_NAME"
  field "Capacity"       "$(echo "$PV_JSON" | jq -r '.spec.capacity.storage                  // "unknown"')"
  field "Status"         "$(echo "$PV_JSON" | jq -r '.status.phase                           // "unknown"')"
  field "Reclaim Policy" "$(echo "$PV_JSON" | jq -r '.spec.persistentVolumeReclaimPolicy     // "unknown"')"
  field "Storage Class"  "$(echo "$PV_JSON" | jq -r '.spec.storageClassName                  // "unknown"')"
  field "CSI Driver"     "$(echo "$PV_JSON" | jq -r '.spec.csi.driver                        // "unknown"')"

  # ------------------------------------------
  # Longhorn volume section
  # ------------------------------------------
  header "Longhorn Volume"
  LH_VOL_JSON=$(kubectl get volumes.longhorn.io "$LH_VOLUME" -n longhorn-system -o json 2>/dev/null || true)

  if [ -z "$LH_VOL_JSON" ] || ! echo "$LH_VOL_JSON" | jq -e '.metadata.name' &>/dev/null; then
    echo "  (Longhorn volume '$LH_VOLUME' not found — may not be a Longhorn-backed PV)"
    return
  fi

  local lh_size lh_actual_size
  lh_size=$(echo "$LH_VOL_JSON"        | jq -r '.spec.size         // ""')
  lh_actual_size=$(echo "$LH_VOL_JSON" | jq -r '.status.actualSize // ""')

  field "Volume Name"  "$LH_VOLUME"
  field "State"        "$(echo "$LH_VOL_JSON" | jq -r '.status.state          // "unknown"')"
  field "Robustness"   "$(echo "$LH_VOL_JSON" | jq -r '.status.robustness     // "unknown"')"
  field "Size"         "$(bytes_to_human "$lh_size") ($lh_size bytes)"
  if [ -n "$lh_actual_size" ] && [ "$lh_actual_size" != "0" ]; then
    field "Actual Used"  "$(bytes_to_human "$lh_actual_size")"
  fi
  field "Frontend"     "$(echo "$LH_VOL_JSON" | jq -r '.spec.frontend         // "unknown"')"
  field "Replicas"     "$(echo "$LH_VOL_JSON" | jq -r '.spec.numberOfReplicas // "unknown"')"
  field "Current Node" "$(echo "$LH_VOL_JSON" | jq -r '.status.currentNodeID  // "unattached"')"
  field "Migratable"   "$(echo "$LH_VOL_JSON" | jq -r '.spec.migratable       // "false"')"

  # ------------------------------------------
  # Snapshot section
  # ------------------------------------------
  header "Snapshots"
  local SNAPSHOTS_JSON snap_count snap_total_bytes
  SNAPSHOTS_JSON=$(kubectl get snapshots.longhorn.io -n longhorn-system \
    -l "longhornvolume=$LH_VOLUME" -o json 2>/dev/null || true)
  snap_count=$(echo "$SNAPSHOTS_JSON" | jq '.items | length')
  # Only count snapshots still on disk (readyToUse: true).
  # readyToUse: false = purged from disk, CRD kept as a backup target reference.
  snap_total_bytes=$(echo "$SNAPSHOTS_JSON" \
    | jq '[.items[] | select(.status.readyToUse == true) | .status.size // "0" | tonumber] | add // 0')

  if [ "$snap_count" -eq 0 ]; then
    echo "  (no snapshots found)"
  else
    printf "  %-52s %-26s %-18s %s\n" "NAME" "CREATED" "STATUS" "SIZE"
    printf "  %-52s %-26s %-18s %s\n" "----" "-------" "------" "----"
    echo "$SNAPSHOTS_JSON" | jq -c '.items[]' | while read -r snap; do
      ready=$(echo "$snap" | jq -r '.status.readyToUse // false')
      if [ "$ready" = "true" ]; then
        status="active"
      else
        status="removed (backup ref)"
      fi
      printf "  %-52s %-26s %-18s %s\n" \
        "$(echo "$snap" | jq -r '.metadata.name')" \
        "$(echo "$snap" | jq -r '.status.creationTime // "unknown"')" \
        "$status" \
        "$(bytes_to_human "$(echo "$snap" | jq -r '.status.size // "0"')")"
    done
    echo ""
    field "  On-Disk Snapshot Usage" "$(bytes_to_human "$snap_total_bytes")"
  fi

  # ------------------------------------------
  # Replica section
  # ------------------------------------------
  header "Replicas"
  local REPLICAS_JSON replica_count
  REPLICAS_JSON=$(kubectl get replicas.longhorn.io -n longhorn-system \
    -l "longhornvolume=$LH_VOLUME" -o json 2>/dev/null || true)
  replica_count=$(echo "$REPLICAS_JSON" | jq '.items | length')

  if [ "$replica_count" -eq 0 ]; then
    echo "  (no replicas found)"
  else
    local idx=0
    echo "$REPLICAS_JSON" | jq -c '.items[]' | while read -r replica; do
      idx=$((idx + 1))
      local r_node r_disk_path r_state r_size
      r_node=$(echo "$replica"      | jq -r '.spec.nodeID         // "unknown"')
      r_disk_path=$(echo "$replica" | jq -r '.spec.diskPath       // "unknown"')
      r_state=$(echo "$replica"     | jq -r '.status.currentState // "unknown"')
      r_size=$(echo "$replica"      | jq -r '.spec.volumeSize     // ""')

      echo ""
      printf "  ${BOLD}Replica %d${RESET}  —  %s\n" "$idx" "$r_node"
      field "  Disk Path"    "$r_disk_path"
      field "  State"        "$r_state"
      field "  Replica Size" "$(bytes_to_human "$r_size")"

      # Disk capacity: status.diskStatus is keyed by disk name, not replica diskID UUID.
      # Match by disk path via spec.disks on the Longhorn node object.
      if [ -n "$r_disk_path" ] && [ "$r_node" != "unknown" ]; then
        local node_json disk_name disk_json
        node_json=$(kubectl get nodes.longhorn.io "$r_node" -n longhorn-system \
          -o json 2>/dev/null || true)
        if [ -n "$node_json" ] && echo "$node_json" | jq -e '.metadata.name' &>/dev/null; then
          disk_name=$(echo "$node_json" \
            | jq -r --arg path "$r_disk_path" \
              '.spec.disks | to_entries[] | select(.value.path == $path) | .key' \
            | head -1)
          if [ -n "$disk_name" ]; then
            disk_json=$(echo "$node_json" \
              | jq --arg name "$disk_name" '.status.diskStatus[$name] // empty')
          fi
          if [ -n "${disk_json:-}" ]; then
            local d_max d_avail d_scheduled
            d_max=$(echo "$disk_json"       | jq -r '.storageMaximum   // ""')
            d_avail=$(echo "$disk_json"     | jq -r '.storageAvailable // ""')
            d_scheduled=$(echo "$disk_json" | jq -r '.storageScheduled // ""')
            field "  Disk Total"     "$(bytes_to_human "$d_max")"
            field "  Disk Available" "$(bytes_to_human "$d_avail")"
            field "  Disk Scheduled" "$(bytes_to_human "$d_scheduled")"
            echo ""

            # Backup reserve for this volume: use actualSize (already written data)
            # as the estimate for the next snapshot, falling back to provisioned size.
            local this_reserve
            if [ -n "$lh_actual_size" ] && [ "$lh_actual_size" != "0" ]; then
              this_reserve="$lh_actual_size"
            else
              this_reserve="$lh_size"
            fi

            # Backup reserve for other volumes on this disk: sum their actualSize.
            local other_vols other_backup_reserve other_vol other_actual
            other_vols=$(kubectl get replicas.longhorn.io -n longhorn-system -o json \
              | jq -r --arg node "$r_node" --arg disk "$r_disk_path" \
                       --arg vol "$LH_VOLUME" \
                '[.items[] | select(
                    .spec.nodeID   == $node and
                    .spec.diskPath == $disk and
                    .metadata.labels.longhornvolume != $vol
                  ) | .metadata.labels.longhornvolume] | unique[]' 2>/dev/null || true)

            other_backup_reserve=0
            for other_vol in $other_vols; do
              other_actual=$(kubectl get volumes.longhorn.io "$other_vol" \
                -n longhorn-system \
                -o jsonpath='{.status.actualSize}' 2>/dev/null || echo "0")
              [ -z "$other_actual" ] && other_actual=0
              other_backup_reserve=$((other_backup_reserve + other_actual))
            done

            awk -v avail="$d_avail" -v total="$d_max" \
                -v scheduled="$d_scheduled" -v vol="$lh_size" \
                -v this_res="$this_reserve" -v other_res="$other_backup_reserve" \
            'function human(b,    s,i,v) {
               split("B KiB MiB GiB TiB", s, " ")
               sign = (b < 0) ? "-" : ""
               v = (b < 0) ? -b : b+0; i = 1
               while (v >= 1024 && i < 5) { v /= 1024; i++ }
               return sprintf("%s%.2f %s", sign, v, s[i])
             }
             function flag(v) { return (v < 0 ? "  *** INSUFFICIENT ***" : "") }
             BEGIN {
               other_sched = scheduled - vol
               headroom    = avail - other_sched
               safe        = avail - other_sched - this_res - other_res
               worst_case  = total - (2 * scheduled)
               printf "  %-28s %s\n",   "  Other Vol. Scheduled:",    human(other_sched)
               printf "  %-28s %s\n",   "  Expansion Headroom:",      human(headroom)
               printf "  %-28s %s  (this volume, actual usage)\n",  \
                 "  Backup Reserve (this):",   human(this_res)
               printf "  %-28s %s  (other volumes, actual usage)\n", \
                 "  Backup Reserve (others):", human(other_res)
               printf "  %-28s %s%s\n", "  Safe Headroom:",           human(safe), flag(safe)
               printf "\n"
               printf "  %-28s %s%s\n", "  Worst-Case Headroom:",     human(worst_case), flag(worst_case)
               printf "  %s\n", "  (all volumes 100% full + one full backup snapshot each)"
             }'
          else
            field "  Disk Capacity" "(disk not found on node for path '$r_disk_path')"
          fi
        else
          field "  Disk Capacity" "(node '$r_node' not found in Longhorn)"
        fi
      else
        field "  Disk Capacity" "(disk path unavailable)"
      fi
    done
  fi
}

# ==========================================
# Expansion feasibility check
# Prints a plan and returns 1 if any replica would go negative.
# Args: LH_VOLUME  CURRENT_BYTES  NEW_BYTES
# ==========================================

check_expansion() {
  local LH_VOLUME="$1"
  local current_bytes="$2"
  local new_bytes="$3"
  local delta_bytes
  delta_bytes=$(awk -v n="$new_bytes" -v c="$current_bytes" 'BEGIN { printf "%.0f\n", n - c }')

  local REPLICAS_JSON all_ok=true
  REPLICAS_JSON=$(kubectl get replicas.longhorn.io -n longhorn-system \
    -l "longhornvolume=$LH_VOLUME" -o json 2>/dev/null || true)

  local idx=0
  while IFS= read -r replica; do
    idx=$((idx + 1))
    local r_node r_disk_path
    r_node=$(echo "$replica"      | jq -r '.spec.nodeID   // "unknown"')
    r_disk_path=$(echo "$replica" | jq -r '.spec.diskPath // "unknown"')

    local node_json disk_name disk_json d_max d_scheduled
    node_json=$(kubectl get nodes.longhorn.io "$r_node" -n longhorn-system \
      -o json 2>/dev/null || true)
    disk_name=$(echo "$node_json" \
      | jq -r --arg path "$r_disk_path" \
        '.spec.disks | to_entries[] | select(.value.path == $path) | .key' \
      | head -1)
    disk_json=$(echo "$node_json" \
      | jq --arg name "$disk_name" '.status.diskStatus[$name] // empty' 2>/dev/null || true)

    if [ -z "${disk_json:-}" ]; then
      echo -e "  ${RED}Replica $idx ($r_node): could not read disk stats — skipping check.${RESET}"
      continue
    fi

    d_max=$(echo "$disk_json"       | jq -r '.storageMaximum   // "0"')
    d_scheduled=$(echo "$disk_json" | jq -r '.storageScheduled // "0"')

    # Worst-case headroom after expansion:
    #   current:  d_max - 2 * d_scheduled
    #   expanded: d_max - 2 * (d_scheduled + delta)
    local result
    result=$(awk -v max="$d_max" -v sched="$d_scheduled" -v delta="$delta_bytes" \
      -v node="$r_node" -v disk="$r_disk_path" \
    'function human(b,    s,i,v) {
       split("B KiB MiB GiB TiB", s, " ")
       sign = (b < 0) ? "-" : ""
       v = (b < 0) ? -b : b+0; i = 1
       while (v >= 1024 && i < 5) { v /= 1024; i++ }
       return sprintf("%s%.2f %s", sign, v, s[i])
     }
     BEGIN {
       cur  = max - 2 * sched
       post = max - 2 * (sched + delta)
       ok   = (post >= 0) ? "OK" : "FAIL"
       printf "%s|%s|%s|%s\n", human(cur), human(post), ok, node
     }')

    local cur_h post_h ok_flag r_name
    cur_h=$(echo "$result"  | cut -d'|' -f1)
    post_h=$(echo "$result" | cut -d'|' -f2)
    ok_flag=$(echo "$result" | cut -d'|' -f3)
    r_name=$(echo "$result" | cut -d'|' -f4)

    printf "  Replica %-2s  —  %s (%s)\n" "$idx" "$r_name" "$r_disk_path"
    printf "    %-32s %s\n" "Current Worst-Case Headroom:" "$cur_h"
    if [ "$ok_flag" = "FAIL" ]; then
      printf "    %-32s %s  ${RED}*** WOULD EXCEED CAPACITY ***${RESET}\n" \
        "New Worst-Case Headroom:" "$post_h"
      all_ok=false
    else
      printf "    %-32s %s\n" "New Worst-Case Headroom:" "$post_h"
    fi
    echo ""
  done < <(echo "$REPLICAS_JSON" | jq -c '.items[]')

  [ "$all_ok" = "true" ]
}

# ==========================================
# Argument parsing
# ==========================================

INPUT=""
GIVEN_NAMESPACE=""
EXPAND_SIZE=""
AUTO_YES=false

while [ $# -gt 0 ]; do
  case "$1" in
    --expand)
      shift
      # Size is optional here: omitting it shows info then exits, letting the
      # caller (e.g. lobot-tui) supply the size separately via --yes.
      if [ $# -gt 0 ] && [[ "${1^^}" =~ ^[0-9]+[MGT]$ ]]; then
        EXPAND_SIZE="${1^^}"
      elif [ $# -gt 0 ] && [ "${1:0:2}" != "--" ]; then
        die "Invalid size '$1'. Use a number followed by M, G, or T (e.g. 100G, 500M, 2T)."
      fi
      ;;
    --yes)
      AUTO_YES=true
      ;;
    *)
      if [ -z "$INPUT" ]; then
        INPUT="$1"
      elif [ -z "$GIVEN_NAMESPACE" ]; then
        GIVEN_NAMESPACE="$1"
      else
        die "Unexpected argument '$1'."
      fi
      ;;
  esac
  shift
done

if [ -z "$INPUT" ]; then
  echo "Usage: $0 <pv-name|pvc-name|pod-name> [namespace] [--expand SIZE] [--yes]"
  echo "  SIZE: number + M, G, or T  (e.g. 100G, 500M, 2T)"
  echo "  --yes: skip confirmation prompt (for scripted use)"
  exit 1
fi

# ==========================================
# Resolve input: PV → PVC → Pod
# Sets: RESOLVED_PV, RESOLVED_PVC, RESOLVED_NS (may be empty for bare PV)
# ==========================================

RESOLVED_PV=""
RESOLVED_PVC=""
RESOLVED_NS=""
IS_POD=false

# --- Try as PV ---
PV_JSON=$(kubectl get pv "$INPUT" -o json 2>/dev/null || true)
if [ -n "$PV_JSON" ] && echo "$PV_JSON" | jq -e '.metadata.name' &>/dev/null; then
  RESOLVED_PV="$INPUT"
  RESOLVED_PVC=$(echo "$PV_JSON" | jq -r '.spec.claimRef.name      // ""')
  RESOLVED_NS=$(echo "$PV_JSON"  | jq -r '.spec.claimRef.namespace // ""')
fi

# --- Try as PVC ---
if [ -z "$RESOLVED_PV" ]; then
  if [ -n "$GIVEN_NAMESPACE" ]; then
    PVC_JSON=$(kubectl get pvc "$INPUT" -n "$GIVEN_NAMESPACE" -o json 2>/dev/null || true)
    RESOLVED_NS="$GIVEN_NAMESPACE"
  else
    PVC_JSON=$(kubectl get pvc -A -o json 2>/dev/null \
      | jq --arg n "$INPUT" '.items[] | select(.metadata.name == $n)' || true)
    RESOLVED_NS=$(echo "$PVC_JSON" | jq -r '.metadata.namespace // ""')
  fi
  if [ -n "$PVC_JSON" ] && echo "$PVC_JSON" | jq -e '.metadata.name' &>/dev/null; then
    RESOLVED_PV=$(echo "$PVC_JSON" | jq -r '.spec.volumeName // ""')
    [ -z "$RESOLVED_PV" ] && die "PVC '$INPUT' is not yet bound to a PV."
    RESOLVED_PVC="$INPUT"
  fi
fi

# --- Try as Pod ---
if [ -z "$RESOLVED_PV" ]; then
  IS_POD=true
  if [ -n "$GIVEN_NAMESPACE" ]; then
    POD_JSON=$(kubectl get pod "$INPUT" -n "$GIVEN_NAMESPACE" -o json 2>/dev/null || true)
    POD_NAMESPACE="$GIVEN_NAMESPACE"
  else
    POD_JSON=$(kubectl get pods -A -o json 2>/dev/null \
      | jq --arg n "$INPUT" '.items[] | select(.metadata.name == $n)' || true)
    POD_NAMESPACE=$(echo "$POD_JSON" | jq -r '.metadata.namespace // ""')
  fi

  if [ -z "$POD_JSON" ] || ! echo "$POD_JSON" | jq -e '.metadata.name' &>/dev/null; then
    die "'$INPUT' not found as a PV, PVC, or Pod."
  fi

  mapfile -t PVC_NAMES < <(echo "$POD_JSON" \
    | jq -r '.spec.volumes[]?.persistentVolumeClaim.claimName // empty')

  if [ ${#PVC_NAMES[@]} -eq 0 ]; then
    die "Pod '$INPUT' has no PersistentVolumeClaims attached."
  fi

  if [ -n "$EXPAND_SIZE" ] && [ ${#PVC_NAMES[@]} -gt 1 ]; then
    die "Pod '$INPUT' has ${#PVC_NAMES[@]} PVCs. Specify the PVC name directly for expansion."
  fi
fi

# ==========================================
# Display info
# ==========================================

if [ "$IS_POD" = "true" ]; then
  echo -e "${BOLD}Pod:${RESET} $INPUT  ${DIM}(namespace: $POD_NAMESPACE)${RESET}"
  echo -e "${BOLD}PVCs attached:${RESET} ${#PVC_NAMES[@]}"

  FIRST=true
  for PVC_NAME in "${PVC_NAMES[@]}"; do
    [ "$FIRST" = "true" ] && FIRST=false || divider
    echo ""
    echo -e "${BOLD}Volume: $PVC_NAME${RESET}"

    PVC_JSON=$(kubectl get pvc "$PVC_NAME" -n "$POD_NAMESPACE" -o json 2>/dev/null || true)
    if [ -z "$PVC_JSON" ] || ! echo "$PVC_JSON" | jq -e '.metadata.name' &>/dev/null; then
      echo "  (PVC '$PVC_NAME' not found in namespace '$POD_NAMESPACE')"
      continue
    fi
    PV_NAME=$(echo "$PVC_JSON" | jq -r '.spec.volumeName // ""')
    if [ -z "$PV_NAME" ]; then
      echo "  (PVC '$PVC_NAME' is not yet bound to a PV)"
      continue
    fi
    show_volume_info "$PV_NAME" "$PVC_NAME" "$POD_NAMESPACE"

    # Single-PVC pod + --expand: capture for expansion below
    if [ -n "$EXPAND_SIZE" ]; then
      RESOLVED_PV="$PV_NAME"
      RESOLVED_PVC="$PVC_NAME"
      RESOLVED_NS="$POD_NAMESPACE"
    fi
  done
  echo ""
else
  show_volume_info "$RESOLVED_PV" "$RESOLVED_PVC" "$RESOLVED_NS"
  echo ""
fi

# ==========================================
# Expansion
# ==========================================

[ -z "$EXPAND_SIZE" ] && exit 0

if [ -z "$RESOLVED_PVC" ] || [ -z "$RESOLVED_NS" ]; then
  die "Expansion requires a PVC. Cannot expand a bare PV directly."
fi

# Get current volume size in bytes from Longhorn
LH_VOLUME=$(kubectl get pv "$RESOLVED_PV" \
  -o jsonpath='{.spec.csi.volumeHandle}' 2>/dev/null \
  || echo "$RESOLVED_PV")
CURRENT_BYTES=$(kubectl get volumes.longhorn.io "$LH_VOLUME" \
  -n longhorn-system -o jsonpath='{.spec.size}' 2>/dev/null || echo "0")
NEW_BYTES=$(parse_size_to_bytes "$EXPAND_SIZE")
K8S_SIZE=$(size_to_k8s "$EXPAND_SIZE")

# Must be an increase
DELTA=$(awk -v n="$NEW_BYTES" -v c="$CURRENT_BYTES" 'BEGIN { printf "%.0f\n", n - c }')
if [ "$DELTA" -le 0 ]; then
  die "New size ($EXPAND_SIZE = $(bytes_to_human "$NEW_BYTES")) must be larger than current size ($(bytes_to_human "$CURRENT_BYTES"))."
fi

header "Expansion Plan"
field "PVC"            "$RESOLVED_PVC  (namespace: $RESOLVED_NS)"
field "Current Size"   "$(bytes_to_human "$CURRENT_BYTES")"
field "Requested Size" "$(bytes_to_human "$NEW_BYTES")  ($EXPAND_SIZE)"
field "Delta"          "$(bytes_to_human "$DELTA")"
echo ""

if ! check_expansion "$LH_VOLUME" "$CURRENT_BYTES" "$NEW_BYTES"; then
  echo -e "${RED}Expansion blocked: worst-case headroom would go negative on one or more replicas.${RESET}"
  echo "  Migrate a volume off this disk to free space, then retry."
  exit 1
fi

# Confirm
if [ "$AUTO_YES" = "true" ]; then
  echo "Auto-confirmed (--yes)."
else
  printf "Expand '%s' from %s to %s? [y/N]: " \
    "$RESOLVED_PVC" "$(bytes_to_human "$CURRENT_BYTES")" "$(bytes_to_human "$NEW_BYTES")"
  read -r CONFIRM < /dev/tty
  if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Expansion cancelled."
    exit 0
  fi
fi

echo ""
kubectl patch pvc "$RESOLVED_PVC" -n "$RESOLVED_NS" \
  -p "{\"spec\":{\"resources\":{\"requests\":{\"storage\":\"$K8S_SIZE\"}}}}"

echo ""
echo "Waiting for expansion to complete..."
while true; do
  current_bytes=$(kubectl get volumes.longhorn.io "$LH_VOLUME" \
    -n longhorn-system -o jsonpath='{.spec.size}' 2>/dev/null || echo "0")
  if [ "$current_bytes" = "$NEW_BYTES" ]; then
    echo "  Done. Volume is now $(bytes_to_human "$current_bytes")."
    break
  fi
  echo "  Volume size: $(bytes_to_human "$current_bytes") — waiting..."
  sleep 2
done
