#
#   platform.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   Platform abstraction for platform-specific IPMI raw commands.
#
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, List, Optional


def validate_input_range(value: int, valrepr: str, minval: int, maxval: int) -> None:
    """Validate that a value lies within the inclusive interval [minval, maxval].
    Args:
        value (int): The value to validate
        valrepr (str): A string representation of what the value is
        minval (int): The minimum inclusive value within the range to test
        maxval (int): The maximum inclusive value within the range to test
    Raises:
        ValueError: value does not lie within [minval, maxval].
    """
    if minval > value or value > maxval:
        raise ValueError(f"Invalid value: {valrepr} ({value}). Valid range is [{minval},{maxval}].")


class IpmiError(RuntimeError):
    """An `ipmitool` failure, carrying the IPMI completion code when the BMC returned one.

    It subclasses `RuntimeError` so that every existing `except RuntimeError` keeps catching it
    unchanged. The completion code is what separates a command the BMC *rejected* (e.g. 0xC1 - this
    command does not exist on this BMC stack) from an unreachable BMC, a wedged `/dev/ipmi0` or a
    `sudo` problem, all of which are otherwise indistinguishable by exception type. The X14/H14 stack
    probe depends on that distinction: only `rsp=0xc1` means ATEN, and a wrong stack applies the wrong
    lever to the fans (see `doc/X14H14_MANUAL_FANCONTROL.md`, Part 1.3).
    """

    completion_code: Optional[int]   # IPMI completion code, None when ipmitool failed for another reason

    def __init__(self, message: str, completion_code: Optional[int] = None) -> None:
        """Initialize the error with a message and the optional IPMI completion code.
        Args:
            message (str): the error message
            completion_code (Optional[int]): IPMI completion code the BMC returned, if any
        """
        super().__init__(message)
        self.completion_code = completion_code


class FanMode(IntEnum):
    """The different fan modes supported by Supermicro platforms.
    The integers represent the hex values propagated to ipmitool raw commands.
    """
    STANDARD = 0
    FULL = 1
    OPTIMAL = 2
    PUE = 3
    HEAVY_IO = 4


def get_fan_mode_name(mode: int) -> str:
    """Get the name of the specified IPMI fan mode.
    Args:
        mode (int): fan mode
    Returns:
        str: name of the fan mode ('UNKNOWN', 'STANDARD', 'FULL', 'OPTIMAL', 'PUE', 'HEAVY IO')
    """
    fan_mode_name: str  # Name of the fan mode

    fan_mode_name = "UNKNOWN"
    if mode == FanMode.STANDARD:
        fan_mode_name = "STANDARD"
    elif mode == FanMode.FULL:
        fan_mode_name = "FULL"
    elif mode == FanMode.OPTIMAL:
        fan_mode_name = "OPTIMAL"
    elif mode == FanMode.PUE:
        fan_mode_name = "PUE"
    elif mode == FanMode.HEAVY_IO:
        fan_mode_name = "HEAVY IO"
    return fan_mode_name


class ControlState(IntEnum):
    """The result of a Platform.check_fan_mode() call: is smfc still in control of the fans?

    There is no UNKNOWN state on purpose: if the platform state cannot be read at all, smfc cannot
    demonstrate that it is in control, so that case is reported as LOST (with `confirmed=False`) and the
    caller re-acquires control instead of skipping the cycle.
    """
    OK = 0      # smfc is in control of the fans
    LOST = 1    # control was lost: mode drifted, manual flag cleared, or the state could not be read


@dataclass(frozen=True)
class ControlStatus:
    """The outcome of a Platform.check_fan_mode() call."""
    state: ControlState     # OK or LOST
    detail: str             # Human-readable reason, logged verbatim by Service
    fan_mode: int           # Observed base fan mode, for the snapshot cache (-1 = not read)
    confirmed: bool = True  # False when the state could not be read at all (BMC error)


class Platform(ABC):
    """Abstract base class for platforms with different ipmitool raw functionality.

    The class carries the majority policy of Supermicro boards: "the BMC is in FULL fan mode" is what
    "smfc controls the fans" means, so `start()`, `check_fan_mode()`, `end()`, `get_fan_mode()` and
    `set_fan_mode()` are implemented here and inherited by most platforms. Concrete subclasses implement the
    genuinely board-specific fan level commands, and override the control methods only where the board
    behaves differently (X14 uses an explicit per-zone manual mode instead of FULL).
    """

    _name: str
    _exec: Callable[[List[str]], subprocess.CompletedProcess]
    valid_fan_modes: List[int] = [FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO]
    ENFORCES_FULL_MODE: bool = True     # False on platforms where FULL fan mode is not the controlled state

    def __init__(self, name: str, exec_ipmitool: Callable[[List[str]], subprocess.CompletedProcess]) -> None:
        """Initialize the Platform with a name and an ipmitool execution callback.

        Args:
            name (str): platform name (e.g. from BMC product name or config)
            exec_ipmitool (Callable): function that executes ipmitool commands
        """
        self._name = name
        self._exec = exec_ipmitool

    @property
    def name(self) -> str:
        """The name of the platform."""
        return self._name

    def start(self, zones: List[int]) -> bool:  # pylint: disable=unused-argument
        """Acquire (or re-acquire) control of the fans. Called at startup and again on every recovery from a
        lost control state, so it must be idempotent.

        On most platforms being in control means the BMC is in FULL fan mode, so the mode is written only if
        the BMC is not in FULL already: skipping the redundant write avoids a needless `fan_mode_delay` sleep
        (and the momentary fan blip some firmware produces when FULL is re-latched).
        Args:
            zones (List[int]): IPMI zones smfc controls (unused here, needed by platforms with per-zone state)
        Returns:
            bool: True if the fan mode was written, so the caller applies `fan_mode_delay`
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem
            ValueError: output of the ipmitool cannot be interpreted/converted
        """
        if self.get_fan_mode() != FanMode.FULL:
            self.set_fan_mode(FanMode.FULL)
            return True
        return False

    def check_fan_mode(self, zones: List[int]) -> ControlStatus:  # pylint: disable=unused-argument
        """Report whether smfc is still in control of the fans.

        The platform - not the caller - defines what "in control" means. Here it is FULL fan mode. A BMC error
        is not propagated: it is reported as LOST with `confirmed=False`, because an unreadable state is a
        state smfc cannot demonstrate control over.
        Args:
            zones (List[int]): IPMI zones smfc controls (unused here, needed by platforms with per-zone state)
        Returns:
            ControlStatus: the observed control state
        Raises:
            FileNotFoundError: ipmitool cannot be found
        """
        try:
            mode = self.get_fan_mode()
        except (RuntimeError, ValueError) as e:
            return ControlStatus(ControlState.LOST, f"BMC fan mode could not be read: {e}", -1, confirmed=False)
        if mode == FanMode.FULL:
            return ControlStatus(ControlState.OK, "", mode)
        detail = f"BMC fan mode drifted from FULL to {get_fan_mode_name(mode)}"
        return ControlStatus(ControlState.LOST, detail, mode)

    def end(self, zones: List[int], level: int) -> None:
        """Apply the exit fan level and restore the platform state when shutting down.
        Called once at shutdown. The BMC is left in FULL fan mode on most platforms, so the applied level is
        the state the fans keep until something else changes it. The zone list is resolved by the caller (the
        platform is created before the fan controllers exist, so it cannot know the configured zones itself).
        A negative level (`[Ipmi] exit_level=-1`) means "leave the fan levels alone", so no level is
        written - but `end()` is still called, because platforms that hold an explicit control state
        (X14/H14) must release it on every exit path regardless of the exit level. Skipping the release
        would leave the fans frozen at their last duty with nothing regulating them.
        Args:
            zones (List[int]): configured IPMI zones the exit level is applied to
            level (int): fan level in % (0-100), or a negative value to leave the levels unchanged
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem
        """
        if level >= 0:
            self.set_multiple_fan_levels(zones, level)

    def get_fan_mode(self) -> int:
        """Get the current IPMI fan mode.
        Returns:
            int: fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem
            ValueError: output of the ipmitool cannot be interpreted/converted
        """
        r = self._exec(["raw", "0x30", "0x45", "0x00"])
        return int(r.stdout)

    def set_fan_mode(self, mode: int) -> None:
        """Set the IPMI fan mode.
        Args:
            mode (int): fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem
        """
        if mode not in self.valid_fan_modes:
            raise ValueError(f"Invalid value: fan mode ({mode}).")
        self._exec(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])

    @abstractmethod
    def get_fan_level(self, zone: int) -> int:
        """Get the current fan level in a specific IPMI zone.
        Args:
            zone (int): fan zone
        Returns:
            int: fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem
        """

    @abstractmethod
    def set_fan_level(self, zone: int, level: int) -> None:
        """Set the fan level in the specified IPMI zone.
        Args:
            zone (int): IPMI zone
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem
        """

    @abstractmethod
    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        """Set the fan level in multiple IPMI zones.
        Args:
            zone_list (List[int]): List of IPMI zones
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem
        """


# End.
