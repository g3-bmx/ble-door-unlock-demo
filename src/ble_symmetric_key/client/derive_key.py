"""
Utility to derive Device Key from Master Key + Device ID.

This simulates the enrollment process where a device receives its
derived key. In production, this would be done by a secure backend.

Usage:
    python -m ble_symmetric_key.client.derive_key
    python -m ble_symmetric_key.client.derive_key --master-key <hex> --device-id <hex>
"""

import argparse
from .crypto import derive_device_key

# Default POC values (must match server)
DEFAULT_MASTER_KEY = "00112233445566778899aabbccddeeff"
DEFAULT_DEVICE_ID = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"


def main() -> None:
    """Derive and display the device key."""
    parser = argparse.ArgumentParser(
        description="Derive Device Key from Master Key + Device ID"
    )
    parser.add_argument(
        "--master-key",
        type=str,
        default=DEFAULT_MASTER_KEY,
        help=f"Master key in hex (default: {DEFAULT_MASTER_KEY})",
    )
    parser.add_argument(
        "--device-id",
        type=str,
        default=DEFAULT_DEVICE_ID,
        help=f"Device ID in hex (default: {DEFAULT_DEVICE_ID})",
    )
    args = parser.parse_args()

    master_key = bytes.fromhex(args.master_key)
    device_id = bytes.fromhex(args.device_id)

    print("=" * 60)
    print("Device Key Derivation Utility")
    print("=" * 60)
    print()
    print(f"Master Key:  {master_key.hex()}")
    print(f"Device ID:   {device_id.hex()}")
    print()

    device_key = derive_device_key(master_key, device_id)

    print(f"Device Key:  {device_key.hex()}")
    print()
    print("=" * 60)
    print("Usage:")
    print("=" * 60)
    print()
    print("Run the client with:")
    print(f"  python -m ble_symmetric_key.client --device-key {device_key.hex()}")
    print()
    print("Or set POC_DEVICE_KEY in client.py:")
    print(f'  POC_DEVICE_KEY = bytes.fromhex("{device_key.hex()}")')
    print()


if __name__ == "__main__":
    main()
