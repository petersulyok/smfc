#
#   generic.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   Platform implementation for the most common Supermicro X10/X11/X12/X13 motherboards.
#
from typing import List

from smfc.platform import FanMode, Platform, validate_input_range


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

    def start(self) -> None:
        pass

    def end(self) -> None:
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


# End.
