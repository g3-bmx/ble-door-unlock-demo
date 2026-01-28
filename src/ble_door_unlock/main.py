"""Entry point for the BLE GATT server."""

import asyncio
import logging
import signal
import sys

from .server import IntercomGattServer


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


async def run_server() -> None:
    """Run the GATT server until interrupted."""
    server = IntercomGattServer(name="Intercom")

    # Handle shutdown gracefully
    stop_event = asyncio.Event()

    def signal_handler():
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    await server.start()
    print("Press Ctrl+C to stop")

    await stop_event.wait()
    await server.stop()


def main() -> None:
    """Main entry point."""
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    setup_logging(verbose=verbose)

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
