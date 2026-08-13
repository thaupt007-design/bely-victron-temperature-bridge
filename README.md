# BeLY LiFePO4 BLE Temperature Bridge for Victron Venus OS

A small Python bridge that reads internal battery temperatures from BeLY LiFePO4 batteries over Bluetooth LE and exposes them as **native Victron temperature sensors** on a GX device.

The project grew out of a real four-battery installation on a sailboat. The goal was deliberately narrow: use the temperature sensors already inside the batteries instead of adding four external probes.

## Tested setup

- Victron Cerbo GX
- Venus OS 3.75
- 4 × BeLY 12 V / 180 Ah LiFePO4 batteries in series
- Python 3
- Bleak
- Victron D-Bus / `VeDbusService`

The tested BeLY batteries use a **JBD-compatible BLE protocol**. That does not prove that the installed BMS hardware itself is manufactured by JBD.

## What it does

For every configured battery the bridge:

1. connects directly to the battery via BLE;
2. requests the BMS status packet;
3. reads all reported internal temperature sensors;
4. discards implausible values;
5. uses the **highest valid temperature**;
6. publishes that value as a native Victron battery-temperature service on D-Bus.

The result is one temperature device per battery in GX Touch / Remote Console, VRM and VRM temperature history.

The bridge does **not** duplicate battery voltage, current or state of charge.

## BLE protocol used

Service: `0000ff00-0000-1000-8000-00805f9b34fb`  
Notify: `0000ff01-0000-1000-8000-00805f9b34fb`  
Write: `0000ff02-0000-1000-8000-00805f9b34fb`  
Status command: `DD A5 03 00 FF FD 77`

Temperature values are interpreted as 0.1 K and converted to °C.

## Configure your batteries

Edit the `BATTERIES` section in `bely_victron_temperature_bridge.py`:

```python
BATTERIES = [
    BatteryConfig("1", "AA:BB:CC:DD:EE:01", 40),
    BatteryConfig("2", "AA:BB:CC:DD:EE:02", 41),
]
```

- `suffix` must be unique.
- `address` is the BLE address visible from Linux/BlueZ.
- `instance` must be a unique Victron DeviceInstance.

The tested installation uses fixed addresses and direct BLE connections rather than scanning. Some BLE devices use private/random addresses that can rotate, so verify address stability first.

## Measurement interval

The default is `UPDATE_INTERVAL_SECONDS = 1800`, i.e. 30 minutes. The first measurement starts immediately.

Between BLE measurements the last value remains on D-Bus. VRM can therefore report the device as recently seen even if the underlying BLE measurement is older.

## Failure behaviour

- Highest valid internal temperature wins.
- One remaining plausible sensor value is accepted.
- No plausible value means no invented `0 °C`.
- On a later BLE failure, `/Connected` becomes `0` and the previous temperature is retained.

## Victron D-Bus integration

Each battery becomes a service such as `com.victronenergy.temperature.bely1` with the usual temperature paths including `/DeviceInstance`, `/CustomName`, `/Connected`, `/TemperatureType` and `/Temperature`.

Each service uses its own private `dbus.SystemBus()` connection. This avoids duplicate object-path handler errors when several `VeDbusService` instances run in one Python process.

## Important: Victron Bluetooth Sensors integration

On the tested Cerbo GX, Victron's own Bluetooth sensor service could compete with the Bleak client. One symptom was an occasional battery failing to appear after boot.

The clean fix was:

**Settings → Integrations → Bluetooth Sensors → Enable = Off**

This is separate from the main Bluetooth interface used for VictronConnect.

## Installing Bleak on Venus OS

The tested Cerbo GX did not provide `pip`, so Bleak and its dependencies were prepared on another Linux machine:

```bash
mkdir -p ~/bely_ble_deps
python3 -m pip install --target ~/bely_ble_deps bleak
```

Copy that directory to `/data/bely_ble_deps` on the GX device and verify:

```bash
PYTHONPATH=/data/bely_ble_deps python3 -c "import bleak; print('Bleak OK')"
```

## Install the bridge

Copy the script to `/data/bely_victron_temperature_bridge.py`.

Create `/data/bely-temperature-service/run`:

```sh
#!/bin/sh
exec env PYTHONPATH=/data/bely_ble_deps \
    python3 /data/bely_victron_temperature_bridge.py 2>&1
```

Then:

```bash
chmod +x /data/bely-temperature-service/run
```

### Start automatically

Victron documents `/data/rc.local` as a startup hook for custom code that must survive firmware updates. Changes directly under `/service` do not persist on their own.

Add to `/data/rc.local`:

```sh
#!/bin/sh
if [ ! -e /service/bely-temperature ]; then
    ln -s /data/bely-temperature-service /service/bely-temperature
fi
```

Then:

```bash
chmod +x /data/rc.local
ln -s /data/bely-temperature-service /service/bely-temperature
svstat /service/bely-temperature
```

A successful service should report `up`.

## Firmware updates

Victron states that firmware updates replace the root filesystem while `/data` is preserved. Root passwords on the root filesystem are reset by firmware updates. Keep the bridge and its dependencies under `/data` and verify the service after an OS update.

## Limitations

- Tested with one BeLY battery family only.
- Uses fixed BLE addresses, not name-based discovery.
- Does not validate the JBD packet checksum.
- Does not control charging or discharging.
- No claim that every BeLY battery uses the same BLE protocol.
- Independent community project, not an official Victron or BeLY product.

## Safety

This is monitoring software, not a battery safety system. It must not replace the BMS or other required protection.

## References

- Victron Cerbo GX configuration manual: https://www.victronenergy.com/media/pg/Cerbo_GX/en/configuration.html
- Victron Venus OS root/customisation documentation: https://www.victronenergy.com/live/ccgx%3Aroot_access

## License

MIT

---

Built from a working installation, then left alone because a running system has suffered enough.
