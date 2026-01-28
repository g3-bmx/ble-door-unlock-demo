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
   scp ble_server.py monarch@<YOUR_INTERCOM_IP_ADDRESS>:/home/monarch/
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
