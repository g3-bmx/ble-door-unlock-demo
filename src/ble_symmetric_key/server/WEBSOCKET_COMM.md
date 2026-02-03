# WebSocket Communication Layer

This document describes the WebSocket server that enables external applications to validate credentials received by the BLE GATT server.

## Overview

The GATT server exposes a WebSocket interface on `localhost:8799` that allows external applications to:
1. Receive decrypted credential data from BLE clients
2. Perform custom validation logic
3. Return validation results to the GATT server

This decouples credential validation from the BLE layer, allowing flexible integration with access control systems, databases, or other validation services.

## Configuration

| Setting | Value |
|---------|-------|
| Host | `localhost` |
| Port | `8799` |
| Protocol | WebSocket (ws://) |

## Connection Behavior

- **Multiple clients**: If multiple WebSocket clients connect, credential data is broadcast to all active connections.
- **No clients connected**: Falls back to local validation (accepts all credentials in POC mode).
- **Response timeout**: 3 seconds. If no response is received, falls back to local validation.

## Message Formats

### Credential Request (GATT → WebSocket Client)

Sent when the GATT server receives and decrypts a credential from a BLE client.

```json
{
  "credential": "<hex-encoded decrypted payload>",
  "device_id": "<hex-encoded device id>"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `credential` | string | Hex-encoded decrypted credential payload |
| `device_id` | string | Hex-encoded device identifier (8 bytes) |

### Validation Response (WebSocket Client → GATT)

The external application must respond with a validation result.

```json
{
  "status": "<STATUS_VALUE>"
}
```

| Status Value | Description |
|--------------|-------------|
| `SUCCESS` | Credential is valid, grant access |
| `DENIED` | Credential is invalid, deny access |
| `EXPIRED` | Credential has expired |
| `REVOKED` | Credential has been revoked |
| `UNKNOWN_ERROR` | Validation failed due to an error |

## Sequence Diagram

```
BLE Client          GATT Server           WebSocket Client
    |                    |                       |
    |-- CREDENTIAL ----->|                       |
    |                    |-- credential req ---->|
    |                    |                       |
    |                    |<-- validation resp ---|
    |<-- CRED_RESPONSE --|                       |
    |                    |                       |
```

## Timeout & Fallback Behavior

1. GATT server decrypts credential and sends to WebSocket clients
2. Waits up to **3 seconds** for a response
3. If response received: uses the provided status
4. If timeout or no clients: falls back to local validation (POC accepts all)

## Example WebSocket Client (Python)

```python
import asyncio
import websockets
import json

async def credential_validator():
    uri = "ws://localhost:8799"
    async with websockets.connect(uri) as websocket:
        print("Connected to GATT server")

        async for message in websocket:
            data = json.loads(message)
            print(f"Received credential: {data['credential']}")
            print(f"Device ID: {data['device_id']}")

            # Perform validation logic here
            is_valid = validate_credential(data['credential'])

            response = {
                "status": "SUCCESS" if is_valid else "DENIED"
            }
            await websocket.send(json.dumps(response))

def validate_credential(credential_hex):
    # Custom validation logic
    return True

asyncio.run(credential_validator())
```

## Integration Notes

- The WebSocket server runs alongside the GATT server in the same process
- Both servers share the same event loop for coordinated async operation
- The WebSocket interface is intended for local integrations only (localhost binding)
