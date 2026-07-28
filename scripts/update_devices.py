#!/usr/bin/env python3
"""
Refresh the bundled device support snapshot from the GrapheneOS FAQ.

  python scripts/update_devices.py           # rewrite devices.json
  python scripts/update_devices.py --check    # validate the committed file

--check does not hit the network: it only confirms the committed snapshot
parses and is non-empty, so CI never fails because a new device shipped.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grapheneos_flasher.devices import (  # noqa: E402
    DeviceSupport,
    fetch_device_support,
)

DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "grapheneos_flasher"
    / "data"
    / "devices.json"
)


def check() -> int:
    if not DATA_FILE.exists():
        print(f"missing {DATA_FILE}", file=sys.stderr)
        return 1
    try:
        support = DeviceSupport.from_json(DATA_FILE.read_text())
    except (ValueError, KeyError) as exc:
        print(f"{DATA_FILE} is not valid: {exc}", file=sys.stderr)
        return 1
    if not support.supported or not support.eol:
        print(f"{DATA_FILE} has empty device lists", file=sys.stderr)
        return 1
    print(
        f"ok — {len(support.supported)} supported, {len(support.eol)} "
        f"end-of-life, generated {support.generated or 'unknown'}"
    )
    return 0


def update() -> int:
    support = fetch_device_support()
    if support is None:
        print("could not fetch device support data", file=sys.stderr)
        return 1

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(support.to_json() + "\n", encoding="utf-8")
    print(
        f"wrote {DATA_FILE} — {len(support.supported)} supported, "
        f"{len(support.eol)} end-of-life"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the committed snapshot instead of refreshing it",
    )
    args = parser.parse_args()
    return check() if args.check else update()


if __name__ == "__main__":
    sys.exit(main())
