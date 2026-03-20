"""LobotApp: root Textual application."""

from pathlib import Path

from textual.app import App

from .config import APP_TITLE, THEME_FILE
from .data.collector import ServiceCollector
from .data.job_manager import BackgroundJobManager, JobCompleted
from .screens.main_screen import MainScreen
from .themes import THEME_NAMES, THEMES

CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"


class LobotApp(App):
    """btop-style cluster management TUI for the Lobot JupyterHub cluster."""

    CSS_PATH = str(CSS_PATH)
    TITLE = APP_TITLE

    async def on_mount(self) -> None:
        for theme in THEMES:
            self.register_theme(theme)
        self.theme = self._load_theme()

        self._collector = ServiceCollector(poster=self)
        self.job_manager = BackgroundJobManager()
        main = MainScreen(self._collector)
        self.push_screen(main)
        self._collector.start()

    def get_theme_variable_defaults(self) -> dict[str, str]:
        # Default values (lobot dark); individual themes override via Theme.variables.
        return {
            "panel-border": "#30363d",
            "accent-focus": "#e3b341",
            "bg-cursor": "#0a1e35",
            "bg-hover": "#2d333b",
            "chrome-bg": "#002452",
            "stripe-gold": "#fabd0f",
            "stripe-red": "#b90e31",
        }

    def cycle_theme(self) -> str:
        """Advance to the next theme and persist the choice. Returns the new theme name."""
        try:
            idx = THEME_NAMES.index(self.theme)
        except ValueError:
            idx = 0
        next_name = THEME_NAMES[(idx + 1) % len(THEME_NAMES)]
        self.theme = next_name
        self._save_theme(next_name)
        return next_name

    # ── persistence ──────────────────────────────────────────────────────────

    def _load_theme(self) -> str:
        # Env var takes priority — useful on shared accounts (e.g. croot) where
        # the saved file is shared but individuals may want their own theme:
        #   LOBOT_TUI_THEME=tricolour lobot-tui
        import os

        env = os.environ.get("LOBOT_TUI_THEME", "").strip()
        if env in THEME_NAMES:
            return env
        try:
            name = THEME_FILE.read_text().strip()
            if name in THEME_NAMES:
                return name
        except OSError:
            pass
        return THEME_NAMES[0]

    def _save_theme(self, name: str) -> None:
        # Don't overwrite the shared file when running with an env var override.
        import os

        if os.environ.get("LOBOT_TUI_THEME", "").strip() in THEME_NAMES:
            return
        try:
            THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
            THEME_FILE.write_text(name)
        except OSError:
            pass

    # ── message routing ───────────────────────────────────────────────────────

    def on_cluster_state_updated(self, event) -> None:
        try:
            self.screen.post_message(event)
        except Exception:
            pass

    def on_job_completed(self, event: JobCompleted) -> None:
        for screen in self.screen_stack:
            try:
                screen.post_message(event)
            except Exception:
                pass
