#!/usr/bin/env python3
#
#   test_11_platform.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   Unit tests for smfc.platform module (GenericPlatform, GenericX9Platform, X10QBi, create_platform).
#
import subprocess
from typing import List
import pytest
from mock import MagicMock, call
from smfc.platform import FanMode, GenericPlatform, GenericX9Platform, Platform, X10QBi, create_platform


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


class TestGenericX9Platform:
    """Unit test class for GenericX9Platform platform."""

    @pytest.mark.parametrize(
        "mode, error",
        [
            (0, "GenericX9Platform.get_fan_mode() 1"),
            (1, "GenericX9Platform.get_fan_mode() 2"),
            (2, "GenericX9Platform.get_fan_mode() 3"),
            (4, "GenericX9Platform.get_fan_mode() 4"),
        ],
    )
    def test_get_fan_mode_p(self, mode: int, error: str) -> None:
        """Positive unit test for GenericX9Platform.get_fan_mode() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call get_fan_mode()
        - ASSERT: if the returned fan mode is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {mode:02}")
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        assert platform.get_fan_mode() == mode, error
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x00"])

    @pytest.mark.parametrize(
        "zone, hex_output, expected_level, error",
        [
            (16, " 80", 0x80, "GenericX9Platform.get_fan_level() 1"),
            (17, " ff", 0xFF, "GenericX9Platform.get_fan_level() 2"),
            (18, " 00", 0x00, "GenericX9Platform.get_fan_level() 3"),
            (19, " 40", 0x40, "GenericX9Platform.get_fan_level() 4"),
        ],
    )
    def test_get_fan_level_p(self, zone: int, hex_output: str, expected_level: int, error: str) -> None:
        """Positive unit test for GenericX9Platform.get_fan_level() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call get_fan_level() with valid zones (16-19)
        - ASSERT: if the returned fan level is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=hex_output)
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        assert platform.get_fan_level(zone) == expected_level, error
        mock_exec.assert_called_with(["raw", "0x30", "0x90", "0x5a", "0x03", f"0x{zone:x}", "0x01"])

    @pytest.mark.parametrize(
        "zone, error",
        [
            (0, "GenericX9Platform.get_fan_level() 5"),
            (1, "GenericX9Platform.get_fan_level() 6"),
            (15, "GenericX9Platform.get_fan_level() 7"),
            (20, "GenericX9Platform.get_fan_level() 8"),
        ],
    )
    def test_get_fan_level_n(self, zone: int, error: str) -> None:
        """Negative unit test for GenericX9Platform.get_fan_level() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call get_fan_level() with invalid zones (outside 16-19)
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.get_fan_level(zone)
        assert cm.type is ValueError, error

    def test_set_fan_manual_mode(self) -> None:
        """Positive unit test for GenericX9Platform.set_fan_manual_mode() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_manual_mode()
        - ASSERT: if the mock exec was called (should be a no-op)
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        platform.set_fan_manual_mode()
        mock_exec.assert_not_called()

    @pytest.mark.parametrize(
        "mode, error",
        [
            (FanMode.STANDARD, "GenericX9Platform.set_fan_mode() 1"),
            (FanMode.FULL, "GenericX9Platform.set_fan_mode() 2"),
            (FanMode.OPTIMAL, "GenericX9Platform.set_fan_mode() 3"),
            (FanMode.HEAVY_IO, "GenericX9Platform.set_fan_mode() 4"),
        ],
    )
    def test_set_fan_mode_p(self, mode: int, error: str) -> None:
        """Positive unit test for GenericX9Platform.set_fan_mode() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_mode() with valid modes (STANDARD, FULL, OPTIMAL, HEAVY_IO)
        - ASSERT: if the mock exec was called with different parameters than expected
        - ASSERT: if the mock exec was called more than once
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        platform.set_fan_mode(mode)
        mock_exec.assert_called_with(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])
        assert mock_exec.call_count == 1, error

    @pytest.mark.parametrize(
        "mode, error",
        [
            (FanMode.PUE, "GenericX9Platform.set_fan_mode() 5"),
            (-1, "GenericX9Platform.set_fan_mode() 6"),
            (100, "GenericX9Platform.set_fan_mode() 7"),
        ],
    )
    def test_set_fan_mode_n(self, mode: int, error: str) -> None:
        """Negative unit test for GenericX9Platform.set_fan_mode() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_mode() with invalid modes (PUE not supported on X9)
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_mode(mode)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zone, level, expected_normalised, error",
        [
            (16, 100, 255, "GenericX9Platform.set_fan_level() 1"),
            (17, 50, 127,  "GenericX9Platform.set_fan_level() 2"),
            (18, 0, 0,     "GenericX9Platform.set_fan_level() 3"),
            (19, 75, 191,  "GenericX9Platform.set_fan_level() 4"),
        ],
    )
    def test_set_fan_level_p(self, zone: int, level: int, expected_normalised: int, error: str) -> None:
        """Positive unit test for GenericX9Platform.set_fan_level() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_level() with valid zones and levels
        - ASSERT: if the mock exec was called more than once
        - ASSERT: if the mock exec call has different parameters than expected (normalised level 0-255)
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        platform.set_fan_level(zone, level)
        assert mock_exec.call_count == 1, error
        mock_exec.assert_called_with(
            ["raw", "0x30", "0x91", "0x5a", "0x03", f"0x{zone:02x}", f"0x{expected_normalised:02x}"]
        )

    @pytest.mark.parametrize(
        "zone, level, error",
        [
            (0, 50, "GenericX9Platform.set_fan_level() 5"),
            (15, 50, "GenericX9Platform.set_fan_level() 6"),
            (20, 50, "GenericX9Platform.set_fan_level() 7"),
            (16, -1, "GenericX9Platform.set_fan_level() 8"),
            (16, 101, "GenericX9Platform.set_fan_level() 9"),
        ],
    )
    def test_set_fan_level_n(self, zone: int, level: int, error: str) -> None:
        """Negative unit test for GenericX9Platform.set_fan_level() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_fan_level() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_fan_level(zone, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zones, level, expected_normalised, error",
        [
            ([16, 17], 100, 255, "GenericX9Platform.set_multiple_fan_levels() 1"),
            ([16, 17, 18, 19], 50, 127, "GenericX9Platform.set_multiple_fan_levels() 2"),
            ([18], 0, 0, "GenericX9Platform.set_multiple_fan_levels() 3"),
        ],
    )
    def test_set_multiple_fan_levels_p(self, zones: List[int], level: int, expected_normalised: int,
                                       error: str) -> None:
        """Positive unit test for GenericX9Platform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_multiple_fan_levels() with valid zones and level
        - ASSERT: if the mock exec call count is different from expected (N zones)
        - ASSERT: if the mock exec zone-setting calls have different parameters than expected
        """
        mock_exec = MagicMock()
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        platform.set_multiple_fan_levels(zones, level)
        assert mock_exec.call_count == len(zones), error
        level_hex = f"0x{expected_normalised:02x}"
        zone_calls = [call(["raw", "0x30", "0x91", "0x5a", "0x03", f"0x{z:02x}", level_hex]) for z in zones]
        mock_exec.assert_has_calls(zone_calls)

    @pytest.mark.parametrize(
        "zones, level, error",
        [
            ([0, 16], 50, "GenericX9Platform.set_multiple_fan_levels() 4"),
            ([16, 20], 50, "GenericX9Platform.set_multiple_fan_levels() 5"),
            ([16], -1, "GenericX9Platform.set_multiple_fan_levels() 6"),
            ([16], 101, "GenericX9Platform.set_multiple_fan_levels() 7"),
        ],
    )
    def test_set_multiple_fan_levels_n(self, zones: List[int], level: int, error: str) -> None:
        """Negative unit test for GenericX9Platform.set_multiple_fan_levels() method. It contains the following steps:
        - create a GenericX9Platform instance with a mock exec function
        - call set_multiple_fan_levels() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = GenericX9Platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error


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
        """Positive unit test for X10QBi.get_fan_mode() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call get_fan_mode()
        - ASSERT: if the returned fan mode is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
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
        """Positive unit test for X10QBi.get_fan_level() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call get_fan_level() with valid zones (16-19)
        - ASSERT: if the returned fan level is different from the expected value
        - ASSERT: if the mock exec was called with different parameters than expected
        """
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
        """Negative unit test for X10QBi.get_fan_level() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call get_fan_level() with invalid zones (outside 16-19)
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = X10QBi("X10QBi", mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.get_fan_level(zone)
        assert cm.type is ValueError, error

    def test_set_fan_manual_mode(self) -> None:
        """Positive unit test for X10QBi.set_fan_manual_mode() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call set_fan_manual_mode()
        - ASSERT: if the mock exec was not called 11 times (10 TMFR + 1 FOMC)
        - ASSERT: if the mock exec was called with different parameters than expected
        """
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
        """Positive unit test for X10QBi.set_fan_mode() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call set_fan_mode() with valid modes (STANDARD, FULL, HEAVY_IO)
        - ASSERT: if the mock exec was called with different parameters than expected
        - ASSERT: if the mock exec was called more than once
        """
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
        """Negative unit test for X10QBi.set_fan_mode() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call set_fan_mode() with invalid modes (OPTIMAL, PUE not supported)
        - ASSERT: if ValueError exception was not raised
        """
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
        """Positive unit test for X10QBi.set_fan_level() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call set_fan_level() with valid zones and levels
        - ASSERT: if the mock exec call count is different from expected (11 manual mode + 1 set level)
        - ASSERT: if the last mock exec call has different parameters than expected (normalised level 0-255)
        """
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
        """Negative unit test for X10QBi.set_fan_level() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call set_fan_level() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
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
        """Positive unit test for X10QBi.set_multiple_fan_levels() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call set_multiple_fan_levels() with valid zones and level
        - ASSERT: if the mock exec call count is different from expected (11 manual mode + N zones)
        - ASSERT: if the mock exec zone-setting calls have different parameters than expected
        """
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
        """Negative unit test for X10QBi.set_multiple_fan_levels() method. It contains the following steps:
        - create an X10QBi instance with a mock exec function
        - call set_multiple_fan_levels() with invalid zone or level parameters
        - ASSERT: if ValueError exception was not raised
        """
        mock_exec = MagicMock()
        platform = X10QBi("X10QBi", mock_exec)
        with pytest.raises(ValueError) as cm:
            platform.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error


class TestCreatePlatform:
    """Unit test class for create_platform() factory function."""

    def test_create_genericx9(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - call create_platform() with 'genericx9' platform name
        - ASSERT: if the returned platform is not a GenericX9Platform instance
        - ASSERT: if the platform name is different from expected
        """
        mock_exec = MagicMock()
        platform = create_platform(Platform.PLATFORM_GENERIC_X9, mock_exec)
        assert isinstance(platform, GenericX9Platform)
        assert platform.name == Platform.PLATFORM_GENERIC_X9

    def test_create_x10qbi(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - call create_platform() with 'X10QBi' platform name
        - ASSERT: if the returned platform is not an X10QBi instance
        - ASSERT: if the platform name is different from expected
        """
        mock_exec = MagicMock()
        platform = create_platform("X10QBi", mock_exec)
        assert isinstance(platform, X10QBi)
        assert platform.name == "X10QBi"

    def test_create_generic_explicit(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - call create_platform() with 'generic' platform name
        - ASSERT: if the returned platform is not a GenericPlatform instance
        - ASSERT: if the platform name is 'generic'
        """
        mock_exec = MagicMock()
        platform = create_platform(Platform.PLATFORM_GENERIC, mock_exec)
        assert isinstance(platform, GenericPlatform)
        assert platform.name == Platform.PLATFORM_GENERIC

    def test_create_generic_fallback(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - call create_platform() with an unknown platform name (BMC product name)
        - ASSERT: if the returned platform is not a GenericPlatform instance
        - ASSERT: if the platform name is different from expected
        """
        mock_exec = MagicMock()
        platform = create_platform("X11SCH-LN4F", mock_exec)
        assert isinstance(platform, GenericPlatform)
        assert platform.name == "X11SCH-LN4F"


# End.
