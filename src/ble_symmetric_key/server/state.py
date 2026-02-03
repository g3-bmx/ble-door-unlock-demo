"""
Connection state machine for BLE authentication protocol.

States:
    IDLE -> CONNECTED -> AUTHENTICATING -> AUTHENTICATED -> PROCESSING -> COMPLETE -> IDLE
"""

import logging
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional

from .crypto import (
    derive_device_key,
    decrypt,
    encrypt,
    generate_nonce,
    generate_iv,
    NONCE_SIZE,
)
from .protocol import (
    MessageType,
    AuthRequest,
    AuthResponse,
    Credential,
    CredentialResponse,
    ErrorMessage,
    CredentialStatus,
    ErrorCode,
    parse_message,
)

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state machine states."""
    IDLE = auto()
    CONNECTED = auto()
    AUTHENTICATING = auto()
    AUTHENTICATED = auto()
    PROCESSING = auto()
    COMPLETE = auto()


@dataclass
class SessionContext:
    """Per-connection session data."""
    device_id: Optional[bytes] = None
    device_key: Optional[bytes] = None
    nonce_mobile: Optional[bytes] = None
    nonce_reader: Optional[bytes] = None
    state: ConnectionState = ConnectionState.IDLE


class ProtocolHandler:
    """
    Handles the authentication protocol state machine.

    Processes incoming messages and generates responses based on current state.
    """

    def __init__(self, master_key: bytes):
        """
        Initialize the protocol handler.

        Args:
            master_key: The 16-byte master key for deriving device keys
        """
        self.master_key = master_key
        self.sessions: dict[str, SessionContext] = {}

    def get_session(self, client_id: str) -> SessionContext:
        """Get or create a session for a client."""
        if client_id not in self.sessions:
            self.sessions[client_id] = SessionContext()
        return self.sessions[client_id]

    def on_connect(self, client_id: str) -> None:
        """Handle client connection."""
        session = self.get_session(client_id)
        session.state = ConnectionState.CONNECTED
        logger.info(f"Client {client_id} connected, state: CONNECTED")

    def on_disconnect(self, client_id: str) -> None:
        """Handle client disconnection."""
        if client_id in self.sessions:
            del self.sessions[client_id]
        logger.info(f"Client {client_id} disconnected, session cleared")

    def handle_message(self, client_id: str, data: bytes) -> Optional[bytes]:
        """
        Process an incoming message and return a response.

        Args:
            client_id: Unique identifier for the connected client
            data: Raw message bytes

        Returns:
            Response bytes to send back, or None if no response needed
        """
        session = self.get_session(client_id)
        msg_type, parsed = parse_message(data)

        if msg_type is None:
            logger.warning(f"Invalid message from {client_id}")
            return ErrorMessage(ErrorCode.INVALID_MESSAGE).build()

        logger.info(f"Received {msg_type.name} from {client_id} in state {session.state.name}")

        # State machine dispatch
        if msg_type == MessageType.AUTH_REQUEST:
            return self._handle_auth_request(session, parsed)
        elif msg_type == MessageType.CREDENTIAL:
            return self._handle_credential(session, parsed)
        else:
            logger.warning(f"Unexpected message type {msg_type} in state {session.state}")
            return ErrorMessage(ErrorCode.INVALID_STATE).build()

    def _reset_session(self, session: SessionContext) -> None:
        """Reset session to initial connected state for a new authentication flow."""
        session.device_id = None
        session.device_key = None
        session.nonce_mobile = None
        session.nonce_reader = None
        session.state = ConnectionState.CONNECTED
        logger.info("Session reset for new connection")

    def _handle_auth_request(
        self, session: SessionContext, request: Optional[AuthRequest]
    ) -> bytes:
        """Handle AUTH_REQUEST message."""
        # Allow AUTH_REQUEST in CONNECTED state, or reset session if in terminal/stale state
        # This handles reconnections when bless doesn't provide per-client tracking
        if session.state in (ConnectionState.COMPLETE, ConnectionState.IDLE):
            logger.info(f"AUTH_REQUEST received in {session.state.name} state, treating as new connection")
            self._reset_session(session)
        elif session.state != ConnectionState.CONNECTED:
            logger.warning(f"AUTH_REQUEST in invalid state: {session.state}")
            return ErrorMessage(ErrorCode.INVALID_STATE).build()

        if request is None:
            logger.warning("Failed to parse AUTH_REQUEST")
            return ErrorMessage(ErrorCode.INVALID_MESSAGE).build()

        session.state = ConnectionState.AUTHENTICATING
        logger.info(f"Processing AUTH_REQUEST for device {request.device_id.hex()}")

        # Derive device key from master key + device ID
        try:
            device_key = derive_device_key(self.master_key, request.device_id)
            session.device_id = request.device_id
            session.device_key = device_key
        except Exception as e:
            logger.error(f"Key derivation failed: {e}")
            session.state = ConnectionState.CONNECTED
            return ErrorMessage(ErrorCode.UNKNOWN_DEVICE).build()

        # Decrypt the mobile's nonce
        try:
            nonce_mobile = decrypt(device_key, request.iv, request.encrypted_nonce)
            if len(nonce_mobile) != NONCE_SIZE:
                raise ValueError(f"Decrypted nonce wrong size: {len(nonce_mobile)}")
            session.nonce_mobile = nonce_mobile
            logger.info(f"Decrypted mobile nonce: {nonce_mobile.hex()}")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            session.state = ConnectionState.CONNECTED
            return ErrorMessage(ErrorCode.DECRYPTION_FAILED).build()

        # Generate reader's nonce
        nonce_reader = generate_nonce()
        session.nonce_reader = nonce_reader
        logger.info(f"Generated reader nonce: {nonce_reader.hex()}")

        # Build response: Enc_DK(Nonce_M || Nonce_R)
        combined_nonces = nonce_mobile + nonce_reader
        iv, encrypted_nonces = encrypt(device_key, combined_nonces)

        session.state = ConnectionState.AUTHENTICATED
        logger.info("Authentication successful, state: AUTHENTICATED")

        response = AuthResponse(iv=iv, encrypted_nonces=encrypted_nonces)
        return response.build()

    def _handle_credential(
        self, session: SessionContext, credential: Optional[Credential]
    ) -> bytes:
        """Handle CREDENTIAL message."""
        # Validate state
        if session.state != ConnectionState.AUTHENTICATED:
            logger.warning(f"CREDENTIAL in invalid state: {session.state}")
            return ErrorMessage(ErrorCode.INVALID_STATE).build()

        if credential is None:
            logger.warning("Failed to parse CREDENTIAL")
            return ErrorMessage(ErrorCode.INVALID_MESSAGE).build()

        if session.device_key is None:
            logger.error("No device key in session")
            return ErrorMessage(ErrorCode.INVALID_STATE).build()

        session.state = ConnectionState.PROCESSING
        logger.info("Processing credential")

        # Decrypt the credential payload
        try:
            payload = decrypt(session.device_key, credential.iv, credential.encrypted_payload)
            logger.info(f"Decrypted credential payload ({len(payload)} bytes): {payload.hex()}")
        except Exception as e:
            logger.error(f"Credential decryption failed: {e}")
            session.state = ConnectionState.AUTHENTICATED
            return ErrorMessage(ErrorCode.DECRYPTION_FAILED).build()

        # Process credential (for POC, just log and accept)
        # In production, this would validate against a database, check expiry, etc.
        status = self._validate_credential(payload)

        session.state = ConnectionState.COMPLETE
        logger.info(f"Credential processing complete, status: {status.name}")

        return CredentialResponse(status=status).build()

    def _validate_credential(self, payload: bytes) -> CredentialStatus:
        """
        Validate a credential payload.

        For POC purposes, this just accepts all credentials.
        In production, implement actual validation logic here.
        """
        # POC: Accept all credentials
        logger.info(f"Validating credential: {payload}")
        return CredentialStatus.SUCCESS
