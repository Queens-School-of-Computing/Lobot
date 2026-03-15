"""LobotApp: root Textual application."""

from pathlib import Path
from textual.app import App

from .config import APP_TITLE
from .data.collector import DataCollector
from .data.job_manager import BackgroundJobManager, JobCompleted
from .screens.main_screen import MainScreen

CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"


class LobotApp(App):
    """btop-style cluster management TUI for the Lobot JupyterHub cluster."""

    CSS_PATH = str(CSS_PATH)
    TITLE = APP_TITLE

    def on_mount(self) -> None:
        # Create the data collector, using MainScreen as the message bus poster
        # We post messages via the app itself so all screens receive them.
        self._collector = DataCollector(poster=self)
        self.job_manager = BackgroundJobManager()
        main = MainScreen(self._collector)
        self.push_screen(main)
        # Start polling after screen is pushed so the message handler is live
        self._collector.start()

    def on_cluster_state_updated(self, event) -> None:
        # Re-broadcast to the current screen so all its widgets receive it
        try:
            self.screen.post_message(event)
        except Exception:
            pass

    def on_job_completed(self, event: JobCompleted) -> None:
        # Re-broadcast to ALL screens in the stack so MainScreen always receives it,
        # even when another screen (logs, describe, jobs) is on top.
        for screen in self.screen_stack:
            try:
                screen.post_message(event)
            except Exception:
                pass
