"""
End-to-end tests driving the real CLI as a subprocess.

The only faked components are the ``fastboot``/``adb`` binaries and the
release server (see conftest.py) — argument parsing, downloads over
HTTP, real ssh-keygen signature verification, archive extraction, the
interactive prompts, and the full bootloader state machine all run for
real. These tests are hermetic: no network, no hardware.
"""

from pathlib import Path

import pytest
from harness import DEVICE, VERSION, FakeDevice

pytestmark = pytest.mark.e2e


def _first_index(calls: list[str], prefix: str) -> int:
    for i, call in enumerate(calls):
        if call.startswith(prefix):
            return i
    raise AssertionError(f"no call starting with {prefix!r} in {calls}")


class TestDownloadAndVerify:

    def test_download_verify_only_succeeds(self, run_cli, work_dir: Path):
        result = run_cli(DEVICE)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "Signature is valid" in result.stdout
        assert "HOW TO FLASH" in result.stdout
        assert (work_dir / f"{DEVICE}-install-{VERSION}.zip").exists()
        assert (work_dir / f"{DEVICE}-install-{VERSION}.zip.sig").exists()
        assert (work_dir / "allowed_signers").exists()

    def test_tampered_image_aborts_before_flashing(
        self, run_cli, work_dir: Path, fake_device: FakeDevice
    ):
        # Pre-seed a corrupted factory image; the downloader keeps
        # existing files, so verification runs against the bad bytes.
        (work_dir / f"{DEVICE}-install-{VERSION}.zip").write_bytes(
            b"tampered payload"
        )

        result = run_cli(DEVICE, "--flash", answers="yes\n")

        assert result.returncode == 1
        assert "Signature verification FAILED" in result.stdout
        assert "do not flash unverified" in result.stdout
        # The device must never have been touched beyond tool checks.
        assert not any(
            "flashing" in call or "flash " in call
            for call in fake_device.calls
        )
        assert fake_device.bootloader_state == "locked"


class TestFlashFlow:

    def test_full_flash_unlocks_flashes_and_relocks(
        self, run_cli, fake_device: FakeDevice
    ):
        # Prompts: pre-flash checklist, unlock confirm, lock confirm.
        result = run_cli(DEVICE, "--flash", answers="yes\nyes\nyes\n")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "Signature is valid" in result.stdout
        assert "Bootloader is unlocked — verified" in result.stdout
        assert fake_device.bootloader_state == "locked"

        calls = fake_device.calls
        unlock = _first_index(calls, "fastboot flashing unlock")
        flash = _first_index(calls, "fastboot flash bootloader")
        lock = _first_index(calls, "fastboot flashing lock")
        assert unlock < flash < lock

    def test_manual_bootloader_mode_flashes_without_locking(
        self, run_cli, fake_device: FakeDevice
    ):
        fake_device.set_bootloader_state("unlocked")

        result = run_cli(
            DEVICE,
            "--flash",
            "--no-bootloader-mgmt",
            answers="yes\n",
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "prerequisite met" in result.stdout
        # The tool must remind the user, not lock on their behalf.
        assert "fastboot flashing lock" in result.stdout
        assert fake_device.bootloader_state == "unlocked"
        assert not any(
            call.startswith("fastboot flashing lock")
            for call in fake_device.calls
        )

    def test_declining_checklist_cancels_cleanly(
        self, run_cli, fake_device: FakeDevice
    ):
        result = run_cli(DEVICE, "--flash", answers="no\n")

        assert result.returncode == 0
        assert "cancelled" in result.stdout.lower()
        assert fake_device.bootloader_state == "locked"
        assert not any(
            call.startswith("fastboot flash") for call in fake_device.calls
        )


class TestSideloadFlow:

    def test_sideload_ota_update(self, run_cli, fake_device: FakeDevice):
        fake_device.set_adb_mode("sideload")

        result = run_cli(DEVICE, "--sideload", answers="yes\n")

        assert result.returncode == 0, result.stdout + result.stderr
        ota = f"{DEVICE}-ota_update-{VERSION}.zip"
        assert any(
            call.startswith("adb sideload") and ota in call
            for call in fake_device.calls
        )
