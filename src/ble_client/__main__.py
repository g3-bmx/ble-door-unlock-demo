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


async def cmd_challenge(args: argparse.Namespace) -> int:
    """Connect to the Intercom and receive the challenge nonce."""
    client = IntercomClient(device_name=args.name)

    device = await client.scan(timeout=args.timeout)
    if not device:
        print(f"Device '{args.name}' not found")
        return 1

    if not await client.connect():
        print("Failed to connect")
        return 1

    try:
        print("Subscribing to challenge characteristic...")
        nonce = await client.get_challenge(timeout=args.challenge_timeout)

        if nonce:
            print(f"\nChallenge nonce received:")
            print(f"  Hex: {nonce.hex()}")
            print(f"  Length: {len(nonce)} bytes")
            return 0
        else:
            print("Failed to receive challenge nonce")
            return 1
    finally:
        await client.disconnect()


async def cmd_read_challenge(args: argparse.Namespace) -> int:
    """Connect and read the challenge nonce directly (without notifications)."""
    client = IntercomClient(device_name=args.name)

    device = await client.scan(timeout=args.timeout)
    if not device:
        print(f"Device '{args.name}' not found")
        return 1

    if not await client.connect():
        print("Failed to connect")
        return 1

    try:
        print("Reading challenge characteristic...")
        nonce = await client.read_challenge()

        if nonce:
            print(f"\nChallenge nonce read:")
            print(f"  Hex: {nonce.hex()}")
            print(f"  Length: {len(nonce)} bytes")
            return 0
        else:
            print("Failed to read challenge nonce")
            return 1
    finally:
        await client.disconnect()


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

    # Challenge command (subscribe to notifications)
    challenge_parser = subparsers.add_parser(
        "challenge",
        help="Connect and receive challenge nonce via notification"
    )
    challenge_parser.add_argument(
        "-n", "--name",
        default="Intercom",
        help="Device name to connect to (default: Intercom)",
    )
    challenge_parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=10.0,
        help="Scan timeout in seconds (default: 10)",
    )
    challenge_parser.add_argument(
        "--challenge-timeout",
        type=float,
        default=10.0,
        help="Timeout waiting for challenge nonce (default: 10)",
    )

    # Read challenge command (direct read)
    read_parser = subparsers.add_parser(
        "read-challenge",
        help="Connect and read challenge nonce directly"
    )
    read_parser.add_argument(
        "-n", "--name",
        default="Intercom",
        help="Device name to connect to (default: Intercom)",
    )
    read_parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=10.0,
        help="Scan timeout in seconds (default: 10)",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.command == "scan":
        return asyncio.run(cmd_scan(args))
    elif args.command == "challenge":
        return asyncio.run(cmd_challenge(args))
    elif args.command == "read-challenge":
        return asyncio.run(cmd_read_challenge(args))
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
