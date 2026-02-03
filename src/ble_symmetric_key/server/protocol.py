"""
BLE authentication protocol message definitions and parsing.

Message format: [Type (1 byte)][Payload (variable)]
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from .crypto import IV_SIZE, NONCE_SIZE, KEY_SIZE


# Device ID size (same as key size for simplicity)
DEVICE_ID_SIZE = KEY_SIZE


class MessageType(IntEnum):
    """Protocol message types."""
    AUTH_REQUEST = 0x01
    AUTH_RESPONSE = 0x02
    CREDENTIAL = 0x03
    CREDENTIAL_RESPONSE = 0x04
    ERROR = 0xFF


class CredentialStatus(IntEnum):
    """Credential processing result codes."""
    SUCCESS = 0x00
    REJECTED = 0x01
    EXPIRED = 0x02
    REVOKED = 0x03
    INVALID_FORMAT = 0x04


class ErrorCode(IntEnum):
    """Protocol error codes."""
    INVALID_MESSAGE = 0x01
    UNKNOWN_DEVICE = 0x02
    DECRYPTION_FAILED = 0x03
    INVALID_STATE = 0x04
    AUTH_FAILED = 0x05
    TIMEOUT = 0x06


@dataclass
class AuthRequest:
    """
    AUTH_REQUEST message (0x01).

    Format: [0x01][DeviceID (16B)][IV (16B)][Enc_DK(Nonce_M) (16B)]
    Total: 49 bytes
    """
    device_id: bytes
    iv: bytes
    encrypted_nonce: bytes

    @classmethod
    def parse(cls, data: bytes) -> Optional["AuthRequest"]:
        """Parse AUTH_REQUEST from raw bytes (excluding message type)."""
        expected_size = DEVICE_ID_SIZE + IV_SIZE + NONCE_SIZE  # 48 bytes
        if len(data) < expected_size:
            return None

        device_id = data[:DEVICE_ID_SIZE]
        iv = data[DEVICE_ID_SIZE:DEVICE_ID_SIZE + IV_SIZE]
        encrypted_nonce = data[DEVICE_ID_SIZE + IV_SIZE:DEVICE_ID_SIZE + IV_SIZE + NONCE_SIZE]

        return cls(device_id=device_id, iv=iv, encrypted_nonce=encrypted_nonce)


@dataclass
class AuthResponse:
    """
    AUTH_RESPONSE message (0x02).

    Format: [0x02][IV (16B)][Enc_DK(Nonce_M || Nonce_R) (32B)]
    Total: 49 bytes
    """
    iv: bytes
    encrypted_nonces: bytes  # Nonce_M || Nonce_R encrypted

    def build(self) -> bytes:
        """Build AUTH_RESPONSE message bytes."""
        return bytes([MessageType.AUTH_RESPONSE]) + self.iv + self.encrypted_nonces


@dataclass
class Credential:
    """
    CREDENTIAL message (0x03).

    Format: [0x03][IV (16B)][Enc_DK(CredentialPayload) (variable)]
    """
    iv: bytes
    encrypted_payload: bytes

    @classmethod
    def parse(cls, data: bytes) -> Optional["Credential"]:
        """Parse CREDENTIAL from raw bytes (excluding message type)."""
        if len(data) < IV_SIZE + 16:  # At least IV + one block
            return None

        iv = data[:IV_SIZE]
        encrypted_payload = data[IV_SIZE:]

        return cls(iv=iv, encrypted_payload=encrypted_payload)


@dataclass
class CredentialResponse:
    """
    CREDENTIAL_RESPONSE message (0x04).

    Format: [0x04][Status (1B)]
    Total: 2 bytes
    """
    status: CredentialStatus

    def build(self) -> bytes:
        """Build CREDENTIAL_RESPONSE message bytes."""
        return bytes([MessageType.CREDENTIAL_RESPONSE, self.status])


@dataclass
class ErrorMessage:
    """
    ERROR message (0xFF).

    Format: [0xFF][ErrorCode (1B)]
    Total: 2 bytes
    """
    error_code: ErrorCode

    def build(self) -> bytes:
        """Build ERROR message bytes."""
        return bytes([MessageType.ERROR, self.error_code])


def parse_message_type(data: bytes) -> Optional[MessageType]:
    """Extract message type from raw data."""
    if not data:
        return None
    try:
        return MessageType(data[0])
    except ValueError:
        return None


def parse_message(data: bytes) -> tuple[Optional[MessageType], Optional[object]]:
    """
    Parse a complete message from raw bytes.

    Returns:
        Tuple of (message_type, parsed_message) or (None, None) on error
    """
    if not data:
        return None, None

    msg_type = parse_message_type(data)
    if msg_type is None:
        return None, None

    payload = data[1:]  # Everything after message type byte

    if msg_type == MessageType.AUTH_REQUEST:
        return msg_type, AuthRequest.parse(payload)
    elif msg_type == MessageType.CREDENTIAL:
        return msg_type, Credential.parse(payload)
    else:
        # AUTH_RESPONSE and CREDENTIAL_RESPONSE are outgoing only
        return msg_type, None
