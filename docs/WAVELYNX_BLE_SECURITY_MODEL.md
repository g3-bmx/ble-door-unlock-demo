# Wavelynx BLE Credential Security Model

Technical documentation for the Wavelynx LEAF BLE SDK security architecture, credential structure, and server integration.

---

## Table of Contents

1. [Overview](#overview)
2. [Credential Structure](#credential-structure)
3. [Key Diversification](#key-diversification)
4. [BLE Authentication Protocol](#ble-authentication-protocol)
5. [Server API Integration](#server-api-integration)
6. [Encryption & Cryptography](#encryption--cryptography)
7. [Key Management (3 Keys Per Application)](#key-management-3-keys-per-application)
8. [Credential Expiration](#credential-expiration)
9. [Custom Server Implementation](#custom-server-implementation)
10. [Key Files Reference](#key-files-reference)
11. [Constants Reference](#constants-reference)

---

## Overview

### What is LEAF?

LEAF (not an acronym) is an open credential standard created by the LEAF Community, led by Wavelynx Technologies. It provides:

- **Interoperability** - Any LEAF credential works with any LEAF-certified reader
- **Security** - Built on NXP MIFARE DESFire EV2/EV3 with AES-128 encryption
- **Flexibility** - Supports physical cards, mobile credentials (BLE/NFC), and wallet integrations

### SDK Components

| Component | Description |
|-----------|-------------|
| `leafble-4.0.0.aar` | Android SDK library |
| `LeafBle.xcframework` | iOS SDK framework |
| `libleaflib.so` | Native library for low-level crypto operations |

### What Enables Door Access?

A Wavelynx credential contains a **bitstream** (typically 26-bit, 32-bit, or custom format) that includes:
- **Badge ID** - Unique identifier for the credential holder
- **Facility Code** - Optional, identifies the organization/site
- **Parity bits** - For error detection

The reader:
1. Authenticates the credential using AES-128 mutual authentication
2. Extracts the bitstream from the decrypted payload
3. Sends the bitstream to the access control panel via Wiegand or OSDP
4. The panel decides whether to grant access based on its database

---

## Credential Structure

### Credential Payload (CP) - 372 bytes

Defined in `LeafCore.h`:

```c
typedef struct _leaf_cred_payload_t {
    // Tag header: 0xCC when serialized
    unsigned short    length;                    // 2 bytes - payload length
    leaf_payload_id_t identifier;                // 2 bytes - content type
    unsigned char     dUid[8];                   // 8 bytes - Device UID
    unsigned char     token[32];                 // 32 bytes - Server-defined token
    unsigned char     value[330];                // 330 bytes - Payload contents (badge data)
} leaf_cred_payload_t;
```

| Field | Size | Description |
|-------|------|-------------|
| Tag Header | 1 byte | `0xCC` identifies this as a CP |
| Length | 2 bytes | Big-endian payload length |
| Identifier | 2 bytes | Payload type (keyset, accesscontrol, configfile, passthrough) |
| Device UID | 8 bytes | Unique identifier for this credential/device |
| Token | 32 bytes | Server-generated token for verification |
| Value | 330 bytes | Encrypted credential data (badge ID, facility code, etc.) |

**Total: 372 bytes** (330 value + 42 overhead)

### Transaction Certificate (TC) - 98 bytes

Returned by the reader after successful authentication:

```c
typedef struct _leaf_transaction_cert_t {
    // Tag header: 0xCE when serialized
    unsigned short    length;                    // 2 bytes
    leaf_payload_id_t identifier;                // 2 bytes - ID from CP
    unsigned char     rUid[8];                   // 8 bytes - Reader UID
    unsigned char     dUid[8];                   // 8 bytes - Device UID from CP
    unsigned char     token[32];                 // 32 bytes - Server token from CP
    unsigned char     rfu[48];                   // 48 bytes - Reserved for future use
} leaf_transaction_cert_t;
```

### Payload Identifiers

```c
typedef enum _leaf_payload_id_t {
    leaf_id_keyset = 0,        // Keyset/key material
    leaf_id_accesscontrol,     // Access control data (badge ID, etc.)
    leaf_id_configfile,        // Configuration data
    leaf_id_passthrough,       // Pass-through data
} leaf_payload_id_t;
```

### Android Credential Storage

The Android app stores credentials with these components:

| Field | Key | Description |
|-------|-----|-------------|
| Device ID | `deviceId` | 8-byte unique device identifier |
| Access KMD | `accessKmd` | Key Material Data for primary access |
| Access CP | `accessCp` | Credential Payload for primary access |
| Keyset KMD | `keysetKmd` | Key Material Data for backup keyset |
| Keyset CP | `keysetCp` | Credential Payload for backup keyset |
| Metadata | `metadata` | 4-byte keyset metadata |
| Card Display | `cardDisplay` | Human-readable credential name |

---

## Key Diversification

### What is Key Diversification?

Key diversification is a cryptographic technique where a **single master key** is used to derive **unique keys for each device/credential**.

### Algorithm

```c
void Leaf_DiversifyKey(unsigned char *pDiversifiedKey,   // Output: unique 16-byte key
                       unsigned char *pUid,              // Input: 8-byte device UID
                       unsigned char *pBaseKey);         // Input: 16-byte master key
```

### How It Works

```
Master Key (Base Key): AAAA...AAAA (16 bytes)
Device UID:            1234567890ABCDEF (8 bytes)
                       ↓
            Diversification Algorithm
            (XOR constant: 0x87)
            (Input constant: 0x01)
                       ↓
Diversified Key:       XXXX...XXXX (16 bytes) ← unique to this device
```

### Why Key Diversification Matters

1. **Compromise isolation** - If one device is compromised, only that device's key is exposed
2. **Master key protection** - The master key is never transmitted or stored on devices
3. **Scalability** - Millions of unique keys from one master key
4. **Standard compliance** - Follows NXP AN10922 (Symmetric Key Diversification)

---

## BLE Authentication Protocol

### State Machine

Defined in `LeafCentral.h`:

```c
typedef enum _leaf_central_status_t {
    central_challenge = 0,   // Connected, send dUID + AUTH_REQ
    central_authenticated,   // AUTH_RSP + AUTH_REQ received and validated
    central_mutual_auth,     // Send AUTH_RSP
    central_transfer,        // Send CP (Credential Payload)
    central_done,            // TC (Transaction Certificate) received
} leaf_central_status_t;
```

### Authentication Flow

```
┌──────────────┐                              ┌──────────────┐
│    Device    │                              │    Reader    │
│   (Central)  │                              │ (Peripheral) │
└──────┬───────┘                              └──────┬───────┘
       │                                             │
       │  1. Connect (BLE)                           │
       │────────────────────────────────────────────>│
       │                                             │
       │  2. Send dUID + AUTH_REQ (random challenge) │
       │────────────────────────────────────────────>│
       │                                             │
       │  3. AUTH_RSP + AUTH_REQ (reader challenge)  │
       │<────────────────────────────────────────────│
       │                                             │
       │  4. Validate reader response                │
       │  5. Send AUTH_RSP                           │
       │────────────────────────────────────────────>│
       │                                             │
       │  6. Send CP (Credential Payload)            │
       │────────────────────────────────────────────>│
       │                                             │
       │  7. TC (Transaction Certificate)            │
       │<────────────────────────────────────────────│
       │                                             │
       │  8. Door release (if authorized)            │
       │                                             │
```

### Message Tags

```c
typedef enum _leaf_tag_t {
    leaf_tag_rsp = 0,    // Generic response
    leaf_tag_duid,       // Device UID
    leaf_tag_authreq,    // Authorization request (challenge)
    leaf_tag_authrsp,    // Authorization response
    leaf_tag_cp,         // Credential payload
    leaf_tag_tc,         // Transaction certificate
    leaf_tag_meta,       // Keyset metadata
    leaf_tag_ivreset     // Reset the IV
} leaf_tag_t;
```

### BLE Message Structure

```c
typedef struct _leaf_ble_msg_t {
    unsigned char  start;      // 0x81 (plaintext) or 0xC1 (cipher)
    leaf_tag_t     tag;        // Message type
    unsigned short length;     // Big-endian length
    unsigned char  sequence;   // Rotating sequence number
    unsigned char  value[400]; // Message payload
} leaf_ble_msg_t;
```

### Fallback Mechanism

The Android app implements a fallback strategy:

1. First attempt authentication with **ACCESS** payload
2. If `WlStatus.FAILED`, try **KEYSET** payload (backup)
3. This handles key rotation scenarios where reader has newer keys

---

## Server API Integration

### Wavelynx Server (nyx.wavelynxtech.com)

#### Registration Endpoint

```
POST /device/register
Content-Type: application/json

Request:
{
  "pubKey": "<Base64 EC P-256 public key>",
  "hash": "<Base64 SHA-256 hash of public key>"
}

Response:
{
  "serverPubKey": "<Base64 server EC public key>",
  "serverPubKeyHash": "<Base64 hash for verification>",
  "name": "<Credential name for future requests>"
}
```

**Purpose:**
- Device onboarding and identity establishment
- ECDH key exchange for secure communication
- Server stores device public key for future authentication

#### Refresh Endpoint

```
POST /device/refresh
Content-Type: application/json

Request:
{
  "hash": "<Device public key SHA-256 hash>",
  "name": "<Credential name from registration>"
}

Response:
{
  "deviceId": "<Hex device ID>",
  "payloads": {
    "access": {
      "kmd": "<Hex Access KMD>",
      "cp": "<Hex Access CP>",
      "meta": ["value:<Hex metadata>"]
    },
    "keyset": {
      "kmd": "<Hex Keyset KMD>",
      "cp": "<Hex Keyset CP>",
      "meta": ["value:<Hex metadata>"]
    }
  }
}
```

**Purpose:**
- Retrieve/update credential payloads
- Key rotation (get new keys when rotation occurs)
- Credential updates (access permissions changed)
- Keyset synchronization

### External/Custom Server

The SDK supports a simpler external server API with both registration and refresh:

#### Registration Endpoint

```
GET /device/register

Response:
{
  "uid": "<Hex device ID>"
}
```

**Purpose:**
- Assigns a unique device UID
- Simpler than Wavelynx (no EC key exchange required)
- UID is used for subsequent refresh requests

#### Refresh/Credential Endpoint

```
GET /device/credential?uid={deviceIdHex}&format=W36-9

Response:
{
  "kmp": "<Hex Access KMD>",
  "cp": "<Hex Access CP>",
  "badgeid": "<Display name>"
}
```

**Purpose:**
- Retrieves credential payloads for the registered device
- Returns ACCESS payload only (no keyset backup)
- `format` parameter specifies bitstream format (e.g., W36-9)

#### Wavelynx vs External Server Comparison

| Feature | Wavelynx Server | External Server |
|---------|-----------------|-----------------|
| HTTP Method | POST | GET |
| Registration | EC public key exchange | Simple UID assignment |
| Authentication | Hash-based (public key hash) | UID-based (simpler) |
| Refresh returns | Access + Keyset payloads | Access only (no keyset) |
| Security model | ECDH key agreement | Relies on network security |
| Use case | Production | Development/Testing/Custom |

**Note:** The external server (hardcoded to `192.168.86.46:8080`) appears designed for development/testing or custom integrations where partners manage their own credential issuance.

---

## Encryption & Cryptography

### Algorithms Used

| Purpose | Algorithm | Key Size |
|---------|-----------|----------|
| Message encryption | AES-128 CBC | 128-bit (16 bytes) |
| Credential encryption | AES-128 CBC | 128-bit |
| Key diversification | AES-based | 128-bit |
| Device identity | ECDH P-256 | 256-bit |
| Hash-based auth | SHA-256 | 256-bit |

### AES-128 CBC

```c
// Function prototype from SDK
typedef short (*Leaf_AesCbc)(unsigned char *data,    // Data to encrypt/decrypt
                             unsigned short length,   // Data length
                             unsigned char *key,      // 16-byte key
                             unsigned char *iv);      // 16-byte IV

// Default IV
extern unsigned char Leaf_defaultIv[LEAF_BLOCK_SIZE];  // 16 bytes
```

### Message Encryption

- **Plaintext messages:** Start byte `0x81`
- **Encrypted messages:** Start byte `0xC1`
- Encryption uses KMD (Key Material Data) as the key
- IV can be reset using `leaf_tag_ivreset`

### App-Level Encryption

The Android app uses additional encryption layers:

| Layer | Algorithm | Purpose |
|-------|-----------|---------|
| Android Keystore | AES-256-GCM | Protect data at rest without PIN |
| User-derived key | SHA-256 + AES | PIN-protected sensitive data |

---

## Key Management (3 Keys Per Application)

### What is an "Application"?

In the LEAF/DESFire context, an **application** is a functional area on the credential:

| Application | Purpose | Example Data |
|-------------|---------|--------------|
| PACS | Physical access control | Badge ID, facility code |
| Campus | Auxiliary services | Cafeteria balance, library access |
| Biometrics | Template storage | Iris/fingerprint templates |

### Key Slots

Each application supports multiple key slots:

```c
typedef enum _leaf_active_keys_id_t {
    leaf_key1_active = 1,        // Only key slot 1 active
    leaf_key1and2_active = 3     // Key slots 1 AND 2 active
} leaf_active_keys_id_t;
```

| Key Slot | Purpose |
|----------|---------|
| **Key 1** | Primary/current active key |
| **Key 2** | Backup/next key (for rotation) |
| **Key 3** | Reserved/transitional key |

### Key Rotation Flow

```
Before rotation:  Key 1 active only (leaf_key1_active = 1)
                  ↓
During rotation:  Key 1 AND Key 2 active (leaf_key1and2_active = 3)
                  (Reader accepts either key)
                  ↓
After rotation:   Key 2 becomes new Key 1
                  Old Key 1 discarded
                  New Key 2 provisioned
```

### Why Multiple Keys?

1. **Seamless rotation** - No downtime during key changes
2. **Rollback capability** - Old key works if new key fails
3. **User continuity** - Users never get locked out during updates

---

## Credential Expiration

### SDK Behavior

The SDK **does not enforce expiration** - it's a server-side concern.

### Metadata

```c
#define LEAF_META_LEN 0x04  // 4 bytes of metadata per keyset
extern unsigned char Leaf_emptyMetadata[LEAF_META_LEN];
```

Metadata can encode:
- Expiration timestamps
- Version numbers
- Active key indicators
- Custom application data

### Server-Side Expiration

The server manages credential lifecycle:

1. Database tracks credential expiration dates
2. On `/device/refresh`, server checks validity
3. Expired credentials are either:
   - Rejected (access revoked)
   - Renewed (new credentials issued)

### Best Practices

- Call `/device/refresh` periodically
- Handle refresh failures gracefully
- Implement background refresh before expiration

---

## Custom Server Implementation

### Can You Implement Your Own Server?

**Yes**, but with significant requirements.

### Requirements

| Requirement | Difficulty | Notes |
|-------------|------------|-------|
| Generate valid CP payloads | High | 330-byte value format undocumented |
| Create server tokens | Medium | Random 32-byte generation |
| Manage device UIDs | Low | 8-byte unique identifiers |
| **Access to LEAF keys** | **Critical** | Must have valid encryption keys |

### The Key Problem

The SDK uses AES-128 for all encryption:

```c
Leaf_SerializeBleMessage(..., unsigned char *kmd);   // KMD for message encryption
Leaf_PackCredentialPayload(..., unsigned char *kcd); // KCD for credential data
```

**Without valid keys:**
- Credentials won't decrypt on the reader
- Authentication fails (`leaf_rsp_fail`)
- Door won't open

### Obtaining Keys

1. **LEAF Si (Secure Issuance)** - Wavelynx manages shared keys
2. **LEAF Cc (Custom Crypto)** - Own keys via LEAF Community membership

### LEAF Community Membership

The [LEAF Community](https://www.leaf-community.com/) offers:
- Visionary tier: LEAF Universal API access
- Key exchange protocols
- Integration support

### Custom Server Use Cases

The external server pattern supports several use cases:

**1. Direct implementation (if you have LEAF keys):**
- Implement the simple GET-based API
- Generate valid KMD/CP using your LEAF keys
- Full control over credential lifecycle

**2. Proxy to Wavelynx:**
- Your server handles device management
- Calls Wavelynx backend for actual credential generation
- Returns credentials to your app
- Add custom business logic (access schedules, approvals, audit logs)

**3. Development/Testing:**
- Mock server for app development
- Test credential flows without Wavelynx connectivity
- Validate app behavior with controlled responses

**4. Enterprise integration:**
- Connect to existing identity management systems
- Sync with HR databases for employee credentials
- Implement custom approval workflows

---

## Key Files Reference

### Android SDK

| File | Purpose |
|------|---------|
| `app/libs/leafble-4.0.0.aar` | LEAF BLE SDK library |
| `app/src/main/jniLibs/*/libleaflib.so` | Native crypto library |

### iOS SDK

| File | Purpose |
|------|---------|
| `ios-sdk/LeafBle.xcframework/` | iOS framework |
| `Headers/LeafCore.h` | Core data structures (341 lines) |
| `Headers/LeafCentral.h` | Central state machine (44 lines) |
| `Headers/Aes.h` | AES-128 CBC functions (56 lines) |
| `Headers/Random.h` | Random generation (16 lines) |

### Android App Source

| File | Purpose |
|------|---------|
| `utilities/Crypto.kt` | AES-GCM, ECDH, key generation |
| `utilities/SecureStore.kt` | Encrypted SharedPreferences |
| `userdatastore/Credential.kt` | Credential data model |
| `userdatastore/Identity.kt` | EC key pair management |
| `credentialissuanceserver/implementation/WlNyxCredentialServer.kt` | Wavelynx API client |
| `credentialissuanceserver/implementation/ExternalCredentialServer.kt` | Custom server client |
| `ui/screens/credential/view/CredentialViewModel.kt` | BLE transaction orchestration |

---

## Constants Reference

### From LeafCore.h

```c
// Block sizes
#define LEAF_BLOCK_SIZE        0x10    // 16 bytes (AES block)
#define LEAF_UID_LEN           0x08    // 8 bytes (device UID)
#define LEAF_META_LEN          0x04    // 4 bytes (metadata)

// Credential Payload
#define LEAF_CP_VALUE_LEN      330     // Payload value size
#define LEAF_CP_OVERHEAD       42      // Header overhead
#define LEAF_CP_ID             0xCC    // CP tag identifier

// Transaction Certificate
#define LEAF_TC_LEN            98      // Total TC size
#define LEAF_TC_RFU_LEN        48      // Reserved field size
#define LEAF_TC_ID             0xCE    // TC tag identifier

// BLE Messaging
#define LEAF_BLE_MSG_OVERHEAD  0x04    // Message header size
#define LEAF_MAX_BLE_MSG_VAL   400     // Max payload size
#define LEAF_BLE_MSG_PLAINTEXT 0x81    // Plaintext start byte
#define LEAF_BLE_MSG_CIPHER    0xC1    // Encrypted start byte

// Key diversification
#define LEAF_SUBKEY_XOR_VAL    0x87    // XOR constant
#define LEAF_DIVINPUT_CONST    0x01    // Diversification input

// NFC
#define LEAF_MAX_APDU_DATA_LEN 0xFF    // 255 bytes max APDU data
#define LEAF_AID_LEN           5       // Application ID length
```

### Response Codes

```c
typedef enum _leaf_rsp_t {
    leaf_rsp_success = 0,      // Success
    leaf_rsp_fail,             // Failure
    leaf_rsp_authrequired,     // Authentication required
    leaf_rsp_invalid,          // Invalid request
    leaf_rsp_multistart,       // Multi-message start
    leaf_rsp_multiend          // Multi-message end
} leaf_rsp_t;
```

### NFC Status Words (SW1)

```c
typedef enum _leaf_sw1_t {
    leaf_sw1_not_allowed = 0x69,  // Unknown/invalid command
    leaf_sw1_fail = 0x6F,         // Known command failed
    leaf_sw1_success = 0x90       // Success
} leaf_sw1_t;
```

---

## References

### Official Resources

- [LEAF Community](https://www.leaf-community.com/)
- [LEAF Framework](https://www.leaf-community.com/leaf-framework)
- [Wavelynx Support](https://support.wavelynx.com/)
- [Wavelynx Key Management](https://www.wavelynx.com/products/key-management)

### Technical Standards

- NXP AN10922 - Symmetric Key Diversification
- NXP AN10957 - Generic Access Control Data Model
- ISO 7816-4 - APDU Command Format
- MIFARE DESFire EV2/EV3 Specification

### SDK Documentation

- iOS SDK: `ios-sdk/docs/index.html`
- SDK Version: 4.0.0 (2025-07-14)
- Copyright: WaveLynx Technologies, 2019-2023

---

*Document generated from technical analysis of the Wavelynx LEAF BLE SDK (Android and iOS) and public LEAF Community resources.*
