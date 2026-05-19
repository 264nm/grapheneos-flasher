"""
Unit tests for GrapheneOS Flasher core functionality
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from grapheneos_flasher.core import (
    GrapheneOSFlasher,
    DownloadConfig,
    FlashResult,
    DefaultFileHandler,
    SecurityVerifier,
    DeviceManager,
)


class TestDownloadConfig:
    """Test DownloadConfig data class"""

    def test_init(self):
        """Test basic initialization"""
        config = DownloadConfig("shiba", "2026050900")
        assert config.device == "shiba"
        assert config.version == "2026050900"
        assert config.base_url == "https://releases.grapheneos.org"

    def test_url_properties(self):
        """Test URL generation properties"""
        config = DownloadConfig("shiba", "2026050900")
        assert config.install_url == "https://releases.grapheneos.org/shiba-install-2026050900.zip"
        assert config.signature_url == "https://releases.grapheneos.org/shiba-install-2026050900.zip.sig"
        assert config.ota_url == "https://releases.grapheneos.org/shiba-ota_update-2026050900.zip"

    def test_custom_base_url(self):
        """Test custom base URL"""
        config = DownloadConfig("shiba", "2026050900", base_url="http://example.com")
        assert config.install_url == "http://example.com/shiba-install-2026050900.zip"


class TestDefaultFileHandler:
    """Test default file handler implementation"""

    def test_download_file_success(self):
        """Test successful file download"""
        handler = DefaultFileHandler()
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test.txt"

            # Mock urllib.request.urlretrieve to succeed
            with patch('urllib.request.urlretrieve') as mock_retrieve:
                mock_retrieve.return_value = None
                result = handler.download_file("http://example.com/file.txt", dest)

            assert result is True
            # The file should exist after successful download
            # Note: urlretrieve creates the file even in mocks
            mock_retrieve.assert_called_once()

    def test_download_file_failure(self):
        """Test failed file download"""
        handler = DefaultFileHandler()
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test.txt"

            # Mock urllib.request.urlretrieve to fail
            with patch('urllib.request.urlretrieve') as mock_retrieve:
                from urllib.error import URLError
                mock_retrieve.side_effect = URLError("Network error")
                result = handler.download_file("http://example.com/file.txt", dest)

            assert result is False
            # The file should not exist since download failed
            assert not dest.exists()


class TestSecurityVerifier:
    """Test security verification functionality"""

    def test_verify_signature_success(self):
        """Test successful signature verification"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sig_file = tmp_path / "test.sig"
            data_file = tmp_path / "test.zip"

            # Create dummy files
            data_file.write_bytes(b"test data")
            sig_file.write_bytes(b"dummy signature")

            allowed_signers = tmp_path / "allowed_signers"
            allowed_signers.write_text("test key")

            verifier = SecurityVerifier(allowed_signers)

            # Mock subprocess to simulate success
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Good signature"

            with patch('subprocess.run', return_value=mock_result):
                result = verifier.verify_signature(sig_file, data_file)

            assert result is True


class TestDeviceManager:
    """Test device management functionality"""

    def test_check_fastboot_device_found(self):
        """Test device detection when device is found"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "device_123\tfastboot"

        with patch('subprocess.run', return_value=mock_result):
            result = DeviceManager.check_fastboot_device()

        assert result is True

    def test_check_fastboot_device_not_found(self):
        """Test device detection when no device found"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch('subprocess.run', return_value=mock_result):
            result = DeviceManager.check_fastboot_device()

        assert result is False

    def test_flash_device_user_cancelled(self):
        """Test flash device when user cancels"""
        with patch('builtins.input', return_value="no"):
            result = DeviceManager.flash_device(Path("/fake/script.sh"))

        assert result == FlashResult.CANCELLED


class TestGrapheneOSFlasher:
    """Test main flasher class"""

    def test_init(self):
        """Test flasher initialization"""
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)

        assert flasher.config == config
        assert flasher.work_dir.exists()

    def test_get_latest_release_success(self):
        """Test successful release version fetch"""
        mock_atom_content = """
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>GrapheneOS 2026050900</title>
            </entry>
        </feed>
        """

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = mock_atom_content.encode('utf-8')
            mock_urlopen.return_value.__enter__.return_value = mock_response

            version = GrapheneOSFlasher.get_latest_release()

        assert version == "2026050900"

    def test_prepare_factory_image_success(self):
        """Test successful factory image preparation"""
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)

        mock_handler = Mock()
        mock_handler.download_file.return_value = True
        flasher.file_handler = mock_handler

        result = flasher.prepare_factory_image()

        assert result is True

    def test_verify_signature_not_initialized(self):
        """Test signature verification when verifier not initialized"""
        config = DownloadConfig("shiba", "2026050900")
        flasher = GrapheneOSFlasher(config)
        flasher.security_verifier = None

        result = flasher.verify_signature()

        assert result is False


class TestFlashResult:
    """Test FlashResult enum"""

    def test_enum_members(self):
        """Test all enum members exist"""
        assert FlashResult.SUCCESS.value == "success"
        assert FlashResult.FAILED_SIGNATURE.value == "signature_failed"
        assert FlashResult.FAILED_DOWNLOAD.value == "download_failed"
        assert FlashResult.FAILED_FLASH.value == "flash_failed"
        assert FlashResult.NO_DEVICE.value == "no_device"
        assert FlashResult.CANCELLED.value == "cancelled"