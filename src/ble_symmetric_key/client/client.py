"""
BLE GATT Client for symmetric key authentication.

Uses the bleak library to connect to a BLE peripheral (reader) and
perform credential communication.
"""

import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from .protocol import (
    AuthRequestBuilder,
    AuthResponseParser,
    CredentialBuilder,
    parse_credential_response,
    MessageType,
)

logger = logging.getLogger(__name__)

# GATT UUIDs (must match server)
CREDENTIAL_SERVICE_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
DATA_TRANSFER_CHAR_UUID = "b2c3d4e5-f678-90ab-cdef-234567890abc"

# Timeouts (seconds)
SCAN_TIMEOUT = 30.0  # Extended for better service discovery
RESPONSE_TIMEOUT = 3.0


@dataclass
class ClientConfig:
    """Client configuration."""
    device_id: bytes  # 16 bytes
    device_key: bytes  # 16 bytes
    credential: str   # Credential string to present


@dataclass
class Result:
    """Operation result."""
    success: bool
    message: str


class CredentialClient:
    """
    BLE GATT Client for credential communication.

    Implements the client-side authentication protocol and credential transfer.
    """

    def __init__(self, config: ClientConfig):
        """
        Initialize the client.

        Args:
            config: Client configuration with device ID, key, and credential
        """
        self.config = config
        self._notification_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._nonce_m: Optional[bytes] = None

    def _notification_handler(
        self,
        characteristic: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        """Handle incoming notifications."""
        logger.debug(f"Notification received ({len(data)} bytes): {data.hex()}")
        self._notification_queue.put_nowait(bytes(data))

    async def _wait_for_response(self, timeout: float = RESPONSE_TIMEOUT) -> Optional[bytes]:
        """Wait for a notification response with timeout."""
        try:
            return await asyncio.wait_for(self._notification_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def present_credential(self) -> Result:
        """
        Perform the full credential presentation flow.

        1. Scan for reader
        2. Connect
        3. Subscribe to notifications
        4. Authenticate
        5. Send credential
        6. Return result

        Returns:
            Result with success status and message
        """
        # 1. Scan for reader
        logger.info(f"Scanning for reader (service: {CREDENTIAL_SERVICE_UUID})...")
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: CREDENTIAL_SERVICE_UUID.lower() in [
                s.lower() for s in (ad.service_uuids or [])
            ],
            timeout=SCAN_TIMEOUT,
        )

        if device is None:
            logger.error("No reader found")
            return Result(success=False, message="No reader found")

        logger.info(f"Found reader: {device.name} ({device.address})")

        # 2. Connect and perform protocol
        async with BleakClient(device) as client:
            logger.info("Connected to reader")

            # Request higher MTU if supported
            try:
                mtu = client.mtu_size
                logger.info(f"MTU size: {mtu}")
            except Exception:
                pass

            # 3. Subscribe to notifications
            logger.info("Subscribing to notifications...")
            await client.start_notify(DATA_TRANSFER_CHAR_UUID, self._notification_handler)

            # Small delay to ensure subscription is active
            await asyncio.sleep(0.1)

            # 4. Authenticate
            auth_result = await self._authenticate(client)
            if not auth_result.success:
                return auth_result

            # 5. Send credential
            cred_result = await self._send_credential(client)
            return cred_result

    async def _authenticate(self, client: BleakClient) -> Result:
        """Perform mutual authentication with the reader."""
        logger.info("Starting authentication...")

        # Build AUTH_REQUEST
        builder = AuthRequestBuilder(
            device_id=self.config.device_id,
            device_key=self.config.device_key,
        )
        auth_request, nonce_m = builder.build()
        self._nonce_m = nonce_m

        logger.debug(f"Device ID: {self.config.device_id.hex()}")
        logger.debug(f"Nonce_M: {nonce_m.hex()}")
        logger.debug(f"AUTH_REQUEST ({len(auth_request)} bytes): {auth_request.hex()}")

        # Send AUTH_REQUEST
        logger.info("Sending AUTH_REQUEST...")
        await client.write_gatt_char(
            DATA_TRANSFER_CHAR_UUID,
            auth_request,
            response=False,  # Write without response
        )

        # Wait for AUTH_RESPONSE
        logger.info("Waiting for AUTH_RESPONSE...")
        response = await self._wait_for_response(RESPONSE_TIMEOUT)

        if response is None:
            logger.error("Authentication timeout")
            return Result(success=False, message="Authentication timeout")

        logger.debug(f"AUTH_RESPONSE ({len(response)} bytes): {response.hex()}")

        # Parse and verify response
        parser = AuthResponseParser(device_key=self.config.device_key)
        success, nonce_r, message = parser.parse(response, nonce_m)

        if success:
            logger.info(f"Authentication successful. Nonce_R: {nonce_r.hex()}")
        else:
            logger.error(f"Authentication failed: {message}")

        return Result(success=success, message=message)

    async def _send_credential(self, client: BleakClient) -> Result:
        """Send credential to the reader."""
        logger.info("Sending credential...")

        # Build CREDENTIAL
        builder = CredentialBuilder(device_key=self.config.device_key)
        credential_msg = builder.build(self.config.credential)

        logger.debug(f"CREDENTIAL ({len(credential_msg)} bytes): {credential_msg.hex()}")

        # Send CREDENTIAL
        await client.write_gatt_char(
            DATA_TRANSFER_CHAR_UUID,
            credential_msg,
            response=False,
        )

        # Wait for CREDENTIAL_RESPONSE
        logger.info("Waiting for CREDENTIAL_RESPONSE...")
        response = await self._wait_for_response(RESPONSE_TIMEOUT)

        if response is None:
            logger.error("Credential response timeout")
            return Result(success=False, message="Response timeout")

        logger.debug(f"CREDENTIAL_RESPONSE ({len(response)} bytes): {response.hex()}")

        # Parse response
        success, message = parse_credential_response(response)

        if success:
            logger.info(f"Credential accepted: {message}")
        else:
            logger.error(f"Credential rejected: {message}")

        return Result(success=success, message=message)


# =============================================================================
# POC Configuration
# =============================================================================

# POC Device ID (fixed for reproducibility)
# In production, this would be assigned during device enrollment
POC_DEVICE_ID = bytes.fromhex("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4")

# POC Device Key (derived from master key + device ID)
# Run `python -m ble_symmetric_key.client.derive_key` to compute this
# Master Key: 00112233445566778899aabbccddeeff
# Device ID:  a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
# This will be computed by derive_key.py
# POC_DEVICE_KEY: Optional[bytes] = None  # Set after running derive_key.py
POC_DEVICE_KEY = bytes.fromhex("13f75379273f324d31335278a66062af")


def get_poc_config(credential: str, device_key_hex: Optional[str] = None) -> ClientConfig:
    """
    Get POC client configuration.

    Args:
        credential: Credential string to present
        device_key_hex: Device key in hex (if not using derive_key.py)

    Returns:
        ClientConfig for POC testing
    """
    if device_key_hex:
        device_key = bytes.fromhex(device_key_hex)
    elif POC_DEVICE_KEY:
        device_key = POC_DEVICE_KEY
    else:
        raise ValueError(
            "Device key not configured. Run 'python -m ble_symmetric_key.client.derive_key' "
            "to compute the device key, or provide --device-key argument."
        )

    return ClientConfig(
        device_id=POC_DEVICE_ID,
        device_key=device_key,
        credential=credential,
    )


async def main(
    credential: str,
    device_key_hex: Optional[str] = None,
    verbose: bool = False,
) -> int:
    """
    Main entry point for the client.

    Args:
        credential: Credential string to present
        device_key_hex: Optional device key in hex
        verbose: Enable verbose logging

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        config = get_poc_config(credential, device_key_hex)
    except ValueError as e:
        logger.error(str(e))
        return 1

    logger.info(f"Device ID: {config.device_id.hex()}")
    logger.info(f"Credential: {config.credential}")

    client = CredentialClient(config)
    result = await client.present_credential()

    print()
    if result.success:
        print(f"✓ {result.message}")
        return 0
    else:
        print(f"✗ {result.message}")
        return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BLE GATT Credential Client")
    parser.add_argument(
        "--credential",
        type=str,
        default="test-credential-12345",
        help="Credential string to present",
    )
    parser.add_argument(
        "--device-key",
        type=str,
        help="Device key in hex format (32 characters)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.credential, args.device_key, args.verbose)))
