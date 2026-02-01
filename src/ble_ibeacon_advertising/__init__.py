"""iBeacon advertising module for Linux intercom devices.

This module provides iBeacon advertising functionality using the BlueZ
Bluetooth stack on Linux. It allows the intercom to broadcast iBeacon
advertisements that can be detected by iOS and Android mobile applications.

Example:
    from ble_ibeacon_advertising import IBeaconAdvertiser, IBeaconConfig, TxPowerLevel

    config = IBeaconConfig(
        uuid="E7B2C021-5D07-4D0B-9C20-223488C8B012",
        major=1,
        minor=1,
        tx_power=-75,  # Calibrated RSSI at 1m (for distance calculation)
    )

    # Use TxPowerLevel to control actual hardware transmit power (detection range)
    advertiser = IBeaconAdvertiser(config, hw_tx_power=TxPowerLevel.LOW)
    await advertiser.start()
"""

__version__ = "0.1.0"

from .ibeacon_packet import (
    IBeaconConfig,
    IBeaconConfigError,
    build_ibeacon_payload,
    build_manufacturer_data,
    get_default_config,
    APPLE_COMPANY_ID,
    DEFAULT_UUID,
    DEFAULT_MAJOR,
    DEFAULT_MINOR,
    DEFAULT_TX_POWER,
)
from .advertiser import (
    IBeaconAdvertiser,
    TxPowerLevel,
    set_adapter_tx_power,
    get_adapter_tx_power,
)

__all__ = [
    # Version
    "__version__",
    # Classes
    "IBeaconConfig",
    "IBeaconConfigError",
    "IBeaconAdvertiser",
    "TxPowerLevel",
    # Functions
    "build_ibeacon_payload",
    "build_manufacturer_data",
    "get_default_config",
    "set_adapter_tx_power",
    "get_adapter_tx_power",
    # Constants
    "APPLE_COMPANY_ID",
    "DEFAULT_UUID",
    "DEFAULT_MAJOR",
    "DEFAULT_MINOR",
    "DEFAULT_TX_POWER",
]
