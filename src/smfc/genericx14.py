#
#   genericx14.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   Platform implementations for Supermicro X14/H14 motherboards (OpenBMC and ATEN BMC firmware).
#
import subprocess
from typing import Callable, Dict, List, Optional, Set

from smfc.generic import GenericPlatform
from smfc.platform import (ControlState, ControlStatus, FanLevelUnavailable, FanMode, IpmiError,
                           Platform, validate_input_range)


class X14OpenBmcPlatform(Platform):
    """Platform implementation for Supermicro X14/H14 motherboards running the OpenBMC
    (`openbmc-phosphor`) firmware stack.

    This stack differs from the older platforms in the way fan control is acquired: instead of FULL fan mode
    it has an explicit per-zone *manual mode*, and the base fan mode only selects the automatic curve the fans
    fall back to when manual mode is lost. `smfc` therefore reads the base fan mode but never writes it -
    writing it would clear manual mode on every zone.

    Zone numbering is the crux of this platform: the OEM manual/failsafe commands count zones from 1, the duty
    commands from 0. smfc zone IDs are 0-based everywhere (configuration, controllers, all other platforms),
    so the +1 is applied in exactly one place, `_manual_zone()`.

    The stack is not implied by the board name - most X14 boards run OpenBMC but `X14SDW`/`X14SDV` do not,
    and the H14 board `H14SHM` does - so this class is selected by the runtime probe in `platform_factory`,
    never by a name prefix. See `doc/X14H14_MANUAL_FANCONTROL.md` Part 3 for the full command reference and
    Part 5.1 for the per-board zone tables.
    """

    FANCTL_COUNT: int = 5           # Firmware bound: the duty commands reject a zone byte above 0x04
    ENFORCES_FULL_MODE: bool = False
    MIN_LEVEL: int = 5                      # Never write a duty below this, see _clamp_level()
    FAILSAFE_REPORT_AFTER: int = 3          # Consecutive observations before failsafe is named as the cause
    DEFAULT_FAN_MODES: List[int] = [
        FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO,
        0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
    ]
    # OEM command prefix for the manual/failsafe fan control commands (IANA 0x0000C2CF).
    OEM_PREFIX: List[str] = ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00"]
    OEM_OP_READ_MANUAL: str = "0x00"        # Read the manual mode flag of a zone
    OEM_OP_SET_MANUAL: str = "0x01"         # Set the manual mode flag of a zone
    OEM_OP_READ_FAILSAFE: str = "0x02"      # Read the failsafe flag of a zone
    GET_SUPPORTED_MODES: List[str] = ["raw", "0x30", "0x45", "0x02"]     # Supported fan mode bitmask
    DEFAULT_ZONE_SENSOR: int = 0x41         # FAN1, zone 0 on every documented X14 board

    zone_sensors: Dict[int, int]            # IPMI zone -> representative fan sensor number
    latched_zones: List[int]                # Zones manual mode was latched in by start()
    _zone_count: Optional[int]              # Zones the board has, discovered by probe() on first use
    _supported_modes: Optional[List[int]]   # Fan modes the board supports, read from the BMC on first use
    _failsafe_count: Dict[int, int]         # IPMI zone -> consecutive observations in failsafe

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
        self.latched_zones = []
        self._zone_count = None
        self._supported_modes = None
        self._failsafe_count = {}

    @property
    def valid_fan_modes(self) -> List[int]:
        """The base fan modes this board supports, from the bitmask the BMC reports.

        The bitmask is two bytes, little-endian, one bit per mode value: `02 0c` is 0x0C02, bits 1, 10 and
        11, i.e. FullSpeed, Performance and Silent. Reading it is the only way to know a mode is real - a
        mode the board does not have is accepted silently and reads back correctly while a different fan
        table is loaded (Part 3.4). Firmware without the command falls back to the documented 0x00-0x0B
        range, which is the widest a board can support.
        """
        if self._supported_modes is None:
            try:
                reply = self._exec(self.GET_SUPPORTED_MODES).stdout or ""
                mask = int("".join(reversed(reply.split())), 16)
                self._supported_modes = [mode for mode in range(mask.bit_length()) if mask >> mode & 1]
            except (RuntimeError, ValueError):
                self._supported_modes = list(self.DEFAULT_FAN_MODES)
        return self._supported_modes

    @property
    def zone_count(self) -> int:
        """The number of fan zones this board has, discovered once by probing the failsafe flag upward.

        There is no command that reports the zone layout, so the count is found by reading a per-zone flag
        for zone 1, 2, 3 ... and stopping at the first zone the BMC does not have (Part 5.1). The failsafe
        flag is used rather than the manual mode flag because it is unrelated to the lever `start()` is
        about to operate, so probing cannot disturb the state being established. A board that answers for
        no zone at all leaves nothing to validate against, so the firmware bound stands and the BMC rejects
        a zone it does not have.
        """
        if self._zone_count is None:
            count = 0
            for zone in range(self.FANCTL_COUNT):
                try:
                    self._exec(self.OEM_PREFIX + [self.OEM_OP_READ_FAILSAFE, self._manual_zone(zone)])
                except (RuntimeError, ValueError):
                    break
                count += 1
            self._zone_count = count or self.FANCTL_COUNT
        return self._zone_count

    def _clamp_level(self, level: int) -> int:
        """Raise a duty below the 5 % floor, so that a legal configuration cannot stop the fans.

        `Config` permits `min_level=0`, and a manual duty write has no floor of its own: the 15 % floor
        belongs to the BMC's automatic control, which a latched zone is no longer under. A written `0x00`
        would therefore reach the fans as a real 0 % with nothing regulating them.
        Args:
            level (int): the requested duty percentage
        Returns:
            int: the duty percentage actually written
        """
        return max(self.MIN_LEVEL, level)

    def _get_failsafe(self, zone: int) -> bool:
        """Return True if the BMC has forced the given zone to 100 % by failsafe."""
        r = self._exec(self.OEM_PREFIX + [self.OEM_OP_READ_FAILSAFE, self._manual_zone(zone)])
        return int(r.stdout.split()[-1], 16) == 1

    @staticmethod
    def _manual_zone(zone: int) -> str:
        """Convert an smfc (0-based) zone ID to the 1-based zone byte of the OEM manual/failsafe commands."""
        return f"0x{zone + 1:02x}"

    def _get_manual_mode(self, zone: int) -> bool:
        """Return True if manual fan mode is active in the given zone.

        The reply echoes the IANA ID of the OEM command back before the payload, so it reads
        `cf c2 00 <flag>` and the flag is the last byte.
        """
        r = self._exec(self.OEM_PREFIX + [self.OEM_OP_READ_MANUAL, self._manual_zone(zone)])
        return int(r.stdout.split()[-1], 16) == 1

    def _set_manual_mode(self, zone: int, enabled: bool) -> None:
        """Enable or disable manual fan mode in the given zone."""
        value = "0x01" if enabled else "0x00"
        self._exec(self.OEM_PREFIX + [self.OEM_OP_SET_MANUAL, self._manual_zone(zone), value])

    def start(self, zones: List[int]) -> bool:
        """Latch manual fan mode in the controlled zones and confirm it was accepted.

        This is also the recovery path, so it must tolerate being run again; re-latching an already latched
        zone is harmless. Only the controlled zones are latched: latching a zone smfc does not drive would
        freeze it at its current duty with nothing regulating it.

        The base fan mode is deliberately not written here: on this stack it would clear manual mode on every
        zone. The latched zones are recorded so that `end()` releases exactly what was acquired, without
        depending on the caller resolving the same zone list again during interpreter shutdown.
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
        beyond = [zone for zone in zones if zone >= self.zone_count]
        if beyond:
            raise ValueError(f"IPMI zone(s) {beyond} do not exist on this board, which has {self.zone_count} "
                             f"zone(s) (see doc/X14H14_MANUAL_FANCONTROL.md, Part 5.1).")
        latched: List[int] = []
        for zone in zones:
            self._set_manual_mode(zone, True)
            # Read the flag back: an accepted command is not proof that the zone is latched, and smfc must not
            # pretend to control a zone that the BMC still drives itself. The stack was identified by probe, so
            # a refusal here means the zone does not exist or the BMC rejected the command - not a wrong stack.
            if not self._get_manual_mode(zone):
                self.latched_zones = sorted(set(self.latched_zones) | set(latched))
                raise RuntimeError(f"IPMI zone {zone} did not accept manual fan mode (see "
                                   f"doc/X14H14_MANUAL_FANCONTROL.md, Part 3.5).")
            latched.append(zone)
        self.latched_zones = sorted(set(self.latched_zones) | set(latched))
        return False

    def check_fan_mode(self, zones: List[int]) -> ControlStatus:
        """Report whether manual fan mode is still latched in all controlled zones.

        The manual flag is not sticky: a BMC reboot, a firmware update or a fan mode change made from any
        other interface clears it, and the BMC takes the fans back within about a second. The base fan mode is
        read as well, but only to keep the snapshot cache populated - it plays no part in the decision here,
        and in particular nothing about the zone map is inferred from it (Part 3.4: an unsupported mode is
        accepted silently and reads back correctly while a different fan table is loaded).
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
            pinned = [zone for zone in zones if self._get_failsafe(zone)]
        except (RuntimeError, ValueError) as e:
            return ControlStatus(ControlState.LOST, f"Manual fan mode could not be read: {e}", -1, confirmed=False)
        for zone in zones:
            self._failsafe_count[zone] = self._failsafe_count.get(zone, 0) + 1 if zone in pinned else 0
        if lost:
            return ControlStatus(ControlState.LOST, f"Manual fan mode was cleared in IPMI zone(s) {lost}", fan_mode)
        if pinned:
            return ControlStatus(ControlState.LOST, self._failsafe_detail(pinned), fan_mode)
        return ControlStatus(ControlState.OK, "", fan_mode)

    def _failsafe_detail(self, pinned: List[int]) -> str:
        """Compose the user-facing reason for a zone the BMC holds at 100 %.

        Manual mode is still latched, so nothing in the lever explains it, and re-acquiring cannot win the
        zone back: failsafe outranks manual mode and the BMC discards every duty written to that zone until
        the trip clears. The cause is only named once it has persisted, so that a single poll landing on a
        transient trip does not send the user after a fan that is not faulty - on a board whose fans turn
        slower than the tacho can resolve, a healthy fan reads as 0 RPM and trips failsafe by itself.
        Args:
            pinned (List[int]): IPMI zones whose failsafe flag is set
        Returns:
            str: the reason, logged verbatim by `Service`
        """
        settled = [zone for zone in pinned if self._failsafe_count.get(zone, 0) >= self.FAILSAFE_REPORT_AFTER]
        if settled:
            return (f"IPMI zone(s) {settled} are held at 100% by the BMC failsafe, which outranks manual fan "
                    f"mode, so the fan duty smfc writes is discarded and restoring fan control cannot "
                    f"recover it. A fan reading 0 RPM is the usual trigger, and a fan that turns slower than "
                    f"the BMC tacho can resolve reads as 0 while running normally (see "
                    f"doc/X14H14_MANUAL_FANCONTROL.md, Part 2 and Part 3.1)")
        return f"IPMI zone(s) {pinned} are not following the fan duty smfc wrote"

    def end(self, zones: List[int], level: int) -> None:
        """Apply the exit fan level to the configured zones, then release manual fan mode in all zones,
        restoring automatic BMC fan control.

        This platform behaves differently from the others: manual mode is an explicit OEM state that would stay
        latched forever if it were not released, leaving every zone frozen at the exit level with nothing
        regulating it. The release therefore runs on every exit path: with `exit_level=-1`, when no level
        is written at all, and equally when the level write itself fails. Releasing hands the fans back to
        the BMC, so the exit level is only a transition here - within about a second the BMC applies its own
        curve. Note that the BMC regulates on CPU and system sensors only, so drive temperatures are not
        part of that loop.
        Args:
            zones (List[int]): configured IPMI zones the exit level is applied to
            level (int): fan level in % (0-100), or a negative value to leave the levels unchanged
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem
        """
        # Apply the exit level first: releasing manual mode first would hand control to the BMC and make the
        # level write a no-op. The release is in a `finally`, so a failing level write cannot skip it: the
        # level is optional, the release is not - a latch that stays armed leaves the zones frozen at their
        # last duty with nothing regulating them.
        try:
            super().end(zones, level)
        finally:
            # Release manual mode with the all-zones shortcut, so nothing stays latched even if smfc latched
            # a zone in an earlier run. Firmware that rejects the shortcut is handled per zone, over the
            # zones start() actually latched.
            try:
                self._exec(["raw", "0x30", "0x70", "0x66", "0x02", "0x00"])
            except RuntimeError:
                for zone in self.latched_zones or zones:
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
            FanLevelUnavailable: the zone has no fan sensor configured, so its level cannot be read at all
            RuntimeError: ipmitool execution problem
        """
        validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        sensor = self.zone_sensors.get(zone)
        if sensor is None:
            raise FanLevelUnavailable(f"IPMI zone {zone} has no fan sensor configured "
                                     f"(see [Ipmi] x14_zone_sensors=).")
        r = self._exec(["raw", "0x30", "0x70", "0x88", f"0x{sensor:02x}"])
        duty = int(r.stdout.split()[0], 16)
        if duty == 0xFF:
            raise ValueError(f"Fan duty is unavailable in IPMI zone {zone}.")
        return duty

    def set_fan_level(self, zone: int, level: int) -> None:
        """Set the fan duty cycle percentage for the given zone, never below the 5 % floor."""
        # Selector 0x01 writes a duty, 0x00 reads one. The value is a percentage (0x00-0x64), and manual
        # mode must be latched first (start()) or the automatic loop overwrites it.
        validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        validate_input_range(level, "level", 0, 100)
        written = self._clamp_level(level)
        self._exec(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{written:02x}"])

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        """Set the same fan duty cycle percentage for all given zones, never below the 5 % floor."""
        # Selector 0x01 writes a duty, 0x00 reads one. The value is a percentage (0x00-0x64), and manual
        # mode must be latched first (start()) or the automatic loop overwrites it.
        for zone in zone_list:
            validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
        validate_input_range(level, "level", 0, 100)
        written = self._clamp_level(level)
        for zone in zone_list:
            self._exec(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{written:02x}"])


class X14AtenPlatform(GenericPlatform):
    """Platform implementation for Supermicro X14/H14 motherboards running the ATEN BMC firmware stack.

    ATEN is the firmware line Supermicro shipped through X9-X13, so the duty commands are byte-for-byte
    `GenericPlatform`'s and are inherited unchanged - that is the reason this is the one platform that does
    not subclass `Platform` directly. What differs is the *lever*: the automatic control loop re-asserts its
    own duty in every fan mode, so FULL fan mode does not hand the fans over. Only the global bypass flag
    suspends the loop, which is why field reports from H14 owners describe levels drifting back within a
    second (`doc/X14H14_MANUAL_FANCONTROL.md`, Part 4.1).

    Two properties of that bypass shape everything here:

    - It is **global**: every zone is bypassed, not only the driven ones. A zone the user did not configure
      sits frozen at its last duty with nothing regulating it. This is documented in `README.md` rather than
      handled at runtime - there is no reliable way to learn how many zones a board has, and driving zones
      the user did not configure would move fans nobody asked smfc to move.
    - It is **write-only**: no command reads it back, so `check_fan_mode()` infers it from a duty read-back
      instead of polling a flag (Part 4.5).

    The base fan mode is read but never written: it persists across a BMC restart while the bypass does not,
    so a board left in Full Speed comes back at 100 % with nothing to stop it (Part 4.1).
    """

    ENFORCES_FULL_MODE: bool = False
    MIN_LEVEL: int = 5              # Never write a duty below this, see _clamp_level()
    PINNED_LEVEL: int = 100         # A zone stuck here is most likely a fan-failure trip (Part 5.2)
    PINNED_REPORT_AFTER: int = 3    # Consecutive pinned observations before the fan-failure hint is reported
    BYPASS_ON: List[str] = ["raw", "0x30", "0x70", "0x66", "0x02", "0x01"]
    BYPASS_OFF: List[str] = ["raw", "0x30", "0x70", "0x66", "0x02", "0x00"]
    CC_LOCKDOWN: int = 0xD4         # System Lockdown is enabled in the BMC
    CC_UNSUPPORTED: int = 0xCC      # This firmware build has no fan duty sub-command at all

    bypassed_zones: List[int]           # Zones recorded by start(), released by end()
    _expected: Dict[int, Set[int]]      # IPMI zone -> duty bytes the BMC may report back
    _pinned_count: Dict[int, int]       # IPMI zone -> consecutive observations pinned at 100%

    def __init__(self, name: str, exec_ipmitool: Callable[[List[str]], subprocess.CompletedProcess]) -> None:
        """Initialize the platform and the read-back bookkeeping `check_fan_mode()` needs.
        Args:
            name (str): platform name (e.g. from BMC product name or config)
            exec_ipmitool (Callable): function that executes ipmitool commands
        """
        super().__init__(name, exec_ipmitool)
        self.bypassed_zones = []
        self._expected = {}
        self._pinned_count = {}

    @staticmethod
    def accepted(level: int) -> Set[int]:
        """Duty bytes the BMC may report back after `level` was written (Part 4.4).

        ATEN firmware has two duty paths and the board name does not say which is active: an 8-bit PWM path
        that clamps to 5-100 and truncates twice, and a path that stores the percentage exactly. The two never
        differ by more than one count, so the read-back is compared against a set rather than a single
        computed value. Getting that wrong is not cosmetic in either direction - a single expectation makes
        every duty that is not a multiple of 20 mismatch on every poll on one of the two paths, which is a
        permanent false "control lost".
        Args:
            level (int): the duty percentage that was written
        Returns:
            Set[int]: every duty byte that means "our value is still in place"
        """
        pwm = max(5, min(100, level))
        return {((pwm * 255) // 100) * 100 // 255, pwm, max(0, min(100, level))}

    def _clamp_level(self, level: int) -> int:
        """Raise a duty below the 5 % floor, so that a legal configuration cannot stop the fans.

        `Config` permits `min_level=0`, and on the PWM duty path that is harmless - the firmware clamps it to
        5 % itself. Part 4.4 states that the percent path has **no floor**, so on X14SDW / X14SDV a written
        `0x00` may reach the fans as a real 0 % while the BMC's own thermal loop is suspended by our bypass
        and nothing else regulates them. smfc cannot identify the active path, so it never writes below 5 %.
        Args:
            level (int): the requested duty percentage
        Returns:
            int: the duty percentage actually written
        """
        return max(self.MIN_LEVEL, level)

    def start(self, zones: List[int]) -> bool:
        """Suspend the BMC's automatic fan control loop with the global bypass flag.

        One command covers every zone, so the zone list is only recorded for `end()`. The base fan mode is
        deliberately never written (Part 4.1). Idempotent by construction, which is what the recovery path in
        `Service._check_fan_mode()` needs.
        Args:
            zones (List[int]): IPMI zones smfc controls (recorded for the release in `end()`)
        Returns:
            bool: always False, the fan mode is never written on this platform (so no `fan_mode_delay` is due)
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem, System Lockdown, or a build without fan duty control
            ValueError: invalid input parameter
        """
        for zone in zones:
            validate_input_range(zone, "zone", 0, 100)
        try:
            self._exec(self.BYPASS_ON)
        except IpmiError as e:
            if e.completion_code == self.CC_LOCKDOWN:
                raise IpmiError("System Lockdown is enabled in the BMC, so it rejects fan duty control (0x30 "
                                "0x70 0x66 rejected with 0xD4); disable it in the BMC web UI (see "
                                "doc/X14H14_MANUAL_FANCONTROL.md, Part 4.1).", e.completion_code) from e
            if e.completion_code == self.CC_UNSUPPORTED:
                raise IpmiError("This BMC build implements no IPMI fan duty control (0x30 0x70 0x66 rejected "
                                "with 0xCC); only the base fan mode can be set (see "
                                "doc/X14H14_MANUAL_FANCONTROL.md, Part 4.6).", e.completion_code) from e
            raise
        self.bypassed_zones = sorted(set(self.bypassed_zones) | set(zones))
        return False

    def check_fan_mode(self, zones: List[int]) -> ControlStatus:
        """Report whether the bypass is still in effect, by reading each zone's duty back.

        The bypass flag is write-only, so there is no flag to poll: the detector is the Part 4.5 comparison of
        a duty read against what smfc wrote. The read happens before this pass's write, because reading
        straight after our own write returns our own value regardless of the bypass - the automatic loop needs
        about a second to overwrite. Before the first duty write there is nothing to compare, so the first
        call reports OK; `Service` writes levels on every iteration, so that window is one poll.

        The accepted values come from `set_fan_level()`/`set_multiple_fan_levels()` recording what they
        actually wrote, not from `Service.applied_levels`: the platform must not depend on its caller's
        bookkeeping.

        The cost of comparing against a set is that a genuine takeover landing within one count of our own
        value is missed for a single poll. That is not a real exposure - the automatic curve keeps moving, so
        the next poll sees it.
        Args:
            zones (List[int]): IPMI zones smfc controls
        Returns:
            ControlStatus: the observed control state
        Raises:
            FileNotFoundError: ipmitool cannot be found
        """
        mismatched: Dict[int, int] = {}
        try:
            # Read purely to populate the snapshot cache; it plays no part in the decision.
            fan_mode = self.get_fan_mode()
            for zone in zones:
                expected = self._expected.get(zone)
                if expected is None:
                    continue
                actual = self.get_fan_level(zone)
                if actual in expected:
                    self._pinned_count[zone] = 0
                    continue
                mismatched[zone] = actual
                if actual == self.PINNED_LEVEL:
                    self._pinned_count[zone] = self._pinned_count.get(zone, 0) + 1
                else:
                    self._pinned_count[zone] = 0
        except (RuntimeError, ValueError) as e:
            return ControlStatus(ControlState.LOST, f"Fan duty could not be read: {e}", -1, confirmed=False)
        if not mismatched:
            return ControlStatus(ControlState.OK, "", fan_mode)
        return ControlStatus(ControlState.LOST, self._lost_detail(mismatched), fan_mode)

    def _lost_detail(self, mismatched: Dict[int, int]) -> str:
        """Compose the user-facing reason for a lost bypass.

        A zone reading 100 % that smfc did not ask for is most likely a fan-failure trip rather than a lost
        bypass, but the two boards differ and smfc cannot tell which it is on: on the H14 boards the
        fan-failure check runs *before* the bypass check, so a trip forces 100 % on every tick and re-arming
        can never win it back, while on X14SDW / X14SDV the bypass is checked first and holds through a fan
        failure (Part 5.2). The cause is therefore named as likely, not asserted, and only after it has
        persisted - without this the log repeats "control lost" forever and points the user at the wrong thing.
        Args:
            mismatched (Dict[int, int]): IPMI zone -> the duty that was read back
        Returns:
            str: the reason, logged verbatim by `Service`
        """
        pinned = [z for z in sorted(mismatched) if self._pinned_count.get(z, 0) >= self.PINNED_REPORT_AFTER]
        if pinned:
            return (f"IPMI zone {pinned[0]} is pinned at 100% and is most likely a fan failure rather than a "
                    f"lost bypass; on boards where fan failure outranks the bypass, re-arming cannot recover "
                    f"it (see doc/X14H14_MANUAL_FANCONTROL.md, Part 4.6 and Part 5.2)")
        levels = ", ".join(f"{z}={mismatched[z]}%" for z in sorted(mismatched))
        return f"Fan duty was overwritten by the BMC automatic fan control loop in IPMI zone(s) {levels}"

    def end(self, zones: List[int], level: int) -> None:
        """Apply the exit fan level, then release the global bypass, restoring automatic BMC fan control.

        The release runs on every exit path: with `exit_level=-1`, when no level is written at all, and
        equally when the level write itself fails. The bypass would otherwise stay armed and leave every zone
        on the board - not only the configured ones - frozen at its last duty with nothing regulating it
        (Part 4.1). The exit level is only a transition here - within about a second the
        BMC applies its own curve, which regulates on CPU and system sensors only, so drive temperatures are
        not part of it.
        Args:
            zones (List[int]): configured IPMI zones the exit level is applied to
            level (int): fan level in % (0-100), or a negative value to leave the levels unchanged
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem
        """
        # Apply the exit level first: releasing the bypass first would let the automatic loop overwrite it.
        # The release is in a `finally`, so a failing level write cannot skip it: the level is optional, the
        # release is not - a bypass that stays armed leaves every zone on the board frozen at its last duty
        # with the BMC's own thermal loop suspended.
        try:
            super().end(zones, level)
        finally:
            self._exec(self.BYPASS_OFF)

    def set_fan_level(self, zone: int, level: int) -> None:
        """Set the fan duty cycle percentage for the given zone, never below the 5 % floor."""
        validate_input_range(zone, "zone", 0, 100)
        validate_input_range(level, "level", 0, 100)
        written = self._clamp_level(level)
        super().set_fan_level(zone, written)
        self._expected[zone] = self.accepted(written)

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        """Set the same fan duty cycle percentage for all given zones, never below the 5 % floor."""
        for zone in zone_list:
            validate_input_range(zone, "zone", 0, 100)
        validate_input_range(level, "level", 0, 100)
        written = self._clamp_level(level)
        super().set_multiple_fan_levels(zone_list, written)
        for zone in zone_list:
            self._expected[zone] = self.accepted(written)


# End.
