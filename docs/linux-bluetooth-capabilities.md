----------------------------------------
Bluetooth BLE - linux intercom
----------------------------------------
- bluetoothctl --version
	- determine version of bluetoothctl.

- systemctl status bluetooth
	- determine current status of bluetooth service

- dpkg -l | grep -i bluez
	- view bluetooth related packages installed

- busctl tree org.bluez
	- inspect bluez via d-bus

- cat /sys/module/bluetooth/version
	- Check kernel Bluetooth subsystem info

- dmesg | grep -i bluetooth
	- review dmesg for stack initialization


----------------------------------------------------------------
bluetoothctl --version
----------------------------------------------------------------
bluetoothctl: 5.64

----------------------------------------------------------------
systemctl status bluetooth
----------------------------------------------------------------
● bluetooth.service - Bluetooth service
     Loaded: loaded (/lib/systemd/system/bluetooth.service; enabled; vendor preset: enabled)
    Drop-In: /etc/systemd/system/bluetooth.service.d
             └─override.conf
     Active: active (running) since Wed 2026-01-28 13:51:01 UTC; 9min ago
       Docs: man:bluetoothd(8)
   Main PID: 1347 (bluetoothd)
     Status: "Running"
      Tasks: 1 (limit: 7992)
     Memory: 2.1M
     CGroup: /system.slice/bluetooth.service
             └─1347 /usr/libexec/bluetooth/bluetoothd -P battery

Jan 28 13:51:00 M108-23070001 systemd[1]: Starting Bluetooth service...
Jan 28 13:51:01 M108-23070001 systemd[1]: Started Bluetooth service.


----------------------------------------------------------------
dpkg -l | grep -i bluez
----------------------------------------------------------------
iF  bluez5                                                                  5.64-r0                    arm64        Linux Bluetooth Stack Userland V5
ii  gstreamer1.0-plugins-bad-bluez                                          1.20.0.imx-r0              arm64        GStreamer 1.0 plugin for bluez
ii  pulseaudio-lib-bluez5-util                                              15.0-r0                    arm64        PulseAudio library for bluez5-util
ii  pulseaudio-module-bluez5-device                                         15.0-r0                    arm64        PulseAudio module for bluez5-device
ii  pulseaudio-module-bluez5-discover                                       15.0-r0                    arm64        PulseAudio module for bluez5-discover


----------------------------------------------------------------
busctl tree org.bluez
----------------------------------------------------------------
M108-23070001:~$ busctl tree org.bluez
└─/org
  └─/org/bluez
    └─/org/bluez/hci0


----------------------------------------------------------------
cat /sys/module/bluetooth/version
----------------------------------------------------------------
2.22


----------------------------------------------------------------
dmesg | grep -i bluetooth
----------------------------------------------------------------
[    0.128979] Bluetooth: Core ver 2.22
[    0.129006] NET: Registered PF_BLUETOOTH protocol family
[    0.129012] Bluetooth: HCI device and connection manager initialized
[    0.129026] Bluetooth: HCI socket layer initialized
[    0.129036] Bluetooth: L2CAP socket layer initialized
[    0.129051] Bluetooth: SCO socket layer initialized
[    1.779754] Bluetooth: HCI UART driver ver 2.3
[    1.784217] Bluetooth: HCI UART protocol H4 registered
[    1.789366] Bluetooth: HCI UART protocol BCSP registered
[    1.794708] Bluetooth: HCI UART protocol LL registered
[    1.799859] Bluetooth: HCI UART protocol ATH3K registered
[    1.805286] Bluetooth: HCI UART protocol Three-wire (H5) registered
[    1.811703] Bluetooth: HCI UART protocol Broadcom registered
[    1.817389] Bluetooth: HCI UART protocol QCA registered
[    2.213800] Bluetooth: RFCOMM TTY layer initialized
[    2.218699] Bluetooth: RFCOMM socket layer initialized
[    2.223887] Bluetooth: RFCOMM ver 1.11
[    2.227658] Bluetooth: BNEP (Ethernet Emulation) ver 1.3
[    2.232978] Bluetooth: BNEP filters: protocol multicast
[    2.238225] Bluetooth: BNEP socket layer initialized
[    2.243199] Bluetooth: HIDP (Human Interface Emulation) ver 1.2
[    2.249135] Bluetooth: HIDP socket layer initialized



----------------------------------------------------------------
Notes
----------------------------------------------------------------
- Linux intercom is using bluez 5.64
- Bluez - entire bluetooth stack project for linux.
- bluetoothctl is a command line tool part of the bluez stack.

BlueZ (the project) includes:
- bluetoothd — the main Bluetooth daemon/service
- bluetoothctl — interactive CLI tool for managing Bluetooth
- hciconfig, hcitool, hcidump — lower-level HCI utilities (deprecated in newer versions)
- btmon — Bluetooth monitor for debugging
- Kernel modules and libraries
- D-Bus APIs
	- D-Bus (Desktop Bus) is an inter-process communication (IPC) system for Linux and Unix-like operating systems.
	- It allows different programs running on the same machine to talk to each other.
	- Two main buses:
		- System bus — for system-wide services (like BlueZ, NetworkManager, systemd)
		- Session bus — for user applications within a login session
	- How BlueZ uses D-Bus:
		- Instead of applications directly controlling Bluetooth hardware, they send requests to the bluetoothd daemon over D-Bus.
		- For example, when you pair a device using a GUI app, that app sends D-Bus messages to BlueZ, which handles the actual Bluetooth operations.


------------------------------------------------------------------
Why D-Bus matters?
------------------------------------------------------------------
Provides a standardized way for programs to communicate
Enables sandboxing and security controls
Lets you script/automate system services (like Bluetooth) using D-Bus commands
D-Bus is fundamental to modern Linux desktops and system services — almost everything from Bluetooth to networking to power management uses it.


