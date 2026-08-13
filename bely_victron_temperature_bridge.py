#!/usr/bin/env python3
"""
BeLY LiFePO4 BLE temperature bridge for Victron Venus OS.

Reads temperature values from BeLY batteries using the JBD-compatible BLE
status command and publishes one native Victron temperature service per
battery on D-Bus.

Tested on Victron Cerbo GX / Venus OS 3.75 with four BeLY 12 V / 180 Ah
LiFePO4 batteries.
"""

import asyncio
import sys
from dataclasses import dataclass

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

sys.path.insert(0, "/data/bely_ble_deps")
sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")

from bleak import BleakClient  # noqa: E402
from vedbus import VeDbusService  # noqa: E402

NOTIFY_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
COMMAND = bytes.fromhex("DD A5 03 00 FF FD 77")

CONNECT_TIMEOUT = 15.0
RESPONSE_TIMEOUT = 8.0
UPDATE_INTERVAL_SECONDS = 1800


@dataclass(frozen=True)
class BatteryConfig:
    suffix: str
    address: str
    instance: int


# USER CONFIGURATION
# Replace the example BLE addresses with your batteries' stable BlueZ addresses.
# DeviceInstance values must be unique on the GX device.
BATTERIES = [
    BatteryConfig("1", "AA:BB:CC:DD:EE:01", 40),
    BatteryConfig("2", "AA:BB:CC:DD:EE:02", 41),
    BatteryConfig("3", "AA:BB:CC:DD:EE:03", 42),
    BatteryConfig("4", "AA:BB:CC:DD:EE:04", 43),
]


def parse_temperatures(data: bytes) -> list[float]:
    if len(data) < 29:
        raise ValueError("BMS response too short")
    if data[0] != 0xDD or data[1] != 0x03:
        raise ValueError("Unexpected BMS response")

    sensor_count = data[26]
    position = 27
    values: list[float] = []

    for _ in range(sensor_count):
        if position + 2 > len(data):
            raise ValueError("Incomplete temperature data")
        raw = int.from_bytes(data[position:position + 2], "big")
        temperature = raw / 10.0 - 273.15
        if -40.0 <= temperature <= 100.0:
            values.append(temperature)
        position += 2

    if not values:
        raise ValueError("No plausible temperature value")
    return values


async def read_one_battery(address: str) -> tuple[list[float], float]:
    response = bytearray()
    complete = asyncio.Event()

    def notification_handler(_sender, data: bytearray) -> None:
        response.extend(data)
        if len(response) >= 4:
            payload_length = response[3]
            expected_length = payload_length + 7
            if len(response) >= expected_length:
                complete.set()

    async with BleakClient(address, timeout=CONNECT_TIMEOUT) as client:
        await client.start_notify(NOTIFY_UUID, notification_handler)
        await client.write_gatt_char(WRITE_UUID, COMMAND)
        try:
            await asyncio.wait_for(complete.wait(), timeout=RESPONSE_TIMEOUT)
        finally:
            await client.stop_notify(NOTIFY_UUID)

    values = parse_temperatures(bytes(response))
    return values, max(values)


class TemperatureService:
    def __init__(self, battery: BatteryConfig):
        self.battery = battery
        self.bus = dbus.SystemBus(private=True)
        self.service = VeDbusService(
            f"com.victronenergy.temperature.bely{battery.suffix}",
            bus=self.bus,
            register=False,
        )
        self.service.add_path("/Mgmt/ProcessName", __file__)
        self.service.add_path("/Mgmt/ProcessVersion", "1.0")
        self.service.add_path("/Mgmt/Connection", "Bluetooth LE")
        self.service.add_path("/DeviceInstance", battery.instance)
        self.service.add_path("/ProductId", 0xFFFF)
        self.service.add_path("/ProductName", f"BeLY Battery {battery.suffix}")
        self.service.add_path("/CustomName", f"LiFePO4 {battery.suffix}")
        self.service.add_path("/Connected", 0)
        self.service.add_path("/TemperatureType", 0)
        self.service.add_path(
            "/Temperature",
            None,
            gettextcallback=lambda _path, value: "---" if value is None else f"{value:.1f} °C",
        )
        self.service.register()

    def update(self, temperature: float) -> None:
        self.service["/Temperature"] = temperature
        self.service["/Connected"] = 1

    def mark_disconnected(self) -> None:
        self.service["/Connected"] = 0

    def current_temperature(self):
        return self.service["/Temperature"]


SERVICES: dict[str, TemperatureService] = {}


async def measurement_round() -> None:
    print("\nStarting BLE measurement round ...")
    for battery in BATTERIES:
        service = SERVICES[battery.suffix]
        try:
            print(f"{battery.suffix}: connecting directly to {battery.address} ...")
            values, selected = await read_one_battery(battery.address)
            service.update(selected)
            sensor_text = ", ".join(f"{value:.1f} °C" for value in values)
            print(f"{battery.suffix}: {sensor_text} -> selected {selected:.1f} °C")
        except Exception as error:
            service.mark_disconnected()
            current = service.current_temperature()
            if current is None:
                print(f"{battery.suffix}: error: {error}")
            else:
                print(f"{battery.suffix}: error ({error}); keeping last value {current:.1f} °C")
        await asyncio.sleep(1.0)
    print("Measurement round finished.")


def run_measurement_round_once() -> bool:
    try:
        asyncio.run(measurement_round())
    except Exception as error:
        print(f"Measurement round aborted: {error}")
    return False


def run_measurement_round_periodic() -> bool:
    try:
        asyncio.run(measurement_round())
    except Exception as error:
        print(f"Measurement round aborted: {error}")
    return True


def main() -> None:
    DBusGMainLoop(set_as_default=True)
    for battery in BATTERIES:
        SERVICES[battery.suffix] = TemperatureService(battery)

    print("BeLY BLE temperature bridge started.")
    print("First measurement starts immediately.")

    GLib.idle_add(run_measurement_round_once)
    GLib.timeout_add_seconds(UPDATE_INTERVAL_SECONDS, run_measurement_round_periodic)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
