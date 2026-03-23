"""ActionsPanel: left hints | bongo cat | right hints."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label, Static

# ── Hint data ─────────────────────────────────────────────────────────────────

_ROW1_LEFT = [
    ("[bold dim]PODS[/]", "hint-prefix", None),
    ("[bold cyan](l)[/] logs", "hint-pod", "l"),
    ("[bold cyan](x)[/] exec", "hint-pod", "x"),
    ("[bold cyan](d)[/] describe", "hint-pod", "d"),
    ("[bold cyan](X)[/] delete", "hint-pod", "X"),
    ("[bold cyan](f)[/] filter", "hint-pod", "f"),
    ("[bold cyan](N)[/] ns", "hint-pod", "N"),
]
_ROW2_LEFT = [
    ("[bold dim]NODES[/]", "hint-prefix", None),
    ("[bold cyan](n)[/] node filter", "hint-node", "n"),
    ("[bold cyan](r)[/] resource filter", "hint-node", "r"),
    ("[bold cyan](c)[/] cordon", "hint-node", "c"),
    ("[bold cyan](u)[/] uncordon", "hint-node", "u"),
    ("[bold cyan](w)[/] drain", "hint-node", "w"),
]
_ROW1_RIGHT = [
    ("[bold dim]TOOLS[/]", "hint-prefix", None),
    ("[bold yellow](1)[/] image-pull", "hint-tool", "1"),
    ("[bold yellow](2)[/] image-cleanup", "hint-tool", "2"),
    ("[bold yellow](3)[/] apply-config", "hint-tool", "3"),
    ("[bold yellow](4)[/] sync-groups", "hint-tool", "4"),
    ("[bold yellow](5)[/] helm upgrade", "hint-tool", "5"),
    ("[bold yellow](6)[/] announce", "hint-tool", "6"),
]
_ROW2_RIGHT = [
    ("[bold yellow](`)[/] console", "hint-tool", "`"),
    ("[bold yellow](b)[/] jobs", "hint-tool", "b"),
    ("[bold yellow](?)[/] help", "hint-tool", "?"),
    ("[bold yellow](G)[/] guide", "hint-tool", "G"),
    ("[bold yellow](T)[/] theme", "hint-tool", "T"),
    ("[bold yellow](q)[/] quit", "hint-tool", "q"),
]

# ── Bongo cat ─────────────────────────────────────────────────────────────────

# Typing cat: paws alternate hitting the keyboard.
# Eyes squint on the hitting side. `/` = arm raised, `.` = paw down on keys.
# Hit frames use {k} (3 chars) to show the key pressed.
# ༼ つ ◕_◕ ༽つ
# _CAT_FRAMES = [
#     "(•ω•)\n/[{k}]\\",  # neutral — both paws raised — key shown
#     "(•ω•)\n.[{k}]/",   # left paw hits — key shown
#     "(•ω•)\n/[{k}]\\",  # neutral — both paws raised — key shown
#     "(•ω•)\n/[{k}].",   # right paw hits — key shown
# ]
_CAT_FRAMES = [
    "༼-╯⊙_⊙༽╯  [{k}]",    # neutral, both paws raised.    
    "༼つ⊙_⊙༽╯  [{k}]",    # right paw pressed
    "༼-╯⊙_⊙༽つ [{k}]",   # left paw pressed
    "༼つ⊙_⊙༽つ [{k}]",   # both paws pressed.
]

# Textual key name → 3-char display string (must be exactly 3 chars)
_KEY_ABBREVS: dict[str, str] = {
    "space": "spc",
    "tab": "tab",
    "escape": "esc",
    "enter": "ret",
    "backspace": "bsp",
    "delete": "del",
    "up": " ↑ ",
    "down": " ↓ ",
    "left": " ← ",
    "right": " → ",
    "grave_accent": " ` ",
    "question_mark": " ? ",
}


def _fmt_key(key: str) -> str:
    """Return exactly 3 chars representing the key for display in the cat frame."""
    if key in _KEY_ABBREVS:
        return _KEY_ABBREVS[key]
    if len(key) == 1:
        return f" {key} "
    if key.startswith("ctrl+") and len(key) == 6:
        return f"^{key[5]} "
    # fallback: first 3 chars left-justified
    return key[:3].ljust(3)

# ── Shared label types ────────────────────────────────────────────────────────


class HintClicked(Message):
    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key


class HintLabel(Label):
    DEFAULT_CSS = """
    HintLabel {
        width: auto;
        padding: 0 1 0 0;
        color: $foreground;
    }
    HintLabel:hover { text-style: underline; color: $primary; }
    HintLabel.hint-prefix { color: $text-muted; }
    """

    def __init__(self, text: str, key: str | None, **kwargs) -> None:
        super().__init__(text, **kwargs)
        self._hint_key = key

    def on_click(self) -> None:
        if self._hint_key:
            self.post_message(HintClicked(self._hint_key))


# ── The three panels ──────────────────────────────────────────────────────────


class LeftActionsWidget(Widget):
    """Pod and node action hints. Layout set by #left-actions in app.tcss."""

    def compose(self) -> ComposeResult:
        with Horizontal():
            for text, cls, key in _ROW1_LEFT:
                yield HintLabel(text, key, classes=cls, markup=True)
        with Horizontal():
            for text, cls, key in _ROW2_LEFT:
                yield HintLabel(text, key, classes=cls, markup=True)


class BongoCatWidget(Widget):
    """Animated bongo cat. Sizing set by #bongo-cat-panel in app.tcss."""

    def compose(self) -> ComposeResult:
        initial = _CAT_FRAMES[0].replace("{k}", "   ")
        yield Static(initial, id="bongo-cat", markup=False)

    def on_mount(self) -> None:
        self._frame_idx = 0

    def bongo_hit(self, key: str = "") -> None:
        self._frame_idx = (self._frame_idx + 1) % len(_CAT_FRAMES)
        template = _CAT_FRAMES[self._frame_idx]
        frame = template.replace("{k}", _fmt_key(key)) if "{k}" in template else template
        try:
            self.query_one("#bongo-cat", Static).update(frame)
        except Exception:
            pass


class RightActionsWidget(Widget):
    """Tool and global action hints. Layout set by #right-actions in app.tcss."""

    def compose(self) -> ComposeResult:
        with Horizontal():
            for text, cls, key in _ROW1_RIGHT:
                yield HintLabel(text, key, classes="hint-tools-right " + cls, markup=True)
        with Horizontal():
            for text, cls, key in _ROW2_RIGHT:
                yield HintLabel(text, key, classes="hint-tools-right " + cls, markup=True)
            yield Label("", id="job-status-label", markup=True)

    def set_job_status(self, text: str | None) -> None:
        job_label = self.query_one("#job-status-label", Label)
        right_hints = self.query(".hint-tools-right")
        if text is None:
            job_label.display = False
            for w in right_hints:
                w.display = True
        else:
            for w in right_hints:
                w.display = False
            job_label.update(text)
            job_label.display = True
