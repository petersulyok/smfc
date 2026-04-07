#
#   genericx14.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   Platform implementation for Supermicro X14 motherboards.
#
from typing import List

from smfc.platform import FanMode, Platform, validate_input_range


class GenericX14Platform(Platform):
    """Platform implementation for Supermicro X14 motherboards.

    X14 BMC uses different IPMI raw commands discovered through reverse engineering
    of libsupermicrooemcmds.so and libmanualcmds.so.

    Key differences from generic platforms:
    - Uses 0x30 0x70 0x88 for fan duty cycle control (instead of 0x30 0x70 0x66)
    - Requires manual mode enablement via 0x2c 0x04 0xcf 0xc2 0x00 <zone> 0x01
    - Supports extended fan modes (0x00-0x0B)
    - Duty cycle is in percentage (0x00-0x64), not 0-255 scale
    """

    # Extended fan modes supported by X14
    valid_fan_modes: List[int] = [
        FanMode.STANDARD,   # 0x00
        FanMode.FULL,       # 0x01
        FanMode.OPTIMAL,    # 0x02
        FanMode.PUE,        # 0x03
        FanMode.HEAVY_IO,   # 0x04
        0x05,  # PUE3
        0x06,  # LiquidCooling
        0x07,  # Smart
        0x08,  # PUE (alternate)
        0x09,  # SmartCooling
        0x0A,  # Performance
        0x0B,  # Silent
    ]

    def get_fan_mode(self) -> int:
        r = self._exec(["raw", "0x30", "0x45", "0x00"])
        return int(r.stdout)

    def get_fan_level(self, zone: int) -> int:
        validate_input_range(zone, "zone", 0, 5)
        r = self._exec(["raw", "0x30", "0x70", "0x88", f"0x{zone:02x}"])
        return int(r.stdout, 16)

    def start(self) -> None:
        """Enable manual mode for all zones at startup.

        This stops the BMC's PID controller (swampd) from overriding PWM values.
        Uses OpenBMC OEM command (IANA: 0x0000C2CF).
        """
        # Enable manual mode for zones 0-5
        for zone in range(6):
            self._exec(["raw", "0x2c", "0x04", "0xcf", "0xc2", "0x00", f"0x{zone:02x}", "0x01"])

    def end(self) -> None:
        """Disable manual mode for all zones at shutdown.

        Restores automatic PID control by the BMC's swampd daemon.
        """
        # Disable manual mode for zones 0-5
        for zone in range(6):
            self._exec(["raw", "0x2c", "0x04", "0xcf", "0xc2", "0x00", f"0x{zone:02x}", "0x00"])

    def set_fan_mode(self, mode: int) -> None:
        if mode not in self.valid_fan_modes:
            raise ValueError(f"Invalid value: fan mode ({mode}).")
        self._exec(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])

    def set_fan_level(self, zone: int, level: int) -> None:
        validate_input_range(zone, "zone", 0, 5)
        validate_input_range(level, "level", 0, 100)
        # Set duty cycle (X14 uses percentage directly: 0x00-0x64)
        self._exec(["raw", "0x30", "0x70", "0x88", f"0x{zone:02x}", f"0x{level:02x}"])

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        for zone in zone_list:
            validate_input_range(zone, "zone", 0, 5)
        validate_input_range(level, "level", 0, 100)
        # Set level for each zone
        for zone in zone_list:
            self._exec(["raw", "0x30", "0x70", "0x88", f"0x{zone:02x}", f"0x{level:02x}"])


# End.
