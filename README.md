# BLE Door Unlock

A cross-platform BLE GATT server for door unlock proof-of-concept.
Uses the `bless` library to run on both macOS (CoreBluetooth) and Linux (BlueZ).

## Context

This project implements a BLE peripheral that advertises as "Intercom" and exposes a GATT service for receiving data from mobile devices. When a client connects and writes to the characteristic, the server logs the received data.

**Service UUID:** `E7B2C021-5D07-4D0B-9C20-223488C8B012`
**Characteristic UUID:** `E7B2C021-5D07-4D0B-9C20-223488C8B013`

The characteristic supports:
- Read
- Write
- Write without response

## Setup

### Run Locally (macOS)

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Run the server:
   ```bash
   uv run python ble_server.py
   ```

3. Run with verbose logging:
   ```bash
   uv run python ble_server.py -v
   ```

> **Note:** macOS will prompt for Bluetooth permission on first run. Grant access for the server to advertise.

### Run on Intercom (Linux)

1. Copy the single-file server to the device:
   ```bash
   scp ble_server_basic.py monarch@<YOUR_INTERCOM_IP_ADDRESS>:/home/monarch/
   ```

2. Install the dependency (one-time):
   ```bash
   pip3 install bless==0.3.0
   ```

3. Run the server:
   ```bash
   python3 ble_server.py
   ```

4. Run with verbose logging:
   ```bash
   python3 ble_server.py -v
   ```

> **Requirements:** BlueZ 5.43+ and D-Bus. The intercom runs BlueZ 5.64.

### Observability

Once the GATT server is running (either locally / intercom), you can view the BLE advertising
through a mobile app called "nRF connect". That app listens to all BLE advertising and allows 
you to connect and explore the GATT services and characteristics that we are working on.

#### Using nRF Connect

[nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile) is a mobile app (iOS/Android) for scanning and interacting with BLE peripherals. Use it to verify the GATT server is advertising and functioning correctly.

**Scanning for the device:**
1. Open nRF Connect and tap "Scan"
2. Look for a device named **"Intercom"** in the scan results
3. The device will show as connectable with the service UUID `E7B2C021-5D07-4D0B-9C20-223488C8B012`

**Connecting and exploring services:**
1. Tap "Connect" on the Intercom device
2. Once connected, the app will discover services automatically
3. Expand the service with UUID `E7B2C021-5D07-4D0B-9C20-223488C8B012`
4. You'll see the characteristic `E7B2C021-5D07-4D0B-9C20-223488C8B013` with Read/Write properties

**Testing read/write:**
1. Tap the **down arrow** icon to read the current characteristic value
2. Tap the **up arrow** icon to write data to the characteristic
3. Select "Text" format and enter a test message (e.g., "Hello")
4. Tap "Send" — the server terminal will log the received data

**Troubleshooting:**
- If the device doesn't appear, ensure the BLE server is running and Bluetooth is enabled
- On macOS, ensure Bluetooth permissions were granted to the terminal
- Try toggling Bluetooth off/on or restarting the scan
