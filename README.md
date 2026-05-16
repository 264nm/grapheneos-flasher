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
manual instructions at the end. Nothing is written to your device.

### Flash GrapheneOS (installs the OS, wipes all data)

```bash
uv run grapheneos-flasher shiba --flash
```

Runs through download → verify → extract, then presents a pre-flight checklist
and walks you through the flash interactively. After a successful flash, it
reminds you to lock the bootloader — a required step that the tool cannot skip
for you.

### Flash a specific version

```bash
uv run grapheneos-flasher shiba --version 2026050900 --flash
```

### Sideload an OTA update (updates an existing GrapheneOS install, preserves data)

```bash
uv run grapheneos-flasher shiba --sideload
```

Downloads the OTA update package for your device and version, verifies it, then
guides you through booting into recovery and sideloading via `adb sideload`.
Use this to update a device **already running GrapheneOS** — it is not a
substitute for a fresh flash.

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

For the authoritative list see
[grapheneos.org/faq#device-support](https://grapheneos.org/faq#device-support).

---

## What the tool does

### Fresh install (`--flash`)

1. **Download** the GrapheneOS public key (`allowed_signers`), the factory
   image zip, and its `.sig` signature file from `releases.grapheneos.org`.
2. **Verify** the signature with `ssh-keygen -Y verify`, exactly as the
   official guide prescribes.
3. **Extract** the archive with `tar xf`.
4. **Pre-flight checklist** — the tool pauses and shows you exactly which steps
   to complete on your device (OEM unlocking, bootloader unlock, fastboot mode)
   before you type `yes`.
5. **Flash** — runs `bash flash-all.sh` from the extracted directory.
6. **Post-flash instructions** — reminds you to run `fastboot flashing lock`
   and disable OEM unlocking after setup. **Do not skip this step.**

### OTA sideload (`--sideload`)

1. Downloads and verifies the OTA update package.
2. Guides you through booting into recovery mode and selecting
   *Apply update from ADB*.
3. Runs `adb sideload <ota.zip>`.

> **Note:** Sideloading is for updating a device that already runs GrapheneOS.
> For a fresh install, use `--flash` instead.

---

## Security

- Signature verification uses the same `ssh-keygen -Y verify` command as the
  official GrapheneOS CLI guide — no third-party crypto libraries.
- The tool refuses to flash if verification fails.
- All files are downloaded to an isolated temporary directory.
- The factory image's namespace is `"factory images"` and the identity is
  `contact@grapheneos.org`, matching GrapheneOS's published signing policy.

---

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest

# Run a specific test category
uv run pytest -m unit
uv run pytest -m integration   # requires network + platform-tools

# Type checking
uv run mypy grapheneos_flasher

# Formatting and linting
uv run black grapheneos_flasher tests
uv run isort grapheneos_flasher tests
uv run flake8 grapheneos_flasher tests

# Coverage report
uv run pytest --cov=grapheneos_flasher --cov-report=html
```

### Architecture

| Class | Responsibility |
|-------|---------------|
| `GrapheneOSFlasher` | Top-level orchestrator |
| `DownloadConfig` | URL and filename construction |
| `DefaultFileHandler` | HTTP downloads and archive extraction |
| `SecurityVerifier` | `ssh-keygen` signature verification |
| `DeviceManager` | `fastboot` and `adb` device interaction |

`FileHandler` is an abstract base class — you can supply a custom
implementation to `GrapheneOSFlasher(config, file_handler=...)` for testing
or alternative download strategies.

---

## License

MIT. Provided for educational and personal use.
Always verify the security of any flashing process against the
[official GrapheneOS documentation](https://grapheneos.org/install).
