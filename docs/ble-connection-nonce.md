# BLE Connection & Challenge Flow - Implementation Guide

This document describes the implementation of steps 1-3 of the door unlock protocol:

1. Mobile application scans for intercom advertising messages
2. Mobile application connects to intercom (BLE connect)
3. Intercom responds with nonce challenge

---

## Overview

The challenge flow establishes a secure session between the mobile client and the intercom. The intercom generates a fresh cryptographic nonce for each connection, which the mobile client will use to derive session keys for encryption in subsequent steps.

```
┌─────────────┐                                    ┌─────────────┐
│   Mobile    │                                    │  Intercom   │
│  (Central)  │                                    │ (Peripheral)│
└──────┬──────┘                                    └──────┬──────┘
       │                                                  │
       │  1. Scan for "Intercom"                          │
       │ ────────────────────────────────────────────────>│
       │                                                  │
       │  2. Connect                                      │
       │ ────────────────────────────────────────────────>│
       │                                                  │ (generates 16-byte nonce)
       │                                                  │ (starts 30s timeout)
       │                                                  │
       │  3. Subscribe to Challenge characteristic        │
       │ ────────────────────────────────────────────────>│
       │                                                  │
       │  4. Notification: nonce (16 bytes)               │
       │ <────────────────────────────────────────────────│
       │                                                  │
       │  (client stores nonce for authentication)        │
       │                                                  │
```

---

## GATT Service Structure

### Door Access Service

| Attribute | Value |
|-----------|-------|
| Service UUID | `12340000-1234-5678-9ABC-DEF012345678` |

### Challenge Characteristic

| Attribute | Value |
|-----------|-------|
| UUID | `12340000-1234-5678-9ABC-DEF012345235` (short: `0x1235`) |
| Properties | Read, Notify |
| Permissions | Open (no BLE-level encryption) |
| Value | 16 bytes (challenge nonce) |

---

## Server Implementation

### Nonce Generation

The server generates a cryptographically secure 16-byte nonce using `secrets.token_bytes(16)`. This nonce is:

- Generated fresh for each new connection
- Stored with a timestamp for timeout tracking
- Invalidated after 30 seconds or after successful authentication
- Single-use (prevents replay attacks)

### Nonce State

```python
@dataclass
class NonceState:
    value: bytes          # 16-byte nonce
    created_at: float     # timestamp (time.time())
    used: bool            # whether it's been consumed
```

### Server Behavior

| Event | Action |
|-------|--------|
| Client connects | Generate new nonce, store with timestamp, start 30s timer |
| Client subscribes to Challenge char | Send nonce via notification |
| Client reads Challenge char | Return current nonce |
| 30 seconds elapsed | Invalidate nonce (do NOT auto-regenerate or notify) |
| Successful authentication | Invalidate nonce immediately |

### Timeout Handling

When the nonce expires after 30 seconds:
- The nonce is marked as invalid
- No new notification is sent
- Client must disconnect and reconnect to get a fresh nonce
- This prevents stale sessions from lingering

---

## Client Implementation

### Connection Flow

```python
async def connect_and_get_challenge(self) -> bytes | None:
    """
    Complete connection flow:
    1. Scan for device
    2. Connect
    3. Subscribe to challenge characteristic
    4. Wait for and return the nonce
    """
```

### Client State

After the challenge flow, the client stores:
- `challenge_nonce: bytes` - The 16-byte nonce received from the server

This nonce will be used in step 4 (authentication) to:
- Derive session keys via HKDF
- Encrypt the authentication payload

### Subscription Handling

The client subscribes to notifications on the Challenge characteristic. When a notification arrives:
1. Validate it's 16 bytes
2. Store the nonce
3. Signal that the challenge was received (asyncio.Event)

---

## UUIDs

Both server and client must use matching UUIDs:

```python
# Door Access Service
SERVICE_UUID = "12340000-1234-5678-9ABC-DEF012345678"

# Challenge Characteristic (Read, Notify)
CHALLENGE_CHAR_UUID = "12340000-1234-5678-9ABC-DEF012345235"
```

Note: The old UUIDs (`E7B2C021-...`) are replaced with the spec-defined UUIDs.

---

## Testing the Flow

### Start the Server

```bash
# Terminal 1
python -m ble_door_unlock_server -v
```

Expected output:
```
Starting GATT server: Intercom
GATT server started
  Service UUID: 12340000-1234-5678-9ABC-DEF012345678
  Challenge Characteristic UUID: 12340000-1234-5678-9ABC-DEF012345235
```

### Run the Client

```bash
# Terminal 2 (on a separate device or with a second Bluetooth adapter)
python -m ble_client challenge
```

Expected output:
```
Scanning for device: Intercom
Found device: Intercom (XX:XX:XX:XX:XX:XX)
Connecting...
Connected: True
Subscribing to challenge characteristic...
Received challenge nonce: a1b2c3d4e5f6... (16 bytes)
```

### Server Log on Connection

```
Client connected
Generated nonce: a1b2c3d4e5f6...
Client subscribed to challenge characteristic
Sent nonce notification
```

---

## Error Cases

| Scenario | Behavior |
|----------|----------|
| Client doesn't subscribe within 30s | Nonce expires, client must reconnect |
| Client subscribes but disconnects | Nonce is discarded, new one generated on next connection |
| Multiple subscription attempts | Same nonce is sent each time (until expired or used) |
| Nonce already used | Client receives error on auth attempt, must reconnect |

---

## Security Considerations

1. **Fresh nonce per connection**: Prevents replay attacks across sessions
2. **30-second timeout**: Limits window for attacks on a single nonce
3. **Single-use nonce**: Once authentication succeeds, nonce is invalidated
4. **No BLE-level encryption**: Security is handled at the application layer (AES-GCM in step 4)
5. **Single connection only**: Server accepts one client at a time, simplifying nonce management

---

## Next Steps

After this flow completes, the client has the nonce needed for step 4:

1. Compute shared secret: `ECDH(PrivMobile, PubIntercom)`
2. Derive session keys using HKDF with the nonce as salt
3. Encrypt the door unlock payload
4. Write to the Authentication characteristic

See [ble-service-door-unlock.md](ble-service-door-unlock.md) for the full protocol specification.
