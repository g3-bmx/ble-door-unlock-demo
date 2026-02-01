--------------------------------------------------------
iBeacon Advertising | Intercom Implementation Guide
--------------------------------------------------------
This document covers iBeacon advertising implementation for the
intercom device. Engineers implementing iBeacon on the intercom
should use this as a reference for requirements, configuration
options, and limitations.
--------------------------------------------------------


--------------------------------------------------------
What is iBeacon
--------------------------------------------------------
iBeacon is a protocol developed by Apple that allows BLE devices
to broadcast a small advertisement packet to nearby devices.
It is a one-way transmitter that announces presence to listening
devices. The intercom will act as the broadcaster, and mobile
applications will scan for and detect the intercom's beacon.
--------------------------------------------------------


--------------------------------------------------------
iBeacon Advertisement Packet Structure
--------------------------------------------------------
The intercom broadcasts a BLE advertisement containing:

| Field     | Size     | Description                                    |
|-----------|----------|------------------------------------------------|
| UUID      | 16 bytes | Unique identifier for the intercom/application |
| Major     | 2 bytes  | Group identifier (optional for single device)  |
| Minor     | 2 bytes  | Device identifier (optional for single device) |
| TX Power  | 1 byte   | Calibrated signal strength at 1 meter (dBm)    |

All intercoms share the same UUID. The mobile app registers one
beacon region for this UUID and detects all intercoms. Major and
Minor values can be used to identify specific intercoms or groups
if needed, but specific intercom identification typically happens
after GATT connection.
--------------------------------------------------------


--------------------------------------------------------
Configuration Options
--------------------------------------------------------

UUID Selection
--------------
- Generate a unique UUID for the intercom application
- Use a standard UUID generator (v4 recommended)
- This UUID must be shared with mobile applications for scanning
- Example: "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"

TX Power Configuration
----------------------
TX Power controls the effective broadcast range and affects
how mobile applications estimate distance from the intercom.

| TX Power Setting | Typical Detection Range | Use Case              |
|------------------|-------------------------|-----------------------|
| High (+4 dBm)    | ~30-50 meters           | Early detection       |
| Medium (-8 dBm)  | ~10-20 meters           | Room-level detection  |
| Low (-20 dBm)    | ~2-5 meters             | Close proximity only  |

Considerations:
- Higher TX Power = earlier detection but less precise proximity
- Lower TX Power = later detection but better proximity accuracy
- Environmental factors (walls, interference) affect actual range
- TX Power value stored in packet is the expected RSSI at 1 meter
  (used by mobile apps for distance calculation)

Broadcast Interval
------------------
How frequently the intercom sends advertisement packets.

| Interval    | Battery Impact | Detection Speed        |
|-------------|----------------|------------------------|
| 100ms       | High           | Fast (~100ms)          |
| 350ms       | Medium         | Moderate (~350ms)      |
| 1000ms      | Low            | Slow (~1-2 seconds)    |

For a powered intercom device (not battery-operated), a faster
interval (100-350ms) is recommended for responsive detection.
--------------------------------------------------------


--------------------------------------------------------
Benefits
--------------------------------------------------------

Low Complexity
--------------
- Simple broadcast protocol with no pairing required
- Mobile devices detect presence without establishing connection
- Minimal implementation overhead on intercom side

Wide Compatibility
------------------
- Supported by iOS and Android natively
- Works with any BLE-capable mobile device
- Apple's protocol but universally adopted

Passive Detection
-----------------
- Mobile apps can detect intercom without user interaction
- Enables automatic proximity-based features
- iOS can monitor for beacon even when app is terminated

Coexistence with GATT Services
------------------------------
- iBeacon advertising can run alongside existing BLE GATT services
- Mobile app detects intercom via iBeacon, then connects via GATT
- Supports the existing door unlock challenge/response flow
--------------------------------------------------------


--------------------------------------------------------
Limitations
--------------------------------------------------------

One-Way Communication Only
--------------------------
- iBeacon only broadcasts; it cannot receive data
- For bidirectional communication, GATT connection is required
- iBeacon is for presence detection, not authentication

No Data Payload
---------------
- Only transmits UUID, Major, Minor, and TX Power
- Cannot include dynamic data (e.g., intercom status, door state)
- Mobile app must connect via GATT for meaningful interaction

Distance Estimation is Imprecise
--------------------------------
- RSSI-based distance calculation has +/- 1-3 meter accuracy
- Affected by obstacles, interference, device orientation, humidity
- Should not be relied upon for exact distance measurements
- Use proximity zones (immediate/near/far) rather than exact meters

No Security
-----------
- iBeacon packets can be spoofed by any device
- Anyone can broadcast the same UUID
- DO NOT use iBeacon for authentication or access control decisions
- iBeacon is for discovery only; authentication must happen over
  the encrypted GATT connection using challenge/response

iOS Background Detection Delay
------------------------------
- When mobile app is terminated, iOS batches BLE scans to save battery
- Detection can take 1-15 minutes in worst case
- For immediate detection, user must have app in foreground
--------------------------------------------------------


--------------------------------------------------------
Mobile Platform Limitations (UUID Registration)
--------------------------------------------------------
These limitations exist on iOS and Android and affect how
UUIDs should be configured on the intercom. Understanding
these constraints is important for UUID strategy decisions.

iOS Limitations
---------------

20 Region Limit Per App
- iOS allows a maximum of 20 beacon regions per app
- A "region" can be: UUID only, UUID+Major, or UUID+Major+Minor
- If all intercoms share ONE UUID: uses 1 region slot (recommended)
- If each intercom has UNIQUE UUID: uses 1 slot per intercom (max 20)

| UUID Strategy           | Regions Used | Max Intercoms Trackable |
|-------------------------|--------------|-------------------------|
| Shared UUID (all same)  | 1            | Unlimited               |
| UUID + Major grouping   | 1 per group  | 20 groups               |
| Unique UUID per device  | 1 per device | 20 devices              |

RECOMMENDATION: Use a shared UUID across all intercoms. The mobile
app can identify specific intercoms after GATT connection, not at
the iBeacon detection layer.

"Always" Location Permission Required
- Background beacon monitoring requires "Always Allow" location permission
- "When In Use" permission is NOT sufficient for background detection
- Users are often reluctant to grant "Always" permission
- If user denies, beacon detection only works when app is foregrounded
- Mobile app must handle graceful fallback for denied permissions

No Distance Threshold for Region Monitoring
- iOS does not allow setting a trigger distance (e.g., "alert at 3m")
- Region entry triggers when beacon is detected at ANY range
- To control effective trigger distance, adjust TX Power on intercom
- Lower TX Power = beacon only detectable when user is closer

Background Ranging Not Available
- "Ranging" (distance estimation) only works when app is in foreground
- When app is backgrounded/terminated, only region enter/exit events fire
- After region entry wakes the app, ranging is available for ~10 seconds
- Mobile cannot continuously monitor distance in background

Android Limitations
-------------------

Permission Requirements
- Requires BLUETOOTH_SCAN permission
- Requires ACCESS_FINE_LOCATION permission
- Android 10+: Requires ACCESS_BACKGROUND_LOCATION for background scanning
- Users must explicitly grant background location in system settings

Background Scanning Reliability
- Standard background scanning is unreliable (OS kills processes)
- Reliable background scanning requires a Foreground Service
- Foreground Service shows persistent notification ("App is running")
- This may be undesirable for user experience

No Native iBeacon API
- Android does not have native iBeacon support like iOS CLLocationManager
- Must parse iBeacon format from raw BLE scan results
- Or use third-party libraries (AltBeacon, etc.)
- Slightly more implementation effort on mobile side

Impact on Intercom UUID Strategy
--------------------------------
Given these constraints, the recommended approach is:

1. Use a SINGLE shared UUID for all intercoms
   - Avoids iOS 20 region limit
   - Mobile app registers one region, detects all intercoms
   - Specific intercom identified after GATT connection

2. Use Major/Minor for optional grouping
   - Major: building or location identifier
   - Minor: specific intercom within location
   - Mobile can filter by Major/Minor after ranging (foreground only)

3. Keep TX Power consistent across intercoms
   - Predictable detection range for users
   - Consistent distance estimation accuracy
--------------------------------------------------------


--------------------------------------------------------
Implementation Requirements
--------------------------------------------------------

Hardware Requirements
---------------------
- BLE 4.0+ capable radio on intercom
- Ability to configure advertisement packet data
- Sufficient processing for concurrent advertising and GATT services

Software Requirements
---------------------
- BLE stack supporting iBeacon advertisement format
- Configuration interface for UUID and TX Power settings
- Advertisement must include Apple's iBeacon prefix:
  - Company ID: 0x004C (Apple)
  - iBeacon type: 0x02
  - Length: 0x15 (21 bytes)

Advertisement Packet Format (Manufacturer Specific Data)
--------------------------------------------------------
| Offset | Length | Value       | Description           |
|--------|--------|-------------|-----------------------|
| 0      | 2      | 0x4C00      | Apple Company ID (LE) |
| 2      | 1      | 0x02        | iBeacon type          |
| 3      | 1      | 0x15        | Length (21 bytes)     |
| 4      | 16     | [UUID]      | Proximity UUID        |
| 20     | 2      | [Major]     | Major value (BE)      |
| 22     | 2      | [Minor]     | Minor value (BE)      |
| 24     | 1      | [TX Power]  | Calibrated TX Power   |

Note: UUID Major/Minor are big-endian. Company ID is little-endian.
--------------------------------------------------------


--------------------------------------------------------
Mobile Application Integration
--------------------------------------------------------
The mobile application will:

1. Register the intercom's UUID for beacon monitoring
2. Receive region entry/exit events from the OS
3. On region entry, optionally start ranging for distance
4. Initiate GATT connection for door unlock flow

From the intercom's perspective:
- Advertise continuously (or on schedule)
- Be prepared for GATT connection after mobile detects beacon
- iBeacon advertising can continue during GATT connection

Recommended Flow:
-----------------
1. Intercom advertises iBeacon with configured UUID
2. Mobile detects beacon (background or foreground)
3. Mobile initiates BLE GATT connection to intercom
4. Door unlock proceeds via existing challenge/response protocol
--------------------------------------------------------


--------------------------------------------------------
Configuration Checklist
--------------------------------------------------------
Before deployment, ensure the following are configured:

[ ] UUID generated and documented
[ ] UUID shared with mobile application team
[ ] TX Power set appropriately for desired detection range
[ ] Broadcast interval configured (recommend 100-350ms)
[ ] Major/Minor values set (can be 0 for single device)
[ ] Advertisement tested with BLE scanner app (nRF Connect, LightBlue)
[ ] Verified coexistence with GATT services
[ ] Documented TX Power value for mobile distance calculations
--------------------------------------------------------


--------------------------------------------------------
Testing and Validation
--------------------------------------------------------

Recommended Testing Tools
-------------------------
- nRF Connect (iOS/Android) - scan and view iBeacon packets
- LightBlue (iOS) - beacon detection and RSSI monitoring
- Bluetooth Explorer (macOS) - detailed packet analysis

Validation Steps
----------------
1. Verify advertisement packet is correctly formatted
2. Confirm UUID, Major, Minor, TX Power values are as configured
3. Test detection range at various distances
4. Verify GATT services remain functional during advertising
5. Test mobile app background detection (iOS/Android)
6. Measure detection latency in foreground vs background
--------------------------------------------------------
