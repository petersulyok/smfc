#!/usr/bin/env python3
#
#   test_11_platform.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   Unit tests for smfc.platform module (X10QBi, create_platform).
#
import subprocess
from typing import List
import pytest
from mock import MagicMock, call
from smfc.platform import FanMode, GenericPlatform, X10QBi, create_platform


class TestX10QBi:
    """Unit test class for X10QBi platform."""

    @pytest.mark.parametrize(
        "mode, error",
        [
            (0, "X10QBi.get_fan_mode() 1"),
            (1, "X10QBi.get_fan_mode() 2"),
            (4, "X10QBi.get_fan_mode() 3"),
        ],
    )
    def test_get_fan_mode_p(self, mode: int, error: str) -> None:
        """Positive test for X10QBi.get_fan_mode()."""
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {mode:02}")
        platform = X10QBi("X10QBi", mock_exec)
        assert platform.get_fan_mode() == mode, error
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x00"])

    @pytest.mark.parametrize(
        "zone, hex_output, expected_level, error",
        [
            (16, " 80", 0x80, "X10QBi.get_fan_level() 1"),
            (17, " ff", 0xFF, "X10QBi.get_fan_level() 2"),
            (18, " 00", 0x00, "X10QBi.get_fan_level() 3"),
            (19, " 40", 0x40, "X10QBi.get_fan_level() 4"),
        ],
    )
    def test_get_fan_level_p(self, zone: int, hex_output: str, expected_level: int, error: str) -> None:
        """Positive test for X10QBi.get_fan_level() with valid zones (16-19)."""
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=hex_output)
        platform = X10QBi("X10QBi", mock_exec)
        assert platform.get_fan_level(zone) == expected_level, error
        mock_exec.assert_called_with(["raw", "0x30", "0x90", "0x5c", "0x03", f"0x{zone:x}", "0x01"])

    @pytest.mark.parametrize(
        "zone, error",
        [
            (0, "X10QBi.get_fan_level() 5"),
            (1, "X10QBi.get_fan_level() 6"),
            (15, "X10QBi.get_fan_level() 7"),
            (20, "X10QBi.get_fan_level() 8"),
        ],
    )
    def test_get_fan_level_n(self, zone: int, error: str) -> None:
        """Negative test for X10QBi.get_fan_level() with invalid zones."""
        mock_exec = MagicMock()
        platform = X10QBi("X10QBi", mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.get_fan_level(zone)
        assert cm.type is ValueError, error

    def test_set_fan_manual_mode(self) -> None:
        """Test X10QBi.set_fan_manual_mode() makes 11 IPMI calls (10 TMFR + 1 FOMC)."""
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = X10QBi("X10QBi", mock_exec)
        platform.set_fan_manual_mode()
        assert mock_exec.call_count == 11
        expected_calls = [
            call(["raw", "0x30", "0x91", "0x5c", "0x03", "0x00", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x03", "0x01", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x03", "0x02", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x03", "0x03", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x04", "0x00", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x04", "0x01", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x04", "0x02", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x04", "0x03", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x04", "0x04", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x04", "0x05", "0x00"]),
            call(["raw", "0x30", "0x91", "0x5c", "0x03", "0x07", "0x00"]),
        ]
        mock_exec.assert_has_calls(expected_calls)

    @pytest.mark.parametrize(
        "mode, error",
        [
            (FanMode.STANDARD, "X10QBi.set_fan_mode() 1"),
            (FanMode.FULL, "X10QBi.set_fan_mode() 2"),
            (FanMode.HEAVY_IO, "X10QBi.set_fan_mode() 3"),
        ],
    )
    def test_set_fan_mode_p(self, mode: int, error: str) -> None:
        """Positive test for X10QBi.set_fan_mode() with valid modes."""
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = X10QBi("X10QBi", mock_exec)
        platform.set_fan_mode(mode)
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])
        assert mock_exec.call_count == 1, error

    @pytest.mark.parametrize(
        "mode, error",
        [
            (FanMode.OPTIMAL, "X10QBi.set_fan_mode() 4"),
            (FanMode.PUE, "X10QBi.set_fan_mode() 5"),
            (-1, "X10QBi.set_fan_mode() 6"),
            (100, "X10QBi.set_fan_mode() 7"),
        ],
    )
    def test_set_fan_mode_n(self, mode: int, error: str) -> None:
        """Negative test for X10QBi.set_fan_mode() with invalid modes (OPTIMAL, PUE not supported)."""
        mock_exec = MagicMock()
        platform = X10QBi("X10QBi", mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_mode(mode)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zone, level, expected_normalised, error",
        [
            (16, 100, 255, "X10QBi.set_fan_level() 1"),
            (17, 50, 127,  "X10QBi.set_fan_level() 2"),
            (18, 0, 0,     "X10QBi.set_fan_level() 3"),
            (19, 75, 191,  "X10QBi.set_fan_level() 4"),
        ],
    )
    def test_set_fan_level_p(self, zone: int, level: int, expected_normalised: int, error: str) -> None:
        """Positive test for X10QBi.set_fan_level() with level normalization (0-100 -> 0-255)."""
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = X10QBi("X10QBi", mock_exec)
        platform.set_fan_level(zone, level)
        assert mock_exec.call_count == 12, error  # 11 (manual mode) + 1 (set level)
        mock_exec.assert_called_with(
            ["raw", "0x30", "0x91", "0x5c", "0x03", f"0x{zone:02x}", f"0x{expected_normalised:02x}"]
        )

    @pytest.mark.parametrize(
        "zone, level, error",
        [
            (0, 50, "X10QBi.set_fan_level() 5"),
            (15, 50, "X10QBi.set_fan_level() 6"),
            (20, 50, "X10QBi.set_fan_level() 7"),
            (16, -1, "X10QBi.set_fan_level() 8"),
            (16, 101, "X10QBi.set_fan_level() 9"),
        ],
    )
    def test_set_fan_level_n(self, zone: int, level: int, error: str) -> None:
        """Negative test for X10QBi.set_fan_level() with invalid parameters."""
        mock_exec = MagicMock()
        platform = X10QBi("X10QBi", mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_level(zone, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zones, level, expected_normalised, error",
        [
            ([16, 17], 100, 255, "X10QBi.set_multiple_fan_levels() 1"),
            ([16, 17, 18, 19], 50, 127, "X10QBi.set_multiple_fan_levels() 2"),
            ([18], 0, 0, "X10QBi.set_multiple_fan_levels() 3"),
        ],
    )
    def test_set_multiple_fan_levels_p(self, zones: List[int], level: int, expected_normalised: int,
                                       error: str) -> None:
        """Positive test for X10QBi.set_multiple_fan_levels() with level normalization."""
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = X10QBi("X10QBi", mock_exec)
        platform.set_multiple_fan_levels(zones, level)
        assert mock_exec.call_count == 11 + len(zones), error  # 11 (manual mode) + N zones
        level_hex = f"0x{expected_normalised:02x}"
        zone_calls = [call(["raw", "0x30", "0x91", "0x5c", "0x03", f"0x{z:02x}", level_hex]) for z in zones]
        mock_exec.assert_has_calls(zone_calls)

    @pytest.mark.parametrize(
        "zones, level, error",
        [
            ([0, 16], 50, "X10QBi.set_multiple_fan_levels() 4"),
            ([16, 20], 50, "X10QBi.set_multiple_fan_levels() 5"),
            ([16], -1, "X10QBi.set_multiple_fan_levels() 6"),
            ([16], 101, "X10QBi.set_multiple_fan_levels() 7"),
        ],
    )
    def test_set_multiple_fan_levels_n(self, zones: List[int], level: int, error: str) -> None:
        """Negative test for X10QBi.set_multiple_fan_levels() with invalid parameters."""
        mock_exec = MagicMock()
        platform = X10QBi("X10QBi", mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error


class TestCreatePlatform:
    """Unit test class for create_platform() factory function."""

    def test_create_x10qbi(self) -> None:
        """Test that create_platform returns X10QBi for 'X10QBi' name."""
        mock_exec = MagicMock()
        platform = create_platform("X10QBi", mock_exec)
        assert isinstance(platform, X10QBi)
        assert platform.name == "X10QBi"

    def test_create_generic(self) -> None:
        """Test that create_platform returns GenericPlatform for unknown names."""
        mock_exec = MagicMock()
        platform = create_platform("X11SCH-LN4F", mock_exec)
        assert isinstance(platform, GenericPlatform)
        assert platform.name == "X11SCH-LN4F"


# End.
