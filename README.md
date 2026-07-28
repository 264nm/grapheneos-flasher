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

### From PyPI (recommended)

```bash
uv tool install grapheneos-flasher
# or
pip install grapheneos-flasher
```

Then run:

```bash
grapheneos-flasher <device_codename> [options]
```

### From source

```bash
git clone https://github.com/264nm/grapheneos-flasher
cd grapheneos-flasher
uv sync
uv run grapheneos-flasher <device_codename> [options]
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
| `frankel` | Pixel 10 |
| `blazer` | Pixel 10 Pro |
| `mustang` | Pixel 10 Pro XL |
| `rango` | Pixel 10 Pro Fold |
| `stallion` | Pixel 10a |
| `tokay` | Pixel 9 |
| `caiman` | Pixel 9 Pro |
| `komodo` | Pixel 9 Pro XL |
| `comet` | Pixel 9 Pro Fold |
| `tegu` | Pixel 9a |
| `shiba` | Pixel 8 |
| `husky` | Pixel 8 Pro |
| `akita` | Pixel 8a |
| `felix` | Pixel Fold |
| `tangorpro` | Pixel Tablet |
| `panther` | Pixel 7 |
| `cheetah` | Pixel 7 Pro |
| `lynx` | Pixel 7a |
| `oriole` | Pixel 6 |
| `raven` | Pixel 6 Pro |
| `bluejay` | Pixel 6a |

The table above is a snapshot. The device list is checked live on every run,
so it stays correct without waiting for a release.

### Device support checks

On each run the tool fetches the current device list from the GrapheneOS FAQ
and checks the device you asked for:

- **End-of-life device** — the run stops before anything is downloaded:

  ```
    ✗  Pixel 5 (redfin) is end-of-life.
       GrapheneOS no longer publishes builds for this device and
       it no longer receives security updates.
  ```

- **Support ending within three months** — a warning, then the run continues:

  ```
    ⚠  OEM support for the Pixel 6 ends October 2026.
       After that date the device stops receiving full security
       updates. Consider moving to a newer device.
  ```

- **Supported device** — no message.

If the FAQ cannot be reached, the tool says so and falls back to the snapshot
bundled with the package (`grapheneos_flasher/data/devices.json`), so it still
works offline. That snapshot is refreshed weekly by the `update-devices`
workflow, which opens a pull request whenever GrapheneOS changes the list — it
is generated, not hand-edited. To refresh it locally:

```bash
uv run python scripts/update_devices.py
```

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

### End-to-end tests

Two e2e suites live in `tests/e2e/`:

**Stub device harness** (`-m e2e`, hermetic — runs in normal CI). Drives
the real CLI as a subprocess: downloads from a local HTTP server serving
a miniature ssh-signed release, verifies the signature with real
`ssh-keygen`, extracts, and walks the full bootloader state machine
(locked → unlocked → flashed → locked) against stub `fastboot`/`adb`
binaries that log every invocation.

```bash
uv run python -m pytest tests/e2e -m e2e
```

**Pixel emulator** (`-m emulator` — separate CI job). Runs against a real
Android device stack: a booted Pixel-profile AVD reached through real
platform-tools. Covers adb device detection and pins down why the flash
pipeline can't be emulator-tested (AVDs have no bootloader, so fastboot
never sees one).

These tests **skip unless an emulator is actually booted** — a bare
`pytest -m emulator` on a machine with no running AVD reports all tests
as skipped, which is expected, not a failure.

```bash
task emulator:start        # downloads + creates the AVD on first run, then boots it
task test:e2e:emulator
task emulator:stop
```

`emulator:setup` (run automatically by `emulator:start`) needs the Android
SDK command-line tools and a JDK. It defaults to `~/Library/Android/sdk`
and the JDK bundled with Android Studio; override with `ANDROID_HOME` and
`JAVA_HOME`. The AVD uses an arm64 API 34 image — edit `SYSTEM_IMAGE` in
`Taskfile.yml` for an x86_64 host.

To point the flasher (or tests) at a release mirror, set
`GRAPHENEOS_FLASHER_BASE_URL`.

### Releasing

The version lives in exactly one place:
`grapheneos_flasher/__init__.py` (`__version__`). `pyproject.toml` reads
it dynamically via hatchling, and the CLI banner imports it at runtime.

To cut a release, bump `__version__` and merge to `main` — CI does the
rest:

1. The release workflow runs on every push to `main` and compares
   `__version__` against the existing git tags.
2. If tag `v<version>` does not exist yet, it runs the test suite, then
   creates the tag and a GitHub Release (with build artifacts and
   generated notes) at that commit.
3. The wheel and sdist are published to PyPI via trusted publishing.

Pushes without a version bump skip all of this — only the cheap version
check runs. Manually pushing a `v*.*.*` tag still triggers the same
release path, as an escape hatch.

After bumping, run `uv lock` so `uv.lock` picks up the new project
version.

---

## License

MIT. Provided for educational and personal use.
Always verify the security of any flashing process against the
[official GrapheneOS documentation](https://grapheneos.org/install).
