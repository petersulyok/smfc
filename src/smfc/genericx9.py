#
#   genericx9.py (C) 2025-2026, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   Platform implementation for generic Supermicro X9 motherboards.
#
from typing import List

from smfc.platform import FanMode, Platform, validate_input_range


class GenericX9Platform(Platform):
    """Platform implementation for generic Supermicro X9 motherboards."""

    FANCTL_BASE_REG: int = 0x10     # Base register address for fan zone duty cycle
    FANCTL_COUNT: int = 4           # Number of fan zones
    valid_fan_modes: List[FanMode] = [FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.HEAVY_IO]

    def get_fan_mode(self) -> int:
        r = self._exec(["raw", "0x30", "0x45", "0x00"])
        return int(r.stdout)

    def get_fan_level(self, zone: int) -> int:
        # Zone 0-3 maps to register 0x10-0x13
        validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        reg = self.FANCTL_BASE_REG + zone
        r = self._exec(["raw", "0x30", "0x90", "0x5a", "0x03", f"0x{reg:x}", "0x01"])
        return int(r.stdout, 16)

    def set_fan_manual_mode(self) -> None:
        pass

    def set_fan_mode(self, mode: int) -> None:
        if mode not in self.valid_fan_modes:
            raise ValueError(f"Invalid value: fan mode ({mode}).")
        self._exec(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])

    def set_fan_level(self, zone: int, level: int) -> None:
        # Zone 0-3 maps to register 0x10-0x13
        # Duty cycle uses 0-255 scale (100% = 0xFF)
        validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        validate_input_range(level, "level", 0, 100)
        reg = self.FANCTL_BASE_REG + zone
        normalised_level = level * 255 // 100
        self._exec(["raw", "0x30", "0x91", "0x5a", "0x03", f"0x{reg:02x}", f"0x{normalised_level:02x}"])

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        # Zone 0-3 maps to register 0x10-0x13
        for zone in zone_list:
            validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        validate_input_range(level, "level", 0, 100)
        normalised_level = level * 255 // 100
        for zone in zone_list:
            reg = self.FANCTL_BASE_REG + zone
            self._exec(["raw", "0x30", "0x91", "0x5a", "0x03", f"0x{reg:02x}", f"0x{normalised_level:02x}"])


# End.
