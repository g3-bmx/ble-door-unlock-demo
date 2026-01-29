"""BLE Client implementation using bleak to simulate a mobile device."""

import asyncio
import json
import logging
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

logger = logging.getLogger(__name__)

# UUIDs matching the GATT server
SERVICE_UUID = "E7B2C021-5D07-4D0B-9C20-223488C8B012"
CHAR_UUID = "E7B2C021-5D07-4D0B-9C20-223488C8B013"


class IntercomClient:
    """BLE client that simulates a mobile device connecting to the Intercom GATT server."""

    def __init__(self, device_name: str = "Intercom"):
        self.device_name = device_name
        self.client: BleakClient | None = None
        self.device: BLEDevice | None = None

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

    async def write(self, data: bytes | str | dict) -> bool:
        """Write data to the characteristic.

        Args:
            data: Can be bytes, a string, or a dict (will be JSON-encoded)
        """
        if not self.client or not self.client.is_connected:
            logger.error("Not connected to device")
            return False

        # Convert data to bytes
        if isinstance(data, dict):
            data = json.dumps(data).encode("utf-8")
        elif isinstance(data, str):
            data = data.encode("utf-8")

        try:
            await self.client.write_gatt_char(CHAR_UUID, data)
            logger.info(f"Sent: {data}")
            return True
        except Exception as e:
            logger.error(f"Write failed: {e}")
            return False

    async def read(self) -> bytes | None:
        """Read data from the characteristic."""
        if not self.client or not self.client.is_connected:
            logger.error("Not connected to device")
            return None

        try:
            data = await self.client.read_gatt_char(CHAR_UUID)
            logger.info(f"Received: {data}")
            return data
        except Exception as e:
            logger.error(f"Read failed: {e}")
            return None

    async def subscribe(self, callback: Callable[[bytes], None]) -> bool:
        """Subscribe to notifications from the characteristic."""
        if not self.client or not self.client.is_connected:
            logger.error("Not connected to device")
            return False

        def notification_handler(sender, data: bytearray):
            logger.debug(f"Notification from {sender}: {data}")
            callback(bytes(data))

        try:
            await self.client.start_notify(CHAR_UUID, notification_handler)
            logger.info("Subscribed to notifications")
            return True
        except Exception as e:
            logger.error(f"Subscribe failed: {e}")
            return False

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
