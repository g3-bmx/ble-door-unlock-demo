"""CLI entry point for the BLE client."""

import argparse
import asyncio
import logging
import sys

from .client import IntercomClient, scan_all_devices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def cmd_scan(args: argparse.Namespace) -> int:
    """Scan for all BLE devices."""
    devices = await scan_all_devices(timeout=args.timeout)
    print(f"\nFound {len(devices)} device(s)")
    return 0


async def cmd_connect(args: argparse.Namespace) -> int:
    """Connect to the Intercom and optionally send data."""
    client = IntercomClient(device_name=args.name)

    device = await client.scan(timeout=args.timeout)
    if not device:
        print(f"Device '{args.name}' not found")
        return 1

    if not await client.connect():
        print("Failed to connect")
        return 1

    try:
        if args.message:
            success = await client.write(args.message)
            if not success:
                return 1

        if args.interactive:
            print("\nInteractive mode. Type messages to send (Ctrl+C to exit):")
            while True:
                try:
                    message = input("> ")
                    if message:
                        await client.write(message)
                except KeyboardInterrupt:
                    print("\nExiting...")
                    break
    finally:
        await client.disconnect()

    return 0


async def cmd_unlock(args: argparse.Namespace) -> int:
    """Send an unlock command to the Intercom."""
    async with IntercomClient(device_name=args.name) as client:
        if not client.client or not client.client.is_connected:
            print(f"Failed to connect to '{args.name}'")
            return 1

        payload = {"action": "unlock"}
        success = await client.write(payload)

        if success:
            print("Unlock command sent successfully")
            return 0
        else:
            print("Failed to send unlock command")
            return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BLE Client - Simulate a mobile device connecting to the GATT server"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan for all BLE devices")
    scan_parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=10.0,
        help="Scan timeout in seconds (default: 10)",
    )

    # Connect command
    connect_parser = subparsers.add_parser("connect", help="Connect to the Intercom")
    connect_parser.add_argument(
        "-n", "--name",
        default="Intercom",
        help="Device name to connect to (default: Intercom)",
    )
    connect_parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=10.0,
        help="Scan timeout in seconds (default: 10)",
    )
    connect_parser.add_argument(
        "-m", "--message",
        help="Message to send after connecting",
    )
    connect_parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Enter interactive mode to send multiple messages",
    )

    # Unlock command
    unlock_parser = subparsers.add_parser("unlock", help="Send unlock command")
    unlock_parser.add_argument(
        "-n", "--name",
        default="Intercom",
        help="Device name to connect to (default: Intercom)",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "scan":
        return asyncio.run(cmd_scan(args))
    elif args.command == "connect":
        return asyncio.run(cmd_connect(args))
    elif args.command == "unlock":
        return asyncio.run(cmd_unlock(args))
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
