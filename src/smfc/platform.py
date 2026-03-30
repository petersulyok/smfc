#
#   platform.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   Platform abstraction for platform-specific IPMI raw commands.
#
import subprocess
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Callable, List


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


class FanMode(IntEnum):
    """The different fan modes supported by Supermicro platforms.
    The integers represent the hex values propagated to ipmitool raw commands.
    """
    STANDARD = 0
    FULL = 1
    OPTIMAL = 2
    PUE = 3
    HEAVY_IO = 4


class Platform(ABC):
    """Abstract base class for platforms with different ipmitool raw functionality.
    Concrete subclasses implement platform-specific fan control commands.
    """
    PLATFORM_AUTO: str = "auto"
    PLATFORM_GENERIC: str = "generic"
    PLATFORM_GENERIC_X9: str = "genericx9"

    _name: str
    _exec: Callable[[List[str]], subprocess.CompletedProcess]

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

    @abstractmethod
    def get_fan_mode(self) -> int:
        """Get the current IPMI fan mode.
        Returns:
            int: fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem
            ValueError: output of the ipmitool cannot be interpreted/converted
        """

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
    def set_fan_manual_mode(self) -> None:
        """Set the fan controllers on the platform to accept manual PWM or DC input.
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem
        """

    @abstractmethod
    def set_fan_mode(self, mode: int) -> None:
        """Set the IPMI fan mode.
        Args:
            mode (int): fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
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


def create_platform(platform_name: str, exec_ipmitool: Callable[[List[str]], subprocess.CompletedProcess]) -> Platform:
    """Factory method to create the appropriate Platform object for the given platform name.
    Args:
        platform_name (str): The platform name, one of:
            - 'generic': force the GenericPlatform (X10-X13/H10-H13)
            - 'genericx9': force the GenericX9Platform (X9 motherboards)
            - 'X10QBi': force the X10QBi platform
            - any other string: looked up in the platform registry, falls back to GenericPlatform
        exec_ipmitool (Callable): Function that executes ipmitool commands
    Returns:
        Platform: The platform-specific implementation (defaults to GenericPlatform)
    """
    from smfc.generic import GenericPlatform
    from smfc.genericx9 import GenericX9Platform
    from smfc.x10qbi import X10QBi

    platform_factory = {
        Platform.PLATFORM_GENERIC: GenericPlatform,
        Platform.PLATFORM_GENERIC_X9: GenericX9Platform,
        "X10QBi": X10QBi,
    }
    return platform_factory.get(platform_name, GenericPlatform)(platform_name, exec_ipmitool)


# End.
