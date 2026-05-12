#!/usr/bin/env python3
#
#   test_genericx9.py (C) 2025-2026, Peter Sulyok
#   Unit tests for smfc.genericx9 module (GenericX9Platform).
#
import subprocess
from typing import List
import pytest
from mock import MagicMock, call
from smfc.platform import FanMode, PlatformName
from smfc.genericx9 import GenericX9Platform


class TestGenericX9Platform:
    """Unit test class for GenericX9Platform platform."""

    @pytest.mark.parametrize(
        "mode, error_str",
        [
            # STANDARD mode
            (0, "GenericX9Platform.get_fan_mode() p1"),
            # FULL mode
            (1, "GenericX9Platform.get_fan_mode() p2"),
            # OPTIMAL mode
            (2, "GenericX9Platform.get_fan_mode() p3"),
            # HEAVY_IO mode
            (4, "GenericX9Platform.get_fan_mode() p4"),
        ],
    )
    def test_get_fan_mode_p(self, mode: int, error_str: str) -> None:
        """Positive unit test for GenericX9Platform.get_fan_mode() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call get_fan_mode()
        - ASSERT: if the returned fan mode is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {mode:02}")
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        assert platform.get_fan_mode() == mode, error_str
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x00"])

    @pytest.mark.parametrize(
        "zone, hex_output, expected_level, error_str",
        [
            # Zone 0, level 0x80
            (0, " 80", 0x80, "GenericX9Platform.get_fan_level() p1"),
            # Zone 1, level 0xFF
            (1, " ff", 0xFF, "GenericX9Platform.get_fan_level() p2"),
            # Zone 2, level 0x00
            (2, " 00", 0x00, "GenericX9Platform.get_fan_level() p3"),
            # Zone 3, level 0x40
            (3, " 40", 0x40, "GenericX9Platform.get_fan_level() p4"),
        ],
    )
    def test_get_fan_level_p(self, zone: int, hex_output: str, expected_level: int, error_str: str) -> None:
        """Positive unit test for GenericX9Platform.get_fan_level() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call get_fan_level() with valid zones (0-3)
        - ASSERT: if the returned fan level is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=hex_output)
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        assert platform.get_fan_level(zone) == expected_level, error_str
        reg = 0x10 + zone
        mock_exec.assert_called_with(["raw", "0x30", "0x90", "0x5a", "0x03", f"0x{reg:x}", "0x01"])

    @pytest.mark.parametrize(
        "zone, error_str",
        [
            # Invalid zone: negative
            (-1, "GenericX9Platform.get_fan_level() n1"),
            # Invalid zone: over 3
            (4, "GenericX9Platform.get_fan_level() n2"),
        ],
    )
    def test_get_fan_level_n(self, zone: int, error_str: str) -> None:
        """Negative unit test for GenericX9Platform.get_fan_level() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call get_fan_level() with invalid zones (outside 0-3)
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.get_fan_level(zone)
        assert cm.type is ValueError, error_str

    def test_set_fan_manual_mode(self) -> None:
        """Positive unit test for GenericX9Platform.set_fan_manual_mode() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_manual_mode()
        - ASSERT: if the mock exec was called (should be a no-op)
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        platform.set_fan_manual_mode()
        mock_exec.assert_not_called()

    @pytest.mark.parametrize(
        "mode, error_str",
        [
            # STANDARD mode
            (FanMode.STANDARD, "GenericX9Platform.set_fan_mode() p1"),
            # FULL mode
            (FanMode.FULL, "GenericX9Platform.set_fan_mode() p2"),
            # OPTIMAL mode
            (FanMode.OPTIMAL, "GenericX9Platform.set_fan_mode() p3"),
            # HEAVY_IO mode
            (FanMode.HEAVY_IO, "GenericX9Platform.set_fan_mode() p4"),
        ],
    )
    def test_set_fan_mode_p(self, mode: int, error_str: str) -> None:
        """Positive unit test for GenericX9Platform.set_fan_mode() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_mode() with valid modes (STANDARD, FULL, OPTIMAL, HEAVY_IO)
        - ASSERT: if the mock exec was called with different parameters than expected
        - ASSERT: if the mock exec was called more than once
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        platform.set_fan_mode(mode)
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])
        assert mock_exec.call_count == 1, error_str

    @pytest.mark.parametrize(
        "mode, error_str",
        [
            # Invalid mode: PUE not supported on X9
            (FanMode.PUE, "GenericX9Platform.set_fan_mode() n1"),
            # Invalid mode: negative value
            (-1, "GenericX9Platform.set_fan_mode() n2"),
            # Invalid mode: value over valid range
            (100, "GenericX9Platform.set_fan_mode() n3"),
        ],
    )
    def test_set_fan_mode_n(self, mode: int, error_str: str) -> None:
        """Negative unit test for GenericX9Platform.set_fan_mode() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_mode() with invalid modes (PUE not supported on X9)
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_mode(mode)
        assert cm.type is ValueError, error_str

    @pytest.mark.parametrize(
        "zone, level, expected_normalised, error_str",
        [
            # Zone 0, level 100 (max) -> normalised 255
            (0, 100, 255, "GenericX9Platform.set_fan_level() p1"),
            # Zone 1, level 50 -> normalised 127
            (1, 50, 127, "GenericX9Platform.set_fan_level() p2"),
            # Zone 2, level 0 (min) -> normalised 0
            (2, 0, 0, "GenericX9Platform.set_fan_level() p3"),
            # Zone 3, level 75 -> normalised 191
            (3, 75, 191, "GenericX9Platform.set_fan_level() p4"),
        ],
    )
    def test_set_fan_level_p(self, zone: int, level: int, expected_normalised: int, error_str: str) -> None:
        """Positive unit test for GenericX9Platform.set_fan_level() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_level() with valid zones and levels
        - ASSERT: if the mock exec was called more than once
        - ASSERT: if the mock exec call has different parameters than expected (normalised level 0-255)
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        platform.set_fan_level(zone, level)
        assert mock_exec.call_count == 1, error_str
        reg = 0x10 + zone
        mock_exec.assert_called_with(
            ["raw", "0x30", "0x91", "0x5a", "0x03", f"0x{reg:02x}", f"0x{expected_normalised:02x}"]
        )

    @pytest.mark.parametrize(
        "zone, level, error_str",
        [
            # Invalid zone: negative
            (-1, 50, "GenericX9Platform.set_fan_level() n1"),
            # Invalid zone: over 3
            (4, 50, "GenericX9Platform.set_fan_level() n2"),
            # Invalid level: negative
            (0, -1, "GenericX9Platform.set_fan_level() n3"),
            # Invalid level: over 100
            (0, 101, "GenericX9Platform.set_fan_level() n4"),
        ],
    )
    def test_set_fan_level_n(self, zone: int, level: int, error_str: str) -> None:
        """Negative unit test for GenericX9Platform.set_fan_level() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_level() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_level(zone, level)
        assert cm.type is ValueError, error_str

    @pytest.mark.parametrize(
        "zones, level, expected_normalised, error_str",
        [
            # Two zones, level 100 -> normalised 255
            ([0, 1], 100, 255, "GenericX9Platform.set_multiple_fan_levels() p1"),
            # Four zones, level 50 -> normalised 127
            ([0, 1, 2, 3], 50, 127, "GenericX9Platform.set_multiple_fan_levels() p2"),
            # Single zone, level 0 -> normalised 0
            ([2], 0, 0, "GenericX9Platform.set_multiple_fan_levels() p3"),
        ],
    )
    def test_set_multiple_fan_levels_p(self, zones: List[int], level: int, expected_normalised: int,
                                       error_str: str) -> None:
        """Positive unit test for GenericX9Platform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_multiple_fan_levels() with valid zones and level
        - ASSERT: if the mock exec call count is different from expected (N zones)
        - ASSERT: if the mock exec zone-setting calls have different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        platform.set_multiple_fan_levels(zones, level)
        assert mock_exec.call_count == len(zones), error_str
        level_hex = f"0x{expected_normalised:02x}"
        zone_calls = [call(["raw", "0x30", "0x91", "0x5a", "0x03", f"0x{0x10 + z:02x}", level_hex]) for z in zones]
        mock_exec.assert_has_calls(zone_calls)

    @pytest.mark.parametrize(
        "zones, level, error_str",
        [
            # Invalid zone: negative in list
            ([-1, 0], 50, "GenericX9Platform.set_multiple_fan_levels() n1"),
            # Invalid zone: over 3 in list
            ([0, 4], 50, "GenericX9Platform.set_multiple_fan_levels() n2"),
            # Invalid level: negative
            ([0], -1, "GenericX9Platform.set_multiple_fan_levels() n3"),
            # Invalid level: over 100
            ([0], 101, "GenericX9Platform.set_multiple_fan_levels() n4"),
        ],
    )
    def test_set_multiple_fan_levels_n(self, zones: List[int], level: int, error_str: str) -> None:
        """Negative unit test for GenericX9Platform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_multiple_fan_levels() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(PlatformName.GENERIC_X9, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error_str


# End.
