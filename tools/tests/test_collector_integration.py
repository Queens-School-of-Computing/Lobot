"""Integration tests for the lobot-collector HTTP service.

These tests require lobot-collector to be running on 127.0.0.1:9095.
They are skipped automatically if the service is not reachable.

Run with:  /opt/Lobot/tools/run-tests.sh -v tests/test_collector_integration.py
"""

import http.client
import json
import socket

import pytest

from lobot_tui.data.models import ClusterState

_HOST = "127.0.0.1"
_PORT = 9095


def _service_reachable() -> bool:
    try:
        s = socket.create_connection((_HOST, _PORT), timeout=2)
        s.close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _service_reachable(),
    reason="lobot-collector is not running on 127.0.0.1:9095",
)


def _get(path: str, timeout: int = 5) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection(_HOST, _PORT, timeout=timeout)
    conn.request("GET", path, headers={"Connection": "close"})
    return conn.getresponse()


# ── /api/state ────────────────────────────────────────────────────────────────


class TestApiState:
    def test_returns_200(self):
        resp = _get("/api/state")
        assert resp.status == 200

    def test_content_type_is_json(self):
        resp = _get("/api/state")
        ct = resp.getheader("Content-Type", "")
        assert "application/json" in ct

    def test_body_is_valid_json(self):
        resp = _get("/api/state")
        body = resp.read()
        data = json.loads(body)
        assert isinstance(data, dict)

    def test_deserializes_to_cluster_state(self):
        resp = _get("/api/state")
        data = json.loads(resp.read())
        state = ClusterState.from_dict(data)
        assert isinstance(state, ClusterState)

    def test_top_level_keys_present(self):
        resp = _get("/api/state")
        data = json.loads(resp.read())
        for key in ("resources", "pods", "nodes", "longhorn_disks"):
            assert key in data, f"Missing key: {key}"

    def test_resources_is_dict(self):
        resp = _get("/api/state")
        state = ClusterState.from_dict(json.loads(resp.read()))
        assert isinstance(state.resources, dict)

    def test_pods_is_list(self):
        resp = _get("/api/state")
        state = ClusterState.from_dict(json.loads(resp.read()))
        assert isinstance(state.pods, list)

    def test_nodes_is_list(self):
        resp = _get("/api/state")
        state = ClusterState.from_dict(json.loads(resp.read()))
        assert isinstance(state.nodes, list)

    def test_nodes_have_expected_fields(self):
        resp = _get("/api/state")
        state = ClusterState.from_dict(json.loads(resp.read()))
        for node in state.nodes:
            assert node.name, "Node has no name"
            assert node.status in ("Ready", "NotReady", "Unknown"), f"Unexpected status: {node.status}"
            assert node.cpu_allocatable >= 0
            assert node.ram_allocatable_gb >= 0

    def test_pods_have_expected_fields(self):
        resp = _get("/api/state")
        state = ClusterState.from_dict(json.loads(resp.read()))
        for pod in state.pods:
            assert pod.name, "Pod has no name"
            assert pod.namespace, "Pod has no namespace"
            assert pod.phase in ("Running", "Pending", "Failed", "Succeeded", "Unknown"), (
                f"Unexpected phase: {pod.phase}"
            )

    def test_no_service_error(self):
        resp = _get("/api/state")
        state = ClusterState.from_dict(json.loads(resp.read()))
        assert state.service_error is None, f"Unexpected service_error: {state.service_error}"

    def test_repeated_calls_are_consistent(self):
        # Two rapid calls should return the same resource group names
        state1 = ClusterState.from_dict(json.loads(_get("/api/state").read()))
        state2 = ClusterState.from_dict(json.loads(_get("/api/state").read()))
        assert set(state1.resources.keys()) == set(state2.resources.keys())
        assert {n.name for n in state1.nodes} == {n.name for n in state2.nodes}


# ── /api/events ───────────────────────────────────────────────────────────────


class TestApiEvents:
    def _read_first_sse_event(self) -> str:
        """Connect to /api/events and return the JSON payload of the first event."""
        conn = http.client.HTTPConnection(_HOST, _PORT, timeout=10)
        conn.request("GET", "/api/events", headers={"Connection": "close"})
        resp = conn.getresponse()
        assert resp.status == 200

        # Read lines until we get a data: line followed by a blank line
        buf = b""
        while True:
            chunk = resp.read(1)
            if not chunk:
                break
            buf += chunk
            if b"\n\n" in buf:
                break

        conn.close()
        lines = buf.decode(errors="replace").splitlines()
        for line in lines:
            if line.startswith("data: "):
                return line[len("data: "):]
        raise AssertionError(f"No data: line found in SSE response. Got: {buf!r}")

    def test_returns_200(self):
        conn = http.client.HTTPConnection(_HOST, _PORT, timeout=10)
        conn.request("GET", "/api/events", headers={"Connection": "close"})
        resp = conn.getresponse()
        assert resp.status == 200
        conn.close()

    def test_content_type_is_event_stream(self):
        conn = http.client.HTTPConnection(_HOST, _PORT, timeout=10)
        conn.request("GET", "/api/events", headers={"Connection": "close"})
        resp = conn.getresponse()
        ct = resp.getheader("Content-Type", "")
        assert "text/event-stream" in ct
        conn.close()

    def test_first_event_is_valid_json(self):
        payload = self._read_first_sse_event()
        data = json.loads(payload)
        assert isinstance(data, dict)

    def test_first_event_deserializes_to_cluster_state(self):
        payload = self._read_first_sse_event()
        state = ClusterState.from_dict(json.loads(payload))
        assert isinstance(state, ClusterState)

    def test_first_event_matches_state_endpoint(self):
        # /api/events first event should contain the same nodes as /api/state
        sse_state = ClusterState.from_dict(json.loads(self._read_first_sse_event()))
        api_state = ClusterState.from_dict(json.loads(_get("/api/state").read()))
        assert {n.name for n in sse_state.nodes} == {n.name for n in api_state.nodes}
