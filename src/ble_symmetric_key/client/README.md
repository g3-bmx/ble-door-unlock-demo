# BLE GATT Client - Symmetric Key Authentication

A BLE central (GATT client) specification for credential communication using symmetric key authentication.
This document provides platform-agnostic specifications for implementing the client on any platform (iOS, Android, etc.).

---

## Table of Contents

1. [Context](#context)
2. [Architecture Overview](#architecture-overview)
3. [Authentication Process](#authentication-process)
4. [GATT Client](#gatt-client)
5. [Characteristics](#characteristics)
6. [Message Format](#message-format)
7. [Responses](#responses)
8. [Cryptographic Specification](#cryptographic-specification)
9. [State Machine](#state-machine)
10. [Error Handling](#error-handling)

---

## Context

This GATT client represents a mobile device that:

1. Scans for and connects to credential readers (GATT servers)
2. Authenticates with the reader using symmetric key cryptography
3. Sends encrypted credentials to the reader
4. Receives and displays credential acceptance or rejection

The design follows the WaveLynx LEAF SDK pattern of using a **single characteristic** for bidirectional communication via Write (commands) and Notify (responses).

### Key Assumptions

- The mobile device has a **Device ID** assigned during enrollment
- The mobile device has a **Device Key (DK)** provisioned during enrollment
- The mobile device **never** has access to the Master Key
- All sensitive payloads are encrypted with AES-128-CBC

### Prerequisites

The client must have these values **pre-provisioned**:

| Data | Size | Description |
|------|------|-------------|
| Device ID | 16 bytes | Unique identifier for this mobile device |
| Device Key (DK) | 16 bytes | Symmetric key derived from MasterKey + DeviceID |
| Credential Payload | Variable | The credential string to present |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         System Architecture                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Mobile Device (Central)              Reader (Peripheral)           │
│   ┌─────────────────────┐              ┌─────────────────────┐      │
│   │                     │              │                     │      │
│   │  Device ID (16B)    │              │  Master Key (16B)   │      │
│   │  Device Key (DK)    │              │                     │      │
│   │                     │              │                     │      │
│   │  (DK provisioned    │              │  On AUTH_REQUEST:   │      │
│   │   to device during  │              │  1. Extract DeviceID│      │
│   │   enrollment -      │              │  2. Derive DK:      │      │
│   │   device never      │              │     DK = HKDF(      │      │
│   │   knows MasterKey)  │              │       MasterKey,    │      │
│   │                     │              │       DeviceID      │      │
│   │                     │              │     )               │      │
│   └─────────┬───────────┘              └──────────┬──────────┘      │
│             │                                     │                  │
│             │         BLE Connection              │                  │
│             │◄───────────────────────────────────►│                  │
│             │                                     │                  │
│             │  Write ──────────────────────────►  │                  │
│             │  (Commands)                         │                  │
│             │                                     │                  │
│             │  ◄────────────────────────── Notify │                  │
│             │                         (Responses) │                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Client Responsibilities

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Flow                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. SCAN         Scan for CREDENTIAL_SERVICE_UUID                   │
│       │                                                              │
│       ▼                                                              │
│  2. CONNECT      Connect to discovered peripheral                   │
│       │                                                              │
│       ▼                                                              │
│  3. DISCOVER     Find DATA_TRANSFER characteristic                  │
│       │                                                              │
│       ▼                                                              │
│  4. SUBSCRIBE    Write 0x0001 to CCCD (enable notifications)        │
│       │                                                              │
│       ▼                                                              │
│  5. AUTH         Send AUTH_REQUEST, wait for AUTH_RESPONSE          │
│       │          Verify Nonce_M in response                         │
│       ▼                                                              │
│  6. CREDENTIAL   Send CREDENTIAL, wait for CREDENTIAL_RESPONSE      │
│       │                                                              │
│       ▼                                                              │
│  7. DISCONNECT   Clean up and display result                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Authentication Process

The client initiates mutual authentication using a challenge-response protocol.
Both parties prove possession of the shared Device Key without transmitting it.

### Flow Diagram

```
Mobile (Central)                                    Reader (Peripheral)
      │                                                      │
      │                    ┌─────────────┐                   │
      │                    │ 1. CONNECT  │                   │
      │  ─────────────────►│             │◄───────────────── │
      │                    └─────────────┘                   │
      │                                                      │
      │  ══════════════════════════════════════════════════  │
      │                  AUTHENTICATION PHASE                │
      │  ══════════════════════════════════════════════════  │
      │                                                      │
      │  Generate Nonce_M (16 bytes random)                  │
      │  Generate IV_M (16 bytes random)                     │
      │  SAVE Nonce_M for verification                       │
      │                                                      │
      │  ──── AUTH_REQUEST ────────────────────────────────► │
      │       [0x01][DeviceID][IV_M][Enc_DK(Nonce_M)]        │
      │                                                      │
      │  Start 3-second timeout                              │
      │                                                      │
      │                          Lookup/Derive DK from DeviceID
      │                          Decrypt Nonce_M using DK + IV_M
      │                          Generate Nonce_R (16 bytes random)
      │                          Generate IV_R (16 bytes random)
      │                                                      │
      │  ◄─────────────────────────────────── AUTH_RESPONSE  │
      │       [0x02][IV_R][Enc_DK(Nonce_M || Nonce_R)]       │
      │                                                      │
      │  Decrypt payload using DK + IV_R                     │
      │  Extract Received_Nonce_M = Decrypted[0:16]          │
      │  Extract Nonce_R = Decrypted[16:32]                  │
      │                                                      │
      │  ┌─────────────────────────────────────────────┐     │
      │  │ VERIFY: Received_Nonce_M == Nonce_M ?       │     │
      │  │   YES → Reader authenticated, continue      │     │
      │  │   NO  → FAIL: "Authentication failed"       │     │
      │  └─────────────────────────────────────────────┘     │
      │                                                      │
      │  ══════════════════════════════════════════════════  │
      │                  CREDENTIAL PHASE                    │
      │  ══════════════════════════════════════════════════  │
      │                                                      │
      │  Generate IV_C (16 bytes random)                     │
      │  Encode credential string as UTF-8 bytes             │
      │                                                      │
      │  ──── CREDENTIAL ──────────────────────────────────► │
      │       [0x03][IV_C][Enc_DK(CredentialPayload)]        │
      │                                                      │
      │  Start 3-second timeout                              │
      │                                                      │
      │                          Decrypt credential using DK + IV_C
      │                          Process/validate credential
      │                                                      │
      │  ◄───────────────────────────── CREDENTIAL_RESPONSE  │
      │       [0x04][Status]                                 │
      │                                                      │
      │  Display result to user                              │
      │                                                      │
      │                    ┌─────────────┐                   │
      │                    │ DISCONNECT  │                   │
      │  ◄─────────────────│             │─────────────────► │
      │                    └─────────────┘                   │
      │                                                      │
```

### Mutual Authentication Explained

| Step | Who Proves What | How |
|------|-----------------|-----|
| AUTH_REQUEST | Mobile proves it has DK | Encrypts Nonce_M with DK; only correct DK can produce valid ciphertext |
| AUTH_RESPONSE | Reader proves it has DK | Includes decrypted Nonce_M in response; mobile verifies it matches |

The reader echoing back `Nonce_M` inside the encrypted response proves:
1. Reader successfully decrypted the AUTH_REQUEST (has correct DK)
2. Reader is responding to *this specific* authentication attempt (replay protection)

### Client Verification Steps

```
1. Receive AUTH_RESPONSE notification
2. Parse: IV_R = response[1:17], Encrypted_Nonces = response[17:49]
3. Decrypt: Decrypted = AES-128-CBC-Decrypt(DK, IV_R, Encrypted_Nonces)
4. Extract: Received_Nonce_M = Decrypted[0:16], Nonce_R = Decrypted[16:32]
5. Compare: Received_Nonce_M == Nonce_M (the one we generated and saved)
6. If match: Reader is authenticated → proceed to send credential
7. If no match: FAIL → display "Authentication failed", disconnect
```

---

## GATT Client

### Service Discovery

| Property | Value |
|----------|-------|
| **Service Name** | Credential Service |
| **Service UUID** | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |

### Scanning

The client scans with:
- Service UUID filter: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- Scan timeout: 5 seconds
- On discovery: Connect to first matching peripheral

### Connection Sequence

```
1. Scan for peripherals advertising CREDENTIAL_SERVICE_UUID
2. Stop scan when peripheral found
3. Connect to peripheral
4. Wait for connection confirmation
5. Discover services
6. Find CREDENTIAL_SERVICE by UUID
7. Discover characteristics for service
8. Find DATA_TRANSFER characteristic by UUID
9. Write 0x0001 to CCCD descriptor to enable notifications
10. Wait for notification subscription confirmation
11. Begin authentication protocol
```

---

## Characteristics

### Data Transfer Characteristic

The client interacts with a single characteristic for all communication.

| Property | Value |
|----------|-------|
| **Characteristic Name** | Data Transfer |
| **Characteristic UUID** | `b2c3d4e5-f678-90ab-cdef-234567890abc` |
| **Properties Used** | Write Without Response, Notify |
| **Descriptors** | CCCD (0x2902) |

#### Write Operations

- Use **Write Without Response** for all writes
- Do not wait for write confirmation at BLE layer
- Protocol-level responses come via notifications

#### Notification Handling

- Subscribe to notifications before sending any messages
- All server responses arrive as notifications
- Buffer notifications and match to pending requests

### Client Characteristic Configuration Descriptor (CCCD)

| Property | Value |
|----------|-------|
| **UUID** | `0x2902` (Standard BLE) |
| **Purpose** | Enable/disable notifications |
| **Value to Enable** | `0x0001` (little-endian) |
| **Value to Disable** | `0x0000` |

**Important**: The client MUST write `0x0001` to the CCCD before sending AUTH_REQUEST, otherwise responses will not be received.

---

## Message Format

All messages follow a simple Type-Length-Value inspired format:

```
┌──────────────┬─────────────────────────────────────────┐
│ Message Type │              Payload                    │
│   (1 byte)   │           (variable length)             │
└──────────────┴─────────────────────────────────────────┘
```

### Message Types

| Type | Code | Direction | Description |
|------|------|-----------|-------------|
| AUTH_REQUEST | `0x01` | Mobile → Reader | Initiate authentication |
| AUTH_RESPONSE | `0x02` | Reader → Mobile | Authentication challenge response |
| CREDENTIAL | `0x03` | Mobile → Reader | Send encrypted credential |
| CREDENTIAL_RESPONSE | `0x04` | Reader → Mobile | Credential processing result |
| ERROR | `0xFF` | Reader → Mobile | Error notification |

### Messages Sent by Client

#### AUTH_REQUEST (0x01)

```
┌──────┬────────────┬────────────┬─────────────────────┐
│ 0x01 │ Device ID  │     IV     │   Enc_DK(Nonce_M)   │
│  1B  │    16B     │    16B     │        16B          │
└──────┴────────────┴────────────┴─────────────────────┘
Total: 49 bytes
```

**Build Process:**
```
1. Generate Nonce_M: 16 cryptographically random bytes
2. SAVE Nonce_M in memory (needed for verification)
3. Generate IV_M: 16 cryptographically random bytes
4. Encrypt: Ciphertext = AES-128-CBC-Encrypt(DK, IV_M, Nonce_M)
5. Build: [0x01] + DeviceID + IV_M + Ciphertext
```

#### CREDENTIAL (0x03)

```
┌──────┬────────────┬─────────────────────────────┐
│ 0x03 │     IV     │   Enc_DK(CredentialPayload) │
│  1B  │    16B     │         Variable            │
└──────┴────────────┴─────────────────────────────┘
Total: 17 + len(encrypted_credential) bytes
```

**Build Process:**
```
1. Encode credential string as UTF-8 bytes
2. Generate IV_C: 16 cryptographically random bytes
3. Pad payload using PKCS7
4. Encrypt: Ciphertext = AES-128-CBC-Encrypt(DK, IV_C, PaddedPayload)
5. Build: [0x03] + IV_C + Ciphertext
```

### Messages Received by Client

#### AUTH_RESPONSE (0x02)

```
┌──────┬────────────┬─────────────────────────────┐
│ 0x02 │     IV     │  Enc_DK(Nonce_M || Nonce_R) │
│  1B  │    16B     │            32B              │
└──────┴────────────┴─────────────────────────────┘
Total: 49 bytes
```

**Parse Process:**
```
1. Verify message type: response[0] == 0x02
2. Extract IV_R: response[1:17]
3. Extract Encrypted_Nonces: response[17:49]
4. Decrypt: Decrypted = AES-128-CBC-Decrypt(DK, IV_R, Encrypted_Nonces)
5. Extract Received_Nonce_M: Decrypted[0:16]
6. Extract Nonce_R: Decrypted[16:32]
7. VERIFY: Received_Nonce_M == Nonce_M (saved earlier)
```

#### CREDENTIAL_RESPONSE (0x04)

```
┌──────┬────────┐
│ 0x04 │ Status │
│  1B  │   1B   │
└──────┴────────┘
Total: 2 bytes
```

**Parse Process:**
```
1. Verify message type: response[0] == 0x04
2. Extract status: response[1]
3. Map status to user message
```

#### ERROR (0xFF)

```
┌──────┬────────────┐
│ 0xFF │ Error Code │
│  1B  │     1B     │
└──────┴────────────┘
Total: 2 bytes
```

**Parse Process:**
```
1. Verify message type: response[0] == 0xFF
2. Extract error code: response[1]
3. Map error to user message
4. Disconnect
```

---

## Responses

### Credential Response Status Codes

| Code | Name | User Message |
|------|------|--------------|
| `0x00` | SUCCESS | "Access granted" |
| `0x01` | REJECTED | "Access denied" |
| `0x02` | EXPIRED | "Credential expired" |
| `0x03` | REVOKED | "Credential revoked" |
| `0x04` | INVALID_FORMAT | "Invalid credential" |

### Error Codes

| Code | Name | User Message |
|------|------|--------------|
| `0x01` | INVALID_MESSAGE | "Communication error" |
| `0x02` | UNKNOWN_DEVICE | "Device not recognized" |
| `0x03` | DECRYPTION_FAILED | "Authentication failed" |
| `0x04` | INVALID_STATE | "Protocol error" |
| `0x05` | AUTH_FAILED | "Authentication failed" |
| `0x06` | TIMEOUT | "Reader timeout" |

---

## Cryptographic Specification

### Algorithm Parameters

| Parameter | Value |
|-----------|-------|
| **Encryption Algorithm** | AES-128-CBC |
| **Key Size** | 128 bits (16 bytes) |
| **Block Size** | 16 bytes |
| **IV Size** | 16 bytes |
| **Padding** | PKCS7 |
| **Nonce Size** | 16 bytes |

### Initialization Vector (IV)

- **Purpose**: Ensures identical plaintexts produce different ciphertexts
- **Generation**: Cryptographically random, 16 bytes
- **Uniqueness**: Must be unique per encryption operation
- **Secrecy**: Not secret; transmitted in plaintext alongside ciphertext
- **Reuse**: NEVER reuse an IV with the same key

### Encryption Process (Client)

```
1. Generate random 16-byte IV
2. Pad plaintext to 16-byte boundary using PKCS7
3. Encrypt: ciphertext = AES-128-CBC-Encrypt(DK, IV, padded_plaintext)
4. Build message: [MessageType] + [IV] + [ciphertext]
```

### Decryption Process (Client)

```
1. Extract IV from message (bytes after message type, 16 bytes)
2. Extract ciphertext (remaining bytes)
3. Decrypt: padded_plaintext = AES-128-CBC-Decrypt(DK, IV, ciphertext)
4. Remove PKCS7 padding
```

### PKCS7 Padding

**Padding (before encryption):**
```
1. Calculate padding_length = 16 - (len(data) % 16)
2. If data length is multiple of 16, padding_length = 16
3. Append padding_length bytes, each with value padding_length
```

**Unpadding (after decryption):**
```
1. Read last byte of decrypted data as padding_length
2. Verify last padding_length bytes all equal padding_length
3. Remove last padding_length bytes
```

---

## State Machine

The GATT client maintains state to track protocol progress.

```
         ┌──────────────┐
         │     IDLE     │◄─────────────────────────────────┐
         └──────┬───────┘                                  │
                │ User initiates                           │
                ▼                                          │
         ┌──────────────┐                                  │
         │   SCANNING   │──── Timeout (5s) ────► IDLE      │
         └──────┬───────┘     "No reader found"            │
                │ Found reader                             │
                ▼                                          │
         ┌──────────────┐                                  │
         │  CONNECTING  │──── Fail ────► IDLE              │
         └──────┬───────┘     "Connection failed"          │
                │ Connected                                │
                ▼                                          │
         ┌──────────────┐                                  │
         │  DISCOVERING │──── Fail ────► IDLE              │
         └──────┬───────┘     "Service not found"          │
                │ Service & Characteristic found           │
                ▼                                          │
         ┌──────────────┐                                  │
         │  SUBSCRIBING │──── Fail ────► IDLE              │
         └──────┬───────┘     "Subscription failed"        │
                │ CCCD written, notifications enabled      │
                ▼                                          │
         ┌──────────────┐                                  │
         │AUTHENTICATING│──── Timeout (3s) ────► IDLE      │
         └──────┬───────┘     "Authentication timeout"     │
                │             │                            │
                │             │ ERROR received ────► IDLE  │
                │             │ (show error message)       │
                │             │                            │
                │             │ Nonce mismatch ────► IDLE  │
                │               "Authentication failed"    │
                │                                          │
                │ AUTH_RESPONSE valid                      │
                ▼                                          │
         ┌──────────────┐                                  │
         │ SENDING_CRED │──── Timeout (3s) ────► IDLE      │
         └──────┬───────┘     "Response timeout"           │
                │             │                            │
                │             │ ERROR received ────► IDLE  │
                │               (show error message)       │
                │                                          │
                │ CREDENTIAL_RESPONSE received             │
                ▼                                          │
         ┌──────────────┐                                  │
         │   COMPLETE   │──── Show result ────► IDLE       │
         └──────────────┘     Disconnect                   │
```

### State Transitions

| Current State | Event | Next State | Action |
|---------------|-------|------------|--------|
| IDLE | User initiates | SCANNING | Start BLE scan |
| SCANNING | Reader found | CONNECTING | Stop scan, connect |
| SCANNING | Timeout (5s) | IDLE | Show "No reader found" |
| CONNECTING | Connected | DISCOVERING | Discover services |
| CONNECTING | Failure | IDLE | Show "Connection failed" |
| DISCOVERING | Found characteristic | SUBSCRIBING | Write to CCCD |
| DISCOVERING | Not found | IDLE | Show "Service not found" |
| SUBSCRIBING | Subscribed | AUTHENTICATING | Send AUTH_REQUEST |
| SUBSCRIBING | Failure | IDLE | Show "Subscription failed" |
| AUTHENTICATING | Valid AUTH_RESPONSE | SENDING_CRED | Send CREDENTIAL |
| AUTHENTICATING | Invalid response | IDLE | Show "Authentication failed" |
| AUTHENTICATING | ERROR received | IDLE | Show error message |
| AUTHENTICATING | Timeout (3s) | IDLE | Show "Authentication timeout" |
| SENDING_CRED | CREDENTIAL_RESPONSE | COMPLETE | Parse status |
| SENDING_CRED | ERROR received | IDLE | Show error message |
| SENDING_CRED | Timeout (3s) | IDLE | Show "Response timeout" |
| COMPLETE | Result shown | IDLE | Disconnect |

---

## Error Handling

### Timeout Configuration

| Operation | Timeout | On Timeout |
|-----------|---------|------------|
| BLE Scan | 5 seconds | "No reader found" |
| Connection | 5 seconds | "Connection failed" |
| Service Discovery | 5 seconds | "Service not found" |
| AUTH_RESPONSE wait | 3 seconds | "Authentication timeout" |
| CREDENTIAL_RESPONSE wait | 3 seconds | "Response timeout" |

### Error Response Handling

When an ERROR message (0xFF) is received:
```
1. Parse error code from response[1]
2. Map to user-friendly message
3. Disconnect from peripheral
4. Display error to user
5. Return to IDLE state
```

### Authentication Failure

When Nonce_M verification fails:
```
1. DO NOT send any more messages
2. Disconnect immediately
3. Display "Authentication failed - reader verification failed"
4. Return to IDLE state
```

### Connection Loss

If connection drops unexpectedly:
```
1. Cancel any pending timeouts
2. Clear session data (nonces, etc.)
3. Display "Connection lost"
4. Return to IDLE state
```

### Security Checklist

- [ ] Device Key stored securely (iOS Keychain / Android Keystore)
- [ ] Nonce_M kept only in memory during auth, cleared after
- [ ] IV generated fresh for each encryption operation
- [ ] Verify Nonce_M match before trusting reader
- [ ] Clear sensitive data from memory after disconnect
- [ ] Do not log sensitive data (keys, nonces, credentials)

---

## MTU Negotiation

The client should request the highest possible MTU to accommodate variable-length credentials.

| Parameter | Value |
|-----------|-------|
| **Requested MTU** | 512 bytes |
| **Minimum Required** | 49 bytes (AUTH_REQUEST size) |
| **Default BLE MTU** | 23 bytes (20 byte payload) |

**Platform Notes:**
- **iOS**: MTU negotiation is automatic; system handles it
- **Android**: Call `requestMtu(512)` after connection

If MTU is too low for credential payload, the client should:
1. Display "Credential too large"
2. Disconnect
3. Return to IDLE

---

## Security Considerations

### Implemented

- **Mutual authentication**: Both parties prove key possession
- **Replay protection**: Random nonces per session
- **Encryption**: All sensitive data encrypted with AES-128-CBC
- **Nonce verification**: Client verifies reader's response

### Client Security Requirements

- Store Device Key in secure enclave (Keychain/Keystore)
- Generate cryptographically random IVs and nonces
- Never log or persist sensitive data
- Clear memory after disconnect
- Validate all server responses before processing

### Not Implemented (POC Limitations)

- **Key rotation**: Device Key is static
- **Certificate pinning**: No PKI infrastructure
- **Message integrity**: CBC provides confidentiality, not integrity (consider GCM for production)
- **Secure pairing**: Relies on pre-provisioned keys

---

## References

- [BLE GATT Server Specification](../server/README.md)
- [WaveLynx LEAF iOS SDK GATT Specifics](../../../docs/IOS_BLE_GATT_SERVER_SPECIFICS.md)
- [BLE Communication Flows](../../../docs/BLE_COMMUNICATION_FLOWS.md)
- [Bluetooth GATT Specification](https://www.bluetooth.com/specifications/gatt/)
- [AES-CBC NIST SP 800-38A](https://csrc.nist.gov/publications/detail/sp/800-38a/final)

---

## Appendix: POC Test Configuration

For testing with the POC server, use these hardcoded values:

```
Master Key (Server): 00112233445566778899aabbccddeeff
Device ID:           deadbeefcafebabedeadbeefcafebabe
Device Key (DK):     <derived from HKDF-SHA256(MasterKey, DeviceID, "device-key")>
Credential:          "test-credential-12345"
```

**Note**: The Device Key must be derived using the same HKDF parameters as the server. See the server's crypto module for the exact derivation.
