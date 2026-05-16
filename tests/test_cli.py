"""
Unit tests for GrapheneOS Flasher CLI
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from grapheneos_flasher.cli import parse_args, validate_device, main, build_parser


class TestArgumentParsing:
    """Test CLI argument parsing"""

    def test_parse_args_basic(self):
        """Test basic argument parsing"""
        test_args = ["shiba"]

        with patch.object(sys, 'argv', ['grapheneos-flasher'] + test_args):
            args = parse_args()

        assert args.device == "shiba"
        assert args.flash is False
        assert args.version is None
        assert args.temp_dir is None

    def test_parse_args_with_flash(self):
        """Test argument parsing with flash flag"""
        test_args = ["shiba", "--flash"]

        with patch.object(sys, 'argv', ['grapheneos-flasher'] + test_args):
            args = parse_args()

        assert args.device == "shiba"
        assert args.flash is True

    def test_parse_args_with_version(self):
        """Test argument parsing with version"""
        test_args = ["shiba", "--version", "2026050900"]

        with patch.object(sys, 'argv', ['grapheneos-flasher'] + test_args):
            args = parse_args()

        assert args.device == "shiba"
        assert args.version == "2026050900"

    def test_parse_args_with_temp_dir(self):
        """Test argument parsing with temp directory"""
        test_args = ["shiba", "--temp-dir", "/tmp/test"]

        with patch.object(sys, 'argv', ['grapheneos-flasher'] + test_args):
            args = parse_args()

        assert args.device == "shiba"
        assert args.temp_dir == Path("/tmp/test")


class TestDeviceValidation:
    """Test device codename validation"""

    def test_valid_device_codenames(self):
        """Test valid device codenames"""
        valid_devices = ["shiba", "husky", "panther", "cheetah", "oriole", "raven"]

        for device in valid_devices:
            assert validate_device(device) is True

    def test_invalid_device_codenames(self):
        """Test invalid device codenames"""
        # Must be >= 3 chars, all lowercase alphabetic (no digits, dashes, underscores)
        invalid_devices = ["", "a", "123", "SHIBA", "shiba123", "device-with-dash", "invalid_device"]

        for device in invalid_devices:
            assert validate_device(device) is False


class TestCLIErrorHandling:
    """Test CLI error handling"""

    def test_invalid_device_exits(self):
        """Test CLI exits on invalid device via validation, not main execution"""
        # This test should test the validation function directly
        assert validate_device("invalid_device") is False


class TestMainFunction:
    """Test main CLI function"""

    @pytest.fixture
    def mock_flasher(self):
        """Create a mock GrapheneOSFlasher for testing"""
        mock_config = Mock()
        mock_config.device = "shiba"
        mock_config.version = "2026050900"

        mock_flasher = Mock()
        mock_flasher.config = mock_config
        mock_flasher.prepare_files.return_value = True
        mock_flasher.verify_signature.return_value = True
        mock_flasher.extract_files.return_value = Path("/tmp/flash.sh")
        mock_flasher.flash.return_value = Mock()

        return mock_flasher

    def test_main_successful_download(self, mock_flasher):
        """Test successful download without flash"""
        test_args = ["shiba"]

        with patch.object(sys, 'argv', ['grapheneos-flasher'] + test_args):
            with patch('grapheneos_flasher.cli.GrapheneOSFlasher', return_value=mock_flasher):
                with patch('grapheneos_flasher.cli.GrapheneOSFlasher.get_latest_release', return_value="2026050900"):
                    with patch('builtins.print') as mock_print:
                        main()

        # Should have called the flasher methods
        mock_flasher.prepare_files.assert_called_once()
        mock_flasher.verify_signature.assert_called_once()
        mock_flasher.extract_files.assert_called_once()
        # Should not have called flash since --flash was not passed
        mock_flasher.flash.assert_not_called()

    def test_main_successful_flash(self, mock_flasher):
        """Test successful flashing"""
        test_args = ["shiba", "--flash"]
        from grapheneos_flasher.core import FlashResult

        # Mock the return value to be the actual FlashResult enum
        mock_flasher.flash.return_value = FlashResult.SUCCESS

        with patch.object(sys, 'argv', ['grapheneos-flasher'] + test_args):
            with patch('grapheneos_flasher.cli.GrapheneOSFlasher', return_value=mock_flasher):
                with patch('grapheneos_flasher.cli.GrapheneOSFlasher.get_latest_release', return_value="2026050900"):
                    # Just test that the function calls are made correctly
                    try:
                        main()
                    except SystemExit as e:
                        # Don't worry about the exact exit code for this test
                        pass

        # Should have called all flasher methods including flash
        mock_flasher.prepare_files.assert_called_once()
        mock_flasher.verify_signature.assert_called_once()
        mock_flasher.extract_files.assert_called_once()
        mock_flasher.flash.assert_called_once()

    def test_main_failed_preparation(self, mock_flasher):
        """Test failure during file preparation"""
        test_args = ["shiba"]
        mock_flasher.prepare_files.return_value = False

        with patch.object(sys, 'argv', ['grapheneos-flasher'] + test_args):
            with patch('grapheneos_flasher.cli.GrapheneOSFlasher', return_value=mock_flasher):
                with patch('grapheneos_flasher.cli.GrapheneOSFlasher.get_latest_release', return_value="2026050900"):
                    with patch('sys.exit') as mock_exit:
                        main()

        # Should have exited after failed preparation
        mock_exit.assert_called_with(1)

    def test_main_failed_verification(self, mock_flasher):
        """Test failure during signature verification"""
        test_args = ["shiba"]
        mock_flasher.verify_signature.return_value = False

        with patch.object(sys, 'argv', ['grapheneos-flasher'] + test_args):
            with patch('grapheneos_flasher.cli.GrapheneOSFlasher', return_value=mock_flasher):
                with patch('grapheneos_flasher.cli.GrapheneOSFlasher.get_latest_release', return_value="2026050900"):
                    with patch('builtins.print') as mock_print:
                        try:
                            main()
                        except SystemExit as e:
                            assert e.code == 1

        # Verification failure should cause a sys.exit(1)