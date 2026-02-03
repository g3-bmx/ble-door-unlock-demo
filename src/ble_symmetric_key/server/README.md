# BLE GATT Server - Symmetric Key Authentication

A BLE peripheral (GATT server) implementation for credential communication using symmetric key authentication.
Built with Python and the `bless` library for portability purposes.

---

## Table of Contents

1. [Context](#context)
2. [Architecture Overview](#architecture-overview)
3. [Authentication Process](#authentication-process)
4. [GATT Server](#gatt-server)
5. [Characteristics](#characteristics)
6. [Message Format](#message-format)
7. [Responses](#responses)
8. [Cryptographic Specification](#cryptographic-specification)
9. [State Machine](#state-machine)
10. [Error Handling](#error-handling)

---

## Context

This GATT server simulates a door reader device/intercom that:

1. Advertises a credential service for mobile devices to discover
2. Authenticates connecting mobile devices using symmetric key cryptography
3. Receives and processes encrypted credentials
4. Responds with credential acceptance or rejection

The design follows the WaveLynx LEAF SDK pattern of using a **single characteristic** for bidirectional communication via Write (commands) and Notify (responses).

### Key Assumptions

- The reader holds a **Master Key** used to derive device-specific keys
- Mobile devices have a **Device Key** derived from the Master Key + their Device ID
- Device Key derivation uses HKDF-SHA256 (Wavelynx uses a different approach - but unknown for now)
- All sensitive payloads are encrypted with AES-128-CBC

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
│   │                     │              │  Derives DK from:   │      │
│   │  DK = HKDF(         │              │  DK = HKDF(         │      │
│   │    MasterKey,       │              │    MasterKey,       │      │
│   │    DeviceID         │              │    DeviceID         │      │
│   │  )                  │              │  )                  │      │
│   │                     │              │                     │      │
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

---

## Authentication Process

The server implements mutual authentication using a challenge-response protocol. Both parties prove possession of the shared Device Key without transmitting it.

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
      │                                                      │
      │  ──── AUTH_REQUEST ────────────────────────────────► │
      │       [0x01][DeviceID][IV_M][Enc_DK(Nonce_M)]        │
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
      │  Verify first 16 bytes == Nonce_M                    │
      │  Extract Nonce_R (proves reader has correct DK)      │
      │                                                      │
      │  ══════════════════════════════════════════════════  │
      │                  CREDENTIAL PHASE                    │
      │  ══════════════════════════════════════════════════  │
      │                                                      │
      │  Generate IV_C (16 bytes random)                     │
      │                                                      │
      │  ──── CREDENTIAL ──────────────────────────────────► │
      │       [0x03][IV_C][Enc_DK(CredentialPayload)]        │
      │                                                      │
      │                          Decrypt credential using DK + IV_C
      │                          Process/validate credential
      │                                                      │
      │  ◄───────────────────────────── CREDENTIAL_RESPONSE  │
      │       [0x04][Status]                                 │
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

---

## GATT Server

### Service Definition

| Property | Value |
|----------|-------|
| **Service Name** | Credential Service |
| **Service UUID** | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| **Service Type** | Primary |

### Advertising

The server advertises with:
- Service UUID in the advertisement data
- Local name: `CRED-READER` (configurable)
- Connectable: Yes

---

## Characteristics

### Data Transfer Characteristic

The server exposes a single characteristic for all communication.

| Property | Value |
|----------|-------|
| **Characteristic Name** | Data Transfer |
| **Characteristic UUID** | `b2c3d4e5-f678-90ab-cdef-234567890abc` |
| **Properties** | Write Without Response, Notify |
| **Descriptors** | CCCD (0x2902) |

#### Why Write Without Response?

- Eliminates ACK round-trip latency (~7.5ms saved per write)
- Protocol handles reliability at application layer
- Matches WaveLynx LEAF SDK pattern

#### Why Notify (not Indicate)?

- Lower latency than Indicate (no ACK required)
- Sufficient for credential transfer use case
- Application-layer responses provide confirmation

### Client Characteristic Configuration Descriptor (CCCD)

| Property | Value |
|----------|-------|
| **UUID** | `0x2902` (Standard BLE) |
| **Purpose** | Enable/disable notifications |
| **Value to Enable** | `0x0001` |
| **Value to Disable** | `0x0000` |

Mobile devices must write `0x0001` to the CCCD before receiving notifications.

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

### Payload Structures

#### AUTH_REQUEST (0x01)

```
┌──────┬────────────┬────────────┬─────────────────────┐
│ 0x01 │ Device ID  │     IV     │   Enc_DK(Nonce_M)   │
│  1B  │    16B     │    16B     │        16B          │
└──────┴────────────┴────────────┴─────────────────────┘
Total: 49 bytes
```

#### AUTH_RESPONSE (0x02)

```
┌──────┬────────────┬─────────────────────────────┐
│ 0x02 │     IV     │  Enc_DK(Nonce_M || Nonce_R) │
│  1B  │    16B     │            32B              │
└──────┴────────────┴─────────────────────────────┘
Total: 49 bytes
```

#### CREDENTIAL (0x03)

```
┌──────┬────────────┬─────────────────────────────┐
│ 0x03 │     IV     │   Enc_DK(CredentialPayload) │
│  1B  │    16B     │         Variable            │
└──────┴────────────┴─────────────────────────────┘
Total: 17 + len(encrypted_credential) bytes
```

#### CREDENTIAL_RESPONSE (0x04)

```
┌──────┬────────┐
│ 0x04 │ Status │
│  1B  │   1B   │
└──────┴────────┘
Total: 2 bytes
```

#### ERROR (0xFF)

```
┌──────┬────────────┐
│ 0xFF │ Error Code │
│  1B  │     1B     │
└──────┴────────────┘
Total: 2 bytes
```

---

## Responses

### Credential Response Status Codes

| Code | Name | Description |
|------|------|-------------|
| `0x00` | SUCCESS | Credential accepted, access granted |
| `0x01` | REJECTED | Credential rejected, access denied |
| `0x02` | EXPIRED | Credential has expired |
| `0x03` | REVOKED | Credential has been revoked |
| `0x04` | INVALID_FORMAT | Credential payload malformed |

### Error Codes

| Code | Name | Description |
|------|------|-------------|
| `0x01` | INVALID_MESSAGE | Message format invalid or incomplete |
| `0x02` | UNKNOWN_DEVICE | Device ID not recognized |
| `0x03` | DECRYPTION_FAILED | Could not decrypt payload (wrong key?) |
| `0x04` | INVALID_STATE | Message received in unexpected state |
| `0x05` | AUTH_FAILED | Authentication verification failed |
| `0x06` | TIMEOUT | Operation timed out |

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
| **KDF** | HKDF-SHA256 |

### Key Derivation

Device Keys are derived from the Master Key using HKDF:

```
DeviceKey = HKDF-SHA256(
    ikm    = MasterKey,        // Input key material (16 bytes)
    salt   = DeviceID,         // Salt (16 bytes)
    info   = b"device-key",    // Context string
    length = 16                // Output length (16 bytes)
)
```

### Initialization Vector (IV)

- **Purpose**: Ensures identical plaintexts produce different ciphertexts
- **Generation**: Cryptographically random, 16 bytes
- **Uniqueness**: Must be unique per encryption operation
- **Secrecy**: Not secret; transmitted in plaintext alongside ciphertext
- **Reuse**: NEVER reuse an IV with the same key

### Encryption Process

```
1. Generate random 16-byte IV
2. Pad plaintext to 16-byte boundary (PKCS7)
3. Encrypt: ciphertext = AES-128-CBC(key, IV, padded_plaintext)
4. Transmit: [IV][ciphertext]
```

### Decryption Process

```
1. Extract IV (first 16 bytes)
2. Extract ciphertext (remaining bytes)
3. Decrypt: padded_plaintext = AES-128-CBC-Decrypt(key, IV, ciphertext)
4. Remove PKCS7 padding
```

---

## State Machine

The GATT server maintains connection state to enforce the authentication protocol.

```
                         ┌─────────────────────┐
                         │                     │
                         ▼                     │
                  ┌─────────────┐              │
         ┌───────│    IDLE     │◄──────────────┤
         │       └──────┬──────┘               │
         │              │                      │
         │              │ Client connects      │
         │              │ CCCD enabled         │
         │              ▼                      │
         │       ┌─────────────┐               │
         │       │  CONNECTED  │               │
         │       └──────┬──────┘               │
         │              │                      │
         │              │ Receives 0x01        │
         │              │ (AUTH_REQUEST)       │
         │              ▼                      │
         │       ┌─────────────┐               │
  Timeout│       │AUTHENTICATING│──── Fail ────┤
   or    │       └──────┬──────┘               │
  Error  │              │                      │
         │              │ Sends 0x02           │
         │              │ (AUTH_RESPONSE)      │
         │              ▼                      │
         │       ┌─────────────┐               │
         ├───────│AUTHENTICATED│──── Fail ─────┤
         │       └──────┬──────┘               │
         │              │                      │
         │              │ Receives 0x03        │
         │              │ (CREDENTIAL)         │
         │              ▼                      │
         │       ┌─────────────┐               │
         ├───────│ PROCESSING  │               │
         │       └──────┬──────┘               │
         │              │                      │
         │              │ Sends 0x04           │
         │              │ (CREDENTIAL_RESPONSE)│
         │              ▼                      │
         │       ┌─────────────┐               │
         └───────│  COMPLETE   │───────────────┘
                 └─────────────┘
                        │
                        │ Disconnect
                        ▼
                     (IDLE)
```

### State Transitions

| Current State | Event | Next State | Action |
|---------------|-------|------------|--------|
| IDLE | Client connects | CONNECTED | Initialize session |
| CONNECTED | Receive AUTH_REQUEST | AUTHENTICATING | Derive key, decrypt, validate |
| AUTHENTICATING | Validation success | AUTHENTICATED | Send AUTH_RESPONSE |
| AUTHENTICATING | Validation failure | IDLE | Send ERROR, disconnect |
| AUTHENTICATED | Receive CREDENTIAL | PROCESSING | Decrypt, process |
| PROCESSING | Processing complete | COMPLETE | Send CREDENTIAL_RESPONSE |
| COMPLETE | Response sent | IDLE | Disconnect |
| Any | Timeout | IDLE | Disconnect |
| Any | Error | IDLE | Send ERROR, disconnect |

---

## Error Handling

### Protocol Errors

| Scenario | Response | Action |
|----------|----------|--------|
| Unknown message type | ERROR (0x01) | Disconnect |
| Message too short | ERROR (0x01) | Disconnect |
| Unknown Device ID | ERROR (0x02) | Disconnect |
| Decryption failure | ERROR (0x03) | Disconnect |
| Wrong state for message | ERROR (0x04) | Disconnect |
| Nonce verification failed | ERROR (0x05) | Disconnect |

### Connection Errors

| Scenario | Behavior |
|----------|----------|
| Client disconnects unexpectedly | Reset to IDLE |
| CCCD not enabled | Responses not sent (client's problem) |
| Write to unknown characteristic | Ignored |

### Timeouts

| State | Timeout | Action |
|-------|---------|--------|
| CONNECTED (waiting for AUTH_REQUEST) | 30 seconds | Disconnect |
| AUTHENTICATED (waiting for CREDENTIAL) | 30 seconds | Disconnect |
| PROCESSING | 10 seconds | Send ERROR, disconnect |

---

## MTU Negotiation

The server requests the highest possible MTU to accommodate variable-length credentials.

| Parameter | Value |
|-----------|-------|
| **Requested MTU** | 512 bytes |
| **Minimum Required** | 49 bytes (AUTH_REQUEST size) |
| **Default BLE MTU** | 23 bytes (20 byte payload) |

If MTU negotiation fails or results in a low MTU, large credentials may need fragmentation (not implemented in this POC).

---

## Security Considerations

### Implemented

- **Mutual authentication**: Both parties prove key possession
- **Replay protection**: Random nonces per session
- **Encryption**: All sensitive data encrypted with AES-128-CBC
- **Key derivation**: Device-specific keys via HKDF

### Not Implemented (POC Limitations)

- **Key rotation**: Master key is hardcoded
- **Rate limiting**: No protection against brute-force
- **Secure storage**: Keys stored in plaintext
- **Certificate pinning**: No PKI infrastructure
- **Message integrity**: CBC provides confidentiality, not integrity (consider GCM for production)

---

## References

- [WaveLynx LEAF iOS SDK GATT Specifics](../../../docs/IOS_BLE_GATT_SERVER_SPECIFICS.md)
- [BLE Communication Flows](../../../docs/BLE_COMMUNICATION_FLOWS.md)
- [Bluetooth GATT Specification](https://www.bluetooth.com/specifications/gatt/)
- [HKDF RFC 5869](https://tools.ietf.org/html/rfc5869)
- [AES-CBC NIST SP 800-38A](https://csrc.nist.gov/publications/detail/sp/800-38a/final)
