#
#   ipmi.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.Ipmi() class implementation.
#
import subprocess
import time
from configparser import ConfigParser
from typing import List
from smfc.log import Log
from smfc.platform import FanMode, Platform, PlatformName
from smfc.platform_factory import create_platform


class Ipmi:
    """IPMI interface class can set/get IPMI fan mode, and can set IPMI fan level using ipmitool."""

    log: Log                    # Reference to a Log class instance
    command: str                # Full path for ipmitool command.
    fan_mode_delay: float       # Delay time after execution of IPMI set fan mode function
    fan_level_delay: float      # Delay time after execution of IPMI set fan level function
    remote_parameters: str      # Remote IPMI parameters
    sudo: bool                  # Use `sudo` command for `ipmitool` command
    bmc_device_id: int          # BMC device ID
    bmc_device_rev: int         # BMC device revision
    bmc_firmware_rev: str       # BMC firmware revision
    bmc_ipmi_version: str       # BMC IPMI version
    bmc_manufacturer_id: int    # BMC manufacturer ID
    bmc_manufacturer_name: str  # BMC manufacturer name
    bmc_product_id: int         # BMC product ID
    bmc_product_name: str       # BMC product name
    platform_name: str          # Platform name (from config or auto-detected)
    platform: Platform          # Platform implementation for fan control

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

    # Constant values for the configuration parameters.
    CS_IPMI: str = "Ipmi"
    CV_IPMI_COMMAND: str = "command"
    CV_IPMI_FAN_MODE_DELAY: str = "fan_mode_delay"
    CV_IPMI_FAN_LEVEL_DELAY: str = "fan_level_delay"
    CV_IPMI_REMOTE_PARAMETERS: str = "remote_parameters"
    CV_IPMI_PLATFORM_NAME: str = "platform_name"

    # Timeout value for BMC initialization (seconds).
    BMC_INIT_TIMEOUT: float = 120.0

    def __init__(self, log: Log, config: ConfigParser, sudo: bool) -> None:
        """Initialize the Ipmi class with a log class and with a configuration class.
        Args:
            log (Log): a Log class instance
            config (ConfigParser): a ConfigParser class instance
            sudo (bool): sudo flag
        Raises:
            ValueError: invalid input parameters
            FileNotFoundError: ipmitool not found
            RuntimeError: ipmitool execution error
        """
        # Set default or read from configuration
        self.log = log
        self.command = config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_COMMAND, "/usr/bin/ipmitool")
        self.fan_mode_delay = config[Ipmi.CS_IPMI].getint(Ipmi.CV_IPMI_FAN_MODE_DELAY, fallback=10)
        self.fan_level_delay = config[Ipmi.CS_IPMI].getint(Ipmi.CV_IPMI_FAN_LEVEL_DELAY, fallback=2)
        self.remote_parameters = config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_REMOTE_PARAMETERS, fallback="")
        self.platform_name = config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_PLATFORM_NAME, fallback=PlatformName.AUTO)
        self.sudo = sudo

        # Validate configuration
        # Check 1: a valid command can be executed successfully and wait if BMC is not ready.
        bmc_timeout = 0.0
        while True:
            try:
                # May raise FileNotFoundError if ipmitool is not found.
                self._exec_ipmitool(["sdr"])
                break
            except RuntimeError as e:
                # In case of ipmitool error we try to wait BMC initialization in maximum 120 seconds
                # (in 5 seconds steps), otherwise reraise the exception.
                if "ipmitool" in e.args[0]:
                    self.log.msg(Log.LOG_INFO, "BMC is not ready, waiting 5 seconds.")
                    time.sleep(5)
                    bmc_timeout += 5
                    if bmc_timeout < Ipmi.BMC_INIT_TIMEOUT:
                        continue
                raise

        # Check 2: fan_mode_delay must be positive.
        if self.fan_mode_delay < 0:
            raise ValueError(f"Negative fan_mode_delay= parameter ({self.fan_mode_delay})")
        # Check 3: fan_level_delay must be positive.
        if self.fan_level_delay < 0:
            raise ValueError(f"Negative fan_level_delay= parameter ({self.fan_level_delay})")

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
        if self.platform_name == PlatformName.AUTO:
            self.platform_name = self.bmc_product_name
        self.platform = create_platform(self.platform_name, self._exec_ipmitool)
        self.log.msg(Log.LOG_CONFIG, f"   platform = {self.platform.name} ({type(self.platform).__name__})")
        self.platform.set_fan_manual_mode()

        # Print the configuration out at CONFIG log level.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, "Ipmi module was initialized with:")
            self.log.msg(Log.LOG_CONFIG, f"   {Ipmi.CV_IPMI_COMMAND} = {self.command}")
            self.log.msg(Log.LOG_CONFIG, f"   {Ipmi.CV_IPMI_FAN_MODE_DELAY} = {self.fan_mode_delay}")
            self.log.msg(Log.LOG_CONFIG, f"   {Ipmi.CV_IPMI_FAN_LEVEL_DELAY} = {self.fan_level_delay}")
            self.log.msg(Log.LOG_CONFIG, f"   {Ipmi.CV_IPMI_REMOTE_PARAMETERS} = {self.remote_parameters}")
            self.log.msg(Log.LOG_CONFIG, f"   {Ipmi.CV_IPMI_PLATFORM_NAME} = {self.platform.name} "
                                         f"({type(self.platform).__name__})")
            self.log.msg(Log.LOG_CONFIG, "BMC information:")
            self.log.msg(Log.LOG_CONFIG, f"   manufacturer name and id = {self.bmc_manufacturer_name} "
                                         f"({self.bmc_manufacturer_id})")
            self.log.msg(Log.LOG_CONFIG, f"   product name and id = {self.bmc_product_name} ({self.bmc_product_id})")
            self.log.msg(Log.LOG_CONFIG, f"   IPMI version = {self.bmc_ipmi_version}")
            self.log.msg(Log.LOG_CONFIG, f"   firmware revision = {self.bmc_firmware_rev}")

    def _exec_ipmitool(self, args: List[str]) -> subprocess.CompletedProcess:
        """Execute `ipmitool` command.
        Args:
            args (List[str]): command line parameters
        Returns:
            subprocess.CompletedProcess: result of the executed subprocess
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        r: subprocess.CompletedProcess  # result of the executed process
        arguments: List[str]  # Command arguments

        # Construct command line parameters.
        arguments = []
        # Add `sudo` if needed.
        if self.sudo:
            arguments.append("sudo")
        # Add `ipmitool` path.
        arguments.append(self.command)
        # Add remote parameters if needed.
        if self.remote_parameters:
            arguments.extend(self.remote_parameters.split())
        # Add additional command line parameters from caller.
        arguments.extend(args)
        # May raise FileNotFoundError if ipmitool is not found.
        r = subprocess.run(arguments, check=False, capture_output=True, text=True)
        # Check error code.
        if r.returncode != 0:
            if self.sudo and "sudo" in r.stderr:
                raise RuntimeError(f"sudo error ({r.returncode}): {r.stderr}.")
            raise RuntimeError(f"ipmitool error ({r.returncode}): {r.stderr}.")
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
        fan_mode_name: str  # Name of the fan mode

        fan_mode_name = "UNKNOWN"
        if mode == FanMode.STANDARD:
            fan_mode_name = "STANDARD"
        elif mode == FanMode.FULL:
            fan_mode_name = "FULL"
        elif mode == FanMode.OPTIMAL:
            fan_mode_name = "OPTIMAL"
        elif mode == FanMode.PUE:
            fan_mode_name = "PUE"
        elif mode == FanMode.HEAVY_IO:
            fan_mode_name = "HEAVY IO"
        return fan_mode_name

    def set_fan_mode(self, mode: int) -> None:
        """Set the IPMI fan mode.
        Args:
            mode (int): fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        self.platform.set_fan_mode(mode)
        # Give time for IPMI system/fans to apply changes in the new fan mode.
        time.sleep(self.fan_mode_delay)

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
        self.platform.set_fan_level(zone, level)
        # Give time for IPMI and fans to spin up/down.
        time.sleep(self.fan_level_delay)

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
        time.sleep(self.fan_level_delay)

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
