"""aiohttp HTTP server: GET /api/state and GET /api/events (SSE).

Binds to 127.0.0.1 only — unreachable from outside the machine at TCP level.
"""

import asyncio
import json
import logging

from aiohttp import web

from .collector import ClusterCollector
from .config import SERVICE_HOST, SERVICE_PORT

logger = logging.getLogger(__name__)


async def handle_state(request: web.Request) -> web.Response:
    """GET /api/state — returns a snapshot of the current ClusterState as JSON."""
    collector: ClusterCollector = request.app["collector"]
    return web.Response(
        content_type="application/json",
        text=json.dumps(collector.state.to_dict()),
    )


async def handle_events(request: web.Request) -> web.StreamResponse:
    """GET /api/events — SSE stream; current state sent immediately, then on every update."""
    collector: ClusterCollector = request.app["collector"]

    response = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
    await response.prepare(request)

    queue = collector.subscribe()
    try:
        # Send current state to the client immediately on connect
        await _send_event(response, collector.state)
        # Then stream every future update
        while True:
            state = await queue.get()
            await _send_event(response, state)
    except ConnectionResetError, asyncio.CancelledError:
        pass
    finally:
        collector.unsubscribe(queue)

    return response


async def _send_event(response: web.StreamResponse, state) -> None:
    data = json.dumps(state.to_dict())
    await response.write(f"data: {data}\n\n".encode())


def _build_app(collector: ClusterCollector) -> web.Application:
    app = web.Application()
    app["collector"] = collector
    app.router.add_get("/api/state", handle_state)
    app.router.add_get("/api/events", handle_events)
    return app


async def run_server(collector: ClusterCollector) -> None:
    """Start the aiohttp server and return (it keeps running in the background)."""
    app = _build_app(collector)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, SERVICE_HOST, SERVICE_PORT)
    await site.start()
    logger.info("Listening on http://%s:%d", SERVICE_HOST, SERVICE_PORT)
