# Key Management FAQ

This document answers common questions about the master key and diversified key architecture in the Wavelynx BLE credential system.

---

## 1. Why Do We Need a Master Key?

The master key provides:
- **Centralized Key Management**: A single cryptographic root for deriving unique credentials for millions of devices
- **Scalability**: Generate unlimited unique device keys without storing individual keys per device
- **Compromise Isolation**: If one device is compromised, only that device's derived key is exposed, not the master key
- **Security**: The master key never leaves the server, maintaining a secure cryptographic root

Reference: [WAVELYNX_BLE_SECURITY_MODEL.md](WAVELYNX_BLE_SECURITY_MODEL.md)

---

## 2. What Are All the Places Where the Master Key Is Stored?

The master key is stored in the following locations:

### Always Has Master Key

1. **Wavelynx Server** (`nyx.wavelynxtech.com`)
   - Used by the secure issuance (LEAF Si) infrastructure
   - Accessed during `/device/register` and `/device/refresh` endpoints

2. **Custom/External Server** (`192.168.86.46:8080`)
   - Alternative server implementation for enterprise deployments

### May Have Master Key (Architecture Dependent)

3. **LEAF Readers** (depends on deployment architecture)
   - **Architecture 1**: Readers store only pre-provisioned diversified keys for authorized devices
   - **Architecture 2**: Readers store the master key and derive diversified keys on-demand from device UIDs
   - **Hybrid**: Some combination of both approaches

   The specific reader architecture depends on the access control system vendor configuration.

### NEVER Has Master Key

4. **Mobile Devices** (Android/iOS)
   - The master key is explicitly NOT stored on Android or iOS devices
   - Only diversified keys (derived from the master key) are stored on mobile devices

**Critical Security Principle**: "The master key is never transmitted or stored on mobile devices"

**Security Trade-off**: Reader compromise could expose stored diversified keys (Architecture 1) or the master key itself (Architecture 2). Consult with Wavelynx or your access control system vendor for specifics on reader key management in your deployment.

---

## 3. How Is the Master Key Set on the Devices?

**The master key is NOT set on devices.** Instead:

### Server-Side Derivation

The server derives a unique **diversified key** per device using:
```
Diversified Key = Leaf_DiversifyKey(Master Key, Device UID)
```

### Transmission to Device

- Only the **diversified key (KMD)** is sent to the device, never the master key
- Sent via `/device/register` and `/device/refresh` API endpoints

### Storage on Android Device

Stored in encrypted SharedPreferences using AES-256-GCM encryption.

Key storage locations in `Credential.kt`:
- `ACCESS_KMD_KEY` - Diversified key for access (primary)
- `ACCESS_CP_KEY` - Encrypted credential payload
- `KEYSET_KMD_KEY` - Backup diversified key (for rotation)
- `KEYSET_CP_KEY` - Backup credential payload

All keys are protected by Android Keystore.

**Reference Files**:
- `app/src/main/java/com/wavelynx/nyx/ble/userdatastore/Credential.kt`
- `app/src/main/java/com/wavelynx/nyx/ble/utilities/SecureStore.kt`

---

## 4. If We Have a Master Key, Why Do We Need Diversified Keys?

Diversified keys provide critical security benefits:

| Aspect | Master Key | Diversified Key |
|--------|-----------|-----------------|
| **Storage** | Server only | Device-specific |
| **Uniqueness** | Shared globally | Unique per device |
| **Compromise Impact** | ALL credentials exposed | Only that device compromised |
| **Use Case** | Server-side key generation | Device authentication |
| **Transmission** | Never transmitted | Derived per-device |

### Two-Tier Hierarchy for Defense-in-Depth

```
Master Key (Server)
    ↓
    └─→ Leaf_DiversifyKey(masterKey, deviceUID)
        ├─→ Device A: Unique Key A
        ├─→ Device B: Unique Key B
        └─→ Device C: Unique Key C
```

This follows the **NXP AN10922 standard** for key diversification.

### Key Security Principle

From the documentation:
> "Key diversification is a cryptographic technique where a **single master key** is used to derive **unique keys for each device/credential**"

This approach provides:
- **Scalability**: One master key can derive millions of unique device keys
- **Security**: Compromising one device doesn't expose other devices
- **Manageability**: Central key management without distributing the master key

---

## 5. What Is the Purpose of the Diversified Keys?

Diversified keys serve multiple critical purposes:

### A. Device Authentication (Primary Purpose)

- Used in mutual authentication between mobile device and LEAF reader
- Both sides compute: `Response = AES(K, Challenge)` to prove identity
- The diversified key `K` is used for mutual authentication

**How Each Component Gets K**:
- **Mobile Device**: Receives pre-computed `K` from server during registration (never computes it)
- **Reader**: Either has `K` pre-provisioned OR computes `K = Leaf_DiversifyKey(masterKey, deviceUID)` on-demand
- **Server**: Computes `K = Leaf_DiversifyKey(masterKey, deviceUID)` during credential issuance

**Authentication Flow**:
```
Device                                              Reader
   │
   │  Generate random nonce (Ra)
   │
   │  ─────────── DUID + AUTH_REQ(Ra) ─────────→
   │
   │                    Reader obtains K for this deviceUID:
   │                    - Option 1: Lookup pre-provisioned K
   │                    - Option 2: Compute K = Leaf_DiversifyKey(masterKey, deviceUID)
   │
   │                    Reader computes: Rb' = AES(K, Ra)
   │
   │  ◄──────── AUTH_RSP(Rb') + AUTH_REQ(Rb) ────
   │
   │  Device uses stored K
   │  Verify: Rb' == expected (reader is authentic)
   │  Compute: Ra' = AES(K, Rb)
   │
   │  ─────────── AUTH_RSP(Ra') ─────────────────→
   │
   │                    Reader verifies Ra' (device is authentic)
   │
   │  ◄──── MUTUAL AUTHENTICATION COMPLETE ─────
```

**Important Note**: The mobile device never computes `K` - it only uses the pre-computed diversified key received from the server during registration.

Reference: [BLE_COMMUNICATION_FLOWS.md](BLE_COMMUNICATION_FLOWS.md)

### B. Message Encryption

- Also called **KMD (Key Material Data)**
- Encrypts all BLE protocol messages using AES-128 CBC
- Ensures only authorized devices and readers can communicate

### C. Credential Protection

- Used alongside KCD (Key for Credential Data) to encrypt credential payloads
- Prevents unauthorized access to badge data and facility codes

### D. Key Rotation Support

- Supports two keyset payloads: ACCESS and KEYSET
- Allows seamless key rotation without service interruption
- Enables fallback mechanism when keys are rotated

---

## 6. Where Are the Diversified Keys Stored?

### On Android Devices

Diversified keys are stored in **encrypted SharedPreferences** with multiple layers of security.

#### Storage Locations

**Access Payload (Primary/Current Keys)**:
- Key: `"com.wavelynxtech.nyx.ble.accesskmd"`
- Value: 16-byte diversified key (encrypted)
- Location: `Credential.kt:37`

**Keyset Payload (Backup/Rotation Keys)**:
- Key: `"com.wavelynxtech.nyx.ble.keysetkmd"`
- Value: 16-byte diversified key (encrypted)
- Purpose: Backup for key rotation scenarios

#### Encryption Layers

**1. Android Keystore Level** (`SecureStore.kt`):
- AES-256-GCM encryption
- Key alias: `"com.wavelynx.nyx.ble.securestore.key"`
- Purpose: `PURPOSE_ENCRYPT | PURPOSE_DECRYPT`

**2. Cryptographic Implementation** (`Crypto.kt`):
```kotlin
private const val AES_MODE_M_OR_GREATER = "AES/GCM/NoPadding"
val NULL_GCM_IV = byteArrayOf(0,0,0,0,0,0,0,0,0,0,0,0)  // 12-byte IV
```

**3. NFC Service Access**:
- Credentials stored **without user info requirement**
- Allows NFC service to access keys even when app is not running
- Comment from code: "they must be able to be accessed outside of the main application by the NFC service"

#### Code Example from Credential.kt

```kotlin
// Credentials saved without user info requirement (accessible to NFC service)
secureStore.saveBytes(DEVICE_ID_KEY, deviceId ?: ByteArray(0), false)
secureStore.saveBytes(ACCESS_KMD_KEY, accessKmd ?: ByteArray(0), false)
secureStore.saveBytes(KEYSET_KMD_KEY, keysetKmd ?: ByteArray(0), false)

// Loaded without user info requirement
deviceId = secureStore.loadBytes(DEVICE_ID_KEY, false) ?: ByteArray(0)
accessKmd = secureStore.loadBytes(ACCESS_KMD_KEY, false) ?: ByteArray(0)
keysetKmd = secureStore.loadBytes(KEYSET_KMD_KEY, false) ?: ByteArray(0)
```

### On iOS Devices

While not in this Android codebase, the iOS SDK uses similar storage:
- iOS Keychain (equivalent of Android Keystore)
- Same KMD structure for diversified keys

**Reference Files**:
- `app/src/main/java/com/wavelynx/nyx/ble/userdatastore/Credential.kt`
- `app/src/main/java/com/wavelynx/nyx/ble/utilities/SecureStore.kt`
- `app/src/main/java/com/wavelynx/nyx/ble/utilities/Crypto.kt`

---

## Summary Table

| Aspect | Details |
|--------|---------|
| **Master Key Location** | Server (always), Readers (architecture dependent) |
| **Master Key on Mobile Devices?** | ❌ Never |
| **Master Key on Readers?** | ⚠️ Depends on architecture (see Question 2) |
| **How Keys Set on Mobile Devices** | Via `/device/register` and `/device/refresh` endpoints as pre-computed diversified KMD |
| **Diversified Key Storage (Mobile)** | Android Secure SharedPreferences (AES-256-GCM encrypted) |
| **Derivation Method** | `Leaf_DiversifyKey(masterKey, deviceUID)` per NXP AN10922 |
| **Who Derives Keys** | Server (for mobile devices), Readers (if using Architecture 2) |
| **Diversified Key Purpose** | Authentication, message encryption, credential protection, key rotation |
| **Key Rotation** | ACCESS + KEYSET payloads for seamless rotation |
| **Security Standard** | NXP AN10922 key diversification |

---

## Architecture Overview

The system follows a **defense-in-depth** security model:

```
┌──────────────────────────────────────────────────────────────┐
│  Wavelynx Server / Custom Server                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Master Key                                            │  │
│  │  - Always stored on server                            │  │
│  │  - Used to derive device-specific keys                │  │
│  │  - May also be provisioned to readers (arch dependent)│  │
│  └────────────────────────────────────────────────────────┘  │
│                         │                                     │
│                         ▼                                     │
│          Leaf_DiversifyKey(masterKey, deviceUID)             │
│                         │                                     │
└─────────────────────────┼─────────────────────────────────────┘
                          │
         ┌────────────────┼──────────────────┐
         │                │                  │
         ▼                ▼                  ▼
    Device A         Device B          Device C
    ┌─────────┐      ┌─────────┐      ┌─────────┐
    │ Key A   │      │ Key B   │      │ Key C   │
    │ (stored │      │ (stored │      │ (stored │
    │ AES-256 │      │ AES-256 │      │ AES-256 │
    │ -GCM)   │      │ -GCM)   │      │ -GCM)   │
    └─────────┘      └─────────┘      └─────────┘
         │                │                  │
         │                │                  │
         └────────────────┼──────────────────┘
                          │
                          ▼
               ┌──────────────────────┐
               │  LEAF Readers        │
               │                      │
               │ Architecture 1:      │
               │ - Store Keys A,B,C   │
               │                      │
               │ Architecture 2:      │
               │ - Store Master Key   │
               │ - Derive keys on-fly │
               └──────────────────────┘
```

### Key Security Benefits

1. **Master key protected on mobile devices**: Never transmitted to or stored on mobile devices
2. **Limited blast radius**: Compromising one mobile device doesn't expose other devices' keys
3. **Scalable**: Millions of unique device keys derived from one master key
4. **Manageable**: Central key management and rotation capabilities
5. **Standard-compliant**: Follows NXP AN10922 industry standard

### Security Considerations

**Reader Security**: Depending on the architecture, readers may store:
- **Architecture 1**: Only diversified keys for authorized devices (limited exposure if compromised)
- **Architecture 2**: The master key itself (full system compromise if reader is compromised)

Physical security of readers is critical, especially in Architecture 2 deployments. Consult with Wavelynx or your access control vendor about the specific architecture and security measures in your deployment.

---

## Clarification: Does the Mobile Device Need the Master Key?

**No.** This is a common point of confusion when looking at the authentication protocol.

The authentication protocol states: `K = Leaf_DiversifyKey(masterKey, deviceUID)`

However:
- **Mobile Device**: Receives the **already-computed K** from the server and stores it. Never computes or needs the master key.
- **Reader**: Either has K pre-provisioned OR computes K from the master key + device UID
- **Server**: Computes K during credential issuance using the master key

See [BLE_COMMUNICATION_FLOWS.md](BLE_COMMUNICATION_FLOWS.md) lines 374-380 for explicit documentation of reader architecture options.

---

## Related Documentation

- [WAVELYNX_BLE_SECURITY_MODEL.md](WAVELYNX_BLE_SECURITY_MODEL.md) - Complete security architecture
- [BLE_COMMUNICATION_FLOWS.md](BLE_COMMUNICATION_FLOWS.md) - Protocol flows and authentication (see lines 374-380 for reader key management)
- `app/src/main/java/com/wavelynx/nyx/ble/userdatastore/Credential.kt` - Key storage implementation
- `app/src/main/java/com/wavelynx/nyx/ble/utilities/SecureStore.kt` - Encrypted storage layer
- `app/src/main/java/com/wavelynx/nyx/ble/utilities/Crypto.kt` - Cryptographic operations

---

*Document generated: 2026-01-30*
*Last updated: 2026-01-30 - Clarified reader master key storage*
