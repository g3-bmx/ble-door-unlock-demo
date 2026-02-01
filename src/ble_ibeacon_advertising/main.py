"""Entry point for the iBeacon advertising service.

This module provides the main entry point for running the iBeacon advertiser
as a standalone service. It handles:
- Logging configuration
- Signal handling for graceful shutdown
- Creating and running the advertiser

Usage:
    python -m ble_ibeacon_advertising
    # or
    ble-ibeacon  (if installed via pip/uv)
"""

import argparse
import asyncio
import logging
import signal
import sys

from .advertiser import IBeaconAdvertiser, TxPowerLevel
from .ibeacon_packet import IBeaconConfig, format_config_for_logging, get_default_config

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    # Build tx power choices from enum
    tx_power_choices = {level.name.lower(): level.value for level in TxPowerLevel}

    parser = argparse.ArgumentParser(
        description="iBeacon advertising service for Linux intercom devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Hardware TX Power Levels (controls detection range):
    high     = {TxPowerLevel.HIGH:+d} dBm  (max range ~30-50m)
    medium   = {TxPowerLevel.MEDIUM:+d} dBm  (moderate range ~10-20m)
    low      = {TxPowerLevel.LOW:+d} dBm  (short range ~5-10m)
    very_low = {TxPowerLevel.VERY_LOW:+d} dBm (close proximity ~2-5m)
    minimum  = {TxPowerLevel.MINIMUM:+d} dBm (very close ~1-2m)

Examples:
    # Run with default configuration
    python -m ble_ibeacon_advertising

    # Run with low TX power (user must be close)
    sudo python -m ble_ibeacon_advertising --hw-tx-power low

    # Run with specific dBm value
    sudo python -m ble_ibeacon_advertising --hw-tx-power -15

    # Use a specific Bluetooth adapter
    python -m ble_ibeacon_advertising --adapter hci1
        """,
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )
    parser.add_argument(
        "--adapter",
        default="hci0",
        help="Bluetooth adapter to use (default: hci0)",
    )
    parser.add_argument(
        "--hw-tx-power",
        metavar="LEVEL",
        help=(
            "Hardware transmit power. Use a preset name "
            "(high/medium/low/very_low/minimum) or a dBm value (-20 to +4). "
            "Lower values = shorter range. Requires sudo."
        ),
    )
    return parser.parse_args()


def parse_tx_power(value: str | None) -> int | None:
    """Parse hardware TX power from string argument.

    Args:
        value: Preset name (high/medium/low/very_low/minimum) or dBm integer

    Returns:
        TX power in dBm, or None if not specified
    """
    if value is None:
        return None

    # Try preset names first
    presets = {level.name.lower(): level.value for level in TxPowerLevel}
    if value.lower() in presets:
        return presets[value.lower()]

    # Try parsing as integer
    try:
        return int(value)
    except ValueError:
        valid_presets = ", ".join(presets.keys())
        raise argparse.ArgumentTypeError(
            f"Invalid TX power '{value}'. Use a preset ({valid_presets}) or integer dBm value."
        )


async def async_main(config: IBeaconConfig, adapter: str, hw_tx_power: int | None) -> None:
    """Async entry point with signal handling.

    Args:
        config: iBeacon configuration
        adapter: Bluetooth adapter name
        hw_tx_power: Hardware TX power in dBm, or None
    """
    # Create the advertiser
    advertiser = IBeaconAdvertiser(config, adapter=adapter, hw_tx_power=hw_tx_power)

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler(sig: signal.Signals) -> None:
        logger.info(f"[MAIN] Received signal {sig.name}, initiating shutdown...")
        shutdown_event.set()

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler, sig)

    # Start advertising
    try:
        await advertiser.start()
        logger.info("[MAIN] iBeacon advertising is active. Press Ctrl+C to stop.")

        # Wait for shutdown signal
        await shutdown_event.wait()

    except Exception as e:
        logger.error(f"[MAIN] Error during advertising: {e}")
        raise
    finally:
        # Always cleanup
        await advertiser.stop()
        logger.info("[MAIN] Shutdown complete")


def main() -> None:
    """Main entry point for the iBeacon advertising service."""
    args = parse_args()
    setup_logging(verbose=args.verbose)

    logger.info("[MAIN] Starting iBeacon advertising service...")

    # Parse hardware TX power
    try:
        hw_tx_power = parse_tx_power(args.hw_tx_power)
    except argparse.ArgumentTypeError as e:
        logger.error(f"[MAIN] {e}")
        sys.exit(1)

    # Get default configuration (hardcoded for POC)
    config = get_default_config()

    # Log configuration
    logger.info("[MAIN] Configuration:")
    for line in format_config_for_logging(config).split("\n"):
        logger.info(f"[MAIN]   {line}")
    logger.info(f"[MAIN]   Adapter: {args.adapter}")
    if hw_tx_power is not None:
        logger.info(f"[MAIN]   Hardware TX Power: {hw_tx_power} dBm")
    else:
        logger.info("[MAIN]   Hardware TX Power: (not set, using adapter default)")

    # Check platform
    if sys.platform != "linux":
        logger.error(f"[MAIN] This service only runs on Linux (current: {sys.platform})")
        logger.error("[MAIN] BlueZ D-Bus API is Linux-specific")
        sys.exit(1)

    # Run the async main
    try:
        asyncio.run(async_main(config, args.adapter, hw_tx_power))
    except KeyboardInterrupt:
        # This shouldn't happen as we handle SIGINT, but just in case
        logger.info("[MAIN] Interrupted")
    except Exception as e:
        logger.error(f"[MAIN] Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
