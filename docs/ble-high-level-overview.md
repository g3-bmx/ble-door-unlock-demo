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
Intercom embedded BLE service advertises in iBeacon format
for mobile application to scan and recognize a particular intercom
--------------------------------------------------------
... ? ...


--------------------------------------------------------
Mobile Application | BLE Connection Start
--------------------------------------------------------
Mobile application scans for intercom advertising (iBeacon)
and attempts to connect to the intercom
--------------------------------------------------------
... ? ...



--------------------------------------------------------
Mobile Application | BLE Door Unlock Request
--------------------------------------------------------
Mobile application connected successfully to intercom through BLE.
Mobile application sends an unlock request to embeded BLE service and that's passed through to Monarch.
Monarch receives door unlock payload, parses it and determines whether release the door.
Monarch / embeded service will send a response back to mobile app for success / failure result.
--------------------------------------------------------
... ? ...