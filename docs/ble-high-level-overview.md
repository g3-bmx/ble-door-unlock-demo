--------------------------------------------------------
Mobile Application (BLE Setup)
--------------------------------------------------------
BLE unlock feature is started by user on mobile application.
Perhaps no need for close proximity to intercom.
--------------------------------------------------------
1. user hits a button that says 'setup bluetooth unlocks' in mobile application
2. mobile app creates public and private key and stores them locally
3. mobile app sends a request to POST /device/register to register user/device key in CORE
	- POST /device/register | payload: { pubkey, hash } | response: ?
	- backend stores user/device/pubkey into db
	- backend creates BLE access tool for user/device pair
		- BLE access tool has "expires on" property (allows for offline grace period)
		- BLE access tool has "devicePubKey" property (if we have a list of access tools with devicePubKey then we have an allowlist of intercoms that can communicate with Monarch)
	- backend sends a "cache refresh" message to Monarch
		- Monarch fetches access tools and has the new BLE access tool

--------------------------------------------------------
Mobile Application | BLE Access tool refresh
--------------------------------------------------------
Mobile application checks BLE access tool expiration and refreshes if needed
--------------------------------------------------------
1. mobile application starts up
2. mobile application checks BLE access tool expiration date
3. if close to expiration by a given threshold, then it sends a request to renew
4. mobile application sends request to POST /device/refresh to refresh access tool
	- POST / device/refresh | payload: { accessToolId } | response: ?
5. backend refreshes BLE access tool expiration date
6. backend sends command refresh to Monarch to fetch updated access tools
	- the BLE access tool will have an updated "expires on" property (allows for offline grace period)


--------------------------------------------------------
Monarch Intercom | Advertising
--------------------------------------------------------
Intercom embedded BLE service advertises for mobile application
to scan and recognize a particular intercom.
--------------------------------------------------------
1. Intercom starts BLE advertising on boot (or after cache refresh)
2. Advertising packet includes the Door Access Service UUID (0x1234)
3. Mobile applications can scan for this UUID to discover nearby intercoms
4. Advertising continues until a mobile device connects


--------------------------------------------------------
Mobile Application | BLE Connection Start
--------------------------------------------------------
Mobile application scans for intercom advertising
and attempts to connect to the intercom.
--------------------------------------------------------
1. Mobile application scans for BLE peripherals advertising Door Access Service UUID
2. Mobile discovers nearby intercom and initiates connection
3. Mobile negotiates MTU (request 247+ bytes for larger payloads)
4. Mobile discovers GATT services and characteristics
5. Mobile subscribes to Response characteristic (indications)
6. Mobile subscribes to Challenge characteristic (notifications)
7. Intercom generates a fresh nonce and sends it via notification
	- See ble-service-door-unlock.md for GATT service/characteristic details


--------------------------------------------------------
Mobile Application | BLE Door Unlock Request
--------------------------------------------------------
Mobile application connected successfully to intercom through BLE.
Mobile application sends an unlock request to embedded BLE service and that's passed through to Monarch.
Monarch receives door unlock payload, parses it and determines whether to release the door.
Monarch / embedded service will send a response back to mobile app for success / failure result.
--------------------------------------------------------
1. Mobile receives challenge nonce from intercom
2. Mobile computes shared secret using ECDH (mobile private key + intercom public key)
3. Mobile derives session keys from shared secret + nonce
4. Mobile encrypts unlock request payload (AES-GCM) and writes to Auth characteristic
5. Intercom decrypts and verifies:
	- derives same shared secret using ECDH (intercom private key + mobile public key)
	- decrypts payload
	- validates credential (expiration, revocation, allowlist)
6. Intercom encrypts response and sends via Response characteristic (indication)
7. Mobile decrypts response and displays result (success / failure)
	- See ble-service-door-unlock.md for detailed protocol and message formats