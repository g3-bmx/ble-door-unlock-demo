"""iBeacon packet construction utilities.

This module provides pure Python functions to build iBeacon advertisement
packets. It has no platform dependencies and can be reused across different
BLE implementations.

iBeacon Packet Format (Manufacturer Specific Data):
    Offset  Length  Value       Description
    0-1     2       0x4C00      Apple Company ID (little-endian)
    2       1       0x02        iBeacon type
    3       1       0x15        Length (21 bytes following)
    4-19    16      [UUID]      Proximity UUID (big-endian)
    20-21   2       [Major]     Major value (big-endian)
    22-23   2       [Minor]     Minor value (big-endian)
    24      1       [TxPower]   Calibrated TX Power (signed int8)
"""

from dataclasses import dataclass
import re
import struct

# Apple's company identifier for iBeacon
APPLE_COMPANY_ID = 0x004C

# iBeacon type and length constants
IBEACON_TYPE = 0x02
IBEACON_DATA_LENGTH = 0x15  # 21 bytes

# Default configuration values
DEFAULT_UUID = "E7B2C021-5D07-4D0B-9C20-223488C8B012"
DEFAULT_MAJOR = 1
DEFAULT_MINOR = 1
DEFAULT_TX_POWER = -65  # Calibrated TX power at 1 meter (lower = closer proximity)

# UUID regex pattern (with or without hyphens)
UUID_PATTERN = re.compile(
    r"^[0-9A-Fa-f]{8}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{4}-?[0-9A-Fa-f]{12}$"
)


@dataclass
class IBeaconConfig:
    """Configuration for an iBeacon advertisement.

    Attributes:
        uuid: 16-byte proximity UUID as string (e.g., "A1B2C3D4-E5F6-7890-ABCD-EF1234567890")
        major: Group identifier (0-65535)
        minor: Device identifier within group (0-65535)
        tx_power: Calibrated TX power at 1 meter in dBm (typically -59 to -65)
    """

    uuid: str = DEFAULT_UUID
    major: int = DEFAULT_MAJOR
    minor: int = DEFAULT_MINOR
    tx_power: int = DEFAULT_TX_POWER

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        validate_config(self)


class IBeaconConfigError(ValueError):
    """Raised when iBeacon configuration is invalid."""

    pass


def uuid_to_bytes(uuid_str: str) -> bytes:
    """Convert a UUID string to 16 bytes.

    Args:
        uuid_str: UUID string with or without hyphens
                  (e.g., "A1B2C3D4-E5F6-7890-ABCD-EF1234567890")

    Returns:
        16-byte representation of the UUID (big-endian)

    Raises:
        IBeaconConfigError: If UUID format is invalid
    """
    # Remove hyphens and validate
    hex_str = uuid_str.replace("-", "")

    if len(hex_str) != 32:
        raise IBeaconConfigError(f"UUID must be 32 hex characters, got {len(hex_str)}")

    try:
        return bytes.fromhex(hex_str)
    except ValueError as e:
        raise IBeaconConfigError(f"Invalid UUID hex characters: {e}") from e


def validate_config(config: IBeaconConfig) -> None:
    """Validate iBeacon configuration values.

    Args:
        config: IBeaconConfig instance to validate

    Raises:
        IBeaconConfigError: If any configuration value is invalid
    """
    # Validate UUID format
    if not UUID_PATTERN.match(config.uuid):
        raise IBeaconConfigError(
            f"Invalid UUID format: {config.uuid}. "
            "Expected format: XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
        )

    # Validate major (0-65535, unsigned 16-bit)
    if not 0 <= config.major <= 65535:
        raise IBeaconConfigError(f"Major must be 0-65535, got {config.major}")

    # Validate minor (0-65535, unsigned 16-bit)
    if not 0 <= config.minor <= 65535:
        raise IBeaconConfigError(f"Minor must be 0-65535, got {config.minor}")

    # Validate TX power (-127 to 127, signed 8-bit)
    if not -127 <= config.tx_power <= 127:
        raise IBeaconConfigError(f"TX power must be -127 to 127, got {config.tx_power}")


def build_ibeacon_payload(config: IBeaconConfig) -> bytes:
    """Build the iBeacon payload (without Apple company ID prefix).

    This builds the 23-byte payload that goes after the company ID in
    the manufacturer-specific data. The format is:
        - 1 byte: iBeacon type (0x02)
        - 1 byte: data length (0x15 = 21)
        - 16 bytes: proximity UUID
        - 2 bytes: major (big-endian)
        - 2 bytes: minor (big-endian)
        - 1 byte: TX power (signed)

    Args:
        config: iBeacon configuration

    Returns:
        23-byte iBeacon payload
    """
    uuid_bytes = uuid_to_bytes(config.uuid)

    # Pack the iBeacon data
    # >: big-endian
    # B: unsigned char (1 byte) - type
    # B: unsigned char (1 byte) - length
    # 16s: 16-byte string - UUID
    # H: unsigned short (2 bytes) - major
    # H: unsigned short (2 bytes) - minor
    # b: signed char (1 byte) - tx_power
    payload = struct.pack(
        ">BB16sHHb",
        IBEACON_TYPE,
        IBEACON_DATA_LENGTH,
        uuid_bytes,
        config.major,
        config.minor,
        config.tx_power,
    )

    return payload


def build_manufacturer_data(config: IBeaconConfig) -> dict[int, bytes]:
    """Build the manufacturer-specific data dictionary for BlueZ.

    BlueZ expects manufacturer data as a dictionary mapping company ID
    to payload bytes. For iBeacon, the company ID is Apple (0x004C).

    Args:
        config: iBeacon configuration

    Returns:
        Dictionary with Apple company ID as key and iBeacon payload as value
    """
    payload = build_ibeacon_payload(config)
    return {APPLE_COMPANY_ID: payload}


def format_config_for_logging(config: IBeaconConfig) -> str:
    """Format configuration for human-readable logging.

    Args:
        config: iBeacon configuration

    Returns:
        Multi-line string with formatted configuration
    """
    return (
        f"UUID: {config.uuid}\n"
        f"Major: {config.major}\n"
        f"Minor: {config.minor}\n"
        f"TX Power: {config.tx_power} dBm"
    )


def get_default_config() -> IBeaconConfig:
    """Get the default iBeacon configuration.

    Returns:
        IBeaconConfig with default values
    """
    return IBeaconConfig()
