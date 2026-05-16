"""
Core functionality for GrapheneOS Flasher
"""

import sys
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from xml.etree import ElementTree


# ─────────────────────────────────────────────────────────────────────────────
# Terminal formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

_W = 66  # output width


def _rule(char: str = "─") -> str:
    return char * _W


def _block(text: str) -> None:
    """Print a pre-formatted multi-line instruction block (one print call)."""
    print(text.strip("\n"))


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗  {msg}")


def _info(msg: str) -> None:
    print(f"  →  {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠  {msg}")


def _step(n: int, total: int, title: str) -> None:
    print(f"\n{_rule()}\n  Step {n}/{total} — {title}\n{_rule()}")


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

class FlashResult(Enum):
    """Possible outcomes of the flashing or sideloading process"""
    SUCCESS = "success"
    FAILED_SIGNATURE = "signature_failed"
    FAILED_DOWNLOAD = "download_failed"
    FAILED_FLASH = "flash_failed"
    FAILED_SIDELOAD = "sideload_failed"
    NO_DEVICE = "no_device"
    NOT_IN_RECOVERY = "not_in_recovery"
    NOT_IN_SIDELOAD = "not_in_sideload"
    CANCELLED = "cancelled"


@dataclass
class DownloadConfig:
    """Configuration for downloading GrapheneOS artifacts"""
    device: str
    version: str
    base_url: str = "https://releases.grapheneos.org"

    @property
    def install_url(self) -> str:
        return f"{self.base_url}/{self.device}-install-{self.version}.zip"

    @property
    def signature_url(self) -> str:
        return f"{self.install_url}.sig"

    @property
    def ota_url(self) -> str:
        return f"{self.base_url}/{self.device}-ota_update-{self.version}.zip"

    @property
    def install_filename(self) -> str:
        return f"{self.device}-install-{self.version}.zip"

    @property
    def signature_filename(self) -> str:
        return f"{self.device}-install-{self.version}.zip.sig"

    @property
    def ota_filename(self) -> str:
        return f"{self.device}-ota_update-{self.version}.zip"


# ─────────────────────────────────────────────────────────────────────────────
# File operations
# ─────────────────────────────────────────────────────────────────────────────

class FileHandler(ABC):
    """Abstract base class for file operations"""

    @abstractmethod
    def download_file(self, url: str, destination: Path) -> bool:
        """Download a file from URL to destination"""
        pass

    @abstractmethod
    def extract_archive(self, archive_path: Path, destination: Path) -> bool:
        """Extract archive to destination"""
        pass


class DefaultFileHandler(FileHandler):
    """Default implementation of file operations"""

    def download_file(self, url: str, destination: Path) -> bool:
        """Download a file with progress indication"""
        filename = destination.name
        _info(f"Downloading {filename} …")
        try:
            urllib.request.urlretrieve(url, destination)
            try:
                size_mb = destination.stat().st_size / (1024 * 1024)
                size_str = f"  ({size_mb:.0f} MB)" if size_mb >= 1.0 else ""
            except OSError:
                size_str = ""
            _ok(f"{filename}{size_str}")
            return True
        except urllib.error.HTTPError as e:
            _fail(f"HTTP {e.code} — could not download {filename}")
            if e.code == 404:
                _block("""
       The version or device codename may not exist.
       Check: https://grapheneos.org/releases
""")
            return False
        except urllib.error.URLError as e:
            _fail(f"Network error downloading {filename}: {e.reason}")
            _block("""
       Check your internet connection and try again.
""")
            return False

    def extract_archive(self, archive_path: Path, destination: Path) -> bool:
        """Extract the factory image zip"""
        _info(f"Extracting {archive_path.name} …")
        try:
            subprocess.run(
                ["tar", "xf", str(archive_path)],
                cwd=destination,
                check=True,
                capture_output=True,
            )
            _ok(f"Extracted to: {destination}")
            return True
        except subprocess.CalledProcessError as e:
            _fail(f"Extraction failed: {e.stderr.decode().strip() if e.stderr else e}")
            return False
        except FileNotFoundError:
            _fail("'tar' not found — please install it and try again.")
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Signature verification
# ─────────────────────────────────────────────────────────────────────────────

class SecurityVerifier:
    """Handles cryptographic verification of downloaded files"""

    GRAPHENEOS_IDENTITY = "contact@grapheneos.org"
    GRAPHENEOS_NAMESPACE = "factory images"

    def __init__(self, allowed_signers_path: Path):
        self.allowed_signers_path = allowed_signers_path

    def verify_signature(self, signature_path: Path, file_path: Path) -> bool:
        """
        Verify the factory image signature using ssh-keygen.

        Runs the same command as the official GrapheneOS CLI guide:
          ssh-keygen -Y verify -f allowed_signers \\
            -I contact@grapheneos.org -n "factory images" \\
            -s <device>-install-<version>.zip.sig \\
            < <device>-install-<version>.zip
        """
        _info("Verifying cryptographic signature against GrapheneOS public key …")
        try:
            with open(file_path, "rb") as f:
                result = subprocess.run(
                    [
                        "ssh-keygen", "-Y", "verify",
                        "-f", str(self.allowed_signers_path),
                        "-I", self.GRAPHENEOS_IDENTITY,
                        "-n", self.GRAPHENEOS_NAMESPACE,
                        "-s", str(signature_path),
                    ],
                    stdin=f,
                    capture_output=True,
                    text=True,
                )

            if result.returncode == 0:
                _ok("Signature is valid — files are authentic and unmodified")
                return True

            _fail("Signature verification FAILED")
            _block(f"""
  The downloaded files may be corrupted or tampered with.
  Do NOT flash these images.
{"  ssh-keygen: " + result.stderr.strip() if result.stderr.strip() else ""}
""")
            return False

        except FileNotFoundError:
            _fail("'ssh-keygen' not found")
            _block("""
  OpenSSH is required for signature verification.
  Install it with your package manager:
    macOS  : built-in (update macOS if missing)
    Debian : sudo apt install openssh-client
    Arch   : sudo pacman -S openssh
""")
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Instruction blocks
# ─────────────────────────────────────────────────────────────────────────────

def _pre_flash_checklist() -> str:
    return f"""
{"═" * _W}
  ⚠   PRE-FLASH CHECKLIST — complete ALL steps before continuing
{"═" * _W}

  You must do the following on your device BEFORE flashing:

  1. Enable Developer Options
     Settings → About phone → tap 'Build number' 7 times

  2. Enable OEM Unlocking
     Settings → Developer Options → OEM unlocking → ON

  3. Boot into Fastboot Mode
     Power off → hold Volume Down + press Power
     (or from your computer: adb reboot bootloader)

  4. Unlock the bootloader
     ⚠   This WIPES ALL DATA — back up first!
     Run: fastboot flashing unlock
     Confirm the prompt shown on your device screen.

  5. Connect device directly to your computer (no USB hubs)

{"─" * _W}
  ⚠   FLASHING WILL ERASE EVERYTHING on the device.
{"─" * _W}
"""


def _post_flash_instructions() -> str:
    return f"""
{"═" * _W}
  ✅  GrapheneOS installed successfully!
{"═" * _W}

  ⚠   CRITICAL NEXT STEP — lock the bootloader now.
  Your device is still in Fastboot Mode. Run:

    fastboot flashing lock

  Confirm the prompt on your device screen.
  ⚠   This wipes the device again — that is expected and required.

  After the device reboots into GrapheneOS setup:

  1. Complete the setup wizard
  2. Settings → Developer Options → OEM unlocking → OFF

  Congratulations — your device is now running GrapheneOS!
"""


def _flash_failure_help() -> str:
    return f"""
  Troubleshooting:
    • Check all USB connections (no hubs, try a different cable)
    • Confirm the bootloader was unlocked: fastboot flashing unlock
    • See the full guide:
      https://grapheneos.org/install/cli#flashing-factory-images
"""


def _pre_sideload_instructions(ota_filename: str) -> str:
    return f"""
{"═" * _W}
  📱  Sideload OTA Update
{"═" * _W}

  This pushes an OTA update to a device already running GrapheneOS.
  Your data will be preserved.

  Prepare your device:

  1. Boot into Recovery Mode
     Power off → hold Volume Down + press Power → select 'Recovery Mode'
     (if 'No command' appears: hold Power, tap Volume Up once)

  2. In the recovery menu, select 'Apply update from ADB'

{"─" * _W}
  OTA package: {ota_filename}
{"─" * _W}
"""


def _post_sideload_instructions() -> str:
    return f"""
{"═" * _W}
  ✅  OTA update sideloaded successfully!
{"═" * _W}

  Next steps on your device:

  1. Select 'Reboot system now' in the recovery menu
  2. Wait for the device to boot into the updated GrapheneOS
"""


def _sideload_failure_help() -> str:
    return f"""
  Troubleshooting:
    • Make sure 'Apply update from ADB' is selected on the device
    • Try a different USB cable or port (no hubs)
    • Confirm the OTA package matches this exact device model
"""


# ─────────────────────────────────────────────────────────────────────────────
# Device management
# ─────────────────────────────────────────────────────────────────────────────

class DeviceManager:
    """Manages device interaction via fastboot and adb"""

    # ── Fastboot ──────────────────────────────────────────────────────────────

    @staticmethod
    def check_fastboot_available() -> bool:
        """Return True if fastboot binary is on PATH"""
        try:
            return subprocess.run(
                ["fastboot", "--version"],
                capture_output=True,
            ).returncode == 0
        except FileNotFoundError:
            return False

    @staticmethod
    def check_fastboot_device() -> bool:
        """Check that a device is connected in fastboot mode"""
        try:
            result = subprocess.run(
                ["fastboot", "devices"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                _ok("Device detected in fastboot mode:")
                for line in result.stdout.strip().splitlines():
                    print(f"       {line}")
                return True

            _fail("No device found in fastboot mode")
            _block("""
  Make sure your device shows 'Fastboot Mode' on screen and is
  connected directly (no USB hubs). Try a different cable or port.
""")
            return False
        except FileNotFoundError:
            _fail("'fastboot' not found — add Android platform-tools to your PATH")
            _block("""
  Download platform-tools:
    https://developer.android.com/tools/releases/platform-tools
""")
            return False

    @staticmethod
    def flash_device(flash_script_path: Path) -> FlashResult:
        """Run the GrapheneOS flash-all.sh script after a pre-flight checklist"""

        _block(_pre_flash_checklist())

        response = input("  Have you completed all 5 steps? Type 'yes' to begin flashing: ").strip().lower()
        print()
        if response not in ("yes", "y"):
            _info("Flashing cancelled. Run again when ready.")
            return FlashResult.CANCELLED

        if not DeviceManager.check_fastboot_device():
            _fail("Cannot flash — no device detected in fastboot mode.")
            return FlashResult.NO_DEVICE

        print()
        _info("Starting flash process — do not unplug the device …")
        print()

        try:
            result = subprocess.run(["bash", str(flash_script_path)], check=False)
        except FileNotFoundError:
            _fail("'bash' not found — cannot run the flash script.")
            return FlashResult.FAILED_FLASH

        if result.returncode == 0:
            _block(_post_flash_instructions())
            return FlashResult.SUCCESS

        _fail("Flashing failed (flash-all.sh returned a non-zero exit code).")
        _block(_flash_failure_help())
        return FlashResult.FAILED_FLASH

    # ── ADB / Recovery ────────────────────────────────────────────────────────

    @staticmethod
    def check_adb_available() -> bool:
        """Return True if adb binary is on PATH"""
        try:
            return subprocess.run(
                ["adb", "version"],
                capture_output=True,
            ).returncode == 0
        except FileNotFoundError:
            return False

    @staticmethod
    def check_sideload_mode() -> bool:
        """Return True if a device is in ADB sideload mode (silent — used for polling)"""
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            return result.returncode == 0 and "sideload" in result.stdout
        except FileNotFoundError:
            return False

    @staticmethod
    def sideload_update(ota_path: Path) -> FlashResult:
        """Sideload a GrapheneOS OTA update package via adb"""

        _block(_pre_sideload_instructions(ota_path.name))

        response = input("  Device ready in sideload mode? Type 'yes' to start: ").strip().lower()
        print()
        if response not in ("yes", "y"):
            _info("Sideload cancelled. Run again when your device is ready.")
            return FlashResult.CANCELLED

        if not DeviceManager.check_sideload_mode():
            _info("Waiting for device to enter sideload mode …")
            _block("""
  (Select 'Apply update from ADB' on your device if you haven't yet)
""")
            deadline = 60
            for elapsed in range(deadline):
                if DeviceManager.check_sideload_mode():
                    _ok("Device is in sideload mode")
                    break
                if elapsed % 10 == 9:
                    _info(f"Still waiting … {deadline - elapsed - 1}s remaining")
                time.sleep(1)
            else:
                _fail("Timed out waiting for sideload mode.")
                _block("""
  Select 'Apply update from ADB' on your device, then run again.
""")
                return FlashResult.NOT_IN_SIDELOAD

        print()
        _info(f"Sideloading {ota_path.name} — do not unplug the device …")
        print()

        try:
            result = subprocess.run(["adb", "sideload", str(ota_path)], check=False)
        except FileNotFoundError:
            _fail("'adb' not found — add Android platform-tools to your PATH.")
            return FlashResult.FAILED_SIDELOAD

        if result.returncode == 0:
            _block(_post_sideload_instructions())
            return FlashResult.SUCCESS

        _fail("Sideload failed (adb returned a non-zero exit code).")
        _block(_sideload_failure_help())
        return FlashResult.FAILED_SIDELOAD


# ─────────────────────────────────────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class GrapheneOSFlasher:
    """Orchestrates the full GrapheneOS download → verify → flash pipeline"""

    FlashResult = FlashResult  # re-export for callers

    def __init__(
        self,
        config: DownloadConfig,
        file_handler: FileHandler | None = None,
        temp_dir: Path | None = None,
    ):
        self.config = config
        self.file_handler = file_handler or DefaultFileHandler()
        self.temp_dir = temp_dir or Path(tempfile.mkdtemp(prefix="grapheneos_"))
        self.security_verifier: SecurityVerifier | None = None
        self.device_manager = DeviceManager()

    @classmethod
    def get_latest_release(cls) -> str:
        """
        Fetch the latest GrapheneOS release version from the Atom feed.
        Returns a 10-digit version string (e.g. '2026050900').
        """
        _info("Fetching latest GrapheneOS release version …")
        try:
            with urllib.request.urlopen("https://grapheneos.org/releases.atom") as resp:
                content = resp.read().decode("utf-8")

            root = ElementTree.fromstring(content)
            for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                title_el = entry.find("{http://www.w3.org/2005/Atom}title")
                if title_el is not None and title_el.text:
                    candidate = title_el.text.strip().split()[-1]
                    if candidate.isdigit() and len(candidate) == 10:
                        _ok(f"Latest release: {candidate}")
                        return candidate

            raise ValueError("No valid release version found in the Atom feed")

        except urllib.error.URLError as e:
            _fail(f"Could not reach grapheneos.org: {e.reason}")
            _block("""
  Check your internet connection and try again.
  You can specify a version manually with --version <version>.
""")
            sys.exit(1)
        except ValueError as e:
            _fail(str(e))
            sys.exit(1)

    def prepare_files(self, include_ota: bool = False) -> bool:
        """
        Download and stage all files needed for flashing (or sideloading).

        Args:
            include_ota: Also download the OTA update package.
                         Only needed when --sideload is used.
        """
        _info(f"Working directory: {self.temp_dir}")
        print()

        # 1. Download the GrapheneOS public key (allowed_signers)
        allowed_signers_path = self.temp_dir / "allowed_signers"
        if not self.file_handler.download_file(
            f"{self.config.base_url}/allowed_signers", allowed_signers_path
        ):
            return False

        self.security_verifier = SecurityVerifier(allowed_signers_path)

        # 2. Download factory image and its signature
        files: list[tuple[str, Path]] = [
            (self.config.install_url, self.temp_dir / self.config.install_filename),
            (self.config.signature_url, self.temp_dir / self.config.signature_filename),
        ]
        for url, dest in files:
            if not self.file_handler.download_file(url, dest):
                return False

        # 3. Optionally download OTA package (sideload mode only)
        if include_ota:
            ota_path = self.temp_dir / self.config.ota_filename
            if not self.file_handler.download_file(self.config.ota_url, ota_path):
                _warn("OTA package not available for this version/device.")
                _block(f"""
  You may need to download it manually from:
    {self.config.ota_url}
""")

        return True

    def verify_signature(self) -> bool:
        """Verify the factory image against GrapheneOS's public signing key"""
        if not self.security_verifier:
            _fail("Security verifier not initialised — call prepare_files() first")
            return False

        sig_path = self.temp_dir / self.config.signature_filename
        img_path = self.temp_dir / self.config.install_filename
        return self.security_verifier.verify_signature(sig_path, img_path)

    def extract_files(self) -> Path | None:
        """Extract the factory image archive and return the path to flash-all.sh"""
        install_path = self.temp_dir / self.config.install_filename

        if not self.file_handler.extract_archive(install_path, self.temp_dir):
            return None

        extract_dir = self.temp_dir / self.config.install_filename.removesuffix(".zip")

        if not extract_dir.is_dir():
            candidates = [
                p for p in self.temp_dir.glob(f"{self.config.device}-install-{self.config.version}*")
                if p.is_dir()
            ]
            if not candidates:
                _fail("Could not find the extracted factory image directory.")
                return None
            extract_dir = candidates[0]

        flash_script = extract_dir / "flash-all.sh"
        if not flash_script.exists():
            _fail(f"flash-all.sh not found in {extract_dir}")
            _block("  The archive may be corrupt. Try downloading again.")
            return None

        return flash_script

    def flash(self, flash_script_path: Path) -> FlashResult:
        """Run the interactive flashing process"""
        return self.device_manager.flash_device(flash_script_path)

    def get_instructions(self, flash_script_path: Path) -> str:
        """Return manual flashing / sideloading instructions as a single string"""
        extract_dir = flash_script_path.parent
        ota_path = self.temp_dir / self.config.ota_filename
        r = _rule()
        R = "═" * _W

        flash_steps = f"""\
{r}
  HOW TO FLASH (installs GrapheneOS, wipes all data)
{r}

  1. Enable Developer Options
     Settings → About phone → tap 'Build number' 7 times

  2. Enable OEM Unlocking
     Settings → Developer Options → OEM unlocking → ON

  3. Boot into Fastboot Mode
     Power off → hold Volume Down + press Power
     (or from your computer: adb reboot bootloader)

  4. Unlock the bootloader  ⚠   backs up first, this WIPES ALL DATA
     $ fastboot flashing unlock
     Confirm the prompt shown on your device screen.

  5. Flash GrapheneOS
     $ cd {extract_dir}
     $ bash flash-all.sh

  6. Lock the bootloader  ⚠   DO NOT SKIP THIS STEP
     $ fastboot flashing lock
     Confirm on your device screen.

  7. Disable OEM Unlocking after setup completes
     Settings → Developer Options → OEM unlocking → OFF\
"""

        sideload_steps = f"""\

{r}
  HOW TO SIDELOAD AN OTA UPDATE (updates GrapheneOS, preserves data)
{r}

  1. Boot into Recovery Mode
     Power off → hold Volume Down + press Power → select 'Recovery Mode'
     (if 'No command' appears: hold Power, tap Volume Up once)

  2. Select 'Apply update from ADB' in the recovery menu

  3. Run on your computer:
     $ adb sideload {ota_path}

  4. Select 'Reboot system now' when complete\
""" if ota_path.exists() else ""

        automate = f"    Flash   : grapheneos-flasher {self.config.device} --flash"
        if ota_path.exists():
            automate += f"\n    Sideload: grapheneos-flasher {self.config.device} --sideload"

        return f"""
{R}
  ✅  Files downloaded and verified — ready to flash
{R}

  Device  : {self.config.device}
  Version : {self.config.version}
  Files   : {self.temp_dir}

{flash_steps}
{sideload_steps}

{r}
  Automate these steps with:
{automate}

  Full guide: https://grapheneos.org/install/cli
"""

    @property
    def version(self) -> str:
        return self.config.version
