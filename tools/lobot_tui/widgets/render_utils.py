"""render_utils.py — Rich markup helpers for progress bars and status badges."""

from rich.text import Text

_FILLED   = "▉"
_EMPTY    = "▉"
_COLOR_OK   = "#00dd55"   # vivid green
_COLOR_WARN = "#f0a800"   # vivid amber
_COLOR_CRIT = "#ff3333"   # vivid red
_COLOR_DIM  = "#3a404e"   # near-invisible text on dark bg

_BG_CORDONED = "#1a1500"   # very dark amber for cordoned rows
_BG_NOTREADY = "#1a0505"   # very dark red for NotReady rows


def _pct_color(ratio: float) -> str:
    if ratio >= 0.90:
        return _COLOR_CRIT
    elif ratio >= 0.75:
        return _COLOR_WARN
    return _COLOR_OK


# ── Value formatters ───────────────────────────────────────────────────────────
# Return a single right-justified string of fixed width.
# CPU/RAM: 7 chars.  GPU: 5 chars.

def fmt_cpu(used: float, total: float) -> str:
    """'used/total' right-justified in 7 chars. e.g. '  2/256', '128/512'"""
    s = f"{int(round(used))}/{int(round(total))}"
    return s[:7].rjust(7)


def fmt_ram_gb(used_gb: float, total_gb: float) -> str:
    """'used/totalU' right-justified in 7 chars. Uses T above 512G."""
    if total_gb >= 512:
        s = f"{used_gb / 1024:.1f}/{total_gb / 1024:.0f}T"
    else:
        s = f"{int(round(used_gb))}/{int(round(total_gb))}G"
    return s[:7].rjust(7)


def fmt_gpu(used: float, total: float) -> str:
    """'used/total' right-justified in 5 chars. e.g. '  6/8', '24/64'"""
    s = f"{int(round(used))}/{int(round(total))}"
    return s[:5].rjust(5)


# ── Bar renderers ──────────────────────────────────────────────────────────────
# Column width = bar_w + 1 + len(val_str)
# CPU/RAM: bar_w=7, val=7  → col_width=15
# GPU:     bar_w=4, val=5  → col_width=10

def render_bar(used: float, total: float, bar_w: int, val_str: str) -> str:
    """
    Wide bar followed by dim used/total text.
    Visible width = bar_w + 1 + len(val_str)
    """
    col_width = bar_w + 1 + len(val_str)
    if total <= 0 or bar_w <= 0:
        return f"[{_COLOR_DIM}]{'–':>{col_width}}[/]"
    ratio  = min(1.0, max(0.0, used / total))
    color  = _pct_color(ratio)
    filled = int(round(ratio * bar_w))
    empty  = bar_w - filled
    bar    = f"[{color}]{_FILLED * filled}[/][{_COLOR_DIM}]{_EMPTY * empty}[/]"
    return f"{bar} [{_COLOR_DIM}]{val_str}[/]"


def render_bar_text(used: float, total: float, bar_w: int, val_str: str,
                    row_bg: "str | None" = None) -> Text:
    """Like render_bar() but returns a rich.text.Text — needed for tinted rows."""
    col_width = bar_w + 1 + len(val_str)
    base  = f"on {row_bg}" if row_bg else ""
    t = Text(no_wrap=True)
    if total <= 0 or bar_w <= 0:
        t.append(f"{'–':>{col_width}}", style=f"{_COLOR_DIM} {base}".strip())
        return t
    ratio  = min(1.0, max(0.0, used / total))
    color  = _pct_color(ratio)
    filled = int(round(ratio * bar_w))
    empty  = bar_w - filled
    t.append(_FILLED * filled, style=f"{color} {base}".strip())
    t.append(_EMPTY  * empty,  style=f"{_COLOR_DIM} {base}".strip())
    t.append(" " + val_str,    style=f"{_COLOR_DIM} {base}".strip())
    return t


_GPU_BAR_W = 8   # fixed visual width for all GPU bars in the node table


def render_gpu_bar(used: float, total: float, val_str: str) -> str:
    """
    GPU bar: always _GPU_BAR_W chars wide.
    For nodes with <= _GPU_BAR_W GPUs: each segment = 1 GPU (segment_w chars each).
    For nodes with > _GPU_BAR_W GPUs (e.g. time-sliced 96): ratio mode.
    Visible width = _GPU_BAR_W + 1 + len(val_str)
    """
    col_width = _GPU_BAR_W + 1 + len(val_str)
    if total <= 0:
        return f"[{_COLOR_DIM}]{'–':>{col_width}}[/]"
    ratio = min(1.0, max(0.0, used / total))
    color = _pct_color(ratio)
    gpu_total = int(round(total))
    gpu_used  = int(round(used))
    if gpu_total > _GPU_BAR_W:
        # More GPUs than bar width — ratio mode
        filled = int(round(ratio * _GPU_BAR_W))
        empty  = _GPU_BAR_W - filled
    else:
        seg_w  = _GPU_BAR_W // gpu_total
        filled = gpu_used * seg_w
        empty  = (gpu_total - gpu_used) * seg_w
    pad = _GPU_BAR_W - filled - empty
    bar = f"[{color}]{_FILLED * filled}[/][{_COLOR_DIM}]{_EMPTY * empty}[/]{' ' * pad}"
    return f"{bar} [{_COLOR_DIM}]{val_str}[/]"


def render_gpu_bar_text(used: float, total: float, val_str: str,
                        row_bg: "str | None" = None) -> Text:
    """Like render_gpu_bar() but returns a rich.text.Text for tinted rows."""
    col_width = _GPU_BAR_W + 1 + len(val_str)
    base = f"on {row_bg}" if row_bg else ""
    t = Text(no_wrap=True)
    if total <= 0:
        t.append(f"{'–':>{col_width}}", style=f"{_COLOR_DIM} {base}".strip())
        return t
    ratio = min(1.0, max(0.0, used / total))
    color = _pct_color(ratio)
    gpu_total = int(round(total))
    gpu_used  = int(round(used))
    if gpu_total > _GPU_BAR_W:
        filled = int(round(ratio * _GPU_BAR_W))
        empty  = _GPU_BAR_W - filled
    else:
        seg_w  = _GPU_BAR_W // gpu_total
        filled = gpu_used * seg_w
        empty  = (gpu_total - gpu_used) * seg_w
    pad = _GPU_BAR_W - filled - empty
    t.append(_FILLED * filled,  style=f"{color} {base}".strip())
    t.append(_EMPTY  * empty,   style=f"{_COLOR_DIM} {base}".strip())
    if pad:
        t.append(" " * pad,     style=base or "")
    t.append(" " + val_str,     style=f"{_COLOR_DIM} {base}".strip())
    return t


# ── Status badges ──────────────────────────────────────────────────────────────

def status_badge(node) -> str:
    """Return a Rich markup status badge for a NodeInfo (plain string version)."""
    if node.is_control_plane:
        return "[dim]● ctrl[/]"
    if node.status == "Ready" and node.schedulable:
        return "[#00dd55]● Ready[/]"
    if node.status == "Ready" and not node.schedulable:
        return "[#f0a800]◆ Cordoned[/]"
    if node.status == "NotReady":
        return "[#ff3333]✖ NotReady[/]"
    return "[dim]? Unknown[/]"


def status_badge_text(node, row_bg: "str | None" = None) -> Text:
    """Same as status_badge() but returns a Text object for tinted rows."""
    base = f"on {row_bg}" if row_bg else ""
    t = Text(no_wrap=True)
    if node.is_control_plane:
        t.append("● ctrl",     style=f"dim {base}".strip())
    elif node.status == "Ready" and node.schedulable:
        t.append("● Ready",    style=f"#00dd55 {base}".strip())
    elif node.status == "Ready" and not node.schedulable:
        t.append("◆ Cordoned", style=f"#f0a800 {base}".strip())
    elif node.status == "NotReady":
        t.append("✖ NotReady", style=f"#ff3333 {base}".strip())
    else:
        t.append("? Unknown",  style=f"dim {base}".strip())
    return t


# ── Row helpers ────────────────────────────────────────────────────────────────

def row_bg_for_node(node) -> "str | None":
    """Return tint background for cordoned/NotReady nodes, or None."""
    if node.is_control_plane:
        return None
    if not node.schedulable:
        return _BG_CORDONED
    if node.status == "NotReady":
        return _BG_NOTREADY
    return None


def plain_text(s: str, row_bg: "str | None"):
    """Return s as-is (str) for normal rows, or Text with bg for tinted rows."""
    if row_bg is None:
        return s
    return Text(s, style=f"on {row_bg}", no_wrap=True)


def filter_highlight(s: str, row_bg: "str | None"):
    """Return s with bold cyan filter highlight, optionally with row background tint."""
    if row_bg is None:
        return f"[bold cyan]{s}[/]"
    return Text(s, style=f"bold cyan on {row_bg}", no_wrap=True)
