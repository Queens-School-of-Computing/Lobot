"""Theme definitions for lobot-tui."""

from textual.theme import Theme

# Current GitHub-dark inspired colours — preserved as the default theme.
# success="#3fb950",
LOBOT_DARK = Theme(
    name="lobot",
    dark=True,
    primary="#58a6ff",
    secondary="#79c0ff",
    background="#090d13",
    surface="#161b22",
    panel="#0d1117",
    warning="#d29922",
    error="#f85149",
    success="#008700",
    foreground="#c9d1d9",
    accent="#e3b341",
    variables={
        "panel-border": "#30363d",
        "accent-focus": "#e3b341",
        "bg-cursor": "#0a1e35",
        "bg-hover": "#2d333b",
        "chrome-bg": "#002452",
        "stripe-gold": "#fabd0f",
        "stripe-red": "#b90e31",
    },
)

# Queen's University brand identity (https://www.queensu.ca/brand-central/visual-identity/colours)
# Primary: Queen's Blue #002452 · Queen's Gold #fabd0f · Queen's Red #b90e31
TRICOLOUR = Theme(
    name="tricolour",
    dark=True,
    primary="#fabd0f",  # Queen's Gold — accent, titles, links
    secondary="#fdd44e",  # lighter gold — table headers
    background="#00091a",  # very dark navy
    surface="#002452",  # Queen's Blue — headers, bars, dialogs
    panel="#000d24",  # dark navy — DataTable, log backgrounds
    warning="#fabd0f",  # Queen's Gold — stale/pending
    error="#b90e31",  # Queen's Red — failed/delete
    success="#4a9fd4",  # bright Queen's Blue — live/running/ready
    foreground="#f0ece4",  # warm off-white
    accent="#fabd0f",  # Queen's Gold
    variables={
        "text-muted": "#b4aea8",  # Light Limestone — overrides Textual's computed value
        "panel-border": "#003d80",
        "accent-focus": "#fabd0f",
        "bg-cursor": "#b90e31",  # Queen's Red row highlight
        "bg-hover": "#001c3f",
        "chrome-bg": "#002452",
        "stripe-gold": "#fabd0f",
        "stripe-red": "#b90e31",
    },
)

# THEMES: list[Theme] = [LOBOT_DARK, TRICOLOUR]
THEMES: list[Theme] = [LOBOT_DARK]
THEME_NAMES: list[str] = [t.name for t in THEMES]

# ── Python-level color constants ──────────────────────────────────────────────
# Used in Rich markup strings where CSS variables are unavailable.
# Keep in sync with the Theme definitions above.

# Status / resource bar colours
COLOR_OK = "#008700"  # success · Ready · Running       (xterm-256 #28)
COLOR_WARN = "#fabd0f"  # warning · Cordoned · Pending    (Queen's Gold)
COLOR_CRIT = "#af0000"  # critical · NotReady · Failed    (Queen's Red, xterm-256 #124)
COLOR_DIM = "#3a404e"  # empty bar segments / dim text

# Row-tint backgrounds
BG_CORDONED = "#1a1500"  # very dark amber — cordoned node rows
BG_NOTREADY = "#1a0505"  # very dark red   — NotReady node rows

# Chrome / stripe
CHROME = "#002452"  # Queen's Blue
STRIPE_GOLD = "#fabd0f"  # Queen's Gold
STRIPE_RED = "#af0000"  # Queen's Red (256-colour-safe variant)

# LOBOT dark theme accents used in Rich markup (top-bar stats, etc.)
PRIMARY = "#58a6ff"
SECONDARY = "#79c0ff"
