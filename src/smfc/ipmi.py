#
#   ipmi.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.Ipmi() class implementation.
#
import subprocess
import time
from configparser import ConfigParser
from typing import List
from smfc.log import Log


class Ipmi:
    """IPMI interface class can set/get IPMI fan mode, and can set IPMI fan level using ipmitool."""

    log: Log                    # Reference to a Log class instance
    command: str                # Full path for ipmitool command.
    fan_mode_delay: float       # Delay time after execution of IPMI set fan mode function
    fan_level_delay: float      # Delay time after execution of IPMI set fan level function
    remote_parameters: str      # Remote IPMI parameters
    sudo: bool                  # Use `sudo` command for `ipmitool` command

    # Constant values for IPMI fan modes:
    STANDARD_MODE: int = 0
    FULL_MODE: int = 1
    OPTIMAL_MODE: int = 2
    PUE_MODE: int = 3
    HEAVY_IO_MODE: int = 4

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

        # Validate configuration
        # Check 1: a valid command can be executed successfully.
        try:
            self._exec_ipmitool(['sdr'])
        except (FileNotFoundError, RuntimeError) as e:
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

    def get_fan_mode(self) -> int:
        """Get the current IPMI fan mode.
        Returns:
            int: fan mode (ERROR, STANDARD_MODE, FULL_MODE, OPTIMAL_MODE, HEAVY_IO_MODE)
        Raises:
            FileNotFoundError: ipmitool cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
            ValueError: output of the ipmitool cannot be interpreted/converted
        """
        r: subprocess.CompletedProcess  # result of the executed process
        m: int                          # fan mode

        # Read the current IPMI fan mode.
        try:
            r = self._exec_ipmitool(['raw', '0x30', '0x45', '0x00'])
            m = int(r.stdout)
        except (RuntimeError, FileNotFoundError) as e:
            raise e
        return m

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
        if mode == Ipmi.STANDARD_MODE:
            fan_mode_name = 'STANDARD'
        elif mode == Ipmi.FULL_MODE:
            fan_mode_name = 'FULL'
        elif mode == Ipmi.OPTIMAL_MODE:
            fan_mode_name = 'OPTIMAL'
        elif mode == Ipmi.PUE_MODE:
            fan_mode_name = 'PUE'
        elif mode == Ipmi.HEAVY_IO_MODE:
            fan_mode_name = 'HEAVY IO'
        return fan_mode_name

    def set_fan_mode(self, mode: int) -> None:
        """Set the IPMI fan mode.
        Args:
            mode (int): fan mode (STANDARD_MODE, FULL_MODE, OPTIMAL_MODE, PUE_MODE, HEAVY_IO_MODE)
        Raises:
            ValueError: invalid input parameter
            FileNotFoundError: ipmitool command cannot be found
            RuntimeError: ipmitool execution problem (e.g. non-root user, incompatible IPMI system/motherboard)
        """
        # Validate mode parameter.
        if mode not in {self.STANDARD_MODE, self.FULL_MODE, self.OPTIMAL_MODE, self.PUE_MODE, self.HEAVY_IO_MODE}:
            raise ValueError(f'Invalid fan mode value ({mode}).')
        # Call ipmitool command and set the new IPMI fan mode.
        try:
            self._exec_ipmitool(['raw', '0x30', '0x45', '0x01', f'0x{mode:02x}'])
        except (RuntimeError, FileNotFoundError) as e:
            raise e
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
        # Validate zone parameter
        if zone not in range(0, 101):
            raise ValueError(f'Invalid value: zone ({zone}).')
        # Validate level parameter (must be in the interval [0..100%])
        if level not in range(0, 101):
            raise ValueError(f'Invalid value: level ({level}).')
        # Set the new IPMI fan level in the specific zone
        try:
            self._exec_ipmitool(['raw', '0x30', '0x70', '0x66', '0x01', f'0x{zone:02x}', f'0x{level:02x}'])
        except (FileNotFoundError, RuntimeError) as e:
            raise e
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
        # Validate zone parameters
        for zone in zone_list:
            if zone not in range(0, 101):
                raise ValueError(f'Invalid value: zone ({zone}).')
        # Validate level parameter (must be in the interval [0..100%])
        if level not in range(0, 101):
            raise ValueError(f'Invalid value: level ({level}).')
        # Set the new IPMI fan level in the specific zone
        try:
            for zone in zone_list:
                self._exec_ipmitool(['raw', '0x30', '0x70', '0x66', '0x01', f'0x{zone:02x}', f'0x{level:02x}'])
        except (FileNotFoundError, RuntimeError) as e:
            raise e
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
        r: subprocess.CompletedProcess  # result of the executed process
        level: int                      # Level

        # Validate zone parameter
        if zone not in range(0, 101):
            raise ValueError(f'Invalid value: zone ({zone}).')
        # Get the new IPMI fan level in the specific zone
        try:
            r = self._exec_ipmitool(['raw', '0x30', '0x70', '0x66', '0x00', f'0x{zone:x}'])
            level = int(r.stdout, 16)
        except (FileNotFoundError, RuntimeError) as e:
            raise e
        return level


# End.
