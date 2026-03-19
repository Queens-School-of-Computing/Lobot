"""Cluster data collector: polls lobot-collector service for pod, node, and disk data."""

import asyncio
import json

from textual.message import Message
from textual.widget import Widget

from ..config import (
    PODS_INTERVAL,
    SERVICE_HOST,
    SERVICE_PORT,
)
from .models import ClusterState

# ---------------------------------------------------------------------------
# Message emitted to the app when new data is ready
# ---------------------------------------------------------------------------


class ClusterStateUpdated(Message):
    def __init__(self, state: ClusterState, source: str = "service") -> None:
        super().__init__()
        self.state = state
        self.source = source


# ---------------------------------------------------------------------------
# ServiceCollector — polls lobot-collector /api/state
# ---------------------------------------------------------------------------


class ServiceCollector:
    """
    Polls the lobot-collector HTTP service for ClusterState every PODS_INTERVAL
    seconds. All data — pods, nodes, and Longhorn disk — is collected exclusively
    by lobot-collector and delivered here via the wire format.
    """

    def __init__(self, poster: Widget) -> None:
        self._poster = poster

    def start(self) -> None:
        asyncio.ensure_future(self._poll())

    async def _poll(self) -> None:
        while True:
            await self._fetch()
            await asyncio.sleep(PODS_INTERVAL)

    async def _fetch(self) -> None:
        # Attempt connection first so we can distinguish "not running" from other errors
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(SERVICE_HOST, SERVICE_PORT), timeout=2.0
            )
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):  # fmt: skip
            self._poster.post_message(
                ClusterStateUpdated(
                    ClusterState(service_error="lobot-collector is not running"),
                    source="service",
                )
            )
            return

        try:
            writer.write(b"GET /api/state HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            await writer.drain()
            content_length = None
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if not line or line in (b"\r\n", b"\n"):
                    break
                if line.lower().startswith(b"content-length:"):
                    content_length = int(line.split(b":", 1)[1].strip())
            if content_length is not None:
                body = await asyncio.wait_for(reader.readexactly(content_length), timeout=10.0)
            else:
                body = await asyncio.wait_for(reader.read(-1), timeout=10.0)
            state = ClusterState.from_dict(json.loads(body))
            self._poster.post_message(ClusterStateUpdated(state, source="service"))
        except Exception as e:
            self._poster.post_message(
                ClusterStateUpdated(
                    ClusterState(service_error=f"collector error: {type(e).__name__}"),
                    source="service",
                )
            )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def force_refresh(self) -> None:
        await self._fetch()
