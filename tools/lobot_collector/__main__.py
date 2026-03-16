"""Entry point: python3 -m lobot_collector [--dev]"""

import asyncio
import logging
import signal
import sys

from .collector import ClusterCollector
from .config import DEV_MODE, SERVICE_HOST, SERVICE_PORT
from .notifier import send_shutdown_email, send_startup_email
from .server import run_server
from .writer import write_current_json


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )


async def main() -> None:
    logger = logging.getLogger("lobot_collector")
    collector = ClusterCollector()
    shutdown_event = asyncio.Event()

    def _handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, shutting down…", sig_name)
        asyncio.get_event_loop().call_soon_threadsafe(shutdown_event.set)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if DEV_MODE:
        logger.info("Dev mode — kubectl calls will be attempted (no mock data in service)")

    logger.info("Starting lobot-collector on %s:%d", SERVICE_HOST, SERVICE_PORT)
    await send_startup_email()

    # Start kubectl polling
    await collector.start()

    # Start HTTP server (runs in background; keeps the event loop busy)
    await run_server(collector)

    # Wire up writer: subscribe to state updates and write current.json on each one
    writer_queue = collector.subscribe()

    async def _writer_loop() -> None:
        while True:
            state = await writer_queue.get()
            if state.resources:  # only write when we have data
                write_current_json(state)

    asyncio.ensure_future(_writer_loop())

    logger.info("lobot-collector running — Ctrl-C or SIGTERM to stop")
    await shutdown_event.wait()

    logger.info("Shutting down…")
    await send_shutdown_email("Signal received")


if __name__ == "__main__":
    _setup_logging()
    asyncio.run(main())
