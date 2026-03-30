#!/usr/bin/env python3
#
#   test_12_generic.py (C) 2025-2026, Peter Sulyok
#   Unit tests for smfc.generic module (GenericPlatform).
#
import subprocess
from typing import List
import pytest
from mock import MagicMock, call
from smfc.platform import FanMode, Platform
from smfc.generic import GenericPlatform


class TestGenericPlatform:
    """Unit test class for GenericPlatform platform."""

    @pytest.mark.parametrize(
        "mode, error",
        [
            (0, "GenericPlatform.get_fan_mode() 1"),
            (1, "GenericPlatform.get_fan_mode() 2"),
            (2, "GenericPlatform.get_fan_mode() 3"),
            (4, "GenericPlatform.get_fan_mode() 4"),
        ],
    )
    def test_get_fan_mode_p(self, mode: int, error: str) -> None:
        """Positive unit test for GenericPlatform.get_fan_mode() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call get_fan_mode()
        - ASSERT: if the returned fan mode is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {mode:02}")
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        assert platform.get_fan_mode() == mode, error
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x00"])

    @pytest.mark.parametrize(
        "zone, hex_output, expected_level, error",
        [
            (0, " 32", 0x32, "GenericPlatform.get_fan_level() 1"),
            (1, " 64", 0x64, "GenericPlatform.get_fan_level() 2"),
            (50, " ff", 0xFF, "GenericPlatform.get_fan_level() 3"),
            (100, " 00", 0x00, "GenericPlatform.get_fan_level() 4"),
        ],
    )
    def test_get_fan_level_p(self, zone: int, hex_output: str, expected_level: int, error: str) -> None:
        """Positive unit test for GenericPlatform.get_fan_level() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call get_fan_level() with valid zones (0-100)
        - ASSERT: if the returned fan level is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=hex_output)
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        assert platform.get_fan_level(zone) == expected_level, error
        mock_exec.assert_called_with(["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:x}"])

    @pytest.mark.parametrize(
        "zone, error",
        [
            (-1, "GenericPlatform.get_fan_level() 5"),
            (101, "GenericPlatform.get_fan_level() 6"),
        ],
    )
    def test_get_fan_level_n(self, zone: int, error: str) -> None:
        """Negative unit test for GenericPlatform.get_fan_level() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call get_fan_level() with invalid zones (outside 0-100)
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.get_fan_level(zone)
        assert cm.type is ValueError, error

    def test_set_fan_manual_mode(self) -> None:
        """Positive unit test for GenericPlatform.set_fan_manual_mode() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_manual_mode()
        - ASSERT: if the mock exec was called (should be a no-op)
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        platform.set_fan_manual_mode()
        mock_exec.assert_not_called()

    @pytest.mark.parametrize(
        "mode, error",
        [
            (FanMode.STANDARD, "GenericPlatform.set_fan_mode() 1"),
            (FanMode.FULL, "GenericPlatform.set_fan_mode() 2"),
            (FanMode.OPTIMAL, "GenericPlatform.set_fan_mode() 3"),
            (FanMode.PUE, "GenericPlatform.set_fan_mode() 4"),
            (FanMode.HEAVY_IO, "GenericPlatform.set_fan_mode() 5"),
        ],
    )
    def test_set_fan_mode_p(self, mode: int, error: str) -> None:
        """Positive unit test for GenericPlatform.set_fan_mode() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_mode() with valid modes
        - ASSERT: if the mock exec was called with different parameters than expected
        - ASSERT: if the mock exec was called more than once
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        platform.set_fan_mode(mode)
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])
        assert mock_exec.call_count == 1, error

    @pytest.mark.parametrize(
        "mode, error",
        [
            (-1, "GenericPlatform.set_fan_mode() 6"),
            (100, "GenericPlatform.set_fan_mode() 7"),
        ],
    )
    def test_set_fan_mode_n(self, mode: int, error: str) -> None:
        """Negative unit test for GenericPlatform.set_fan_mode() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_mode() with invalid modes
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_mode(mode)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zone, level, error",
        [
            (0, 50, "GenericPlatform.set_fan_level() 1"),
            (1, 100, "GenericPlatform.set_fan_level() 2"),
            (100, 0, "GenericPlatform.set_fan_level() 3"),
        ],
    )
    def test_set_fan_level_p(self, zone: int, level: int, error: str) -> None:
        """Positive unit test for GenericPlatform.set_fan_level() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_level() with valid zones and levels
        - ASSERT: if the mock exec was called with different parameters than expected
        - ASSERT: if the mock exec was called more than once
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        platform.set_fan_level(zone, level)
        mock_exec.assert_called_with(
            ["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{level:02x}"]
        )
        assert mock_exec.call_count == 1, error

    @pytest.mark.parametrize(
        "zone, level, error",
        [
            (-1, 50, "GenericPlatform.set_fan_level() 4"),
            (101, 50, "GenericPlatform.set_fan_level() 5"),
            (0, -1, "GenericPlatform.set_fan_level() 6"),
            (0, 101, "GenericPlatform.set_fan_level() 7"),
        ],
    )
    def test_set_fan_level_n(self, zone: int, level: int, error: str) -> None:
        """Negative unit test for GenericPlatform.set_fan_level() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_fan_level() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_level(zone, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zones, level, error",
        [
            ([0, 1], 100, "GenericPlatform.set_multiple_fan_levels() 1"),
            ([0, 1, 2, 3], 50, "GenericPlatform.set_multiple_fan_levels() 2"),
            ([0], 0, "GenericPlatform.set_multiple_fan_levels() 3"),
        ],
    )
    def test_set_multiple_fan_levels_p(self, zones: List[int], level: int, error: str) -> None:
        """Positive unit test for GenericPlatform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_multiple_fan_levels() with valid zones and level
        - ASSERT: if the mock exec call count is different from expected (N zones)
        - ASSERT: if the mock exec zone-setting calls have different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        platform.set_multiple_fan_levels(zones, level)
        assert mock_exec.call_count == len(zones), error
        level_hex = f"0x{level:02x}"
        zone_calls = [call(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{z:02x}", level_hex]) for z in zones]
        mock_exec.assert_has_calls(zone_calls)

    @pytest.mark.parametrize(
        "zones, level, error",
        [
            ([-1, 0], 50, "GenericPlatform.set_multiple_fan_levels() 4"),
            ([0, 101], 50, "GenericPlatform.set_multiple_fan_levels() 5"),
            ([0], -1, "GenericPlatform.set_multiple_fan_levels() 6"),
            ([0], 101, "GenericPlatform.set_multiple_fan_levels() 7"),
        ],
    )
    def test_set_multiple_fan_levels_n(self, zones: List[int], level: int, error: str) -> None:
        """Negative unit test for GenericPlatform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericPlatform instance with a mock exec function
        - call set_multiple_fan_levels() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericPlatform(Platform.PLATFORM_GENERIC, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error


# End.
