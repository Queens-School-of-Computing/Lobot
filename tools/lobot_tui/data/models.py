"""Domain model dataclasses for lobot-tui."""

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ResourceSummary:
    name: str
    cpu_free: int
    cpu_total: int
    ram_free_gb: float
    ram_total_gb: float
    gpu_free: int
    gpu_total: int
    pod_count: int = 0

    @property
    def cpu_used(self) -> int:
        return self.cpu_total - self.cpu_free

    @property
    def ram_used_gb(self) -> float:
        return self.ram_total_gb - self.ram_free_gb

    @property
    def gpu_used(self) -> int:
        return self.gpu_total - self.gpu_free

    @property
    def has_gpu(self) -> bool:
        return self.gpu_total > 0


@dataclass
class PodInfo:
    name: str               # full pod name, e.g. jupyter-username
    username: str           # display name: stripped jupyter- prefix, -2d→-
    namespace: str
    node: str
    resource: str           # from node label lab=<value>
    image: str              # full image string
    image_tag: str          # tag portion only
    cpu_requested: float
    ram_requested_gb: float
    gpu_requested: int
    age: str
    phase: str              # Running / Pending / Failed / Unknown
    start_time: Optional[str] = None


@dataclass
class NodeInfo:
    name: str
    resource: str
    status: str             # Ready / NotReady / Unknown
    schedulable: bool       # False = cordoned
    cpu_allocatable: int
    cpu_requested: int
    ram_allocatable_gb: float
    ram_requested_gb: float
    gpu_allocatable: int
    gpu_requested: int
    is_control_plane: bool = False

    @property
    def cordoned(self) -> bool:
        return not self.schedulable

    @property
    def cpu_free(self) -> int:
        return max(0, self.cpu_allocatable - self.cpu_requested)

    @property
    def ram_free_gb(self) -> float:
        return max(0.0, self.ram_allocatable_gb - self.ram_requested_gb)

    @property
    def gpu_free(self) -> int:
        return max(0, self.gpu_allocatable - self.gpu_requested)


@dataclass
class ClusterState:
    resources: dict = field(default_factory=dict)  # resource_name -> ResourceSummary
    pods: list = field(default_factory=list)        # list[PodInfo]
    nodes: list = field(default_factory=list)       # list[NodeInfo]
    last_pods_update: Optional[datetime] = None
    last_nodes_update: Optional[datetime] = None
    pods_error: Optional[str] = None
    nodes_error: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict (used for SSE wire format)."""
        d = dataclasses.asdict(self)
        for key in ("last_pods_update", "last_nodes_update"):
            if d[key] is not None:
                d[key] = d[key].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ClusterState":
        """Reconstruct ClusterState from a dict produced by to_dict()."""
        # Accept both "resources" (new) and "labs" (old wire format) keys
        resources = {k: ResourceSummary(**v) for k, v in (d.get("resources") or d.get("labs", {})).items()}
        pods = [PodInfo(**p) for p in d.get("pods", [])]
        nodes = [NodeInfo(**n) for n in d.get("nodes", [])]
        lpu = d.get("last_pods_update")
        lnu = d.get("last_nodes_update")
        return cls(
            resources=resources,
            pods=pods,
            nodes=nodes,
            last_pods_update=datetime.fromisoformat(lpu) if lpu else None,
            last_nodes_update=datetime.fromisoformat(lnu) if lnu else None,
            pods_error=d.get("pods_error"),
            nodes_error=d.get("nodes_error"),
        )
