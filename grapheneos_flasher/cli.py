"""
Command-line interface for GrapheneOS Flasher
"""

import argparse
import sys
import tempfile
from pathlib import Path

from grapheneos_flasher import __version__
from grapheneos_flasher.core import (
    DeviceManager,
    DownloadConfig,
    FlashResult,
    GrapheneOSFlasher,
    Instructions,
)

# ─────────────────────────────────────────────────────────────────────────────
# Known supported devices  (see https://grapheneos.org/faq#device-support)
# ─────────────────────────────────────────────────────────────────────────────

DEVICE_CODENAMES: dict[str, str] = {
    # Pixel 9 series
    "tokay": "Pixel 9a",
    "caiman": "Pixel 9 Pro XL",
    "komodo": "Pixel 9 Pro XL",  # alternate name in older builds
    "comet": "Pixel 9 Pro",
    "tegu": "Pixel 9 Pro Fold",
    "akita": "Pixel 9",
    # Pixel 8 series
    "shiba": "Pixel 8",
    "husky": "Pixel 8 Pro",
    "huskypro": "Pixel 8 Pro",
    "felix": "Pixel Fold",
    "tangorpro": "Pixel Tablet",
    "axolotl": "Pixel 8a",
    # Pixel 7 series
    "panther": "Pixel 7",
    "cheetah": "Pixel 7 Pro",
    "lynx": "Pixel 7a",
    # Pixel 6 series
    "oriole": "Pixel 6",
    "raven": "Pixel 6 Pro",
    "bluejay": "Pixel 6a",
}

DEVICE_TABLE = "\n".join(
    f"  {code:<14} {name}"
    for code, name in sorted(DEVICE_CODENAMES.items(), key=lambda kv: kv[1])
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
    """
    Validate a GrapheneOS device codename.

    All known GrapheneOS codenames are lowercase alphabetic strings of at
    least 3 characters (e.g. 'shiba', 'oriole', 'caiman').
    """
    return len(device) >= 3 and device.isalpha() and device.islower()


def warn_unknown_device(device: str) -> None:
    """Print a non-fatal warning when the codename isn't in our known list"""
    if device not in DEVICE_CODENAMES:
        print(f"  ⚠  '{device}' is not in the known device list.")
        print(
            "     If you're sure this is correct, the download will tell you."
        )
        print(
            "     Check supported devices: https://grapheneos.org/faq#device-support"
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
    print(
        f"  ⚠  '{specified}' does not exist — using temp dir instead: {work_dir}"
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
        print()
        print("  ⚠   Missing required tools:")
        print()
        for tool, reason in missing:
            print(f"    • {tool}  ({reason})")
        print()
        print(
            "  Install Android platform-tools (fastboot and adb are included):"
        )
        print(
            "    https://developer.android.com/tools/releases/platform-tools"
        )
        print()
        print("  Add the extracted directory to your PATH, then run again.")
        print()
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
    print()
    print(Instructions._H)
    print(f"  GrapheneOS Flasher  v{__version__}")
    print(f"  Device : {args.device}")
    print(f"  Mode   : {mode_label}")
    if args.flash:
        mgmt_label = (
            "on (--no-bootloader-mgmt to disable)"
            if args.bootloader_mgmt
            else "off (manual)"
        )
        print(f"  Bootloader mgmt : {mgmt_label}")
    print(Instructions._H)

    # ── Basic validation ──────────────────────────────────────────────────────
    if not validate_device(args.device):
        print()
        print(f"  ✗  Invalid device codename: '{args.device}'")
        print(
            "     Codenames are lowercase alphanumeric (e.g. shiba, oriole)."
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
        print(f"  →  Using specified version: {version}")
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
            print("  ✗  Could not download OTA package. Check messages above.")
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
        print("  ✗  Download failed. Check the messages above and try again.")
        sys.exit(1)

    Instructions.step(2, total_steps, "Verifying signature")
    print()

    if not flasher.verify_signature():
        print()
        print("  ✗  Aborting — do not flash unverified images.")
        sys.exit(1)

    Instructions.step(3, total_steps, "Extracting factory image")
    print()

    flash_script_path = flasher.extract_files()
    if not flash_script_path:
        print()
        print(
            "  ✗  Extraction failed. The download may be corrupt; try again."
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
