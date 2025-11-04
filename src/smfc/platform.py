from abc import ABC, abstractmethod
from enum import IntEnum
import subprocess
from typing import Callable, List


def validate_input_range(value: int, valrepr: str, minval: int, maxval: int) -> None:
    """Throw an error if a value does not lie within the interval specified by
    [minval, maxval]
    Args:
        value (int): The value to validate
        valrepr (str): A string representation of what the value is
        minval (int): The minimum inclusive value within the range to test
        maxval (int): The maximum inclusive value within the range to test
    Return:
       None
    Raises:
        ValueError: `value` does not lie within `[minval, maxval]`.
    """
    if value not in range(minval, maxval + 1):
        raise ValueError(
            f"Invalid value: {valrepr} ({value}). "
            f"Please provide a value within the valid {valrepr} range "
            f"of [{minval},{maxval}]"
        )

class FanMode(IntEnum):
    """The different fan modes supported by Supermicro platforms
    The integers associated with each of these represent the hex values
    that need to be propagated to `ipmitool raw` commands to set these modes.
    """
    STANDARD = 0
    FULL = 1
    OPTIMAL = 2
    PUE = 3
    HEAVY_IO = 4


class Platform(ABC):
    """Abstract interface class to represent platforms with different `ipmitool raw`
    functionality. Concrete derivatives of this class will implement the functionality
    to make a number of platform-specific queries manipulate fan control.
    """
    _name: str

    def __init__(self, name):
        self._name = name

    # Getters
    def name(self) -> str:
        """Get the name of the platform
        Returns:
            str: The name of the platform
        """
        return self._name

    @abstractmethod
    def get_fan_mode(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess]
    ) -> int:
        """Get the current IPMI fan mode.
        Args:
            ipmitool_fn (Callable[[List[str]], subprocess.CompletedProcess]): Function that executes `ipmitool`
                subprocess
        Returns:
            int: fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
            ValueError: output of the ipmitool cannot be interpreted/converted
        """

    @abstractmethod
    def get_fan_level(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess], zone: int
    ) -> int:
        """Get the current fan level in a specific IPMI zone. Raise an exception in case of invalid parameters.
        Args:
            ipmitool_fn (Callable[[List[str]], subprocess.CompletedProcess]): Function that executes `ipmitool`
                subprocess
            zone (int): fan zone (CPU_ZONE, HD_ZONE)
        Returns:
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """

    # Setters
    @abstractmethod
    def set_fan_manual_mode(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess]
    ) -> None:
        """Set the fan controllers on the platform to accept manual PWM or DC input
        Args:
            ipmitool_fn (Callable[[List[str]], subprocess.CompletedProcess]): Function that executes `ipmitool`
                subprocess
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
            ValueError: output of the ipmitool cannot be interpreted/converted
        """

    @abstractmethod
    def set_fan_mode(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess], mode: int
    ) -> None:
        """Set the IPMI fan mode.
        Args:
            ipmitool_fn (Callable[[List[str]], subprocess.CompletedProcess]): Function that executes `ipmitool`
                subprocess
            mode (int): fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """

    @abstractmethod
    def set_fan_level(
        self,
        ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess],
        zone: int,
        level: int,
    ) -> None:
        """Set the fan level in the specified IPMI zone. Could raise several exceptions in case of invalid parameters.
        Args:
            ipmitool_fn (Callable[[List[str]], subprocess.CompletedProcess]): Function that executes `ipmitool`
                subprocess
            zone (int): IPMI zone
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """

    @abstractmethod
    def set_multiple_fan_levels(
        self,
        ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess],
        zone_list: List[int],
        level: int,
    ) -> None:
        """Set the fan level in multiple IPMI zones. Could raise several exceptions in case of invalid parameters.
        Args:
            ipmitool_fn (Callable[[List[str]], subprocess.CompletedProcess]): Function that executes `ipmitool`
                subprocess
            zone_list (List[int]): List of IPMI zones
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """


def create_platform(platform_name: str) -> Platform:
    """Factory method to create the appropriate Platform object from the platform_name string
    Args:
        platform_name (str): The string representing the platform name
    Returns:
        Platform: Object providing the low level platform `ipmitool raw` functionality
            for the specified platform
    """
    platform_factory = {
        "X10QBi": X10QBi,
    }
    return platform_factory.get(platform_name, GenericPlatform)(platform_name)


class GenericPlatform(Platform):
    """Class specialisation of Platform to represent the most common `ipmitool raw`
    functionality of Supermicro X10/X11/X12/X13 motherboards.
    """
    valid_fan_modes: List[FanMode] = [
        FanMode.STANDARD,
        FanMode.FULL,
        FanMode.OPTIMAL,
        FanMode.PUE,
        FanMode.HEAVY_IO
    ]

    # Getters
    def get_fan_mode(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess]
    ) -> int:
        r: subprocess.CompletedProcess  # result of the executed process
        m: int  # fan mode

        # Read the current IPMI fan mode.
        try:
            r = ipmitool_fn(["raw", "0x30", "0x45", "0x00"])
            m = int(r.stdout)
        except (RuntimeError, FileNotFoundError) as e:
            raise e
        return m

    def get_fan_level(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess], zone: int
    ) -> int:
        r: subprocess.CompletedProcess  # result of the executed process
        level: int  # Level

        # Validate zone parameter
        validate_input_range(zone, "zone", 0, 100)
        # Get the new IPMI fan level in the specific zone
        try:
            r = ipmitool_fn(["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:x}"])
            level = int(r.stdout, 16)
        except (FileNotFoundError, RuntimeError) as e:
            raise e
        return level

    # Setters
    def set_fan_manual_mode(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess]
    ) -> None:
        pass

    def set_fan_mode(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess], mode: int
    ) -> None:
        """Set the IPMI fan mode.
        Args:
            ipmitool_fn (Callable[[List[str]], subprocess.CompletedProcess]): Function that executes `ipmitool`
                subprocess
            mode (int): fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        # Validate mode parameter.
        if mode not in self.valid_fan_modes:
            raise ValueError(f"Invalid value: fan mode ({mode}).")
        # Call ipmitool command and set the new IPMI fan mode.
        try:
            ipmitool_fn(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])
        except (RuntimeError, FileNotFoundError) as e:
            raise e

    def set_fan_level(
        self,
        ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess],
        zone: int,
        level: int,
    ) -> None:
        # Validate zone parameter
        validate_input_range(zone, "zone", 0, 100)
        # Validate level parameter (must be in the interval [0..100%])
        validate_input_range(level, "level", 0, 100)
        # Set the new IPMI fan level in the specific zone
        try:
            ipmitool_fn(
                [
                    "raw",
                    "0x30",
                    "0x70",
                    "0x66",
                    "0x01",
                    f"0x{zone:02x}",
                    f"0x{level:02x}",
                ]
            )
        except (FileNotFoundError, RuntimeError) as e:
            raise e

    def set_multiple_fan_levels(
        self,
        ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess],
        zone_list: List[int],
        level: int,
    ) -> None:
        # Validate zone parameter
        # Validate zone parameters
        for zone in zone_list:
            validate_input_range(zone, "zone", 0, 100)
        # Validate level parameter (must be in the interval [0..100%])
        validate_input_range(level, "level", 0, 100)
        # Set the new IPMI fan level in the specific zone
        try:
            for zone in zone_list:
                ipmitool_fn(
                    [
                        "raw",
                        "0x30",
                        "0x70",
                        "0x66",
                        "0x01",
                        f"0x{zone:02x}",
                        f"0x{level:02x}",
                    ]
                )
        except (FileNotFoundError, RuntimeError) as e:
            raise e


class X10QBi(Platform):
    """Class specialisation of Platform to represent the `ipmitool raw` functionality
    of the Supermicro X10QBi motherboard.
    """
    # Constant values for IPMI fan modes:
    valid_fan_modes: List[FanMode] = [
        FanMode.STANDARD,
        FanMode.FULL,
        FanMode.HEAVY_IO,
    ]
    BANK_3_REGISTER: str = "0x03"
    BANK_4_REGISTER: str = "0x04"

    # Getters
    def get_fan_mode(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess]
    ) -> int:
        r: subprocess.CompletedProcess  # result of the executed process
        m: int  # fan mode

        # Read the current IPMI fan mode.
        try:
            r = ipmitool_fn(["raw", "0x30", "0x45", "0x00"])
            m = int(r.stdout)
        except (RuntimeError, FileNotFoundError) as e:
            raise e
        return m

    def get_fan_level(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess], zone: int
    ) -> int:
        r: subprocess.CompletedProcess  # result of the executed process
        level: int  # Level

        # Validate zone parameter
        # Valid zones:
        # * 0x10: FANCTL1
        # * 0x11: FANCTL2
        # * 0x12: FANCTL3
        # * 0x13: FANCTL4
        validate_input_range(zone, "zone", int("0x10", 16), int("0x13", 16))
        # Get the new IPMI fan level in the specific zone
        try:
            r = ipmitool_fn(["raw", "0x30", "0x90", "0x5c", "0x03", f"0x{zone:x} 0x01"])
            level = int(r.stdout, 16)
        except (FileNotFoundError, RuntimeError) as e:
            raise e
        return level

    # Setters
    def set_fan_manual_mode(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess]
    ) -> None:
        # Set Temperature Fan Mapping Relationships (TMFR)
        # These map which of the 4 fan controllers are assigned to which
        # of the 10 temperature sensors. Each temperature sensor can have
        # any of the 4 fan controllers assigned.
        # Set T1FMR - T10FMR to 0x00 (00000000)
        # Bits 0-3 contain the settings for FANCTL1-FANCTL4 SMART FAN (F1SF etc).
        # Set these to 0 to make sure they are not in SmartFan mode
        # Reference: Nuvoton NCT7904D Datasheet (p114)
        # https://www.nuvoton.com/export/resource-files/en-us--Nuvoton_NCT7904D_Datasheet_V17.pdf
        T1FMR_ADDRESS: str = "0x00"  # pylint: disable=C0103
        T2FMR_ADDRESS: str = "0x01"  # pylint: disable=C0103
        T3FMR_ADDRESS: str = "0x02"  # pylint: disable=C0103
        T4FMR_ADDRESS: str = "0x03"  # pylint: disable=C0103
        T5FMR_ADDRESS: str = "0x00"  # pylint: disable=C0103
        T6FMR_ADDRESS: str = "0x01"  # pylint: disable=C0103
        T7FMR_ADDRESS: str = "0x02"  # pylint: disable=C0103
        T8FMR_ADDRESS: str = "0x03"  # pylint: disable=C0103
        T9FMR_ADDRESS: str = "0x04"  # pylint: disable=C0103
        T10FMR_ADDRESS: str = "0x05"  # pylint: disable=C0103
        tmfr_addresses = [
            (self.BANK_3_REGISTER, T1FMR_ADDRESS),
            (self.BANK_3_REGISTER, T2FMR_ADDRESS),
            (self.BANK_3_REGISTER, T3FMR_ADDRESS),
            (self.BANK_3_REGISTER, T4FMR_ADDRESS),
            (self.BANK_4_REGISTER, T5FMR_ADDRESS),
            (self.BANK_4_REGISTER, T6FMR_ADDRESS),
            (self.BANK_4_REGISTER, T7FMR_ADDRESS),
            (self.BANK_4_REGISTER, T8FMR_ADDRESS),
            (self.BANK_4_REGISTER, T9FMR_ADDRESS),
            (self.BANK_4_REGISTER, T10FMR_ADDRESS),
        ]
        MANUAL_MODE: str = "0x00"  # pylint: disable=C0103

        for register, tmfr_address in tmfr_addresses:
            ipmitool_fn(
                [
                    "raw",
                    "0x30",
                    "0x91",
                    "0x5c",
                    register,
                    tmfr_address,
                    MANUAL_MODE,
                ]
            )

        # Set FOMC (FANCTL1-4 Output Mode Control) to PWM output
        # Bit 3 controls output mode control (0 = set to PWM)
        # Bits 4-7 control 3Wire-Fan Enable (0 = set to disable)
        # Reference: Nuvoton NCT7904D Datasheet (p115)
        # https://www.nuvoton.com/export/resource-files/en-us--Nuvoton_NCT7904D_Datasheet_V17.pdf
        FOMC_ADDRESS: str = "0x07"  # pylint: disable=C0103
        PWM_OUTPUT: str = "0x00"  # pylint: disable=C0103
        ipmitool_fn(
            [
                "raw",
                "0x30",
                "0x91",
                "0x5c",
                self.BANK_3_REGISTER,
                FOMC_ADDRESS,
                PWM_OUTPUT,
            ]
        )

    def set_fan_mode(
        self, ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess], mode: int
    ) -> None:
        # Validate mode parameter.
        if mode not in self.valid_fan_modes:
            raise ValueError(f"Invalid value: fan mode ({mode}).")
        # Call ipmitool command and set the new IPMI fan mode.
        try:
            ipmitool_fn(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])
        except (RuntimeError, FileNotFoundError) as e:
            raise e

    def set_fan_level(
        self,
        ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess],
        zone: int,
        level: int,
    ) -> None:
        # Validate zone parameter
        # Valid zones:
        # * 0x10: FANCTL1
        # * 0x11: FANCTL2
        # * 0x12: FANCTL3
        # * 0x13: FANCTL4
        # Reference: Nuvoton NCT7904D Datasheet (p120)
        # https://www.nuvoton.com/export/resource-files/en-us--Nuvoton_NCT7904D_Datasheet_V17.pdf
        validate_input_range(zone, "zone", int("0x10", 16), int("0x13", 16))
        # Validate level parameter (must be in the interval [0..100%])
        validate_input_range(level, "level", 0, 100)

        # On the X10QBi, 100% is 0xFF (255), not 0x64 (100)
        normalised_level = level * 255 // 100
        # Set the new IPMI fan level in the specific zone
        try:
            self.set_fan_manual_mode(ipmitool_fn)
            ipmitool_fn(
                [
                    "raw",
                    "0x30",
                    "0x91",
                    "0x5c",
                    self.BANK_3_REGISTER,
                    f"0x{zone:02x}",
                    f"0x{normalised_level:02x}",
                ]
            )
        except (FileNotFoundError, RuntimeError) as e:
            raise e

    def set_multiple_fan_levels(
        self,
        ipmitool_fn: Callable[[List[str]], subprocess.CompletedProcess],
        zone_list: List[int],
        level: int,
    ) -> None:
        # Validate zone parameters
        # Valid zones:
        # * 0x10: FANCTL1
        # * 0x11: FANCTL2
        # * 0x12: FANCTL3
        # * 0x13: FANCTL4
        # Reference: Nuvoton NCT7904D Datasheet (p120)
        # https://www.nuvoton.com/export/resource-files/en-us--Nuvoton_NCT7904D_Datasheet_V17.pdf
        for zone in zone_list:
            validate_input_range(zone, "zone", int("0x10", 16), int("0x13", 16))
        # Validate level parameter (must be in the interval [0..100%])
        validate_input_range(level, "level", 0, 100)
        # On the X10QBi, 100% is 0xFF (255), not 0x64 (100)
        normalised_level = level * 255 // 100
        # Set the new IPMI fan level in the specific zone
        try:
            self.set_fan_manual_mode(ipmitool_fn)
            for zone in zone_list:
                ipmitool_fn(
                    [
                        "raw",
                        "0x30",
                        "0x91",
                        "0x5c",
                        self.BANK_3_REGISTER,
                        f"0x{zone:02x}",
                        f"0x{normalised_level:02x}",
                    ]
                )
        except (FileNotFoundError, RuntimeError) as e:
            raise e
