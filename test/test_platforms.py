#!/usr/bin/env python3
#
#   test_platforms.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   Unified, matrix-driven unit tests for all smfc Platform implementations
#   (GenericPlatform, GenericX9Platform, X14OpenBmcPlatform, X14AtenPlatform, X10QBi).
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
from smfc.platform import ControlState, FanMode, IpmiError, Platform
from smfc.config import PlatformName
from smfc.generic import GenericPlatform
from smfc.genericx9 import GenericX9Platform
from smfc.genericx14 import X14AtenPlatform, X14OpenBmcCmd, X14OpenBmcPlatform
from smfc.x10qbi import X10QBi
from .test_fixtures import FakeOpenBmc

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
def _x14_get_cmd(zone: int) -> List[str]:
    # The duty read addresses the same 0-based zone as the write; selector 0x00 reads, 0x01 writes.
    return ["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:02x}"]


def _x14_set_cmd(zone: int, wire: int) -> List[str]:
    # Duty commands address zones 0-based; selector 0x01 writes a duty, 0x00 reads one.
    return ["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{wire:02x}"]


def _x14_set_manual_cmd(zone: int, enabled: bool) -> List[str]:
    # Manual mode commands address zones 1-based.
    return ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x01", f"0x{zone + 1:02x}", "0x01" if enabled else "0x00"]


def _x14_get_manual_cmd(zone: int) -> List[str]:
    return ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x00", f"0x{zone + 1:02x}"]


def _x14_get_failsafe_cmd(zone: int) -> List[str]:
    return ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x02", f"0x{zone + 1:02x}"]


def _x14_exec(stdout: str) -> Callable[[List[str]], subprocess.CompletedProcess]:
    """Answer every command with `stdout`, except the OEM failsafe read, which reports a healthy zone.

    The X14 rows drive the whole matrix from one reply string, and the failsafe flag shares the reply
    shape of the manual mode flag. Without this the same `01` would mean both "manual mode is latched"
    and "the BMC has forced this zone to 100%", which are opposite states.
    """
    def exec_fn(args: List[str]) -> subprocess.CompletedProcess:
        if args[:7] == ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x02"]:
            return subprocess.CompletedProcess([], returncode=0, stdout=" cf c2 00 00")
        return subprocess.CompletedProcess([], returncode=0, stdout=stdout)
    return exec_fn


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
_X14_PROBE_CALLS = tuple(call(_x14_get_failsafe_cmd(zone)) for zone in range(X14OpenBmcPlatform.FANCTL_COUNT))
_X14_START_CALLS = _X14_PROBE_CALLS + tuple(
    c for zone in START_ZONES
    for c in (call(_x14_set_manual_cmd(zone, True)), call(_x14_get_manual_cmd(zone)))
)
# X14 releases manual mode in every zone with a single shortcut command.
_X14_END_CALLS = (call(["raw", "0x30", "0x70", "0x66", "0x02", "0x00"]),)
# The ATEN stack has no per-zone lever: one global bypass flag suspends the BMC's automatic fan control
# loop for every zone, and the same flag is cleared on exit. It is write-only, so there is nothing to
# read back and start() issues exactly one command.
_ATEN_BYPASS_ON = ["raw", "0x30", "0x70", "0x66", "0x02", "0x01"]
_ATEN_BYPASS_OFF = ["raw", "0x30", "0x70", "0x66", "0x02", "0x00"]
_ATEN_START_CALLS = (call(_ATEN_BYPASS_ON),)
_ATEN_END_CALLS = (call(_ATEN_BYPASS_OFF),)
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
    lost_stdout: Optional[str]                          # BMC reply reporting a lost control state (None => skip)
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
    set_mode_extra_calls: int = 0                       # extra exec calls before the fan mode write
    roundtrip_min: int = 0                              # duty floor the platform clamps every write to


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
        label="x14_openbmc",
        make=lambda exec_fn: X14OpenBmcPlatform(PlatformName.GENERIC_X14, exec_fn),
        get_mode_values=(0, 1, 2, 4, 0x0B),
        get_level_cmd=_x14_get_cmd,
        get_level_vectors=((0, " 64", 0x64), (1, " 32", 0x32), (2, " 00", 0x00), (3, " 4b", 0x4B)),
        bad_zones=(-1, 5),
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
        set_mode_extra_calls=1,
        set_level_cmd=_x14_set_cmd,
        set_level_extra_calls=0,
        set_level_vectors=((0, 100, 100), (1, 50, 50), (2, 0, 5), (3, 75, 75), (4, 40, 40)),
        bad_levels=((-1, 50), (5, 50), (0, -1), (0, 101)),
        multi_extra_calls=0,
        multi_vectors=(([0, 1], 100, 100), ([0, 1, 2], 50, 50), ([2], 0, 5), ([0, 3], 75, 75), ([0, 4], 60, 60)),
        multi_bad=(([-1, 0], 50), ([0, 5], 50), ([0], -1), ([0], 101)),
        roundtrip_min=5,
    ),
    PlatformSpec(
        # The ATEN duty commands are byte-for-byte GenericPlatform's (ATEN *is* the X9-X13 firmware line),
        # so this row deliberately reuses the _generic_* command builders: if the two ever diverge, this row
        # fails. What differs is the lever - a global bypass flag instead of FULL fan mode - and the 5% floor.
        label="x14_aten",
        make=lambda exec_fn: X14AtenPlatform(PlatformName.GENERIC_X14, exec_fn),
        get_mode_values=(0, 1, 2, 4),
        get_level_cmd=_generic_get_cmd,
        get_level_vectors=((0, " 32", 0x32), (1, " 64", 0x64), (2, " 31", 0x31), (3, " 05", 0x05)),
        bad_zones=(-1, 101),
        start_stdout=" 01",
        start_calls=_ATEN_START_CALLS,
        start_returns=False,
        acquire_stdout=None,
        acquire_calls=(),
        lost_stdout=None,
        lost_detail="",
        end_calls=_ATEN_END_CALLS,
        set_mode_valid=(FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO),
        set_mode_invalid=(-1, 100),
        set_level_cmd=_generic_set_cmd,
        set_level_extra_calls=0,
        set_level_vectors=((0, 50, 50), (1, 100, 100), (100, 0, 5), (2, 3, 5), (3, 5, 5)),
        bad_levels=((-1, 50), (101, 50), (0, -1), (0, 101)),
        multi_extra_calls=0,
        multi_vectors=(([0, 1], 100, 100), ([0, 1, 2, 3], 50, 50), ([0], 0, 5)),
        multi_bad=(([-1, 0], 50), ([0, 101], 50), ([0], -1), ([0], 101)),
        roundtrip_min=5,
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
        - ASSERT: get_fan_level() returns the level originally passed to set_fan_level() for every level in
          [0..100], except below a platform's own duty floor (spec.roundtrip_min), where the write is clamped
          on purpose: X14AtenPlatform never writes below 5% because the ATEN percent duty path has no floor of
          its own and a real 0% would stop the fans with the BMC thermal loop suspended
        """
        platform = spec.make(mock_exec)
        for level in range(101):
            mock_exec.reset_mock()
            platform.set_fan_level(0, level)
            wire_byte = mock_exec.call_args[0][0][-1]
            mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {wire_byte[2:]}")
            assert platform.get_fan_level(0) == max(level, spec.roundtrip_min)

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
        mock_exec.side_effect = _x14_exec(spec.start_stdout)
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
        mock_exec.side_effect = _x14_exec(spec.start_stdout)
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
        if spec.lost_stdout is None:
            pytest.skip(f"{spec.label} has no readable lever; its loss detection is covered by TestX14AtenPlatform")
        mock_exec.side_effect = _x14_exec(spec.lost_stdout)
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
        assert mock_exec.call_count == spec.set_mode_extra_calls + 1

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


class TestX14OpenBmcPlatform:
    """Unit tests for the behaviour that is unique to X14OpenBmcPlatform and therefore not covered by the
    shared PlatformSpec matrix: the manual-mode latch confirmation, the configured zone -> fan sensor map and
    the two-byte duty reply."""

    @staticmethod
    def _platform(mock_exec: MagicMock) -> X14OpenBmcPlatform:
        """Build an X14OpenBmcPlatform around the given mock exec callback."""
        return X14OpenBmcPlatform(PlatformName.GENERIC_X14, mock_exec)

    def test_start_latch_not_confirmed(self, mock_exec: MagicMock) -> None:
        """Negative unit test for X14OpenBmcPlatform.start() method. It contains the following steps:
        - mock the ipmitool exec callback so the manual mode flag reads back as cleared (the BMC accepted the
          latch command but did not enter manual mode)
        - build the platform and invoke start() for zone 0
        - ASSERT: start() raises RuntimeError instead of pretending smfc controls the zone
        - ASSERT: the error names the zone and points at the OpenBMC procedure of the command reference. It no
          longer suggests an H14 board: the firmware stack is settled by the Part 1 probe before this class is
          built, so a refusal here means the zone does not exist or the BMC rejected the command
        """
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=" 00")
        platform = self._platform(mock_exec)
        with pytest.raises(RuntimeError) as excinfo:
            platform.start([0])
        assert "IPMI zone 0" in str(excinfo.value)
        assert "doc/X14H14_MANUAL_FANCONTROL.md, Part 3.5" in str(excinfo.value)

    @pytest.mark.parametrize("reply, latched", [(" cf c2 00 01", True), (" cf c2 00 00", False)],
                             ids=["latched", "cleared"])
    def test_manual_flag_is_the_last_reply_byte(self, reply: str, latched: bool, mock_exec: MagicMock) -> None:
        """Positive and negative unit test for X14OpenBmcPlatform._get_manual_mode(). It contains the steps:
        - mock the ipmitool exec callback to answer with the OEM reply the BMC really sends, which echoes the
          IANA ID of the command back before the payload: `cf c2 00 <flag>`
        - build the platform and invoke start() for zone 0
        - ASSERT: the latched reply is read as latched, i.e. start() succeeds and records the zone. Reading
          the first byte instead of the last would see `cf` and never confirm a latch
        - ASSERT: the cleared reply is read as cleared, i.e. start() raises rather than pretending smfc
          controls a zone the BMC still drives itself
        """
        f = "TestX14OpenBmcPlatform.test_manual_flag_is_the_last_reply_byte"
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=reply)
        platform = self._platform(mock_exec)
        if latched:
            platform.start([0])
            assert platform.latched_zones == [0], f"{f}: latched zones"
        else:
            with pytest.raises(RuntimeError):
                platform.start([0])
            assert platform.latched_zones == [], f"{f}: nothing latched"

    def test_start_latches_only_controlled_zones(self, mock_exec: MagicMock) -> None:
        """Positive unit test for X14OpenBmcPlatform.start() method. It contains the following steps:
        - mock the ipmitool exec callback to report a latched manual mode flag
        - build the platform and invoke start() for zone 1 only
        - ASSERT: only zone 1 is latched (as the 1-based zone byte 0x02), because latching a zone smfc does not
          drive would freeze it at its current duty with nothing regulating it
        - ASSERT: exec callback is invoked exactly twice beyond the zone count probe, i.e. the latch write and
          its read-back confirmation, and nothing for the zones smfc does not drive
        """
        mock_exec.side_effect = _x14_exec(" 01")
        platform = self._platform(mock_exec)
        platform.start([1])
        assert mock_exec.call_count == len(_X14_PROBE_CALLS) + 2
        mock_exec.assert_has_calls([call(_x14_set_manual_cmd(1, True)), call(_x14_get_manual_cmd(1))])

    @pytest.mark.parametrize("zone", [-1, 5], ids=["below-range", "above-range"])
    def test_start_invalid_zone(self, zone: int, mock_exec: MagicMock) -> None:
        """Negative unit test for X14OpenBmcPlatform.start() method. It contains the following steps:
        - mock the ipmitool exec callback (no BMC interaction expected)
        - build the platform and invoke start() with a zone outside the documented 0-4 range
        - ASSERT: start() raises ValueError
        - ASSERT: no ipmitool command is issued, so an invalid configuration never touches the BMC
        """
        platform = self._platform(mock_exec)
        with pytest.raises(ValueError):
            platform.start([zone])
        mock_exec.assert_not_called()

    def test_end_falls_back_to_per_zone_release(self, mock_exec: MagicMock) -> None:
        """Positive unit test for X14OpenBmcPlatform.end() method. It contains the following steps:
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

    def test_end_exit_level_none_still_releases(self, mock_exec: MagicMock) -> None:
        """Positive unit test for X14OpenBmcPlatform.end() method. It contains the following steps:
        - mock the ipmitool exec callback to record the sequence of issued commands
        - build the platform and invoke end() for zones 0 and 1 with the exit level -1 (`exit_level=-1`)
        - ASSERT: no fan level is written, because -1 means smfc leaves the fan levels alone
        - ASSERT: manual mode is released all the same - a latch that is never released leaves every zone
          frozen at its last duty with nothing regulating it, which is a worse outcome than any exit level
        """
        f = "TestX14OpenBmcPlatform.test_end_exit_level_none_still_releases"
        platform = self._platform(mock_exec)
        platform.end([0, 1], -1)
        assert mock_exec.call_args_list == [call(["raw", "0x30", "0x70", "0x66", "0x02", "0x00"])], f"{f}: calls"

    def test_end_releases_even_if_the_level_write_fails(self, mock_exec: MagicMock) -> None:
        """Negative unit test for X14OpenBmcPlatform.end() method. It contains the following steps:
        - mock the ipmitool exec callback so the exit level write fails but every other command succeeds
        - build the platform and invoke end() for zones 0 and 1 with the exit level 50%
        - ASSERT: end() propagates the level write error, so the caller can log it
        - ASSERT: manual mode is released all the same. The exit level is optional; the release is not, and
          making it depend on the level write succeeding would leave the zones frozen at their last duty with
          nothing regulating them - the same defect as skipping end() when `exit_level=-1`
        """
        f = "TestX14OpenBmcPlatform.test_end_releases_even_if_the_level_write_fails"
        shortcut = ["raw", "0x30", "0x70", "0x66", "0x02", "0x00"]
        ok = subprocess.CompletedProcess([], returncode=0, stdout="")

        def exec_fn(args):
            if args[:5] == ["raw", "0x30", "0x70", "0x66", "0x01"]:
                raise IpmiError("ipmitool error (1): Unable to establish IPMI v2 session.", None)
            return ok

        mock_exec.side_effect = exec_fn
        platform = self._platform(mock_exec)
        with pytest.raises(RuntimeError):
            platform.end([0, 1], 50)
        assert call(shortcut) in mock_exec.call_args_list, f"{f}: manual mode released"

    def test_start_records_latched_zones(self, mock_exec: MagicMock) -> None:
        """Positive unit test for X14OpenBmcPlatform.start() method. It contains the following steps:
        - mock the ipmitool exec callback to report a latched manual mode flag
        - build the platform and invoke start() for zones 0 and 2
        - ASSERT: the latched zones are recorded on the platform, so end() can release exactly what start()
          acquired without depending on the caller resolving the same zone list during interpreter shutdown
        """
        f = "TestX14OpenBmcPlatform.test_start_records_latched_zones"
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=" 01")
        platform = self._platform(mock_exec)
        platform.start([0, 2])
        assert platform.latched_zones == [0, 2], f"{f}: latched zones"


class TestX14OpenBmcCmd:
    """Unit tests for the OpenBMC command table.

    Every raw command of this stack is built here, so this is the one place to diff against Part 3.1 and
    Part 3.2 of `doc/X14H14_MANUAL_FANCONTROL.md`. The expected byte sequences below are written out in
    full and deliberately not composed from the class's own constants: a test that reuses the code's
    building blocks can only confirm the code agrees with itself.
    """

    @pytest.mark.parametrize("args, expected", [
        pytest.param((0,), ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x00", "0x01"], id="zone-0"),
        pytest.param((4,), ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x00", "0x05"], id="zone-4"),
    ])
    def test_read_manual(self, args: tuple, expected: List[str]) -> None:
        """Positive unit test for X14OpenBmcCmd.read_manual(). It contains the following steps:
        - call read_manual() for the first and the last zone
        - ASSERT: the command matches Part 3.1 byte for byte, on netfn 0x2e and carrying the IANA ID
        - ASSERT: the zone byte is 1-based, so smfc zone 0 is 0x01
        """
        assert X14OpenBmcCmd.read_manual(*args) == expected

    @pytest.mark.parametrize("enabled, expected", [
        pytest.param(True, ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x01", "0x01", "0x01"], id="on"),
        pytest.param(False, ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x01", "0x01", "0x00"], id="off"),
    ])
    def test_set_manual(self, enabled: bool, expected: List[str]) -> None:
        """Positive unit test for X14OpenBmcCmd.set_manual(). It contains the following steps:
        - call set_manual() for zone 0, enabling and disabling
        - ASSERT: the command matches Part 3.1, with operation byte 0x01 and the flag last
        """
        assert X14OpenBmcCmd.set_manual(0, enabled) == expected

    def test_read_failsafe(self) -> None:
        """Positive unit test for X14OpenBmcCmd.read_failsafe(). It contains the following steps:
        - call read_failsafe() for zone 1
        - ASSERT: the command matches Part 3.1, with operation byte 0x02 and the 1-based zone byte
        """
        assert X14OpenBmcCmd.read_failsafe(1) == ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x02", "0x02"]

    def test_read_duty(self) -> None:
        """Positive unit test for X14OpenBmcCmd.read_duty(). It contains the following steps:
        - call read_duty() for zone 1
        - ASSERT: selector 0x00 and a 0-based zone byte, i.e. the same zone the write addresses by the same
          number, and no duty byte - this selector never writes
        """
        assert X14OpenBmcCmd.read_duty(1) == ["raw", "0x30", "0x70", "0x66", "0x00", "0x01"]

    @pytest.mark.parametrize("zone, level, expected", [
        pytest.param(0, 50, ["raw", "0x30", "0x70", "0x66", "0x01", "0x00", "0x32"], id="zone-0-50pc"),
        pytest.param(4, 100, ["raw", "0x30", "0x70", "0x66", "0x01", "0x04", "0x64"], id="zone-4-100pc"),
    ])
    def test_write_duty(self, zone: int, level: int, expected: List[str]) -> None:
        """Positive unit test for X14OpenBmcCmd.write_duty(). It contains the following steps:
        - call write_duty() for the first and the last zone
        - ASSERT: selector 0x01 and a 0-based zone byte, with the duty as a percentage (0x00-0x64)
        """
        assert X14OpenBmcCmd.write_duty(zone, level) == expected

    @pytest.mark.parametrize("enabled, expected", [
        pytest.param(True, ["raw", "0x30", "0x70", "0x66", "0x02", "0x01"], id="on"),
        pytest.param(False, ["raw", "0x30", "0x70", "0x66", "0x02", "0x00"], id="off"),
    ])
    def test_set_manual_all(self, enabled: bool, expected: List[str]) -> None:
        """Positive unit test for X14OpenBmcCmd.set_manual_all(). It contains the following steps:
        - call set_manual_all() enabling and disabling
        - ASSERT: selector 0x02 and the flag, i.e. the all-zones shortcut of Part 3.1
        """
        assert X14OpenBmcCmd.set_manual_all(enabled) == expected

    def test_get_supported_modes(self) -> None:
        """Positive unit test for X14OpenBmcCmd.get_supported_modes(). It contains the following steps:
        - call get_supported_modes()
        - ASSERT: the command matches Part 3.1, which returns the supported fan mode bitmask
        """
        assert X14OpenBmcCmd.get_supported_modes() == ["raw", "0x30", "0x45", "0x02"]

    def test_the_two_zone_numberings_do_not_get_aligned(self) -> None:
        """Negative unit test for the zone numbering of X14OpenBmcCmd. It contains the following steps:
        - build the manual mode and duty commands for the same smfc zone
        - ASSERT: the OEM command's zone byte is exactly one higher than the duty command's, for every zone
        - ASSERT: no OEM command ever addresses zone 0x00, which does not exist and returns an error
        """
        f = "TestX14OpenBmcCmd.test_the_two_zone_numberings_do_not_get_aligned"
        for zone in range(X14OpenBmcPlatform.FANCTL_COUNT):
            oem = int(X14OpenBmcCmd.read_manual(zone)[-1], 16)
            duty = int(X14OpenBmcCmd.read_duty(zone)[-1], 16)
            assert oem == duty + 1, f"{f}: zone {zone} numbering"
            assert oem != 0x00, f"{f}: zone {zone} is never addressed as 0x00"


class TestX14OpenBmcBehaviour:
    """Behavioural tests for X14OpenBmcPlatform, driven against the `FakeOpenBmc` model of the board.

    The PlatformSpec matrix and the TestX14OpenBmcPlatform tests above assert which commands the platform
    sends, which pins the wire format but cannot catch a command the board accepts and ignores: the expected
    argv is built the same way the implementation builds it, so both are wrong together. These tests assert
    the state the *board* ends up in instead - which zones are latched, and what duty each zone is running -
    so a command that reaches the BMC and does nothing fails here.
    """

    ZONES = [0, 1]

    @staticmethod
    def _platform(bmc: FakeOpenBmc) -> X14OpenBmcPlatform:
        """Build an X14OpenBmcPlatform driven against the modelled board."""
        return X14OpenBmcPlatform(PlatformName.GENERIC_X14, bmc)

    def test_start_latches_exactly_the_controlled_zones(self) -> None:
        """Positive unit test for X14OpenBmcPlatform.start() method. It contains the following steps:
        - build a five-zone modelled board and a platform driven against it
        - invoke start() for zones 0 and 2
        - ASSERT: the board reports zones 0 and 2 latched, i.e. the OEM command reached it and took effect
        - ASSERT: no other zone is latched. Latching a zone smfc does not drive would freeze it at its
          current duty with nothing regulating it
        - ASSERT: the base fan mode was never written; on this stack that would clear manual mode everywhere
        """
        f = "TestX14OpenBmcBehaviour.test_start_latches_exactly_the_controlled_zones"
        bmc = FakeOpenBmc()
        self._platform(bmc).start([0, 2])
        assert bmc.latched_zones == [0, 2], f"{f}: latched zones"
        assert bmc.fan_mode_writes == 0, f"{f}: base fan mode untouched"

    def test_duty_reaches_the_fans_of_a_latched_zone(self) -> None:
        """Positive unit test for X14OpenBmcPlatform.set_fan_level() method. It contains the following steps:
        - build a modelled board whose automatic curve holds every zone at 30%
        - latch zone 1 with start(), then write 40% to it
        - ASSERT: the board's zone 1 is running at 40%, i.e. the duty write moved the fans. A write sent
          with the read selector is accepted by the BMC and changes nothing, which this catches
        - ASSERT: get_fan_level() reads the same 40% back from the board
        - ASSERT: the untouched zone 0 is still on the automatic curve
        """
        f = "TestX14OpenBmcBehaviour.test_duty_reaches_the_fans_of_a_latched_zone"
        bmc = FakeOpenBmc(auto_duty=30)
        platform = self._platform(bmc)
        platform.start([1])
        platform.set_fan_level(1, 40)
        assert bmc.duty[1] == 40, f"{f}: duty of the latched zone"
        assert platform.get_fan_level(1) == 40, f"{f}: duty read back"
        assert bmc.duty[0] == 30, f"{f}: uncontrolled zone left alone"

    def test_duty_does_not_hold_without_manual_mode(self) -> None:
        """Negative unit test for X14OpenBmcPlatform.set_fan_level() method. It contains the following steps:
        - build a modelled board whose automatic curve holds every zone at 30%
        - write 40% to zone 1 without latching manual mode first
        - ASSERT: the board reports zone 1 back at 30%, because the automatic control loop reclaims every
          unlatched zone within about a second. The duty write is not the lever, the manual mode flag is
        """
        f = "TestX14OpenBmcBehaviour.test_duty_does_not_hold_without_manual_mode"
        bmc = FakeOpenBmc(auto_duty=30)
        platform = self._platform(bmc)
        platform.set_fan_level(1, 40)
        assert platform.get_fan_level(1) == 30, f"{f}: automatic control took the zone back"

    def test_set_multiple_fan_levels_reaches_every_zone(self) -> None:
        """Positive unit test for X14OpenBmcPlatform.set_multiple_fan_levels() method. It contains the steps:
        - build a modelled board and latch zones 0, 1 and 2
        - write 60% to all three in one call
        - ASSERT: all three zones are running at 60% on the board
        - ASSERT: the zones that were not written are still on the automatic curve
        """
        f = "TestX14OpenBmcBehaviour.test_set_multiple_fan_levels_reaches_every_zone"
        bmc = FakeOpenBmc(auto_duty=30)
        platform = self._platform(bmc)
        platform.start([0, 1, 2])
        platform.set_multiple_fan_levels([0, 1, 2], 60)
        assert [bmc.duty[z] for z in (0, 1, 2)] == [60, 60, 60], f"{f}: written zones"
        assert [bmc.duty[z] for z in (3, 4)] == [30, 30], f"{f}: untouched zones"

    def test_check_fan_mode_sees_the_board_clear_the_latch(self) -> None:
        """Negative unit test for X14OpenBmcPlatform.check_fan_mode() method. It contains the following steps:
        - build a modelled board, latch zones 0 and 1, and confirm the platform reports OK
        - clear zone 1's manual mode flag on the board, as a BMC restart or a fan mode change from another
          interface does
        - ASSERT: check_fan_mode() reports ControlState.LOST, i.e. the loss is observed on the board and not
          merely inferred from what smfc last wrote
        - ASSERT: the detail names zone 1 and not zone 0, so the log points at the zone that was taken away
        """
        f = "TestX14OpenBmcBehaviour.test_check_fan_mode_sees_the_board_clear_the_latch"
        bmc = FakeOpenBmc()
        platform = self._platform(bmc)
        platform.start(self.ZONES)
        assert platform.check_fan_mode(self.ZONES).state == ControlState.OK, f"{f}: latched"
        bmc.manual[1] = False
        status = platform.check_fan_mode(self.ZONES)
        assert status.state == ControlState.LOST, f"{f}: latch cleared"
        assert "[1]" in status.detail, f"{f}: detail names the lost zone"

    def test_start_reacquires_a_zone_the_board_took_back(self) -> None:
        """Positive unit test for X14OpenBmcPlatform.start() method as the recovery path. It contains the
        steps:
        - build a modelled board, latch zones 0 and 1 and drive them to 60%
        - clear both manual mode flags on the board, so the automatic curve reclaims the zones
        - invoke start() again, as `Service` does on a lost control state, and re-apply the level
        - ASSERT: both zones are latched again, i.e. start() is idempotent and usable as the recovery path
        - ASSERT: both zones are back at 60%, so recovery restores the duty and not only the flag
        """
        f = "TestX14OpenBmcBehaviour.test_start_reacquires_a_zone_the_board_took_back"
        bmc = FakeOpenBmc(auto_duty=30)
        platform = self._platform(bmc)
        platform.start(self.ZONES)
        platform.set_multiple_fan_levels(self.ZONES, 60)
        bmc.manual = {z: False for z in range(bmc.zones)}
        platform.start(self.ZONES)
        platform.set_multiple_fan_levels(self.ZONES, 60)
        assert bmc.latched_zones == self.ZONES, f"{f}: re-latched"
        assert [bmc.duty[z] for z in self.ZONES] == [60, 60], f"{f}: duty restored"

    def test_a_failsafe_zone_ignores_the_duty(self) -> None:
        """Negative unit test for X14OpenBmcPlatform.set_fan_level() method. It contains the following steps:
        - build a modelled board and latch zone 1
        - trip zone 1 into failsafe, as the BMC does on a fan failure or a missing thermal sensor
        - write 40% to it
        - ASSERT: the zone reads back 100%, not 40%: failsafe outranks manual mode, so the duty smfc writes
          is discarded while the trip lasts and re-writing it cannot win the zone back
        """
        f = "TestX14OpenBmcBehaviour.test_a_failsafe_zone_ignores_the_duty"
        bmc = FakeOpenBmc()
        platform = self._platform(bmc)
        platform.start([1])
        bmc.failsafe[1] = True
        platform.set_fan_level(1, 40)
        assert platform.get_fan_level(1) == 100, f"{f}: zone pinned by failsafe"

    @pytest.mark.parametrize("level", [50, -1], ids=["with-exit-level", "without-exit-level"])
    def test_end_releases_every_zone(self, level: int) -> None:
        """Positive unit test for X14OpenBmcPlatform.end() method. It contains the following steps:
        - build a modelled board and latch zones 0 and 1
        - invoke end() for both zones, once with an exit level and once with exit_level=-1
        - ASSERT: no zone is latched on the board afterwards. The release runs on every exit path; a latch
          left armed freezes the zones at their last duty with nothing regulating them
        - ASSERT: the board is back under automatic control, i.e. the zones return to the automatic curve
        """
        f = "TestX14OpenBmcBehaviour.test_end_releases_every_zone"
        bmc = FakeOpenBmc(auto_duty=30)
        platform = self._platform(bmc)
        platform.start(self.ZONES)
        platform.end(self.ZONES, level)
        assert bmc.latched_zones == [], f"{f}: nothing latched"
        assert platform.get_fan_level(0) == 30, f"{f}: automatic control resumed"
        expected = [level] * len(self.ZONES) if level >= 0 else [30] * len(self.ZONES)
        assert [bmc.duty_at_release[z] for z in self.ZONES] == expected, f"{f}: exit level in force at release"


    def test_duty_reads_back_exactly_what_was_written(self) -> None:
        """Positive unit test for X14OpenBmcPlatform.get_fan_level() method. It contains the following steps:
        - build a modelled board and latch every zone
        - write each duty in turn and read it straight back
        - ASSERT: every duty reads back as the exact value written, including ones that are not multiples of
          20. The read addresses the same 0-based zone as the write, so nothing is converted on the way and
          the redundant-write check of the CONST controller matches instead of rewriting on every poll
        """
        f = "TestX14OpenBmcBehaviour.test_duty_reads_back_exactly_what_was_written"
        bmc = FakeOpenBmc()
        platform = self._platform(bmc)
        platform.start([0])
        for level in (7, 33, 50, 67, 99, 100):
            platform.set_fan_level(0, level)
            assert platform.get_fan_level(0) == level, f"{f}: {level}% round-trip"

    def test_start_rejects_a_zone_the_board_does_not_have(self) -> None:
        """Negative unit test for X14OpenBmcPlatform.start() method. It contains the following steps:
        - build a modelled board with two zones and a platform driven against it
        - invoke start() for zones 0 and 2, i.e. one zone beyond what the board has
        - ASSERT: start() raises ValueError, because the zone count is discovered from the board rather than
          assumed from the firmware bound
        - ASSERT: the message names the offending zone and the number of zones the board really has
        - ASSERT: nothing was latched, so a misconfiguration never leaves the board half taken over
        """
        f = "TestX14OpenBmcBehaviour.test_start_rejects_a_zone_the_board_does_not_have"
        bmc = FakeOpenBmc(zones=2)
        platform = self._platform(bmc)
        with pytest.raises(ValueError) as excinfo:
            platform.start([0, 2])
        assert "[2]" in str(excinfo.value), f"{f}: message names the zone"
        assert "2 zone(s)" in str(excinfo.value), f"{f}: message names the discovered count"
        assert bmc.latched_zones == [], f"{f}: nothing latched"

    def test_zone_count_is_probed_once(self) -> None:
        """Positive unit test for X14OpenBmcPlatform.zone_count property. It contains the following steps:
        - build a modelled board with three zones and a platform driven against it
        - read the zone count twice
        - ASSERT: the discovered count matches the board
        - ASSERT: the board saw the probe only once. It runs on every recovery path through start(), so a
          probe per call would add an IPMI read per zone to every lost-control poll
        """
        f = "TestX14OpenBmcBehaviour.test_zone_count_is_probed_once"
        bmc = FakeOpenBmc(zones=3)
        platform = self._platform(bmc)
        assert platform.zone_count == 3, f"{f}: discovered zone count"
        before = len(bmc.commands)
        assert platform.zone_count == 3, f"{f}: cached zone count"
        assert len(bmc.commands) == before, f"{f}: probed only once"

    def test_supported_fan_modes_come_from_the_board(self) -> None:
        """Positive unit test for X14OpenBmcPlatform.valid_fan_modes property. It contains the following steps:
        - build a modelled board reporting the FullSpeed, Performance and Silent bitmask of Part 3.1
        - read the supported fan modes, then try to write a mode outside them
        - ASSERT: the modes decoded from the little-endian bitmask are exactly bits 1, 10 and 11
        - ASSERT: set_fan_mode() rejects a mode the board does not have. Such a mode is otherwise accepted
          silently and reads back correctly while a different fan table is loaded
        """
        f = "TestX14OpenBmcBehaviour.test_supported_fan_modes_come_from_the_board"
        bmc = FakeOpenBmc()
        bmc.SUPPORTED_MODES = 0x0C02
        platform = self._platform(bmc)
        assert platform.valid_fan_modes == [1, 10, 11], f"{f}: decoded bitmask"
        with pytest.raises(ValueError):
            platform.set_fan_mode(FanMode.STANDARD)

    def test_check_fan_mode_reports_a_failsafe_trip(self) -> None:
        """Negative unit test for X14OpenBmcPlatform.check_fan_mode() method. It contains the following steps:
        - build a modelled board, latch zones 0 and 1, and trip zone 1 into failsafe
        - poll check_fan_mode() until the cause has persisted
        - ASSERT: the state is LOST although manual mode is still latched in both zones, which is the case
          the manual mode flag alone cannot show
        - ASSERT: once the trip has persisted, the detail names the zone and says that restoring fan control
          cannot recover it, so the log does not send the user after a lever that is already in place
        - ASSERT: the detail also names the tacho cause, because on a board whose fans turn slower than the
          BMC can measure a healthy fan trips failsafe by itself
        """
        f = "TestX14OpenBmcBehaviour.test_check_fan_mode_reports_a_failsafe_trip"
        bmc = FakeOpenBmc()
        platform = self._platform(bmc)
        platform.start(self.ZONES)
        bmc.failsafe[1] = True
        for _ in range(X14OpenBmcPlatform.FAILSAFE_REPORT_AFTER):
            status = platform.check_fan_mode(self.ZONES)
        assert bmc.latched_zones == self.ZONES, f"{f}: manual mode still latched"
        assert status.state == ControlState.LOST, f"{f}: failsafe is a loss of control"
        assert "[1]" in status.detail, f"{f}: detail names the pinned zone"
        assert "cannot recover it" in status.detail, f"{f}: detail says re-acquiring will not help"
        assert "0 RPM" in status.detail, f"{f}: detail names the usual trigger"

    def test_check_fan_mode_recovers_when_the_failsafe_trip_clears(self) -> None:
        """Positive unit test for X14OpenBmcPlatform.check_fan_mode() method. It contains the following steps:
        - build a modelled board, latch zones 0 and 1, trip zone 1 into failsafe and poll once
        - clear the trip on the board and poll again
        - ASSERT: the state is OK again, i.e. a failsafe trip is not sticky in smfc's own bookkeeping
        - ASSERT: a later trip has to persist again before the cause is named, so a zone that trips
          intermittently does not carry a stale count into its next trip
        """
        f = "TestX14OpenBmcBehaviour.test_check_fan_mode_recovers_when_the_failsafe_trip_clears"
        bmc = FakeOpenBmc()
        platform = self._platform(bmc)
        platform.start(self.ZONES)
        bmc.failsafe[1] = True
        platform.check_fan_mode(self.ZONES)
        bmc.failsafe[1] = False
        assert platform.check_fan_mode(self.ZONES).state == ControlState.OK, f"{f}: trip cleared"
        bmc.failsafe[1] = True
        assert "cannot recover it" not in platform.check_fan_mode(self.ZONES).detail, f"{f}: count restarted"

    def test_a_zero_duty_never_reaches_the_fans(self) -> None:
        """Negative unit test for X14OpenBmcPlatform.set_fan_level() method. It contains the following steps:
        - build a modelled board and latch zones 0 and 1
        - write a duty of 0% to one zone and to both zones at once
        - ASSERT: the board runs at the 5% floor, not at 0%. `min_level=0` is a legal configuration, and a
          manual duty write has no floor of its own: the 15% floor belongs to the automatic control a
          latched zone is no longer under, so a written 0 would stop the fans with nothing regulating them
        """
        f = "TestX14OpenBmcBehaviour.test_a_zero_duty_never_reaches_the_fans"
        bmc = FakeOpenBmc()
        platform = self._platform(bmc)
        platform.start(self.ZONES)
        platform.set_fan_level(0, 0)
        platform.set_multiple_fan_levels(self.ZONES, 0)
        assert [bmc.duty[z] for z in self.ZONES] == [5, 5], f"{f}: duty floor"


class TestX14AtenPlatform:
    """Unit tests for the behaviour that is unique to X14AtenPlatform and therefore not covered by the shared
    PlatformSpec matrix: the two duty read-back paths the `accepted()` set absorbs, the duty-based bypass
    watchdog that replaces a readable lever, the 5% write floor and the two fatal start() completion codes."""

    ZONES = [0, 1]

    @staticmethod
    def _platform(mock_exec: MagicMock) -> X14AtenPlatform:
        """Build an X14AtenPlatform around the given mock exec callback."""
        return X14AtenPlatform(PlatformName.GENERIC_X14, mock_exec)

    @staticmethod
    def _replies(fan_mode: str, duties: List[str]) -> Callable:
        """An exec callback answering the fan mode read, then one duty read per zone, in check order."""
        outputs = [fan_mode] + duties
        return lambda args: subprocess.CompletedProcess(
            [], returncode=0, stdout=outputs.pop(0) if outputs else " 00")

    @pytest.mark.parametrize("level, expected", [
        (50, {49, 50}), (20, {20}), (100, {100}), (0, {0, 4, 5}), (120, {100}), (5, {4, 5}),
    ], ids=["50", "20", "100", "0", "120", "5"])
    def test_accepted(self, level: int, expected: set) -> None:
        """Positive unit test for X14AtenPlatform.accepted() method. It contains the following steps:
        - call accepted() with the duty levels of the guide's Part 4.4 worked examples
        - ASSERT: the returned set holds every duty byte the BMC may report back for that level, i.e. the
          truncated PWM read-back, the clamped write and the raw write. ATEN firmware has two duty paths and
          the board name does not say which is active, so a single computed expectation would make every duty
          that is not a multiple of 20 mismatch on every poll on one of them - a permanent false "control lost"
        - ASSERT: 100 and 20 collapse to a single value, i.e. the two paths agree at multiples of 20
        """
        f = "TestX14AtenPlatform.test_accepted"
        assert X14AtenPlatform.accepted(level) == expected, f"{f}: accepted({level})"

    @pytest.mark.parametrize("level", [50, 20, 100, 33, 5], ids=["50", "20", "100", "33", "5"])
    @pytest.mark.parametrize("path", ["pwm", "percent"])
    def test_check_fan_mode_ok_on_both_duty_paths(self, level: int, path: str, mock_exec: MagicMock) -> None:
        """Positive unit test for X14AtenPlatform.check_fan_mode() method. It contains the following steps:
        - build the platform and write `level` to both zones, which records what the BMC may report back
        - mock the ipmitool exec callback to answer the fan mode read and then one duty read per zone, with
          the read-back of the PWM duty path (truncated) or of the percent path (exact)
        - invoke check_fan_mode() for both zones
        - ASSERT: the state is OK on *both* duty paths for every level, which is the whole point of comparing
          against a set: a fixture modelling only one path could not fail a regression that reintroduced a
          single expectation
        - ASSERT: the status is confirmed and the base fan mode is cached for the snapshot
        """
        f = "TestX14AtenPlatform.test_check_fan_mode_ok_on_both_duty_paths"
        platform = self._platform(mock_exec)
        platform.set_multiple_fan_levels(self.ZONES, level)
        pwm = ((max(5, level) * 255) // 100) * 100 // 255
        readback = f" {(pwm if path == 'pwm' else max(5, level)):02x}"
        mock_exec.side_effect = self._replies(" 01", [readback, readback])
        status = platform.check_fan_mode(self.ZONES)
        assert status.state == ControlState.OK, f"{f}: {path} read-back {readback} for level {level}"
        assert status.confirmed is True, f"{f}: confirmed"
        assert status.fan_mode == FanMode.FULL, f"{f}: fan mode cached"

    def test_check_fan_mode_before_first_write(self, mock_exec: MagicMock) -> None:
        """Positive unit test for X14AtenPlatform.check_fan_mode() method. It contains the following steps:
        - build the platform and invoke check_fan_mode() without writing any duty first
        - ASSERT: the state is OK - before the first duty write there is nothing to compare against, and
          Service writes levels on every iteration so that window is a single poll
        - ASSERT: only the base fan mode is read, i.e. no duty read is issued for a zone with no expectation
        """
        f = "TestX14AtenPlatform.test_check_fan_mode_before_first_write"
        mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=" 01")
        platform = self._platform(mock_exec)
        status = platform.check_fan_mode(self.ZONES)
        assert status.state == ControlState.OK, f"{f}: state"
        assert mock_exec.call_args_list == [call(GET_FAN_MODE_CMD)], f"{f}: only the fan mode is read"

    def test_check_fan_mode_lost(self, mock_exec: MagicMock) -> None:
        """Negative unit test for X14AtenPlatform.check_fan_mode() method. It contains the following steps:
        - build the platform and write 50% to both zones
        - mock the ipmitool exec callback so zone 1 reads back a duty outside the accepted set, i.e. the BMC's
          automatic fan control loop resumed and overwrote it (the bypass flag itself cannot be read)
        - invoke check_fan_mode() for both zones
        - ASSERT: the state is LOST and confirmed, so Service counts it as drift and re-arms the bypass
        - ASSERT: ControlStatus.detail names the offending zone and the duty that was read back
        """
        f = "TestX14AtenPlatform.test_check_fan_mode_lost"
        platform = self._platform(mock_exec)
        platform.set_multiple_fan_levels(self.ZONES, 50)
        mock_exec.side_effect = self._replies(" 01", [" 31", " 4b"])
        status = platform.check_fan_mode(self.ZONES)
        assert status.state == ControlState.LOST, f"{f}: state"
        assert status.confirmed is True, f"{f}: confirmed"
        assert "1=75%" in status.detail, f"{f}: detail names the zone and duty: {status.detail}"

    def test_check_fan_mode_unreadable(self, mock_exec: MagicMock) -> None:
        """Negative unit test for X14AtenPlatform.check_fan_mode() method. It contains the following steps:
        - build the platform, write 50% to both zones, then make every ipmitool call fail
        - invoke check_fan_mode() for both zones
        - ASSERT: the error is not propagated, the state is LOST but not confirmed, so Service re-arms the
          bypass without counting drift or exiting
        - ASSERT: ControlStatus.fan_mode is -1, so the caller leaves the cached fan mode untouched
        """
        f = "TestX14AtenPlatform.test_check_fan_mode_unreadable"
        platform = self._platform(mock_exec)
        platform.set_multiple_fan_levels(self.ZONES, 50)
        mock_exec.side_effect = IpmiError("ipmitool error (1): Unable to establish IPMI v2 session.", None)
        status = platform.check_fan_mode(self.ZONES)
        assert status.state == ControlState.LOST, f"{f}: state"
        assert status.confirmed is False, f"{f}: not confirmed"
        assert status.fan_mode == -1, f"{f}: fan mode untouched"

    def test_check_fan_mode_fan_failure_hint(self, mock_exec: MagicMock) -> None:
        """Negative unit test for X14AtenPlatform.check_fan_mode() method. It contains the following steps:
        - build the platform and write 50% to zone 0
        - mock the ipmitool exec callback so zone 0 reads back 100% on every poll
        - invoke check_fan_mode() three times in a row
        - ASSERT: every pass reports LOST, because the duty is not the one smfc wrote
        - ASSERT: the first two passes report the plain overwrite reason
        - ASSERT: from the third pass on the detail names a fan failure as the likely cause without asserting
          it: the boards differ in whether fan failure outranks the bypass, and on those where it does,
          re-arming can never win the zone back - without this the log repeats "control lost" forever and
          points the user at the wrong thing
        """
        f = "TestX14AtenPlatform.test_check_fan_mode_fan_failure_hint"
        platform = self._platform(mock_exec)
        platform.set_fan_level(0, 50)
        details = []
        for _ in range(3):
            mock_exec.side_effect = self._replies(" 01", [" 64"])
            status = platform.check_fan_mode([0])
            assert status.state == ControlState.LOST, f"{f}: state"
            details.append(status.detail)
        assert "fan failure" not in details[0], f"{f}: first pass: {details[0]}"
        assert "fan failure" not in details[1], f"{f}: second pass: {details[1]}"
        assert "IPMI zone 0 is pinned at 100%" in details[2], f"{f}: third pass: {details[2]}"
        assert "most likely a fan failure" in details[2], f"{f}: third pass names the likely cause"

    def test_start_lockdown(self, mock_exec: MagicMock) -> None:
        """Negative unit test for X14AtenPlatform.start() method. It contains the following steps:
        - mock the ipmitool exec callback to reject the bypass command with completion code 0xD4
        - build the platform and invoke start() for both zones
        - ASSERT: start() raises with a message naming System Lockdown, because the fix is in the BMC web UI
          and nothing in smfc can work around it
        """
        f = "TestX14AtenPlatform.test_start_lockdown"
        mock_exec.side_effect = IpmiError("ipmitool error (1): rsp=0xd4.", 0xD4)
        platform = self._platform(mock_exec)
        with pytest.raises(RuntimeError) as excinfo:
            platform.start(self.ZONES)
        assert "System Lockdown" in str(excinfo.value), f"{f}: message: {excinfo.value}"

    def test_start_no_duty_control(self, mock_exec: MagicMock) -> None:
        """Negative unit test for X14AtenPlatform.start() method. It contains the following steps:
        - mock the ipmitool exec callback to reject the bypass command with completion code 0xCC
        - build the platform and invoke start() for both zones
        - ASSERT: start() raises with its own message saying this firmware build implements no fan duty
          control at all. The Part 1 stack probe identifies the *stack*, not that duty control exists, so
          this is the first point where such a build can be recognised
        - ASSERT: the message is distinct from the System Lockdown one, because the only recourse here is a
          firmware change and a generic ipmitool error would send the user hunting the wrong thing
        """
        f = "TestX14AtenPlatform.test_start_no_duty_control"
        mock_exec.side_effect = IpmiError("ipmitool error (1): rsp=0xcc.", 0xCC)
        platform = self._platform(mock_exec)
        with pytest.raises(RuntimeError) as excinfo:
            platform.start(self.ZONES)
        assert "no IPMI fan duty control" in str(excinfo.value), f"{f}: message: {excinfo.value}"
        assert "System Lockdown" not in str(excinfo.value), f"{f}: distinct from the lockdown message"

    def test_start_other_error_propagates(self, mock_exec: MagicMock) -> None:
        """Negative unit test for X14AtenPlatform.start() method. It contains the following steps:
        - mock the ipmitool exec callback to fail with no IPMI completion code, i.e. an unreachable BMC
        - build the platform and invoke start() for both zones
        - ASSERT: the original error propagates unchanged, so an unreachable BMC is never reported as a
          firmware limitation
        """
        f = "TestX14AtenPlatform.test_start_other_error_propagates"
        mock_exec.side_effect = IpmiError("ipmitool error (1): Unable to establish IPMI v2 session.", None)
        platform = self._platform(mock_exec)
        with pytest.raises(RuntimeError) as excinfo:
            platform.start(self.ZONES)
        assert "Unable to establish IPMI v2 session" in str(excinfo.value), f"{f}: message: {excinfo.value}"

    @pytest.mark.parametrize("level", [0, 1, 4], ids=["0", "1", "4"])
    def test_never_writes_below_the_floor(self, level: int, mock_exec: MagicMock) -> None:
        """Positive unit test for X14AtenPlatform.set_fan_level() method. It contains the following steps:
        - build the platform and invoke set_fan_level() and set_multiple_fan_levels() with a duty below 5%
        - ASSERT: the BMC receives 0x05, never 0x00. Config permits `min_level=0`, and on the PWM duty path
          that is harmless because the firmware clamps it itself - but the percent path has no floor, so a
          written 0x00 may reach the fans as a real 0% with the BMC thermal loop suspended by our own bypass
        - ASSERT: the accepted read-back set is the one of the *clamped* value, so the clamp and the watchdog
          stay consistent by construction
        """
        f = "TestX14AtenPlatform.test_never_writes_below_the_floor"
        platform = self._platform(mock_exec)
        platform.set_fan_level(0, level)
        assert mock_exec.call_args_list[-1] == call(_generic_set_cmd(0, 5)), f"{f}: set_fan_level({level})"
        platform.set_multiple_fan_levels([1], level)
        assert mock_exec.call_args_list[-1] == call(_generic_set_cmd(1, 5)), f"{f}: multiple({level})"
        assert platform.accepted(5) == {4, 5}, f"{f}: accepted set of the clamped value"

    def test_end_exit_level_none_still_releases(self, mock_exec: MagicMock) -> None:
        """Positive unit test for X14AtenPlatform.end() method. It contains the following steps:
        - mock the ipmitool exec callback to record the sequence of issued commands
        - build the platform and invoke end() for both zones with the exit level -1 (`exit_level=-1`)
        - ASSERT: no fan level is written, because -1 means smfc leaves the fan levels alone
        - ASSERT: the global bypass is released all the same. It is global, so a bypass that is never released
          leaves *every* zone on the board frozen at its last duty with nothing regulating it
        """
        f = "TestX14AtenPlatform.test_end_exit_level_none_still_releases"
        platform = self._platform(mock_exec)
        platform.end(self.ZONES, -1)
        assert mock_exec.call_args_list == [call(_ATEN_BYPASS_OFF)], f"{f}: calls"

    def test_end_applies_level_before_release(self, mock_exec: MagicMock) -> None:
        """Positive unit test for X14AtenPlatform.end() method. It contains the following steps:
        - mock the ipmitool exec callback to record the sequence of issued commands
        - build the platform and invoke end() for both zones with the exit level 50%
        - ASSERT: the exit level is written to both zones and only then is the bypass released - releasing
          first would let the automatic loop overwrite the level immediately
        """
        f = "TestX14AtenPlatform.test_end_applies_level_before_release"
        platform = self._platform(mock_exec)
        platform.end(self.ZONES, 50)
        expected = [call(_generic_set_cmd(0, 50)), call(_generic_set_cmd(1, 50)), call(_ATEN_BYPASS_OFF)]
        assert mock_exec.call_args_list == expected, f"{f}: calls"

    def test_end_releases_even_if_the_level_write_fails(self, mock_exec: MagicMock) -> None:
        """Negative unit test for X14AtenPlatform.end() method. It contains the following steps:
        - mock the ipmitool exec callback so the exit level write fails but every other command succeeds
        - build the platform and invoke end() for both zones with the exit level 50%
        - ASSERT: end() propagates the level write error, so the caller can log it
        - ASSERT: the global bypass is released all the same. The exit level is optional; the release is not,
          and because the bypass is global, skipping it would leave *every* zone on the board - not only the
          configured ones - frozen at its last duty with the BMC's own thermal loop suspended
        """
        f = "TestX14AtenPlatform.test_end_releases_even_if_the_level_write_fails"
        ok = subprocess.CompletedProcess([], returncode=0, stdout="")

        def exec_fn(args):
            if args[:5] == ["raw", "0x30", "0x70", "0x66", "0x01"]:
                raise IpmiError("ipmitool error (1): Unable to establish IPMI v2 session.", None)
            return ok

        mock_exec.side_effect = exec_fn
        platform = self._platform(mock_exec)
        with pytest.raises(RuntimeError):
            platform.end(self.ZONES, 50)
        assert mock_exec.call_args_list[-1] == call(_ATEN_BYPASS_OFF), f"{f}: bypass released last"

    def test_never_writes_the_base_fan_mode(self, mock_exec: MagicMock) -> None:
        """Positive unit test for X14AtenPlatform.start() method. It contains the following steps:
        - mock the ipmitool exec callback to record the sequence of issued commands
        - build the platform and invoke start() for both zones
        - ASSERT: exactly one command is issued, the global bypass, and it returns False so no fan_mode_delay
          is due
        - ASSERT: no set-fan-mode command is issued. The base fan mode persists across a BMC restart while the
          bypass does not, so a board left in Full Speed would come back at 100% with nothing to stop it
        """
        f = "TestX14AtenPlatform.test_never_writes_the_base_fan_mode"
        platform = self._platform(mock_exec)
        assert platform.start(self.ZONES) is False, f"{f}: no fan mode written"
        assert mock_exec.call_args_list == [call(_ATEN_BYPASS_ON)], f"{f}: calls"


# End.
