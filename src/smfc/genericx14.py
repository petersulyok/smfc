#
#   genericx14.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   Platform implementation for Supermicro X14 motherboards.
#
import subprocess
from typing import Callable, Dict, List, Optional

from smfc.platform import ControlState, ControlStatus, FanMode, Platform, validate_input_range


class GenericX14Platform(Platform):
    """Platform implementation for Supermicro X14 (AST2600) motherboards.

    The X14 BMC differs from the older platforms in the way fan control is acquired: instead of FULL fan mode
    it has an explicit per-zone *manual mode*, and the base fan mode only selects the automatic curve the fans
    fall back to when manual mode is lost. `smfc` therefore reads the base fan mode but never writes it -
    writing it would clear manual mode on every zone.

    Zone numbering is the crux of this platform: the OEM manual/failsafe commands count zones from 1, the duty
    commands from 0. smfc zone IDs are 0-based everywhere (configuration, controllers, all other platforms),
    so the +1 is applied in exactly one place, `_manual_zone()`.

    See `doc/X14_MANUAL_FANCONTROL.md` for the full command reference.
    """

    FANCTL_COUNT: int = 4           # Number of fan zones (0-3), the documented board maximum
    ENFORCES_FULL_MODE: bool = False
    valid_fan_modes: List[int] = [
        FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO,
        0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
    ]
    # OEM command prefix for the manual/failsafe fan control commands (IANA 0x0000C2CF).
    OEM_PREFIX: List[str] = ["raw", "0x2c", "0x04", "0xcf", "0xc2", "0x00"]
    OEM_OP_READ_MANUAL: str = "0x00"        # Read the manual mode flag of a zone
    OEM_OP_SET_MANUAL: str = "0x01"         # Set the manual mode flag of a zone
    DEFAULT_ZONE_SENSOR: int = 0x41         # FAN1, zone 0 on every documented X14 board

    zone_sensors: Dict[int, int]            # IPMI zone -> representative fan sensor number

    def __init__(self, name: str, exec_ipmitool: Callable[[List[str]], subprocess.CompletedProcess],
                 zone_sensors: Optional[Dict[int, int]] = None) -> None:
        """Initialize the platform with the zone -> fan sensor map needed by `get_fan_level()`.

        The map cannot be derived from the fan names: the first sensor of zone 1 is 0x46 on X14SBI-F, 0x47 on
        X14DBI-SP, 0x46 (a numbered fan) on X14DBG-AP and 0x44 on X14SRG-TF, so the user supplies it with
        `[Ipmi] x14_zone_sensors=`.
        Args:
            name (str): platform name (e.g. from BMC product name or config)
            exec_ipmitool (Callable): function that executes ipmitool commands
            zone_sensors (Optional[Dict[int, int]]): IPMI zone -> fan sensor number (default: {0: 0x41})
        """
        super().__init__(name, exec_ipmitool)
        self.zone_sensors = dict(zone_sensors) if zone_sensors else {0: self.DEFAULT_ZONE_SENSOR}

    @staticmethod
    def _manual_zone(zone: int) -> str:
        """Convert an smfc (0-based) zone ID to the 1-based zone byte of the OEM manual/failsafe commands."""
        return f"0x{zone + 1:02x}"

    def _get_manual_mode(self, zone: int) -> bool:
        """Return True if manual fan mode is active in the given zone."""
        r = self._exec(self.OEM_PREFIX + [self.OEM_OP_READ_MANUAL, self._manual_zone(zone)])
        return int(r.stdout, 16) == 1

    def _set_manual_mode(self, zone: int, enabled: bool) -> None:
        """Enable or disable manual fan mode in the given zone."""
        value = "0x01" if enabled else "0x00"
        self._exec(self.OEM_PREFIX + [self.OEM_OP_SET_MANUAL, self._manual_zone(zone), value])

    def start(self, zones: List[int]) -> bool:
        """Latch manual fan mode in the controlled zones and confirm it was accepted.

        This is also the recovery path, so it must tolerate being run again; re-latching an already latched
        zone is harmless. Only the controlled zones are latched: latching a zone smfc does not drive would
        freeze it at its current duty with nothing regulating it.

        The base fan mode is deliberately not written here: on X14 it would clear manual mode on every zone.
        A board without per-zone manual mode (H14 answers 0xC1 to the OEM command) fails here, which is the
        preflight check of `doc/X14_MANUAL_FANCONTROL.md` chapter 4.0.
        Args:
            zones (List[int]): IPMI zones smfc controls
        Returns:
            bool: always False, the fan mode is never written on this platform (so no `fan_mode_delay` is due)
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem, or a zone did not accept manual mode
            ValueError: invalid input parameter, or the reply cannot be interpreted
        """
        for zone in zones:
            validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
            self._set_manual_mode(zone, True)
            # Read the flag back: an accepted command is not proof that the zone is latched, and smfc must not
            # pretend to control a zone that the BMC still drives itself.
            if not self._get_manual_mode(zone):
                raise RuntimeError(f"IPMI zone {zone} did not accept manual fan mode (see "
                                   f"doc/X14_MANUAL_FANCONTROL.md chapter 4.0).")
        return False

    def check_fan_mode(self, zones: List[int]) -> ControlStatus:
        """Report whether manual fan mode is still latched in all controlled zones.

        The manual flag is not sticky: a BMC reboot, a firmware update or a fan mode change made from any
        other interface clears it, and the BMC takes the fans back within about a second. The base fan mode is
        read as well, but only to keep the snapshot cache populated - it plays no part in the decision here.
        Args:
            zones (List[int]): IPMI zones smfc controls
        Returns:
            ControlStatus: the observed control state
        Raises:
            FileNotFoundError: ipmitool cannot be found
        """
        try:
            fan_mode = self.get_fan_mode()
            lost = [zone for zone in zones if not self._get_manual_mode(zone)]
        except (RuntimeError, ValueError) as e:
            return ControlStatus(ControlState.LOST, f"Manual fan mode could not be read: {e}", -1, confirmed=False)
        if lost:
            return ControlStatus(ControlState.LOST, f"Manual fan mode was cleared in IPMI zone(s) {lost}", fan_mode)
        return ControlStatus(ControlState.OK, "", fan_mode)

    def end(self, zones: List[int], level: int) -> None:
        """Apply the exit fan level to the configured zones, then release manual fan mode in all zones,
        restoring automatic BMC fan control.

        This platform behaves differently from the others: manual mode is an explicit OEM state that would stay
        latched forever if it were not released, leaving every zone frozen at the exit level with nothing
        regulating it. Releasing it hands the fans back to the BMC, so the exit level is only a transition here
        - within seconds the BMC applies its own curve. Note that the BMC regulates on CPU and system sensors
        only, so drive temperatures are not part of that loop.
        Args:
            zones (List[int]): configured IPMI zones the exit level is applied to
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem
        """
        # Apply the exit level first: releasing manual mode first would hand control to the BMC and make the
        # level write a no-op.
        self.set_multiple_fan_levels(zones, level)
        # Release manual mode with the all-zones shortcut, so nothing stays latched even if smfc latched a
        # zone in an earlier run. Firmware that rejects the shortcut is handled per zone.
        try:
            self._exec(["raw", "0x30", "0x70", "0x66", "0x02", "0x00"])
        except RuntimeError:
            for zone in zones:
                self._set_manual_mode(zone, False)

    def get_fan_level(self, zone: int) -> int:
        """Return the current fan duty cycle percentage for the given zone.

        The duty is read from one representative fan of the zone (all fans of a zone share the same duty), and
        the reply carries two hexadecimal bytes: the duty and the temperature of that fan.
        Args:
            zone (int): IPMI zone
        Returns:
            int: fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter, or the duty is unavailable
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem, or the zone has no fan sensor configured
        """
        validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        sensor = self.zone_sensors.get(zone)
        if sensor is None:
            raise RuntimeError(f"IPMI zone {zone} has no fan sensor configured (see [Ipmi] x14_zone_sensors=).")
        r = self._exec(["raw", "0x30", "0x70", "0x88", f"0x{sensor:02x}"])
        duty = int(r.stdout.split()[0], 16)
        if duty == 0xFF:
            raise ValueError(f"Fan duty is unavailable in IPMI zone {zone}.")
        return duty

    def set_fan_level(self, zone: int, level: int) -> None:
        """Set the fan duty cycle percentage for the given zone."""
        # X14 uses the percentage directly (0x00-0x64); manual mode must be latched first (start()).
        validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        validate_input_range(level, "level", 0, 100)
        self._exec(["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:02x}", f"0x{level:02x}"])

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        """Set the same fan duty cycle percentage for all given zones."""
        # X14 uses the percentage directly (0x00-0x64); manual mode must be latched first (start()).
        for zone in zone_list:
            validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        validate_input_range(level, "level", 0, 100)
        for zone in zone_list:
            self._exec(["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:02x}", f"0x{level:02x}"])


# End.
