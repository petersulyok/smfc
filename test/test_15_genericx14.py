#!/usr/bin/env python3
#
#   test_15_genericx14.py (C) 2026, Peter Sulyok
#   Unit tests for smfc.genericx14 module (GenericX14Platform).
#
import subprocess
from typing import List
import pytest
from mock import MagicMock, call
from smfc.platform import FanMode, PlatformName
from smfc.genericx14 import GenericX14Platform


class TestGenericX14Platform:
    """Unit test class for GenericX14Platform platform."""

    @pytest.mark.parametrize(
        "mode, error",
        [
            (0, "GenericX14Platform.get_fan_mode() 1"),
            (1, "GenericX14Platform.get_fan_mode() 2"),
            (2, "GenericX14Platform.get_fan_mode() 3"),
            (4, "GenericX14Platform.get_fan_mode() 4"),
            (0x0B, "GenericX14Platform.get_fan_mode() 5"),
        ],
    )
    def test_get_fan_mode_p(self, mode: int, error: str) -> None:
        """Positive unit test for GenericX14Platform.get_fan_mode() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call get_fan_mode()
        - ASSERT: if the returned fan mode is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {mode:02}")
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        assert platform.get_fan_mode() == mode, error
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x00"])

    @pytest.mark.parametrize(
        "zone, hex_output, expected_level, error",
        [
            (0, " 64", 0x64, "GenericX14Platform.get_fan_level() 1"),
            (1, " 32", 0x32, "GenericX14Platform.get_fan_level() 2"),
            (2, " 00", 0x00, "GenericX14Platform.get_fan_level() 3"),
            (3, " 50", 0x50, "GenericX14Platform.get_fan_level() 4"),
            (4, " 4b", 0x4B, "GenericX14Platform.get_fan_level() 5"),
            (5, " 0a", 0x0A, "GenericX14Platform.get_fan_level() 6"),
        ],
    )
    def test_get_fan_level_p(self, zone: int, hex_output: str, expected_level: int, error: str) -> None:
        """Positive unit test for GenericX14Platform.get_fan_level() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call get_fan_level() with valid zones (0-5)
        - ASSERT: if the returned fan level is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=hex_output)
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        assert platform.get_fan_level(zone) == expected_level, error
        mock_exec.assert_called_with(["raw", "0x30", "0x70", "0x88", f"0x{zone:02x}"])

    @pytest.mark.parametrize(
        "zone, error",
        [
            (-1, "GenericX14Platform.get_fan_level() 7"),
            (6, "GenericX14Platform.get_fan_level() 8"),
        ],
    )
    def test_get_fan_level_n(self, zone: int, error: str) -> None:
        """Negative unit test for GenericX14Platform.get_fan_level() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call get_fan_level() with invalid zones (outside 0-5)
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.get_fan_level(zone)
        assert cm.type is ValueError, error

    def test_start(self) -> None:
        """Positive unit test for GenericX14Platform.start() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call start()
        - ASSERT: if the mock exec was not called 6 times (once per zone 0-5)
        - ASSERT: if the mock exec was called with correct manual mode enable commands
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        platform.start()
        assert mock_exec.call_count == 6
        expected_calls = [
            call(["raw", "0x2c", "0x04", "0xcf", "0xc2", "0x00", f"0x{zone:02x}", "0x01"])
            for zone in range(6)
        ]
        mock_exec.assert_has_calls(expected_calls)

    def test_end(self) -> None:
        """Positive unit test for GenericX14Platform.end() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call end()
        - ASSERT: if the mock exec was not called 6 times (once per zone 0-5)
        - ASSERT: if the mock exec was called with correct manual mode disable commands
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        platform.end()
        assert mock_exec.call_count == 6
        expected_calls = [
            call(["raw", "0x2c", "0x04", "0xcf", "0xc2", "0x00", f"0x{zone:02x}", "0x00"])
            for zone in range(6)
        ]
        mock_exec.assert_has_calls(expected_calls)

    @pytest.mark.parametrize(
        "mode, error",
        [
            (FanMode.STANDARD, "GenericX14Platform.set_fan_mode() 1"),
            (FanMode.FULL, "GenericX14Platform.set_fan_mode() 2"),
            (FanMode.OPTIMAL, "GenericX14Platform.set_fan_mode() 3"),
            (FanMode.PUE, "GenericX14Platform.set_fan_mode() 4"),
            (FanMode.HEAVY_IO, "GenericX14Platform.set_fan_mode() 5"),
            (0x0B, "GenericX14Platform.set_fan_mode() 6"),  # Silent mode
        ],
    )
    def test_set_fan_mode_p(self, mode: int, error: str) -> None:
        """Positive unit test for GenericX14Platform.set_fan_mode() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call set_fan_mode() with valid modes (all X14 modes including extended)
        - ASSERT: if the mock exec was called with different parameters than expected
        - ASSERT: if the mock exec was called more than once
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        platform.set_fan_mode(mode)
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])
        assert mock_exec.call_count == 1, error

    @pytest.mark.parametrize(
        "mode, error",
        [
            (-1, "GenericX14Platform.set_fan_mode() 7"),
            (0x0C, "GenericX14Platform.set_fan_mode() 8"),  # Beyond max
            (100, "GenericX14Platform.set_fan_mode() 9"),
        ],
    )
    def test_set_fan_mode_n(self, mode: int, error: str) -> None:
        """Negative unit test for GenericX14Platform.set_fan_mode() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call set_fan_mode() with invalid modes
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_mode(mode)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zone, level, error",
        [
            (0, 100, "GenericX14Platform.set_fan_level() 1"),
            (1, 50, "GenericX14Platform.set_fan_level() 2"),
            (2, 0, "GenericX14Platform.set_fan_level() 3"),
            (3, 75, "GenericX14Platform.set_fan_level() 4"),
            (4, 25, "GenericX14Platform.set_fan_level() 5"),
            (5, 80, "GenericX14Platform.set_fan_level() 6"),
        ],
    )
    def test_set_fan_level_p(self, zone: int, level: int, error: str) -> None:
        """Positive unit test for GenericX14Platform.set_fan_level() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call set_fan_level() with valid zones and levels
        - ASSERT: if the mock exec was called exactly once (level set only, no manual mode enable)
        - ASSERT: if the mock exec call has expected parameters (X14 uses percentage directly)
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        platform.set_fan_level(zone, level)
        assert mock_exec.call_count == 1, error
        mock_exec.assert_called_with(["raw", "0x30", "0x70", "0x88", f"0x{zone:02x}", f"0x{level:02x}"])

    @pytest.mark.parametrize(
        "zone, level, error",
        [
            (-1, 50, "GenericX14Platform.set_fan_level() 7"),
            (6, 50, "GenericX14Platform.set_fan_level() 8"),
            (0, -1, "GenericX14Platform.set_fan_level() 9"),
            (0, 101, "GenericX14Platform.set_fan_level() 10"),
        ],
    )
    def test_set_fan_level_n(self, zone: int, level: int, error: str) -> None:
        """Negative unit test for GenericX14Platform.set_fan_level() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call set_fan_level() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_level(zone, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zones, level, error",
        [
            ([0, 1], 100, "GenericX14Platform.set_multiple_fan_levels() 1"),
            ([0, 1, 2], 50, "GenericX14Platform.set_multiple_fan_levels() 2"),
            ([2], 0, "GenericX14Platform.set_multiple_fan_levels() 3"),
            ([0, 3, 5], 75, "GenericX14Platform.set_multiple_fan_levels() 4"),
        ],
    )
    def test_set_multiple_fan_levels_p(self, zones: List[int], level: int, error: str) -> None:
        """Positive unit test for GenericX14Platform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call set_multiple_fan_levels() with valid zones and level
        - ASSERT: if the mock exec call count is different from expected (N zones, no manual mode enables)
        - ASSERT: if the mock exec calls have expected parameters
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        platform.set_multiple_fan_levels(zones, level)
        assert mock_exec.call_count == len(zones), error
        expected_calls = [
            call(["raw", "0x30", "0x70", "0x88", f"0x{zone:02x}", f"0x{level:02x}"])
            for zone in zones
        ]
        mock_exec.assert_has_calls(expected_calls)

    @pytest.mark.parametrize(
        "zones, level, error",
        [
            ([-1, 0], 50, "GenericX14Platform.set_multiple_fan_levels() 5"),
            ([0, 6], 50, "GenericX14Platform.set_multiple_fan_levels() 6"),
            ([0], -1, "GenericX14Platform.set_multiple_fan_levels() 7"),
            ([0], 101, "GenericX14Platform.set_multiple_fan_levels() 8"),
        ],
    )
    def test_set_multiple_fan_levels_n(self, zones: List[int], level: int, error: str) -> None:
        """Negative unit test for GenericX14Platform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericX14Platform instance with a mock exec function
        - call set_multiple_fan_levels() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX14Platform(PlatformName.GENERIC_X14, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error


# End.