"""
Unit tests for device support data and EOL checking
"""

import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from grapheneos_flasher.devices import (
    DeviceSupport,
    EOLDeviceError,
    check_device,
    fetch_device_support,
    get_device_support,
    load_bundled,
    months_until,
    parse_faq,
)

FIXTURE = Path(__file__).parent / "fixtures" / "faq_fixture.html"


@pytest.fixture
def faq_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def support(faq_html: str) -> DeviceSupport:
    return parse_faq(faq_html)


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────


class TestParseFaq:

    def test_extracts_supported_devices(self, support):
        assert support.supported == {
            "frankel": "Pixel 10",
            "comet": "Pixel 9 Pro Fold",
            "shiba": "Pixel 8",
            "tangorpro": "Pixel Tablet",
            "oriole": "Pixel 6",
        }

    def test_extracts_eol_devices(self, support):
        assert support.eol == {
            "redfin": "Pixel 5",
            "bramble": "Pixel 4a (5G)",
            "bullhead": "Nexus 5X",
        }

    def test_excludes_development_boards(self, support):
        # The legacy article has a second list of boards that were never
        # shipped as devices.
        assert "hikey" not in support.eol
        assert "hikey960" not in support.eol

    def test_codename_with_parenthesised_name(self, support):
        # "Pixel 4a (5G) (bramble)" — the codename is the last group.
        assert support.eol["bramble"] == "Pixel 4a (5G)"

    def test_support_end_is_last_day_of_month(self, support):
        assert support.support_end["oriole"] == date(2026, 10, 31)
        assert support.support_end["tangorpro"] == date(2028, 6, 30)
        assert support.support_end["frankel"] == date(2032, 8, 31)

    def test_support_end_covers_every_supported_device(self, support):
        assert set(support.support_end) == set(support.supported)

    def test_records_generation_date(self, support):
        assert support.generated == date.today().isoformat()

    def test_missing_section_raises(self):
        with pytest.raises(ValueError, match="supported-devices"):
            parse_faq("<html><body>nothing here</body></html>")

    def test_empty_supported_list_raises(self, faq_html):
        gutted = faq_html.replace("<li>Pixel 10 (frankel)</li>", "")
        gutted = gutted.replace("<li>Pixel 9 Pro Fold (comet)</li>", "")
        gutted = gutted.replace("<li>Pixel 8 (shiba)</li>", "")
        gutted = gutted.replace("<li>Pixel Tablet (tangorpro)</li>", "")
        gutted = gutted.replace("<li>Pixel 6 (oriole)</li>", "")
        with pytest.raises(ValueError, match="no supported devices"):
            parse_faq(gutted)


# ─────────────────────────────────────────────────────────────────────────────
# Serialisation
# ─────────────────────────────────────────────────────────────────────────────


class TestSerialisation:

    def test_round_trip(self, support):
        restored = DeviceSupport.from_json(support.to_json())
        assert restored.supported == support.supported
        assert restored.eol == support.eol
        assert restored.support_end == support.support_end
        assert restored.generated == support.generated

    def test_keys_are_sorted(self, support):
        payload = support.to_json()
        codenames = sorted(support.supported)
        positions = [payload.index(f'"{c}"') for c in codenames]
        assert positions == sorted(positions)

    def test_bundled_snapshot_loads(self):
        bundled = load_bundled()
        assert bundled.supported
        assert bundled.eol
        assert "shiba" in bundled.supported


# ─────────────────────────────────────────────────────────────────────────────
# Fetching
# ─────────────────────────────────────────────────────────────────────────────


def _response(html: str) -> Mock:
    response = Mock()
    response.read.return_value = html.encode("utf-8")
    return response


class TestFetchDeviceSupport:

    def test_uses_primary_url(self, faq_html):
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value = _response(faq_html)
            result = fetch_device_support()

        assert result is not None
        assert "shiba" in result.supported
        assert mock_open.call_count == 1

    def test_passes_timeout(self, faq_html):
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value = _response(faq_html)
            fetch_device_support(timeout=3.0)

        assert mock_open.call_args.kwargs["timeout"] == 3.0

    def test_falls_back_to_second_url(self, faq_html):
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [
                urllib.error.URLError("down"),
                Mock(
                    __enter__=Mock(return_value=_response(faq_html)),
                    __exit__=Mock(return_value=False),
                ),
            ]
            result = fetch_device_support()

        assert result is not None
        assert mock_open.call_count == 2

    def test_returns_none_when_all_urls_fail(self):
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = urllib.error.URLError("offline")
            assert fetch_device_support() is None

    def test_returns_none_on_unparseable_markup(self):
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value = _response(
                "<html>redesigned</html>"
            )
            assert fetch_device_support() is None

    def test_get_device_support_falls_back_to_bundled(self):
        with patch(
            "grapheneos_flasher.devices.fetch_device_support",
            return_value=None,
        ):
            support, is_live = get_device_support()

        assert is_live is False
        assert "shiba" in support.supported

    def test_get_device_support_offline_skips_network(self):
        with patch("urllib.request.urlopen") as mock_open:
            support, is_live = get_device_support(offline=True)

        assert is_live is False
        assert support.supported
        mock_open.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Support policy
# ─────────────────────────────────────────────────────────────────────────────


class TestMonthsUntil:

    def test_same_month_is_zero(self):
        assert months_until(date(2026, 7, 31), date(2026, 7, 1)) == 0

    def test_across_year_boundary(self):
        assert months_until(date(2027, 1, 31), date(2026, 10, 15)) == 3

    def test_past_date_is_negative(self):
        assert months_until(date(2026, 1, 31), date(2026, 7, 1)) == -6


class TestCheckDevice:

    def test_eol_device_raises(self, support):
        with pytest.raises(EOLDeviceError) as exc:
            check_device("redfin", support, today=date(2026, 7, 28))

        assert exc.value.codename == "redfin"
        assert exc.value.name == "Pixel 5"

    def test_supported_device_is_silent(self, support):
        assert check_device("shiba", support, today=date(2026, 7, 28)) is None

    def test_warns_when_support_ends_within_three_months(self, support):
        # Pixel 6 support ends October 2026.
        warning = check_device("oriole", support, today=date(2026, 7, 28))

        assert warning is not None
        assert "Pixel 6" in warning
        assert "October 2026" in warning

    def test_warns_on_exact_boundary(self, support):
        assert check_device("oriole", support, today=date(2026, 7, 1))

    def test_silent_four_months_out(self, support):
        assert check_device("oriole", support, today=date(2026, 6, 30)) is None

    def test_expired_support_raises(self, support):
        with pytest.raises(EOLDeviceError):
            check_device("oriole", support, today=date(2026, 11, 1))

    def test_unknown_codename_is_silent(self, support):
        # Unknown devices are the caller's problem, not an error here.
        assert (
            check_device("nosuchdevice", support, today=date(2026, 7, 28))
            is None
        )

    def test_device_without_end_date_is_silent(self):
        support = DeviceSupport(supported={"newphone": "Pixel 99"}, eol={})
        assert (
            check_device("newphone", support, today=date(2026, 7, 28)) is None
        )
