---------------------------------------------
Mobile App: Unlock Request
---------------------------------------------
1. Mobile application scans for intercom advertising messages
2. Mobile applications start connection to intercom (BLE connect)
3. Intercom responds with nonce challenge (explain why this is important!)
	- nonce_challenge: random 16b number
4. Mobile application sends encrypted request to intercom
	- shared secret: ECDH(privM, pubD)
	- session salt: nonce
	- derived keys for: MobileToIntercom, IntercomToMobile, AuthKey
	- encrypt the door unlock payload (MobileToIntercom key)
5. Intercom receives encrypted request and decrypts
	- intercom parses mobile public key from message
	- intercom derives the same keys as mobile
		- shared secret: ECDH(privI, pubM)
		- session salt: nonce
		- derive keys: MobileToIntercom, IntercomToMobile, AuthKey
	- decrypt the payload using the derived keys
	- verify credential sig
	- verify hmac
	- verify expiration time
	- verify revocation
	- all good? unlock door
	- intercom encrypts response | success / failure scenario
6. Mobile application decrypts response
	- mobile application shows unlock request response (success / failure)



The above is just a step by step outline for the unlock request from Mobile to intercom.
However it is lacking details for actually implementing this through BLE GATT services / characteristics.

Protocol flow mapped to GATT operations:
──────────────────────────────────────
1. Mobile connects to intercom
	mobile connection to intercom is "just works".
	It just connects to the intercom and begins the auth flow.
2. Mobile subscribes to notifications
3. Intercom sends challenge nonce          → Notify
	- intercom sends the challenge nonce immediately after the mobile device subscribes successfully (faster)
4. Mobile sends encrypted auth request     → Write
5. Intercom sends encrypted response       → Indicate
6. (Optional) Mobile sends commands        → Write
7. (Optional) Intercom sends status        → Indicate


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
    		    	- Return current nonce
    		    - On Notify subscription:
    		    	- Immediately send current nonce via notification
    		    - On timeout (30 seconds):
    		      - Invalidate nonce
    		      - Generate new nonce
    		      - Notify subscribed clients
    		    - On successful authentication:
    		      - Invalidate nonce immediately
    		      - Prevents replay within same connection
        │
        ├── Authentication Characteristic  
        │   UUID: 0x1236
        │   Properties: Write
        │	Permissions: Open (app-layer encryption handles security)
        │   Value: up to 512 bytes (encrypted request)
        │	Note: You will need to negotiate the maximum packet size on connection (MTU)
        │	Behavior:
        		- Check message size (min 94 bytes, max 512 bytes)
        			- If invalid → Respond with error via Response characteristic
    			- Extract PubM (bytes 1-65)
    			- Verify PubM is valid curve point
   					- If invalid → Respond with error
				- Compute SharedSecret = ECDH(PrivIntercom, PubMobile)
				- Derive session keys from sharedSecret using the stored nonce as salt
					- MobileToIntercom key = HKDF(SharedSecret, Nonce_C, "m2i-enc")
					- AuthKey = HKDF(SharedSecret, Nonce_C, "auth")
				- Decrypt payload using AES-256-GCM:
   					- If tag invalid → Respond with AUTH_FAILED
   				- Verify door release credential:
   					- validate access tool id | access point id | tenant id (i dunno yet)
   					- check credential offline grace period 
   					- check intercom's allowlist for intercoms
   					- fail request if the above checks fail
   				- verify hmac
   					- I have no idea what this means
   				- if all valid:
   					- unlock that door
   					- invalidate current nonce
   					- send success response
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
        	0x01 = Auth failed (bad signature, HMAC, or decryption)
        	0x02 = Credential expired
        	0x03 = Credential not yet valid
        	0x04 = Credential revoked
        	0x05 = Wrong door (aud mismatch)
        	0x06 = Permission denied (action not allowed)
        	0x07 = Rate limited (too many attempts)
        	0x08 = Door mechanically jammed
        	0x09 = Internal error
        	0x0A = Challenge expired (took too long)

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
       │     Chars: 0x1235, 0x1236, 0x1237, 0x1238            │
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
       │ │    - Compute ECDH(PrivM, PubD)             │       │
       │ │    - Derive EncKeyM2I, AuthKey             │       │
       │ │    - Build payload with credential         │       │
       │ │    - Compute HMAC                          │       │
       │ │    - Encrypt with AES-GCM                  │       │
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
       │                                               │ - ECDH       │
       │                                               │ - Decrypt    │
       │                                               │ - Verify sig │
       │                                               │ - Verify HMAC│
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
       │  14. Disconnect (optional, or keep alive)            │
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
