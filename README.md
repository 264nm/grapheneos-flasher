# GrapheneOS Flasher

A Python tool that automates the download, cryptographic verification, and
flashing of [GrapheneOS](https://grapheneos.org) factory images.

It follows the official
[CLI installation guide](https://grapheneos.org/install/cli) step-by-step and
surfaces clear, actionable prompts at each stage so you always know what is
happening and why.

---

## Requirements

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.14+ | Runtime |
| OpenSSH (`ssh-keygen`) | any | Signature verification |
| Android platform-tools (`fastboot`, `adb`) | 35.0.1+ | Device communication |

**Install platform-tools:**
Download from [developer.android.com](https://developer.android.com/tools/releases/platform-tools)
and add the extracted directory to your `PATH`.

---

## Installation

This tool is not yet published to PyPI. Run it directly from source using
[uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/yourusername/grapheneos-flasher
cd grapheneos-flasher
uv sync
```

Run the tool with:

```bash
uv run grapheneos-flasher <device_codename> [options]
```

Or activate the virtual environment first:

```bash
source .venv/bin/activate
grapheneos-flasher <device_codename> [options]
```

---

## Usage

### Download and verify only (safe — no device changes)

```bash
uv run grapheneos-flasher shiba
```

Downloads the latest factory image and signature, verifies the cryptographic
signature against GrapheneOS's public key, and extracts the archive. Prints
manual step-by-step instructions at the end. Nothing is written to your device.

### Flash GrapheneOS (installs the OS, wipes all data)

```bash
uv run grapheneos-flasher shiba --flash
```

Runs through download → verify → extract, then presents a pre-flight checklist
and walks you through the flash interactively. The tool handles unlocking and
re-locking the bootloader automatically.

### Flash without bootloader management

```bash
uv run grapheneos-flasher shiba --flash --no-bootloader-mgmt
```

Skips automatic unlock/lock. You must run `fastboot flashing unlock` before
flashing and `fastboot flashing lock` afterwards. The tool still validates that
the bootloader is unlocked before proceeding.

### Flash a specific version

```bash
uv run grapheneos-flasher shiba --version 2026050900 --flash
```

### Sideload an OTA update (updates an existing GrapheneOS install, preserves data)

```bash
uv run grapheneos-flasher shiba --sideload
```

Downloads only the OTA update package (not the full factory image), then guides
you through booting into recovery and sideloading via `adb sideload`. Use this
to update a device **already running GrapheneOS** — it is not a substitute for
a fresh flash.

### Re-running without re-downloading

By default, files are saved in your current working directory. Running the same
command again will skip files that are already present:

```
  ✓  shiba-install-2026050900.zip  (1573 MB)  (already exists, skipping)
```

Use `--work-dir` to specify a different location:

```bash
uv run grapheneos-flasher shiba --work-dir ~/grapheneos-files
```

If the directory does not exist the tool falls back to a system temp directory.

---

## Supported devices

| Codename | Device |
|----------|--------|
| `tokay` | Pixel 9a |
| `akita` | Pixel 9 |
| `comet` | Pixel 9 Pro |
| `caiman` | Pixel 9 Pro XL |
| `tegu` | Pixel 9 Pro Fold |
| `shiba` | Pixel 8 |
| `husky` | Pixel 8 Pro |
| `axolotl` | Pixel 8a |
| `felix` | Pixel Fold |
| `tangorpro` | Pixel Tablet |
| `panther` | Pixel 7 |
| `cheetah` | Pixel 7 Pro |
| `lynx` | Pixel 7a |
| `oriole` | Pixel 6 |
| `raven` | Pixel 6 Pro |
| `bluejay` | Pixel 6a |

Devices are modelled by the `Device` enum in `cli.py` — member name is the
codename, value is the display name. `Device.from_codename(s)` returns the
member or `None` for unknown inputs.

For the authoritative list see
[grapheneos.org/faq#device-support](https://grapheneos.org/faq#device-support).

---

## What the tool does

### Fresh install (`--flash`)

1. **Download** `allowed_signers`, the factory image zip, and its `.sig`
   signature file from `releases.grapheneos.org`. Skips files already present
   in the working directory.
2. **Verify** the signature with `ssh-keygen -Y verify`, exactly as the
   official guide prescribes.
3. **Extract** the archive with `tar xf`.
4. **Pre-flight checklist** — pauses and shows what to prepare on your device
   before you type `yes`.
5. **Unlock** — checks `fastboot getvar unlocked`. If locked, sends
   `fastboot flashing unlock`, waits for the device to wipe and reboot back
   into fastboot, and verifies the new state. Skipped with `--no-bootloader-mgmt`.
6. **Flash** — runs `bash flash-all.sh` from inside the extracted directory.
7. **Lock** — sends `fastboot flashing lock` and verifies the bootloader is
   locked before the device reboots into GrapheneOS setup.
   Skipped with `--no-bootloader-mgmt` (reminder shown instead).

### OTA sideload (`--sideload`)

1. Downloads only the OTA update package (no factory image).
2. Guides you through booting into recovery mode and selecting
   *Apply update from ADB*.
3. Runs `adb sideload <ota.zip>`.

> **Note:** Sideloading is for updating a device already running GrapheneOS.
> For a fresh install, use `--flash` instead.

---

## Security

- Signature verification uses the same `ssh-keygen -Y verify` command as the
  official GrapheneOS CLI guide — no third-party crypto libraries.
- The tool refuses to flash if verification fails.
- All files are downloaded to the working directory (default: CWD).
- The factory image namespace is `"factory images"` and the identity is
  `contact@grapheneos.org`, matching GrapheneOS's published signing policy.

---

## Architecture

| Module | Class | Responsibility |
|--------|-------|---------------|
| `ui.py` | `Instructions` | Terminal output helpers (`ok`, `fail`, `info`, `warn`, `block`, `step`) and all user-facing instruction text |
| `core.py` | `GrapheneOSFlasher` | Top-level orchestrator |
| `core.py` | `DownloadConfig` | URL and filename construction |
| `core.py` | `DefaultFileHandler` | HTTP downloads and archive extraction |
| `core.py` | `SecurityVerifier` | `ssh-keygen` signature verification |
| `core.py` | `DeviceManager` | `fastboot` and `adb` device interaction, bootloader management |
| `cli.py` | — | Argument parsing and entry point |

`FileHandler` is an abstract base class — supply a custom implementation to
`GrapheneOSFlasher(config, file_handler=...)` for testing or alternative
download strategies.

---

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
uv run python -m pytest

# Run a specific test file
uv run python -m pytest tests/test_ui.py
uv run python -m pytest tests/test_core.py
uv run python -m pytest tests/test_cli.py

# With coverage
uv run python -m pytest --cov=grapheneos_flasher --cov-report=html

# Type checking
uv run mypy grapheneos_flasher

# Formatting and linting
uv run black grapheneos_flasher tests
uv run isort grapheneos_flasher tests
uv run flake8 grapheneos_flasher tests
```

---

## License

MIT. Provided for educational and personal use.
Always verify the security of any flashing process against the
[official GrapheneOS documentation](https://grapheneos.org/install).
