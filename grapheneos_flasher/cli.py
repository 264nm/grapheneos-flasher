"""
Command-line interface for GrapheneOS Flasher
"""

import argparse
import sys
import tempfile
from enum import StrEnum
from pathlib import Path

from grapheneos_flasher import __version__
from grapheneos_flasher.core import (
    DeviceManager,
    DownloadConfig,
    FlashResult,
    GrapheneOSFlasher,
)
from grapheneos_flasher.ui import Instructions

# ─────────────────────────────────────────────────────────────────────────────
# Known supported devices  (see https://grapheneos.org/faq#device-support)
# ─────────────────────────────────────────────────────────────────────────────


class Device(StrEnum):
    """Supported GrapheneOS devices. Member name = codename, value = display name."""

    # Pixel 9 series
    tokay = "Pixel 9a"
    akita = "Pixel 9"
    comet = "Pixel 9 Pro"
    caiman = "Pixel 9 Pro XL"
    tegu = "Pixel 9 Pro Fold"
    # Pixel 8 series
    shiba = "Pixel 8"
    husky = "Pixel 8 Pro"
    axolotl = "Pixel 8a"
    felix = "Pixel Fold"
    tangorpro = "Pixel Tablet"
    # Pixel 7 series
    panther = "Pixel 7"
    cheetah = "Pixel 7 Pro"
    lynx = "Pixel 7a"
    # Pixel 6 series
    oriole = "Pixel 6"
    raven = "Pixel 6 Pro"
    bluejay = "Pixel 6a"

    @classmethod
    def codenames(cls) -> set[str]:
        """Return all known codenames."""
        return {d.name for d in cls}

    @classmethod
    def from_codename(cls, codename: str) -> "Device | None":
        """Look up a device by codename, returning None if unknown."""
        return cls._member_map_.get(codename)  # type: ignore[return-value]

    def __str__(self) -> str:
        return f"{self.name} ({self.value})"


DEVICE_TABLE = "\n".join(
    f"  {d.name:<14} {d.value}" for d in sorted(Device, key=lambda d: d.value)
)


# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse and return CLI arguments (convenience wrapper used by tests)."""
    return build_parser().parse_args()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grapheneos-flasher",
        description=(
            "Download, verify, and flash GrapheneOS factory images.\n"
            "Follows the official CLI installation guide at:\n"
            "  https://grapheneos.org/install/cli"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
modes:
  (none)      Download and verify the factory image only — no changes to device
  --flash     Full guided install: download, verify, and run flash-all.sh
  --sideload  Sideload an OTA update onto an existing GrapheneOS device

examples:
  grapheneos-flasher shiba
      Download and verify the latest Pixel 8 factory image

  grapheneos-flasher shiba --flash
      Download, verify, and flash GrapheneOS onto a Pixel 8

  grapheneos-flasher shiba --version 2026050900 --flash
      Flash a specific GrapheneOS version

  grapheneos-flasher shiba --sideload
      Sideload the latest OTA update onto a Pixel 8 running GrapheneOS

supported devices:
{DEVICE_TABLE}

  See the full device list at: https://grapheneos.org/faq#device-support
""",
    )

    parser.add_argument(
        "device",
        help="Device codename (e.g. shiba, husky, oriole)",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--flash",
        action="store_true",
        help="Download, verify, then flash the factory image (wipes device)",
    )
    mode.add_argument(
        "--sideload",
        action="store_true",
        help="Download, verify, then sideload an OTA update (preserves data)",
    )

    parser.add_argument(
        "--version",
        metavar="VERSION",
        help="Specific release to use, e.g. 2026050900 (default: latest)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        metavar="PATH",
        help=(
            "Directory for downloaded files "
            "(default: current working directory; "
            "falls back to a temp dir if the path does not exist)"
        ),
    )
    parser.add_argument(
        "--no-bootloader-mgmt",
        dest="bootloader_mgmt",
        action="store_false",
        default=True,
        help=(
            "Skip automatic bootloader unlock/lock. "
            "You must unlock before flashing and lock afterwards manually. "
            "The bootloader state is still validated as a prerequisite."
        ),
    )

    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────────────────────


def validate_device(device: str) -> bool:
    """Return True if the string is a plausible codename (non-empty, lowercase alpha)."""
    return len(device) >= 3 and device.isalpha() and device.islower()


def warn_unknown_device(device: str) -> None:
    """Print a non-fatal warning when the codename isn't in the Device enum."""
    if Device.from_codename(device) is None:
        Instructions.warn(f"'{device}' is not in the known device list.")
        Instructions.block(
            "     If you're sure this is correct, the download will tell you.\n"
            "     Check supported devices:"
            " https://grapheneos.org/faq#device-support"
        )
        print()


def resolve_work_dir(specified: Path | None) -> Path:
    """
    Resolve the working directory for downloads:
      - Nothing specified  → current working directory
      - Path exists        → use it
      - Path doesn't exist → warn and fall back to a system temp dir
    """
    if specified is None:
        return Path.cwd()
    if specified.exists():
        return specified
    work_dir = Path(tempfile.mkdtemp(prefix="grapheneos_"))
    Instructions.warn(
        f"'{specified}' does not exist"
        f" — using temp dir instead: {work_dir}"
    )
    return work_dir


def check_prerequisites(mode_flash: bool, mode_sideload: bool) -> None:
    """Warn early about missing system tools so the user can fix them first"""
    missing = []

    if not DeviceManager.check_fastboot_available():
        missing.append(("fastboot", "needed to flash the device"))
    if mode_sideload and not DeviceManager.check_adb_available():
        missing.append(("adb", "needed for sideloading OTA updates"))

    if missing:
        Instructions.missing_tools(missing)
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # ── Banner ────────────────────────────────────────────────────────────────
    mode_label = (
        "Flash (install GrapheneOS)"
        if args.flash
        else (
            "Sideload (OTA update)"
            if args.sideload
            else "Download & Verify only"
        )
    )
    mgmt_label = None
    if args.flash:
        mgmt_label = (
            "on (--no-bootloader-mgmt to disable)"
            if args.bootloader_mgmt
            else "off (manual)"
        )
    Instructions.banner(__version__, args.device, mode_label, mgmt_label)

    # ── Basic validation ──────────────────────────────────────────────────────
    if not validate_device(args.device):
        print()
        Instructions.fail(f"Invalid device codename: '{args.device}'")
        Instructions.block(
            "     Codenames are lowercase alphabetic (e.g. shiba, oriole)."
        )
        sys.exit(1)

    print()
    warn_unknown_device(args.device)

    # ── Tool prerequisites ────────────────────────────────────────────────────
    if args.flash or args.sideload:
        check_prerequisites(args.flash, args.sideload)

    # ── Resolve version ───────────────────────────────────────────────────────
    if args.version:
        version = args.version
        Instructions.info(f"Using specified version: {version}")
    else:
        version = GrapheneOSFlasher.get_latest_release()

    print()

    config = DownloadConfig(device=args.device, version=version)
    work_dir = resolve_work_dir(args.work_dir)
    flasher = GrapheneOSFlasher(config, work_dir=work_dir)

    # ── Sideload path (independent — only needs the OTA package) ─────────────
    if args.sideload:
        Instructions.step(1, 2, "Downloading OTA package")

        if not flasher.prepare_ota():
            print()
            Instructions.fail(
                "Could not download OTA package. Check messages above."
            )
            sys.exit(1)

        Instructions.step(2, 2, "Sideloading")

        result = flasher.device_manager.sideload_update(
            flasher.work_dir / config.ota_filename
        )
        sys.exit(
            0 if result in (FlashResult.SUCCESS, FlashResult.CANCELLED) else 1
        )

    # ── Flash / dry-run path ──────────────────────────────────────────────────
    total_steps = 4 if args.flash else 3

    Instructions.step(1, total_steps, "Downloading factory image")

    if not flasher.prepare_factory_image():
        print()
        Instructions.fail(
            "Download failed. Check the messages above and try again."
        )
        sys.exit(1)

    Instructions.step(2, total_steps, "Verifying signature")
    print()

    if not flasher.verify_signature():
        print()
        Instructions.fail("Aborting — do not flash unverified images.")
        sys.exit(1)

    Instructions.step(3, total_steps, "Extracting factory image")
    print()

    flash_script_path = flasher.extract_files()
    if not flash_script_path:
        print()
        Instructions.fail(
            "Extraction failed. The download may be corrupt; try again."
        )
        sys.exit(1)

    if args.flash:
        result = flasher.flash(
            flash_script_path, manage_bootloader=args.bootloader_mgmt
        )
        sys.exit(
            0 if result in (FlashResult.SUCCESS, FlashResult.CANCELLED) else 1
        )
    else:
        print(flasher.get_instructions(flash_script_path))


if __name__ == "__main__":
    main()
