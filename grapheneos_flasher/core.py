"""
Core functionality for GrapheneOS Flasher
"""

import subprocess
import sys
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from xml.etree import ElementTree

from grapheneos_flasher.ui import Instructions

# ─────────────────────────────────────────────────────────────────────────────
# Data types  (Instructions lives in ui.py)
# ─────────────────────────────────────────────────────────────────────────────


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
        """Download a file with progress indication, skipping if already present"""
        filename = destination.name

        if destination.exists():
            try:
                size_mb = destination.stat().st_size / (1024 * 1024)
                size_str = f"  ({size_mb:.0f} MB)" if size_mb >= 1.0 else ""
            except OSError:
                size_str = ""
            Instructions.ok(
                f"{filename}{size_str}  (already exists, skipping)"
            )
            return True

        Instructions.info(f"Downloading {filename} …")
        try:
            urllib.request.urlretrieve(url, destination)
            try:
                size_mb = destination.stat().st_size / (1024 * 1024)
                size_str = f"  ({size_mb:.0f} MB)" if size_mb >= 1.0 else ""
            except OSError:
                size_str = ""
            Instructions.ok(f"{filename}{size_str}")
            return True
        except urllib.error.HTTPError as e:
            Instructions.fail(f"HTTP {e.code} — could not download {filename}")
            if e.code == 404:
                Instructions.block(
                    "       The version or device codename may not exist.\n"
                    "       Check: https://grapheneos.org/releases"
                )
            return False
        except urllib.error.URLError as e:
            Instructions.fail(
                f"Network error downloading {filename}: {e.reason}"
            )
            Instructions.block(
                "       Check your internet connection and try again."
            )
            return False

    def extract_archive(self, archive_path: Path, destination: Path) -> bool:
        """Extract the factory image zip"""
        Instructions.info(f"Extracting {archive_path.name} …")
        try:
            subprocess.run(
                ["tar", "xf", str(archive_path)],
                cwd=destination,
                check=True,
                capture_output=True,
            )
            Instructions.ok(f"Extracted to: {destination}")
            return True
        except subprocess.CalledProcessError as e:
            Instructions.fail(
                f"Extraction failed: {e.stderr.decode().strip() if e.stderr else e}"
            )
            return False
        except FileNotFoundError:
            Instructions.fail(
                "'tar' not found — please install it and try again."
            )
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
        Instructions.info(
            "Verifying cryptographic signature against GrapheneOS public key …"
        )
        try:
            with open(file_path, "rb") as f:
                result = subprocess.run(
                    [
                        "ssh-keygen",
                        "-Y",
                        "verify",
                        "-f",
                        str(self.allowed_signers_path),
                        "-I",
                        self.GRAPHENEOS_IDENTITY,
                        "-n",
                        self.GRAPHENEOS_NAMESPACE,
                        "-s",
                        str(signature_path),
                    ],
                    stdin=f,
                    capture_output=True,
                    text=True,
                )

            if result.returncode == 0:
                Instructions.ok(
                    "Signature is valid — files are authentic and unmodified"
                )
                return True

            Instructions.fail("Signature verification FAILED")
            detail = (
                f"\n  ssh-keygen: {result.stderr.strip()}"
                if result.stderr.strip()
                else ""
            )
            Instructions.block(
                "  The downloaded files may be corrupted or tampered with.\n"
                f"  Do NOT flash these images.{detail}"
            )
            return False

        except FileNotFoundError:
            Instructions.fail("'ssh-keygen' not found")
            Instructions.block(
                "  OpenSSH is required for signature verification.\n"
                "  Install it with your package manager:\n"
                "    macOS  : built-in (update macOS if missing)\n"
                "    Debian : sudo apt install openssh-client\n"
                "    Arch   : sudo pacman -S openssh"
            )
            return False


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
            return (
                subprocess.run(
                    ["fastboot", "--version"],
                    capture_output=True,
                ).returncode
                == 0
            )
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
                Instructions.ok("Device detected in fastboot mode:")
                for line in result.stdout.strip().splitlines():
                    print(f"       {line}")
                return True

            Instructions.fail("No device found in fastboot mode")
            Instructions.block(
                "  Make sure your device shows 'Fastboot Mode' on screen and is\n"
                "  connected directly (no USB hubs). Try a different cable or port."
            )
            return False
        except FileNotFoundError:
            Instructions.fail(
                "'fastboot' not found — add Android platform-tools to your PATH"
            )
            Instructions.block(
                "  Download platform-tools:\n"
                "    https://developer.android.com/tools/releases/platform-tools"
            )
            return False

    @staticmethod
    def get_bootloader_state() -> str | None:
        """
        Query the bootloader lock state via fastboot.
        Returns 'unlocked', 'locked', or None if undetermined / no device.
        """
        try:
            result = subprocess.run(
                ["fastboot", "getvar", "unlocked"],
                capture_output=True,
                text=True,
            )
            output = result.stdout + result.stderr
            if "unlocked: yes" in output:
                return "unlocked"
            if "unlocked: no" in output:
                return "locked"
            return None
        except FileNotFoundError:
            return None

    @staticmethod
    def wait_for_fastboot(timeout: int = 120) -> bool:
        """Poll until a device appears in fastboot mode or timeout expires."""
        Instructions.info("Waiting for device to return to fastboot mode …")
        for elapsed in range(timeout):
            try:
                result = subprocess.run(
                    ["fastboot", "devices"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and result.stdout.strip():
                    Instructions.ok("Device is back in fastboot mode")
                    return True
            except FileNotFoundError:
                return False
            if elapsed > 0 and elapsed % 15 == 0:
                Instructions.info(f"Still waiting … ({elapsed}s / {timeout}s)")
            time.sleep(1)
        Instructions.fail(
            f"Timed out after {timeout}s — device did not return to fastboot mode"
        )
        return False

    @staticmethod
    def unlock_bootloader() -> bool:
        """
        Interactively unlock the bootloader.

        The device displays a confirmation prompt; the user selects
        'Unlock the bootloader' with volume/power buttons. Afterwards
        the device wipes and reboots back into fastboot automatically.
        """
        Instructions.block(Instructions.unlock_prompt)
        response = (
            input("  Ready to unlock? Type 'yes' to send the unlock command: ")
            .strip()
            .lower()
        )
        print()
        if response not in ("yes", "y"):
            Instructions.info("Unlock cancelled.")
            return False

        Instructions.info(
            "Sending unlock command — confirm on your device screen …"
        )
        try:
            result = subprocess.run(
                ["fastboot", "flashing", "unlock"], check=False
            )
        except FileNotFoundError:
            Instructions.fail("'fastboot' not found.")
            return False

        if result.returncode != 0:
            Instructions.fail("Unlock command failed (non-zero exit code).")
            return False

        print()
        if not DeviceManager.wait_for_fastboot():
            Instructions.fail(
                "Device did not return to fastboot after unlock."
            )
            Instructions.block(
                "  Boot your device into fastboot mode manually:\n"
                "    Power off → hold Volume Down + press Power\n"
                "  Then run the flasher again."
            )
            return False

        state = DeviceManager.get_bootloader_state()
        if state == "unlocked":
            Instructions.ok("Bootloader is unlocked — verified")
            return True

        Instructions.fail(
            f"Expected bootloader to be unlocked, got: {state or 'unknown'}"
        )
        return False

    @staticmethod
    def lock_bootloader() -> bool:
        """
        Interactively lock the bootloader after a successful flash.

        The device displays a confirmation prompt. After confirming it
        wipes once more and reboots into GrapheneOS setup — expected behaviour.
        """
        Instructions.block(Instructions.lock_prompt)
        response = (
            input("  Ready to lock? Type 'yes' to send the lock command: ")
            .strip()
            .lower()
        )
        print()
        if response not in ("yes", "y"):
            Instructions.block(Instructions.post_flash_manual_lock)
            return False

        Instructions.info(
            "Sending lock command — confirm on your device screen …"
        )
        try:
            result = subprocess.run(
                ["fastboot", "flashing", "lock"], check=False
            )
        except FileNotFoundError:
            Instructions.fail("'fastboot' not found.")
            Instructions.block(Instructions.post_flash_manual_lock)
            return False

        if result.returncode != 0:
            Instructions.fail("Lock command failed (non-zero exit code).")
            Instructions.block(Instructions.post_flash_manual_lock)
            return False

        # After locking the device reboots into GrapheneOS — fastboot won't
        # be reachable for long. Accept None (already rebooted) as success
        # since the command returned 0.
        print()
        Instructions.info("Verifying bootloader state …")
        time.sleep(2)
        state = DeviceManager.get_bootloader_state()

        if state == "locked":
            Instructions.ok("Bootloader is locked — verified")
            return True
        elif state is None:
            Instructions.ok("Device has rebooted — bootloader lock confirmed")
            return True
        else:
            Instructions.fail(
                f"Unexpected bootloader state after lock: {state}"
            )
            Instructions.block(Instructions.post_flash_manual_lock)
            return False

    @staticmethod
    def flash_device(
        flash_script_path: Path, manage_bootloader: bool = True
    ) -> FlashResult:
        """
        Run the GrapheneOS flash-all.sh script.

        With manage_bootloader=True (default):
          - Checks/unlocks the bootloader before flashing
          - Locks the bootloader after a successful flash
          - Validates state at each step

        With manage_bootloader=False:
          - Validates that the bootloader IS already unlocked (hard prerequisite)
          - Shows manual lock reminder after flashing
        """
        steps = "4" if manage_bootloader else "5"
        Instructions.block(Instructions.pre_flash_checklist(manage_bootloader))

        response = (
            input(
                f"  Have you completed all {steps} steps? Type 'yes' to continue: "
            )
            .strip()
            .lower()
        )
        print()
        if response not in ("yes", "y"):
            Instructions.info("Flashing cancelled. Run again when ready.")
            return FlashResult.CANCELLED

        if not DeviceManager.check_fastboot_device():
            Instructions.fail(
                "Cannot proceed — no device detected in fastboot mode."
            )
            return FlashResult.NO_DEVICE

        print()

        if manage_bootloader:
            state = DeviceManager.get_bootloader_state()
            if state == "unlocked":
                Instructions.ok("Bootloader is already unlocked — proceeding")
            elif state == "locked":
                Instructions.info("Bootloader is locked — unlocking now …")
                if not DeviceManager.unlock_bootloader():
                    return FlashResult.FAILED_FLASH
                print()
                if not DeviceManager.check_fastboot_device():
                    return FlashResult.NO_DEVICE
                print()
            else:
                Instructions.warn(
                    "Could not determine bootloader state — proceeding anyway"
                )
                Instructions.block(
                    "  If flashing fails, ensure the bootloader is unlocked:\n"
                    "    fastboot flashing unlock"
                )
        else:
            state = DeviceManager.get_bootloader_state()
            if state == "locked":
                Instructions.fail("Bootloader is locked — cannot flash")
                Instructions.block(
                    "  Unlock it first, then run again:\n"
                    "    fastboot flashing unlock"
                )
                return FlashResult.FAILED_FLASH
            elif state == "unlocked":
                Instructions.ok("Bootloader is unlocked — prerequisite met")
            else:
                Instructions.warn(
                    "Could not verify bootloader state — proceeding anyway"
                )
            print()

        Instructions.info(
            "Starting flash process — do not unplug the device …"
        )
        print()

        try:
            result = subprocess.run(
                ["bash", flash_script_path.name],
                cwd=flash_script_path.parent,
                check=False,
            )
        except FileNotFoundError:
            Instructions.fail(
                "'bash' not found — cannot run the flash script."
            )
            return FlashResult.FAILED_FLASH

        if result.returncode != 0:
            Instructions.fail(
                "Flashing failed (flash-all.sh returned a non-zero exit code)."
            )
            Instructions.block(Instructions.flash_failure_help)
            return FlashResult.FAILED_FLASH

        print()

        if manage_bootloader:
            if not DeviceManager.check_fastboot_device():
                Instructions.info(
                    "Device not immediately available — waiting …"
                )
                if not DeviceManager.wait_for_fastboot(timeout=60):
                    Instructions.block(Instructions.post_flash_manual_lock)
                    return FlashResult.SUCCESS

            locked = DeviceManager.lock_bootloader()
            Instructions.block(
                Instructions.post_flash_locked
                if locked
                else Instructions.post_flash_manual_lock
            )
        else:
            Instructions.block(Instructions.post_flash_manual_lock)

        return FlashResult.SUCCESS

    # ── ADB / Recovery ────────────────────────────────────────────────────────

    @staticmethod
    def check_adb_available() -> bool:
        """Return True if adb binary is on PATH"""
        try:
            return (
                subprocess.run(
                    ["adb", "version"],
                    capture_output=True,
                ).returncode
                == 0
            )
        except FileNotFoundError:
            return False

    @staticmethod
    def check_sideload_mode() -> bool:
        """Return True if a device is in ADB sideload mode (silent polling)."""
        try:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True
            )
            return result.returncode == 0 and "sideload" in result.stdout
        except FileNotFoundError:
            return False

    @staticmethod
    def sideload_update(ota_path: Path) -> FlashResult:
        """Sideload a GrapheneOS OTA update package via adb"""
        Instructions.block(Instructions.pre_sideload(ota_path.name))

        response = (
            input("  Device ready in sideload mode? Type 'yes' to start: ")
            .strip()
            .lower()
        )
        print()
        if response not in ("yes", "y"):
            Instructions.info(
                "Sideload cancelled. Run again when your device is ready."
            )
            return FlashResult.CANCELLED

        if not DeviceManager.check_sideload_mode():
            Instructions.info("Waiting for device to enter sideload mode …")
            Instructions.block(
                "  (Select 'Apply update from ADB' on your device if you haven't yet)"
            )

            deadline = 60
            for elapsed in range(deadline):
                if DeviceManager.check_sideload_mode():
                    Instructions.ok("Device is in sideload mode")
                    break
                if elapsed % 10 == 9:
                    Instructions.info(
                        f"Still waiting … {deadline - elapsed - 1}s remaining"
                    )
                time.sleep(1)
            else:
                Instructions.fail("Timed out waiting for sideload mode.")
                Instructions.block(
                    "  Select 'Apply update from ADB' on your device, then run again."
                )
                return FlashResult.NOT_IN_SIDELOAD

        print()
        Instructions.info(
            f"Sideloading {ota_path.name} — do not unplug the device …"
        )
        print()

        try:
            result = subprocess.run(
                ["adb", "sideload", str(ota_path)], check=False
            )
        except FileNotFoundError:
            Instructions.fail(
                "'adb' not found — add Android platform-tools to your PATH."
            )
            return FlashResult.FAILED_SIDELOAD

        if result.returncode == 0:
            Instructions.block(Instructions.post_sideload)
            return FlashResult.SUCCESS

        Instructions.fail(
            "Sideload failed (adb returned a non-zero exit code)."
        )
        Instructions.block(Instructions.sideload_failure_help)
        return FlashResult.FAILED_SIDELOAD


# ─────────────────────────────────────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────────────────────────────────────


class GrapheneOSFlasher:
    """Orchestrates the full GrapheneOS download → verify → flash pipeline"""

    def __init__(
        self,
        config: DownloadConfig,
        file_handler: FileHandler | None = None,
        work_dir: Path | None = None,
    ):
        self.config = config
        self.file_handler = file_handler or DefaultFileHandler()
        self.work_dir = work_dir or Path.cwd()
        self.security_verifier: SecurityVerifier | None = None
        self.device_manager = DeviceManager()

    @classmethod
    def get_latest_release(cls) -> str:
        """
        Fetch the latest GrapheneOS release version from the Atom feed.
        Returns a 10-digit version string (e.g. '2026050900').
        """
        Instructions.info("Fetching latest GrapheneOS release version …")
        try:
            with urllib.request.urlopen(
                "https://grapheneos.org/releases.atom"
            ) as resp:
                content = resp.read().decode("utf-8")

            root = ElementTree.fromstring(content)
            for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                title_el = entry.find("{http://www.w3.org/2005/Atom}title")
                if title_el is not None and title_el.text:
                    candidate = title_el.text.strip().split()[-1]
                    if candidate.isdigit() and len(candidate) == 10:
                        Instructions.ok(f"Latest release: {candidate}")
                        return candidate

            raise ValueError("No valid release version found in the Atom feed")

        except urllib.error.URLError as e:
            Instructions.fail(f"Could not reach grapheneos.org: {e.reason}")
            Instructions.block(
                "  Check your internet connection and try again.\n"
                "  You can specify a version manually with --version <version>."
            )
            sys.exit(1)
        except ValueError as e:
            Instructions.fail(str(e))
            sys.exit(1)

    def prepare_factory_image(self) -> bool:
        """Download and stage the factory image and its signature for flashing."""
        Instructions.info(f"Working directory: {self.work_dir}")
        print()

        allowed_signers_path = self.work_dir / "allowed_signers"
        if not self.file_handler.download_file(
            f"{self.config.base_url}/allowed_signers", allowed_signers_path
        ):
            return False

        self.security_verifier = SecurityVerifier(allowed_signers_path)

        files: list[tuple[str, Path]] = [
            (
                self.config.install_url,
                self.work_dir / self.config.install_filename,
            ),
            (
                self.config.signature_url,
                self.work_dir / self.config.signature_filename,
            ),
        ]
        for url, dest in files:
            if not self.file_handler.download_file(url, dest):
                return False

        return True

    def prepare_ota(self) -> bool:
        """Download the OTA update package for sideloading."""
        Instructions.info(f"Working directory: {self.work_dir}")
        print()

        ota_path = self.work_dir / self.config.ota_filename
        if not self.file_handler.download_file(self.config.ota_url, ota_path):
            Instructions.warn(
                "OTA package not available for this version/device."
            )
            Instructions.block(
                f"  Download it manually from:\n    {self.config.ota_url}"
            )
            return False

        return True

    def verify_signature(self) -> bool:
        """Verify the factory image against GrapheneOS's public signing key"""
        if not self.security_verifier:
            Instructions.fail(
                "Security verifier not initialised — call prepare_factory_image() first"
            )
            return False

        sig_path = self.work_dir / self.config.signature_filename
        img_path = self.work_dir / self.config.install_filename
        return self.security_verifier.verify_signature(sig_path, img_path)

    def extract_files(self) -> Path | None:
        """Extract the factory image archive and return the path to flash-all.sh"""
        install_path = self.work_dir / self.config.install_filename

        if not self.file_handler.extract_archive(install_path, self.work_dir):
            return None

        extract_dir = (
            self.work_dir / self.config.install_filename.removesuffix(".zip")
        )

        if not extract_dir.is_dir():
            candidates = [
                p
                for p in self.work_dir.glob(
                    f"{self.config.device}-install-{self.config.version}*"
                )
                if p.is_dir()
            ]
            if not candidates:
                Instructions.fail(
                    "Could not find the extracted factory image directory."
                )
                return None
            extract_dir = candidates[0]

        flash_script = extract_dir / "flash-all.sh"
        if not flash_script.exists():
            Instructions.fail(f"flash-all.sh not found in {extract_dir}")
            Instructions.block(
                "  The archive may be corrupt. Try downloading again."
            )
            return None

        return flash_script

    def flash(
        self, flash_script_path: Path, manage_bootloader: bool = True
    ) -> FlashResult:
        """Run the interactive flashing process"""
        return self.device_manager.flash_device(
            flash_script_path, manage_bootloader
        )

    def get_instructions(self, flash_script_path: Path) -> str:
        """Return manual flashing / sideloading instructions as a single string"""
        extract_dir = flash_script_path.parent
        ota_path = self.work_dir / self.config.ota_filename
        H = Instructions._H
        r = Instructions._r

        lines = [
            "",
            H,
            "  ✅  Files downloaded and verified — ready to flash",
            H,
            "",
            f"  Device  : {self.config.device}",
            f"  Version : {self.config.version}",
            f"  Files   : {self.work_dir}",
            "",
            r,
            "  HOW TO FLASH (installs GrapheneOS, wipes all data)",
            r,
            "",
            "  1. Enable Developer Options",
            "     Settings → About phone → tap 'Build number' 7 times",
            "",
            "  2. Enable OEM Unlocking",
            "     Settings → Developer Options → OEM unlocking → ON",
            "",
            "  3. Boot into Fastboot Mode",
            "     Power off → hold Volume Down + press Power",
            "     (or from your computer: adb reboot bootloader)",
            "",
            "  4. Unlock the bootloader  ⚠   back up first, this WIPES ALL DATA",
            "     $ fastboot flashing unlock",
            "     Confirm the prompt on your device screen.",
            "",
            "  5. Flash GrapheneOS",
            f"     $ cd {extract_dir}",
            "     $ bash flash-all.sh",
            "",
            "  6. Lock the bootloader  ⚠   DO NOT SKIP THIS STEP",
            "     $ fastboot flashing lock",
            "     Confirm on your device screen.",
            "",
            "  7. Disable OEM Unlocking after setup completes",
            "     Settings → Developer Options → OEM unlocking → OFF",
        ]

        if ota_path.exists():
            lines += [
                "",
                r,
                "  HOW TO SIDELOAD AN OTA UPDATE (updates GrapheneOS, preserves data)",
                r,
                "",
                "  1. Boot into Recovery Mode",
                "     Power off → hold Volume Down + press Power"
                " → select 'Recovery Mode'",
                "     (if 'No command' appears: hold Power, tap Volume Up once)",
                "",
                "  2. Select 'Apply update from ADB' in the recovery menu",
                "",
                "  3. Run on your computer:",
                f"     $ adb sideload {ota_path}",
                "",
                "  4. Select 'Reboot system now' when complete",
            ]

        automate_lines = [
            f"    Flash   : grapheneos-flasher {self.config.device} --flash"
        ]
        if ota_path.exists():
            automate_lines.append(
                f"    Sideload: grapheneos-flasher {self.config.device} --sideload"
            )

        lines += [
            "",
            r,
            "  Automate these steps with:",
            *automate_lines,
            "",
            "  Full guide: https://grapheneos.org/install/cli",
            "",
        ]

        return "\n".join(lines)

    @property
    def version(self) -> str:
        return self.config.version
