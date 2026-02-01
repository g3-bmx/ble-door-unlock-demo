## Setup

1. copy the `ble_ibeacon_advertising` folder to your intercom
```
scp -r src/ble_ibeacon_advertising monarch@<YOUR_INTERCOM_IP_ADDRESS>:/home/monarch
```

2. install `dbus-next` within the intercom
```
sudo pip3 install dbus-next
```

3. run the project on the intercom
```
sudo python3 -m ble_ibeacon_advertising --hw-tx-power -16
```

## Verifying iBeacon advertising
You can use the following mobile app to view the ibeacon advertising
- IOS - beacon scan
- you will have to register the beacon you want to track (UUID)