"""
Unit tests for GrapheneOS Flasher core functionality
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from grapheneos_flasher.core import (
    DefaultFileHandler,
    DeviceManager,
    DownloadConfig,
    FlashResult,
    GrapheneOSFlasher,
    SecurityVerifier,
)

# ─────────────────────────────────────────────────────────────────────────────
# DownloadConfig
# ─────────────────────────────────────────────────────────────────────────────


class TestDownloadConfig:

    def test_init(self):
        config = DownloadConfig("shiba", "2026050900")
        assert config.device == "shiba"
        assert config.version == "2026050900"
        assert config.base_url == "https://releases.grapheneos.org"

    def test_url_properties(self):
        config = DownloadConfig("shiba", "2026050900")
        assert (
            config.install_url
            == "https://releases.grapheneos.org/shiba-install-2026050900.zip"
        )
        assert (
            config.signature_url
            == "https://releases.grapheneos.org/shiba-install-2026050900.zip.sig"
        )
        assert (
            config.ota_url
            == "https://releases.grapheneos.org/shiba-ota_update-2026050900.zip"
        )

    def test_filename_properties(self):
        config = DownloadConfig("shiba", "2026050900")
        assert config.install_filename == "shiba-install-2026050900.zip"
        assert config.signature_filename == "shiba-install-2026050900.zip.sig"
        assert config.ota_filename == "shiba-ota_update-2026050900.zip"

    def test_custom_base_url(self):
        config = DownloadConfig(
            "shiba", "2026050900", base_url="http://example.com"
        )
        assert (
            config.install_url
            == "http://example.com/shiba-install-2026050900.zip"
        )


# ─────────────────────────────────────────────────────────────────────────────
# DefaultFileHandler
# ─────────────────────────────────────────────────────────────────────────────


class TestDefaultFileHandler:

    def test_download_file_success(self):
        handler = DefaultFileHandler()
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test.txt"
            with patch("urllib.request.urlretrieve") as mock_retrieve:
                mock_retrieve.return_value = None
                result = handler.download_file(
                    "http://example.com/file.txt", dest
                )
            assert result is True
            mock_retrieve.assert_called_once()

    def test_download_file_network_error(self):
        handler = DefaultFileHandler()
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test.txt"
            with patch("urllib.request.urlretrieve") as mock_retrieve:
                from urllib.error import URLError

                mock_retrieve.side_effect = URLError("Network error")
                result = handler.download_file(
                    "http://example.com/file.txt", dest
                )
            assert result is False
            assert not dest.exists()

    def test_download_file_http_404(self):
        handler = DefaultFileHandler()
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test.txt"
            with patch("urllib.request.urlretrieve") as mock_retrieve:
                from urllib.error import HTTPError

                mock_retrieve.side_effect = HTTPError(
                    "http://example.com/file.txt", 404, "Not Found", {}, None
                )
                result = handler.download_file(
                    "http://example.com/file.txt", dest
                )
            assert result is False

    def test_download_skips_existing_file(self):
        handler = DefaultFileHandler()
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "existing.txt"
            dest.write_text("already here")
            with patch("urllib.request.urlretrieve") as mock_retrieve:
                result = handler.download_file(
                    "http://example.com/existing.txt", dest
                )
            assert result is True
            mock_retrieve.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# SecurityVerifier
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurityVerifier:

    def test_verify_signature_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sig_file = tmp_path / "test.sig"
            data_file = tmp_path / "test.zip"
            data_file.write_bytes(b"test data")
            sig_file.write_bytes(b"dummy signature")
            allowed_signers = tmp_path / "allowed_signers"
            allowed_signers.write_text("test key")

            verifier = SecurityVerifier(allowed_signers)
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Good signature"
            mock_result.stderr = ""

            with patch("subprocess.run", return_value=mock_result):
                result = verifier.verify_signature(sig_file, data_file)

        assert result is True

    def test_verify_signature_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sig_file = tmp_path / "test.sig"
            data_file = tmp_path / "test.zip"
            data_file.write_bytes(b"test data")
            sig_file.write_bytes(b"bad signature")
            allowed_signers = tmp_path / "allowed_signers"
            allowed_signers.write_text("test key")

            verifier = SecurityVerifier(allowed_signers)
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Signature verification failed"

            with patch("subprocess.run", return_value=mock_result):
                result = verifier.verify_signature(sig_file, data_file)

        assert result is False

    def test_verify_signature_no_ssh_keygen(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            data_file = tmp_path / "test.zip"
            data_file.write_bytes(b"test data")
            sig_file = tmp_path / "test.sig"
            sig_file.write_bytes(b"sig")
            allowed_signers = tmp_path / "allowed_signers"
            allowed_signers.write_text("key")

            verifier = SecurityVerifier(allowed_signers)
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = verifier.verify_signature(sig_file, data_file)

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# DeviceManager — fastboot helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestDeviceManagerFastboot:

    def test_check_fastboot_device_found(self):
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "device_123\tfastboot"
        with patch("subprocess.run", return_value=mock_result):
            assert DeviceManager.check_fastboot_device() is True

    def test_check_fastboot_device_not_found(self):
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            assert DeviceManager.check_fastboot_device() is False

    def test_check_fastboot_device_missing_binary(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert DeviceManager.check_fastboot_device() is False

    def test_get_bootloader_state_unlocked(self):
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = "unlocked: yes\nOKAY [  0.001s]"
        with patch("subprocess.run", return_value=mock_result):
            assert DeviceManager.get_bootloader_state() == "unlocked"

    def test_get_bootloader_state_locked(self):
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = "unlocked: no\nOKAY [  0.001s]"
        with patch("subprocess.run", return_value=mock_result):
            assert DeviceManager.get_bootloader_state() == "locked"

    def test_get_bootloader_state_unknown(self):
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = "some unexpected output"
        with patch("subprocess.run", return_value=mock_result):
            assert DeviceManager.get_bootloader_state() is None

    def test_get_bootloader_state_no_fastboot(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert DeviceManager.get_bootloader_state() is None

    def test_wait_for_fastboot_succeeds(self):
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "device_123\tfastboot"
        with patch("subprocess.run", return_value=mock_result):
            with patch("time.sleep"):
                assert DeviceManager.wait_for_fastboot(timeout=5) is True

    def test_wait_for_fastboot_times_out(self):
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            with patch("time.sleep"):
                assert DeviceManager.wait_for_fastboot(timeout=3) is False

    def test_wait_for_fastboot_no_binary(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with patch("time.sleep"):
                assert DeviceManager.wait_for_fastboot(timeout=3) is False


# ─────────────────────────────────────────────────────────────────────────────
# DeviceManager — bootloader unlock / lock
# ─────────────────────────────────────────────────────────────────────────────


class TestBootloaderManagement:

    def test_unlock_bootloader_user_cancels(self):
        with patch("builtins.input", return_value="no"):
            assert DeviceManager.unlock_bootloader() is False

    def test_unlock_bootloader_fastboot_not_found(self):
        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                assert DeviceManager.unlock_bootloader() is False

    def test_unlock_bootloader_command_fails(self):
        mock_result = Mock()
        mock_result.returncode = 1
        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", return_value=mock_result):
                assert DeviceManager.unlock_bootloader() is False

    def test_unlock_bootloader_success(self):
        unlock_result = Mock(returncode=0)
        devices_result = Mock(returncode=0, stdout="ABC123\tfastboot")
        getvar_result = Mock(returncode=0, stdout="", stderr="unlocked: yes\n")

        call_count = 0

        def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "flashing" in cmd and "unlock" in cmd:
                return unlock_result
            if "devices" in cmd:
                return devices_result
            if "getvar" in cmd:
                return getvar_result
            return Mock(returncode=0, stdout="", stderr="")

        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", side_effect=side_effect):
                with patch("time.sleep"):
                    result = DeviceManager.unlock_bootloader()

        assert result is True

    def test_lock_bootloader_user_cancels(self):
        # User declines — should return False but not raise
        with patch("builtins.input", return_value="no"):
            assert DeviceManager.lock_bootloader() is False

    def test_lock_bootloader_fastboot_not_found(self):
        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                assert DeviceManager.lock_bootloader() is False

    def test_lock_bootloader_device_rebooted(self):
        # returncode=0 from lock, device gone (None state) — expected success
        lock_result = Mock(returncode=0)
        getvar_result = Mock(returncode=0, stdout="", stderr="some unexpected")

        def side_effect(cmd, **kwargs):
            if "flashing" in cmd and "lock" in cmd:
                return lock_result
            return getvar_result

        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", side_effect=side_effect):
                with patch("time.sleep"):
                    result = DeviceManager.lock_bootloader()

        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# DeviceManager — flash_device
# ─────────────────────────────────────────────────────────────────────────────


class TestFlashDevice:

    def test_user_cancelled(self):
        with patch("builtins.input", return_value="no"):
            result = DeviceManager.flash_device(Path("/fake/flash-all.sh"))
        assert result == FlashResult.CANCELLED

    def test_no_device_in_fastboot(self):
        no_device = Mock(returncode=0, stdout="")
        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", return_value=no_device):
                result = DeviceManager.flash_device(Path("/fake/flash-all.sh"))
        assert result == FlashResult.NO_DEVICE

    def test_locked_bootloader_without_management_fails(self):
        fastboot_devices = Mock(returncode=0, stdout="ABC\tfastboot")
        getvar_locked = Mock(returncode=0, stdout="", stderr="unlocked: no")

        def side_effect(cmd, **kwargs):
            if cmd[1] == "devices":
                return fastboot_devices
            if cmd[1] == "getvar":
                return getvar_locked
            return Mock(returncode=0)

        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", side_effect=side_effect):
                result = DeviceManager.flash_device(
                    Path("/fake/flash-all.sh"), manage_bootloader=False
                )

        assert result == FlashResult.FAILED_FLASH

    def test_unlocked_bootloader_without_management_proceeds(self):
        fastboot_devices = Mock(returncode=0, stdout="ABC\tfastboot")
        getvar_unlocked = Mock(returncode=0, stdout="", stderr="unlocked: yes")
        flash_success = Mock(returncode=0)

        def side_effect(cmd, **kwargs):
            if cmd == ["fastboot", "devices"]:
                return fastboot_devices
            if cmd == ["fastboot", "getvar", "unlocked"]:
                return getvar_unlocked
            if cmd[0] == "bash":
                return flash_success
            return Mock(returncode=0)

        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", side_effect=side_effect):
                with patch(
                    "grapheneos_flasher.core.DeviceManager.lock_bootloader",
                    return_value=False,
                ):
                    result = DeviceManager.flash_device(
                        Path("/fake/flash-all.sh"), manage_bootloader=False
                    )

        assert result == FlashResult.SUCCESS


# ─────────────────────────────────────────────────────────────────────────────
# DeviceManager — sideload
# ─────────────────────────────────────────────────────────────────────────────


class TestSideload:

    def test_sideload_user_cancelled(self):
        with patch("builtins.input", return_value="no"):
            result = DeviceManager.sideload_update(Path("/fake/update.zip"))
        assert result == FlashResult.CANCELLED

    def test_sideload_timeout(self):
        no_sideload = Mock(returncode=0, stdout="")
        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", return_value=no_sideload):
                with patch("time.sleep"):
                    result = DeviceManager.sideload_update(
                        Path("/fake/update.zip")
                    )
        assert result == FlashResult.NOT_IN_SIDELOAD

    def test_sideload_adb_not_found(self):
        # Device reports as in sideload mode, but 'adb sideload' binary is missing
        in_sideload = Mock(returncode=0, stdout="ABC\tsideload")

        def side_effect(cmd, **kwargs):
            if cmd == ["adb", "sideload", "/fake/update.zip"]:
                raise FileNotFoundError
            return in_sideload

        with patch("builtins.input", return_value="yes"):
            with patch("subprocess.run", side_effect=side_effect):
                result = DeviceManager.sideload_update(
                    Path("/fake/update.zip")
                )
        assert result == FlashResult.FAILED_SIDELOAD


# ─────────────────────────────────────────────────────────────────────────────
# GrapheneOSFlasher
# ─────────────────────────────────────────────────────────────────────────────


class TestGrapheneOSFlasher:

    def test_init_defaults_to_cwd(self):
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)
        assert flasher.work_dir == Path.cwd()
        assert flasher.work_dir.exists()

    def test_init_custom_work_dir(self):
        config = DownloadConfig("shiba", "2026050900")
        with tempfile.TemporaryDirectory() as tmpdir:
            flasher = GrapheneOSFlasher(config, work_dir=Path(tmpdir))
            assert flasher.work_dir == Path(tmpdir)

    def test_get_latest_release_success(self):
        mock_atom = """
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry><title>GrapheneOS 2026050900</title></entry>
        </feed>
        """
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = mock_atom.encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response
            version = GrapheneOSFlasher.get_latest_release()
        assert version == "2026050900"

    def test_prepare_factory_image_success(self):
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)
        mock_handler = Mock()
        mock_handler.download_file.return_value = True
        flasher.file_handler = mock_handler

        result = flasher.prepare_factory_image()

        assert result is True
        # allowed_signers + install zip + .sig = 3 downloads
        assert mock_handler.download_file.call_count == 3

    def test_prepare_factory_image_download_failure(self):
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)
        mock_handler = Mock()
        mock_handler.download_file.return_value = False
        flasher.file_handler = mock_handler

        assert flasher.prepare_factory_image() is False

    def test_prepare_ota_success(self):
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)
        mock_handler = Mock()
        mock_handler.download_file.return_value = True
        flasher.file_handler = mock_handler

        result = flasher.prepare_ota()

        assert result is True
        assert mock_handler.download_file.call_count == 1

    def test_prepare_ota_failure(self):
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)
        mock_handler = Mock()
        mock_handler.download_file.return_value = False
        flasher.file_handler = mock_handler

        assert flasher.prepare_ota() is False

    def test_verify_signature_not_initialized(self):
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)
        flasher.security_verifier = None
        assert flasher.verify_signature() is False

    def test_flash_passes_manage_bootloader(self):
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)
        script = Path("/fake/flash-all.sh")

        with patch.object(
            flasher.device_manager,
            "flash_device",
            return_value=FlashResult.SUCCESS,
        ) as mock_flash:
            flasher.flash(script, manage_bootloader=False)
            mock_flash.assert_called_once_with(script, False)


# ─────────────────────────────────────────────────────────────────────────────
# FlashResult
# ─────────────────────────────────────────────────────────────────────────────


class TestFlashResult:

    def test_enum_members(self):
        assert FlashResult.SUCCESS.value == "success"
        assert FlashResult.FAILED_SIGNATURE.value == "signature_failed"
        assert FlashResult.FAILED_DOWNLOAD.value == "download_failed"
        assert FlashResult.FAILED_FLASH.value == "flash_failed"
        assert FlashResult.FAILED_SIDELOAD.value == "sideload_failed"
        assert FlashResult.NO_DEVICE.value == "no_device"
        assert FlashResult.NOT_IN_SIDELOAD.value == "not_in_sideload"
        assert FlashResult.CANCELLED.value == "cancelled"
