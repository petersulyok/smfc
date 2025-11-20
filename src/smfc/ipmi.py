#
#   ipmi.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.Ipmi() class implementation.
#
import subprocess
import time
from configparser import ConfigParser
from typing import List, Dict
from smfc.log import Log
from smfc.platform import Platform, FanMode, create_platform


class Ipmi:
    """IPMI interface class can set/get IPMI fan mode, and can set IPMI fan level using ipmitool."""

    log: Log                    # Reference to a Log class instance
    command: str                # Full path for ipmitool command.
    fan_mode_delay: float       # Delay time after execution of IPMI set fan mode function
    fan_level_delay: float      # Delay time after execution of IPMI set fan level function
    remote_parameters: str      # Remote IPMI parameters
    sudo: bool                  # Use `sudo` command for `ipmitool` command
    platform_name: str
    platform: Platform

    # Constant values for IPMI fan zones:
    CPU_ZONE: int = 0
    HD_ZONE: int = 1

    # Constant values for the results of IPMI operations:
    SUCCESS: int = 0
    ERROR: int = -1

    # Constant values for the configuration parameters.
    CS_IPMI: str = 'Ipmi'
    CV_IPMI_COMMAND: str = 'command'
    CV_IPMI_FAN_MODE_DELAY: str = 'fan_mode_delay'
    CV_IPMI_FAN_LEVEL_DELAY: str = 'fan_level_delay'
    CV_IPMI_REMOTE_PARAMETERS: str = 'remote_parameters'
    CV_IPMI_PLATFORM_NAME: str = 'platform_name'

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
        self.command = config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_COMMAND, '/usr/bin/ipmitool')
        self.fan_mode_delay = config[Ipmi.CS_IPMI].getint(Ipmi.CV_IPMI_FAN_MODE_DELAY, fallback=10)
        self.fan_level_delay = config[Ipmi.CS_IPMI].getint(Ipmi.CV_IPMI_FAN_LEVEL_DELAY, fallback=2)
        self.remote_parameters = config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_REMOTE_PARAMETERS, fallback='')
        self.sudo = sudo
        self.platform_name = config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_PLATFORM_NAME, fallback='')

        # Validate configuration
        # Check 1: a valid command can be executed successfully and wait if BMC is not ready.
        bmc_timeout = 0.0
        while 1:
            try:
                self.get_sensor_data_repository()
                break
            except FileNotFoundError as e:
                raise e
            except RuntimeError as e:
                # In case of ipmitool error we try to wait BMC initialization in maximum 120 seconds
                # (in 5 seconds steps), otherwise reraise the exception.
                if 'ipmitool' in e.args[0]:
                    self.log.msg(Log.LOG_INFO, 'BMC is not ready, waiting 5 seconds.')
                    time.sleep(5)
                    bmc_timeout += 5
                    if bmc_timeout < Ipmi.BMC_INIT_TIMEOUT:
                        continue
                raise e

        # Check 2: fan_mode_delay must be positive.
        if self.fan_mode_delay < 0:
            raise ValueError(f'Negative fan_mode_delay= parameter ({self.fan_mode_delay})')
        # Check 3: fan_mode_delay must be positive.
        if self.fan_level_delay < 0:
            raise ValueError(f'Negative fan_level_delay= parameter ({self.fan_level_delay})')

        # Print the configuration out at DEBUG log level.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, 'Ipmi module was initialized with:')
            self.log.msg(Log.LOG_CONFIG, f'   {Ipmi.CV_IPMI_COMMAND} = {self.command}')
            self.log.msg(Log.LOG_CONFIG, f'   {Ipmi.CV_IPMI_FAN_MODE_DELAY} = {self.fan_mode_delay}')
            self.log.msg(Log.LOG_CONFIG, f'   {Ipmi.CV_IPMI_FAN_LEVEL_DELAY} = {self.fan_level_delay}')
            self.log.msg(Log.LOG_CONFIG, f'   {Ipmi.CV_IPMI_REMOTE_PARAMETERS} = {self.remote_parameters}')
            self.log.msg(Log.LOG_CONFIG, f'   {Ipmi.CV_IPMI_PLATFORM_NAME} = {self.platform_name}')

        # Now that the BMC has been initialised, use it to determine the platform
        # name if it hasn't been specified by the user
        if not self.platform_name:
            self.platform_name = self.identify_platform_name()
        self.platform = create_platform(self.platform_name)
        self.log.msg(
            Log.LOG_DEBUG,
            (
                f"Initialised platform '{self.platform.name()}' using "
                f"'{type(self.platform).__name__}' model."
            )
        )

        # Prepare the fans to be controlled manually
        self.platform.set_fan_manual_mode(self._exec_ipmitool)

    def _exec_ipmitool(self, args: List[str]) -> subprocess.CompletedProcess:
        """Execute `ipmitool` command.
        Args:
            args(List[str]): command line parameters
        Returns:
            subprocess.CompletedProcess: result of the executed subprocess
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        r: subprocess.CompletedProcess      # result of the executed process
        arguments: List[str]                # Command arguments

        try:
            # Construct command line parameters.
            arguments = []
            # Add `sudo` if needed.
            if self.sudo:
                arguments.append('sudo')
            # Add `ipmitool` path.
            arguments.append(self.command)
            # Add remote parameters if needed.
            if self.remote_parameters:
                arguments.extend(self.remote_parameters.split())
            # Add additional command line parameters from caller.
            arguments.extend(args)
            r = subprocess.run(arguments, check=False, capture_output=True, text=True)
            # Check error code.
            if r.returncode != 0:
                if self.sudo and 'sudo' in r.stderr:
                    raise RuntimeError(f'sudo error ({r.returncode}): {r.stderr}.')
                raise RuntimeError(f'ipmitool error ({r.returncode}): {r.stderr}.')
        except FileNotFoundError as e:
            raise e
        return r

    def get_sensor_data_repository(self) -> Dict[str, str]:
        """Get the sensor data repository. This is equivalent to `ipmitool sdr`.
        Returns:
            Dict[str, str]: The value, unit and status of each sensor reported by the system
        Raises:
            FileNotFoundError: ipmitool not found
            RuntimeError: ipmitool execution error
        """
        response = self._exec_ipmitool(['sdr'])
        result = {}
        for line in response.stdout.splitlines():
            parts = line.split("|")
            if len(parts) < 3:
                # The output is malformed here, return
                break
            # The return here always has 3 fields, but the data is not generally well structured
            # The data may or may not contain a unit, for instance when
            # the value is hex of the form '0x00'
            # The data may or may not contain a value, for instance when
            # a sensor is not connected, it will show "no reading"
            name = parts[0].strip()
            status  = parts[2].strip()

            value = 0.00
            unit = ""
            if parts[1].strip() == "no reading":
                unit = parts[1].strip()
            else:
                value_unit = parts[1].strip().split(" ")
                value_str = value_unit[0]
                unit_str = " ".join(value_unit[1:]).strip()
                try:
                    value = float(value_str)
                    unit = unit_str
                except ValueError:
                    try:
                        value = int(value_str, 16) # value is hex
                        unit = "bool"
                    except ValueError:
                        # If it's not a hex or a float, skip this entry
                        # so that we don't throw an exception further up
                        # as this is an unhandled case and we don't want
                        # to break general compatibility over a parsing
                        # issue
                        self.log.msg(
                            Log.LOG_DEBUG,
                            f"Failed to parse sdr entry '{parts[1]}'. Skipping."
                        )
                        continue

            result[name] = {
                "value": value,
                "unit": unit,
                "status": status,
            }

        return result

    def identify_platform_name(self) -> str:
        """Identifies the name of the platform on which smfc is executing. This is
        extracted from `ipmitool mc info` output.
        Returns:
            str: The name of the platform, i.e. 'X10SRi'.
        Raises:
            FileNotFoundError: ipmitool not found
            RuntimeError: ipmitool execution error
        """
        response = self._exec_ipmitool(['mc', 'info'])
        for line in response.stdout.splitlines():
            if "Product Name" in line:
                # Will look for a line that matches the following, and extract "X10SRi"
                # Product Name              : X10SRi
                platform_name = line.split(":")[1].strip()
                self.log.msg(Log.LOG_INFO, f"Platform identified as '{platform_name}'")
                return platform_name
        # Failed to discover platform name
        self.log.msg(Log.LOG_INFO, 'Failed to identify platform name')
        return ""

    def get_fan_mode(self) -> int:
        """Get the current IPMI fan mode.
        Returns:
            int: fan mode (FanMode.STANDARD, FanMode.FULL, FanMode.OPTIMAL, FanMode.PUE, FanMode.HEAVY_IO)
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
            ValueError: output of the ipmitool cannot be interpreted/converted
        """
        return self.platform.get_fan_mode(self._exec_ipmitool)

    @staticmethod
    def get_fan_mode_name(mode: int) -> str:
        """Get the name of the specified IPMI fan mode.
        Args:
            mode (int): fan mode
        Returns:
            str: name of the fan mode ('UNKNOWN', 'STANDARD', 'FULL', 'OPTIMAL', 'PUE' 'HEAVY IO')
        """
        fan_mode_name: str  # Name of the fan mode

        fan_mode_name = 'UNKNOWN'
        if mode == FanMode.STANDARD:
            fan_mode_name = 'STANDARD'
        elif mode == FanMode.FULL:
            fan_mode_name = 'FULL'
        elif mode == FanMode.OPTIMAL:
            fan_mode_name = 'OPTIMAL'
        elif mode == FanMode.PUE:
            fan_mode_name = 'PUE'
        elif mode == FanMode.HEAVY_IO:
            fan_mode_name = 'HEAVY IO'
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
        self.platform.set_fan_mode(self._exec_ipmitool, mode)
        # Give time for IPMI system/fans to apply changes in the new fan mode.
        time.sleep(self.fan_mode_delay)

    def set_fan_level(self, zone: int, level: int) -> None:
        """Set the fan level in the specified IPMI zone. Could raise several exceptions in case of invalid parameters.
        Args:
            zone (int): IPMI zone
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        self.platform.set_fan_level(self._exec_ipmitool, zone, level)
        # Give time for IPMI and fans to spin up/down.
        time.sleep(self.fan_level_delay)

    def set_multiple_fan_levels(self, zone_list: List[int], level: int) -> None:
        """Set the fan level in multiple IPMI zones. Could raise several exceptions in case of invalid parameters.
        Args:
            zone_list (List[int]): List of IPMI zones
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        self.platform.set_multiple_fan_levels(self._exec_ipmitool, zone_list, level)
        # Give time for IPMI and fans to spin up/down.
        time.sleep(self.fan_level_delay)

    def get_fan_level(self, zone: int) -> int:
        """Get the current fan level in a specific IPMI zone. Raise an exception in case of invalid parameters.
        Args:
            zone (int): fan zone (CPU_ZONE, HD_ZONE)
        Returns:
            level (int): fan level in % (0-100)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        return self.platform.get_fan_level(self._exec_ipmitool, zone)


# End.
