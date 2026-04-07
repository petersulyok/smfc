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

    def start(self) -> None:
        """Initialize platform for manual fan control (no-op for generic platforms)."""

    def end(self) -> None:
        """Clean up platform resources (no-op for generic platforms)."""

    def get_fan_mode(self) -> int:
        """Get the current IPMI fan mode using 0x30 0x45 0x00 command.
        Returns:
            int: fan mode (0=STANDARD, 1=FULL, 2=OPTIMAL, 3=PUE, 4=HEAVY_IO)
        """
        r = self._exec(["raw", "0x30", "0x45", "0x00"])
        return int(r.stdout)

    def get_fan_level(self, zone: int) -> int:
        """Get the current fan level in a specific IPMI zone using 0x30 0x70 0x66 0x00 command.
        Args:
            zone (int): IPMI zone (0-100)
        Returns:
            int: fan level in % (0-100)
        """
        validate_input_range(zone, "zone", 0, 100)
        r = self._exec(["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:x}"])
        return int(r.stdout, 16)

    def set_fan_mode(self, mode: int) -> None:
        """Set the IPMI fan mode using 0x30 0x45 0x01 command.
        Args:
            mode (int): fan mode (0=STANDARD, 1=FULL, 2=OPTIMAL, 3=PUE, 4=HEAVY_IO)
        """
        if mode not in self.valid_fan_modes:
            raise ValueError(f"Invalid value: fan mode ({mode}).")
        self._exec(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])

    def set_fan_level(self, zone: int, level: int) -> None:
        """Set the fan level in a specific IPMI zone using 0x30 0x70 0x66 0x01 command.
        Args:
            zone (int): IPMI zone (0-100)
            level (int): fan level in % (0-100)
        """
        validate_input_range(zone, "zone", 0, 100)
        validate_input_range(level, "level", 0, 100)
        self._exec(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{level:02x}"])

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        """Set the fan level in multiple IPMI zones.
        Args:
            zone_list (List[int]): list of IPMI zones (0-100)
            level (int): fan level in % (0-100)
        """
        # Validate zone parameters
        for zone in zone_list:
            validate_input_range(zone, "zone", 0, 100)
        validate_input_range(level, "level", 0, 100)
        for zone in zone_list:
            self._exec(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{level:02x}"])


# End.
