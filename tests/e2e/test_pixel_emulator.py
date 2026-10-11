"""
End-to-end tests against a real Android device stack — a booted
Pixel-profile emulator (AVD) reached through real platform-tools.

Run locally with an emulator booted, or in CI via the e2e-emulator job
(reactivecircus/android-emulator-runner). Tests skip cleanly when no
device is attached.

Scope note: an AVD has no real bootloader — it never appears in
``fastboot devices`` and cannot enter recovery sideload mode, so the
flash pipeline itself is covered by the stub harness suite instead.
One test below pins down that emulator limitation explicitly.
"""

import shutil
import subprocess

import pytest

from grapheneos_flasher.core import DeviceManager

pytestmark = pytest.mark.emulator


def _adb(
    *args: str, serial: str | None = None
) -> "subprocess.CompletedProcess[str]":
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


@pytest.fixture(scope="module")
def emulator_serial() -> str:
    """Serial of a booted device/emulator, or skip the module."""
    if shutil.which("adb") is None:
        pytest.skip("adb not on PATH — install Android platform-tools")
    result = _adb("devices")
    serials = [
        line.split("\t")[0]
        for line in result.stdout.splitlines()[1:]
        if line.strip().endswith("\tdevice")
    ]
    if not serials:
        pytest.skip(
            "no booted Android device/emulator attached — "
            "run 'task emulator:start' (see README → End-to-end tests)"
        )
    return serials[0]


class TestRealDeviceStack:

    def test_adb_stack_is_detected(self, emulator_serial: str):
        assert DeviceManager.check_adb_available() is True

    def test_device_reports_hardware_profile(self, emulator_serial: str):
        model = _adb(
            "shell", "getprop", "ro.product.model", serial=emulator_serial
        )
        device = _adb(
            "shell", "getprop", "ro.product.device", serial=emulator_serial
        )
        assert model.returncode == 0
        assert model.stdout.strip(), "device did not report a model"
        # Surface what we ran against in the test output (-v / -rA).
        print(
            f"device: {model.stdout.strip()} "
            f"({device.stdout.strip()}, serial {emulator_serial})"
        )

    def test_booted_device_is_not_in_sideload_mode(self, emulator_serial: str):
        # A booted system must not be mistaken for recovery sideload —
        # this is the guard that stops sideload_update() from firing.
        assert DeviceManager.check_sideload_mode() is False


class TestEmulatorLimitations:

    def test_emulator_never_appears_in_fastboot(self, emulator_serial: str):
        """AVDs have no bootloader: fastboot must see no device.

        This pins down why the flash pipeline is e2e-tested with the
        stub harness rather than an emulator.
        """
        if not DeviceManager.check_fastboot_available():
            pytest.skip("fastboot not on PATH")
        assert DeviceManager.check_fastboot_device() is False
