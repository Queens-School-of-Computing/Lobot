"""HelpScreen: full key bindings reference."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Markdown

from .guide_screen import GuideScreen

HELP_TEXT = """
# LOBOT TUI — Key Bindings

## Global
| Key | Action |
|-----|--------|
| `q` | Quit (press twice to confirm) |
| `R` | Force refresh all data |
| `Tab` | Cycle panel focus: Resources → Nodes → Pods |
| `?` | This help screen |
| `` ` `` | Command console (history + errors) |
| `b` | Background jobs panel (live output of running tool) |
| `Escape` | Return focus to pod table (from filter input) |

## Pod Table
| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `f` | Focus filter input |
| `Enter` (in filter) | Apply filter, return focus to table |
| `Escape` (in filter) | Return focus to table (text unchanged) |
| `l` | View pod logs (kubectl logs -f) |
| `x` | Exec bash into pod (kubectl exec -it) |
| `d` / `Enter` | Describe pod (kubectl describe pod) |
| `X` | Delete pod (press twice to confirm) |
| `N` | Cycle namespace |
| Click header | Sort by column (click again to reverse) |

## Node Table
| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows (including disk sub-rows) |
| `Space` / `→` | Expand disk sub-rows for selected node |
| `←` | Collapse disk sub-rows for selected node |
| Click row | Toggle disk sub-rows |
| `n` | Toggle node filter — filter pods to selected node; navigate to update |
| `c` | Cordon node (press twice to confirm) |
| `u` | Uncordon node (press twice to confirm) |
| `w` | Drain node (press twice to confirm) |
| Click header | Sort by column (click again to reverse) |

> Node operations (`c`, `u`, `w`, `n`) always apply to the parent node regardless of which disk sub-row is selected. The control plane is protected from cordon/drain.

## Resource Table
| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `r` | Toggle resource filter — filter pods to selected resource group; navigate to update |

> Stats show **jupyter-\\* pod requests only**. Full node accounting is in the Node Table.

## Tool Actions
| Key | Action |
|-----|--------|
| `1` | image-pull wizard |
| `2` | image-cleanup wizard |
| `3` | apply-config (confirm required) |
| `4` | sync-groups |
| `5` | helm upgrade — JupyterHub |
| `6` | Edit announcement.yaml + push to GitHub |

> Tool actions run as background jobs. Only one job runs at a time. Press `b` to return to the dashboard while the job continues.

## Background Jobs Panel
| Key | Action |
|-----|--------|
| `b` | Background the panel — return to dashboard, job keeps running |
| `k` | Kill job (press twice within 3 seconds to confirm) |
| `s` | Save output to /opt/Lobot/logs/lobot-tui-\\<name\\>-\\<timestamp\\>.log |

> While a job is **running**: `Escape` and `q` have no effect. Once **finished**: `Escape` / `q` / `b` all close the panel.

## Logs / Action / Exec Screens
| Key | Action |
|-----|--------|
| `Escape` (×2) / `q` | Return to main screen (`Escape` needs two presses) |
| `s` | Save output to /opt/Lobot/logs/lobot-tui-*.log |
| `Ctrl-D` / `exit` | Exit exec shell (exec screen only) |

## Log Viewer (scroll behaviour)
| Key | Action |
|-----|--------|
| Scroll up | Pause live stream (new lines buffered, not displayed) |
| `l` | Resume stream — flush buffered lines and scroll to bottom |

## Announcement Editor
| Key | Action |
|-----|--------|
| `Escape` | Cancel without saving |

> Save & push is not yet enabled — edit `announcement.yaml` manually for now.

---

Press `G` to open the full documentation guide (`lobot-tui.md`).
"""


class HelpScreen(ModalScreen):
    """Displays key bindings reference."""

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("q", "close", "Close", priority=True),
        Binding("question_mark", "close", "Close", priority=True),
        Binding("G", "open_guide", "Full guide", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label(
                "[bold cyan]LOBOT TUI — Help[/]  [dim][Esc/q/?] close[/]"
                "  [dim][[G][/] [@click='screen.open_guide'][link]full guide ↗[/link][/]",
                id="help-title",
                markup=True,
            )
            yield Markdown(HELP_TEXT)

    def action_close(self) -> None:
        self.app.pop_screen()

    def action_open_guide(self) -> None:
        self.app.pop_screen()
        self.app.push_screen(GuideScreen())
