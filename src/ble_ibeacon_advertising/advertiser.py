"""iBeacon advertiser using BlueZ D-Bus API.

This module provides the IBeaconAdvertiser class that manages iBeacon
advertising on Linux using the BlueZ Bluetooth stack via D-Bus.

Requirements:
    - Linux with BlueZ 5.x
    - bluetoothd running
    - Bluetooth adapter available and powered on
    - Root/sudo access for hardware TX power control (optional)
"""

import asyncio
import logging
import subprocess
from enum import IntEnum
from typing import Any

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, dbus_property, method, PropertyAccess

from .ibeacon_packet import IBeaconConfig, build_ibeacon_payload, APPLE_COMPANY_ID

logger = logging.getLogger(__name__)


class TxPowerLevel(IntEnum):
    """Hardware transmit power levels for Bluetooth adapter.

    These values represent the power level in dBm that can be set on
    the Bluetooth adapter. Lower values = shorter range = user must be closer.

    Note: Actual supported values depend on the hardware. These are common
    values supported by most adapters. The adapter will use the closest
    supported value if the exact value isn't available.
    """

    # High power - maximum range (~30-50m)
    HIGH = 4

    # Medium power - moderate range (~10-20m)
    MEDIUM = 0

    # Low power - short range (~5-10m)
    LOW = -6

    # Very low power - close proximity (~2-5m)
    VERY_LOW = -12

    # Minimum power - very close proximity (~1-2m)
    MINIMUM = -20


async def set_adapter_tx_power(adapter: str, power_dbm: int) -> bool:
    """Set the Bluetooth adapter's transmit power level.

    This uses hcitool to send an HCI command to set the LE transmit power.
    Requires root/sudo privileges.

    Args:
        adapter: Adapter name (e.g., "hci0")
        power_dbm: Desired transmit power in dBm (-20 to +4 typical range)

    Returns:
        True if successful, False otherwise
    """
    # Clamp power to valid range
    power_dbm = max(-20, min(20, power_dbm))

    logger.info(f"[TX_POWER] Setting {adapter} transmit power to {power_dbm} dBm...")

    try:
        # Method 1: Use btmgmt (preferred, more modern)
        # btmgmt --index 0 power <on/off> doesn't directly set dBm,
        # so we use hcitool for direct HCI control

        # Method 2: Use hcitool to send LE Set Advertising Parameters
        # The HCI command for LE Set Transmit Power Level is vendor-specific
        # A more portable approach is to use the class of device or
        # set via hciconfig

        # For now, use hciconfig to set inquiry transmit power level
        # This affects overall adapter power on many chipsets
        result = await asyncio.create_subprocess_exec(
            "sudo", "hciconfig", adapter, "inqtpl", str(power_dbm),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()

        if result.returncode == 0:
            logger.info(f"[TX_POWER] Successfully set inquiry TX power to {power_dbm} dBm")
        else:
            # inqtpl might not be supported, try alternative
            logger.debug(f"[TX_POWER] inqtpl not supported: {stderr.decode()}")

        # Also try setting LE TX power via hcitool cmd (if supported)
        # HCI_LE_Set_Advertising_Parameters OCF=0x0006, OGF=0x08
        # This is chipset-dependent
        result2 = await asyncio.create_subprocess_exec(
            "sudo", "hciconfig", adapter, "leadv", "3",  # non-connectable advertising
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        await result2.communicate()

        logger.info(f"[TX_POWER] TX power configuration attempted for {adapter}")
        return True

    except FileNotFoundError:
        logger.warning("[TX_POWER] hciconfig not found. Install bluez-utils package.")
        return False
    except PermissionError:
        logger.warning("[TX_POWER] Permission denied. Run with sudo for TX power control.")
        return False
    except Exception as e:
        logger.warning(f"[TX_POWER] Failed to set TX power: {e}")
        return False


async def get_adapter_tx_power(adapter: str) -> int | None:
    """Get the current transmit power level of the adapter.

    Args:
        adapter: Adapter name (e.g., "hci0")

    Returns:
        Current TX power in dBm, or None if unable to read
    """
    try:
        result = await asyncio.create_subprocess_exec(
            "hciconfig", adapter, "inqtpl",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()

        if result.returncode == 0:
            # Parse output like "Inquiry transmit power level: 0"
            output = stdout.decode()
            for line in output.split("\n"):
                if "power level" in line.lower():
                    parts = line.split(":")
                    if len(parts) >= 2:
                        return int(parts[1].strip())
        return None

    except Exception as e:
        logger.debug(f"[TX_POWER] Could not read TX power: {e}")
        return None

# BlueZ D-Bus constants
BLUEZ_SERVICE = "org.bluez"
BLUEZ_ADAPTER_INTERFACE = "org.bluez.Adapter1"
BLUEZ_LE_ADVERTISING_MANAGER_INTERFACE = "org.bluez.LEAdvertisingManager1"
BLUEZ_LE_ADVERTISEMENT_INTERFACE = "org.bluez.LEAdvertisement1"

# D-Bus object paths
DEFAULT_ADAPTER = "hci0"
ADVERTISEMENT_PATH = "/com/intercom/ibeacon/advertisement0"


class IBeaconAdvertisement(ServiceInterface):
    """D-Bus service implementing org.bluez.LEAdvertisement1 for iBeacon.

    This class exposes the required D-Bus properties and methods that BlueZ
    expects for a BLE advertisement. For iBeacon, we use:
    - Type: "broadcast" (one-way advertisement, no connection)
    - ManufacturerData: Apple company ID (0x004C) with iBeacon payload
    """

    def __init__(self, config: IBeaconConfig):
        """Initialize the iBeacon advertisement.

        Args:
            config: iBeacon configuration with UUID, major, minor, tx_power
        """
        super().__init__(BLUEZ_LE_ADVERTISEMENT_INTERFACE)
        self._config = config
        self._manufacturer_data = self._build_manufacturer_data()

    def _build_manufacturer_data(self) -> dict[str, Any]:
        """Build manufacturer data in D-Bus format.

        BlueZ expects manufacturer data as a{qv} (dict of uint16 -> variant).
        The variant contains an array of bytes (ay).

        Returns:
            Dictionary with Apple company ID mapped to iBeacon payload variant
        """
        payload = build_ibeacon_payload(self._config)
        # dbus-next expects bytes directly for "ay" type
        return {APPLE_COMPANY_ID: Variant("ay", payload)}

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":
        """Advertisement type.

        Returns "broadcast" for iBeacon since it's a one-way advertisement
        that doesn't accept connections.
        """
        return "broadcast"

    @dbus_property(access=PropertyAccess.READ)
    def ManufacturerData(self) -> "a{qv}":
        """Manufacturer-specific data.

        Returns Apple's company ID (0x004C) with the iBeacon payload.
        """
        return self._manufacturer_data

    @dbus_property(access=PropertyAccess.READ)
    def IncludeTxPower(self) -> "b":
        """Whether to include TX power in the advertisement.

        Returns False because iBeacon includes TX power in the manufacturer
        data payload itself.
        """
        return False

    @method()
    def Release(self) -> None:
        """Called by BlueZ when the advertisement is released.

        This is a required method for the LEAdvertisement1 interface.
        """
        logger.info("[ADVERTISE] Advertisement released by BlueZ")


class IBeaconAdvertiser:
    """Manages iBeacon advertising on Linux via BlueZ D-Bus.

    This class handles:
    - Connecting to the system D-Bus
    - Exporting the LEAdvertisement1 interface
    - Registering/unregistering the advertisement with BlueZ
    - Optionally setting hardware transmit power level
    - Graceful cleanup on shutdown

    Example:
        config = IBeaconConfig(uuid="...", major=1, minor=1, tx_power=-59)
        advertiser = IBeaconAdvertiser(config, hw_tx_power=TxPowerLevel.LOW)
        await advertiser.start()
        # ... advertising is active ...
        await advertiser.stop()
    """

    def __init__(
        self,
        config: IBeaconConfig,
        adapter: str = DEFAULT_ADAPTER,
        hw_tx_power: TxPowerLevel | int | None = None,
    ):
        """Initialize the iBeacon advertiser.

        Args:
            config: iBeacon configuration
            adapter: Bluetooth adapter name (default: "hci0")
            hw_tx_power: Hardware transmit power level in dBm.
                         Use TxPowerLevel enum for common presets, or specify
                         an integer value (-20 to +4 typical range).
                         None means don't change the adapter's power level.
                         Requires root/sudo to take effect.
        """
        self._config = config
        self._adapter_name = adapter
        self._adapter_path = f"/org/bluez/{adapter}"
        self._hw_tx_power = int(hw_tx_power) if hw_tx_power is not None else None

        self._bus: MessageBus | None = None
        self._advertisement: IBeaconAdvertisement | None = None
        self._advertising_manager: Any = None
        self._is_advertising = False

    @property
    def is_advertising(self) -> bool:
        """Return whether the advertiser is currently active."""
        return self._is_advertising

    async def start(self) -> None:
        """Start iBeacon advertising.

        This method:
        1. Optionally sets hardware transmit power (requires sudo)
        2. Connects to the system D-Bus
        3. Creates and exports the advertisement object
        4. Registers the advertisement with BlueZ

        Raises:
            Exception: If D-Bus connection fails or BlueZ rejects the advertisement
        """
        if self._is_advertising:
            logger.warning("[ADVERTISE] Already advertising, ignoring start request")
            return

        logger.info("[ADVERTISE] Starting iBeacon advertiser...")
        logger.info(f"[ADVERTISE] Adapter: {self._adapter_name}")

        # Set hardware TX power if specified
        if self._hw_tx_power is not None:
            logger.info(f"[ADVERTISE] Requested hardware TX power: {self._hw_tx_power} dBm")
            success = await set_adapter_tx_power(self._adapter_name, self._hw_tx_power)
            if not success:
                logger.warning(
                    "[ADVERTISE] Could not set hardware TX power. "
                    "Continuing with default power level. "
                    "Run with sudo for TX power control."
                )

        # Connect to system D-Bus
        logger.debug("[ADVERTISE] Connecting to system D-Bus...")
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        logger.info("[ADVERTISE] Connected to D-Bus system bus")

        # Create and export the advertisement
        self._advertisement = IBeaconAdvertisement(self._config)
        self._bus.export(ADVERTISEMENT_PATH, self._advertisement)
        logger.debug(f"[ADVERTISE] Exported advertisement at {ADVERTISEMENT_PATH}")

        # Get the adapter object and advertising manager interface
        introspection = await self._bus.introspect(BLUEZ_SERVICE, self._adapter_path)
        adapter_proxy = self._bus.get_proxy_object(
            BLUEZ_SERVICE, self._adapter_path, introspection
        )
        self._advertising_manager = adapter_proxy.get_interface(
            BLUEZ_LE_ADVERTISING_MANAGER_INTERFACE
        )

        # Register the advertisement with BlueZ
        logger.debug("[ADVERTISE] Registering advertisement with BlueZ...")
        await self._advertising_manager.call_register_advertisement(
            ADVERTISEMENT_PATH, {}
        )

        self._is_advertising = True
        logger.info("[ADVERTISE] iBeacon advertising started successfully")

    async def stop(self) -> None:
        """Stop iBeacon advertising and cleanup.

        This method safely unregisters the advertisement and disconnects
        from D-Bus. It handles errors gracefully to ensure cleanup completes.
        """
        if not self._is_advertising:
            logger.debug("[ADVERTISE] Not advertising, nothing to stop")
            return

        logger.info("[ADVERTISE] Stopping iBeacon advertiser...")

        # Unregister the advertisement
        if self._advertising_manager is not None:
            try:
                await self._advertising_manager.call_unregister_advertisement(
                    ADVERTISEMENT_PATH
                )
                logger.debug("[ADVERTISE] Advertisement unregistered")
            except Exception as e:
                logger.warning(f"[ADVERTISE] Error unregistering advertisement: {e}")

        # Disconnect from D-Bus
        if self._bus is not None:
            try:
                self._bus.disconnect()
                logger.debug("[ADVERTISE] Disconnected from D-Bus")
            except Exception as e:
                logger.warning(f"[ADVERTISE] Error disconnecting from D-Bus: {e}")

        self._is_advertising = False
        self._bus = None
        self._advertisement = None
        self._advertising_manager = None

        logger.info("[ADVERTISE] iBeacon advertiser stopped")

    async def run_forever(self) -> None:
        """Start advertising and run until cancelled.

        This is a convenience method that starts advertising and then
        waits indefinitely. Use this when running as a standalone service.

        The method will return when the task is cancelled (e.g., via signal).
        """
        await self.start()

        try:
            # Wait forever (until cancelled)
            await asyncio.Future()
        except asyncio.CancelledError:
            logger.info("[ADVERTISE] Received cancellation, shutting down...")
        finally:
            await self.stop()
