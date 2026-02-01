---------------------------------------------
Mobile App: Unlock Request
---------------------------------------------
1. Mobile application scans for intercom advertising messages
2. Mobile applications start connection to intercom (BLE connect)
3. Intercom responds with nonce challenge
	- nonce_challenge: random 16-byte cryptographic nonce
	- Why important: Prevents replay attacks. Each auth attempt requires a fresh nonce,
	  so an attacker cannot reuse a captured authentication message.
4. Mobile application sends encrypted request to intercom
	- shared secret: ECDH(privM, pubI)
	- session salt: nonce
	- derived keys: MobileToIntercom, IntercomToMobile (via HKDF-SHA256)
	- encrypt the door unlock payload (MobileToIntercom key)
5. Intercom receives encrypted request and decrypts
	- intercom parses mobile public key from message
	- intercom derives the same keys as mobile
		- shared secret: ECDH(privI, pubM)
		- session salt: nonce
		- derive keys via HKDF-SHA256:
			- MobileToIntercom = HKDF(SharedSecret, Nonce, "m2i-enc", 32 bytes)
			- IntercomToMobile = HKDF(SharedSecret, Nonce, "i2m-enc", 32 bytes)
	- decrypt the payload using AES-256-GCM with MobileToIntercom key
	- verify GCM authentication tag (provides integrity + authenticity)
	- verify credential signature (signed by backend)
	- verify expiration time
	- verify revocation status
	- all good? unlock door
	- intercom encrypts response using IntercomToMobile key
6. Mobile application decrypts response
	- mobile application shows unlock request response (success / failure)
7. Connection closed after response



The above is just a step by step outline for the unlock request from Mobile to intercom.
However it is lacking details for actually implementing this through BLE GATT services / characteristics.

Protocol flow mapped to GATT operations:
──────────────────────────────────────
1. Mobile connects to intercom
	mobile connection to intercom is "just works".
	It just connects to the intercom and begins the auth flow.
2. Mobile negotiates MTU (request 251+ bytes)
3. Mobile subscribes to Response characteristic (indications)
4. Mobile subscribes to Challenge characteristic (notifications)
5. Intercom sends challenge nonce          → Notify
	- intercom sends the challenge nonce immediately after subscription (faster)
6. Mobile sends encrypted auth request     → Write
7. Intercom sends encrypted response       → Indicate
8. Mobile acknowledges indication          → ACK
9. Disconnect


┌─────────────────────────────────────────────────────────────────────────────┐
│                    DEVICE INFORMATION SERVICE (Standard)                    │
│                    UUID: 0x180A                                             │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ├── Manufacturer Name
        │   UUID: 0x2A29
        │   Value: "Your Company"
        │
        ├── Model Number  
        │   UUID: 0x2A24
        │   Value: "Monarch-v1"
        │
        ├── Firmware Revision
        │   UUID: 0x2A26
        │   Value: "1.2.3"
        │
        └── Serial Number
            UUID: 0x2A25
            Value: (optional, privacy concern)


┌─────────────────────────────────────────────────────────────────────────────┐
│                    DOOR ACCESS SERVICE                                      │
│                    UUID: 0x1234 (short) or                                  │
│                    12340000-1234-5678-9ABC-DEF012345678 (full 128-bit)      │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ├── Challenge Characteristic
        │	Purpose: Intercom provides fresh challenge nonce for each authentication attempt
        │   UUID: 0x1235
        │   Properties: Read, Notify
        │	Permissions: Open (no encryption required at BLE level)
        │   Value: 16 bytes (challenge nonce)
        │	Value format: nonce - Cryptographically random, generated fresh for each connection
        │	Behavior:
    			- On BLE connection established:
					- Generate new 16-byte random nonce
        		  	- Store nonce with timestamp
        		  	- Start 30-second timeout timer
    			- On Read request:
    		    	- Return current nonce (fallback/debugging path)
    		    - On Notify subscription:
    		    	- Immediately send current nonce via notification (primary path)
    		    - On timeout (30 seconds):
    		      - Invalidate nonce (do NOT regenerate)
    		      - Client must reconnect for fresh nonce
    		    - On successful authentication:
    		      - Invalidate nonce immediately
    		      - Prevents replay within same connection
    		    - On failed authentication:
    		      - Invalidate nonce immediately
    		      - Prevents brute force on same nonce
    		    - On disconnect:
    		      - Invalidate nonce immediately
        │
        ├── Authentication Characteristic
        │   UUID: 0x1236
        │   Properties: Write
        │	Permissions: Open (app-layer encryption handles security)
        │   Value: up to 512 bytes (encrypted request)
        │	Note: Negotiate MTU to 247+ bytes at connection time
        │
        │	Message format:
        │	┌─────────┬────────┬──────────┬────────────────────────┬──────────┐
        │	│ Version │ PubM   │ Nonce_M  │ Encrypted Payload      │ Tag      │
        │	│ 1 B     │ 65 B   │ 12 B     │ Variable               │ 16 B     │
        │	└─────────┴────────┴──────────┴────────────────────────┴──────────┘
        │	- Version: Protocol version (0x01)
        │	- PubM: Mobile's public key (uncompressed P-256 point)
        │	- Nonce_M: GCM nonce for encryption
        │	- Encrypted Payload: Credential data encrypted with AES-256-GCM
        │	- Tag: GCM authentication tag (16 bytes)
        │
        │	Behavior:
        		- Check rate limit by PubM (extract first, check before crypto)
        			- If rate limited → Respond with RATE_LIMITED
        		- Check message size (min 94 bytes, max 512 bytes)
        			- If invalid → Respond with error via Response characteristic
    			- Extract PubM (bytes 1-65)
    			- Verify PubM is valid P-256 curve point
   					- If invalid → Respond with error
				- Compute SharedSecret = ECDH(PrivIntercom, PubMobile)
				- Derive session keys using HKDF-SHA256:
					- MobileToIntercom = HKDF(SharedSecret, Nonce_C, "m2i-enc", 32 bytes)
					- IntercomToMobile = HKDF(SharedSecret, Nonce_C, "i2m-enc", 32 bytes)
				- Decrypt payload using AES-256-GCM with MobileToIntercom key:
   					- If GCM tag invalid → Respond with AUTH_FAILED
   				- Verify door release credential:
   					- verify credential signature (signed by backend authority)
   					- check credential expiration time
   					- check credential not-before time
   					- check door ID matches this intercom
   					- check credential offline grace period
   					- check revocation status (if within grace period)
   					- fail request if any check fails
   				- If all valid:
   					- trigger door unlock
   					- invalidate current nonce
   					- encrypt success response with IntercomToMobile key
   					- send response via Response characteristic
   				- If any check fails:
   					- invalidate current nonce
   					- encrypt failure response with IntercomToMobile key
   					- send response via Response characteristic
        │
        ├── Response Characteristic
        │	Purpose: Intercom sends encrypted result back to mobile
        │   UUID: 0x1237
        │   Properties: Indicate | client can subscribe to characteristic, but must acknowledge messages
        │	Permissions: Open
        │   Value: up to 256 bytes (encrypted response)
        │	Note: You will need to negotiate the maximum packet size on connection (MTU)

        	Value format (encrypted response):
        	┌────────────┬────────────────────────┬──────────┐
        	│ Nonce_I    │ Encrypted Payload      │ Tag      │
        	│ 12 B       │ Variable               │ 16 B     │
        	└────────────┴────────────────────────┴──────────┘

        	Decrypted payload format:
        	┌─────────┬────────────┬───────────────────────┐
        	│ Status  │ Door State │ Extended Data         │
        	│ 1 B     │ 1 B        │ Variable (optional)   │
        	└─────────┴────────────┴───────────────────────┘

        	Status codes:
        	─────────────
        	0x00 = Success
        	0x01 = Auth failed (bad signature or decryption failure)
        	0x02 = Credential expired
        	0x03 = Credential not yet valid
        	0x04 = Credential revoked
        	0x05 = Wrong door (door ID mismatch)
        	0x06 = Permission denied (action not allowed)
        	0x07 = Rate limited (too many attempts from this public key)
        	0x08 = Door mechanically jammed
        	0x09 = Internal error
        	0x0A = Challenge expired (nonce timeout - reconnect required)

        	Door State:
        	───────────
        	0x00 = Unknown
        	0x01 = Locked
        	0x02 = Unlocked
        	0x03 = Ajar (unlocked and open)
        	0x04 = Forced (tamper detected)


        	Indicate:  
        	  Mobile ◀─── Data ─── Intercom
        	  Mobile ───── ACK ───▶ Intercom
        	  (guaranteed delivery confirmation)

        	For door access, you WANT confirmation that the mobile
        	received the unlock status. Use Indicate.



The above are the BLE GATT services / characteristics. but then you also got to dive into the
format of the BLE message being shared between devices. the BLE packet is very limited in size,
if you wanna fit stuff into a single packet, then you have to think about how large is the data
that you are sharing.

MTU is important. Your auth message is ~300 bytes, but default BLE MTU only allows 20 bytes payload.
Always negotiate MTU up to 247+ at connection time—modern phones support this.





-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------

┌─────────────┐                                        ┌─────────────┐
│  Mobile     │                                        │  Intercom   │
│  (Central)  │                                        │ (Peripheral)│
└──────┬──────┘                                        └──────┬──────┘
       │                                                      │
       │  ══════════════ CONNECTION PHASE ══════════════      │
       │                                                      │
       │  1. Scan for peripherals advertising                 │
       │     Door Access Service UUID                         │
       │ ─────────────────────────────────────────────────────▶
       │                                                      │
       │  2. Connect                                          │
       │ ─────────────────────────────────────────────────────▶
       │                                                      │
       │  3. Discover services                                │
       │ ─────────────────────────────────────────────────────▶
       │ ◀─────────────────────────────────────────────────────
       │     Services: 0x1234 (Door Access), 0x180A (DevInfo) │
       │                                                      │
       │  4. Discover characteristics of 0x1234               │
       │ ─────────────────────────────────────────────────────▶
       │ ◀─────────────────────────────────────────────────────
       │     Chars: 0x1235, 0x1236, 0x1237                     │
       │                                                      │
       │  ══════════════ CHALLENGE PHASE ═══════════════      │
       │                                                      │
       │  5. Subscribe to Response char (0x1237) indications  │
       │ ─────────────────────────────────────────────────────▶
       │     Write to CCCD: 0x0002 (indications enabled)      │
       │                                                      │
       │  6. Subscribe to Challenge char (0x1235) notifications
       │ ─────────────────────────────────────────────────────▶
       │     Write to CCCD: 0x0001 (notifications enabled)    │
       │                                                      │
       │                                               ┌──────┴───────┐
       │                                               │ Generate     │
       │                                               │ Nonce_C      │
       │                                               │ Start timer  │
       │                                               └──────┬───────┘
       │                                                      │
       │  7. Receive challenge nonce (notification)           │
       │ ◀─────────────────────────────────────────────────────
       │     ATT Handle Value Notification                    │
       │     Value: Nonce_C (16 bytes)                        │
       │                                                      │
       │  ══════════════ AUTH PHASE ════════════════════      │
       │                                                      │
       │ ┌────────────────────────────────────────────┐       │
       │ │ 8. Mobile prepares request:                │       │
       │ │    - Compute ECDH(PrivM, PubI)             │       │
       │ │    - Derive keys via HKDF-SHA256:          │       │
       │ │      - m2i = HKDF(secret, nonce, "m2i-enc")│       │
       │ │      - i2m = HKDF(secret, nonce, "i2m-enc")│       │
       │ │    - Build payload with credential         │       │
       │ │    - Encrypt with AES-256-GCM (m2i key)    │       │
       │ └────────────────────────────────────────────┘       │
       │                                                      │
       │  9. Write encrypted request to Auth char (0x1236)    │
       │ ─────────────────────────────────────────────────────▶
       │     ATT Write Request                                │
       │     Value: Ver ‖ PubM ‖ Nonce_M ‖ Ciphertext ‖ Tag   │
       │                                                      │
       │ ◀─────────────────────────────────────────────────────
       │     ATT Write Response (acknowledged)                │
       │                                                      │
       │                                               ┌──────┴───────┐
       │                                               │ 10. Process: │
       │                                               │ - Rate check │
       │                                               │ - ECDH       │
       │                                               │ - HKDF keys  │
       │                                               │ - Decrypt    │
       │                                               │ - Verify GCM │
       │                                               │ - Verify cred│
       │                                               │ - Actuate    │
       │                                               └──────┬───────┘
       │                                                      │
       │  ══════════════ RESPONSE PHASE ════════════════      │
       │                                                      │
       │  11. Receive encrypted response (indication)         │
       │ ◀─────────────────────────────────────────────────────
       │     ATT Handle Value Indication                      │
       │     Value: Nonce_I ‖ Ciphertext ‖ Tag                │
       │                                                      │
       │  12. Acknowledge indication                          │
       │ ─────────────────────────────────────────────────────▶
       │     ATT Handle Value Confirmation                    │
       │                                                      │
       │ ┌────────────────────────────────────────────┐       │
       │ │ 13. Mobile decrypts response:              │       │
       │ │     - Decrypt with EncKeyI2M               │       │
       │ │     - Parse status code                    │       │
       │ │     - Update UI                            │       │
       │ └────────────────────────────────────────────┘       │
       │                                                      │
       │  14. Disconnect                                        │
       │ ─────────────────────────────────────────────────────▶
       │                                                      │



-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------


Handling Large Messages (MTU Considerations)
Default BLE MTU is 23 bytes (20 bytes payload). Your auth message is ~300 bytes.

MTU Negotiation (Recommended)
Modern devices support larger MTU:
─────────────────────────────────
- iOS: Up to 185 bytes (often 251)
- Android: Up to 517 bytes
- Most BLE 4.2+ peripherals: 247+ bytes

Flow:
1. After connection, mobile requests MTU exchange
2. Negotiate to 251 or higher
3. Single write can carry entire auth message

┌─────────────┐                          ┌─────────────┐
│   Mobile    │                          │  Intercom   │
└──────┬──────┘                          └──────┬──────┘
       │                                        │
       │  ATT Exchange MTU Request (251)        │
       │ ──────────────────────────────────────▶│
       │                                        │
       │  ATT Exchange MTU Response (247)       │
       │ ◀──────────────────────────────────────│
       │                                        │
       │  Effective MTU: min(251, 247) = 247    │
       │  Payload size: 247 - 3 = 244 bytes     │
       │                                        │



-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------

┌─────────────────────────────────────────────────────────────────┐
│                    DO NOT USE BLE-LEVEL SECURITY                │
└─────────────────────────────────────────────────────────────────┘

You might think: "Why not use BLE's built-in encryption?"

Problems:
─────────
1. Just Works pairing = No MITM protection
2. Passkey pairing = Bad UX for door access
3. OOB pairing = Requires NFC hardware
4. Bonding = Stores keys per device, doesn't scale

Your design is better:
──────────────────────
- Application-layer encryption (AES-GCM)
- Application-layer authentication (ECDH + signed credentials)
- Backend-managed trust model
- Works with any BLE pairing mode (including none)

GATT permissions should be "Open":
──────────────────────────────────
- No BLE-level encryption required
- No BLE-level authentication required
- All security happens at application layer
- Simpler implementation, fewer edge cases


-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------

┌─────────────────────────────────────────────────────────────────┐
│                    CRYPTOGRAPHIC PARAMETERS                     │
└─────────────────────────────────────────────────────────────────┘

Key Exchange:
─────────────
- Algorithm: ECDH (Elliptic Curve Diffie-Hellman)
- Curve: P-256 (secp256r1 / prime256v1)
- Public key format: Uncompressed (65 bytes: 0x04 || x || y)

Key Derivation:
───────────────
- Algorithm: HKDF (RFC 5869)
- Hash: SHA-256
- Salt: Challenge nonce (16 bytes)
- Output length: 32 bytes (256 bits)
- Info strings:
  - "m2i-enc" → MobileToIntercom encryption key
  - "i2m-enc" → IntercomToMobile encryption key

Symmetric Encryption:
─────────────────────
- Algorithm: AES-256-GCM (Galois/Counter Mode)
- Key size: 256 bits (32 bytes)
- Nonce size: 96 bits (12 bytes)
- Tag size: 128 bits (16 bytes)
- GCM provides: confidentiality + integrity + authenticity

Challenge Nonce:
────────────────
- Size: 16 bytes (128 bits)
- Generation: Cryptographically secure random
- Lifetime: 30 seconds or until used (whichever comes first)
- Single-use: Invalidated after any auth attempt (success or failure)


-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------

┌─────────────────────────────────────────────────────────────────┐
│                    SECURITY CONSIDERATIONS                      │
└─────────────────────────────────────────────────────────────────┘

Replay Protection:
──────────────────
- Challenge nonce ensures each auth attempt is unique
- Nonce invalidated immediately after use (success or failure)
- 30-second timeout prevents stale nonce accumulation
- Attacker cannot reuse captured authentication messages

Rate Limiting:
──────────────
- Enforced at GATT server level before expensive crypto operations
- Keyed by mobile public key (PubM)
- Extract PubM from message → check rate limit → proceed or reject
- Recommendation: Also add global rate limit as DoS backstop
  (e.g., max 10 auth attempts/second across all keys)

Forward Secrecy:
────────────────
- NOT provided in this design (static device keys)
- Trade-off: Simpler key management vs. protection of past sessions
- If attacker compromises private key, past recorded sessions can be decrypted
- Acceptable for door unlock (unlock request itself is not highly sensitive)
- If needed: Switch to ephemeral keys per session

Key Management:
───────────────
- Mobile public key (PubM): Static per device/user pair, safe to transmit
- Intercom private key (PrivI): Must be securely stored on device
- Backend signing key: Used to sign credentials, intercom has public key
- Credential: Signed by backend, verified by intercom

Trust Model:
────────────
- Backend is the root of trust (signs credentials)
- Intercom trusts credentials signed by backend
- Mobile proves possession of private key via ECDH
- No BLE-level trust required (application-layer security)
