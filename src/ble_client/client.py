"""BLE Client implementation using bleak to simulate a mobile device."""

import asyncio
import logging

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from cryptography.hazmat.primitives.serialization import load_pem_private_key

logger = logging.getLogger(__name__)

# Door Access Service UUID
SERVICE_UUID = "12340000-1234-5678-9ABC-DEF012345678"

# Challenge Characteristic - receives nonce from server
CHALLENGE_CHAR_UUID = "12340000-1234-5678-9ABC-DEF012345235"

# Response Characteristic - sends signed nonce to server
RESPONSE_CHAR_UUID = "12340000-1234-5678-9ABC-DEF012345236"

# -----------------------------------------------------------------
# Client public/private key pair. Hardcoding for demo purposes!
# -----------------------------------------------------------------
CLIENT_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAJGuguvPqLj68i6omk5KGOmPOONqotufeQRAgh6UccnE=
-----END PUBLIC KEY-----
"""

CLIENT_PRIVATE_KEY_PEM = b"""-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIPn3kRox+MbIxWFWcLxbwBGbLjC9HfT4pGLQrWSCxMRj
-----END PRIVATE KEY-----
"""


class IntercomClient:
    """BLE client that simulates a mobile device connecting to the Intercom GATT server."""

    def __init__(self, device_name: str = "Intercom"):
        self.device_name = device_name
        self.client: BleakClient | None = None
        self.device: BLEDevice | None = None
        self.challenge_nonce: bytes | None = None
        self._challenge_received: asyncio.Event = asyncio.Event()

    async def scan(self, timeout: float = 10.0) -> BLEDevice | None:
        """Scan for the target device by name."""
        logger.info(f"Scanning for device: {self.device_name}")

        self.device = await BleakScanner.find_device_by_name(
            self.device_name, timeout=timeout
        )

        if self.device:
            logger.info(f"Found device: {self.device.name} ({self.device.address})")
        else:
            logger.warning(f"Device '{self.device_name}' not found")

        return self.device

    async def connect(self) -> bool:
        """Connect to the discovered device."""
        if not self.device:
            logger.error("No device to connect to. Run scan() first.")
            return False

        logger.info(f"Connecting to {self.device.address}...")
        self.client = BleakClient(self.device)

        try:
            await self.client.connect()
            logger.info(f"Connected: {self.client.is_connected}")
            return self.client.is_connected
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            logger.info("Disconnected")
        # Reset challenge state
        self.challenge_nonce = None
        self._challenge_received.clear()

    async def subscribe_to_challenge(self) -> bool:
        """Subscribe to the challenge characteristic to receive the nonce."""
        if not self.client or not self.client.is_connected:
            logger.error("Not connected to device")
            return False

        def challenge_handler(sender, data: bytearray):
            """Handle incoming challenge nonce notification."""
            self.challenge_nonce = bytes(data)
            logger.info(f"Received challenge nonce: {self.challenge_nonce.hex()} ({len(self.challenge_nonce)} bytes)")
            self._challenge_received.set()

        try:
            await self.client.start_notify(CHALLENGE_CHAR_UUID, challenge_handler)
            logger.info("Subscribed to challenge characteristic")
            return True
        except Exception as e:
            logger.error(f"Failed to subscribe to challenge: {e}")
            return False

    async def wait_for_challenge(self, timeout: float = 10.0) -> bytes | None:
        """Wait for the challenge nonce to be received.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            The challenge nonce if received, None if timeout
        """
        try:
            await asyncio.wait_for(self._challenge_received.wait(), timeout=timeout)
            return self.challenge_nonce
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for challenge nonce ({timeout}s)")
            return None

    async def get_challenge(self, timeout: float = 10.0) -> bytes | None:
        """Subscribe to challenge and wait for the nonce.

        This is a convenience method that combines subscribe_to_challenge()
        and wait_for_challenge().

        Returns:
            The 16-byte challenge nonce, or None if failed
        """
        if not await self.subscribe_to_challenge():
            return None
        return await self.wait_for_challenge(timeout=timeout)

    async def read_challenge(self) -> bytes | None:
        """Read the challenge nonce directly (alternative to notifications)."""
        if not self.client or not self.client.is_connected:
            logger.error("Not connected to device")
            return None

        try:
            data = await self.client.read_gatt_char(CHALLENGE_CHAR_UUID)
            self.challenge_nonce = bytes(data)
            logger.info(f"Read challenge nonce: {self.challenge_nonce.hex()} ({len(self.challenge_nonce)} bytes)")
            return self.challenge_nonce
        except Exception as e:
            logger.error(f"Failed to read challenge: {e}")
            return None

    def sign_challenge(self, nonce: bytes) -> bytes:
        """Sign the challenge nonce with the client's private key.

        Args:
            nonce: The challenge nonce received from the server

        Returns:
            The Ed25519 signature (64 bytes)
        """
        logger.info(f"[AUTH] Signing nonce: {nonce.hex()}")

        # Load the private key
        private_key = load_pem_private_key(CLIENT_PRIVATE_KEY_PEM, password=None)

        # Sign the nonce
        signature = private_key.sign(nonce)
        logger.info(f"[AUTH] Generated signature: {signature.hex()} ({len(signature)} bytes)")

        return signature

    async def send_response(self, signature: bytes) -> bool:
        """Send the signed response to the server.

        Args:
            signature: The Ed25519 signature of the challenge nonce

        Returns:
            True if write succeeded, False otherwise
        """
        if not self.client or not self.client.is_connected:
            logger.error("Not connected to device")
            return False

        try:
            logger.info(f"[AUTH] Writing signature to response characteristic...")
            await self.client.write_gatt_char(RESPONSE_CHAR_UUID, signature)
            logger.info(f"[AUTH] Signature sent successfully")
            return True
        except Exception as e:
            logger.error(f"[AUTH] Failed to send signature: {e}")
            return False

    async def authenticate(self, timeout: float = 10.0) -> bool:
        """Perform full challenge-response authentication.

        This is a convenience method that:
        1. Subscribes to challenge notifications
        2. Waits for the challenge nonce
        3. Signs the nonce with the client's private key
        4. Sends the signature to the server

        Returns:
            True if authentication completed (signature sent), False otherwise
        """
        logger.info("=" * 60)
        logger.info("[AUTH] Starting challenge-response authentication...")
        logger.info("=" * 60)

        # Step 1: Get the challenge nonce
        logger.info("[AUTH] Step 1: Waiting for challenge nonce...")
        nonce = await self.get_challenge(timeout=timeout)
        if not nonce:
            logger.error("[AUTH] Failed to receive challenge nonce")
            return False
        logger.info(f"[AUTH] Received nonce: {nonce.hex()}")

        # Step 2: Sign the nonce
        logger.info("[AUTH] Step 2: Signing the nonce...")
        signature = self.sign_challenge(nonce)

        # Step 3: Send the signature
        logger.info("[AUTH] Step 3: Sending signature to server...")
        if not await self.send_response(signature):
            logger.error("[AUTH] Failed to send signature")
            return False

        logger.info("=" * 60)
        logger.info("[AUTH] Authentication flow completed!")
        logger.info("=" * 60)
        return True

    async def __aenter__(self):
        """Async context manager entry."""
        await self.scan()
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


async def scan_all_devices(timeout: float = 10.0) -> list[BLEDevice]:
    """Scan and list all nearby BLE devices."""
    logger.info(f"Scanning for all BLE devices ({timeout}s)...")
    devices = await BleakScanner.discover(timeout=timeout)

    for device in devices:
        logger.info(f"  {device.name or 'Unknown'}: {device.address}")

    return devices
