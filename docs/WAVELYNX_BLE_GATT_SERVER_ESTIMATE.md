# WaveLynx BLE GATT Server Implementation Estimate

Technical feasibility assessment for implementing a custom BLE peripheral (reader emulator) that is compatible with the existing WaveLynx LEAF mobile SDKs.

---

> **DISCLAIMER**
>
> This documentation is **tentative** and based entirely on:
> - Reverse-engineering publicly exposed headers and Swift interfaces in the `LeafBle.xcframework`
> - Analysis of the Android SDK (`leafble-4.0.0.aar`) and native library (`libleaflib.so`)
> - Inference from the mobile-side (Central) protocol implementation
>
> **We do not have visibility into:**
> - The reader-side (Peripheral) implementation
> - The actual GATT service/characteristic UUID values (embedded in compiled binary)
> - Internal validation logic within the SDK
> - Undocumented protocol behaviors or edge cases
>
> This estimate assumes **access to the LEAF master key** for key diversification. Without the master key, this implementation is not feasible.
>
> WaveLynx Technologies has not verified this information. Implementation details may differ from what is documented here. Proceed with caution and validate assumptions through real-world testing.
>
> **Last analyzed:** 2026-02-02
> **SDK Version:** LeafBle.xcframework v6.0, leafble-4.0.0.aar

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Prerequisites](#prerequisites)
3. [Architecture Overview](#architecture-overview)
4. [Implementation Requirements](#implementation-requirements)
5. [Difficulty Assessment](#difficulty-assessment)
6. [Phased Implementation Approach](#phased-implementation-approach)
7. [Risk Assessment](#risk-assessment)
8. [Technical Details](#technical-details)
9. [Open Questions](#open-questions)
10. [References](#references)

---

## Executive Summary

### Is This Feasible?

**Yes, with caveats.**

Implementing a custom BLE peripheral that works with the WaveLynx SDK is feasible under the following conditions:

| Condition | Required | Notes |
|-----------|----------|-------|
| Access to LEAF master key | **Yes** | Without this, mutual authentication will always fail |
| BLE peripheral development capability | Yes | ESP32, nRF52, or similar |
| Ability to capture real BLE transactions | Recommended | For protocol validation |
| Tolerance for reverse-engineering work | Yes | Several unknowns require investigation |

### Why Is This Challenging?

The WaveLynx SDK is designed as a **closed system**:
- Mobile app (Central) talks to certified LEAF readers (Peripheral)
- Both sides share cryptographic secrets managed by WaveLynx
- The SDK actively validates reader responses

Inserting a custom peripheral requires replicating the reader's behavior precisely, including cryptographic operations that are not fully documented.

### Effort Estimate

| Phase | Effort | Confidence |
|-------|--------|------------|
| UUID extraction | 1-2 hours | High |
| Key diversification implementation | 2-4 hours | Medium-High |
| Protocol capture & analysis | 2-4 hours | High |
| Core peripheral implementation | 1-2 weeks | Medium |
| Testing & debugging | 1-2 weeks | Low (unknowns) |
| **Total** | **3-5 weeks** | Medium |

---

## Prerequisites

### Required

1. **LEAF Master Key**
   - The master key used to derive per-device diversified keys
   - Without this, the SDK will reject all authentication attempts
   - Key diversification: `K = Leaf_DiversifyKey(masterKey, deviceUID)`

2. **BLE Development Platform**
   - Hardware capable of BLE peripheral role (GATT server)
   - Recommended: ESP32, nRF52840, or Raspberry Pi with BLE adapter
   - Must support: custom service/characteristic UUIDs, notifications

3. **Cryptographic Implementation**
   - AES-128 CBC encryption/decryption
   - Secure random number generation
   - Key diversification algorithm (likely NXP AN10922)

### Recommended

4. **BLE Sniffer**
   - nRF52840 dongle + Wireshark + nRF Sniffer plugin
   - Used to capture real transactions for protocol validation

5. **Real LEAF Reader (for reference)**
   - Capture ground-truth BLE transactions
   - Validate your implementation against known-good behavior

6. **iOS/Android Device with WaveLynx App**
   - Test your custom peripheral against the real SDK
   - Debug connectivity and protocol issues

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Current WaveLynx System                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐         BLE          ┌──────────────────┐             │
│  │   Mobile App     │◄────────────────────►│   LEAF Reader    │             │
│  │   (Central)      │                      │   (Peripheral)   │             │
│  │                  │                      │                  │             │
│  │  - WaveLynx SDK  │                      │  - Proprietary   │             │
│  │  - LeafBle.xcf   │                      │  - Has master key│             │
│  │  - leafble.aar   │                      │  - Certified HW  │             │
│  └──────────────────┘                      └──────────────────┘             │
│           │                                          │                       │
│           │                                          │                       │
│           ▼                                          ▼                       │
│  ┌──────────────────┐                      ┌──────────────────┐             │
│  │ WaveLynx Server  │                      │  Access Control  │             │
│  │ (Credential Mgmt)│                      │     Panel        │             │
│  └──────────────────┘                      └──────────────────┘             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        Target System (Custom Peripheral)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐         BLE          ┌──────────────────┐             │
│  │   Mobile App     │◄────────────────────►│ Custom Peripheral│             │
│  │   (Central)      │                      │ (Reader Emulator)│             │
│  │                  │                      │                  │             │
│  │  - WaveLynx SDK  │                      │  - Your code     │             │
│  │  - Unmodified    │                      │  - Has master key│             │
│  │                  │                      │  - Implements    │             │
│  │                  │                      │    LEAF protocol │             │
│  └──────────────────┘                      └──────────────────┘             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### GATT Server Structure

The custom peripheral must expose a GATT profile matching the LEAF reader:

```
Custom Peripheral GATT Server
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  Service: BLE_CRED_SVC_UUID                                     │
│  (UUID must be extracted from SDK binary or BLE capture)        │
│                                                                 │
│  └── Characteristic: DATA_TRANSFER_CHRC_UUID                    │
│      │                                                          │
│      ├── Properties:                                            │
│      │   ├── Write Without Response  ← Receive from mobile      │
│      │   └── Notify                  ← Send to mobile           │
│      │                                                          │
│      └── Descriptor: CCCD (0x2902)                              │
│          └── Enable notifications                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Requirements

### 1. GATT Server

| Requirement | Details |
|-------------|---------|
| Service UUID | `BLE_CRED_SVC_UUID` - must extract from binary |
| Characteristic UUID | `DATA_TRANSFER_CHRC_UUID` - must extract from binary |
| Characteristic Properties | Write Without Response, Notify |
| Advertising | Include service UUID; optionally use name prefix "ETHS" |
| CCCD | Standard 0x2902 descriptor for notification enable |

### 2. Key Management

```c
// Input: Master key (16 bytes) + Device UID (8 bytes)
// Output: Diversified key (16 bytes)

void Leaf_DiversifyKey(
    unsigned char *pDiversifiedKey,   // Output: 16-byte unique device key
    unsigned char *pUid,              // Input: 8-byte device UID from mobile
    unsigned char *pBaseKey           // Input: 16-byte master key
);

// Constants from SDK headers:
#define LEAF_SUBKEY_XOR_VAL    0x87
#define LEAF_DIVINPUT_CONST    0x01
```

The diversification algorithm is likely based on **NXP AN10922** (Symmetric Key Diversification). Implementation must be verified against known values.

### 3. Protocol State Machine (Reader Side)

```
                              ┌──────────────────┐
                              │   Advertising    │
                              └────────┬─────────┘
                                       │
                                BLE Connection
                                       │
                                       ▼
                    ┌──────────────────────────────────┐
                    │   State 0: Wait for DUID         │
                    │  ─────────────────────────────── │
                    │  Receive: DUID + AUTH_REQ(Ra)    │
                    │  Action: Extract device UID      │
                    │          Derive K from UID       │
                    └────────────────┬─────────────────┘
                                     │
                              DUID received
                                     │
                                     ▼
                    ┌──────────────────────────────────┐
                    │   State 1: Send Challenge        │
                    │  ─────────────────────────────── │
                    │  Action: Compute Rb' = f(K, Ra)  │
                    │          Generate random Rb      │
                    │  Send: AUTH_RSP(Rb') + AUTH_REQ(Rb)│
                    └────────────────┬─────────────────┘
                                     │
                              Response sent
                                     │
                                     ▼
                    ┌──────────────────────────────────┐
                    │   State 2: Validate Device       │
                    │  ─────────────────────────────── │
                    │  Receive: AUTH_RSP(Ra')          │
                    │  Action: Verify Ra' = f(K, Rb)   │
                    │  If invalid: Send failure, abort │
                    └────────────────┬─────────────────┘
                                     │
                              Validation passed
                                     │
                                     ▼
                    ┌──────────────────────────────────┐
                    │   State 3: Receive Credential    │
                    │  ─────────────────────────────── │
                    │  Receive: CP (372 bytes)         │
                    │  Action: Decrypt CP value        │
                    │          Validate structure      │
                    │          Process credential      │
                    └────────────────┬─────────────────┘
                                     │
                              CP processed
                                     │
                                     ▼
                    ┌──────────────────────────────────┐
                    │   State 4: Send TC               │
                    │  ─────────────────────────────── │
                    │  Action: Generate TC (98 bytes)  │
                    │  Send: TC                        │
                    │  Result: Transaction complete    │
                    └──────────────────────────────────┘
```

### 4. Message Format

All messages follow the `leaf_ble_msg_t` structure:

```
┌─────────┬─────────┬─────────┬─────────┬─────────┬───────────────────┐
│  Byte 0 │  Byte 1 │  Byte 2 │  Byte 3 │  Byte 4 │  Bytes 5..N       │
├─────────┼─────────┼─────────┼─────────┼─────────┼───────────────────┤
│  Start  │   Tag   │ Len Hi  │ Len Lo  │   Seq   │  Value (payload)  │
│ 0x81/C1 │  0x00-7 │         │         │  0-255  │  max 400 bytes    │
└─────────┴─────────┴─────────┴─────────┴─────────┴───────────────────┘

Start byte:
  0x81 = Plaintext message
  0xC1 = Encrypted message (AES-128 CBC)

Tags:
  0 = leaf_tag_rsp      (response)
  1 = leaf_tag_duid     (device UID)
  2 = leaf_tag_authreq  (auth request/challenge)
  3 = leaf_tag_authrsp  (auth response)
  4 = leaf_tag_cp       (credential payload)
  5 = leaf_tag_tc       (transaction certificate)
  6 = leaf_tag_meta     (metadata)
  7 = leaf_tag_ivreset  (reset IV)
```

### 5. Cryptographic Operations

| Operation | Algorithm | Key Size | Block Size |
|-----------|-----------|----------|------------|
| Message encryption | AES-128 CBC | 128-bit | 16 bytes |
| Key diversification | AES-based (AN10922) | 128-bit | 16 bytes |
| Challenge-response | AES-128 (likely) | 128-bit | 16 bytes |

```c
// AES-128 CBC (from SDK)
short AesEncryptCbc(
    unsigned char *data,       // Data buffer (modified in-place)
    unsigned short length,     // Must be multiple of 16
    unsigned char key[16],     // 128-bit AES key
    unsigned char iv[16]       // 128-bit initialization vector
);

short AesDecryptCbc(
    unsigned char *data,
    unsigned short length,
    unsigned char key[16],
    unsigned char iv[16]
);

// Padding: ISO 10126 style
// Append 0x80, then 0x00 bytes until 16-byte aligned
```

---

## Difficulty Assessment

### Component Breakdown

| Component | Difficulty | Effort | Confidence | Notes |
|-----------|------------|--------|------------|-------|
| GATT server setup | Easy | 2-4 hrs | High | Standard BLE peripheral development |
| UUID extraction | Easy | 1-2 hrs | High | BLE sniffer or binary analysis |
| AES-128 CBC | Easy | 1-2 hrs | High | Standard algorithm, many libraries |
| Message parsing/serialization | Easy | 2-4 hrs | High | Fully documented in headers |
| Key diversification | Medium | 2-4 hrs | Medium-High | Likely NXP AN10922, verify with test |
| AUTH challenge-response | Medium | 4-8 hrs | Medium | Need to verify: `AES(K, nonce)` or variant |
| TC generation | Unknown | 4-16 hrs | Low | Structure known, validation logic unknown |
| Integration testing | Variable | 1-2 wks | Low | Depends on unknown edge cases |

### What We Know vs. Don't Know

**Fully Documented (from headers):**
- Message structure (`leaf_ble_msg_t`)
- Message tags and their meanings
- Credential Payload structure (372 bytes)
- Transaction Certificate structure (98 bytes)
- Key diversification constants
- AES block size and padding

**Partially Known (inference required):**
- Key diversification algorithm (likely AN10922)
- Challenge-response computation (likely `AES(K, nonce)`)
- Protocol timing expectations

**Unknown (reverse engineering required):**
- Actual GATT UUIDs
- Exact key diversification implementation
- TC validation requirements (is `rfu[48]` actually a MAC?)
- Error handling and recovery flows
- SDK-side validation logic

---

## Phased Implementation Approach

### Phase 1: UUID Extraction (1-2 hours)

**Objective:** Obtain the actual service and characteristic UUIDs.

**Option A: BLE Sniffer (Recommended)**
```
1. Set up nRF52840 dongle + Wireshark + nRF Sniffer
2. Initiate a real transaction: Mobile App ↔ LEAF Reader
3. Capture the BLE advertisement and GATT discovery
4. Extract UUIDs from the capture
```

**Option B: Runtime Hooking**
```
1. Use Frida on jailbroken iOS or rooted Android
2. Hook CoreBluetooth/Android Bluetooth APIs
3. Log CBUUID/UUID values when SDK calls them
```

**Option C: Binary Analysis**
```
1. Extract LeafBle binary from xcframework
2. Use strings/disassembler to find UUID patterns
3. Look for 128-bit UUID constants or 16-bit short UUIDs
```

**Deliverable:** Document with actual UUID values.

### Phase 2: Key Diversification Verification (2-4 hours)

**Objective:** Confirm the key diversification algorithm matches NXP AN10922.

```python
# Pseudocode for verification

def test_diversification():
    # If you have a provisioned credential, you have:
    # - Device UID (from credential)
    # - Diversified key (KMD from server response)
    # - Master key (provided)

    computed_key = nxp_an10922_diversify(master_key, device_uid)
    assert computed_key == known_kmd, "Algorithm mismatch!"
```

**Deliverable:** Verified key diversification implementation.

### Phase 3: Protocol Capture & Analysis (2-4 hours)

**Objective:** Capture a real transaction as ground truth.

```
Mobile App  ←──BLE Sniffer──→  Real LEAF Reader

Capture and document:
1. DUID + AUTH_REQ packet (bytes, decrypted if possible)
2. AUTH_RSP + AUTH_REQ response
3. AUTH_RSP from mobile
4. CP packet (372 bytes)
5. TC packet (98 bytes)
```

**Analysis:**
- Verify message format matches `leaf_ble_msg_t`
- Extract challenge-response values to verify algorithm
- Document timing between messages

**Deliverable:** Annotated packet capture with protocol analysis.

### Phase 4: Minimal Peripheral Implementation (1-2 weeks)

**Objective:** Build a working GATT server that can complete a transaction.

**Step 4.1: GATT Server Skeleton**
```
- Create BLE peripheral with correct UUIDs
- Advertise service
- Accept connections
- Log all received writes
- Send dummy notifications
- Verify: Mobile app connects and discovers service
```

**Step 4.2: Message Parsing**
```
- Parse incoming leaf_ble_msg_t
- Extract tag, length, sequence, value
- Decrypt if start byte is 0xC1
- Verify: Can parse DUID + AUTH_REQ from mobile
```

**Step 4.3: Authentication Flow**
```
- Extract device UID from first message
- Derive diversified key K
- Compute AUTH_RSP to mobile's challenge
- Generate own challenge
- Send AUTH_RSP + AUTH_REQ
- Receive and validate mobile's AUTH_RSP
- Verify: Mutual authentication succeeds (mobile shows "authenticated")
```

**Step 4.4: Credential Processing**
```
- Receive CP (may be fragmented)
- Decrypt CP value field
- Parse credential data
- Verify: Can receive and decrypt CP
```

**Step 4.5: Transaction Certificate**
```
- Generate TC with correct structure
- Populate rUid, dUid, token from CP
- Send TC
- Verify: Mobile shows transaction complete
```

**Deliverable:** Working peripheral that completes full transaction.

### Phase 5: Testing & Hardening (1-2 weeks)

**Objective:** Validate against edge cases and ensure reliability.

```
Test scenarios:
- Multiple consecutive transactions
- Transaction timeout/retry
- Invalid credentials (should fail gracefully)
- Key rotation scenarios
- Different credential types (ACCESS vs KEYSET)
- iOS and Android SDKs
- Background/foreground app states
```

**Deliverable:** Test report documenting compatibility.

---

## Risk Assessment

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Key diversification algorithm differs from AN10922 | Low | High | Verify with known credential before full implementation |
| AUTH challenge-response uses unknown function | Medium | High | Capture real transaction, analyze mathematically |
| TC requires signature/MAC we can't generate | Medium | High | Analyze TC from real transactions for patterns |
| SDK validates undocumented fields | Medium | Medium | Byte-for-byte comparison with real reader responses |
| Timing requirements not met | Low | Medium | Profile real reader, add configurable delays |

### Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| SDK update breaks compatibility | Medium | High | Pin SDK version, monitor WaveLynx releases |
| WaveLynx adds anti-tampering measures | Low | High | May require ongoing reverse engineering |
| Edge cases cause random failures | Medium | Medium | Extensive testing, logging, graceful error handling |
| Performance issues under load | Low | Low | Optimize BLE parameters, test with multiple devices |

### Risk Summary Matrix

```
                        Impact
                 Low    Medium    High
            ┌─────────┬─────────┬─────────┐
      High  │         │         │         │
            ├─────────┼─────────┼─────────┤
Likelihood  │         │ SDK     │ Unknown │
    Medium  │         │ updates │ TC/auth │
            ├─────────┼─────────┼─────────┤
      Low   │ Perf    │ Timing  │ Key div │
            └─────────┴─────────┴─────────┘
```

---

## Technical Details

### Expected Message Exchange

```
Mobile Device (Central)                    Custom Peripheral (Reader)
      │                                               │
      │  ──── Scan for BLE_CRED_SVC_UUID ──────────► │
      │  ◄──── Advertisement ──────────────────────── │
      │                                               │
      │  ──── Connect ─────────────────────────────► │
      │  ◄──── Connected ──────────────────────────── │
      │                                               │
      │  ──── Discover Services ───────────────────► │
      │  ◄──── BLE_CRED_SVC_UUID ──────────────────── │
      │                                               │
      │  ──── Discover Characteristics ────────────► │
      │  ◄──── DATA_TRANSFER_CHRC_UUID ────────────── │
      │                                               │
      │  ──── Write CCCD (0x0001) ─────────────────► │
      │  ◄──── Success ────────────────────────────── │
      │                                               │
      │  ══════════ LEAF Protocol Begins ══════════  │
      │                                               │
      │  ──── Write: DUID + AUTH_REQ ──────────────► │
      │       [C1 01 XX XX SS <encrypted>]           │
      │                                               │
      │  ◄──── Notify: AUTH_RSP + AUTH_REQ ───────── │
      │       [C1 03 XX XX SS <encrypted>]           │
      │                                               │
      │  ──── Write: AUTH_RSP ─────────────────────► │
      │       [C1 03 XX XX SS <encrypted>]           │
      │                                               │
      │  ──── Write: CP (372 bytes) ───────────────► │
      │       [C1 04 XX XX SS <encrypted>]           │
      │       (may be fragmented)                    │
      │                                               │
      │  ◄──── Notify: TC (98 bytes) ──────────────── │
      │       [C1 05 XX XX SS <encrypted>]           │
      │                                               │
      │  ══════════ Transaction Complete ══════════  │
      │                                               │
```

### Credential Payload (CP) Structure

```
Tag: 0xCC (when serialized)
Total size: 372 bytes

┌──────────────────────────────────────────────────────────────────┐
│  Bytes 0-1   │  Length (big-endian)                              │
├──────────────┼───────────────────────────────────────────────────┤
│  Bytes 2-3   │  Payload Identifier (leaf_payload_id_t)           │
│              │    0 = keyset, 1 = accesscontrol,                 │
│              │    2 = configfile, 3 = passthrough                │
├──────────────┼───────────────────────────────────────────────────┤
│  Bytes 4-11  │  Device UID (8 bytes)                             │
├──────────────┼───────────────────────────────────────────────────┤
│  Bytes 12-43 │  Server Token (32 bytes)                          │
├──────────────┼───────────────────────────────────────────────────┤
│  Bytes 44-373│  Value (330 bytes) - Encrypted credential data    │
│              │  Contains: badge ID, facility code, etc.          │
└──────────────┴───────────────────────────────────────────────────┘
```

### Transaction Certificate (TC) Structure

```
Tag: 0xCE (when serialized)
Total size: 98 bytes

┌──────────────────────────────────────────────────────────────────┐
│  Bytes 0-1   │  Length (big-endian)                              │
├──────────────┼───────────────────────────────────────────────────┤
│  Bytes 2-3   │  Payload Identifier (echoed from CP)              │
├──────────────┼───────────────────────────────────────────────────┤
│  Bytes 4-11  │  Reader UID (8 bytes) - Your peripheral's ID      │
├──────────────┼───────────────────────────────────────────────────┤
│  Bytes 12-19 │  Device UID (8 bytes) - Echoed from CP            │
├──────────────┼───────────────────────────────────────────────────┤
│  Bytes 20-51 │  Server Token (32 bytes) - Echoed from CP         │
├──────────────┼───────────────────────────────────────────────────┤
│  Bytes 52-99 │  RFU (48 bytes) - Reserved for future use         │
│              │  ⚠️ Unknown if this contains MAC/signature        │
└──────────────┴───────────────────────────────────────────────────┘
```

---

## Open Questions

The following questions must be answered through reverse engineering or experimentation:

### Critical (Blocking)

1. **What are the actual GATT UUIDs?**
   - `BLE_CRED_SVC_UUID` = ?
   - `DATA_TRANSFER_CHRC_UUID` = ?
   - Method: BLE capture or binary analysis

2. **What is the exact key diversification algorithm?**
   - Likely NXP AN10922, but must verify
   - Method: Test with known credential

3. **What is the challenge-response function?**
   - Is it `AES_Encrypt(K, nonce)`?
   - Or `AES_Encrypt(K, nonce XOR constant)`?
   - Or CMAC-based?
   - Method: Capture real transaction, analyze mathematically

### Important (May Cause Issues)

4. **Is the TC `rfu` field actually unused?**
   - Could contain a MAC or signature
   - Method: Analyze multiple TCs for patterns

5. **What sequence number behavior is expected?**
   - Does reader track sequence?
   - What happens on mismatch?
   - Method: Test with intentional mismatches

6. **How does multi-packet fragmentation work on reader side?**
   - CP (372 bytes) may exceed MTU
   - How does reader signal ready for next fragment?
   - Method: Capture fragmented transaction

### Nice to Know

7. **What error responses does the SDK expect?**
   - `leaf_rsp_fail`, `leaf_rsp_invalid`, etc.
   - Method: Test error scenarios

8. **What are the timing constraints?**
   - Max time between messages?
   - Method: Profile real reader

---

## References

### SDK Documentation

| Document | Description |
|----------|-------------|
| [IOS_BLE_GATT_SERVER_SPECIFICS.md](./IOS_BLE_GATT_SERVER_SPECIFICS.md) | iOS SDK GATT architecture analysis |
| [BLE_COMMUNICATION_FLOWS.md](./BLE_COMMUNICATION_FLOWS.md) | Detailed protocol flows |
| [WAVELYNX_BLE_SECURITY_MODEL.md](./WAVELYNX_BLE_SECURITY_MODEL.md) | Security architecture |
| [KEY_MANAGEMENT_FAQ.md](./KEY_MANAGEMENT_FAQ.md) | Key rotation and management |

### SDK Source Files

| File | Path |
|------|------|
| LeafCore.h | `ios-sdk/LeafBle.xcframework/.../Headers/LeafCore.h` |
| LeafCentral.h | `ios-sdk/LeafBle.xcframework/.../Headers/LeafCentral.h` |
| Aes.h | `ios-sdk/LeafBle.xcframework/.../Headers/Aes.h` |
| Swift Interface | `ios-sdk/LeafBle.xcframework/.../LeafBle.swiftmodule/*.swiftinterface` |

### External Resources

| Resource | URL |
|----------|-----|
| NXP AN10922 (Key Diversification) | https://www.nxp.com/docs/en/application-note/AN10922.pdf |
| Bluetooth GATT Specification | https://www.bluetooth.com/specifications/gatt/ |
| nRF Sniffer for Bluetooth LE | https://www.nordicsemi.com/Products/Development-tools/nRF-Sniffer-for-Bluetooth-LE |
| LEAF Community | https://www.leaf-community.com/ |
| WaveLynx Support | https://support.wavelynx.com/ |

---

*Document generated from technical analysis and feasibility assessment. This is tentative documentation based on publicly available information and has not been verified by WaveLynx Technologies.*
