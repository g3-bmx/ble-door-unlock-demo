"""
BLE GATT Server for symmetric key authentication.

Uses the bless library to create a BLE peripheral that handles
credential communication with mobile devices.
"""

import asyncio
import logging
import signal
import sys
from typing import Any, Optional

from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

from .state import ProtocolHandler

logger = logging.getLogger(__name__)

# GATT UUIDs
CREDENTIAL_SERVICE_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
DATA_TRANSFER_CHAR_UUID = "b2c3d4e5-f678-90ab-cdef-234567890abc"

# Server configuration
SERVER_NAME = "CRED-READER"
DEFAULT_MTU = 512


class CredentialGATTServer:
    """
    BLE GATT Server for credential communication.

    Implements a single-service, single-characteristic pattern for
    bidirectional communication using write and notify operations.
    """

    def __init__(self, master_key: bytes, name: str = SERVER_NAME):
        """
        Initialize the GATT server.

        Args:
            master_key: 16-byte master key for deriving device keys
            name: Advertised device name
        """
        self.master_key = master_key
        self.name = name
        self.server: Optional[BlessServer] = None
        self.protocol_handler = ProtocolHandler(master_key)
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        """Start the GATT server and begin advertising."""
        self._loop = asyncio.get_event_loop()
        self._running = True

        logger.info(f"Starting GATT server '{self.name}'")
        logger.info(f"Service UUID: {CREDENTIAL_SERVICE_UUID}")
        logger.info(f"Characteristic UUID: {DATA_TRANSFER_CHAR_UUID}")

        # Create the server
        self.server = BlessServer(name=self.name, loop=self._loop)

        # Set up callbacks
        self.server.read_request_func = self._handle_read
        self.server.write_request_func = self._handle_write

        # Add the GATT service and characteristic
        await self._setup_gatt()

        # Start advertising
        await self.server.start()
        logger.info("GATT server started and advertising")

    async def _setup_gatt(self) -> None:
        """Configure the GATT service and characteristic."""
        if self.server is None:
            raise RuntimeError("Server not initialized")

        # Add service
        await self.server.add_new_service(CREDENTIAL_SERVICE_UUID)

        # Add data transfer characteristic with Write Without Response + Notify
        char_flags = (
            GATTCharacteristicProperties.write_without_response |
            GATTCharacteristicProperties.notify
        )
        permissions = (
            GATTAttributePermissions.writeable
        )

        await self.server.add_new_characteristic(
            CREDENTIAL_SERVICE_UUID,
            DATA_TRANSFER_CHAR_UUID,
            char_flags,
            None,  # Initial value
            permissions,
        )

        logger.info("GATT service and characteristic configured")

    def _handle_read(
        self,
        characteristic: BlessGATTCharacteristic,
        **kwargs: Any,
    ) -> bytearray:
        """
        Handle read requests.

        Note: Our characteristic doesn't support reads, but we implement
        this to satisfy the bless interface.
        """
        logger.debug(f"Read request for {characteristic.uuid} (not supported)")
        return bytearray()

    def _handle_write(
        self,
        characteristic: BlessGATTCharacteristic,
        value: bytes,
        **kwargs: Any,
    ) -> None:
        """
        Handle write requests to the data transfer characteristic.

        Processes the incoming message through the protocol handler
        and sends a response via notification.
        """
        if characteristic.uuid != DATA_TRANSFER_CHAR_UUID:
            logger.warning(f"Write to unknown characteristic: {characteristic.uuid}")
            return

        # Extract client identifier (use a default for now as bless doesn't expose client ID)
        # In a real implementation, you'd track this per-connection
        client_id = "default_client"

        logger.info(f"Received write ({len(value)} bytes): {value.hex()}")

        # Ensure we're in connected state if this is first message
        session = self.protocol_handler.get_session(client_id)
        if session.state.name == "IDLE":
            self.protocol_handler.on_connect(client_id)

        # Process the message
        response = self.protocol_handler.handle_message(client_id, bytes(value))

        if response:
            # Send response via notification
            asyncio.create_task(self._send_notification(response))

    async def _send_notification(self, data: bytes) -> None:
        """Send a notification with the given data."""
        if self.server is None:
            logger.error("Cannot send notification: server not initialized")
            return

        logger.info(f"Sending notification ({len(data)} bytes): {data.hex()}")

        # Get the characteristic and set its value
        char = self.server.get_characteristic(DATA_TRANSFER_CHAR_UUID)
        if char is None:
            logger.error(f"Characteristic {DATA_TRANSFER_CHAR_UUID} not found")
            return

        char.value = bytearray(data)

        # Update triggers the notification to subscribed clients
        self.server.update_value(CREDENTIAL_SERVICE_UUID, DATA_TRANSFER_CHAR_UUID)

    async def stop(self) -> None:
        """Stop the GATT server."""
        self._running = False
        if self.server:
            await self.server.stop()
            logger.info("GATT server stopped")

    async def run_forever(self) -> None:
        """Run the server until interrupted."""
        await self.start()

        # Set up signal handlers for graceful shutdown
        def signal_handler() -> None:
            logger.info("Shutdown signal received")
            self._running = False

        if sys.platform != "win32":
            self._loop.add_signal_handler(signal.SIGINT, signal_handler)
            self._loop.add_signal_handler(signal.SIGTERM, signal_handler)

        # Keep running until stopped
        try:
            while self._running:
                await asyncio.sleep(1)
        finally:
            await self.stop()


async def main(master_key_hex: Optional[str] = None) -> None:
    """
    Main entry point for the GATT server.

    Args:
        master_key_hex: Optional hex-encoded master key.
                       If not provided, uses a default POC key.
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # POC: Use a hardcoded master key if not provided
    if master_key_hex:
        master_key = bytes.fromhex(master_key_hex)
    else:
        # Default POC master key (DO NOT USE IN PRODUCTION)
        master_key = bytes.fromhex("00112233445566778899aabbccddeeff")
        logger.warning("Using default POC master key - DO NOT USE IN PRODUCTION")

    if len(master_key) != 16:
        raise ValueError("Master key must be 16 bytes (32 hex characters)")

    logger.info(f"Master key: {master_key.hex()}")

    # Create and run the server
    server = CredentialGATTServer(master_key=master_key)
    await server.run_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BLE GATT Credential Server")
    parser.add_argument(
        "--master-key",
        type=str,
        help="Master key in hex format (32 characters)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.master_key))
