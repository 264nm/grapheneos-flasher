"""
Terminal output helpers and all user-facing instruction blocks.
"""


class Instructions:
    """
    Terminal output helpers and all user-facing instruction blocks.

    Formatting primitives are @staticmethod (no class state needed).
    Blocks that reference _H / _r separators are @classmethod.
    Static instruction text lives as class-level attributes.
    """

    _W = 66  # output width
    _H = "═" * _W  # heavy rule — section headers
    _r = "─" * _W  # light rule  — sub-sections

    # ── Formatting primitives ─────────────────────────────────────────────────

    @staticmethod
    def rule(char: str = "─") -> str:
        return char * Instructions._W

    @staticmethod
    def block(text: str) -> None:
        """Print a pre-formatted multi-line block (one print call)."""
        print(text.strip("\n"))

    @staticmethod
    def ok(msg: str) -> None:
        print(f"  ✓  {msg}")

    @staticmethod
    def fail(msg: str) -> None:
        print(f"  ✗  {msg}")

    @staticmethod
    def info(msg: str) -> None:
        print(f"  →  {msg}")

    @staticmethod
    def warn(msg: str) -> None:
        print(f"  ⚠  {msg}")

    @classmethod
    def step(cls, n: int, total: int, title: str) -> None:
        print(f"\n{cls._r}\n  Step {n}/{total} — {title}\n{cls._r}")

    @classmethod
    def banner(
        cls,
        version: str,
        device: str,
        mode: str,
        mgmt_label: str | None = None,
    ) -> None:
        lines = [
            "",
            cls._H,
            f"  GrapheneOS Flasher  v{version}",
            f"  Device : {device}",
            f"  Mode   : {mode}",
        ]
        if mgmt_label is not None:
            lines.append(f"  Bootloader mgmt : {mgmt_label}")
        lines.append(cls._H)
        print("\n".join(lines))

    @classmethod
    def missing_tools(cls, missing: list[tuple[str, str]]) -> None:
        tool_lines = "\n".join(
            f"    • {tool}  ({reason})" for tool, reason in missing
        )
        print(
            "\n".join(
                [
                    "",
                    "  ⚠   Missing required tools:",
                    "",
                    tool_lines,
                    "",
                    "  Install Android platform-tools"
                    " (fastboot and adb are included):",
                    "    https://developer.android.com"
                    "/tools/releases/platform-tools",
                    "",
                    "  Add the extracted directory to your PATH,"
                    " then run again.",
                    "",
                ]
            )
        )

    # ── Static instruction blocks ─────────────────────────────────────────────

    post_flash_locked = f"""
{_H}
  ✅  GrapheneOS installed and bootloader locked!
{_H}

  Your device is rebooting into GrapheneOS setup.

  After setup completes:
    Settings → Developer Options → OEM unlocking → OFF

  Congratulations — your device is now running GrapheneOS!
"""

    post_flash_manual_lock = f"""
{_H}
  ✅  GrapheneOS installed successfully!
{_H}

  ⚠   YOU MUST LOCK THE BOOTLOADER before using this device:

    fastboot flashing lock

  Confirm the prompt on your device screen.
  This wipes the device once more — that is expected and required.

  After the device reboots into GrapheneOS setup:
    Settings → Developer Options → OEM unlocking → OFF
"""

    flash_failure_help = """
  Troubleshooting:
    • Check all USB connections (no hubs, try a different cable)
    • Confirm the bootloader was unlocked: fastboot flashing unlock
    • See the full guide:
      https://grapheneos.org/install/cli#flashing-factory-images
"""

    unlock_prompt = f"""
{_r}
  ⚠   BOOTLOADER UNLOCK
{_r}

  Unlocking the bootloader will WIPE ALL DATA on your device.
  Make sure you have backed up anything you want to keep.

  When the unlock command is sent:
    1. Your device shows an unlock confirmation screen
    2. Use Volume buttons to highlight 'Unlock the bootloader'
    3. Press Power to confirm
    4. Device wipes and reboots back into fastboot mode automatically
"""

    lock_prompt = f"""
{_H}
  ⚠   LOCK THE BOOTLOADER — critical for security
{_H}

  Locking enables verified boot, which is required for GrapheneOS
  to function securely. The device will wipe once more and reboot
  into GrapheneOS setup — this is expected and required.

  When the lock command is sent:
    1. Your device shows a lock confirmation screen
    2. Use Volume buttons to highlight 'Lock the bootloader'
    3. Press Power to confirm
"""

    post_sideload = f"""
{_H}
  ✅  OTA update sideloaded successfully!
{_H}

  Next steps on your device:

  1. Select 'Reboot system now' in the recovery menu
  2. Wait for the device to boot into the updated GrapheneOS
"""

    sideload_failure_help = """
  Troubleshooting:
    • Make sure 'Apply update from ADB' is selected on the device
    • Try a different USB cable or port (no hubs)
    • Confirm the OTA package matches this exact device model
"""

    _managed_steps = (
        "  1. Enable Developer Options\n"
        "     Settings → About phone → tap 'Build number' 7 times\n"
        "\n"
        "  2. Enable OEM Unlocking  ← required for unlock to work\n"
        "     Settings → Developer Options → OEM unlocking → ON\n"
        "\n"
        "  3. Boot into Fastboot Mode\n"
        "     Power off → hold Volume Down + press Power\n"
        "     (or from your computer: adb reboot bootloader)\n"
        "\n"
        "  4. Connect device directly to your computer (no USB hubs)\n"
        "\n"
        "  The tool will handle unlocking and re-locking the bootloader.\n"
        "  Your device will be wiped during the unlock step."
    )

    _manual_steps = (
        "  1. Enable Developer Options\n"
        "     Settings → About phone → tap 'Build number' 7 times\n"
        "\n"
        "  2. Enable OEM Unlocking\n"
        "     Settings → Developer Options → OEM unlocking → ON\n"
        "\n"
        "  3. Boot into Fastboot Mode\n"
        "     Power off → hold Volume Down + press Power\n"
        "     (or from your computer: adb reboot bootloader)\n"
        "\n"
        "  4. Unlock the bootloader  ⚠   This WIPES ALL DATA — back up first!\n"
        "     Run: fastboot flashing unlock\n"
        "     Confirm the prompt shown on your device screen.\n"
        "\n"
        "  5. Connect device directly to your computer (no USB hubs)\n"
        "\n"
        "  After flashing, you must lock the bootloader:\n"
        "     fastboot flashing lock"
    )

    # ── Parameterised blocks ──────────────────────────────────────────────────

    @classmethod
    def pre_flash_checklist(cls, manage_bootloader: bool) -> str:
        steps = cls._managed_steps if manage_bootloader else cls._manual_steps
        return "\n".join(
            [
                cls._H,
                "  ⚠   PRE-FLASH CHECKLIST",
                cls._H,
                "",
                steps,
                "",
                cls._r,
                "  ⚠   FLASHING WILL ERASE EVERYTHING on the device — back up first.",
                cls._r,
            ]
        )

    @classmethod
    def pre_sideload(cls, ota_filename: str) -> str:
        return "\n".join(
            [
                cls._H,
                "  📱  Sideload OTA Update",
                cls._H,
                "",
                "  This pushes an OTA update to a device already running GrapheneOS.",
                "  Your data will be preserved.",
                "",
                "  Prepare your device:",
                "",
                "  1. Boot into Recovery Mode",
                "     Power off → hold Volume Down + press Power"
                " → select 'Recovery Mode'",
                "     (if 'No command' appears: hold Power, tap Volume Up once)",
                "",
                "  2. In the recovery menu, select 'Apply update from ADB'",
                "",
                cls._r,
                f"  OTA package: {ota_filename}",
                cls._r,
            ]
        )
