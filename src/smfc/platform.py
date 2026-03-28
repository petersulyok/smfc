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


class GenericPlatform(Platform):
    """Platform implementation for the most common Supermicro X10/X11/X12/X13 motherboards."""

    valid_fan_modes: List[FanMode] = [FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO]

    def get_fan_mode(self) -> int:
        r = self._exec(["raw", "0x30", "0x45", "0x00"])
        return int(r.stdout)

    def get_fan_level(self, zone: int) -> int:
        validate_input_range(zone, "zone", 0, 100)
        r = self._exec(["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:x}"])
        return int(r.stdout, 16)

    def set_fan_manual_mode(self) -> None:
        pass

    def set_fan_mode(self, mode: int) -> None:
        if mode not in self.valid_fan_modes:
            raise ValueError(f"Invalid value: fan mode ({mode}).")
        self._exec(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])

    def set_fan_level(self, zone: int, level: int) -> None:
        validate_input_range(zone, "zone", 0, 100)
        validate_input_range(level, "level", 0, 100)
        self._exec(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{level:02x}"])

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        # Validate zone parameters
        for zone in zone_list:
            validate_input_range(zone, "zone", 0, 100)
        validate_input_range(level, "level", 0, 100)
        for zone in zone_list:
            self._exec(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{level:02x}"])


class X10QBi(Platform):
    """Platform implementation for the Supermicro X10QBi motherboard (Nuvoton NCT7904D)."""

    valid_fan_modes: List[FanMode] = [FanMode.STANDARD, FanMode.FULL, FanMode.HEAVY_IO]
    BANK_3_REGISTER: str = "0x03"
    BANK_4_REGISTER: str = "0x04"

    def get_fan_mode(self) -> int:
        r = self._exec(["raw", "0x30", "0x45", "0x00"])
        return int(r.stdout)

    def get_fan_level(self, zone: int) -> int:
        # Valid zones: 0x10 (FANCTL1), 0x11 (FANCTL2), 0x12 (FANCTL3), 0x13 (FANCTL4)
        validate_input_range(zone, "zone", 16, 19)
        r = self._exec(["raw", "0x30", "0x90", "0x5c", "0x03", f"0x{zone:x}", "0x01"])
        return int(r.stdout, 16)

    def set_fan_manual_mode(self) -> None:
        # Set Temperature Fan Mapping Relationships (TMFR)
        # These map which of the 4 fan controllers are assigned to which
        # of the 10 temperature sensors. Each temperature sensor can have
        # any of the 4 fan controllers assigned.
        # Set T1FMR - T10FMR to 0x00 (00000000)
        # Bits 0-3 contain the settings for FANCTL1-FANCTL4 SMART FAN (F1SF etc).
        # Set these to 0 to make sure they are not in SmartFan mode.
        # Reference: Nuvoton NCT7904D Datasheet (p114)
        tmfr_addresses = [
            (self.BANK_3_REGISTER, "0x00"),  # T1FMR
            (self.BANK_3_REGISTER, "0x01"),  # T2FMR
            (self.BANK_3_REGISTER, "0x02"),  # T3FMR
            (self.BANK_3_REGISTER, "0x03"),  # T4FMR
            (self.BANK_4_REGISTER, "0x00"),  # T5FMR
            (self.BANK_4_REGISTER, "0x01"),  # T6FMR
            (self.BANK_4_REGISTER, "0x02"),  # T7FMR
            (self.BANK_4_REGISTER, "0x03"),  # T8FMR
            (self.BANK_4_REGISTER, "0x04"),  # T9FMR
            (self.BANK_4_REGISTER, "0x05"),  # T10FMR
        ]
        for register, tmfr_address in tmfr_addresses:
            self._exec(["raw", "0x30", "0x91", "0x5c", register, tmfr_address, "0x00"])

        # Set FOMC (FANCTL1-4 Output Mode Control) to PWM output.
        # Bit 3 controls output mode control (0 = set to PWM).
        # Bits 4-7 control 3Wire-Fan Enable (0 = set to disable).
        # Reference: Nuvoton NCT7904D Datasheet (p115)
        self._exec(["raw", "0x30", "0x91", "0x5c", self.BANK_3_REGISTER, "0x07", "0x00"])

    def set_fan_mode(self, mode: int) -> None:
        if mode not in self.valid_fan_modes:
            raise ValueError(f"Invalid value: fan mode ({mode}).")
        self._exec(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])

    def set_fan_level(self, zone: int, level: int) -> None:
        # Valid zones: 0x10 (FANCTL1), 0x11 (FANCTL2), 0x12 (FANCTL3), 0x13 (FANCTL4)
        # Reference: Nuvoton NCT7904D Datasheet (p120)
        validate_input_range(zone, "zone", 16, 19)
        validate_input_range(level, "level", 0, 100)
        # On the X10QBi, 100% is 0xFF (255), not 0x64 (100)
        normalised_level = level * 255 // 100
        self.set_fan_manual_mode()
        self._exec(["raw", "0x30", "0x91", "0x5c", self.BANK_3_REGISTER, f"0x{zone:02x}", f"0x{normalised_level:02x}"])

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        # Valid zones: 0x10 (FANCTL1), 0x11 (FANCTL2), 0x12 (FANCTL3), 0x13 (FANCTL4)
        # Reference: Nuvoton NCT7904D Datasheet (p120)
        for zone in zone_list:
            validate_input_range(zone, "zone", 16, 19)
        validate_input_range(level, "level", 0, 100)
        # On the X10QBi, 100% is 0xFF (255), not 0x64 (100)
        normalised_level = level * 255 // 100
        self.set_fan_manual_mode()
        for zone in zone_list:
            zone_hex, level_hex = f"0x{zone:02x}", f"0x{normalised_level:02x}"
            self._exec(["raw", "0x30", "0x91", "0x5c", self.BANK_3_REGISTER, zone_hex, level_hex])


def create_platform(platform_name: str, exec_ipmitool: Callable[[List[str]], subprocess.CompletedProcess]) -> Platform:
    """Factory method to create the appropriate Platform object for the given platform name.
    Args:
        platform_name (str): The platform name, one of:
            - 'generic': force the GenericPlatform (X10-X13/H10-H13)
            - 'X10QBi': force the X10QBi platform
            - any other string: looked up in the platform registry, falls back to GenericPlatform
        exec_ipmitool (Callable): Function that executes ipmitool commands
    Returns:
        Platform: The platform-specific implementation (defaults to GenericPlatform)
    """
    platform_factory = {
        Platform.PLATFORM_GENERIC: GenericPlatform,
        "X10QBi": X10QBi,
    }
    return platform_factory.get(platform_name, GenericPlatform)(platform_name, exec_ipmitool)


# End.
