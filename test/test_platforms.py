#!/usr/bin/env python3
#
#   test_platforms.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   Unified, matrix-driven unit tests for all smfc Platform implementations
#   (GenericPlatform, GenericX9Platform, GenericX14Platform, X10QBi).
#
#   Every platform exposes the same Platform contract, so the test bodies are
#   shared and each platform contributes a PlatformSpec describing its
#   platform-specific command bytes, zone range, level normalisation and the
#   start()/end() behaviour. Adding a new platform is a single PLATFORMS entry.
#
import subprocess
from dataclasses import dataclass
from typing import Callable, List
import pytest
from mock import MagicMock, call
from smfc.platform import FanMode, Platform
from smfc.config import PlatformName
from smfc.generic import GenericPlatform
from smfc.genericx9 import GenericX9Platform
from smfc.genericx14 import GenericX14Platform
from smfc.x10qbi import X10QBi

# ipmitool argument lists shared by every platform.
GET_FAN_MODE_CMD = ["raw", "0x30", "0x45", "0x00"]


def _set_fan_mode_cmd(mode: int) -> List[str]:
    """Build the (platform-independent) ipmitool args for set_fan_mode()."""
    return ["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"]


# --- Per-platform get_fan_level()/set_fan_level() command builders ------------
# get builders take a zone, set builders take a zone and the on-the-wire level
# (already normalised to the platform's scale).

def _generic_get_cmd(zone: int) -> List[str]:
    return ["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:x}"]


def _generic_set_cmd(zone: int, wire: int) -> List[str]:
    return ["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{wire:02x}"]


def _x9_get_cmd(zone: int) -> List[str]:
    return ["raw", "0x30", "0x90", "0x5a", "0x03", f"0x{0x10 + zone:x}", "0x01"]


def _x9_set_cmd(zone: int, wire: int) -> List[str]:
    return ["raw", "0x30", "0x91", "0x5a", "0x03", f"0x{0x10 + zone:02x}", f"0x{wire:02x}"]


def _x14_get_cmd(zone: int) -> List[str]:
    return ["raw", "0x30", "0x70", "0x88", f"0x{zone:02x}"]


def _x14_set_cmd(zone: int, wire: int) -> List[str]:
    return ["raw", "0x30", "0x70", "0x88", f"0x{zone:02x}", f"0x{wire:02x}"]


def _x10qbi_get_cmd(zone: int) -> List[str]:
    return ["raw", "0x30", "0x90", "0x5c", "0x03", f"0x{0x10 + zone:x}", "0x01"]


def _x10qbi_set_cmd(zone: int, wire: int) -> List[str]:
    return ["raw", "0x30", "0x91", "0x5c", "0x03", f"0x{0x10 + zone:02x}", f"0x{wire:02x}"]


# start()/end() expected ipmitool calls for the platforms that are not no-ops.
_X14_START_CALLS = tuple(
    call(["raw", "0x2c", "0x04", "0xcf", "0xc2", "0x00", f"0x{zone:02x}", "0x01"]) for zone in range(6)
)
_X14_END_CALLS = tuple(
    call(["raw", "0x2c", "0x04", "0xcf", "0xc2", "0x00", f"0x{zone:02x}", "0x00"]) for zone in range(6)
)
_X10QBI_START_CALLS = (
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
)


@dataclass(frozen=True)
class PlatformSpec:
    """Describes one Platform implementation so the shared tests can drive it.

    Vectors that vary per case are tuples expanded into individual parametrized
    test cases by _cases(); single-value attributes apply to the platform as a
    whole.
    """

    label: str                                          # short id used in test case ids
    make: Callable[[Callable], Platform]                # build a platform around a mock exec callback
    get_mode_values: tuple                              # raw fan modes returned by the BMC
    get_level_cmd: Callable[[int], List[str]]           # zone -> expected get_fan_level() ipmitool args
    get_level_vectors: tuple                            # (zone, bmc_stdout, expected_level)
    bad_zones: tuple                                    # zones rejected by get/set_fan_level()
    start_calls: tuple                                  # expected start() calls (empty => no-op)
    end_calls: tuple                                    # expected end() calls (empty => no-op)
    set_mode_valid: tuple                               # accepted set_fan_mode() values
    set_mode_invalid: tuple                             # rejected set_fan_mode() values
    set_level_cmd: Callable[[int, int], List[str]]      # (zone, wire_level) -> expected set_fan_level() args
    set_level_extra_calls: int                          # extra exec calls before the level write (e.g. X10QBi start)
    set_level_vectors: tuple                            # (zone, level, wire_level)
    bad_levels: tuple                                   # (zone, level) rejected by set_fan_level()
    multi_extra_calls: int                              # extra exec calls before set_multiple_fan_levels() writes
    multi_vectors: tuple                                # (zones, level, wire_level)
    multi_bad: tuple                                    # (zones, level) rejected by set_multiple_fan_levels()


PLATFORMS: List[PlatformSpec] = [
    PlatformSpec(
        label="generic",
        make=lambda exec_fn: GenericPlatform(PlatformName.GENERIC, exec_fn),
        get_mode_values=(0, 1, 2, 4),
        get_level_cmd=_generic_get_cmd,
        get_level_vectors=((0, " 32", 0x32), (1, " 64", 0x64), (50, " ff", 0xFF), (100, " 00", 0x00)),
        bad_zones=(-1, 101),
        start_calls=(),
        end_calls=(),
        set_mode_valid=(FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO),
        set_mode_invalid=(-1, 100),
        set_level_cmd=_generic_set_cmd,
        set_level_extra_calls=0,
        set_level_vectors=((0, 50, 50), (1, 100, 100), (100, 0, 0)),
        bad_levels=((-1, 50), (101, 50), (0, -1), (0, 101)),
        multi_extra_calls=0,
        multi_vectors=(([0, 1], 100, 100), ([0, 1, 2, 3], 50, 50), ([0], 0, 0)),
        multi_bad=(([-1, 0], 50), ([0, 101], 50), ([0], -1), ([0], 101)),
    ),
    PlatformSpec(
        label="x9",
        make=lambda exec_fn: GenericX9Platform(PlatformName.GENERIC_X9, exec_fn),
        get_mode_values=(0, 1, 2, 4),
        get_level_cmd=_x9_get_cmd,
        get_level_vectors=((0, " 80", 0x80), (1, " ff", 0xFF), (2, " 00", 0x00), (3, " 40", 0x40)),
        bad_zones=(-1, 4),
        start_calls=(),
        end_calls=(),
        set_mode_valid=(FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.HEAVY_IO),
        set_mode_invalid=(FanMode.PUE, -1, 100),
        set_level_cmd=_x9_set_cmd,
        set_level_extra_calls=0,
        set_level_vectors=((0, 100, 255), (1, 50, 127), (2, 0, 0), (3, 75, 191)),
        bad_levels=((-1, 50), (4, 50), (0, -1), (0, 101)),
        multi_extra_calls=0,
        multi_vectors=(([0, 1], 100, 255), ([0, 1, 2, 3], 50, 127), ([2], 0, 0)),
        multi_bad=(([-1, 0], 50), ([0, 4], 50), ([0], -1), ([0], 101)),
    ),
    PlatformSpec(
        label="x14",
        make=lambda exec_fn: GenericX14Platform(PlatformName.GENERIC_X14, exec_fn),
        get_mode_values=(0, 1, 2, 4, 0x0B),
        get_level_cmd=_x14_get_cmd,
        get_level_vectors=(
            (0, " 64", 0x64), (1, " 32", 0x32), (2, " 00", 0x00),
            (3, " 50", 0x50), (4, " 4b", 0x4B), (5, " 0a", 0x0A),
        ),
        bad_zones=(-1, 6),
        start_calls=_X14_START_CALLS,
        end_calls=_X14_END_CALLS,
        set_mode_valid=(FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO, 0x0B),
        set_mode_invalid=(-1, 0x0C, 100),
        set_level_cmd=_x14_set_cmd,
        set_level_extra_calls=0,
        set_level_vectors=((0, 100, 100), (1, 50, 50), (2, 0, 0), (3, 75, 75), (4, 25, 25), (5, 80, 80)),
        bad_levels=((-1, 50), (6, 50), (0, -1), (0, 101)),
        multi_extra_calls=0,
        multi_vectors=(([0, 1], 100, 100), ([0, 1, 2], 50, 50), ([2], 0, 0), ([0, 3, 5], 75, 75)),
        multi_bad=(([-1, 0], 50), ([0, 6], 50), ([0], -1), ([0], 101)),
    ),
    PlatformSpec(
        label="x10qbi",
        make=lambda exec_fn: X10QBi("X10QBi", exec_fn),
        get_mode_values=(0, 1, 4),
        get_level_cmd=_x10qbi_get_cmd,
        get_level_vectors=((0, " 80", 0x80), (1, " ff", 0xFF), (2, " 00", 0x00), (3, " 40", 0x40)),
        bad_zones=(-1, 4),
        start_calls=_X10QBI_START_CALLS,
        end_calls=(),
        set_mode_valid=(FanMode.STANDARD, FanMode.FULL, FanMode.HEAVY_IO),
        set_mode_invalid=(FanMode.OPTIMAL, FanMode.PUE, -1, 100),
        set_level_cmd=_x10qbi_set_cmd,
        set_level_extra_calls=11,
        set_level_vectors=((0, 100, 255), (1, 50, 127), (2, 0, 0), (3, 75, 191)),
        bad_levels=((-1, 50), (4, 50), (0, -1), (0, 101)),
        multi_extra_calls=11,
        multi_vectors=(([0, 1], 100, 255), ([0, 1, 2, 3], 50, 127), ([2], 0, 0)),
        multi_bad=(([-1, 0], 50), ([0, 4], 50), ([0], -1), ([0], 101)),
    ),
]

PLATFORM_IDS = [spec.label for spec in PLATFORMS]


def _cases(attr: str) -> list:
    """Expand each platform's vector list under `attr` into flat pytest params.

    Each vector becomes its own parametrized case (id: "<platform>-<n>") with the
    owning PlatformSpec prepended, so platform-specific test data stays granular.
    """
    cases = []
    for spec in PLATFORMS:
        for index, vector in enumerate(getattr(spec, attr), start=1):
            values = vector if isinstance(vector, tuple) else (vector,)
            cases.append(pytest.param(spec, *values, id=f"{spec.label}-{index}"))
    return cases


@pytest.fixture(name="mock_exec")
def fixture_mock_exec() -> MagicMock:
    """A mock ipmitool exec callback returning a successful CompletedProcess by default."""
    exec_mock = MagicMock()
    exec_mock.return_value = subprocess.CompletedProcess([], returncode=0)
    return exec_mock


class TestPlatforms:
    """Matrix-driven unit tests covering the full Platform contract for every platform."""

    @pytest.mark.parametrize("spec, mode", _cases("get_mode_values"))
    def test_get_fan_mode(self, spec: PlatformSpec, mode: int, mock_exec: MagicMock) -> None:
        """get_fan_mode() returns the BMC-reported mode and issues the read raw command."""
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {mode:02}")
        platform = spec.make(mock_exec)
        assert platform.get_fan_mode() == mode
        mock_exec.assert_called_with(GET_FAN_MODE_CMD)

    @pytest.mark.parametrize("spec, zone, hex_output, expected_level", _cases("get_level_vectors"))
    def test_get_fan_level(self, spec: PlatformSpec, zone: int, hex_output: str, expected_level: int,
                           mock_exec: MagicMock) -> None:
        """get_fan_level() decodes the BMC duty cycle and issues the platform's read command."""
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=hex_output)
        platform = spec.make(mock_exec)
        assert platform.get_fan_level(zone) == expected_level
        mock_exec.assert_called_with(spec.get_level_cmd(zone))

    @pytest.mark.parametrize("spec, zone", _cases("bad_zones"))
    def test_get_fan_level_invalid_zone(self, spec: PlatformSpec, zone: int, mock_exec: MagicMock) -> None:
        """get_fan_level() rejects out-of-range zones with ValueError."""
        platform = spec.make(mock_exec)
        with pytest.raises(ValueError):
            platform.get_fan_level(zone)

    @pytest.mark.parametrize("spec", PLATFORMS, ids=PLATFORM_IDS)
    def test_start(self, spec: PlatformSpec, mock_exec: MagicMock) -> None:
        """start() either is a no-op or issues the platform's manual-mode enable commands."""
        platform = spec.make(mock_exec)
        platform.start()
        if spec.start_calls:
            assert mock_exec.call_count == len(spec.start_calls)
            mock_exec.assert_has_calls(list(spec.start_calls))
        else:
            mock_exec.assert_not_called()

    @pytest.mark.parametrize("spec", PLATFORMS, ids=PLATFORM_IDS)
    def test_end(self, spec: PlatformSpec, mock_exec: MagicMock) -> None:
        """end() either is a no-op or issues the platform's manual-mode disable commands."""
        platform = spec.make(mock_exec)
        platform.end()
        if spec.end_calls:
            assert mock_exec.call_count == len(spec.end_calls)
            mock_exec.assert_has_calls(list(spec.end_calls))
        else:
            mock_exec.assert_not_called()

    @pytest.mark.parametrize("spec, mode", _cases("set_mode_valid"))
    def test_set_fan_mode(self, spec: PlatformSpec, mode: int, mock_exec: MagicMock) -> None:
        """set_fan_mode() issues exactly one write raw command for an accepted mode."""
        platform = spec.make(mock_exec)
        platform.set_fan_mode(mode)
        mock_exec.assert_called_with(_set_fan_mode_cmd(mode))
        assert mock_exec.call_count == 1

    @pytest.mark.parametrize("spec, mode", _cases("set_mode_invalid"))
    def test_set_fan_mode_invalid(self, spec: PlatformSpec, mode: int, mock_exec: MagicMock) -> None:
        """set_fan_mode() rejects modes the platform does not support with ValueError."""
        platform = spec.make(mock_exec)
        with pytest.raises(ValueError):
            platform.set_fan_mode(mode)

    @pytest.mark.parametrize("spec, zone, level, wire", _cases("set_level_vectors"))
    def test_set_fan_level(self, spec: PlatformSpec, zone: int, level: int, wire: int,
                           mock_exec: MagicMock) -> None:
        """set_fan_level() normalises the level and issues the platform's write command."""
        platform = spec.make(mock_exec)
        platform.set_fan_level(zone, level)
        assert mock_exec.call_count == spec.set_level_extra_calls + 1
        mock_exec.assert_called_with(spec.set_level_cmd(zone, wire))

    @pytest.mark.parametrize("spec, zone, level", _cases("bad_levels"))
    def test_set_fan_level_invalid(self, spec: PlatformSpec, zone: int, level: int, mock_exec: MagicMock) -> None:
        """set_fan_level() rejects out-of-range zones or levels with ValueError."""
        platform = spec.make(mock_exec)
        with pytest.raises(ValueError):
            platform.set_fan_level(zone, level)

    @pytest.mark.parametrize("spec, zones, level, wire", _cases("multi_vectors"))
    def test_set_multiple_fan_levels(self, spec: PlatformSpec, zones: List[int], level: int, wire: int,
                                     mock_exec: MagicMock) -> None:
        """set_multiple_fan_levels() writes the normalised level once per zone."""
        platform = spec.make(mock_exec)
        platform.set_multiple_fan_levels(zones, level)
        assert mock_exec.call_count == spec.multi_extra_calls + len(zones)
        zone_calls = [call(spec.set_level_cmd(zone, wire)) for zone in zones]
        mock_exec.assert_has_calls(zone_calls)

    @pytest.mark.parametrize("spec, zones, level", _cases("multi_bad"))
    def test_set_multiple_fan_levels_invalid(self, spec: PlatformSpec, zones: List[int], level: int,
                                             mock_exec: MagicMock) -> None:
        """set_multiple_fan_levels() rejects any out-of-range zone or level with ValueError."""
        platform = spec.make(mock_exec)
        with pytest.raises(ValueError):
            platform.set_multiple_fan_levels(zones, level)


# End.
