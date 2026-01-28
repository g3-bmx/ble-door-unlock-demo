"""GATT Server implementation using bless."""

import asyncio
import json
import logging
from typing import Any, Callable

from bless import BlessServer, BlessGATTCharacteristic, GATTCharacteristicProperties, GATTAttributePermissions

logger = logging.getLogger(__name__)

# UUIDs matching the existing intercom implementation
SERVICE_UUID = "E7B2C021-5D07-4D0B-9C20-223488C8B012"
CHAR_UUID = "E7B2C021-5D07-4D0B-9C20-223488C8B013"


def default_write_handler(data: bytes) -> None:
    """Default handler for incoming write requests."""
    try:
        data_str = data.decode("utf-8")
        logger.info(f"Received data: {data_str}")

        try:
            json_data = json.loads(data_str)
            logger.info(f"Parsed JSON: {json_data}")
        except json.JSONDecodeError:
            logger.info("Received plain text (not JSON)")

    except Exception as e:
        logger.error(f"Error processing data: {e}")


class IntercomGattServer:
    """Cross-platform BLE GATT server for the intercom."""

    def __init__(
        self,
        name: str = "Intercom",
        write_handler: Callable[[bytes], None] | None = None,
    ):
        self.name = name
        self.write_handler = write_handler or default_write_handler
        self.server: BlessServer | None = None
        self._running = False

    def _on_read(self, characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
        """Handle read requests."""
        logger.debug(f"Read request for {characteristic.uuid}")
        return bytearray(b"")

    def _on_write(self, characteristic: BlessGATTCharacteristic, value: Any, **kwargs) -> None:
        """Handle write requests."""
        logger.debug(f"Write request for {characteristic.uuid}: {value}")
        if isinstance(value, (bytes, bytearray)):
            self.write_handler(bytes(value))

    async def start(self) -> None:
        """Start the GATT server and begin advertising."""
        logger.info(f"Starting GATT server: {self.name}")

        self.server = BlessServer(name=self.name, loop=asyncio.get_event_loop())
        self.server.read_request_func = self._on_read
        self.server.write_request_func = self._on_write

        await self.server.add_new_service(SERVICE_UUID)

        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_UUID,
            GATTCharacteristicProperties.read
            | GATTCharacteristicProperties.write
            | GATTCharacteristicProperties.write_without_response,
            None,
            GATTAttributePermissions.readable | GATTAttributePermissions.writeable,
        )

        await self.server.start()
        self._running = True

        logger.info(f"GATT server started")
        logger.info(f"  Service UUID: {SERVICE_UUID}")
        logger.info(f"  Characteristic UUID: {CHAR_UUID}")

    async def stop(self) -> None:
        """Stop the GATT server."""
        if self.server and self._running:
            await self.server.stop()
            self._running = False
            logger.info("GATT server stopped")

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._running
