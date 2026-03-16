"""Domain model dataclasses for lobot-tui."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LabSummary:
    name: str
    cpu_free: int
    cpu_total: int
    ram_free_gb: int
    ram_total_gb: int
    gpu_free: int
    gpu_total: int
    pod_count: int = 0

    @property
    def cpu_used(self) -> int:
        return self.cpu_total - self.cpu_free

    @property
    def ram_used_gb(self) -> int:
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
    lab: str                # from node label lab=<value>
    image: str              # full image string
    image_tag: str          # tag portion only
    cpu_requested: int
    ram_requested_gb: int
    gpu_requested: int
    age: str
    phase: str              # Running / Pending / Failed / Unknown
    start_time: Optional[str] = None


@dataclass
class NodeInfo:
    name: str
    lab: str
    status: str             # Ready / NotReady / Unknown
    schedulable: bool       # False = cordoned
    cpu_allocatable: int
    cpu_requested: int
    ram_allocatable_gb: int
    ram_requested_gb: int
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
    def ram_free_gb(self) -> int:
        return max(0, self.ram_allocatable_gb - self.ram_requested_gb)

    @property
    def gpu_free(self) -> int:
        return max(0, self.gpu_allocatable - self.gpu_requested)


@dataclass
class ClusterState:
    labs: dict = field(default_factory=dict)       # lab_name -> LabSummary
    pods: list = field(default_factory=list)        # list[PodInfo]
    nodes: list = field(default_factory=list)       # list[NodeInfo]
    last_pods_update: Optional[datetime] = None
    last_nodes_update: Optional[datetime] = None
    pods_error: Optional[str] = None
    nodes_error: Optional[str] = None
