"""ExecScreen: full-screen TTY handoff for kubectl exec."""

import os
import subprocess

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Label, Static

from ..data import command_log


class ExecScreen(Screen):
    """Suspends the TUI and hands the terminal to kubectl exec."""

    BINDINGS = []

    def __init__(self, pod) -> None:
        super().__init__()
        self._pod = pod

    def compose(self) -> ComposeResult:
        with Horizontal(id="screen-header"):
            yield Label(
                f" [bold cyan]EXEC[/]  {self._pod.name}  [dim]— Ctrl-D or type 'exit' to return[/]",
                id="screen-header-main",
                markup=True,
            )
            yield Label("", id="top-bar-cat", markup=False)
        yield Static("", id="screen-log")
        yield Label(
            "[dim](q)[/] back",
            id="screen-footer",
            markup=True,
        )

    def on_mount(self) -> None:
        cmd = [
            "kubectl",
            "exec",
            "-it",
            self._pod.name,
            "-n",
            self._pod.namespace,
            "--",
            "/bin/bash",
        ]
        with self.app.suspend():
            os.system("clear")
            result = subprocess.run(cmd)
        command_log.record(" ".join(cmd), ["[interactive session]"], result.returncode)
        self.app.pop_screen()
