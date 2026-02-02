# Master Key BLE Connection Pattern

Technical documentation explaining how the master key and derived key pattern works when establishing a secure BLE connection between a peripheral (reader with master key) and a central (mobile phone with derived key).

---

## Table of Contents

1. [Overview: Key Hierarchy](#overview-key-hierarchy)
2. [Architecture 2: Reader Has Master Key](#architecture-2-reader-has-master-key)
3. [Step-by-Step Connection Flow](#step-by-step-connection-flow)
4. [Mutual Authentication Protocol](#mutual-authentication-protocol)
5. [Encrypted Data Transfer](#encrypted-data-transfer)
6. [Cryptographic Details](#cryptographic-details)
7. [Security Analysis](#security-analysis)
8. [FAQ](#faq)
9. [Python Implementation Examples](#python-implementation-examples)
10. [Related Documentation](#related-documentation)

---

## Overview: Key Hierarchy

The system uses a two-tier key hierarchy to protect the master key while enabling secure device authentication:

```
Server (Provisioning System)
       │
       │  Master Key (stored here ONLY)
       │
       ├──► Leaf_DiversifyKey(masterKey, Device_A_UID) → Derived Key A
       ├──► Leaf_DiversifyKey(masterKey, Device_B_UID) → Derived Key B
       └──► Leaf_DiversifyKey(masterKey, Device_C_UID) → Derived Key C
                │
                │ Derived keys sent to Mobile Devices during /device/register
                └──► Mobile stores derived key (never the master key)
```

**Critical Security Principle**: The mobile device **never has the master key**. It only receives its pre-computed derived key (also called KMD - Key Material Data) from the credential issuance server.

### Key Terminology

| Term | Description |
|------|-------------|
| **Master Key** | 16-byte root key stored on server and reader |
| **Derived Key (K)** | 16-byte device-specific key computed from master key + device UID |
| **KMD** | Key Material Data - another name for the derived key |
| **DUID** | Device Unique Identifier (8 bytes) |
| **Nonce** | Random 16-byte challenge used in authentication |

---

## Architecture 2: Reader Has Master Key

This documentation assumes **Architecture 2** where the reader stores the master key and derives device keys on-demand.

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│       Server        │     │    Mobile Phone     │     │       Reader        │
│                     │     │     (Central)       │     │    (Peripheral)     │
├─────────────────────┤     ├─────────────────────┤     ├─────────────────────┤
│  Master Key ────────┼──┐  │                     │     │  Master Key         │
│                     │  │  │                     │     │                     │
└─────────────────────┘  │  └─────────────────────┘     └─────────────────────┘
                         │           │                           │
                         │   K = Leaf_DiversifyKey(              │
                         │       masterKey, DUID)                │
                         │           │                           │
                         └──────────►│                           │
                              Stores K (derived key)             │
```

### Architecture 2 Characteristics

| Aspect | Description |
|--------|-------------|
| **Key Storage** | Reader stores master key only |
| **Key Derivation** | On-demand when device presents its DUID |
| **Scalability** | Unlimited devices without storing individual keys |
| **Trade-off** | Higher risk if reader is physically compromised |

---

## Step-by-Step Connection Flow

### Phase 1: Provisioning (One-Time Setup)

Before any BLE connection can occur, the mobile device must be provisioned with its derived key:

```
Server                                    Mobile Phone
   │                                           │
   │  POST /device/register                    │
   │  ◄────────────────────────────────────────│
   │                                           │
   │  Compute: K = Leaf_DiversifyKey(          │
   │              masterKey, deviceUID)        │
   │                                           │
   │  Response: { deviceId, kmd: K, cp }       │
   │  ────────────────────────────────────────►│
   │                                           │
   │                              Store K in encrypted storage
   │                              (AES-256-GCM via Android Keystore)
```

**Key point**: Mobile never sees the master key—only its pre-computed derived key K.

### Phase 2: BLE Connection & Mutual Authentication

```
Mobile Phone (has K)                              Reader (has Master Key)
      │                                                     │
      │  ══════ BLE Connect + Service Discovery ══════      │
      │                                                     │
      │  Generate Ra (16-byte random nonce)                 │
      │                                                     │
      │  ──────── DUID + AUTH_REQ(Ra) ────────────────────► │
      │  [Encrypted: 0xC1 | tag=1 | DUID | Ra]              │
      │                                                     │
      │                         1. Extract DUID from message│
      │                         2. Derive: K = Leaf_DiversifyKey(
      │                                       masterKey, DUID)
      │                         3. Compute: Ra' = AES(K, Ra)│
      │                         4. Generate Rb (reader nonce)
      │                                                     │
      │  ◄─────── AUTH_RSP(Ra') + AUTH_REQ(Rb) ──────────── │
      │                                                     │
      │  Verify: Ra' == AES(K, Ra)?                         │
      │  ✓ YES → Reader proved it can derive K              │
      │          (Reader has valid master key)              │
      │                                                     │
      │  Compute: Rb' = AES(K, Rb)                          │
      │                                                     │
      │  ──────────── AUTH_RSP(Rb') ──────────────────────► │
      │                                                     │
      │                         Verify: Rb' == AES(K, Rb)?  │
      │                         ✓ YES → Device has valid K  │
      │                                                     │
      │  ═══════════ MUTUAL AUTH COMPLETE ═══════════       │
```

### Phase 3: Encrypted Data Transfer

```
Mobile Phone                                      Reader
      │                                                │
      │  Prepare Credential Payload (CP, 372 bytes)    │
      │  Encrypt with K                                │
      │                                                │
      │  ──────────── [Encrypted CP] ────────────────► │
      │                                                │
      │                         Decrypt with K         │
      │                         Extract badge ID/facility code
      │                         Send to access panel (Wiegand/OSDP)
      │                         Panel decides access   │
      │                                                │
      │  ◄─────────── [Encrypted TC] ───────────────── │
      │  (Transaction Certificate, 98 bytes)           │
      │                                                │
      │  ═══════════ DOOR UNLOCKS ═══════════          │
```

---

## Mutual Authentication Protocol

### The 5-State Machine

The LEAF protocol implements a 5-state mutual authentication flow:

```c
typedef enum _leaf_central_status_t {
    central_challenge = 0,     // Initial: send DUID + challenge
    central_authenticated,     // Reader response validated
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

### The Cryptographic "Proof" in Each Direction

**Device proves identity to Reader:**
```
Reader sends Rb → Device returns AES(K, Rb)
Reader verifies by computing AES(K, Rb) itself
Match = Device has correct K for this DUID
```

**Reader proves identity to Device:**
```
Device sends Ra → Reader returns AES(K, Ra)
Device verifies by computing AES(K, Ra) itself
Match = Reader derived correct K from master key
```

Both sides prove they can perform `AES(K, nonce)` without ever transmitting K over the air.

---

## Encrypted Data Transfer

### Credential Payload (CP) Structure - 372 bytes

```c
typedef struct _leaf_cred_payload_t {
    // Tag header: 0xCC when serialized
    unsigned short    length;          // 2 bytes
    leaf_payload_id_t identifier;      // 2 bytes
    unsigned char     dUid[8];         // 8 bytes - Device UID
    unsigned char     token[32];       // 32 bytes - Server token
    unsigned char     value[330];      // 330 bytes - Encrypted badge data
} leaf_cred_payload_t;
```

### Transaction Certificate (TC) Structure - 98 bytes

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

The Transaction Certificate is a cryptographic proof that the transaction occurred, containing:

| Field | Purpose |
|-------|---------|
| `rUid` | Which reader processed the credential |
| `dUid` | Which device presented the credential |
| `token` | Server token (ties back to credential issuance) |
| `identifier` | What type of payload was processed |
| `rfu` | Reserved (could hold timestamp, access decision, etc.) |

**Note**: The access decision is made by the access control panel (via Wiegand/OSDP), not encoded in the TC itself. The TC proves the BLE transaction completed successfully.

---

## Cryptographic Details

### Key Derivation Algorithm

The `Leaf_DiversifyKey` function is based on the **NXP AN10922** standard for symmetric key diversification:

```c
void Leaf_DiversifyKey(
    unsigned char *pDiversifiedKey,   // Output: 16-byte unique device key (K)
    unsigned char *pUid,              // Input: 8-byte device UID
    unsigned char *pBaseKey           // Input: 16-byte master key
);

// Constants:
LEAF_SUBKEY_XOR_VAL = 0x87    // XOR constant for subkey generation (CMAC standard)
LEAF_DIVINPUT_CONST = 0x01    // Diversification input constant
```

### Encryption Algorithms Used

| Purpose | Algorithm | Key Size |
|---------|-----------|----------|
| Challenge-response | AES-128 ECB | 128-bit (16 bytes) |
| BLE message encryption | AES-128 CBC | 128-bit |
| CP value field encryption | AES-128 CBC | 128-bit (KCD key) |
| Mobile key storage | AES-256 GCM | 256-bit |

### BLE Message Format

```
┌─────────┬─────────┬─────────┬─────────┬─────────┬───────────────────┐
│  Byte 0 │  Byte 1 │  Byte 2 │  Byte 3 │  Byte 4 │  Bytes 5..N       │
├─────────┼─────────┼─────────┼─────────┼─────────┼───────────────────┤
│  Start  │   Tag   │ Len Hi  │ Len Lo  │   Seq   │  Value (payload)  │
│ 0x81/C1 │  0x00-7 │         │         │  0-255  │  max 400 bytes    │
└─────────┴─────────┴─────────┴─────────┴─────────┴───────────────────┘
```

| Start Byte | Meaning |
|------------|---------|
| `0x81` | Plaintext message |
| `0xC1` | Encrypted message (AES-128 CBC) |

---

## Security Analysis

### Architecture 2 Security Considerations

| Aspect | Implication |
|--------|-------------|
| **Reader compromise** | ⚠️ Master key exposed → All device keys derivable |
| **Phone compromise** | ✓ Only that device's K exposed |
| **No pre-provisioning needed** | ✓ Reader derives K on-the-fly from any valid DUID |
| **Scalability** | ✓ Unlimited devices without storing individual keys |

### Why This Pattern Works

1. **Reader verifies device**: Reader challenges with Rb → Device must respond with `AES(K, Rb)` → Only works if device has the correct derived key

2. **Device verifies reader**: Device challenges with Ra → Reader must respond with `AES(K, Ra)` → Reader proves it can derive K from master key + DUID

3. **Compromise isolation**: If one phone is compromised, only that device's derived key (K) is exposed. Attacker cannot derive keys for other devices without the master key.

4. **Scalability**: One master key can derive millions of unique device keys using NXP AN10922 standard.

5. **No key transmission**: The derived key K is never sent over BLE—only encrypted challenges and responses.

---

## FAQ

### 1. Is `Leaf_DiversifyKey` Proprietary?

**Short answer**: The algorithm is based on a public standard, but the exact implementation may have proprietary elements.

The function follows **NXP AN10922** (Symmetric Key Diversification), which is a publicly documented standard. The general algorithm is:

1. Create diversification input from device UID
2. Pad/format input to AES block size (16 bytes)
3. Encrypt input with master key using AES-128
4. Result is the diversified key

The constants from the SDK suggest a CMAC-based approach:
- `LEAF_SUBKEY_XOR_VAL = 0x87` - Standard CMAC constant for 128-bit keys
- `LEAF_DIVINPUT_CONST = 0x01` - Diversification input marker

**Replicable?** Yes, using standard cryptographic libraries. See [Python Implementation Examples](#python-implementation-examples).

### 2. What is AES for Nonce Signature?

The challenge-response uses **AES-128 encryption** (not a digital signature):

```
Response = AES-128-Encrypt(Key=K, Plaintext=Nonce)
```

This is standard AES available in any cryptographic library:
- Python: `cryptography` or `pycryptodome`
- JavaScript: `crypto` (Node.js) or Web Crypto API
- Java: `javax.crypto`

### 3. What is a Transaction Certificate (TC)?

**Not just access granted/denied** — it's a cryptographic proof that the transaction occurred.

**Contents:**
- `rUid` (8 bytes): Reader UID - which reader processed the credential
- `dUid` (8 bytes): Device UID - which device presented the credential
- `token` (32 bytes): Server token - ties back to credential issuance
- `identifier` (2 bytes): Payload type that was processed
- `rfu` (48 bytes): Reserved for future use

**Use cases:**
1. **Audit trail** — Mobile can send TC to server as proof of transaction
2. **Verification** — Server can verify the token matches what it issued
3. **Non-repudiation** — Reader's UID proves which physical reader was involved
4. **Debugging** — Confirms the transaction completed successfully

---

## Python Implementation Examples

### Key Diversification (NXP AN10922 Style)

```python
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def diversify_key_an10922(master_key: bytes, uid: bytes) -> bytes:
    """
    NXP AN10922 key diversification (simplified version)

    Args:
        master_key: 16 bytes - the master key
        uid: 8 bytes - device UID

    Returns:
        16-byte diversified key unique to this device
    """
    # Build diversification input (per AN10922)
    # Format: 0x01 || UID || padding to 16 bytes
    div_input = bytes([0x01]) + uid + bytes(16 - 1 - len(uid))

    # AES-128 encrypt the diversification input with master key
    cipher = Cipher(algorithms.AES(master_key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    diversified_key = encryptor.update(div_input) + encryptor.finalize()

    return diversified_key
```

**Note**: The exact LEAF implementation may differ slightly. Verify against actual SDK output.

### Challenge-Response Computation

```python
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

def compute_challenge_response(key: bytes, nonce: bytes) -> bytes:
    """
    Compute AES-128 response to challenge nonce

    Args:
        key: 16-byte diversified key (K)
        nonce: 16-byte random challenge (Ra or Rb)

    Returns:
        16-byte response (Ra' or Rb')
    """
    # AES-128 ECB (single block, no IV needed)
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    response = encryptor.update(nonce) + encryptor.finalize()
    return response
```

### BLE Message Encryption (AES-128 CBC)

```python
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

def encrypt_ble_message(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    """
    AES-128-CBC encryption for BLE messages

    Args:
        key: 16-byte KMD (diversified key)
        iv: 16-byte initialization vector
        plaintext: data to encrypt

    Returns:
        Encrypted ciphertext (padded to 16-byte boundary)
    """
    # Pad to 16-byte boundary (ISO 10126 style: 0x80 then 0x00s)
    pad_len = 16 - (len(plaintext) % 16)
    if pad_len == 0:
        pad_len = 16
    padded = plaintext + bytes([0x80]) + bytes(pad_len - 1)

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def decrypt_ble_message(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """
    AES-128-CBC decryption for BLE messages

    Args:
        key: 16-byte KMD (diversified key)
        iv: 16-byte initialization vector
        ciphertext: encrypted data

    Returns:
        Decrypted plaintext (with padding removed)
    """
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove ISO 10126 padding (find 0x80 marker)
    try:
        padding_start = padded.rindex(0x80)
        return padded[:padding_start]
    except ValueError:
        return padded  # No padding found
```

### Complete Authentication Simulation

```python
import secrets

def simulate_mutual_authentication():
    """
    Simulate the mutual authentication flow between mobile and reader
    """
    # Setup: Both sides have the derived key K
    master_key = secrets.token_bytes(16)
    device_uid = secrets.token_bytes(8)

    # Server derives K and gives to mobile
    K = diversify_key_an10922(master_key, device_uid)

    # Reader will derive K from master_key + device_uid

    print("=== MUTUAL AUTHENTICATION SIMULATION ===\n")

    # Step 1: Mobile generates challenge Ra
    Ra = secrets.token_bytes(16)
    print(f"Mobile generates Ra: {Ra.hex()}")
    print(f"Mobile sends: DUID={device_uid.hex()}, AUTH_REQ(Ra)")

    # Step 2: Reader derives K and responds
    K_reader = diversify_key_an10922(master_key, device_uid)
    Ra_prime = compute_challenge_response(K_reader, Ra)
    Rb = secrets.token_bytes(16)
    print(f"\nReader derives K from master_key + DUID")
    print(f"Reader computes Ra' = AES(K, Ra): {Ra_prime.hex()}")
    print(f"Reader generates Rb: {Rb.hex()}")
    print(f"Reader sends: AUTH_RSP(Ra'), AUTH_REQ(Rb)")

    # Step 3: Mobile verifies reader
    expected_Ra_prime = compute_challenge_response(K, Ra)
    reader_valid = (Ra_prime == expected_Ra_prime)
    print(f"\nMobile verifies Ra': {reader_valid}")

    if reader_valid:
        # Step 4: Mobile responds to reader's challenge
        Rb_prime = compute_challenge_response(K, Rb)
        print(f"Mobile computes Rb' = AES(K, Rb): {Rb_prime.hex()}")
        print(f"Mobile sends: AUTH_RSP(Rb')")

        # Step 5: Reader verifies mobile
        expected_Rb_prime = compute_challenge_response(K_reader, Rb)
        device_valid = (Rb_prime == expected_Rb_prime)
        print(f"\nReader verifies Rb': {device_valid}")

        if device_valid:
            print("\n✓ MUTUAL AUTHENTICATION COMPLETE")
        else:
            print("\n✗ Device authentication failed")
    else:
        print("\n✗ Reader authentication failed")


if __name__ == "__main__":
    simulate_mutual_authentication()
```

### Installation

```bash
pip install cryptography
```

---

## Related Documentation

- [KEY_MANAGEMENT_FAQ.md](KEY_MANAGEMENT_FAQ.md) - Detailed Q&A about master key and diversified key architecture
- [BLE_COMMUNICATION_FLOWS.md](BLE_COMMUNICATION_FLOWS.md) - Complete protocol specifications and message formats
- [WAVELYNX_BLE_SECURITY_MODEL.md](WAVELYNX_BLE_SECURITY_MODEL.md) - Full security architecture documentation

### External References

- [NXP AN10922](https://www.nxp.com/docs/en/application-note/AN10922.pdf) - Symmetric Key Diversification
- [LEAF Community](https://www.leaf-community.com/) - Official LEAF standard documentation

---

*Document created: 2026-02-01*
*Based on technical analysis of Wavelynx LEAF BLE SDK and Architecture 2 (reader with master key)*
