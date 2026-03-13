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
| `Tab` / `Shift+Tab` | Cycle panel focus |
| `r` | Force refresh all data |
| `?` | This help screen |
| `Escape` | Close modal / go back |

## Pod Table (when focused)
| Key | Action |
|-----|--------|
| `j` / `↓` | Move down |
| `k` / `↑` | Move up |
| `/` | Activate inline filter |
| `Escape` | Clear filter |
| `l` | View pod logs (`kubectl logs -f`) |
| `x` | Exec bash into pod (`kubectl exec -it`) |
| `d` | Delete pod (confirm required) |
| `R` | Restart pod — delete & let JH respawn |
| `D` or `Enter` | Describe pod (`kubectl describe pod`) |
| `n` | Cycle namespace: jhub → all → jhub |

## Node Table (when focused)
| Key | Action |
|-----|--------|
| `j` / `↓` | Move down |
| `k` / `↑` | Move up |
| `c` | Cordon node (confirm required) |
| `u` | Uncordon node (confirm required) |
| `w` | Drain node wizard |

## Tool Actions
| Key | Action |
|-----|--------|
| `1` | image-pull wizard |
| `2` | image-cleanup wizard |
| `3` | apply-config (confirm required) |
| `4` | sync-groups |
| `5` | helm upgrade — JupyterHub |
| `6` | Edit announcement.yaml + push to GitHub |

## Logs / Action Screens
| Key | Action |
|-----|--------|
| `Escape` / `q` | Return to main screen |
| `s` | Save output to `/tmp/lobot-tui-*.log` |

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
        ("?", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Label("[bold cyan]LOBOT TUI — Help[/]  [dim][Esc/q/?] close[/]",
                        id="help-title", markup=True)
            yield Markdown(HELP_TEXT)

    def action_close(self) -> None:
        self.app.pop_screen()
