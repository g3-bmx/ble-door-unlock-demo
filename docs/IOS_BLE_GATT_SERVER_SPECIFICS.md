# iOS BLE GATT Server Specifics

Technical documentation for the WaveLynx LEAF iOS SDK BLE GATT server implementation, extracted from the LeafBle.xcframework.

---

> **DISCLAIMER**
>
> This documentation is **tentative** and based entirely on reverse-engineering the publicly exposed headers, Swift interface files, and HTML documentation within the `LeafBle.xcframework`. The actual GATT UUID values are compiled into the binary and are not directly visible in the source headers.
>
> This document represents our best understanding of the BLE GATT architecture as of the analysis date. WaveLynx Technologies has not verified this information. Implementation details may differ from what is documented here.
>
> **Last analyzed:** 2026-02-02
> **SDK Version:** LeafBle.xcframework v6.0
> **Source:** `ios-sdk/LeafBle.xcframework/`

---

## Table of Contents

1. [Overview](#overview)
2. [GATT Service Architecture](#gatt-service-architecture)
3. [Service UUIDs](#service-uuids)
4. [Characteristic UUIDs](#characteristic-uuids)
5. [Descriptor UUIDs](#descriptor-uuids)
6. [Advertising Identifiers](#advertising-identifiers)
7. [Communication Pattern](#communication-pattern)
8. [iOS SDK Public Interface](#ios-sdk-public-interface)
9. [Known Limitations](#known-limitations)
10. [References](#references)

---

## Overview

The WaveLynx LEAF iOS SDK (`LeafBle.xcframework`) implements a BLE Central that communicates with WaveLynx LEAF readers (BLE Peripherals). The SDK abstracts the underlying GATT service/characteristic details through the `WlReader` struct, which exposes UUID constants for service discovery and data transfer.

### Framework Structure

```
LeafBle.xcframework/
├── ios-arm64/                          # Device architecture
│   └── LeafBle.framework/
│       ├── LeafBle                     # Compiled binary (contains actual UUIDs)
│       ├── Headers/
│       │   ├── LeafCore.h              # Protocol definitions
│       │   ├── LeafCentral.h           # State machine
│       │   ├── Aes.h                   # AES-128 CBC
│       │   └── Random.h                # RNG utilities
│       ├── Modules/
│       │   └── LeafBle.swiftmodule/
│       │       └── *.swiftinterface    # Swift public API
│       └── Info.plist
└── ios-arm64_x86_64-simulator/         # Simulator architecture
```

### Key Components

| Component | Role | Description |
|-----------|------|-------------|
| `WlBluetoothController` | BLE Manager | Singleton handling all CoreBluetooth operations |
| `WlTransaction` | Protocol Handler | Manages LEAF message protocol and state machine |
| `WlReader` | GATT Constants | Exposes service/characteristic UUIDs |
| `LeafCore` | C Library | Low-level protocol serialization |
| `LeafCentral` | C Library | Central device state machine |

---

## GATT Service Architecture

### Reader GATT Profile (Peripheral)

The WaveLynx LEAF reader exposes a minimal GATT profile optimized for credential transfer:

```
┌─────────────────────────────────────────────────────────────────┐
│                    LEAF Reader GATT Profile                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Service: BLE_CRED_SVC_UUID                               │  │
│  │  (WaveLynx Credential Service)                            │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  Characteristic: DATA_TRANSFER_CHRC_UUID            │  │  │
│  │  │  Properties: Write Without Response, Notify         │  │  │
│  │  │                                                     │  │  │
│  │  │  ┌───────────────────────────────────────────────┐  │  │  │
│  │  │  │  Descriptor: CHRC_UPDATE_NTF_DESCR_UUID       │  │  │  │
│  │  │  │  (Client Characteristic Config - 0x2902)      │  │  │  │
│  │  │  └───────────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Service: BLE_TOUCH_SVC_UUID                              │  │
│  │  (WaveLynx Touch Detection - Advertising Only)            │  │
│  │                                                           │  │
│  │  Note: This service UUID appears in advertisements        │  │
│  │  when a touch event is active. It is NOT exposed          │  │
│  │  in the actual GATT profile for connection.               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Service UUIDs

The `WlReader` struct exposes two service UUIDs. The actual UUID values are embedded in the compiled binary.

### BLE_CRED_SVC_UUID

| Property | Value |
|----------|-------|
| **Name** | `BLE_CRED_SVC_UUID` |
| **Type** | `CBUUID` (iOS) |
| **Purpose** | Main WaveLynx credential service |
| **Actual UUID** | *Embedded in binary - not visible in headers* |

**Description:**
This is the primary GATT service for LEAF reader communication. All credential transfer operations occur through characteristics within this service.

**Usage:**
- Scan filtering: Mobile device scans for peripherals advertising this UUID
- Service discovery: After connection, discover this service to access data transfer characteristic

### BLE_TOUCH_SVC_UUID

| Property | Value |
|----------|-------|
| **Name** | `BLE_TOUCH_SVC_UUID` |
| **Type** | `CBUUID` (iOS) |
| **Purpose** | Touch event detection |
| **Actual UUID** | *Embedded in binary - not visible in headers* |

**Description:**
This service UUID indicates a touch event is active on the reader. It appears in BLE advertisements but is **NOT** exposed in the actual GATT profile.

**Usage:**
- Scan filtering: Detect readers where a user has initiated a touch
- Intent detection: Differentiate between passive readers and readers expecting a credential
- **Not for connection**: Do not attempt to discover this service after connecting

---

## Characteristic UUIDs

### DATA_TRANSFER_CHRC_UUID

| Property | Value |
|----------|-------|
| **Name** | `DATA_TRANSFER_CHRC_UUID` |
| **Type** | `CBUUID` (iOS) |
| **Parent Service** | `BLE_CRED_SVC_UUID` |
| **Actual UUID** | *Embedded in binary - not visible in headers* |

**Properties:**

| Property | Supported | Description |
|----------|-----------|-------------|
| Write Without Response | Yes | Send command packets to reader |
| Notify | Yes | Receive response packets from reader |
| Read | No | Not supported |
| Write With Response | No | Not used (latency optimization) |
| Indicate | No | Not used |

**Communication Pattern:**

```
Mobile Device (Central)                    LEAF Reader (Peripheral)
        │                                           │
        │  ──── Write (cmd) ──────────────────────► │
        │                                           │
        │  ◄──── Notification (rsp) ────────────────│
        │                                           │
```

Every write operation to this characteristic triggers a notification response from the reader. This forms the command-response pattern used throughout the LEAF protocol.

**Supported Transaction Types:**
- Legacy credential transfer
- Signed credential transfer
- Encrypted link communication
- Unencrypted link communication (based on reader configuration)

---

## Descriptor UUIDs

### CHRC_UPDATE_NTF_DESCR_UUID

| Property | Value |
|----------|-------|
| **Name** | `CHRC_UPDATE_NTF_DESCR_UUID` |
| **Type** | `CBUUID` (iOS) |
| **Standard UUID** | `0x2902` (Client Characteristic Configuration) |
| **Parent Characteristic** | `DATA_TRANSFER_CHRC_UUID` |

**Description:**
This is the standard BLE Client Characteristic Configuration Descriptor (CCCD). Writing `0x0001` to this descriptor enables notifications on the Data Transfer Characteristic.

**Note:** While the SDK exposes this as a named constant, it is almost certainly the standard CCCD UUID (`2902`). The SDK likely includes it for convenience.

---

## Advertising Identifiers

### ETHOS_IDENTIFIER

| Property | Value |
|----------|-------|
| **Name** | `ETHOS_IDENTIFIER` |
| **Type** | `String` |
| **Default Value** | `"ETHS"` |

**Description:**
The default local name prefix advertised by LEAF readers. Used for scan filtering when service UUID filtering is insufficient.

**Usage:**
```swift
// Filter by advertised name prefix
if peripheral.name?.hasPrefix(WlReader.ETHOS_IDENTIFIER) == true {
    // This is likely a WaveLynx reader
}
```

### IBEACON_UUID

| Property | Value |
|----------|-------|
| **Name** | `IBEACON_UUID` |
| **Type** | `UUID` |
| **Actual UUID** | *Embedded in binary - not visible in headers* |

**Description:**
Some LEAF readers can be configured to periodically broadcast iBeacon advertisements. This UUID identifies WaveLynx iBeacon broadcasts.

**Usage:**
- Region monitoring: Wake app when entering proximity of readers
- Background detection: iOS can detect iBeacons even when app is suspended
- Presence awareness: Determine if user is near access-controlled areas

---

## Communication Pattern

### GATT Operation Sequence

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BLE GATT Operation Sequence                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Mobile Device                                           LEAF Reader         │
│       │                                                       │              │
│  1.   │  ──── Scan for BLE_CRED_SVC_UUID ─────────────────►  │              │
│       │                                                       │              │
│  2.   │  ◄──── Advertisement (Service UUIDs, Name) ──────────│              │
│       │                                                       │              │
│  3.   │  ──── Connect Request ────────────────────────────►  │              │
│       │                                                       │              │
│  4.   │  ◄──── Connection Established ────────────────────── │              │
│       │                                                       │              │
│  5.   │  ──── Discover Services ──────────────────────────►  │              │
│       │                                                       │              │
│  6.   │  ◄──── BLE_CRED_SVC_UUID found ───────────────────── │              │
│       │                                                       │              │
│  7.   │  ──── Discover Characteristics ───────────────────►  │              │
│       │                                                       │              │
│  8.   │  ◄──── DATA_TRANSFER_CHRC_UUID found ─────────────── │              │
│       │                                                       │              │
│  9.   │  ──── Write CCCD (enable notifications) ──────────►  │              │
│       │                                                       │              │
│  10.  │  ◄──── Write Response ────────────────────────────── │              │
│       │                                                       │              │
│       │         ═══════ LEAF Protocol Begins ═══════         │              │
│       │                                                       │              │
│  11.  │  ──── Write (DUID + AUTH_REQ) ────────────────────►  │              │
│       │                                                       │              │
│  12.  │  ◄──── Notification (AUTH_RSP + AUTH_REQ) ────────── │              │
│       │                                                       │              │
│       │                     ... etc ...                       │              │
│       │                                                       │              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Transfer Characteristics

| Direction | GATT Operation | BLE Property | Latency |
|-----------|---------------|--------------|---------|
| Central → Peripheral | Write | Without Response | ~7.5ms |
| Peripheral → Central | Notify | Notification | ~7.5ms |

**Why Write Without Response?**
Write Without Response eliminates the acknowledgment round-trip, reducing latency. The LEAF protocol handles reliability at the application layer through sequence numbers and transaction state.

---

## iOS SDK Public Interface

### WlReader Struct

The complete public interface for GATT constants:

```swift
public struct WlReader {
    /// Main WaveLynx service UUID for reader communication
    /// Used for scan filtering and service discovery
    public static let BLE_CRED_SVC_UUID: CBUUID

    /// Touch event service UUID (advertising only, not in GATT profile)
    /// Indicates reader has active touch - used for scan filtering
    public static let BLE_TOUCH_SVC_UUID: CBUUID

    /// Data transfer characteristic UUID
    /// Properties: Write Without Response, Notify
    public static let DATA_TRANSFER_CHRC_UUID: CBUUID

    /// Client Characteristic Configuration Descriptor UUID
    /// Standard 0x2902 - used to enable notifications
    public static let CHRC_UPDATE_NTF_DESCR_UUID: CBUUID

    /// Default reader advertising name prefix
    /// Value: "ETHS"
    public static let ETHOS_IDENTIFIER: String

    /// iBeacon UUID for proximity detection
    public static let IBEACON_UUID: UUID
}
```

### WlBluetoothController

Singleton that manages all BLE operations:

```swift
public class WlBluetoothController {
    /// Shared singleton instance
    public static let shared: WlBluetoothController

    /// Event delegate for BLE callbacks
    public var delegate: WlBluetoothEventDelegate?

    /// Start scanning for LEAF readers
    public func startScan()

    /// Stop scanning
    public func stopScan()

    /// Connect to a discovered reader
    public func connect(to peripheral: CBPeripheral)

    /// Disconnect from reader
    public func disconnect()

    /// Send data to connected reader
    public func send(_ data: Data)
}
```

### WlBluetoothEventDelegate

Protocol for receiving BLE events:

```swift
public protocol WlBluetoothEventDelegate {
    /// Called when a reader is discovered during scanning
    func didDiscover(peripheral: CBPeripheral, rssi: NSNumber)

    /// Called when connection to reader is established
    func didConnect(peripheral: CBPeripheral)

    /// Called when disconnected from reader
    func didDisconnect(peripheral: CBPeripheral, error: Error?)

    /// Called when data is received from reader (notification)
    func didReceive(data: Data)

    /// Called when ready to send data (GATT discovery complete)
    func didBecomeReady()
}
```

---

## Known Limitations

### UUID Visibility

The actual UUID values for services and characteristics are **not visible** in the public headers or Swift interface files. They are embedded in the compiled binary (`LeafBle.framework/LeafBle`).

**What we know:**
- The UUIDs exist as static constants on `WlReader`
- They are of type `CBUUID` (128-bit BLE UUIDs)
- The SDK uses them internally for scan filtering and GATT operations

**What we don't know:**
- The actual 128-bit UUID values
- Whether they are standard 16-bit UUIDs or custom 128-bit UUIDs
- Any vendor-specific characteristics beyond `DATA_TRANSFER_CHRC_UUID`

### Extracting UUIDs from Binary

To obtain the actual UUID values, one would need to:
1. Reverse-engineer the Mach-O binary
2. Use runtime inspection on a device
3. Capture BLE traffic with a sniffer (Wireshark + nRF Sniffer)
4. Request documentation from WaveLynx Technologies

### Touch Service Ambiguity

The documentation indicates `BLE_TOUCH_SVC_UUID` is "NOT exposed in the actual GATT profile." This likely means:
- It appears in advertisement data as a service UUID
- You cannot discover it after connecting
- Its sole purpose is scan filtering

---

## References

### SDK Source Files

| File | Path | Purpose |
|------|------|---------|
| LeafCore.h | [ios-sdk/LeafBle.xcframework/.../Headers/LeafCore.h](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Headers/LeafCore.h) | Protocol structures |
| LeafCentral.h | [ios-sdk/LeafBle.xcframework/.../Headers/LeafCentral.h](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Headers/LeafCentral.h) | State machine |
| Swift Interface | [ios-sdk/LeafBle.xcframework/.../LeafBle.swiftinterface](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Modules/LeafBle.swiftmodule/arm64-apple-ios.swiftinterface) | Public Swift API |

### Related Documentation

| Document | Description |
|----------|-------------|
| [BLE_COMMUNICATION_FLOWS.md](./BLE_COMMUNICATION_FLOWS.md) | Detailed protocol flows and state machine |
| [WAVELYNX_BLE_SECURITY_MODEL.md](./WAVELYNX_BLE_SECURITY_MODEL.md) | Security architecture and encryption |
| [KEY_MANAGEMENT_FAQ.md](./KEY_MANAGEMENT_FAQ.md) | Key rotation and management |
| [iOS SDK README](../ios-sdk/README.md) | Framework integration guide |
| [iOS SDK HTML Docs](../ios-sdk/docs/index.html) | Full API reference (Jazzy-generated) |

### External Resources

| Resource | URL |
|----------|-----|
| LEAF Community | https://www.leaf-community.com/ |
| WaveLynx Support | https://support.wavelynx.com/ |
| Apple CoreBluetooth | https://developer.apple.com/documentation/corebluetooth |
| BLE GATT Specification | https://www.bluetooth.com/specifications/gatt/ |

---

*Document generated from analysis of WaveLynx LEAF iOS SDK (LeafBle.xcframework v6.0). This is tentative documentation based on publicly exposed interfaces and may not reflect the complete or accurate implementation.*
