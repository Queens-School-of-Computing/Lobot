"""LobotApp: root Textual application."""

import asyncio
from pathlib import Path
from textual.app import App

from .config import APP_TITLE, DEV_MODE, SERVICE_HOST, SERVICE_PORT
from .data.collector import DataCollector, ServiceCollector
from .data.job_manager import BackgroundJobManager, JobCompleted
from .screens.main_screen import MainScreen

CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"


async def _service_available() -> bool:
    """Return True if lobot-collector is accepting connections on SERVICE_PORT."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(SERVICE_HOST, SERVICE_PORT),
            timeout=0.5,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


class LobotApp(App):
    """btop-style cluster management TUI for the Lobot JupyterHub cluster."""

    CSS_PATH = str(CSS_PATH)
    TITLE = APP_TITLE

    async def on_mount(self) -> None:
        # Choose collector: ServiceCollector if lobot-collector is running,
        # otherwise fall back to direct kubectl polling via DataCollector.
        if not DEV_MODE and await _service_available():
            self._collector = ServiceCollector(poster=self)
        else:
            self._collector = DataCollector(poster=self)
        self.job_manager = BackgroundJobManager()
        main = MainScreen(self._collector)
        self.push_screen(main)
        # Start polling/streaming after screen is pushed so message handler is live
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
