#!/usr/bin/env python3
#
#   test_generic.py (C) 2025-2026, Peter Sulyok
#   Unit tests for smfc.generic module (GenericPlatform).
#
import subprocess
from typing import List
import pytest
from mock import MagicMock, call
from smfc.platform import FanMode, PlatformName
from smfc.generic import GenericPlatform


class TestGenericPlatform:
    """Unit test class for GenericPlatform platform."""

    @pytest.mark.parametrize(
        "mode, error_str",
        [
            # STANDARD mode
            (0, "GenericPlatform.get_fan_mode() p1"),
            # FULL mode
            (1, "GenericPlatform.get_fan_mode() p2"),
            # OPTIMAL mode
            (2, "GenericPlatform.get_fan_mode() p3"),
            # HEAVY_IO mode
            (4, "GenericPlatform.get_fan_mode() p4"),
        ],
    )
    def test_get_fan_mode_p(self, mode: int, error_str: str) -> None:
        """Positive unit test for GenericPlatform.get_fan_mode() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call get_fan_mode()
        - ASSERT: if the returned fan mode is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {mode:02}")
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        assert platform.get_fan_mode() == mode, error_str
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x00"])

    @pytest.mark.parametrize(
        "zone, hex_output, expected_level, error_str",
        [
            # Zone 0, level 0x32
            (0, " 32", 0x32, "GenericPlatform.get_fan_level() p1"),
            # Zone 1, level 0x64
            (1, " 64", 0x64, "GenericPlatform.get_fan_level() p2"),
            # Zone 50, level 0xFF
            (50, " ff", 0xFF, "GenericPlatform.get_fan_level() p3"),
            # Zone 100, level 0x00
            (100, " 00", 0x00, "GenericPlatform.get_fan_level() p4"),
        ],
    )
    def test_get_fan_level_p(self, zone: int, hex_output: str, expected_level: int, error_str: str) -> None:
        """Positive unit test for GenericPlatform.get_fan_level() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call get_fan_level() with valid zones (0-100)
        - ASSERT: if the returned fan level is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=hex_output)
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        assert platform.get_fan_level(zone) == expected_level, error_str
        mock_exec.assert_called_with(["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:x}"])

    @pytest.mark.parametrize(
        "zone, error_str",
        [
            # Zone negative
            (-1, "GenericPlatform.get_fan_level() n1"),
            # Zone over 100
            (101, "GenericPlatform.get_fan_level() n2"),
        ],
    )
    def test_get_fan_level_n(self, zone: int, error_str: str) -> None:
        """Negative unit test for GenericPlatform.get_fan_level() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call get_fan_level() with invalid zones (outside 0-100)
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.get_fan_level(zone)
        assert cm.type is ValueError, error_str

    def test_set_fan_manual_mode(self) -> None:
        """Positive unit test for GenericPlatform.set_fan_manual_mode() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_manual_mode()
        - ASSERT: if the mock exec was called (should be a no-op)
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        platform.set_fan_manual_mode()
        mock_exec.assert_not_called()

    @pytest.mark.parametrize(
        "mode, error_str",
        [
            # STANDARD mode
            (FanMode.STANDARD, "GenericPlatform.set_fan_mode() p1"),
            # FULL mode
            (FanMode.FULL, "GenericPlatform.set_fan_mode() p2"),
            # OPTIMAL mode
            (FanMode.OPTIMAL, "GenericPlatform.set_fan_mode() p3"),
            # PUE mode
            (FanMode.PUE, "GenericPlatform.set_fan_mode() p4"),
            # HEAVY_IO mode
            (FanMode.HEAVY_IO, "GenericPlatform.set_fan_mode() p5"),
        ],
    )
    def test_set_fan_mode_p(self, mode: int, error_str: str) -> None:
        """Positive unit test for GenericPlatform.set_fan_mode() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_mode() with valid modes
        - ASSERT: if the mock exec was called with different parameters than expected
        - ASSERT: if the mock exec was called more than once
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        platform.set_fan_mode(mode)
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])
        assert mock_exec.call_count == 1, error_str

    @pytest.mark.parametrize(
        "mode, error_str",
        [
            # Invalid mode: negative value
            (-1, "GenericPlatform.set_fan_mode() n1"),
            # Invalid mode: value over valid range
            (100, "GenericPlatform.set_fan_mode() n2"),
        ],
    )
    def test_set_fan_mode_n(self, mode: int, error_str: str) -> None:
        """Negative unit test for GenericPlatform.set_fan_mode() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_mode() with invalid modes
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_mode(mode)
        assert cm.type is ValueError, error_str

    @pytest.mark.parametrize(
        "zone, level, error_str",
        [
            # Zone 0, level 50
            (0, 50, "GenericPlatform.set_fan_level() p1"),
            # Zone 1, level 100 (max)
            (1, 100, "GenericPlatform.set_fan_level() p2"),
            # Zone 100 (max), level 0 (min)
            (100, 0, "GenericPlatform.set_fan_level() p3"),
        ],
    )
    def test_set_fan_level_p(self, zone: int, level: int, error_str: str) -> None:
        """Positive unit test for GenericPlatform.set_fan_level() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_level() with valid zones and levels
        - ASSERT: if the mock exec was called with different parameters than expected
        - ASSERT: if the mock exec was called more than once
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        platform.set_fan_level(zone, level)
        mock_exec.assert_called_with(
            ["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{level:02x}"]
        )
        assert mock_exec.call_count == 1, error_str

    @pytest.mark.parametrize(
        "zone, level, error_str",
        [
            # Invalid zone: negative
            (-1, 50, "GenericPlatform.set_fan_level() n1"),
            # Invalid zone: over 100
            (101, 50, "GenericPlatform.set_fan_level() n2"),
            # Invalid level: negative
            (0, -1, "GenericPlatform.set_fan_level() n3"),
            # Invalid level: over 100
            (0, 101, "GenericPlatform.set_fan_level() n4"),
        ],
    )
    def test_set_fan_level_n(self, zone: int, level: int, error_str: str) -> None:
        """Negative unit test for GenericPlatform.set_fan_level() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_level() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_level(zone, level)
        assert cm.type is ValueError, error_str

    @pytest.mark.parametrize(
        "zones, level, error_str",
        [
            # Two zones, level 100
            ([0, 1], 100, "GenericPlatform.set_multiple_fan_levels() p1"),
            # Four zones, level 50
            ([0, 1, 2, 3], 50, "GenericPlatform.set_multiple_fan_levels() p2"),
            # Single zone, level 0
            ([0], 0, "GenericPlatform.set_multiple_fan_levels() p3"),
        ],
    )
    def test_set_multiple_fan_levels_p(self, zones: List[int], level: int, error_str: str) -> None:
        """Positive unit test for GenericPlatform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_multiple_fan_levels() with valid zones and level
        - ASSERT: if the mock exec call count is different from expected (N zones)
        - ASSERT: if the mock exec zone-setting calls have different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        platform.set_multiple_fan_levels(zones, level)
        assert mock_exec.call_count == len(zones), error_str
        level_hex = f"0x{level:02x}"
        zone_calls = [call(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{z:02x}", level_hex]) for z in zones]
        mock_exec.assert_has_calls(zone_calls)

    @pytest.mark.parametrize(
        "zones, level, error_str",
        [
            # Invalid zone: negative in list
            ([-1, 0], 50, "GenericPlatform.set_multiple_fan_levels() n1"),
            # Invalid zone: over 100 in list
            ([0, 101], 50, "GenericPlatform.set_multiple_fan_levels() n2"),
            # Invalid level: negative
            ([0], -1, "GenericPlatform.set_multiple_fan_levels() n3"),
            # Invalid level: over 100
            ([0], 101, "GenericPlatform.set_multiple_fan_levels() n4"),
        ],
    )
    def test_set_multiple_fan_levels_n(self, zones: List[int], level: int, error_str: str) -> None:
        """Negative unit test for GenericPlatform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_multiple_fan_levels() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(PlatformName.GENERIC, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error_str


# End.
