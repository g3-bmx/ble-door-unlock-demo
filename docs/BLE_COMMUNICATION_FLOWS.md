# WaveLynx LEAF BLE Communication Flows

A deep-dive technical reference for engineers implementing or debugging BLE communication between mobile devices and WaveLynx LEAF readers.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [BLE Service Discovery](#ble-service-discovery)
3. [Transaction State Machine](#transaction-state-machine)
4. [Message Format Specification](#message-format-specification)
5. [Authentication Protocol](#authentication-protocol)
6. [Credential Transfer](#credential-transfer)
7. [Encryption & Decryption](#encryption--decryption)
8. [Multi-Packet Messaging](#multi-packet-messaging)
9. [Error Handling](#error-handling)
10. [Implementation Requirements](#implementation-requirements)
11. [Debugging Guide](#debugging-guide)

---

## Architecture Overview

### Roles

| Role | BLE Role | Description |
|------|----------|-------------|
| **Mobile Device** | Central | Initiates connection, drives the transaction state machine |
| **LEAF Reader** | Peripheral | Advertises services, responds to authentication, validates credentials |

### Communication Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│         (WlTransaction / WlBluetoothController)             │
├─────────────────────────────────────────────────────────────┤
│                    LEAF Protocol Layer                       │
│   (Message serialization, authentication, encryption)        │
├─────────────────────────────────────────────────────────────┤
│                    BLE GATT Layer                            │
│         (Service/Characteristic read/write/notify)          │
├─────────────────────────────────────────────────────────────┤
│                    BLE Link Layer                            │
│              (Connection, MTU negotiation)                   │
└─────────────────────────────────────────────────────────────┘
```

### SDK Components

**iOS SDK Classes:**
- `WlBluetoothController` - BLE scanning, connection, and GATT operations
- `WlTransaction` - Protocol state machine and message handling
- `LeafCentral` - Core C library for central device logic
- `LeafCore` - Data structures and serialization functions

**Key Header Files:**
- [LeafCore.h](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Headers/LeafCore.h) - Protocol definitions (341 lines)
- [LeafCentral.h](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Headers/LeafCentral.h) - State machine (44 lines)
- [Aes.h](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Headers/Aes.h) - AES-128 CBC (56 lines)

---

## BLE Service Discovery

### Reader Advertisement

LEAF readers advertise with specific service UUIDs that the mobile device scans for:

```swift
public struct WlReader {
    public static let BLE_CRED_SVC_UUID: CBUUID        // Credential service UUID
    public static let BLE_TOUCH_SVC_UUID: CBUUID       // Touch service UUID
    public static let DATA_TRANSFER_CHRC_UUID: CBUUID  // Data transfer characteristic
    public static let CHRC_UPDATE_NTF_DESCR_UUID: CBUUID // Notification descriptor
    public static let ETHOS_IDENTIFIER: String         // "ETHS" - default reader name prefix
    public static let IBEACON_UUID: UUID               // iBeacon proximity UUID
}
```

### Connection Sequence

```
Mobile Device                                    LEAF Reader
      │                                               │
      │  1. Scan for BLE_CRED_SVC_UUID               │
      │  ◄──────────── Advertisement ─────────────────│
      │                                               │
      │  2. Initiate Connection                       │
      │  ─────────────────────────────────────────────►
      │                                               │
      │  3. Discover Services                         │
      │  ─────────────────────────────────────────────►
      │                                               │
      │  4. Discover Characteristics                  │
      │  ─────────────────────────────────────────────►
      │                                               │
      │  5. Enable Notifications on DATA_TRANSFER     │
      │  ─────────────────────────────────────────────►
      │                                               │
      │  6. Ready for LEAF Protocol                   │
      │                                               │
```

### GATT Communication Pattern

All LEAF protocol messages use a single characteristic:

| Direction | Method | Description |
|-----------|--------|-------------|
| Device → Reader | Write (with response) | Send protocol messages |
| Reader → Device | Notification | Receive protocol responses |

---

## Transaction State Machine

The LEAF protocol implements a 5-state mutual authentication flow defined in `LeafCentral.h`:

### State Definitions

```c
typedef enum _leaf_central_status_t {
    central_challenge = 0,     // Initial state: send device UID + challenge
    central_authenticated,     // Reader response received and validated
    central_mutual_auth,       // Send response to reader's challenge
    central_transfer,          // Send credential payload
    central_done,              // Transaction complete
} leaf_central_status_t;
```

### State Transition Diagram

```
                              ┌──────────────────┐
                              │  BLE Connected   │
                              └────────┬─────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────┐
                    │    State 0: central_challenge    │
                    │  ─────────────────────────────── │
                    │  Action: Generate random nonce   │
                    │  Send: DUID + AUTH_REQ message   │
                    └────────────────┬─────────────────┘
                                     │
                              Receive AUTH_RSP + AUTH_REQ
                                     │
                                     ▼
                    ┌──────────────────────────────────┐
                    │ State 1: central_authenticated   │
                    │  ─────────────────────────────── │
                    │  Action: Validate reader's       │
                    │          response to our nonce   │
                    │  If valid: Reader is authentic   │
                    └────────────────┬─────────────────┘
                                     │
                              Validation passed
                                     │
                                     ▼
                    ┌──────────────────────────────────┐
                    │   State 2: central_mutual_auth   │
                    │  ─────────────────────────────── │
                    │  Action: Compute response to     │
                    │          reader's challenge      │
                    │  Send: AUTH_RSP message          │
                    └────────────────┬─────────────────┘
                                     │
                              AUTH_RSP sent
                                     │
                                     ▼
                    ┌──────────────────────────────────┐
                    │    State 3: central_transfer     │
                    │  ─────────────────────────────── │
                    │  Action: Prepare credential      │
                    │  Send: CP (Credential Payload)   │
                    │         372 bytes, encrypted     │
                    └────────────────┬─────────────────┘
                                     │
                              Receive TC
                                     │
                                     ▼
                    ┌──────────────────────────────────┐
                    │      State 4: central_done       │
                    │  ─────────────────────────────── │
                    │  Action: Extract TC, verify      │
                    │  Result: Transaction complete    │
                    │  Door access decision made       │
                    └──────────────────────────────────┘
```

### iOS SDK State Interface

```swift
public struct WlTransaction {
    /// Initialize transaction with credential data
    /// - credential: Tuple of (payload: [UInt8], key: [UInt8], uid: [UInt8])
    /// - reset: Whether to reset the IV
    public static func start(credential: WlMobileCredential, reset: Bool)

    /// Get the next packet to send to the reader
    /// Returns: (status: WlStatus, packet: [UInt8])
    public static func getNextPacket() -> (status: WlStatus, packet: [UInt8])

    /// Process incoming packet from reader
    /// Returns: WlStatus indicating current state
    public static func handlePacket(_ packet: [UInt8]) -> WlStatus

    /// Get transaction certificate after completion
    public static func getTransactionCertificate() -> [UInt8]

    /// Get keyset metadata
    public static func getMetadata() -> [UInt8]
}
```

### Status Codes

```swift
public enum WlStatus : UInt32 {
    case ok           // Normal operation, continue transaction
    case failed       // Authentication or decryption failed
    case authenticated // Mutual authentication complete
    case complete     // Transaction finished, TC available
    case unknown      // Unknown/error state
}
```

---

## Message Format Specification

### BLE Message Structure

Every LEAF BLE message follows this format defined in `LeafCore.h`:

```c
typedef struct _leaf_ble_msg_t {
    unsigned char  start;           // 1 byte: 0x81 (plain) or 0xC1 (cipher)
    leaf_tag_t     tag;             // 1 byte: Message type (0-7)
    unsigned short length;          // 2 bytes: Big-endian payload length
    unsigned char  sequence;        // 1 byte: Rotating sequence counter
    unsigned char  value[400];      // Variable: Message payload (max 400 bytes)
} leaf_ble_msg_t;
```

### Byte-Level Layout

```
┌─────────┬─────────┬─────────┬─────────┬─────────┬───────────────────┐
│  Byte 0 │  Byte 1 │  Byte 2 │  Byte 3 │  Byte 4 │  Bytes 5..N       │
├─────────┼─────────┼─────────┼─────────┼─────────┼───────────────────┤
│  Start  │   Tag   │ Len Hi  │ Len Lo  │   Seq   │  Value (payload)  │
│ 0x81/C1 │  0x00-7 │         │         │  0-255  │  max 400 bytes    │
└─────────┴─────────┴─────────┴─────────┴─────────┴───────────────────┘
         │                                        │
         └────────── Overhead: 5 bytes ───────────┘
```

### Message Tags

```c
typedef enum _leaf_tag_t {
    leaf_tag_rsp = 0,       // Generic response (success/failure)
    leaf_tag_duid = 1,      // Device UID (8 bytes)
    leaf_tag_authreq = 2,   // Authentication request (16-byte challenge)
    leaf_tag_authrsp = 3,   // Authentication response (16-byte response)
    leaf_tag_cp = 4,        // Credential Payload (372 bytes)
    leaf_tag_tc = 5,        // Transaction Certificate (98 bytes)
    leaf_tag_meta = 6,      // Keyset metadata (4 bytes)
    leaf_tag_ivreset = 7    // Reset initialization vector
} leaf_tag_t;
```

### Start Byte Encoding

| Start Byte | Meaning | Description |
|------------|---------|-------------|
| `0x81` | Plaintext | Message payload is not encrypted |
| `0xC1` | Ciphertext | Message payload is AES-128 CBC encrypted |

### Constants

```c
#define LEAF_BLE_MSG_OVERHEAD   0x04    // 4 bytes (start + tag + length)
#define LEAF_BLE_MSG_PLAINTEXT  0x81    // Plaintext message indicator
#define LEAF_BLE_MSG_CIPHER     0xC1    // Encrypted message indicator
#define LEAF_MAX_BLE_MSG_VAL    400     // Maximum payload size
```

---

## Authentication Protocol

### Mutual Authentication Overview

The LEAF protocol implements **mutual authentication** where both the device and reader prove their identity to each other using AES-128 challenge-response:

1. **Device authenticates Reader**: Device sends challenge, validates reader's response
2. **Reader authenticates Device**: Reader sends challenge, validates device's response

**Important:** The key used in authentication (K) is the **diversified key** unique to each device, NOT the master key. See [Key Diversification](#key-diversification) below for details on how K is derived.

### Challenge-Response Mechanism

```
Device                                              Reader
   │                                                   │
   │  Generate random nonce (Ra)                       │
   │                                                   │
   │  ─────────── DUID + AUTH_REQ(Ra) ─────────────►  │
   │                                                   │
   │                            Compute: Rb' = AES(K, Ra)
   │                            Generate: Rb (reader nonce)
   │                            [K = diversified key for this device]
   │                                                   │
   │  ◄──────── AUTH_RSP(Rb') + AUTH_REQ(Rb) ────────  │
   │                                                   │
   │  Verify: Rb' == expected                          │
   │  (proves reader has diversified key K)            │
   │                                                   │
   │  Compute: Ra' = AES(K, Rb)                        │
   │  [K = diversified key stored on device]           │
   │                                                   │
   │  ─────────────── AUTH_RSP(Ra') ─────────────────► │
   │                                                   │
   │                            Verify: Ra' == expected
   │                            (proves device has diversified key K)
   │                                                   │
   │          ◄─── MUTUAL AUTHENTICATION COMPLETE ───► │
```

### Key Diversification

The LEAF protocol uses a two-tier key hierarchy to protect the master key:

**Key Hierarchy:**
```
Master Key (pBaseKey)
     │
     │ Stored at: Server/Provisioning System ONLY
     │ Never sent to mobile devices
     │
     ├─→ Leaf_DiversifyKey(masterKey, Device_A_UID) → Diversified Key A
     ├─→ Leaf_DiversifyKey(masterKey, Device_B_UID) → Diversified Key B
     └─→ Leaf_DiversifyKey(masterKey, Device_C_UID) → Diversified Key C
              │
              │ Stored on: Mobile Device
              │ Used for: Authentication (the "K" in AES(K, nonce))
              └─→ This is the key used in the authentication protocol
```

**Diversification Function:**
```c
void Leaf_DiversifyKey(
    unsigned char *pDiversifiedKey,   // Output: 16-byte unique device key (K)
    unsigned char *pUid,              // Input: 8-byte device UID
    unsigned char *pBaseKey           // Input: 16-byte master key
);
```

**Diversification Algorithm Constants:**
```c
#define LEAF_SUBKEY_XOR_VAL    0x87    // XOR constant for subkey generation
#define LEAF_DIVINPUT_CONST    0x01    // Diversification input constant
```

**Security Benefits:**
- **Master key** remains secure: Never stored on mobile devices, only at provisioning server
- **Diversified key (K)** is device-specific: Compromise of one device doesn't expose master key or other devices' keys
- Each device has cryptographically unique credentials derived from its UID

**Note on Reader Architecture:**
The SDK documentation does not specify how readers obtain or store keys. Possible architectures:
1. **Readers store diversified keys**: Each reader provisioned with keys for authorized devices
2. **Readers have master key**: Derive keys on-demand using device UID
3. **Hybrid approach**: Some combination of the above

This is a critical security consideration, as reader compromise could expose stored keys (architecture 1) or the master key (architecture 2). Consult with Wavelynx or your access control system vendor for specifics on reader key management.

### Random Challenge Generation

```c
// Generate 16-byte random challenge
void Leaf_GenerateRand(unsigned char *pRandToken);

// Generate derived random (Rand')
void Leaf_GenerateRandPrime(
    unsigned char *pRandPrimeToken,  // Output
    unsigned char *pRandToken        // Input random
);

// Verify Rand' matches expected
bool_t Leaf_VerifyRandPrime(
    unsigned char *randPrime1,
    unsigned char *randPrime2
);
```

---

## Credential Transfer

### Credential Payload (CP) Structure

After mutual authentication, the device sends its credential payload:

```c
typedef struct _leaf_cred_payload_t {
    // Tag header: 0xCC when serialized
    unsigned short    length;                    // 2 bytes
    leaf_payload_id_t identifier;                // 2 bytes
    unsigned char     dUid[8];                   // 8 bytes - Device UID
    unsigned char     token[32];                 // 32 bytes - Server token
    unsigned char     value[330];                // 330 bytes - Encrypted badge data
} leaf_cred_payload_t;
```

**Total Size: 372 bytes** (330 value + 42 overhead)

### Payload Identifiers

```c
typedef enum _leaf_payload_id_t {
    leaf_id_keyset = 0,        // Keyset/key material for key rotation
    leaf_id_accesscontrol,     // Access control data (badge ID, facility code)
    leaf_id_configfile,        // Configuration data
    leaf_id_passthrough,       // Pass-through/custom data
} leaf_payload_id_t;
```

### CP Wire Format

```
┌──────────┬────────────┬────────────┬───────────┬────────────┬──────────────────┐
│  Byte 0  │  Bytes 1-2 │  Bytes 3-4 │ Bytes 5-12│ Bytes 13-44│  Bytes 45-374    │
├──────────┼────────────┼────────────┼───────────┼────────────┼──────────────────┤
│ Tag 0xCC │   Length   │ Identifier │  dUid[8]  │  token[32] │   value[330]     │
└──────────┴────────────┴────────────┴───────────┴────────────┴──────────────────┘
                                                               │
                                       Encrypted with KCD key ─┘
```

### Transaction Certificate (TC) Structure

The reader returns a TC upon successful credential validation:

```c
typedef struct _leaf_transaction_cert_t {
    // Tag header: 0xCE when serialized
    unsigned short    length;          // 2 bytes
    leaf_payload_id_t identifier;      // 2 bytes - echoed from CP
    unsigned char     rUid[8];         // 8 bytes - Reader UID
    unsigned char     dUid[8];         // 8 bytes - Device UID from CP
    unsigned char     token[32];       // 32 bytes - Server token from CP
    unsigned char     rfu[48];         // 48 bytes - Reserved for future use
} leaf_transaction_cert_t;
```

**Total Size: 98 bytes**

### TC Wire Format

```
┌──────────┬────────────┬────────────┬───────────┬───────────┬────────────┬──────────┐
│  Byte 0  │  Bytes 1-2 │  Bytes 3-4 │ Bytes 5-12│Bytes 13-20│ Bytes 21-52│Bytes 53+ │
├──────────┼────────────┼────────────┼───────────┼───────────┼────────────┼──────────┤
│ Tag 0xCE │   Length   │ Identifier │  rUid[8]  │  dUid[8]  │  token[32] │ rfu[48]  │
└──────────┴────────────┴────────────┴───────────┴───────────┴────────────┴──────────┘
```

### TC Verification

The mobile app should verify:
1. `identifier` matches the CP that was sent
2. `dUid` matches the device's UID
3. `token` matches the server token from the CP

---

## Encryption & Decryption

### AES-128 CBC Implementation

The SDK uses standard AES-128 in CBC (Cipher Block Chaining) mode:

```c
// Encrypt data in-place
short AesEncryptCbc(
    unsigned char *data,       // Data buffer (modified in-place)
    unsigned short length,     // Must be multiple of 16
    unsigned char key[16],     // 128-bit AES key
    unsigned char iv[16]       // 128-bit initialization vector
);

// Decrypt data in-place
short AesDecryptCbc(
    unsigned char *data,       // Data buffer (modified in-place)
    unsigned short length,     // Must be multiple of 16
    unsigned char key[16],     // 128-bit AES key
    unsigned char iv[16]       // 128-bit initialization vector
);
```

### Block Size and Padding

```c
#define LEAF_BLOCK_SIZE       0x10    // 16 bytes (AES block size)
#define LEAF_PADDING_START    0x80    // ISO 10126 padding start marker
```

**Padding Scheme:**
The SDK uses ISO 10126 style padding:
1. Append `0x80` byte
2. Append `0x00` bytes until length is multiple of 16

```
Original:    [Data bytes...] (variable length)
Padded:      [Data bytes...][0x80][0x00][0x00]...[0x00] (16-byte aligned)
```

### Encryption Keys

| Key | Purpose | Derivation |
|-----|---------|------------|
| **KMD** (Key Material Data) | Encrypts BLE messages during authentication | Same as diversified key K = Leaf_DiversifyKey(masterKey, deviceUID) |
| **KCD** (Key for Credential Data) | Encrypts CP value field (330 bytes) | Provided by server, separate from KMD |

**Note:** KMD is simply another name for the diversified key (K) used throughout the authentication protocol. Both the mobile device and reader have this key.

### Message Serialization

```c
// Serialize and encrypt a BLE message
short Leaf_SerializeBleMessage(
    unsigned char *msg,           // Output buffer
    unsigned short *msgLen,       // Output length
    leaf_tag_t tag,               // Message tag
    unsigned char *val,           // Message value
    unsigned short valLen,        // Value length
    unsigned char seq,            // Sequence number
    unsigned char *kmd,           // Key Material Data (NULL for plaintext)
    leaf_aescbc aesEnc            // AES encrypt function pointer
);

// Deserialize and decrypt a BLE message
leaf_tag_t Leaf_DeserializeBleMessage(
    unsigned char *msg,           // Input buffer
    unsigned short msgLen,        // Input length
    unsigned char *val,           // Output value
    unsigned short *valLen,       // Output length
    unsigned char *seq,           // Sequence number
    unsigned char *kmd,           // Key Material Data
    leaf_aescbc aesDec            // AES decrypt function pointer
);
```

### Encryption Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Message Encryption                             │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   1. Create message structure                                        │
│      ┌─────┬─────┬────────┬─────┬──────────────────┐                │
│      │Start│ Tag │ Length │ Seq │     Value        │                │
│      │0x81 │     │        │     │                  │                │
│      └─────┴─────┴────────┴─────┴──────────────────┘                │
│                                                                      │
│   2. If encrypted (KMD provided):                                    │
│      - Change start byte to 0xC1                                     │
│      - Pad value to 16-byte boundary                                 │
│      - Encrypt value with AES-128 CBC using KMD                      │
│      ┌─────┬─────┬────────┬─────┬──────────────────┐                │
│      │0xC1 │ Tag │ Length │ Seq │ Encrypted Value  │                │
│      └─────┴─────┴────────┴─────┴──────────────────┘                │
│                                                                      │
│   3. Transmit over BLE                                               │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### IV (Initialization Vector) Handling

```c
// Default IV (all zeros typically)
extern unsigned char Leaf_defaultIv[LEAF_BLOCK_SIZE];

// IV reset message tag
leaf_tag_ivreset = 7
```

The IV can be reset during a transaction using the `leaf_tag_ivreset` message. This is useful for:
- Starting a fresh encryption context
- Recovering from desynchronization

---

## Multi-Packet Messaging

### Overview

Large messages (like the 372-byte CP) may exceed the BLE MTU and require fragmentation:

### Response Codes for Multi-Packet

```c
typedef enum _leaf_rsp_t {
    leaf_rsp_success = 0,       // Single message / final fragment
    leaf_rsp_fail = 1,          // Failure
    leaf_rsp_authrequired = 2,  // Authentication required
    leaf_rsp_invalid = 3,       // Invalid request
    leaf_rsp_multistart = 4,    // First fragment of multi-message
    leaf_rsp_multiend = 5       // Last fragment of multi-message
} leaf_rsp_t;
```

### Multi-Packet Functions

```c
// Append received fragment to message buffer
short Leaf_AppendMsg(
    unsigned char *pMsg,          // Accumulated message buffer
    unsigned short *pMsgLen,      // Current accumulated length
    unsigned char *pNewMsg,       // New fragment
    unsigned short newMsgLen      // Fragment length
);

// Process accumulated message and get next complete message
short Leaf_ProcessNextMsg(
    unsigned char *pMsg,          // Buffer with accumulated data
    unsigned short *pMsgLen,      // Remaining length (updated)
    unsigned char *pNextMsg,      // Output: next complete message
    unsigned short *pNextMsgLen   // Output: message length
);
```

### Multi-Packet Flow

```
Device                                              Reader
   │                                                   │
   │  ────────────── CP Fragment 1 ─────────────────► │
   │  (multistart)                                     │
   │                                                   │
   │  ◄─────────────── ACK ────────────────────────── │
   │                                                   │
   │  ────────────── CP Fragment 2 ─────────────────► │
   │  (continuation)                                   │
   │                                                   │
   │  ◄─────────────── ACK ────────────────────────── │
   │                                                   │
   │  ────────────── CP Fragment N ─────────────────► │
   │  (multiend)                                       │
   │                                                   │
   │  ◄─────────────── TC ─────────────────────────── │
   │                                                   │
```

### Sequence Number

The `sequence` field (1 byte) is a rotating counter that:
- Starts at 0 for each transaction
- Increments with each message sent
- Wraps around at 255
- Used to detect duplicate or out-of-order packets

---

## Error Handling

### Response Codes

```c
typedef enum _leaf_rsp_t {
    leaf_rsp_success = 0,       // Operation successful
    leaf_rsp_fail = 1,          // Operation failed (wrong keys, invalid data)
    leaf_rsp_authrequired = 2,  // Authentication required before this operation
    leaf_rsp_invalid = 3,       // Invalid or malformed request
    leaf_rsp_multistart = 4,    // Multi-message transmission started
    leaf_rsp_multiend = 5       // Multi-message transmission ended
} leaf_rsp_t;
```

### NFC APDU Status Words (for NFC variant)

```c
typedef enum _leaf_sw1_t {
    leaf_sw1_not_allowed = 0x69,   // Command not allowed / unknown
    leaf_sw1_fail = 0x6F,          // Known command but execution failed
    leaf_sw1_success = 0x90        // Command executed successfully
} leaf_sw1_t;
```

### SDK Status Codes

```swift
public enum WlStatus : UInt32 {
    case ok           // Operation in progress, continue
    case failed       // Authentication or decryption failed
    case authenticated // Mutual authentication succeeded
    case complete     // Transaction complete
    case unknown      // Unknown or error state
}
```

### Failure Scenarios

| Scenario | Detection | Recovery |
|----------|-----------|----------|
| Wrong encryption key | `leaf_rsp_fail` | Try backup keyset |
| Authentication timeout | BLE disconnect | Reconnect and restart |
| Invalid CP format | `leaf_rsp_invalid` | Check CP structure |
| Reader desync | Unexpected response | Reset IV and retry |
| BLE MTU exceeded | Fragmentation required | Use multi-packet |

### Fallback Mechanism

The SDK implements automatic fallback for key rotation scenarios:

```swift
// Pseudocode for fallback
func performTransaction() {
    // First attempt with ACCESS payload
    let status = WlTransaction.start(credential: accessCredential, reset: true)

    if status == .failed {
        // Fallback to KEYSET payload (backup keys)
        let status2 = WlTransaction.start(credential: keysetCredential, reset: true)
        // Continue with keyset...
    }
}
```

---

## Implementation Requirements

### iOS Requirements

| Requirement | Value |
|-------------|-------|
| Minimum iOS Version | 12.0+ |
| Framework | CoreBluetooth |
| Background Modes | `bluetooth-central` |
| Privacy Keys | `NSBluetoothAlwaysUsageDescription` |

### BLE Requirements

| Parameter | Requirement |
|-----------|-------------|
| MTU | Negotiate maximum supported |
| Connection Interval | 7.5ms - 30ms recommended |
| Slave Latency | 0-4 |
| Supervision Timeout | 2-6 seconds |

### Timing Constraints

| Operation | Typical Duration |
|-----------|------------------|
| BLE Connection | 100-500ms |
| Service Discovery | 50-200ms |
| Full Transaction | 200-800ms |
| Message Round-Trip | 20-100ms |

### Memory Requirements

| Buffer | Size |
|--------|------|
| Message buffer | 405 bytes (400 + 5 overhead) |
| CP buffer | 372 bytes |
| TC buffer | 98 bytes |
| Key storage | 16 bytes per key |

### Security Requirements

1. **Key Storage**: Store KMD in secure enclave or keychain
2. **Random Generation**: Use cryptographically secure RNG
3. **Memory Handling**: Zero sensitive buffers after use
4. **Transport**: All messages after initial handshake must be encrypted

---

## Debugging Guide

### Message Inspection

When debugging, examine messages at the byte level:

```
Example encrypted message (DUID + AUTH_REQ):
┌────┬────┬────┬────┬────┬────────────────────────────────┐
│ C1 │ 01 │ 00 │ 18 │ 00 │ [24 bytes encrypted payload]   │
├────┼────┼────┼────┼────┼────────────────────────────────┤
│Enc │DUID│ Len=24    │Seq │ AES-encrypted device UID     │
│    │Tag │           │=0  │ + random challenge           │
└────┴────┴────┴────┴────┴────────────────────────────────┘

Decrypted payload:
├────────────────────────────────────────────────────────┤
│ [8 bytes Device UID] [16 bytes Random Challenge]       │
└────────────────────────────────────────────────────────┘
```

### Common Issues

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| `leaf_rsp_fail` on AUTH_RSP | Wrong diversified key | Verify device UID and master key |
| Garbage decrypted data | IV mismatch | Send `leaf_tag_ivreset` |
| TC never received | CP validation failed | Check badge data format |
| Connection drops | Timeout | Reduce transaction time |
| Partial message | MTU exceeded | Implement multi-packet |

### Logging Points

Key points to log during development:

1. **Connection**: Reader UUID, RSSI, connection time
2. **State Transitions**: Each state change with timestamp
3. **Messages Sent**: Tag, length, sequence, hex dump (encrypted)
4. **Messages Received**: Tag, length, sequence, hex dump
5. **Decrypted Content**: Challenge/response values (in debug only)
6. **Status Changes**: WlStatus changes
7. **Errors**: Response codes, BLE errors

### Hex Dump Utility

```swift
// Useful for debugging
func hexDump(_ data: [UInt8], prefix: String = "") -> String {
    return prefix + data.map { String(format: "%02X", $0) }.joined(separator: " ")
}

// Usage
print(hexDump(packet, prefix: "TX: "))  // TX: C1 01 00 18 00 ...
print(hexDump(response, prefix: "RX: ")) // RX: C1 03 00 20 01 ...
```

---

## Complete Transaction Example

### Full Message Exchange

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Complete BLE Transaction                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [BLE Connect]                                                              │
│                                                                             │
│  Device ──────────────────────────────────────────────────────────► Reader  │
│  State: central_challenge                                                   │
│  Message: 0xC1 | tag_duid=1 | len | seq=0 | encrypted(dUID + Ra)           │
│                                                                             │
│  Device ◄────────────────────────────────────────────────────────── Reader  │
│  State: central_authenticated                                               │
│  Message: 0xC1 | tag_authrsp=3 | len | seq | encrypted(Ra' + Rb)           │
│  Action: Verify Ra' = AES(K, Ra), extract Rb                               │
│                                                                             │
│  Device ──────────────────────────────────────────────────────────► Reader  │
│  State: central_mutual_auth                                                 │
│  Message: 0xC1 | tag_authrsp=3 | len | seq=1 | encrypted(Rb')              │
│  Note: Rb' = AES(K, Rb) proves device has correct key                      │
│                                                                             │
│  Device ──────────────────────────────────────────────────────────► Reader  │
│  State: central_transfer                                                    │
│  Message: 0xC1 | tag_cp=4 | len=372 | seq=2 | encrypted(CP)                │
│  Note: May be fragmented across multiple BLE writes                        │
│                                                                             │
│  Device ◄────────────────────────────────────────────────────────── Reader  │
│  State: central_done                                                        │
│  Message: 0xC1 | tag_tc=5 | len=98 | seq | encrypted(TC)                   │
│  Action: Extract TC, verify dUID and token match                           │
│                                                                             │
│  [Transaction Complete - Door Access Decision Made]                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

Legend:
  Ra  = Random challenge generated by device
  Rb  = Random challenge generated by reader
  Ra' = Reader's response to device challenge (proves reader identity)
  Rb' = Device's response to reader challenge (proves device identity)
  K   = Diversified key (unique to this device, derived from master key + UID)
        Note: K is NOT the master key - it's device-specific
  CP  = Credential Payload (372 bytes, contains badge data)
  TC  = Transaction Certificate (98 bytes, proof of transaction)
```

---

## References

### SDK Files

| File | Purpose |
|------|---------|
| [LeafCore.h](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Headers/LeafCore.h) | Core data structures and protocol definitions |
| [LeafCentral.h](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Headers/LeafCentral.h) | State machine for central (device) role |
| [Aes.h](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Headers/Aes.h) | AES-128 CBC implementation |
| [Random.h](../ios-sdk/LeafBle.xcframework/ios-arm64/LeafBle.framework/Headers/Random.h) | Cryptographic random generation |

### Related Documentation

- [WaveLynx BLE Security Model](./WAVELYNX_BLE_SECURITY_MODEL.md) - Security architecture and credential structure
- [iOS SDK README](../ios-sdk/README.md) - Framework integration guide
- [iOS SDK API Docs](../ios-sdk/docs/index.html) - Full API reference

### Standards

- NXP AN10922 - Symmetric Key Diversification
- ISO 7816-4 - APDU Command Format
- MIFARE DESFire EV2/EV3 Specification
- Bluetooth Core Specification 5.0+

---

*Document generated from analysis of WaveLynx LEAF iOS SDK v4.0.0*
