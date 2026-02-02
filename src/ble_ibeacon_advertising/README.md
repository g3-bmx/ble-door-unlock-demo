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


## Changing BLE transmission power
```
sudo hciconfig hci0 inqtpl -- -16
```


## BLE Commands
Key Insight: Timing Matters
The TX power might need to be set before advertising starts, not during. Try this sequence:


# 1. Stop all advertising first
sudo hciconfig hci0 noleadv
sudo hciconfig hci0 down

# 2. Set the power while adapter is down/reset
sudo hciconfig hci0 up
sudo hcitool -i hci0 cmd 0x3F 0x0023 0x00

# 3. THEN start your iBeacon advertiser
python your_advertiser.py
