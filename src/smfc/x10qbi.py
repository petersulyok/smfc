#
#   x10qbi.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   Platform implementation for the Supermicro X10QBi motherboard (Nuvoton NCT7904D).
#
from typing import List

from smfc.platform import FanMode, Platform, validate_input_range


class X10QBi(Platform):
    """Platform implementation for the Supermicro X10QBi motherboard (Nuvoton NCT7904D)."""

    valid_fan_modes: List[FanMode] = [FanMode.STANDARD, FanMode.FULL, FanMode.HEAVY_IO]
    BANK_3_REGISTER: str = "0x03"
    BANK_4_REGISTER: str = "0x04"
    FANCTL_BASE_REG: int = 0x10                # FANCTL1 output duty register address
    FANCTL_COUNT: int = 4                      # Number of fan controllers (FANCTL1-FANCTL4)

    def get_fan_mode(self) -> int:
        r = self._exec(["raw", "0x30", "0x45", "0x00"])
        return int(r.stdout)

    def get_fan_level(self, zone: int) -> int:
        # Zone 0-3 maps to register 0x10-0x13 (FANCTL1-FANCTL4)
        validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        reg = self.FANCTL_BASE_REG + zone
        r = self._exec(["raw", "0x30", "0x90", "0x5c", "0x03", f"0x{reg:x}", "0x01"])
        return int(r.stdout, 16)

    def start(self) -> None:
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

    def end(self) -> None:
        pass

    def set_fan_mode(self, mode: int) -> None:
        if mode not in self.valid_fan_modes:
            raise ValueError(f"Invalid value: fan mode ({mode}).")
        self._exec(["raw", "0x30", "0x45", "0x01", f"0x{mode:02x}"])

    def set_fan_level(self, zone: int, level: int) -> None:
        # Zone 0-3 maps to register 0x10-0x13 (FANCTL1-FANCTL4)
        # Reference: Nuvoton NCT7904D Datasheet (p120)
        validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        validate_input_range(level, "level", 0, 100)
        reg = self.FANCTL_BASE_REG + zone
        # On the X10QBi, 100% is 0xFF (255), not 0x64 (100)
        normalised_level = level * 255 // 100
        self.start()
        self._exec(["raw", "0x30", "0x91", "0x5c", self.BANK_3_REGISTER, f"0x{reg:02x}", f"0x{normalised_level:02x}"])

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        # Zone 0-3 maps to register 0x10-0x13 (FANCTL1-FANCTL4)
        # Reference: Nuvoton NCT7904D Datasheet (p120)
        for zone in zone_list:
            validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        validate_input_range(level, "level", 0, 100)
        # On the X10QBi, 100% is 0xFF (255), not 0x64 (100)
        normalised_level = level * 255 // 100
        self.start()
        for zone in zone_list:
            reg = self.FANCTL_BASE_REG + zone
            reg_hex, level_hex = f"0x{reg:02x}", f"0x{normalised_level:02x}"
            self._exec(["raw", "0x30", "0x91", "0x5c", self.BANK_3_REGISTER, reg_hex, level_hex])


# End.
