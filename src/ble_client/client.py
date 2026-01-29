"""BLE Client implementation using bleak to simulate a mobile device."""

import asyncio
import logging

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

logger = logging.getLogger(__name__)

# Door Access Service UUID
SERVICE_UUID = "12340000-1234-5678-9ABC-DEF012345678"

# Challenge Characteristic - receives nonce from server
CHALLENGE_CHAR_UUID = "12340000-1234-5678-9ABC-DEF012345235"

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
