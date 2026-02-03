"""
WebSocket server for credential validation delegation.

Allows external applications to receive decrypted credentials and
return validation results to the GATT server.
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Awaitable

import websockets
from websockets.server import WebSocketServerProtocol, serve

from .protocol import CredentialStatus

logger = logging.getLogger(__name__)

# WebSocket server configuration
WEBSOCKET_HOST = "localhost"
WEBSOCKET_PORT = 8799
VALIDATION_TIMEOUT = 3.0  # seconds


class CredentialValidationServer:
    """
    WebSocket server that delegates credential validation to external applications.

    Broadcasts credential data to all connected clients and waits for a
    validation response. Falls back to local validation on timeout or
    when no clients are connected.
    """

    def __init__(
        self,
        host: str = WEBSOCKET_HOST,
        port: int = WEBSOCKET_PORT,
        timeout: float = VALIDATION_TIMEOUT,
        fallback_validator: Optional[Callable[[bytes], CredentialStatus]] = None,
    ):
        """
        Initialize the WebSocket validation server.

        Args:
            host: Host to bind the WebSocket server to
            port: Port to bind the WebSocket server to
            timeout: Seconds to wait for validation response before fallback
            fallback_validator: Function to call when no WebSocket response available
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.fallback_validator = fallback_validator or self._default_fallback
        self._clients: set[WebSocketServerProtocol] = set()
        self._server: Optional[websockets.WebSocketServer] = None
        self._response_event: Optional[asyncio.Event] = None
        self._validation_response: Optional[CredentialStatus] = None

    def _default_fallback(self, payload: bytes) -> CredentialStatus:
        """Default fallback: accept all credentials (POC behavior)."""
        logger.info("Fallback validation: accepting credential")
        return CredentialStatus.SUCCESS

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await serve(
            self._handle_client,
            self.host,
            self.port,
        )
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("WebSocket server stopped")

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a WebSocket client connection."""
        self._clients.add(websocket)
        client_info = f"{websocket.remote_address}"
        logger.info(f"WebSocket client connected: {client_info}")

        try:
            async for message in websocket:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket client disconnected: {client_info}")
        finally:
            self._clients.discard(websocket)

    async def _handle_message(self, message: str) -> None:
        """Handle an incoming validation response from a client."""
        try:
            data = json.loads(message)
            status_str = data.get("status", "").upper()

            try:
                status = CredentialStatus[status_str]
            except KeyError:
                logger.warning(f"Invalid status value received: {status_str}")
                return

            logger.info(f"Received validation response: {status.name}")
            self._validation_response = status

            if self._response_event:
                self._response_event.set()

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON received: {message}")

    async def validate_credential(
        self,
        credential: bytes,
        device_id: bytes,
    ) -> CredentialStatus:
        """
        Validate a credential by delegating to connected WebSocket clients.

        Args:
            credential: Decrypted credential payload
            device_id: Device identifier

        Returns:
            CredentialStatus from WebSocket client or fallback validation
        """
        if not self._clients:
            logger.info("No WebSocket clients connected, using fallback validation")
            return self.fallback_validator(credential)

        # Prepare the credential request
        request = {
            "credential": credential.hex(),
            "device_id": device_id.hex(),
        }
        message = json.dumps(request)

        # Set up response handling
        self._response_event = asyncio.Event()
        self._validation_response = None

        # Broadcast to all connected clients
        logger.info(f"Broadcasting credential to {len(self._clients)} client(s)")
        await self._broadcast(message)

        # Wait for response with timeout
        try:
            await asyncio.wait_for(
                self._response_event.wait(),
                timeout=self.timeout,
            )

            if self._validation_response:
                logger.info(f"Using WebSocket validation result: {self._validation_response.name}")
                return self._validation_response

        except asyncio.TimeoutError:
            logger.warning(f"Validation timeout after {self.timeout}s, using fallback")

        return self.fallback_validator(credential)

    async def _broadcast(self, message: str) -> None:
        """Broadcast a message to all connected clients."""
        if not self._clients:
            return

        # Send to all clients, removing any that fail
        disconnected = set()
        for client in self._clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)

        self._clients -= disconnected

    @property
    def client_count(self) -> int:
        """Return the number of connected clients."""
        return len(self._clients)

    @property
    def is_running(self) -> bool:
        """Return whether the server is running."""
        return self._server is not None and self._server.is_serving()
