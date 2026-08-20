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
from typing import Callable, List, Optional
import pytest
from mock import MagicMock, call
from smfc.platform import ControlState, FanMode, Platform
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


# The X14 zone -> fan sensor map used by the tests: zone 0 is FAN1 (0x41) on every documented board, the
# other three are the X14DBI-SP layout (FAN6 and the lettered fans).
X14_ZONE_SENSORS = {0: 0x41, 1: 0x46, 2: 0x47, 3: 0x48}


def _x14_get_cmd(zone: int) -> List[str]:
    return ["raw", "0x30", "0x70", "0x88", f"0x{X14_ZONE_SENSORS[zone]:02x}"]


def _x14_set_cmd(zone: int, wire: int) -> List[str]:
    # Duty commands address zones 0-based.
    return ["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:02x}", f"0x{wire:02x}"]


def _x14_set_manual_cmd(zone: int, enabled: bool) -> List[str]:
    # Manual mode commands address zones 1-based.
    return ["raw", "0x2c", "0x04", "0xcf", "0xc2", "0x00", "0x01", f"0x{zone + 1:02x}", "0x01" if enabled else "0x00"]


def _x14_get_manual_cmd(zone: int) -> List[str]:
    return ["raw", "0x2c", "0x04", "0xcf", "0xc2", "0x00", "0x00", f"0x{zone + 1:02x}"]


def _x10qbi_get_cmd(zone: int) -> List[str]:
    return ["raw", "0x30", "0x90", "0x5c", "0x03", f"0x{0x10 + zone:x}", "0x01"]


def _x10qbi_set_cmd(zone: int, wire: int) -> List[str]:
    return ["raw", "0x30", "0x91", "0x5c", "0x03", f"0x{0x10 + zone:02x}", f"0x{wire:02x}"]


# Zone list every platform's start()/check_fan_mode() is driven with in the shared tests.
START_ZONES = (0, 1)
# The fan mode read and write shared by every platform that acquires control through FULL fan mode.
_FULL_START_CALLS = (call(GET_FAN_MODE_CMD),)
_FULL_ACQUIRE_CALLS = (call(GET_FAN_MODE_CMD), call(_set_fan_mode_cmd(FanMode.FULL)))
# X14 latches manual mode per zone and reads the flag back, instead of writing the fan mode.
_X14_START_CALLS = tuple(
    c for zone in START_ZONES
    for c in (call(_x14_set_manual_cmd(zone, True)), call(_x14_get_manual_cmd(zone)))
)
# X14 releases manual mode in every zone with a single shortcut command.
_X14_END_CALLS = (call(["raw", "0x30", "0x70", "0x66", "0x02", "0x00"]),)
_X10QBI_CHIP_CALLS = (
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
    start_stdout: str                                   # BMC reply that makes start() find the platform in control
    start_calls: tuple                                  # expected start() calls with that reply
    start_returns: bool                                 # start() return value with that reply
    acquire_stdout: Optional[str]                       # BMC reply forcing the acquire write (None => never writes)
    acquire_calls: tuple                                # expected start() calls with that reply
    lost_stdout: str                                    # BMC reply reporting a lost control state
    lost_detail: str                                    # substring expected in ControlStatus.detail then
    end_calls: tuple                                    # expected end() calls after the level writes (empty => none)
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
        start_stdout=" 01",
        start_calls=_FULL_START_CALLS,
        start_returns=False,
        acquire_stdout=" 00",
        acquire_calls=_FULL_ACQUIRE_CALLS,
        lost_stdout=" 00",
        lost_detail="drifted from FULL to STANDARD",
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
        get_level_vectors=((0, " 80", 50), (1, " ff", 100), (2, " 00", 0), (3, " 40", 25),
                           (0, " 66", 40), (1, " 87", 53), (2, " 9b", 61)),
        bad_zones=(-1, 4),
        start_stdout=" 01",
        start_calls=_FULL_START_CALLS,
        start_returns=False,
        acquire_stdout=" 00",
        acquire_calls=_FULL_ACQUIRE_CALLS,
        lost_stdout=" 00",
        lost_detail="drifted from FULL to STANDARD",
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
        make=lambda exec_fn: GenericX14Platform(PlatformName.GENERIC_X14, exec_fn, X14_ZONE_SENSORS),
        get_mode_values=(0, 1, 2, 4, 0x0B),
        get_level_cmd=_x14_get_cmd,
        get_level_vectors=(
            (0, " 64 2d", 0x64), (1, " 32 28", 0x32), (2, " 00 1e", 0x00), (3, " 4b 32", 0x4B),
        ),
        bad_zones=(-1, 4),
        start_stdout=" 01",
        start_calls=_X14_START_CALLS,
        start_returns=False,
        acquire_stdout=None,
        acquire_calls=(),
        lost_stdout=" 00",
        lost_detail="cleared in IPMI zone(s) [0, 1]",
        end_calls=_X14_END_CALLS,
        set_mode_valid=(FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO, 0x0B),
        set_mode_invalid=(-1, 0x0C, 100),
        set_level_cmd=_x14_set_cmd,
        set_level_extra_calls=0,
        set_level_vectors=((0, 100, 100), (1, 50, 50), (2, 0, 0), (3, 75, 75)),
        bad_levels=((-1, 50), (4, 50), (0, -1), (0, 101)),
        multi_extra_calls=0,
        multi_vectors=(([0, 1], 100, 100), ([0, 1, 2], 50, 50), ([2], 0, 0), ([0, 3], 75, 75)),
        multi_bad=(([-1, 0], 50), ([0, 4], 50), ([0], -1), ([0], 101)),
    ),
    PlatformSpec(
        label="x10qbi",
        make=lambda exec_fn: X10QBi("X10QBi", exec_fn),
        get_mode_values=(0, 1, 4),
        get_level_cmd=_x10qbi_get_cmd,
        get_level_vectors=((0, " 80", 50), (1, " ff", 100), (2, " 00", 0), (3, " 40", 25),
                           (0, " 66", 40), (1, " 87", 53), (2, " 9b", 61)),
        bad_zones=(-1, 4),
        start_stdout=" 01",
        start_calls=_X10QBI_CHIP_CALLS + _FULL_START_CALLS,
        start_returns=False,
        acquire_stdout=" 00",
        acquire_calls=_X10QBI_CHIP_CALLS + _FULL_ACQUIRE_CALLS,
        lost_stdout=" 00",
        lost_detail="drifted from FULL to STANDARD",
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
        """Positive unit test for Platform.get_fan_mode() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to return a CompletedProcess whose stdout encodes the BMC fan mode
        - build the platform via spec.make() and invoke get_fan_mode()
        - ASSERT: get_fan_mode() returns the BMC-reported mode value
        - ASSERT: exec callback is invoked with the GET_FAN_MODE_CMD ipmitool byte sequence
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {mode:02}")
        platform = spec.make(mock_exec)
        assert platform.get_fan_mode() == mode
        mock_exec.assert_called_with(GET_FAN_MODE_CMD)

    @pytest.mark.parametrize("spec, zone, hex_output, expected_level", _cases("get_level_vectors"))
    def test_get_fan_level(self, spec: PlatformSpec, zone: int, hex_output: str, expected_level: int,
                           mock_exec: MagicMock) -> None:
        """Positive unit test for Platform.get_fan_level() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to return a CompletedProcess whose stdout encodes the duty cycle byte
        - build the platform via spec.make() and invoke get_fan_level() for the given zone
        - ASSERT: get_fan_level() decodes the BMC duty cycle to the expected level
        - ASSERT: exec callback is invoked with the platform-specific read ipmitool byte sequence
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=hex_output)
        platform = spec.make(mock_exec)
        assert platform.get_fan_level(zone) == expected_level
        mock_exec.assert_called_with(spec.get_level_cmd(zone))

    @pytest.mark.parametrize("spec", PLATFORMS, ids=PLATFORM_IDS)
    def test_fan_level_roundtrip(self, spec: PlatformSpec, mock_exec: MagicMock) -> None:
        """Positive unit test for the Platform.set_fan_level()/get_fan_level() round-trip. It contains the steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - build the platform via spec.make() and call set_fan_level() for every level in [0..100]
        - read back the duty cycle byte written to the BMC from the recorded ipmitool command
        - mock the exec callback to return that byte, and invoke get_fan_level() with it
        - ASSERT: get_fan_level() returns the level originally passed to set_fan_level() for every level in [0..100]
        """
        platform = spec.make(mock_exec)
        for level in range(101):
            mock_exec.reset_mock()
            platform.set_fan_level(0, level)
            wire_byte = mock_exec.call_args[0][0][-1]
            mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {wire_byte[2:]}")
            assert platform.get_fan_level(0) == level

    @pytest.mark.parametrize("spec, zone", _cases("bad_zones"))
    def test_get_fan_level_invalid_zone(self, spec: PlatformSpec, zone: int, mock_exec: MagicMock) -> None:
        """Negative unit test for Platform.get_fan_level() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback (no BMC interaction expected)
        - build the platform via spec.make() and invoke get_fan_level() with an out-of-range zone
        - ASSERT: get_fan_level() raises ValueError for zones outside the platform's accepted range
        """
        platform = spec.make(mock_exec)
        with pytest.raises(ValueError):
            platform.get_fan_level(zone)

    @pytest.mark.parametrize("spec", PLATFORMS, ids=PLATFORM_IDS)
    def test_start(self, spec: PlatformSpec, mock_exec: MagicMock) -> None:
        """Positive unit test for Platform.start() method when the platform is already in the controlled state.
        It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to report the controlled state (FULL fan mode, or a latched X14 manual
          mode flag) and to record the sequence of issued commands
        - build the platform via spec.make() and invoke start() with the shared START_ZONES zone list
        - ASSERT: exec callback is invoked exactly len(spec.start_calls) times, i.e. the platform issues no
          command beyond reading the state (and, on X10QBi, configuring the chip)
        - ASSERT: exec callback receives the platform's own acquire ipmitool byte sequences, in order
        - ASSERT: start() returns spec.start_returns, i.e. False whenever no fan mode was written, so the caller
          skips the fan_mode_delay sleep
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=spec.start_stdout)
        platform = spec.make(mock_exec)
        assert platform.start(list(START_ZONES)) is spec.start_returns
        assert mock_exec.call_count == len(spec.start_calls)
        mock_exec.assert_has_calls(list(spec.start_calls))

    @pytest.mark.parametrize("spec", PLATFORMS, ids=PLATFORM_IDS)
    def test_start_acquires(self, spec: PlatformSpec, mock_exec: MagicMock) -> None:
        """Positive unit test for Platform.start() method when control has to be acquired. It contains the steps:
        - applies to the platforms that acquire control through FULL fan mode (Generic, GenericX9, X10qbi); the
          X14 platform never writes the fan mode, so it declares acquire_stdout=None and is skipped here
        - mock the ipmitool exec callback to report a non-FULL fan mode and to record the issued commands
        - build the platform via spec.make() and invoke start() with the shared START_ZONES zone list
        - ASSERT: exec callback receives the fan mode read followed by the FULL fan mode write
        - ASSERT: exec callback is invoked exactly len(spec.acquire_calls) times
        - ASSERT: start() returns True, so the caller applies the fan_mode_delay sleep
        """
        if spec.acquire_stdout is None:
            pytest.skip(f"{spec.label} never writes the fan mode")
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=spec.acquire_stdout)
        platform = spec.make(mock_exec)
        assert platform.start(list(START_ZONES)) is True
        assert mock_exec.call_count == len(spec.acquire_calls)
        mock_exec.assert_has_calls(list(spec.acquire_calls))

    @pytest.mark.parametrize("spec", PLATFORMS, ids=PLATFORM_IDS)
    def test_check_fan_mode_ok(self, spec: PlatformSpec, mock_exec: MagicMock) -> None:
        """Positive unit test for Platform.check_fan_mode() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to report the controlled state (FULL fan mode / latched manual mode)
        - build the platform via spec.make() and invoke check_fan_mode() with the shared START_ZONES zone list
        - ASSERT: the returned ControlStatus.state is ControlState.OK
        - ASSERT: the status is confirmed, i.e. the state was really read from the BMC
        - ASSERT: the observed fan mode is cached in ControlStatus.fan_mode for the snapshot
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=spec.start_stdout)
        platform = spec.make(mock_exec)
        status = platform.check_fan_mode(list(START_ZONES))
        assert status.state == ControlState.OK
        assert status.confirmed is True
        assert status.fan_mode == FanMode.FULL

    @pytest.mark.parametrize("spec", PLATFORMS, ids=PLATFORM_IDS)
    def test_check_fan_mode_lost(self, spec: PlatformSpec, mock_exec: MagicMock) -> None:
        """Negative unit test for Platform.check_fan_mode() method on a lost control state. It contains the steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to report a drifted fan mode (or a cleared X14 manual mode flag)
        - build the platform via spec.make() and invoke check_fan_mode() with the shared START_ZONES zone list
        - ASSERT: the returned ControlStatus.state is ControlState.LOST
        - ASSERT: the status is confirmed, because the loss was really observed and must be counted as drift
        - ASSERT: ControlStatus.detail names the platform-specific reason, which the caller logs verbatim
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=spec.lost_stdout)
        platform = spec.make(mock_exec)
        status = platform.check_fan_mode(list(START_ZONES))
        assert status.state == ControlState.LOST
        assert status.confirmed is True
        assert spec.lost_detail in status.detail

    @pytest.mark.parametrize("spec", PLATFORMS, ids=PLATFORM_IDS)
    def test_check_fan_mode_unreadable(self, spec: PlatformSpec, mock_exec: MagicMock) -> None:
        """Negative unit test for Platform.check_fan_mode() method on an unreadable state. It contains the steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to raise RuntimeError, i.e. the BMC rejected the command or is unreachable
        - build the platform via spec.make() and invoke check_fan_mode() with the shared START_ZONES zone list
        - ASSERT: check_fan_mode() does not propagate the error, the state is reported as ControlState.LOST
        - ASSERT: the status is not confirmed, so the caller neither counts it as drift nor exits on it
        - ASSERT: ControlStatus.fan_mode is -1, so the caller leaves the cached fan mode untouched
        """
        mock_exec.side_effect = RuntimeError("ipmitool error (1): Invalid command.")
        platform = spec.make(mock_exec)
        status = platform.check_fan_mode(list(START_ZONES))
        assert status.state == ControlState.LOST
        assert status.confirmed is False
        assert status.fan_mode == -1

    @pytest.mark.parametrize("spec", PLATFORMS, ids=PLATFORM_IDS)
    def test_end(self, spec: PlatformSpec, mock_exec: MagicMock) -> None:
        """Positive unit test for Platform.end() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to record the sequence of issued commands
        - build the platform via spec.make() and invoke end() with the first multi_vectors (zones, level) case
        - ASSERT: the exit level is written to every requested zone with the platform's own level command and
          wire encoding
        - ASSERT: exec callback is invoked exactly once per zone, plus the platform's pre-write and post-write
          calls (X10QBi chip setup, X14 manual-mode release)
        - ASSERT: platforms releasing manual mode (X14) do so after the level writes, not before, otherwise the
          BMC would take over and the level writes would be lost
        """
        zones, level, wire = spec.multi_vectors[0]
        platform = spec.make(mock_exec)
        platform.end(list(zones), level)
        expected_calls = [call(spec.set_level_cmd(zone, wire)) for zone in zones]
        assert mock_exec.call_count == spec.multi_extra_calls + len(expected_calls) + len(spec.end_calls)
        mock_exec.assert_has_calls(expected_calls + list(spec.end_calls))

    @pytest.mark.parametrize("spec, mode", _cases("set_mode_valid"))
    def test_set_fan_mode(self, spec: PlatformSpec, mode: int, mock_exec: MagicMock) -> None:
        """Positive unit test for Platform.set_fan_mode() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to record the issued command
        - build the platform via spec.make() and invoke set_fan_mode() with a platform-accepted mode
        - ASSERT: exec callback is invoked with the set-fan-mode ipmitool byte sequence for the given mode
        - ASSERT: exec callback is invoked exactly once (single write raw command)
        """
        platform = spec.make(mock_exec)
        platform.set_fan_mode(mode)
        mock_exec.assert_called_with(_set_fan_mode_cmd(mode))
        assert mock_exec.call_count == 1

    @pytest.mark.parametrize("spec, mode", _cases("set_mode_invalid"))
    def test_set_fan_mode_invalid(self, spec: PlatformSpec, mode: int, mock_exec: MagicMock) -> None:
        """Negative unit test for Platform.set_fan_mode() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback (no BMC interaction expected)
        - build the platform via spec.make() and invoke set_fan_mode() with a mode the platform does not support
        - ASSERT: set_fan_mode() raises ValueError for unsupported modes
        """
        platform = spec.make(mock_exec)
        with pytest.raises(ValueError):
            platform.set_fan_mode(mode)

    @pytest.mark.parametrize("spec, zone, level, wire", _cases("set_level_vectors"))
    def test_set_fan_level(self, spec: PlatformSpec, zone: int, level: int, wire: int,
                           mock_exec: MagicMock) -> None:
        """Positive unit test for Platform.set_fan_level() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to record the sequence of issued commands
        - build the platform via spec.make() and invoke set_fan_level() with a valid zone and level
        - ASSERT: exec callback is invoked exactly spec.set_level_extra_calls + 1 times (covers X10QBi pre-write calls)
        - ASSERT: exec callback's last call uses the platform's write ipmitool byte sequence with the normalised wire
          level
        """
        platform = spec.make(mock_exec)
        platform.set_fan_level(zone, level)
        assert mock_exec.call_count == spec.set_level_extra_calls + 1
        mock_exec.assert_called_with(spec.set_level_cmd(zone, wire))

    @pytest.mark.parametrize("spec, zone, level", _cases("bad_levels"))
    def test_set_fan_level_invalid(self, spec: PlatformSpec, zone: int, level: int, mock_exec: MagicMock) -> None:
        """Negative unit test for Platform.set_fan_level() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback (no BMC interaction expected)
        - build the platform via spec.make() and invoke set_fan_level() with an out-of-range zone or level
        - ASSERT: set_fan_level() raises ValueError for invalid zone or level
        """
        platform = spec.make(mock_exec)
        with pytest.raises(ValueError):
            platform.set_fan_level(zone, level)

    @pytest.mark.parametrize("spec, zones, level, wire", _cases("multi_vectors"))
    def test_set_multiple_fan_levels(self, spec: PlatformSpec, zones: List[int], level: int, wire: int,
                                     mock_exec: MagicMock) -> None:
        """Positive unit test for Platform.set_multiple_fan_levels() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback to record the sequence of issued commands
        - build the platform via spec.make() and invoke set_multiple_fan_levels() with a zone list and level
        - ASSERT: exec callback is invoked spec.multi_extra_calls + len(zones) times (pre-write calls + one per zone)
        - ASSERT: exec callback receives the expected platform-specific write ipmitool byte sequence for each zone
        """
        platform = spec.make(mock_exec)
        platform.set_multiple_fan_levels(zones, level)
        assert mock_exec.call_count == spec.multi_extra_calls + len(zones)
        zone_calls = [call(spec.set_level_cmd(zone, wire)) for zone in zones]
        mock_exec.assert_has_calls(zone_calls)

    @pytest.mark.parametrize("spec, zones, level", _cases("multi_bad"))
    def test_set_multiple_fan_levels_invalid(self, spec: PlatformSpec, zones: List[int], level: int,
                                             mock_exec: MagicMock) -> None:
        """Negative unit test for Platform.set_multiple_fan_levels() method. It contains the following steps:
        - applies to all platforms (Generic, GenericX9, GenericX14, X10qbi) via the parametrized PlatformSpec matrix
        - mock the ipmitool exec callback (no BMC interaction expected)
        - build the platform via spec.make() and invoke set_multiple_fan_levels() with an out-of-range zone or level
        - ASSERT: set_multiple_fan_levels() raises ValueError when any zone is out of range or the level is invalid
        """
        platform = spec.make(mock_exec)
        with pytest.raises(ValueError):
            platform.set_multiple_fan_levels(zones, level)


class TestGenericX14Platform:
    """Unit tests for the behaviour that is unique to GenericX14Platform and therefore not covered by the
    shared PlatformSpec matrix: the manual-mode latch confirmation, the configured zone -> fan sensor map and
    the two-byte duty reply."""

    @staticmethod
    def _platform(mock_exec: MagicMock, zone_sensors=None) -> GenericX14Platform:
        """Build a GenericX14Platform around the given mock exec callback."""
        return GenericX14Platform(PlatformName.GENERIC_X14, mock_exec, zone_sensors)

    def test_start_latch_not_confirmed(self, mock_exec: MagicMock) -> None:
        """Negative unit test for GenericX14Platform.start() method. It contains the following steps:
        - mock the ipmitool exec callback so the manual mode flag reads back as cleared (the BMC accepted the
          latch command but did not enter manual mode, which is how an H14 board behaves)
        - build the platform and invoke start() for zone 0
        - ASSERT: start() raises RuntimeError instead of pretending smfc controls the zone
        - ASSERT: the error names the zone and points at the preflight chapter of the X14 command reference
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=" 00")
        platform = self._platform(mock_exec)
        with pytest.raises(RuntimeError) as excinfo:
            platform.start([0])
        assert "IPMI zone 0" in str(excinfo.value)
        assert "chapter 4.0" in str(excinfo.value)

    def test_start_latches_only_controlled_zones(self, mock_exec: MagicMock) -> None:
        """Positive unit test for GenericX14Platform.start() method. It contains the following steps:
        - mock the ipmitool exec callback to report a latched manual mode flag
        - build the platform and invoke start() for zone 1 only
        - ASSERT: only zone 1 is latched (as the 1-based zone byte 0x02), because latching a zone smfc does not
          drive would freeze it at its current duty with nothing regulating it
        - ASSERT: exec callback is invoked exactly twice, i.e. the latch write and its read-back confirmation
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=" 01")
        platform = self._platform(mock_exec)
        platform.start([1])
        assert mock_exec.call_count == 2
        mock_exec.assert_has_calls([call(_x14_set_manual_cmd(1, True)), call(_x14_get_manual_cmd(1))])

    @pytest.mark.parametrize("zone", [-1, 4], ids=["below-range", "above-range"])
    def test_start_invalid_zone(self, zone: int, mock_exec: MagicMock) -> None:
        """Negative unit test for GenericX14Platform.start() method. It contains the following steps:
        - mock the ipmitool exec callback (no BMC interaction expected)
        - build the platform and invoke start() with a zone outside the documented 0-3 range
        - ASSERT: start() raises ValueError
        - ASSERT: no ipmitool command is issued, so an invalid configuration never touches the BMC
        """
        platform = self._platform(mock_exec)
        with pytest.raises(ValueError):
            platform.start([zone])
        mock_exec.assert_not_called()

    def test_end_falls_back_to_per_zone_release(self, mock_exec: MagicMock) -> None:
        """Positive unit test for GenericX14Platform.end() method. It contains the following steps:
        - mock the ipmitool exec callback so every command succeeds except the all-zones manual mode release,
          which raises RuntimeError as firmware rejecting the shortcut would
        - build the platform and invoke end() for zones 0 and 1 with the exit level 50%
        - ASSERT: the exit level is written to both zones before any release is attempted
        - ASSERT: the all-zones shortcut is attempted first
        - ASSERT: after it fails, manual mode is released per zone, so nothing stays latched
        """
        ok = subprocess.CompletedProcess([], returncode=0, stdout="")
        shortcut = ["raw", "0x30", "0x70", "0x66", "0x02", "0x00"]
        mock_exec.side_effect = lambda args: (_ for _ in ()).throw(RuntimeError("rejected")) if args == shortcut else ok
        platform = self._platform(mock_exec)
        platform.end([0, 1], 50)
        expected = [call(_x14_set_cmd(0, 50)), call(_x14_set_cmd(1, 50)), call(shortcut),
                    call(_x14_set_manual_cmd(0, False)), call(_x14_set_manual_cmd(1, False))]
        assert mock_exec.call_args_list == expected

    def test_get_fan_level_unmapped_zone(self, mock_exec: MagicMock) -> None:
        """Negative unit test for GenericX14Platform.get_fan_level() method. It contains the following steps:
        - mock the ipmitool exec callback (no BMC interaction expected)
        - build the platform with the default zone -> fan sensor map, which only covers zone 0
        - invoke get_fan_level() for zone 1
        - ASSERT: get_fan_level() raises RuntimeError naming the configuration parameter that supplies the map
        - ASSERT: no ipmitool command is issued, because there is no sensor number to address
        """
        platform = self._platform(mock_exec)
        with pytest.raises(RuntimeError) as excinfo:
            platform.get_fan_level(1)
        assert "x14_zone_sensors" in str(excinfo.value)
        mock_exec.assert_not_called()

    def test_get_fan_level_default_sensor(self, mock_exec: MagicMock) -> None:
        """Positive unit test for GenericX14Platform.get_fan_level() method. It contains the following steps:
        - mock the ipmitool exec callback to return the two-byte duty + temperature reply of FAN1
        - build the platform without a zone -> fan sensor map, so the default applies
        - invoke get_fan_level() for zone 0
        - ASSERT: zone 0 is read from sensor 0x41 (FAN1), the default that is correct on every documented board
        - ASSERT: the duty is decoded from the first reply byte as a hexadecimal percentage
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=" 32 2d")
        platform = self._platform(mock_exec)
        assert platform.get_fan_level(0) == 50
        mock_exec.assert_called_with(["raw", "0x30", "0x70", "0x88", "0x41"])

    def test_get_fan_level_unavailable(self, mock_exec: MagicMock) -> None:
        """Negative unit test for GenericX14Platform.get_fan_level() method. It contains the following steps:
        - mock the ipmitool exec callback to return 0xff as the duty byte, the BMC's "value unavailable" marker
        - build the platform and invoke get_fan_level() for zone 0
        - ASSERT: get_fan_level() raises ValueError instead of reporting a 255% fan level
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=" ff ff")
        platform = self._platform(mock_exec)
        with pytest.raises(ValueError):
            platform.get_fan_level(0)


# End.
