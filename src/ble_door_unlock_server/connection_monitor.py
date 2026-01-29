"""Connection monitor utility for detecting BLE client disconnections."""

import asyncio
import logging
from typing import Callable, Protocol

logger = logging.getLogger(__name__)


class BLEServer(Protocol):
    """Protocol for BLE servers that support connection checking."""

    async def is_connected(self) -> bool:
        """Check if any clients are connected."""
        ...


class ConnectionMonitor:
    """Monitors BLE connection status and triggers callbacks on disconnect."""

    def __init__(
        self,
        server: BLEServer,
        on_disconnect: Callable[[], None],
        poll_interval: float = 1.0,
    ):
        """Initialize the connection monitor.

        Args:
            server: BLE server instance with is_connected() method
            on_disconnect: Callback to invoke when a client disconnects
            poll_interval: How often to check connection status (seconds)
        """
        self._server = server
        self._on_disconnect = on_disconnect
        self._poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._running = False
        self._was_connected = False

    async def start(self) -> None:
        """Start monitoring for disconnections."""
        if self._task:
            await self.stop()

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.debug("Connection monitor started")

    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.debug("Connection monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop that checks connection status."""
        while self._running:
            await asyncio.sleep(self._poll_interval)

            try:
                is_connected = await self._server.is_connected()

                # Detect connect: was not connected, now connected
                if not self._was_connected and is_connected:
                    logger.info("Client connected")

                # Detect disconnect: was connected, now not connected
                if self._was_connected and not is_connected:
                    logger.info("Client disconnected")
                    self._on_disconnect()

                self._was_connected = is_connected
            except Exception as e:
                logger.error(f"Error checking connection status: {e}")
