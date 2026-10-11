"""
Fixtures for the end-to-end test suites.

Two harnesses are wired up here:

* A local "release server" — an HTTP server serving a miniature,
  genuinely ssh-signed release, so the real download and
  signature-verification code paths run without touching the network.

* Stub ``fastboot`` / ``adb`` executables (see harness.py) placed at
  the front of PATH, backed by state files so tests can steer and
  observe the fake device.
"""

import os
import subprocess
import sys
import tarfile
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest
from harness import (
    DEVICE,
    FAKE_ADB,
    FAKE_FASTBOOT,
    FAKE_FLASH_ALL,
    REPO_ROOT,
    VERSION,
    FakeDevice,
    write_executable,
)


@pytest.fixture(scope="session")
def release_dir(tmp_path_factory) -> Path:
    """Build a miniature release, signed exactly like the real one."""
    root = tmp_path_factory.mktemp("release")

    # Signing key + allowed_signers, matching GrapheneOS's scheme
    # (ssh-keygen -Y with identity/namespace pinned in core.py).
    key = root / "signing_key"
    subprocess.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "contact@grapheneos.org",
            "-f",
            str(key),
        ],
        check=True,
        capture_output=True,
    )
    pubkey = (root / "signing_key.pub").read_text().strip()
    (root / "allowed_signers").write_text(
        f'contact@grapheneos.org namespaces="factory images" {pubkey}\n'
    )

    # Factory image payload. core.py extracts with `tar xf`, so the
    # archive is tar-format under its .zip name — both GNU tar and
    # bsdtar auto-detect by content, keeping the fixture portable.
    payload = root / f"{DEVICE}-install-{VERSION}"
    payload.mkdir()
    write_executable(payload / "flash-all.sh", FAKE_FLASH_ALL)
    (payload / "image-fake.zip").write_bytes(b"not a real image")

    archive = root / f"{DEVICE}-install-{VERSION}.zip"
    with tarfile.open(archive, "w") as tar:
        tar.add(payload, arcname=payload.name)

    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            "factory images",
            str(archive),
        ],
        check=True,
        capture_output=True,
    )

    (root / f"{DEVICE}-ota_update-{VERSION}.zip").write_bytes(
        b"fake ota payload"
    )
    return root


@pytest.fixture(scope="session")
def release_server(release_dir: Path):
    """Serve the fake release over HTTP on an ephemeral local port."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(release_dir))
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def fake_device(tmp_path: Path) -> FakeDevice:
    """Stub fastboot/adb on PATH, device starting locked and booted."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_executable(bin_dir / "fastboot", FAKE_FASTBOOT)
    write_executable(bin_dir / "adb", FAKE_ADB)

    device = FakeDevice(
        bin_dir=bin_dir,
        state_file=tmp_path / "bootloader_state",
        adb_state_file=tmp_path / "adb_state",
        log_file=tmp_path / "tool_calls.log",
    )
    device.set_bootloader_state("locked")
    device.set_adb_mode("device")
    return device


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


@pytest.fixture
def run_cli(fake_device: FakeDevice, release_server: str, work_dir: Path):
    """Run the real CLI as a subprocess against both harnesses."""

    def _run(
        *args: str, answers: str = "", timeout: int = 120
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = f"{fake_device.bin_dir}{os.pathsep}{env['PATH']}"
        env["FAKE_DEVICE_STATE"] = str(fake_device.state_file)
        env["FAKE_ADB_STATE"] = str(fake_device.adb_state_file)
        env["FAKE_TOOL_LOG"] = str(fake_device.log_file)
        env["GRAPHENEOS_FLASHER_BASE_URL"] = release_server
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "grapheneos_flasher",
                *args,
                "--version",
                VERSION,
                "--work-dir",
                str(work_dir),
            ],
            input=answers,
            text=True,
            capture_output=True,
            env=env,
            timeout=timeout,
            cwd=REPO_ROOT,
        )

    return _run
