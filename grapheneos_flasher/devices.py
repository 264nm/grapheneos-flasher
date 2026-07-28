"""
Device support data: which devices GrapheneOS supports, which are
end-of-life, and when OEM support runs out.

Data is fetched from the GrapheneOS FAQ at runtime and falls back to a
snapshot bundled with the package (data/devices.json, refreshed by CI).
"""

import calendar
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from importlib import resources
from typing import Any

# The FAQ is served from the site and from the source repository. Both
# return the same document; the repository copy is tried first because it
# is a static file with no rendering in front of it.
FAQ_URLS = (
    "https://raw.githubusercontent.com/GrapheneOS/grapheneos.org/main/static/faq.html",
    "https://grapheneos.org/faq",
)

BUNDLED_DATA = "devices.json"

# Warn when OEM support ends within this many months.
EOL_WARNING_MONTHS = 3

_ARTICLE_RE = r'<article id="{0}">(.*?)</article>'
# "Pixel 10 Pro Fold (rango)" / "Pixel 4a (5G) (bramble)" — the codename is
# the final parenthesised group, so match greedily up to the last one.
_DEVICE_RE = re.compile(r"<li>\s*(.+)\s*\(([a-z0-9]+)\)\s*</li>")
_ROW_RE = re.compile(
    r"<tr>\s*<td>(.*?)</td>\s*<td>([A-Z][a-z]+ \d{4})</td>", re.DOTALL
)


class EOLDeviceError(Exception):
    """Raised when the target device is no longer supported by GrapheneOS."""

    def __init__(self, codename: str, name: str) -> None:
        self.codename = codename
        self.name = name
        super().__init__(f"{name} ({codename}) is end-of-life")


@dataclass(frozen=True)
class DeviceSupport:
    """A snapshot of GrapheneOS device support."""

    supported: dict[str, str] = field(default_factory=dict)
    eol: dict[str, str] = field(default_factory=dict)
    support_end: dict[str, date] = field(default_factory=dict)
    generated: str = ""

    def to_json(self) -> str:
        """Serialise to the on-disk format, with stable key ordering."""
        return json.dumps(
            {
                "generated": self.generated,
                "supported": dict(sorted(self.supported.items())),
                "eol": dict(sorted(self.eol.items())),
                "support_end": {
                    k: v.isoformat()
                    for k, v in sorted(self.support_end.items())
                },
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> "DeviceSupport":
        """Load from the on-disk format."""
        data: dict[str, Any] = json.loads(raw)
        return cls(
            supported=dict(data["supported"]),
            eol=dict(data["eol"]),
            support_end={
                k: date.fromisoformat(v)
                for k, v in data.get("support_end", {}).items()
            },
            generated=str(data.get("generated", "")),
        )


def _end_of_month(month_year: str) -> date:
    """'October 2026' → date(2026, 10, 31) — support lasts the whole month."""
    parsed = datetime.strptime(month_year, "%B %Y")
    last = calendar.monthrange(parsed.year, parsed.month)[1]
    return date(parsed.year, parsed.month, last)


def _article(html: str, article_id: str) -> str:
    match = re.search(_ARTICLE_RE.format(article_id), html, re.DOTALL)
    if match is None:
        raise ValueError(f"FAQ is missing the '{article_id}' section")
    return match.group(1)


def _devices_in(
    section: str, *, first_list_only: bool = False
) -> dict[str, str]:
    """Map codename → marketing name for every <li> in a section."""
    if first_list_only:
        # 'which-legacy-devices' has a second list of development boards
        # that were never shipped as devices; keep only the first list.
        lists = re.findall(r"<ul>(.*?)</ul>", section, re.DOTALL)
        section = lists[0] if lists else ""
    return {
        codename: name.strip()
        for name, codename in _DEVICE_RE.findall(section)
    }


def parse_faq(html: str) -> DeviceSupport:
    """
    Extract device support data from the GrapheneOS FAQ page.

    Raises ValueError if the expected sections are missing or empty, so
    that markup changes surface as a fetch failure rather than as an
    empty device list.
    """
    supported = _devices_in(_article(html, "supported-devices"))
    eol = _devices_in(
        _article(html, "which-legacy-devices"), first_list_only=True
    )
    if not supported:
        raise ValueError("FAQ listed no supported devices")
    if not eol:
        raise ValueError("FAQ listed no end-of-life devices")

    # The lifetime table is keyed by marketing name ("Google Pixel 6"),
    # so join it back to codenames through the supported list.
    by_name = {name: codename for codename, name in supported.items()}
    support_end: dict[str, date] = {}
    for raw_name, month_year in _ROW_RE.findall(
        _article(html, "device-lifetime")
    ):
        name = re.sub(r"^Google\s+", "", raw_name.strip())
        codename = by_name.get(name)
        if codename is not None:
            support_end[codename] = _end_of_month(month_year)

    if not support_end:
        raise ValueError("FAQ listed no device support end dates")

    return DeviceSupport(
        supported=supported,
        eol=eol,
        support_end=support_end,
        generated=date.today().isoformat(),
    )


def fetch_device_support(timeout: float = 10.0) -> DeviceSupport | None:
    """
    Fetch live device support data, returning None if it cannot be
    retrieved or parsed. Callers fall back to the bundled snapshot.
    """
    for url in FAQ_URLS:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                html = response.read().decode("utf-8")
            return parse_faq(html)
        except urllib.error.URLError, ValueError, OSError:
            continue
    return None


def load_bundled() -> DeviceSupport:
    """Load the snapshot shipped with the package."""
    raw = (
        resources.files("grapheneos_flasher.data")
        .joinpath(BUNDLED_DATA)
        .read_text(encoding="utf-8")
    )
    return DeviceSupport.from_json(raw)


def get_device_support(*, offline: bool = False) -> tuple[DeviceSupport, bool]:
    """
    Return (support data, is_live). Falls back to the bundled snapshot
    when the live fetch fails, so the tool keeps working offline.
    """
    if not offline:
        live = fetch_device_support()
        if live is not None:
            return live, True
    return load_bundled(), False


def months_until(end: date, today: date) -> int:
    """Whole months from today until end (negative once end has passed)."""
    return (end.year - today.year) * 12 + (end.month - today.month)


def check_device(
    codename: str, support: DeviceSupport, today: date | None = None
) -> str | None:
    """
    Validate a device against support data.

    Returns a warning message if support ends soon, or None if the device
    is comfortably supported or simply unrecognised (unknown codenames are
    handled by the caller).

    Raises EOLDeviceError if the device is end-of-life.
    """
    today = today or date.today()

    if codename in support.eol:
        raise EOLDeviceError(codename, support.eol[codename])

    end = support.support_end.get(codename)
    if end is None:
        return None

    remaining = months_until(end, today)
    if remaining < 0:
        raise EOLDeviceError(
            codename, support.supported.get(codename, codename)
        )
    if remaining <= EOL_WARNING_MONTHS:
        return (
            f"OEM support for the "
            f"{support.supported.get(codename, codename)} ends "
            f"{end.strftime('%B %Y')}."
        )
    return None
