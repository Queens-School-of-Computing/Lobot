"""HelpScreen: full key bindings reference."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Markdown

HELP_TEXT = """
# LOBOT TUI — Key Bindings

## Global
| Key | Action |
|-----|--------|
| `q` | Quit |
| `R` | Force refresh all data |
| `Tab` | Cycle panel focus: Resources → Nodes → Pods |
| `?` | This help screen |
| `` ` `` | Command console (history + errors) |
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
| `X` | Delete pod (confirm required) |
| `N` | Cycle namespace |
| Click header | Sort by column (click again to reverse) |

## Node Table
| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `n` | Toggle node filter — filter pods to selected node; navigate to update |
| `c` | Cordon node (confirm required) |
| `u` | Uncordon node (confirm required) |
| `w` | Drain node (confirm required) |
| Click header | Sort by column (click again to reverse) |

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
| `Ctrl+S` | Save YAML and push to GitHub |
| `Escape` | Back (without saving) |

"""


class HelpScreen(ModalScreen):
    """Displays key bindings reference."""

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("q", "close", "Close", priority=True),
        Binding("question_mark", "close", "Close", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label(
                "[bold cyan]LOBOT TUI — Help[/]  [dim][Esc/q/?] close[/]",
                id="help-title",
                markup=True,
            )
            yield Markdown(HELP_TEXT)

    def action_close(self) -> None:
        self.app.pop_screen()
