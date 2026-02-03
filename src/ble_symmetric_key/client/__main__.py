"""
Entry point for running the GATT client as a module.

Usage:
    python -m ble_symmetric_key.client --credential "my-credential" --device-key <hex>
    python -m ble_symmetric_key.client -v  # verbose mode
"""

import asyncio
import argparse
import sys

from .client import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BLE GATT Credential Client")
    parser.add_argument(
        "--credential",
        type=str,
        default="prod-pin_access_tool-7603498",
        help="Credential string to present (default: test-credential-12345)",
    )
    parser.add_argument(
        "--device-key",
        type=str,
        help="Device key in hex format (32 characters). "
             "Run 'python -m ble_symmetric_key.client.derive_key' to compute.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.credential, args.device_key, args.verbose)))
