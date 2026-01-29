"""GATT Server implementation using bless."""

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from bless import BlessServer, BlessGATTCharacteristic, GATTCharacteristicProperties, GATTAttributePermissions

from .connection_monitor import ConnectionMonitor

logger = logging.getLogger(__name__)

# Enable debug logging for bless library
logging.getLogger("bless").setLevel(logging.DEBUG)

# Door Access Service UUID
SERVICE_UUID = "12340000-1234-5678-9ABC-DEF012345678"

# Challenge Characteristic - provides fresh nonce for each connection
CHALLENGE_CHAR_UUID = "12340000-1234-5678-9ABC-DEF012345235"

# Nonce timeout in seconds
NONCE_TIMEOUT_SECONDS = 30

# -----------------------------------------------------------------
# Server public/private key pair. Hardcoding for demo purposes!
# -----------------------------------------------------------------
SERVER_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAs9bGEW7mCKAwC8Zzu51nVeGNcgvtRUpe/4P9qCyH6ns=
-----END PUBLIC KEY-----
"""

SERVER_PRIVATE_KEY_PEM = b"""-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIBSMFFtpYj6Q0hKz09rn/8Z/9o+OQ0ppC+AogwlcRBIz
-----END PRIVATE KEY-----
"""




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
        self._connection_monitor: ConnectionMonitor | None = None

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

    def _on_client_connect(self) -> None:
        """Handle client connection by generating and sending a nonce."""
        logger.info("[CONNECT] Client connected, generating nonce")
        self._generate_nonce()
        asyncio.create_task(self._start_nonce_timeout())
        asyncio.create_task(self._send_challenge_notification())

    def _on_client_disconnect(self) -> None:
        """Handle client disconnection by clearing the nonce."""
        logger.info("Client disconnected, clearing nonce")
        self._clear_nonce()

    def _clear_nonce(self) -> None:
        """Clear the current nonce (on disconnect)."""
        if self._nonce_state:
            logger.info(f"Clearing nonce: {self._nonce_state.value.hex()}")
            self._nonce_state = None

        # Cancel the timeout task since nonce is cleared
        if self._nonce_timeout_task:
            self._nonce_timeout_task.cancel()
            self._nonce_timeout_task = None

    async def _send_challenge_notification(self) -> None:
        """Send the current nonce as a notification."""
        logger.info(f"[NOTIFY] Attempting to send notification, server={self.server is not None}, nonce_state={self._nonce_state is not None}")
        if not self.server or not self._nonce_state:
            logger.warning("[NOTIFY] Cannot send - server or nonce_state is None")
            return

        nonce = self._nonce_state.value
        char = self.server.get_characteristic(CHALLENGE_CHAR_UUID)
        logger.info(f"[NOTIFY] Got characteristic: {char}, uuid={CHALLENGE_CHAR_UUID}")
        if char:
            char.value = bytearray(nonce)
            logger.info(f"[NOTIFY] Set characteristic value to: {nonce.hex()}")
            result = self.server.update_value(SERVICE_UUID, CHALLENGE_CHAR_UUID)
            # Handle both sync (BlueZ) and async (CoreBluetooth) backends
            if asyncio.iscoroutine(result):
                result = await result
            logger.info(f"[NOTIFY] update_value result: {result}")
        else:
            logger.error(f"[NOTIFY] Could not find characteristic {CHALLENGE_CHAR_UUID}")

    def _on_read(self, characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
        """Handle read requests."""
        logger.info(f"[READ] characteristic={characteristic.uuid} kwargs={kwargs}")

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
        logger.info(f"[WRITE] characteristic={characteristic.uuid} value={value} kwargs={kwargs}")

    def _on_subscribe(self, characteristic: BlessGATTCharacteristic, **kwargs) -> None:
        """Handle subscription changes (notifications/indications)."""
        char_uuid = str(characteristic.uuid).upper()
        logger.info(f"[SUBSCRIBE] characteristic={characteristic.uuid} kwargs={kwargs}")

        # Handle Challenge characteristic subscription
        if CHALLENGE_CHAR_UUID.upper() in char_uuid or char_uuid in CHALLENGE_CHAR_UUID.upper():
            logger.info("Client subscribed to challenge characteristic")
            # Generate fresh nonce for this connection and send it
            self._generate_nonce()
            asyncio.create_task(self._start_nonce_timeout())
            asyncio.create_task(self._send_challenge_notification())

    async def start(self) -> None:
        """Start the GATT server and begin advertising."""
        logger.info(f"Starting GATT server: {self.name}")

        self.server = BlessServer(
            name=self.name,
            loop=asyncio.get_event_loop(),
            on_read=self._on_read,
            on_write=self._on_write,
            on_subscribe=self._on_subscribe,
        )

        await self.server.add_new_service(SERVICE_UUID)

        # Challenge Characteristic (Read, Notify)
        # Initial value is zeros - real nonce is generated when client subscribes
        await self.server.add_new_characteristic(
            SERVICE_UUID,
            CHALLENGE_CHAR_UUID,
            GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
            bytearray(16),
            GATTAttributePermissions.readable,
        )

        # Set subscription callback on the characteristic directly
        challenge_char = self.server.get_characteristic(CHALLENGE_CHAR_UUID)
        logger.info(f"[SETUP] Got challenge characteristic: {challenge_char}")
        if challenge_char:
            challenge_char.on_subscribe = self._on_subscribe
            logger.info(f"[SETUP] Set on_subscribe callback on challenge characteristic")
            logger.info(f"[SETUP] Characteristic properties: {challenge_char.properties}")
            logger.info(f"[SETUP] Characteristic on_subscribe: {challenge_char.on_subscribe}")
        else:
            logger.error(f"[SETUP] Could not find challenge characteristic!")

        logger.info(f"[SETUP] Starting server...")
        await self.server.start()
        logger.info(f"[SETUP] Server started")
        self._running = True

        # Start connection monitor to detect connects and disconnects
        # Use faster polling (0.25s) to quickly detect connections
        self._connection_monitor = ConnectionMonitor(
            server=self.server,
            on_disconnect=self._on_client_disconnect,
            on_connect=self._on_client_connect,
            poll_interval=0.25,
        )
        await self._connection_monitor.start()

        logger.info("GATT server started")
        logger.info(f"  Service UUID: {SERVICE_UUID}")
        logger.info(f"  Challenge Characteristic UUID: {CHALLENGE_CHAR_UUID}")

    async def stop(self) -> None:
        """Stop the GATT server."""
        self._running = False

        # Stop connection monitor
        if self._connection_monitor:
            await self._connection_monitor.stop()

        # Cancel nonce timeout task
        if self._nonce_timeout_task:
            self._nonce_timeout_task.cancel()
            try:
                await self._nonce_timeout_task
            except asyncio.CancelledError:
                pass

        if self.server:
            await self.server.stop()
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
