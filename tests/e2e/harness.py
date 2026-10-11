"""
Fake-device harness shared by the e2e fixtures and tests.

Provides stub ``fastboot`` / ``adb`` executables backed by a state
file, so a fake device transitions through locked → unlocked →
flashed → locked exactly like real hardware. Every invocation is
appended to a log file so tests can assert on the command sequence.

An Android emulator cannot stand in for the fastboot side: AVDs have
no real bootloader and never appear in ``fastboot devices``. The
emulator suite (test_pixel_emulator.py) covers the adb-facing paths
against a real device stack; this harness covers everything else.
"""

import stat
import textwrap
from dataclasses import dataclass
from pathlib import Path

DEVICE = "panther"
VERSION = "2026061800"
REPO_ROOT = Path(__file__).resolve().parents[2]

FAKE_FASTBOOT = textwrap.dedent("""\
    #!/usr/bin/env bash
    # Fake fastboot backed by a state file; logs every invocation.
    set -u
    echo "fastboot $*" >> "$FAKE_TOOL_LOG"
    case "${1:-}" in
      --version)
        echo "fastboot version 35.0.0-fake"
        ;;
      devices)
        printf 'FAKESERIAL\\tfastboot\\n'
        ;;
      getvar)
        if [ "${2:-}" = "unlocked" ]; then
          if [ "$(cat "$FAKE_DEVICE_STATE")" = "unlocked" ]; then
            echo "unlocked: yes" >&2
          else
            echo "unlocked: no" >&2
          fi
          echo "Finished. Total time: 0.001s" >&2
        fi
        ;;
      flashing)
        case "${2:-}" in
          unlock) echo unlocked > "$FAKE_DEVICE_STATE" ;;
          lock)   echo locked   > "$FAKE_DEVICE_STATE" ;;
        esac
        ;;
    esac
    exit 0
    """)

FAKE_ADB = textwrap.dedent("""\
    #!/usr/bin/env bash
    # Fake adb; device mode (device/sideload) comes from a state file.
    set -u
    echo "adb $*" >> "$FAKE_TOOL_LOG"
    case "${1:-}" in
      version)
        echo "Android Debug Bridge version 1.0.41 (fake)"
        ;;
      devices)
        echo "List of devices attached"
        printf 'FAKESERIAL\\t%s\\n' "$(cat "$FAKE_ADB_STATE")"
        ;;
      sideload)
        if [ ! -f "${2:-}" ]; then
          echo "adb: sideload requires an existing file" >&2
          exit 1
        fi
        echo "Total xfer: 1.00x"
        ;;
    esac
    exit 0
    """)

# The GrapheneOS flash-all.sh drives fastboot; this miniature version
# exercises the same call shape against the stub.
FAKE_FLASH_ALL = textwrap.dedent("""\
    #!/bin/bash
    set -e
    fastboot flash bootloader bootloader-fake.img
    fastboot reboot-bootloader
    fastboot flash radio radio-fake.img
    fastboot reboot-bootloader
    fastboot -w update image-fake.zip
    """)


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@dataclass
class FakeDevice:
    """Handle onto the stub platform-tools and their device state."""

    bin_dir: Path
    state_file: Path
    adb_state_file: Path
    log_file: Path

    @property
    def bootloader_state(self) -> str:
        return self.state_file.read_text().strip()

    @property
    def calls(self) -> list[str]:
        if not self.log_file.exists():
            return []
        return self.log_file.read_text().splitlines()

    def set_bootloader_state(self, state: str) -> None:
        self.state_file.write_text(f"{state}\n")

    def set_adb_mode(self, mode: str) -> None:
        self.adb_state_file.write_text(f"{mode}\n")
