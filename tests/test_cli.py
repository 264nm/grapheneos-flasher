"""
Unit tests for GrapheneOS Flasher CLI
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from grapheneos_flasher.cli import Device, main, parse_args, validate_device
from grapheneos_flasher.core import FlashResult

# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────────────────────


class TestArgumentParsing:

    def test_parse_args_basic(self):
        with patch.object(sys, "argv", ["grapheneos-flasher", "shiba"]):
            args = parse_args()
        assert args.device == "shiba"
        assert args.flash is False
        assert args.sideload is False
        assert args.version is None
        assert args.work_dir is None
        assert args.bootloader_mgmt is True

    def test_parse_args_with_flash(self):
        with patch.object(
            sys, "argv", ["grapheneos-flasher", "shiba", "--flash"]
        ):
            args = parse_args()
        assert args.flash is True
        assert args.sideload is False

    def test_parse_args_with_sideload(self):
        with patch.object(
            sys, "argv", ["grapheneos-flasher", "shiba", "--sideload"]
        ):
            args = parse_args()
        assert args.sideload is True
        assert args.flash is False

    def test_flash_and_sideload_mutually_exclusive(self):
        with patch.object(
            sys,
            "argv",
            ["grapheneos-flasher", "shiba", "--flash", "--sideload"],
        ):
            with pytest.raises(SystemExit):
                parse_args()

    def test_parse_args_with_version(self):
        with patch.object(
            sys,
            "argv",
            ["grapheneos-flasher", "shiba", "--version", "2026050900"],
        ):
            args = parse_args()
        assert args.version == "2026050900"

    def test_parse_args_with_work_dir(self):
        with patch.object(
            sys,
            "argv",
            ["grapheneos-flasher", "shiba", "--work-dir", "/tmp/test"],
        ):
            args = parse_args()
        assert args.work_dir == Path("/tmp/test")

    def test_no_bootloader_mgmt_flag(self):
        with patch.object(
            sys,
            "argv",
            ["grapheneos-flasher", "shiba", "--flash", "--no-bootloader-mgmt"],
        ):
            args = parse_args()
        assert args.bootloader_mgmt is False

    def test_bootloader_mgmt_default_true(self):
        with patch.object(
            sys, "argv", ["grapheneos-flasher", "shiba", "--flash"]
        ):
            args = parse_args()
        assert args.bootloader_mgmt is True


# ─────────────────────────────────────────────────────────────────────────────
# Device validation
# ─────────────────────────────────────────────────────────────────────────────


class TestDevice:

    def test_known_codenames_resolve(self):
        for codename in ("shiba", "husky", "oriole", "caiman", "tokay"):
            assert Device.from_codename(codename) is not None

    def test_unknown_codename_returns_none(self):
        assert Device.from_codename("unknown") is None

    def test_values_are_display_names(self):
        assert Device.shiba.value == "Pixel 8"
        assert Device.oriole.value == "Pixel 6"
        assert Device.tokay.value == "Pixel 9a"

    def test_codenames_are_lowercase_alpha(self):
        assert all(d.name.isalpha() and d.name.islower() for d in Device)

    def test_codenames_set(self):
        codenames = Device.codenames()
        assert "shiba" in codenames
        assert "unknown" not in codenames

    def test_is_immutable(self):
        with pytest.raises(AttributeError):
            Device.shiba = "something"  # type: ignore[misc]

    def test_str_is_display_name(self):
        # StrEnum: str(member) == member.value (the display name)
        assert str(Device.shiba) == "Pixel 8"

    def test_name_is_codename(self):
        assert Device.shiba.name == "shiba"


class TestDeviceValidation:

    def test_valid_device_codenames(self):
        for device in [
            "shiba",
            "husky",
            "panther",
            "cheetah",
            "oriole",
            "raven",
            "caiman",
        ]:
            assert validate_device(device) is True

    def test_invalid_device_codenames(self):
        # Must be >= 3 chars, all lowercase alphabetic (no digits, dashes, underscores)
        for device in [
            "",
            "a",
            "123",
            "SHIBA",
            "shiba123",
            "device-with-dash",
            "invalid_device",
        ]:
            assert validate_device(device) is False


# ─────────────────────────────────────────────────────────────────────────────
# main() — shared fixture
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_flasher(tmp_path):
    """A pre-wired mock GrapheneOSFlasher instance."""
    m = Mock()
    m.config.device = "shiba"
    m.config.version = "2026050900"
    m.config.ota_filename = "shiba-ota_update-2026050900.zip"
    m.work_dir = tmp_path
    m.prepare_factory_image.return_value = True
    m.prepare_ota.return_value = True
    m.verify_signature.return_value = True
    m.extract_files.return_value = tmp_path / "flash-all.sh"
    m.flash.return_value = FlashResult.SUCCESS
    m.device_manager.sideload_update.return_value = FlashResult.SUCCESS
    return m


def _run_main(argv, flasher_mock):
    """Patch environment and run main(), returning the SystemExit code if raised."""
    with patch.object(sys, "argv", argv):
        with patch(
            "grapheneos_flasher.cli.GrapheneOSFlasher",
            return_value=flasher_mock,
        ):
            with patch(
                "grapheneos_flasher.cli.GrapheneOSFlasher.get_latest_release",
                return_value="2026050900",
            ):
                with patch(
                    "grapheneos_flasher.cli.DeviceManager.check_fastboot_available",
                    return_value=True,
                ):
                    with patch(
                        "grapheneos_flasher.cli.DeviceManager.check_adb_available",
                        return_value=True,
                    ):
                        try:
                            main()
                            return 0
                        except SystemExit as e:
                            return e.code


# ─────────────────────────────────────────────────────────────────────────────
# main() — dry-run (download & verify only)
# ─────────────────────────────────────────────────────────────────────────────


class TestMainDryRun:

    def test_calls_pipeline_without_flash(self, mock_flasher):
        _run_main(["grapheneos-flasher", "shiba"], mock_flasher)

        mock_flasher.prepare_factory_image.assert_called_once()
        mock_flasher.verify_signature.assert_called_once()
        mock_flasher.extract_files.assert_called_once()
        mock_flasher.flash.assert_not_called()

    def test_exits_zero_on_success(self, mock_flasher):
        code = _run_main(["grapheneos-flasher", "shiba"], mock_flasher)
        assert code == 0

    def test_exits_one_on_download_failure(self, mock_flasher):
        mock_flasher.prepare_factory_image.return_value = False
        code = _run_main(["grapheneos-flasher", "shiba"], mock_flasher)
        assert code == 1

    def test_exits_one_on_verification_failure(self, mock_flasher):
        mock_flasher.verify_signature.return_value = False
        code = _run_main(["grapheneos-flasher", "shiba"], mock_flasher)
        assert code == 1

    def test_exits_one_on_extraction_failure(self, mock_flasher):
        mock_flasher.extract_files.return_value = None
        code = _run_main(["grapheneos-flasher", "shiba"], mock_flasher)
        assert code == 1


# ─────────────────────────────────────────────────────────────────────────────
# main() — flash mode
# ─────────────────────────────────────────────────────────────────────────────


class TestMainFlash:

    def test_calls_flash_with_bootloader_mgmt_on(self, mock_flasher, tmp_path):
        script = tmp_path / "flash-all.sh"
        mock_flasher.extract_files.return_value = script

        _run_main(["grapheneos-flasher", "shiba", "--flash"], mock_flasher)

        mock_flasher.flash.assert_called_once_with(
            script, manage_bootloader=True
        )

    def test_calls_flash_with_bootloader_mgmt_off(
        self, mock_flasher, tmp_path
    ):
        script = tmp_path / "flash-all.sh"
        mock_flasher.extract_files.return_value = script

        _run_main(
            ["grapheneos-flasher", "shiba", "--flash", "--no-bootloader-mgmt"],
            mock_flasher,
        )

        mock_flasher.flash.assert_called_once_with(
            script, manage_bootloader=False
        )

    def test_exits_zero_on_success(self, mock_flasher):
        mock_flasher.flash.return_value = FlashResult.SUCCESS
        code = _run_main(
            ["grapheneos-flasher", "shiba", "--flash"], mock_flasher
        )
        assert code == 0

    def test_exits_zero_on_cancelled(self, mock_flasher):
        mock_flasher.flash.return_value = FlashResult.CANCELLED
        code = _run_main(
            ["grapheneos-flasher", "shiba", "--flash"], mock_flasher
        )
        assert code == 0

    def test_exits_one_on_flash_failure(self, mock_flasher):
        mock_flasher.flash.return_value = FlashResult.FAILED_FLASH
        code = _run_main(
            ["grapheneos-flasher", "shiba", "--flash"], mock_flasher
        )
        assert code == 1


# ─────────────────────────────────────────────────────────────────────────────
# main() — sideload mode
# ─────────────────────────────────────────────────────────────────────────────


class TestMainSideload:

    def test_calls_prepare_ota_not_factory_image(self, mock_flasher):
        _run_main(["grapheneos-flasher", "shiba", "--sideload"], mock_flasher)

        mock_flasher.prepare_ota.assert_called_once()
        mock_flasher.prepare_factory_image.assert_not_called()
        mock_flasher.verify_signature.assert_not_called()
        mock_flasher.extract_files.assert_not_called()

    def test_calls_sideload_update(self, mock_flasher, tmp_path):
        # Create the OTA file so the path check passes
        ota = tmp_path / "shiba-ota_update-2026050900.zip"
        ota.write_bytes(b"fake ota")

        _run_main(["grapheneos-flasher", "shiba", "--sideload"], mock_flasher)

        mock_flasher.device_manager.sideload_update.assert_called_once()

    def test_exits_zero_on_success(self, mock_flasher, tmp_path):
        ota = tmp_path / "shiba-ota_update-2026050900.zip"
        ota.write_bytes(b"fake ota")
        mock_flasher.device_manager.sideload_update.return_value = (
            FlashResult.SUCCESS
        )

        code = _run_main(
            ["grapheneos-flasher", "shiba", "--sideload"], mock_flasher
        )
        assert code == 0

    def test_exits_zero_on_cancelled(self, mock_flasher):
        mock_flasher.device_manager.sideload_update.return_value = (
            FlashResult.CANCELLED
        )
        code = _run_main(
            ["grapheneos-flasher", "shiba", "--sideload"], mock_flasher
        )
        assert code == 0

    def test_exits_one_on_ota_download_failure(self, mock_flasher):
        mock_flasher.prepare_ota.return_value = False
        code = _run_main(
            ["grapheneos-flasher", "shiba", "--sideload"], mock_flasher
        )
        assert code == 1
