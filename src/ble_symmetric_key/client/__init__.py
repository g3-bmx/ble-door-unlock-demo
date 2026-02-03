"""
BLE GATT Client for symmetric key authentication.

This package implements a BLE central (GATT client) that handles
credential communication using symmetric key authentication with AES-128-CBC.
"""

from .crypto import (
    encrypt,
    decrypt,
    generate_nonce,
    generate_iv,
    derive_device_key,
    KEY_SIZE,
    IV_SIZE,
    NONCE_SIZE,
)
from .protocol import (
    MessageType,
    CredentialStatus,
    ErrorCode,
    AuthRequestBuilder,
    AuthResponseParser,
    CredentialBuilder,
    parse_credential_response,
)
from .client import (
    CredentialClient,
    ClientConfig,
    Result,
    CREDENTIAL_SERVICE_UUID,
    DATA_TRANSFER_CHAR_UUID,
    POC_DEVICE_ID,
    get_poc_config,
)

__all__ = [
    # Crypto
    "encrypt",
    "decrypt",
    "generate_nonce",
    "generate_iv",
    "derive_device_key",
    "KEY_SIZE",
    "IV_SIZE",
    "NONCE_SIZE",
    # Protocol
    "MessageType",
    "CredentialStatus",
    "ErrorCode",
    "AuthRequestBuilder",
    "AuthResponseParser",
    "CredentialBuilder",
    "parse_credential_response",
    # Client
    "CredentialClient",
    "ClientConfig",
    "Result",
    "CREDENTIAL_SERVICE_UUID",
    "DATA_TRANSFER_CHAR_UUID",
    "POC_DEVICE_ID",
    "get_poc_config",
]
