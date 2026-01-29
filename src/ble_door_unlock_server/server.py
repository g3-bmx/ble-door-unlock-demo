"""GATT Server implementation using bless."""

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from bless import BlessServer, BlessGATTCharacteristic, GATTCharacteristicProperties, GATTAttributePermissions

logger = logging.getLogger(__name__)

# Door Access Service UUID
SERVICE_UUID = "12340000-1234-5678-9ABC-DEF012345678"

# Challenge Characteristic - provides fresh nonce for each connection
CHALLENGE_CHAR_UUID = "12340000-1234-5678-9ABC-DEF012345235"

# Nonce timeout in seconds
NONCE_TIMEOUT_SECONDS = 30


@dataclass
class NonceState:
    """Tracks the current challenge nonce state."""
    value: bytes
    created_at: float
    used: bool = False

    def is_expired(self) -> bool:
        """Check if the nonce has expired."""
        return time.time() - self.created_at > NONCE_TIMEOUT_SECONDS

    def is_valid(self) -> bool:
        """Check if the nonce is still valid for use."""
        return not self.used and not self.is_expired()


class IntercomGattServer:
    """Cross-platform BLE GATT server for the intercom."""

    def __init__(self, name: str = "Intercom"):
        self.name = name
        self.server: BlessServer | None = None
        self._running = False
        self._nonce_state: NonceState | None = None
        self._nonce_timeout_task: asyncio.Task | None = None

    def _generate_nonce(self) -> bytes:
        """Generate a fresh 16-byte cryptographic nonce."""
        nonce = secrets.token_bytes(16)
        self._nonce_state = NonceState(value=nonce, created_at=time.time())
        logger.info(f"Generated nonce: {nonce.hex()}")
        return nonce

    def _invalidate_nonce(self) -> None:
        """Invalidate the current nonce."""
        if self._nonce_state:
            self._nonce_state.used = True
            logger.info("Nonce invalidated")

    async def _start_nonce_timeout(self) -> None:
        """Start a background task to invalidate the nonce after timeout."""
        if self._nonce_timeout_task:
            self._nonce_timeout_task.cancel()
            try:
                await self._nonce_timeout_task
            except asyncio.CancelledError:
                pass

        async def timeout_task():
            await asyncio.sleep(NONCE_TIMEOUT_SECONDS)
            if self._nonce_state and not self._nonce_state.used:
                logger.info(f"Nonce expired after {NONCE_TIMEOUT_SECONDS}s")
                self._invalidate_nonce()

        self._nonce_timeout_task = asyncio.create_task(timeout_task())

    async def _send_challenge_notification(self) -> None:
        """Send the current nonce as a notification."""
        if not self.server or not self._nonce_state:
            return

        nonce = self._nonce_state.value
        self.server.get_characteristic(CHALLENGE_CHAR_UUID).value = bytearray(nonce)
        await self.server.update_value(SERVICE_UUID, CHALLENGE_CHAR_UUID)
        logger.info(f"Sent nonce notification: {nonce.hex()}")

    def _on_read(self, characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
        """Handle read requests."""
        logger.debug(f"Read request for {characteristic.uuid}")

        # Handle Challenge characteristic read
        char_uuid = str(characteristic.uuid).upper()
        if CHALLENGE_CHAR_UUID.upper() in char_uuid or char_uuid in CHALLENGE_CHAR_UUID.upper():
            if self._nonce_state and self._nonce_state.is_valid():
                logger.info(f"Challenge read: {self._nonce_state.value.hex()}")
                return bytearray(self._nonce_state.value)
            else:
                logger.warning("Challenge read but nonce is invalid/expired")
                return bytearray(16)  # Return zeros if no valid nonce

        return bytearray(b"")

    def _on_write(self, characteristic: BlessGATTCharacteristic, value: Any, **kwargs) -> None:
        """Handle write requests."""
        logger.debug(f"Write request for {characteristic.uuid}: {value}")

    def _on_subscribe(self, characteristic: BlessGATTCharacteristic, subscribed: bool, **kwargs) -> None:
        """Handle subscription changes (notifications/indications)."""
        char_uuid = str(characteristic.uuid).upper()
        logger.info(f"Subscription change for {characteristic.uuid}: subscribed={subscribed}")

        # Handle Challenge characteristic subscription
        if CHALLENGE_CHAR_UUID.upper() in char_uuid or char_uuid in CHALLENGE_CHAR_UUID.upper():
            if subscribed:
                logger.info("Client subscribed to challenge characteristic")
                # Send nonce notification when client subscribes
                asyncio.create_task(self._send_challenge_notification())

    async def start(self) -> None:
        """Start the GATT server and begin advertising."""
        logger.info(f"Starting GATT server: {self.name}")

        # Generate initial nonce
        self._generate_nonce()
        await self._start_nonce_timeout()

        self.server = BlessServer(name=self.name, loop=asyncio.get_event_loop())
        self.server.read_request_func = self._on_read
        self.server.write_request_func = self._on_write

        await self.server.add_new_service(SERVICE_UUID)

        # Challenge Characteristic (Read, Notify)
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHALLENGE_CHAR_UUID,
            GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
            bytearray(self._nonce_state.value) if self._nonce_state else bytearray(16),
            GATTAttributePermissions.readable,
        )

        await self.server.start()
        self._running = True

        logger.info("GATT server started")
        logger.info(f"  Service UUID: {SERVICE_UUID}")
        logger.info(f"  Challenge Characteristic UUID: {CHALLENGE_CHAR_UUID}")

    async def stop(self) -> None:
        """Stop the GATT server."""
        # Cancel nonce timeout task
        if self._nonce_timeout_task:
            self._nonce_timeout_task.cancel()
            try:
                await self._nonce_timeout_task
            except asyncio.CancelledError:
                pass

        if self.server and self._running:
            await self.server.stop()
            self._running = False
            logger.info("GATT server stopped")

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._running

    @property
    def current_nonce(self) -> bytes | None:
        """Get the current nonce value if valid."""
        if self._nonce_state and self._nonce_state.is_valid():
            return self._nonce_state.value
        return None
