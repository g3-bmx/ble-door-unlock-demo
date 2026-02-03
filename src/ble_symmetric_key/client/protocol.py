"""
BLE authentication protocol message definitions for client.

Message format: [Type (1 byte)][Payload (variable)]
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from .crypto import IV_SIZE, NONCE_SIZE, KEY_SIZE, encrypt, decrypt, generate_nonce, generate_iv


# Device ID size (same as key size)
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

    def to_message(self) -> str:
        """Convert status to user-friendly message."""
        messages = {
            CredentialStatus.SUCCESS: "Access granted",
            CredentialStatus.REJECTED: "Access denied",
            CredentialStatus.EXPIRED: "Credential expired",
            CredentialStatus.REVOKED: "Credential revoked",
            CredentialStatus.INVALID_FORMAT: "Invalid credential",
        }
        return messages.get(self, f"Unknown status: {self}")


class ErrorCode(IntEnum):
    """Protocol error codes."""
    INVALID_MESSAGE = 0x01
    UNKNOWN_DEVICE = 0x02
    DECRYPTION_FAILED = 0x03
    INVALID_STATE = 0x04
    AUTH_FAILED = 0x05
    TIMEOUT = 0x06

    def to_message(self) -> str:
        """Convert error code to user-friendly message."""
        messages = {
            ErrorCode.INVALID_MESSAGE: "Communication error",
            ErrorCode.UNKNOWN_DEVICE: "Device not recognized",
            ErrorCode.DECRYPTION_FAILED: "Authentication failed",
            ErrorCode.INVALID_STATE: "Protocol error",
            ErrorCode.AUTH_FAILED: "Authentication failed",
            ErrorCode.TIMEOUT: "Reader timeout",
        }
        return messages.get(self, f"Unknown error: {self}")


@dataclass
class AuthRequestBuilder:
    """
    Builds AUTH_REQUEST messages.

    Format: [0x01][DeviceID (16B)][IV (16B)][Enc_DK(Nonce_M) (32B)]
    Total: 65 bytes

    Note: Encrypted nonce is 32 bytes because PKCS7 padding adds a full block
    when the plaintext (16-byte nonce) is exactly one AES block.
    """
    device_id: bytes
    device_key: bytes

    def build(self) -> tuple[bytes, bytes]:
        """
        Build AUTH_REQUEST message.

        Returns:
            Tuple of (message_bytes, nonce_m) - caller must save nonce_m for verification
        """
        nonce_m = generate_nonce()
        iv, encrypted_nonce = encrypt(self.device_key, nonce_m)

        message = (
            bytes([MessageType.AUTH_REQUEST]) +
            self.device_id +
            iv +
            encrypted_nonce
        )
        return message, nonce_m


@dataclass
class AuthResponseParser:
    """
    Parses AUTH_RESPONSE messages.

    Format: [0x02][IV (16B)][Enc_DK(Nonce_M || Nonce_R) (48B)]
    Total: 65 bytes

    Note: Encrypted nonces are 48 bytes because PKCS7 padding adds a full block
    when the plaintext (32 bytes = Nonce_M + Nonce_R) is exactly two AES blocks.
    """
    device_key: bytes

    # Encrypted nonces size: 32-byte plaintext + 16-byte PKCS7 padding = 48 bytes
    ENCRYPTED_NONCES_SIZE = 48

    def parse(self, data: bytes, expected_nonce_m: bytes) -> tuple[bool, Optional[bytes], str]:
        """
        Parse AUTH_RESPONSE and verify mutual authentication.

        Args:
            data: Raw response bytes
            expected_nonce_m: The Nonce_M we sent, for verification

        Returns:
            Tuple of (success, nonce_r, message)
            - success: True if reader authenticated successfully
            - nonce_r: Reader's nonce (if successful)
            - message: Status/error message
        """
        # Check message type
        if len(data) < 1:
            return False, None, "Empty response"

        if data[0] == MessageType.ERROR:
            if len(data) >= 2:
                error_code = ErrorCode(data[1])
                return False, None, error_code.to_message()
            return False, None, "Unknown error"

        if data[0] != MessageType.AUTH_RESPONSE:
            return False, None, f"Unexpected message type: {data[0]:#x}"

        # Check length: 1 (type) + 16 (IV) + 48 (encrypted nonces) = 65
        expected_len = 1 + IV_SIZE + self.ENCRYPTED_NONCES_SIZE
        if len(data) < expected_len:
            return False, None, f"Response too short: {len(data)} bytes (expected {expected_len})"

        # Extract IV and encrypted nonces
        iv = data[1:1 + IV_SIZE]
        encrypted_nonces = data[1 + IV_SIZE:1 + IV_SIZE + self.ENCRYPTED_NONCES_SIZE]

        # Decrypt
        try:
            decrypted = decrypt(self.device_key, iv, encrypted_nonces)
        except Exception as e:
            return False, None, f"Decryption failed: {e}"

        # Should be 32 bytes: Nonce_M (16) + Nonce_R (16)
        if len(decrypted) != 32:
            return False, None, f"Decrypted data wrong size: {len(decrypted)}"

        received_nonce_m = decrypted[:16]
        nonce_r = decrypted[16:32]

        # Verify reader echoed our nonce correctly
        if received_nonce_m != expected_nonce_m:
            return False, None, "Reader authentication failed - nonce mismatch"

        return True, nonce_r, "Reader authenticated"


@dataclass
class CredentialBuilder:
    """
    Builds CREDENTIAL messages.

    Format: [0x03][IV (16B)][Enc_DK(CredentialPayload) (variable)]
    """
    device_key: bytes

    def build(self, credential: str) -> bytes:
        """
        Build CREDENTIAL message.

        Args:
            credential: Credential string to send

        Returns:
            Message bytes
        """
        payload = credential.encode('utf-8')
        iv, encrypted_payload = encrypt(self.device_key, payload)

        return (
            bytes([MessageType.CREDENTIAL]) +
            iv +
            encrypted_payload
        )


def parse_credential_response(data: bytes) -> tuple[bool, str]:
    """
    Parse CREDENTIAL_RESPONSE message.

    Args:
        data: Raw response bytes

    Returns:
        Tuple of (success, message)
    """
    if len(data) < 1:
        return False, "Empty response"

    if data[0] == MessageType.ERROR:
        if len(data) >= 2:
            try:
                error_code = ErrorCode(data[1])
                return False, error_code.to_message()
            except ValueError:
                return False, f"Unknown error code: {data[1]:#x}"
        return False, "Unknown error"

    if data[0] != MessageType.CREDENTIAL_RESPONSE:
        return False, f"Unexpected message type: {data[0]:#x}"

    if len(data) < 2:
        return False, "Response too short"

    try:
        status = CredentialStatus(data[1])
        success = status == CredentialStatus.SUCCESS
        return success, status.to_message()
    except ValueError:
        return False, f"Unknown status code: {data[1]:#x}"
