"""
BLE GATT Server for symmetric key authentication.

This package implements a BLE peripheral (GATT server) that handles
credential communication using symmetric key authentication with AES-128-CBC.
"""

from .crypto import (
    derive_device_key,
    encrypt,
    decrypt,
    generate_nonce,
    generate_iv,
    KEY_SIZE,
    IV_SIZE,
    NONCE_SIZE,
)
from .protocol import (
    MessageType,
    CredentialStatus,
    ErrorCode,
    AuthRequest,
    AuthResponse,
    Credential,
    CredentialResponse,
    ErrorMessage,
)
from .state import (
    ConnectionState,
    SessionContext,
    ProtocolHandler,
)
from .server import (
    CredentialGATTServer,
    CREDENTIAL_SERVICE_UUID,
    DATA_TRANSFER_CHAR_UUID,
    SERVER_NAME,
)

__all__ = [
    # Crypto
    "derive_device_key",
    "encrypt",
    "decrypt",
    "generate_nonce",
    "generate_iv",
    "KEY_SIZE",
    "IV_SIZE",
    "NONCE_SIZE",
    # Protocol
    "MessageType",
    "CredentialStatus",
    "ErrorCode",
    "AuthRequest",
    "AuthResponse",
    "Credential",
    "CredentialResponse",
    "ErrorMessage",
    # State
    "ConnectionState",
    "SessionContext",
    "ProtocolHandler",
    # Server
    "CredentialGATTServer",
    "CREDENTIAL_SERVICE_UUID",
    "DATA_TRANSFER_CHAR_UUID",
    "SERVER_NAME",
]
