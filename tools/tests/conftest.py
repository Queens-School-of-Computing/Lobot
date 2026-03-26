"""Shared pytest fixtures for lobot-tui unit tests."""

import json

import pytest

_BYTES_PER_GIB = 1_073_741_824


@pytest.fixture
def pods_json():
    """Minimal realistic kubectl get pods -o json output.

    Contains:
      - jupyter-alice: Running, worker-1, 2cpu / 8Gi / 1 GPU
      - jupyter-bob-2dtest: Running, worker-1, 4cpu / 16Gi / 2 GPU (hyphen-escape in name)
      - hub-deployment-abc123: Running, worker-1, 500m / 512Mi / 0 GPU (non-jupyter system pod)
    """
    data = {
        "apiVersion": "v1",
        "kind": "PodList",
        "items": [
            {
                "metadata": {"name": "jupyter-alice", "namespace": "jhub"},
                "spec": {
                    "nodeName": "worker-1",
                    "containers": [
                        {
                            "image": "queensschoolofcomputingdocker/gpu-jupyter-latest:2024-03-01",
                            "resources": {
                                "requests": {
                                    "cpu": "2",
                                    "memory": "8Gi",
                                    "nvidia.com/gpu": "1",
                                }
                            },
                        }
                    ],
                },
                "status": {"phase": "Running", "startTime": "2024-01-01T10:00:00Z"},
            },
            {
                "metadata": {"name": "jupyter-bob-2dtest", "namespace": "jhub"},
                "spec": {
                    "nodeName": "worker-1",
                    "containers": [
                        {
                            "image": "queensschoolofcomputingdocker/gpu-jupyter-latest:2024-03-01",
                            "resources": {
                                "requests": {
                                    "cpu": "4",
                                    "memory": "16Gi",
                                    "nvidia.com/gpu": "2",
                                }
                            },
                        }
                    ],
                },
                "status": {"phase": "Running", "startTime": "2024-01-01T10:00:00Z"},
            },
            {
                "metadata": {"name": "hub-deployment-abc123", "namespace": "jhub"},
                "spec": {
                    "nodeName": "worker-1",
                    "containers": [
                        {
                            "image": "jupyterhub/k8s-hub:3.3.7",
                            "resources": {
                                "requests": {
                                    "cpu": "500m",
                                    "memory": "512Mi",
                                }
                            },
                        }
                    ],
                },
                "status": {"phase": "Running", "startTime": "2024-01-01T09:00:00Z"},
            },
        ],
    }
    return json.dumps(data)


@pytest.fixture
def nodes_json():
    """Minimal realistic kubectl get nodes -o json output.

    Contains:
      - worker-1: Ready, schedulable, lab=research, 8cpu / 64Gi / 4 GPU
      - control-plane-node: Ready, has control-plane label, 4cpu / 16Gi / 0 GPU
    """
    data = {
        "apiVersion": "v1",
        "kind": "NodeList",
        "items": [
            {
                "metadata": {
                    "name": "worker-1",
                    "labels": {"lab": "research"},
                },
                "spec": {},
                "status": {
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "allocatable": {
                        "cpu": "8",
                        "memory": "64Gi",
                        "nvidia.com/gpu": "4",
                    },
                },
            },
            {
                "metadata": {
                    "name": "control-plane-node",
                    "labels": {"node-role.kubernetes.io/control-plane": ""},
                },
                "spec": {},
                "status": {
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "allocatable": {
                        "cpu": "4",
                        "memory": "16Gi",
                    },
                },
            },
        ],
    }
    return json.dumps(data)


@pytest.fixture
def longhorn_json():
    """Minimal kubectl get nodes.longhorn.io -o json output.

    Contains worker-1 with:
      - disk-1: 10 GiB total, 4 GiB available, 3 GiB scheduled, schedulable=True
      - disk-uninit: storageMaximum=0 — should be skipped (not yet initialised)
    """
    data = {
        "apiVersion": "longhorn.io/v1beta2",
        "kind": "NodeList",
        "items": [
            {
                "metadata": {"name": "worker-1"},
                "spec": {
                    "disks": {
                        "disk-1": {"path": "/mnt/nvme0n1", "allowScheduling": True},
                        "disk-uninit": {"path": "/mnt/nvme1n1", "allowScheduling": False},
                    }
                },
                "status": {
                    "diskStatus": {
                        "disk-1": {
                            "storageMaximum": 10 * _BYTES_PER_GIB,
                            "storageAvailable": 4 * _BYTES_PER_GIB,
                            "storageScheduled": 3 * _BYTES_PER_GIB,
                        },
                        "disk-uninit": {
                            "storageMaximum": 0,
                            "storageAvailable": 0,
                            "storageScheduled": 0,
                        },
                    }
                },
            }
        ],
    }
    return json.dumps(data)
