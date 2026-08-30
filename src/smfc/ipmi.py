#
#   ipmi.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.Ipmi() class implementation.
#
import re
import subprocess
import time
from typing import List, Optional
from smfc.log import Log
from smfc.platform import FanMode, IpmiError, Platform, get_fan_mode_name
from smfc.platform_factory import create_platform
from smfc.config import IpmiConfig, Config, PlatformName


# `ipmitool` reports the IPMI completion code of a rejected command in its failure line, e.g.
# `Unable to send RAW command (channel=0x0 netfn=0x2e lun=0x0 cmd=0x4 rsp=0xc1): Invalid command`.
RSP_CODE_RE = re.compile(r"rsp=0x([0-9a-fA-F]{1,2})")


def parse_completion_code(stderr: str) -> Optional[int]:
    """Extract the IPMI completion code from an `ipmitool` error message.

    Parsed in exactly one place: matching the message text at the call sites would work too, but it
    leaves a latent trap - a future change to the wording would silently turn a fatal condition into a
    wrong-stack guess, and on X14/H14 the wrong stack applies the wrong lever to the fans
    (see `doc/X14H14_MANUAL_FANCONTROL.md`, Part 1.3).
    Args:
        stderr (str): stderr of the failed `ipmitool` command
    Returns:
        Optional[int]: the completion code (e.g. 0xC1), or None if the message carries none
    """
    m = RSP_CODE_RE.search(stderr)
    return int(m.group(1), 16) if m else None


class Ipmi:
    """IPMI interface class can set/get IPMI fan mode, and can set IPMI fan level using ipmitool."""

    config: IpmiConfig              # Configuration reference
    log: Log                        # Reference to a Log class instance
    sudo: bool                      # Use `sudo` command for `ipmitool` command
    bmc_device_id: int              # BMC device ID
    bmc_device_rev: int             # BMC device revision
    bmc_firmware_rev: str           # BMC firmware revision
    bmc_ipmi_version: str           # BMC IPMI version
    bmc_manufacturer_id: int        # BMC manufacturer ID
    bmc_manufacturer_name: str      # BMC manufacturer name
    bmc_product_id: int             # BMC product ID
    bmc_product_name: str           # BMC product name
    platform: Platform              # Platform implementation for fan control

    # Backward-compatible fan mode constants (use FanMode enum for new code):
    STANDARD_MODE: int = FanMode.STANDARD
    FULL_MODE: int = FanMode.FULL
    OPTIMAL_MODE: int = FanMode.OPTIMAL
    PUE_MODE: int = FanMode.PUE
    HEAVY_IO_MODE: int = FanMode.HEAVY_IO

    # Constant values for IPMI fan zones:
    CPU_ZONE: int = 0
    HD_ZONE: int = 1

    # Constant values for the results of IPMI operations:
    SUCCESS: int = 0
    ERROR: int = -1

    # Timeout value for BMC initialization (seconds). A real `mc reset cold` on an X11SCH-LN4F takes
    # ~102 s (≈30 s interface-down + ≈69 s sensors `ns`) before the fan subsystem settles; 180 s leaves
    # headroom for a no-overlap reset while costing nothing on the happy path (the gate exits as soon as
    # the fans report live data).
    BMC_INIT_TIMEOUT: float = 180.0

    def __init__(self, log: Log, cfg: IpmiConfig, sudo: bool, *,
                 in_client: bool = False, bmc_init_timeout: float = BMC_INIT_TIMEOUT) -> None:
        """Initialize the Ipmi class with a log class and with a configuration.
        Args:
            log (Log): a Log class instance
            cfg (IpmiConfig): IPMI configuration
            sudo (bool): sudo flag
            in_client (bool): if True, skip the fan sensor readiness gate of the BMC startup wait (read-only
                              consumers like smfc-client do not need the fan subsystem to be settled)
            bmc_init_timeout (float): override for the BMC-not-ready retry timeout (seconds);
                                      defaults to Ipmi.BMC_INIT_TIMEOUT (180 s); pass 0 to disable retries
        Raises:
            ValueError: invalid input parameters
            FileNotFoundError: ipmitool not found
            RuntimeError: ipmitool execution error
        """
        # Store config reference
        self.config = cfg
        self.log = log
        self.sudo = sudo

        # Validate configuration
        # Check 1: fan_mode_delay must be positive.
        if cfg.fan_mode_delay < 0:
            raise ValueError(f"Negative fan_mode_delay= parameter ({cfg.fan_mode_delay})")
        # Check 2: fan_level_delay must be positive.
        if cfg.fan_level_delay < 0:
            raise ValueError(f"Negative fan_level_delay= parameter ({cfg.fan_level_delay})")
        # Check 3: ipmitool_timeout must not be negative (0 = wait indefinitely).
        if cfg.ipmitool_timeout < 0:
            raise ValueError(f"Negative ipmitool_timeout= parameter ({cfg.ipmitool_timeout})")
        # Check 4: wait until the BMC is ready. Two conditions must hold, because after a cold boot the
        # IPMI command interface answers well before the fan subsystem has settled:
        #   (a) `sdr` executes successfully (rc=0)  -> the IPMI command interface is up;
        #   (b) a fan sensor reports live data       -> the fan subsystem has settled.
        # During the (a)-but-not-(b) window (up to ~2 minutes on a cold BMC) every sensor reads
        # `disabled`/`no reading` with state `ns`, and fan-level writes are silently forced to 100%.
        # Starting the control loop then leaves a low-polling zone stuck at 100% until its next poll.
        # The read-only `sdr` poll waits this out without touching the fans (a write-readback probe could
        # itself be clobbered mid-window; a fixed sleep is fragile). Read-only clients skip (b) so they
        # never block on a cold BMC. Both conditions share the 180 second budget in 5 second steps.
        # The budget is exhausted by whichever comes first: the 5 second steps this loop takes, or the same
        # number of seconds of wall clock. The step count alone is what the budget always meant, but every
        # `sdr` call may now cost up to `ipmitool_timeout` seconds, so counting only the sleeps would let a
        # slow BMC stretch a "180 second" budget into many minutes of startup. The step count is kept as the
        # second condition because the wall clock alone does not advance when `time.sleep()` is stubbed out.
        bmc_deadline = time.monotonic() + bmc_init_timeout
        bmc_timeout = 0.0
        while True:
            try:
                # May raise FileNotFoundError if ipmitool is not found.
                r = self._exec_ipmitool(["sdr"])
            except RuntimeError as e:
                # In case of ipmitool error we try to wait BMC initialization in maximum 180 seconds
                # (in 5 seconds steps), otherwise reraise the exception.
                if "ipmitool" in e.args[0]:
                    self.log.msg(Log.LOG_INFO, "BMC is not ready, waiting 5 seconds.")
                    time.sleep(5)
                    bmc_timeout += 5
                    if bmc_timeout < bmc_init_timeout and time.monotonic() < bmc_deadline:
                        continue
                raise
            # (a) holds (no exception). Now wait for (b): the fan subsystem to settle. The except branch
            # above never falls through here (it either re-raises or `continue`s). Clients skip (b).
            if in_client or self._fan_sensors_ready(r.stdout):
                break
            if bmc_timeout >= bmc_init_timeout or time.monotonic() >= bmc_deadline:
                self.log.msg(Log.LOG_INFO, "BMC fan sensors still not ready after timeout, continuing.")
                break
            self.log.msg(Log.LOG_INFO, "BMC fan sensors are not ready, waiting 5 seconds.")
            time.sleep(5)
            bmc_timeout += 5

        # Retrieve and parse BMC information.
        r = self._exec_ipmitool(["bmc", "info"])
        fields: dict = {}
        for line in r.stdout.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
        try:
            self.bmc_device_id = int(fields["Device ID"])
            self.bmc_device_rev = int(fields["Device Revision"])
            self.bmc_firmware_rev = fields["Firmware Revision"]
            self.bmc_ipmi_version = fields["IPMI Version"]
            self.bmc_manufacturer_id = int(fields["Manufacturer ID"])
            self.bmc_manufacturer_name = fields["Manufacturer Name"]
            self.bmc_product_id = int(fields["Product ID"].split()[0])
            self.bmc_product_name = fields["Product Name"]
        except (KeyError, ValueError, IndexError) as e:
            raise RuntimeError(f"Cannot parse BMC info: {e}") from e

        # Initialize platform-specific fan control.
        platform_name = self.config.platform_name
        if platform_name == PlatformName.AUTO:
            platform_name = self.bmc_product_name
        self.platform = create_platform(platform_name, self._exec_ipmitool)

        # Print the configuration out at CONFIG log level.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, "Ipmi module was initialized with:")
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_IPMI_COMMAND} = {self.config.command}")
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_IPMI_FAN_MODE_DELAY} = {self.config.fan_mode_delay}")
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_IPMI_FAN_LEVEL_DELAY} = {self.config.fan_level_delay}")
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_IPMI_REMOTE_PARAMETERS} = {self.config.remote_parameters}")
            timeout_suffix = "" if self.config.ipmitool_timeout \
                else " (no timeout, ipmitool may block indefinitely)"
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_IPMI_IPMITOOL_TIMEOUT} = "
                                         f"{self.config.ipmitool_timeout}{timeout_suffix}")
            # `generic_x14` names a platform *family* whose class is chosen by a runtime probe, so it needs
            # the resolved class name just as much as `auto` does - it is the only place the user can see
            # which of the two 14th generation BMC firmware stacks was detected.
            named_families = (PlatformName.AUTO, PlatformName.GENERIC_X14)
            platform_suffix = f" -> {type(self.platform).__name__}" \
                if self.config.platform_name in named_families else ""
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_IPMI_PLATFORM_NAME} = "
                                         f"{self.config.platform_name}{platform_suffix}")
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_IPMI_ENFORCE_FAN_MODE} = {self.config.enforce_fan_mode}")
            exit_level_suffix = " (fan levels are left unchanged at exit)" \
                if self.config.exit_level == Config.EXIT_LEVEL_NONE else ""
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_IPMI_EXIT_LEVEL} = "
                                         f"{self.config.exit_level}{exit_level_suffix}")
            self.log.msg(Log.LOG_CONFIG, "BMC information:")
            self.log.msg(Log.LOG_CONFIG, f"   manufacturer name (id) = {self.bmc_manufacturer_name} "
                                         f"({self.bmc_manufacturer_id})")
            self.log.msg(Log.LOG_CONFIG, f"   product name (id) = {self.bmc_product_name} ({self.bmc_product_id})")
            self.log.msg(Log.LOG_CONFIG, f"   IPMI version = {self.bmc_ipmi_version}")
            self.log.msg(Log.LOG_CONFIG, f"   firmware revision = {self.bmc_firmware_rev}")

    @staticmethod
    def _fan_sensors_ready(sdr_output: str) -> bool:
        """Return True if the BMC fan sensors report live data in `ipmitool sdr` output.

        After a cold boot `sdr` returns rc=0 while every sensor still reads `disabled`/`no reading`
        with state `ns` and fan-level writes are silently forced to 100%. A fan sensor reporting a
        live reading (any state other than `ns`, e.g. `500 RPM | ok`) marks the fan subsystem as
        settled. At least one fan sensor is required so that an unpopulated header that stays `ns`
        forever does not force us to wait for the full timeout.

        A sensor counts as a fan when `FAN` appears anywhere in its name. Boards spell the names
        differently (`FAN1`, `FANA`, `CPU_FAN1`, `SYS_FAN1`, `SYSFAN1`, `FAN_CPU1`), and no other
        sensor of a Supermicro `sdr` list carries `FAN` in its name, so a plain substring match
        covers every naming convention without a per-board special case.
        Args:
            sdr_output (str): stdout of `ipmitool sdr`
        Returns:
            bool: True if at least one fan sensor reports live data
        """
        for line in sdr_output.splitlines():
            fields = [f.strip() for f in line.split("|")]
            if len(fields) < 3:
                continue
            name, state = fields[0], fields[2]
            if "FAN" in name.upper() and state.lower() != "ns":
                return True
        return False

    def _exec_ipmitool(self, args: List[str]) -> subprocess.CompletedProcess:
        """Execute `ipmitool` command.
        Args:
            args (List[str]): command line parameters
        Returns:
            subprocess.CompletedProcess: result of the executed subprocess
        Raises:
            FileNotFoundError: ipmitool cannot be found
            IpmiError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard),
                or it did not finish within `ipmitool_timeout` seconds; a RuntimeError subclass carrying the
                IPMI completion code when the BMC returned one
        """
        r: subprocess.CompletedProcess  # result of the executed process
        arguments: List[str]  # Command arguments

        # Construct command line parameters.
        arguments = []
        # Add `sudo` if needed.
        if self.sudo:
            arguments.append("sudo")
        # Add `ipmitool` path.
        arguments.append(self.config.command)
        # Add remote parameters if needed.
        if self.config.remote_parameters:
            arguments.extend(self.config.remote_parameters.split())
        # Add additional command line parameters from caller.
        arguments.extend(args)
        if hasattr(self, "log") and self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f"ipmitool exec: {' '.join(arguments)}")
        # May raise FileNotFoundError if ipmitool is not found.
        # `timeout=None` means "wait indefinitely", which is what ipmitool_timeout=0 selects. A blocked
        # ipmitool (classically a wedged /dev/ipmi0) would otherwise park the control loop inside this call
        # with nothing regulating the fans behind it, so a timed-out run is reported as an ordinary IPMI
        # failure and handled by the same paths as any other one.
        timeout = self.config.ipmitool_timeout or None
        try:
            r = subprocess.run(arguments, check=False, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise IpmiError(f"ipmitool timed out after {self.config.ipmitool_timeout} seconds: "
                            f"{' '.join(arguments)}.") from e
        if hasattr(self, "log") and self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f"ipmitool result: rc={r.returncode} stdout='{r.stdout.strip()}'")
        # Check error code.
        if r.returncode != 0:
            if self.sudo and "sudo" in r.stderr:
                raise IpmiError(f"sudo error ({r.returncode}): {r.stderr}.")
            raise IpmiError(f"ipmitool error ({r.returncode}): {r.stderr}.", parse_completion_code(r.stderr))
        return r

    def get_fan_mode(self) -> int:
        """Get the current IPMI fan mode.
        Returns:
            int: fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
            ValueError: output of the ipmitool cannot be interpreted/converted
        """
        return self.platform.get_fan_mode()

    @staticmethod
    def get_fan_mode_name(mode: int) -> str:
        """Get the name of the specified IPMI fan mode.
        Args:
            mode (int): fan mode
        Returns:
            str: name of the fan mode ('UNKNOWN', 'STANDARD', 'FULL', 'OPTIMAL', 'PUE', 'HEAVY IO')
        """
        return get_fan_mode_name(mode)

    def set_fan_mode(self, mode: int) -> None:
        """Set the IPMI fan mode.
        Args:
            mode (int): fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        if hasattr(self, "log") and self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f"Setting fan mode to {self.get_fan_mode_name(mode)} ({mode})")
        self.platform.set_fan_mode(mode)
        # Give time for IPMI system/fans to apply changes in the new fan mode.
        time.sleep(self.config.fan_mode_delay)

    def set_fan_level(self, zone: int, level: int) -> None:
        """Set the fan level in the specified IPMI zone.
        Args:
            zone (int): IPMI zone
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        if hasattr(self, "log") and self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f"Setting fan level: zone={zone} level={level}%")
        self.platform.set_fan_level(zone, level)
        # Give time for IPMI and fans to spin up/down.
        time.sleep(self.config.fan_level_delay)

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        """Set the fan level in multiple IPMI zones.
        Args:
            zone_list (List[int]): List of IPMI zones
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        self.platform.set_multiple_fan_levels(zone_list, level)
        # Give time for IPMI and fans to spin up/down.
        time.sleep(self.config.fan_level_delay)

    def get_fan_level(self, zone: int) -> int:
        """Get the current fan level in a specific IPMI zone.
        Args:
            zone (int): fan zone (CPU_ZONE, HD_ZONE)
        Returns:
            int: fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        return self.platform.get_fan_level(zone)


# End.
