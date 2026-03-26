"""Tests for shell scripts in tools/.

Test categories:
  - Argument error tests: always run, no cluster access needed.
    Invoke scripts with bad/missing arguments and assert non-zero exit + error output.
  - lv-manage.sh info tests: read-only kubectl queries, no emails, no pods.
    Skipped automatically if kubectl is unreachable or no PVCs exist on the cluster.
  - script_integration mark: dry-run tests for image-pull.sh and image-cleanup.sh.
    THESE SEND REAL EMAILS and create temporary pods. Opt-in only:
      run-tests.sh -m script_integration

Run only the fast, safe tests (default):
    /opt/Lobot/tools/run-tests.sh -v tools/tests/test_scripts.py

Run everything including email-sending dry-runs:
    /opt/Lobot/tools/run-tests.sh -v -m "script_integration or not script_integration" tools/tests/test_scripts.py
"""

import shutil
import subprocess
from pathlib import Path

import pytest

TOOLS_DIR = Path("/opt/Lobot/tools")


def _run(script: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a tools/ script, capturing stdout + stderr."""
    return subprocess.run(
        ["bash", str(TOOLS_DIR / script)] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _kubectl_available() -> bool:
    if not shutil.which("kubectl"):
        return False
    result = subprocess.run(
        ["kubectl", "cluster-info"],
        capture_output=True,
        timeout=5,
    )
    return result.returncode == 0


def _get_worker_node() -> str | None:
    """Return the name of the first Ready non-control-plane node, or None."""
    result = subprocess.run(
        [
            "kubectl", "get", "nodes",
            "--no-headers",
            "-o", "custom-columns=NAME:.metadata.name,ROLES:.metadata.labels.node-role\\.kubernetes\\.io/control-plane,STATUS:.status.conditions[-1].status",
        ],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 1 and "<none>" in line:
            return parts[0]
    return None


def _get_any_pvc() -> tuple[str, str] | None:
    """Return (pvc_name, namespace) for the first bound PVC on the cluster, or None."""
    result = subprocess.run(
        ["kubectl", "get", "pvc", "-A", "--no-headers",
         "-o", "custom-columns=NS:.metadata.namespace,NAME:.metadata.name,PHASE:.status.phase"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == "Bound":
            return parts[1], parts[0]
    return None


_kubectl_mark = pytest.mark.skipif(
    not _kubectl_available(),
    reason="kubectl not available or cluster unreachable",
)


# ── image-pull.sh argument errors ─────────────────────────────────────────────


class TestImagePullArgErrors:
    def test_missing_image_exits_nonzero(self):
        result = _run("image-pull.sh")
        assert result.returncode != 0

    def test_missing_image_prints_error(self):
        result = _run("image-pull.sh")
        output = result.stdout + result.stderr
        assert output.strip(), "Expected error output, got nothing"

    def test_n_and_e_mutually_exclusive(self):
        result = _run(
            "image-pull.sh",
            "-i", "queensschoolofcomputingdocker/gpu-jupyter-latest:latest",
            "-n", "worker-1",
            "-e", "worker-2",
        )
        assert result.returncode != 0

    def test_n_and_e_prints_error(self):
        result = _run(
            "image-pull.sh",
            "-i", "queensschoolofcomputingdocker/gpu-jupyter-latest:latest",
            "-n", "worker-1",
            "-e", "worker-2",
        )
        output = result.stdout + result.stderr
        assert output.strip()


# ── image-cleanup.sh argument errors ─────────────────────────────────────────


class TestImageCleanupArgErrors:
    def test_missing_image_exits_nonzero(self):
        result = _run("image-cleanup.sh")
        assert result.returncode != 0

    def test_missing_image_prints_error(self):
        result = _run("image-cleanup.sh")
        output = result.stdout + result.stderr
        assert output.strip()

    def test_n_and_e_mutually_exclusive(self):
        result = _run(
            "image-cleanup.sh",
            "-i", "queensschoolofcomputingdocker/gpu-jupyter-latest:latest",
            "-n", "worker-1",
            "-e", "worker-2",
        )
        assert result.returncode != 0

    def test_n_and_e_prints_error(self):
        result = _run(
            "image-cleanup.sh",
            "-i", "queensschoolofcomputingdocker/gpu-jupyter-latest:latest",
            "-n", "worker-1",
            "-e", "worker-2",
        )
        output = result.stdout + result.stderr
        assert output.strip()


# ── lv-manage.sh argument errors ─────────────────────────────────────────────


class TestLvManageArgErrors:
    def test_no_args_exits_nonzero(self):
        result = _run("lv-manage.sh")
        assert result.returncode != 0

    def test_no_args_prints_usage(self):
        result = _run("lv-manage.sh")
        output = result.stdout + result.stderr
        assert "usage" in output.lower() or "Usage" in output

    def test_invalid_expand_size_format(self):
        # SIZE must match [0-9]+[MGT] — a plain number is invalid
        result = _run("lv-manage.sh", "some-pvc", "--expand", "100")
        assert result.returncode != 0

    def test_invalid_expand_size_wrong_suffix(self):
        result = _run("lv-manage.sh", "some-pvc", "--expand", "100K")
        assert result.returncode != 0


# ── sync_groups.sh ────────────────────────────────────────────────────────────


class TestSyncGroupsHelp:
    def test_help_exits_zero(self):
        result = _run("sync_groups.sh", "--help")
        assert result.returncode == 0

    def test_help_prints_usage(self):
        result = _run("sync_groups.sh", "--help")
        output = result.stdout + result.stderr
        assert "usage" in output.lower() or "Usage" in output


# ── lv-manage.sh info mode (read-only, no emails) ────────────────────────────


@_kubectl_mark
class TestLvManageInfo:
    @pytest.fixture(scope="class")
    def pvc(self):
        found = _get_any_pvc()
        if found is None:
            pytest.skip("No bound PVCs found on cluster")
        return found  # (name, namespace)

    def test_exits_zero_for_valid_pvc(self, pvc):
        name, namespace = pvc
        result = _run("lv-manage.sh", name, namespace, timeout=30)
        assert result.returncode == 0, f"lv-manage.sh failed:\n{result.stderr}"

    def test_produces_output_for_valid_pvc(self, pvc):
        name, namespace = pvc
        result = _run("lv-manage.sh", name, namespace, timeout=30)
        assert result.stdout.strip(), "Expected info output, got nothing"

    def test_nonexistent_pvc_exits_nonzero(self):
        result = _run("lv-manage.sh", "this-pvc-does-not-exist-lobot-test", timeout=15)
        assert result.returncode != 0

    def test_nonexistent_pvc_prints_error(self):
        result = _run("lv-manage.sh", "this-pvc-does-not-exist-lobot-test", timeout=15)
        output = result.stdout + result.stderr
        assert output.strip()


# ── image-pull.sh --dry-run (opt-in: sends email, creates pods) ───────────────


@pytest.mark.script_integration
@_kubectl_mark
class TestImagePullDryRun:
    @pytest.fixture(scope="class")
    def worker_node(self):
        node = _get_worker_node()
        if node is None:
            pytest.skip("No Ready worker node found")
        return node

    def test_dry_run_single_node_exits_zero(self, worker_node):
        result = _run(
            "image-pull.sh",
            "-i", "queensschoolofcomputingdocker/gpu-jupyter-latest",
            "-n", worker_node,
            "--dry-run",
            "--yes",
            "--noemail",
            timeout=120,
        )
        assert result.returncode == 0, f"Unexpected failure:\n{result.stdout}\n{result.stderr}"

    def test_dry_run_output_mentions_node(self, worker_node):
        result = _run(
            "image-pull.sh",
            "-i", "queensschoolofcomputingdocker/gpu-jupyter-latest",
            "-n", worker_node,
            "--dry-run",
            "--yes",
            "--noemail",
            timeout=120,
        )
        assert worker_node in result.stdout

    def test_dry_run_reports_present_or_missing(self, worker_node):
        result = _run(
            "image-pull.sh",
            "-i", "queensschoolofcomputingdocker/gpu-jupyter-latest",
            "-n", worker_node,
            "--dry-run",
            "--yes",
            "--noemail",
            timeout=120,
        )
        output = result.stdout + result.stderr
        assert "present" in output.lower() or "pull" in output.lower() or "would" in output.lower()


# ── image-cleanup.sh --dry-run (opt-in: sends email, creates DaemonSet) ───────


@pytest.mark.script_integration
@_kubectl_mark
class TestImageCleanupDryRun:
    def test_dry_run_exits_zero(self):
        result = _run(
            "image-cleanup.sh",
            "-i", "queensschoolofcomputingdocker/gpu-jupyter-latest:latest",
            "--dry-run",
            "--yes",
            "--noemail",
            timeout=180,
        )
        assert result.returncode == 0, f"Unexpected failure:\n{result.stdout}\n{result.stderr}"

    def test_dry_run_produces_output(self):
        result = _run(
            "image-cleanup.sh",
            "-i", "queensschoolofcomputingdocker/gpu-jupyter-latest:latest",
            "--dry-run",
            "--yes",
            "--noemail",
            timeout=180,
        )
        assert result.stdout.strip()
