"""ExecScreen: full-screen TTY handoff for kubectl exec."""

import os
import subprocess

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Label, Static


class ExecScreen(Screen):
    """Suspends the TUI and hands the terminal to kubectl exec."""

    BINDINGS = []

    def __init__(self, pod) -> None:
        super().__init__()
        self._pod = pod

    def compose(self) -> ComposeResult:
        yield Label(
            f" [bold cyan]EXEC[/]  {self._pod.name}  [dim]— Ctrl-D or type 'exit' to return[/]",
            id="screen-header",
            markup=True,
        )
        yield Static("", id="screen-log")
        yield Label(
            "[dim](q)[/] back",
            id="screen-footer",
            markup=True,
        )

    def on_mount(self) -> None:
        cmd = [
            "kubectl", "exec", "-it", self._pod.name,
            "-n", self._pod.namespace, "--", "/bin/bash",
        ]
        with self.app.suspend():
            os.system("clear")
            subprocess.run(cmd)
        self.app.pop_screen()
