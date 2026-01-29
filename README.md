# BLE Door Unlock Demo

A cross-platform BLE GATT server demonstrating challenge-response authentication for door unlock.
Uses the `bless` library (server) and `bleak` library (client) to run on both macOS (CoreBluetooth) and Linux (BlueZ).

## Overview

This project implements a BLE peripheral ("Intercom") that uses Ed25519 challenge-response authentication:

1. Client connects to server
2. Server generates a random 16-byte nonce and sends it to client
3. Client signs the nonce with its private key
4. Server verifies the signature using the client's pre-registered public key
5. If valid, server logs it, client disconnects.

It's just a simple demo to experiment with characteristics and how the nonce exchange / signature flow works. the real production solution will be a little more complex, but taking baby steps is important!

### Service & Characteristics

**Door Access Service UUID:** `12340000-1234-5678-9ABC-DEF012345678`

| Characteristic | UUID | Properties | Size | Purpose |
|---------------|------|------------|------|---------|
| Challenge | `12340000-1234-5678-9ABC-DEF012345235` | Read, Notify | 16 bytes | Server sends nonce to client |
| Response | `12340000-1234-5678-9ABC-DEF012345236` | Write | 64 bytes | Client sends Ed25519 signature |

## Running the Demo

### Linux Intercom (Server)

1. copy the `ble_door_unlock_server` folder to the intercom

```bash
scp -r src/ble_door_unlock_server monarch@<YOUR_INTERCOM_IP_ADDRESS>:/home/monarch
```

2. ssh into your intercom and travel to the location containing `ble_door_unlock_server` (dont cd into it)

```
cd /home/monarch
```

3. Install the dependency (one-time):

```bash
pip3 install bless==0.3.0
```

4. run the ble server on the linux intercom

```bash
python3 -m ble_door_unlock_server.main
```

Requirements: BlueZ 5.43+ and D-Bus. The intercom runs BlueZ 5.64.

Note: observe the logs and verify server is running. You can now start the client on another device.

### MacOS (Client)

1. Install dependencies:

```
uv sync
```

2. cd into `src` folder

```
cd src
```

3. Run the client:

```
uv run python -m ble_client auth
```

Note: macOS will prompt for Bluetooth permission on first run. Grant access for the server to advertise.

### Client Commands

```bash
# Scan for all nearby BLE devices
uv run python -m ble_client scan

# Connect and receive challenge nonce (via notification)
uv run python -m ble_client challenge

# Connect and read challenge nonce (direct read)
uv run python -m ble_client read-challenge

# Perform full challenge-response authentication
uv run python -m ble_client auth

# Specify device name and timeouts
uv run python -m ble_client auth -n "Intercom" -t 15 --challenge-timeout 20
```

## Testing with nRF Connect

[nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile) is a mobile app (iOS/Android) for BLE testing.

**Scanning:**
1. Open nRF Connect and tap "Scan"
2. Look for **"Intercom"** in the results
3. The device shows service UUID `12340000-1234-5678-9ABC-DEF012345678`

**Connecting:**
1. Tap "Connect" on the Intercom device
2. Expand the Door Access Service
3. You'll see Challenge and Response characteristics

**Testing the flow:**
1. Subscribe to the Challenge characteristic (tap the triple-down-arrow icon)
2. You'll receive a 16-byte nonce notification
3. To test writes, write 64 bytes to the Response characteristic (the server will attempt to verify it as an Ed25519 signature)

## Authentication Flow

```
┌─────────────┐                              ┌─────────────┐
│   Client    │                              │   Server    │
│  (Mobile)   │                              │ (Intercom)  │
└──────┬──────┘                              └──────┬──────┘
       │                                            │
       │  1. BLE Connect                            │
       │ ──────────────────────────────────────────>│
       │                                            │
       │  2. Subscribe to Challenge characteristic  │
       │ ──────────────────────────────────────────>│
       │                                            │
       │                              ┌─────────────┴─────────────┐
       │                              │ Generate 16-byte nonce    │
       │                              │ Start 30-second timeout   │
       │                              └─────────────┬─────────────┘
       │                                            │
       │  3. Notification: nonce (16 bytes)         │
       │ <──────────────────────────────────────────│
       │                                            │
       │ ┌────────────────────────────┐             │
       │ │ Sign nonce with Ed25519    │             │
       │ │ private key                │             │
       │ └────────────────────────────┘             │
       │                                            │
       │  4. Write signature to Response (64 bytes) │
       │ ──────────────────────────────────────────>│
       │                                            │
       │                              ┌─────────────┴─────────────┐
       │                              │ Verify signature with     │
       │                              │ client's public key       │
       │                              │                           │
       │                              │ Valid? → Access granted   │
       │                              │ Invalid? → Access denied  │
       │                              └───────────────────────────┘
```

## Security Notes

- **Demo only:** Keys are hardcoded for demonstration purposes
- **Pre-shared keys:** In production, client public keys would be registered during device pairing
- **Nonce expiration:** Nonces expire after 30 seconds and are single-use to prevent replay attacks
- **No BLE-level encryption:** Security is handled at the application layer (see [docs/ble-service-door-unlock.md](docs/ble-service-door-unlock.md) for the full spec)

## Project Structure

```
src/
├── ble_door_unlock_server/
│   ├── __init__.py
│   ├── __main__.py           # Server CLI entry point
│   ├── server.py             # GATT server with auth logic
│   └── connection_monitor.py # BlueZ connection workaround
└── ble_client/
    ├── __init__.py
    ├── __main__.py           # Client CLI entry point
    └── client.py             # BLE client with signing logic
```

## Troubleshooting

- **Device doesn't appear in scan:** Ensure the server is running and Bluetooth is enabled
- **macOS permission issues:** Grant Bluetooth permission to the terminal app
- **BlueZ issues on Linux:** Ensure BlueZ 5.43+ is installed and D-Bus is running
- **Connection timeout:** Try toggling Bluetooth off/on or restarting the scan
