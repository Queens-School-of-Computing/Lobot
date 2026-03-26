"""Unit tests for lobot_tui/data/models.py."""

from datetime import datetime, timezone

import pytest

from lobot_tui.data.models import (
    ClusterState,
    DiskInfo,
    NodeInfo,
    PodInfo,
    ResourceSummary,
)


# ── ResourceSummary ───────────────────────────────────────────────────────────


class TestResourceSummary:
    def _make(self, **kwargs) -> ResourceSummary:
        defaults = dict(
            name="research",
            cpu_free=2,
            cpu_total=8,
            ram_free_gb=16.0,
            ram_total_gb=64.0,
            gpu_free=2,
            gpu_total=4,
            pod_count=3,
        )
        defaults.update(kwargs)
        return ResourceSummary(**defaults)

    def test_cpu_used(self):
        assert self._make(cpu_free=2, cpu_total=8).cpu_used == 6

    def test_cpu_used_all_free(self):
        assert self._make(cpu_free=8, cpu_total=8).cpu_used == 0

    def test_ram_used_gb(self):
        assert self._make(ram_free_gb=16.0, ram_total_gb=64.0).ram_used_gb == pytest.approx(48.0)

    def test_gpu_used(self):
        assert self._make(gpu_free=2, gpu_total=4).gpu_used == 2

    def test_gpu_used_all_free(self):
        assert self._make(gpu_free=4, gpu_total=4).gpu_used == 0

    def test_has_gpu_true(self):
        assert self._make(gpu_total=4).has_gpu is True

    def test_has_gpu_false_when_zero(self):
        assert self._make(gpu_total=0).has_gpu is False


# ── NodeInfo ──────────────────────────────────────────────────────────────────


class TestNodeInfo:
    def _make(self, **kwargs) -> NodeInfo:
        defaults = dict(
            name="worker-1",
            resource="research",
            status="Ready",
            schedulable=True,
            cpu_allocatable=8,
            cpu_requested=4,
            ram_allocatable_gb=64.0,
            ram_requested_gb=32.0,
            gpu_allocatable=4,
            gpu_requested=2,
            is_control_plane=False,
        )
        defaults.update(kwargs)
        return NodeInfo(**defaults)

    def test_cordoned_false_when_schedulable(self):
        assert self._make(schedulable=True).cordoned is False

    def test_cordoned_true_when_not_schedulable(self):
        assert self._make(schedulable=False).cordoned is True

    def test_cpu_free(self):
        assert self._make(cpu_allocatable=8, cpu_requested=4).cpu_free == 4

    def test_cpu_free_fully_used(self):
        assert self._make(cpu_allocatable=8, cpu_requested=8).cpu_free == 0

    def test_cpu_free_clamped_at_zero(self):
        assert self._make(cpu_allocatable=4, cpu_requested=8).cpu_free == 0

    def test_ram_free_gb(self):
        assert self._make(ram_allocatable_gb=64.0, ram_requested_gb=32.0).ram_free_gb == pytest.approx(32.0)

    def test_ram_free_gb_fully_used(self):
        assert self._make(ram_allocatable_gb=64.0, ram_requested_gb=64.0).ram_free_gb == pytest.approx(0.0)

    def test_ram_free_gb_clamped_at_zero(self):
        assert self._make(ram_allocatable_gb=16.0, ram_requested_gb=32.0).ram_free_gb == pytest.approx(0.0)

    def test_gpu_free(self):
        assert self._make(gpu_allocatable=4, gpu_requested=2).gpu_free == 2

    def test_gpu_free_fully_used(self):
        assert self._make(gpu_allocatable=4, gpu_requested=4).gpu_free == 0

    def test_gpu_free_clamped_at_zero(self):
        assert self._make(gpu_allocatable=2, gpu_requested=4).gpu_free == 0


# ── DiskInfo ──────────────────────────────────────────────────────────────────


class TestDiskInfo:
    def test_used_gb(self):
        d = DiskInfo(
            name="disk-1",
            path="/mnt/nvme",
            total_gb=10.0,
            available_gb=4.0,
            scheduled_gb=3.0,
            schedulable=True,
        )
        assert d.used_gb == pytest.approx(6.0)

    def test_used_gb_fully_available(self):
        d = DiskInfo(
            name="disk-1",
            path="/mnt/nvme",
            total_gb=10.0,
            available_gb=10.0,
            scheduled_gb=0.0,
            schedulable=True,
        )
        assert d.used_gb == pytest.approx(0.0)

    def test_used_gb_clamped_at_zero(self):
        # available_gb > total_gb shouldn't happen but must not go negative
        d = DiskInfo(
            name="disk-1",
            path="/mnt/nvme",
            total_gb=4.0,
            available_gb=10.0,
            scheduled_gb=0.0,
            schedulable=True,
        )
        assert d.used_gb == pytest.approx(0.0)


# ── ClusterState serialization ────────────────────────────────────────────────


def _make_full_state() -> ClusterState:
    rs = ResourceSummary(
        name="research",
        cpu_free=2,
        cpu_total=8,
        ram_free_gb=16.0,
        ram_total_gb=64.0,
        gpu_free=1,
        gpu_total=4,
        pod_count=2,
    )
    pod = PodInfo(
        name="jupyter-alice",
        username="alice",
        namespace="jhub",
        node="worker-1",
        resource="research",
        image="queensschoolofcomputingdocker/gpu-jupyter-latest:2024-03-01",
        image_tag="2024-03-01",
        cpu_requested=2.0,
        ram_requested_gb=8.0,
        gpu_requested=1,
        age="1h0m",
        phase="Running",
        start_time="2024-01-01T10:00:00+00:00",
    )
    node = NodeInfo(
        name="worker-1",
        resource="research",
        status="Ready",
        schedulable=True,
        cpu_allocatable=8,
        cpu_requested=2,
        ram_allocatable_gb=64.0,
        ram_requested_gb=8.0,
        gpu_allocatable=4,
        gpu_requested=1,
    )
    disk = DiskInfo(
        name="disk-1",
        path="/mnt/nvme0n1",
        total_gb=10.0,
        available_gb=4.0,
        scheduled_gb=3.0,
        schedulable=True,
    )
    return ClusterState(
        resources={"research": rs},
        pods=[pod],
        nodes=[node],
        longhorn_disks={"worker-1": [disk]},
        last_pods_update=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        last_nodes_update=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        last_longhorn_update=None,
        pods_error=None,
        nodes_error=None,
        service_error=None,
    )


class TestClusterStateSerialization:
    def test_resources_round_trip(self):
        original = _make_full_state()
        restored = ClusterState.from_dict(original.to_dict())
        rs = restored.resources["research"]
        assert rs.cpu_total == 8
        assert rs.cpu_free == 2
        assert rs.gpu_total == 4

    def test_pods_round_trip(self):
        original = _make_full_state()
        restored = ClusterState.from_dict(original.to_dict())
        assert len(restored.pods) == 1
        pod = restored.pods[0]
        assert pod.name == "jupyter-alice"
        assert pod.cpu_requested == pytest.approx(2.0)
        assert pod.gpu_requested == 1

    def test_nodes_round_trip(self):
        original = _make_full_state()
        restored = ClusterState.from_dict(original.to_dict())
        assert len(restored.nodes) == 1
        node = restored.nodes[0]
        assert node.name == "worker-1"
        assert node.cpu_allocatable == 8

    def test_longhorn_disks_round_trip(self):
        original = _make_full_state()
        restored = ClusterState.from_dict(original.to_dict())
        assert "worker-1" in restored.longhorn_disks
        disk = restored.longhorn_disks["worker-1"][0]
        assert disk.name == "disk-1"
        assert disk.total_gb == pytest.approx(10.0)

    def test_datetime_serialized_as_iso_string(self):
        d = _make_full_state().to_dict()
        assert isinstance(d["last_pods_update"], str)
        assert isinstance(d["last_nodes_update"], str)

    def test_datetime_restored_after_round_trip(self):
        original = _make_full_state()
        restored = ClusterState.from_dict(original.to_dict())
        assert isinstance(restored.last_pods_update, datetime)
        assert isinstance(restored.last_nodes_update, datetime)

    def test_none_datetime_stays_none(self):
        d = _make_full_state().to_dict()
        assert d["last_longhorn_update"] is None
        restored = ClusterState.from_dict(d)
        assert restored.last_longhorn_update is None

    def test_backward_compat_labs_key(self):
        """from_dict accepts 'labs' (old wire format) in place of 'resources'."""
        d = _make_full_state().to_dict()
        d["labs"] = d.pop("resources")
        restored = ClusterState.from_dict(d)
        assert "research" in restored.resources
        assert restored.resources["research"].cpu_total == 8

    def test_errors_preserved(self):
        state = ClusterState(
            pods_error="kubectl timeout",
            nodes_error=None,
            service_error="lobot-collector is not running",
        )
        restored = ClusterState.from_dict(state.to_dict())
        assert restored.pods_error == "kubectl timeout"
        assert restored.nodes_error is None
        assert restored.service_error == "lobot-collector is not running"

    def test_empty_state_round_trip(self):
        state = ClusterState()
        restored = ClusterState.from_dict(state.to_dict())
        assert restored.resources == {}
        assert restored.pods == []
        assert restored.nodes == []
        assert restored.longhorn_disks == {}
