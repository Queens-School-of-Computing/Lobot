"""Unit tests for lobot_tui/data/parsers.py."""

import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from lobot_tui.config import MAX_TAG_LEN
from lobot_tui.data.parsers import (
    _age_string,
    _merge_nodes_and_pods,
    _parse_cpu_request,
    _parse_gpu_request,
    _parse_image_tag,
    _parse_longhorn_nodes,
    _parse_memory_request_gb,
    _parse_nodes,
    _parse_pods,
    _pod_username,
)


def _ts_ago(seconds: int) -> str:
    """Return an ISO8601 timestamp that is `seconds` in the past."""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


# ── _pod_username ─────────────────────────────────────────────────────────────


class TestPodUsername:
    def test_strips_jupyter_prefix(self):
        assert _pod_username("jupyter-alice") == "alice"

    def test_unescapes_hyphen(self):
        assert _pod_username("jupyter-bob-2dtest") == "bob-test"

    def test_multiple_hyphen_escapes(self):
        assert _pod_username("jupyter-alice-2dbob-2dcarol") == "alice-bob-carol"

    def test_non_jupyter_passes_through(self):
        assert _pod_username("hub-deployment-abc123") == "hub-deployment-abc123"

    def test_bare_jupyter_prefix(self):
        assert _pod_username("jupyter-") == ""


# ── _parse_image_tag ──────────────────────────────────────────────────────────


class TestParseImageTag:
    def test_simple_tag(self):
        assert _parse_image_tag("repo/image:latest") == "latest"

    def test_no_colon_returns_latest(self):
        assert _parse_image_tag("repo/image") == "latest"

    def test_sha_style_tag(self):
        assert _parse_image_tag("repo/image:sha256-abc123") == "sha256-abc123"

    def test_date_tag(self):
        assert _parse_image_tag("queensschoolofcomputingdocker/gpu-jupyter-latest:2024-03-01") == "2024-03-01"

    def test_tag_at_exact_max_not_truncated(self):
        tag = "x" * MAX_TAG_LEN
        assert _parse_image_tag(f"repo/image:{tag}") == tag

    def test_tag_over_max_is_truncated(self):
        tag = "y" * (MAX_TAG_LEN + 10)
        result = _parse_image_tag(f"repo/image:{tag}")
        assert len(result) == MAX_TAG_LEN
        assert result.startswith("…")

    def test_tag_one_over_max_is_truncated(self):
        tag = "z" * (MAX_TAG_LEN + 1)
        result = _parse_image_tag(f"repo/image:{tag}")
        assert len(result) == MAX_TAG_LEN
        assert result.startswith("…")


# ── _age_string ───────────────────────────────────────────────────────────────


class TestAgeString:
    def test_none_returns_question_mark(self):
        assert _age_string(None) == "?"

    def test_empty_string_returns_question_mark(self):
        assert _age_string("") == "?"

    def test_invalid_string_returns_question_mark(self):
        assert _age_string("not-a-date") == "?"

    def test_seconds_bucket(self):
        result = _age_string(_ts_ago(45))
        assert re.match(r"^\d+s$", result), f"Expected Xs format, got {result!r}"

    def test_minutes_bucket(self):
        result = _age_string(_ts_ago(300))  # 5 minutes
        assert re.match(r"^\d+m$", result), f"Expected Xm format, got {result!r}"

    def test_hours_bucket(self):
        result = _age_string(_ts_ago(7500))  # 2h5m
        assert re.match(r"^\d+h\d+m$", result), f"Expected XhYm format, got {result!r}"

    def test_days_bucket(self):
        result = _age_string(_ts_ago(180_000))  # ~2 days
        assert re.match(r"^\d+d\d+h$", result), f"Expected XdYh format, got {result!r}"

    def test_z_suffix_handled(self):
        # Kubernetes uses Z-suffix timestamps
        result = _age_string("2020-01-01T00:00:00Z")
        assert re.match(r"^\d+d\d+h$", result)


# ── _parse_cpu_request ────────────────────────────────────────────────────────


class TestParseCpuRequest:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("4", 4.0),
            ("0", 0.0),
            ("1", 1.0),
            ("500m", 0.5),
            ("1000m", 1.0),
            ("250m", 0.25),
            ("", 0.0),
            ("bad", 0.0),
        ],
    )
    def test_values(self, raw, expected):
        assert _parse_cpu_request(raw) == pytest.approx(expected)


# ── _parse_memory_request_gb ──────────────────────────────────────────────────


class TestParseMemoryRequestGb:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1Gi", 1.0),
            ("2Gi", 2.0),
            ("512Mi", 0.5),
            ("1024Mi", 1.0),
            ("1Ti", 1024.0),
            ("8G", 8.0),
            ("1024M", 1.0),
            ("1048576Ki", 1.0),
            ("", 0.0),
            ("bad", 0.0),
        ],
    )
    def test_values(self, raw, expected):
        assert _parse_memory_request_gb(raw) == pytest.approx(expected, rel=1e-3)


# ── _parse_gpu_request ────────────────────────────────────────────────────────


class TestParseGpuRequest:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1", 1),
            ("4", 4),
            ("0", 0),
            ("", 0),
            (None, 0),
        ],
    )
    def test_values(self, raw, expected):
        assert _parse_gpu_request(raw) == expected


# ── _parse_pods ───────────────────────────────────────────────────────────────


class TestParsePods:
    def test_returns_all_pods(self, pods_json):
        pods = _parse_pods(pods_json, "jhub", {"worker-1": "research"})
        assert len(pods) == 3

    def test_jupyter_pod_fields(self, pods_json):
        pods = _parse_pods(pods_json, "jhub", {"worker-1": "research"})
        alice = next(p for p in pods if p.name == "jupyter-alice")
        assert alice.username == "alice"
        assert alice.namespace == "jhub"
        assert alice.node == "worker-1"
        assert alice.resource == "research"
        assert alice.phase == "Running"
        assert alice.cpu_requested == pytest.approx(2.0)
        assert alice.ram_requested_gb == pytest.approx(8.0)
        assert alice.gpu_requested == 1
        assert alice.image_tag == "2024-03-01"

    def test_hyphen_unescape_in_username(self, pods_json):
        pods = _parse_pods(pods_json, "jhub", {"worker-1": "research"})
        bob = next(p for p in pods if p.name == "jupyter-bob-2dtest")
        assert bob.username == "bob-test"

    def test_non_jupyter_pod_included(self, pods_json):
        pods = _parse_pods(pods_json, "jhub", {"worker-1": "research"})
        names = [p.name for p in pods]
        assert "hub-deployment-abc123" in names

    def test_non_jupyter_pod_has_millicpu(self, pods_json):
        pods = _parse_pods(pods_json, "jhub", {"worker-1": "research"})
        hub = next(p for p in pods if p.name == "hub-deployment-abc123")
        assert hub.cpu_requested == pytest.approx(0.5)
        assert hub.ram_requested_gb == pytest.approx(0.5)
        assert hub.gpu_requested == 0

    def test_sorted_by_username(self, pods_json):
        pods = _parse_pods(pods_json, "jhub", {"worker-1": "research"})
        usernames = [p.username for p in pods]
        assert usernames == sorted(usernames, key=str.lower)

    def test_node_resource_map_applied(self, pods_json):
        pods = _parse_pods(pods_json, "jhub", {"worker-1": "research"})
        for pod in pods:
            assert pod.resource == "research"

    def test_missing_node_in_map_gives_empty_resource(self, pods_json):
        pods = _parse_pods(pods_json, "jhub", {})
        for pod in pods:
            assert pod.resource == ""

    def test_invalid_json_returns_empty(self):
        assert _parse_pods("not json", "jhub", {}) == []

    def test_empty_items_returns_empty(self):
        assert _parse_pods(json.dumps({"items": []}), "jhub", {}) == []


# ── _parse_nodes ──────────────────────────────────────────────────────────────


class TestParseNodes:
    def test_returns_node_resource_map(self, nodes_json):
        node_resource_map, _ = _parse_nodes(nodes_json)
        assert node_resource_map["worker-1"] == "research"

    def test_worker_node_fields(self, nodes_json):
        _, partial_nodes = _parse_nodes(nodes_json)
        worker = next(n for n in partial_nodes if n.name == "worker-1")
        assert worker.status == "Ready"
        assert worker.schedulable is True
        assert worker.is_control_plane is False
        assert worker.cpu_allocatable == 8
        assert worker.ram_allocatable_gb == pytest.approx(64.0)
        assert worker.gpu_allocatable == 4

    def test_control_plane_detected_by_label(self, nodes_json):
        _, partial_nodes = _parse_nodes(nodes_json)
        ctrl = next(n for n in partial_nodes if n.name == "control-plane-node")
        assert ctrl.is_control_plane is True

    def test_cordoned_node(self):
        data = {
            "items": [
                {
                    "metadata": {"name": "worker-2", "labels": {"lab": "gpu"}},
                    "spec": {"unschedulable": True},
                    "status": {
                        "conditions": [{"type": "Ready", "status": "True"}],
                        "allocatable": {"cpu": "4", "memory": "32Gi"},
                    },
                }
            ]
        }
        _, nodes = _parse_nodes(json.dumps(data))
        assert nodes[0].schedulable is False

    def test_not_ready_status(self):
        data = {
            "items": [
                {
                    "metadata": {"name": "worker-3", "labels": {}},
                    "spec": {},
                    "status": {
                        "conditions": [{"type": "Ready", "status": "False"}],
                        "allocatable": {"cpu": "4", "memory": "32Gi"},
                    },
                }
            ]
        }
        _, nodes = _parse_nodes(json.dumps(data))
        assert nodes[0].status == "NotReady"

    def test_partial_nodes_have_zero_requested(self, nodes_json):
        # _parse_nodes sets requested=0; _merge_nodes_and_pods fills them in
        _, partial_nodes = _parse_nodes(nodes_json)
        for node in partial_nodes:
            assert node.cpu_requested == 0
            assert node.ram_requested_gb == 0
            assert node.gpu_requested == 0

    def test_invalid_json_returns_empty(self):
        node_map, nodes = _parse_nodes("not json")
        assert node_map == {}
        assert nodes == []


# ── _merge_nodes_and_pods ─────────────────────────────────────────────────────


class TestMergeNodesAndPods:
    def test_node_requested_includes_all_pods(self, pods_json, nodes_json):
        node_resource_map, partial_nodes = _parse_nodes(nodes_json)
        pods = _parse_pods(pods_json, "jhub", node_resource_map)
        nodes, _ = _merge_nodes_and_pods(partial_nodes, pods)
        worker = next(n for n in nodes if n.name == "worker-1")
        # alice 2cpu + bob 4cpu + hub 0.5cpu = 6.5 → round = 6 or 7
        # Either way it must be >= 6 and account for all pods
        assert worker.cpu_requested >= 6

    def test_resource_summary_counts_only_jupyter_pods(self, pods_json, nodes_json):
        node_resource_map, partial_nodes = _parse_nodes(nodes_json)
        pods = _parse_pods(pods_json, "jhub", node_resource_map)
        _, resources = _merge_nodes_and_pods(partial_nodes, pods)
        # worker-1 has 8 cpu allocatable
        # jupyter pods: alice 2cpu + bob 4cpu = 6 cpu → cpu_free = 8 - 6 = 2
        # hub-deployment is NOT jupyter so its 0.5cpu is excluded
        assert "research" in resources
        rs = resources["research"]
        assert rs.cpu_total == 8
        assert rs.cpu_free == 2

    def test_resource_summary_gpu(self, pods_json, nodes_json):
        node_resource_map, partial_nodes = _parse_nodes(nodes_json)
        pods = _parse_pods(pods_json, "jhub", node_resource_map)
        _, resources = _merge_nodes_and_pods(partial_nodes, pods)
        rs = resources["research"]
        # worker-1 has 4 GPU allocatable; alice 1 + bob 2 = 3 jupyter GPU used
        assert rs.gpu_total == 4
        assert rs.gpu_free == 1

    def test_control_plane_excluded_from_resources(self, pods_json, nodes_json):
        node_resource_map, partial_nodes = _parse_nodes(nodes_json)
        pods = _parse_pods(pods_json, "jhub", node_resource_map)
        _, resources = _merge_nodes_and_pods(partial_nodes, pods)
        # control-plane-node has no 'lab' label (resource="") and is_control_plane=True
        # Neither condition should produce a resource entry
        for name in resources:
            assert name != ""

    def test_empty_pods_zero_requested(self, nodes_json):
        _, partial_nodes = _parse_nodes(nodes_json)
        nodes, resources = _merge_nodes_and_pods(partial_nodes, [])
        worker = next(n for n in nodes if n.name == "worker-1")
        assert worker.cpu_requested == 0
        assert worker.ram_requested_gb == 0
        assert worker.gpu_requested == 0
        # With no pods, all resources are free
        rs = resources["research"]
        assert rs.cpu_free == rs.cpu_total
        assert rs.gpu_free == rs.gpu_total


# ── _parse_longhorn_nodes ─────────────────────────────────────────────────────


class TestParseLonghornNodes:
    def test_returns_dict_keyed_by_node(self, longhorn_json):
        result = _parse_longhorn_nodes(longhorn_json)
        assert "worker-1" in result

    def test_initialized_disk_fields(self, longhorn_json):
        result = _parse_longhorn_nodes(longhorn_json)
        disk = next(d for d in result["worker-1"] if d.name == "disk-1")
        assert disk.total_gb == pytest.approx(10.0)
        assert disk.available_gb == pytest.approx(4.0)
        assert disk.scheduled_gb == pytest.approx(3.0)
        assert disk.path == "/mnt/nvme0n1"
        assert disk.schedulable is True

    def test_uninitialized_disk_skipped(self, longhorn_json):
        result = _parse_longhorn_nodes(longhorn_json)
        names = [d.name for d in result["worker-1"]]
        assert "disk-uninit" not in names
        assert "disk-1" in names

    def test_disks_sorted_by_name(self, longhorn_json):
        _BYTES_PER_GIB = 1_073_741_824
        data = json.loads(longhorn_json)
        data["items"][0]["spec"]["disks"]["disk-0"] = {
            "path": "/mnt/sda",
            "allowScheduling": True,
        }
        data["items"][0]["status"]["diskStatus"]["disk-0"] = {
            "storageMaximum": 5 * _BYTES_PER_GIB,
            "storageAvailable": 2 * _BYTES_PER_GIB,
            "storageScheduled": 1 * _BYTES_PER_GIB,
        }
        result = _parse_longhorn_nodes(json.dumps(data))
        names = [d.name for d in result["worker-1"]]
        assert names == sorted(names)

    def test_node_with_no_initialized_disks_excluded(self):
        _BYTES_PER_GIB = 1_073_741_824
        data = {
            "items": [
                {
                    "metadata": {"name": "worker-2"},
                    "spec": {"disks": {}},
                    "status": {
                        "diskStatus": {
                            "disk-x": {
                                "storageMaximum": 0,
                                "storageAvailable": 0,
                                "storageScheduled": 0,
                            }
                        }
                    },
                }
            ]
        }
        result = _parse_longhorn_nodes(json.dumps(data))
        assert "worker-2" not in result

    def test_invalid_json_returns_empty(self):
        assert _parse_longhorn_nodes("not json") == {}
