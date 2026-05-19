"""
Unit tests for grapheneos_flasher.ui (Instructions class)
"""

from grapheneos_flasher.ui import Instructions


class TestConstants:

    def test_width(self):
        assert Instructions._W == 66

    def test_heavy_rule(self):
        assert Instructions._H == "═" * 66

    def test_light_rule(self):
        assert Instructions._r == "─" * 66

    def test_rule_default(self):
        assert Instructions.rule() == "─" * 66

    def test_rule_custom_char(self):
        assert Instructions.rule("═") == "═" * 66


class TestFormattingPrimitives:

    def test_ok(self, capsys):
        Instructions.ok("all good")
        assert capsys.readouterr().out == "  ✓  all good\n"

    def test_fail(self, capsys):
        Instructions.fail("something broke")
        assert capsys.readouterr().out == "  ✗  something broke\n"

    def test_info(self, capsys):
        Instructions.info("doing a thing")
        assert capsys.readouterr().out == "  →  doing a thing\n"

    def test_warn(self, capsys):
        Instructions.warn("be careful")
        assert capsys.readouterr().out == "  ⚠  be careful\n"

    def test_block_strips_surrounding_newlines(self, capsys):
        Instructions.block("\n  hello\n  world\n")
        out = capsys.readouterr().out
        assert out.startswith("  hello")
        assert not out.startswith("\n")

    def test_block_single_call(self, capsys):
        Instructions.block("line one\nline two")
        assert capsys.readouterr().out == "line one\nline two\n"

    def test_step_contains_step_label(self, capsys):
        Instructions.step(2, 4, "Verifying signature")
        out = capsys.readouterr().out
        assert "Step 2/4" in out
        assert "Verifying signature" in out

    def test_step_contains_rules(self, capsys):
        Instructions.step(1, 3, "Downloading")
        out = capsys.readouterr().out
        assert "─" * 66 in out


class TestPreFlashChecklist:

    def test_managed_has_four_steps(self):
        text = Instructions.pre_flash_checklist(manage_bootloader=True)
        assert "4." in text
        assert "5." not in text

    def test_managed_mentions_tool_handling(self):
        text = Instructions.pre_flash_checklist(manage_bootloader=True)
        assert "tool will handle" in text.lower()

    def test_managed_no_manual_unlock_command(self):
        text = Instructions.pre_flash_checklist(manage_bootloader=True)
        assert "fastboot flashing unlock" not in text

    def test_manual_has_five_steps(self):
        text = Instructions.pre_flash_checklist(manage_bootloader=False)
        assert "5." in text

    def test_manual_includes_unlock_command(self):
        text = Instructions.pre_flash_checklist(manage_bootloader=False)
        assert "fastboot flashing unlock" in text

    def test_both_warn_about_data_wipe(self):
        for managed in (True, False):
            assert "ERASE EVERYTHING" in Instructions.pre_flash_checklist(
                managed
            )

    def test_contains_heavy_rule(self):
        text = Instructions.pre_flash_checklist(True)
        assert Instructions._H in text


class TestPreSideload:

    def test_contains_filename(self):
        text = Instructions.pre_sideload("shiba-ota_update-2026050900.zip")
        assert "shiba-ota_update-2026050900.zip" in text

    def test_contains_recovery_instructions(self):
        text = Instructions.pre_sideload("update.zip")
        assert "Recovery Mode" in text
        assert "Apply update from ADB" in text

    def test_contains_rules(self):
        text = Instructions.pre_sideload("update.zip")
        assert Instructions._H in text
        assert Instructions._r in text


class TestStaticBlocks:

    def test_post_flash_locked_mentions_success(self):
        assert (
            "installed and bootloader locked" in Instructions.post_flash_locked
        )

    def test_post_flash_manual_lock_has_command(self):
        assert "fastboot flashing lock" in Instructions.post_flash_manual_lock

    def test_flash_failure_help_has_url(self):
        assert "grapheneos.org/install/cli" in Instructions.flash_failure_help

    def test_unlock_prompt_has_steps(self):
        assert "Unlock the bootloader" in Instructions.unlock_prompt

    def test_lock_prompt_has_steps(self):
        assert "Lock the bootloader" in Instructions.lock_prompt

    def test_post_sideload_mentions_reboot(self):
        assert "Reboot system now" in Instructions.post_sideload

    def test_sideload_failure_help_has_tips(self):
        assert "Apply update from ADB" in Instructions.sideload_failure_help
