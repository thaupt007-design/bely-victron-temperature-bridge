# BeLY LiFePO4 BLE temperatures as native Victron GX / VRM sensors

I have published a small bridge that reads the internal temperature sensors of BeLY LiFePO4 batteries over BLE and exposes each battery as a native Victron temperature device on Venus OS.

The tested system is a Cerbo GX running Venus OS 3.75 with four 12 V / 180 Ah BeLY batteries in series.

The bridge uses the JBD-compatible BLE status command, reads the internal temperatures, selects the highest valid value per battery and publishes it via `VeDbusService`.

A few practical findings may be useful to others:

- Multiple `VeDbusService` instances in one Python process worked reliably when each service used its own private D-Bus connection.
- Direct BLE connections to known stable addresses avoided repeated discovery.
- Victron's built-in Bluetooth Sensors integration could compete with the Bleak client. Disabling **Settings → Integrations → Bluetooth Sensors → Enable** solved an intermittent post-boot connection failure in the tested installation.
- The BLE read runs every 30 minutes. The D-Bus value remains continuously available between reads, so VRM can report the device as recently seen without a new BLE measurement.
- The code never invents `0 °C` when a reading fails.

Repository:

`<INSERT GITHUB REPOSITORY LINK>`

This is monitoring only, not a replacement for the BMS or a battery safety system. It has so far been tested only with this BeLY battery family.

I hope it saves someone else a few evenings of BlueZ, D-Bus and battery archaeology.
