"""HelpScreen: full key bindings reference."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Markdown

HELP_TEXT = """
# LOBOT TUI — Key Bindings

## Global
| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Force refresh all data |
| `?` | This help screen |
| `` ` `` | Command console (history + errors) |
| `Escape` | Clear filter / close modal |

## Pod Table
| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `/` | Activate inline filter |
| `Escape` | Clear filter |
| `l` | View pod logs (kubectl logs -f) |
| `x` | Exec bash into pod (kubectl exec -it) |
| `d` / `Enter` | Describe pod (kubectl describe pod) |
| `X` | Delete pod (confirm required) |
| `n` | Cycle namespace |
| Click header | Sort by column (click again to reverse) |

## Node Table
| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `c` | Cordon node (confirm required) |
| `u` | Uncordon node (confirm required) |
| `w` | Drain node (confirm required) |
| Click header | Sort by column (click again to reverse) |

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
| `Escape` / `q` | Return to main screen |
| `s` | Save output to /tmp/lobot-tui-*.log |
| `Ctrl-D` / `exit` | Exit exec shell (exec screen only) |

## Announcement Editor
| Key | Action |
|-----|--------|
| `Ctrl+S` | Save YAML and push to GitHub |
| `Escape` | Back (without saving) |
"""


class HelpScreen(ModalScreen):
    """Displays key bindings reference."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
        ("question_mark", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("[bold cyan]LOBOT TUI — Help[/]  [dim][Esc/q/?] close[/]",
                        id="help-title", markup=True)
            yield Markdown(HELP_TEXT)

    def action_close(self) -> None:
        self.app.pop_screen()
