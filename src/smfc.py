#!/usr/bin/env python3
#
#   smfc.py (C) 2020-2025, Peter Sulyok
#   IPMI fan controller for Super Micro X10-X13 motherboards.
#
import atexit
import argparse
import configparser
import os
import subprocess
import sys
import syslog
import time
from typing import List, Callable
from pyudev import Context, Devices, Device, DeviceNotFoundByFileError
import pySMART


# Program version string
version_str: str = '4.0.0 beta'


class Log:
    """Log class. This class can send log messages considering different log levels and different outputs"""

    # Configuration parameters.
    log_level: int                      # Log level
    log_output: int                     # Log output
    msg: Callable[[int, str], None]     # Function reference to the log function (based on log output)

    # Constants for log levels.
    LOG_NONE: int = 0
    LOG_ERROR: int = 1
    LOG_CONFIG: int = 2
    LOG_INFO: int = 3
    LOG_DEBUG: int = 4

    # Constants for log outputs.
    LOG_STDOUT: int = 0
    LOG_STDERR: int = 1
    LOG_SYSLOG: int = 2

    def __init__(self, log_level: int, log_output: int) -> None:
        """Initialize Log class with log output and log level.

        Args:
            log_level (int): user defined log level (LOG_NONE, LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            log_output (int): user defined log output (LOG_STDOUT, LOG_STDERR, LOG_SYSLOG)
        """
        # Setup log configuration.
        if log_level not in {self.LOG_NONE, self.LOG_ERROR, self.LOG_CONFIG, self.LOG_INFO, self.LOG_DEBUG}:
            raise ValueError(f'Invalid log level value ({log_level})')
        self.log_level = log_level
        if log_output not in {self.LOG_STDOUT, self.LOG_STDERR, self.LOG_SYSLOG}:
            raise ValueError(f'Invalid log output value ({log_output})')
        self.log_output = log_output
        if self.log_output == self.LOG_STDOUT:
            self.msg = self.msg_to_stdout
        elif self.log_output == self.LOG_STDERR:
            self.msg = self.msg_to_stderr
        else:
            self.msg = self.msg_to_syslog
            syslog.openlog('smfc.service', facility=syslog.LOG_DAEMON)

        # Print the configuration out at DEBUG log level.
        if self.log_level >= self.LOG_CONFIG:
            self.msg(Log.LOG_CONFIG, 'Logging module was initialized with:')
            self.msg(Log.LOG_CONFIG, f'   log_level = {self.log_level}')
            self.msg(Log.LOG_CONFIG, f'   log_output = {self.log_output}')

    def map_to_syslog(self, level: int) -> int:
        """Map log level to syslog values.

            Args:
                level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            Returns:
                int: syslog log level
            """
        syslog_level = syslog.LOG_ERR
        if level in (self.LOG_CONFIG, self.LOG_INFO):
            syslog_level = syslog.LOG_INFO
        elif level == self.LOG_DEBUG:
            syslog_level = syslog.LOG_DEBUG
        return syslog_level

    def level_to_str(self, level: int) -> str:
        """Convert a log level to a string.

            Args:
                level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            Returns:
                str: log level string
            """
        string = 'NONE'
        if level == self.LOG_ERROR:
            string = 'ERROR'
        if level == self.LOG_CONFIG:
            string = 'CONFIG'
        if level == self.LOG_INFO:
            string = 'INFO'
        elif level == self.LOG_DEBUG:
            string = 'DEBUG'
        return string

    def msg_to_syslog(self, level: int, msg: str) -> None:
        """Print a log message to syslog.

        Args:
            level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            msg (str): log message
        """
        if level is not self.LOG_NONE:
            if level <= self.log_level:
                syslog.syslog(self.map_to_syslog(level), msg)

    def msg_to_stdout(self, level: int, msg: str) -> None:
        """Print a log message to stdout.

        Args:
            level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            msg (str):  log message
        """
        if level is not self.LOG_NONE:
            if level <= self.log_level:
                print(f'{self.level_to_str(level)}: {msg}', flush=True, file=sys.stdout)

    def msg_to_stderr(self, level: int, msg: str) -> None:
        """Print a log message to stderr.

        Args:
            level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            msg (str):  log message
        """
        if level is not self.LOG_NONE:
            if level <= self.log_level:
                print(f'{self.level_to_str(level)}: {msg}', flush=True, file=sys.stderr)


class Ipmi:
    """IPMI interface class. It can set/get modes of IPMI fan zones and can set IPMI fan levels using ipmitool."""

    log: Log                            # Reference to a Log class instance
    command: str                        # Full path for ipmitool command.
    fan_mode_delay: float               # Delay time after execution of IPMI set fan mode function
    fan_level_delay: float              # Delay time after execution of IPMI set fan level function
    swapped_zones: bool                 # CPU and HD zones are swapped
    remote_parameters: str              # Remote IPMI parameters.

    # Constant values for IPMI fan modes:
    STANDARD_MODE: int = 0
    FULL_MODE: int = 1
    OPTIMAL_MODE: int = 2
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
    CV_IPMI_SWAPPED_ZONES: str = 'swapped_zones'
    CV_IPMI_REMOTE_PARAMETERS: str = 'remote_parameters'

    def __init__(self, log: Log, config: configparser.ConfigParser) -> None:
        """Initialize the Ipmi class with a log class and with a configuration class.

        Args:
            log (Log): Log class
            config (configparser.ConfigParser): configuration values
        """
        # Set default or read from configuration
        self.log = log
        self.command = config[self.CS_IPMI].get(self.CV_IPMI_COMMAND, '/usr/bin/ipmitool')
        self.fan_mode_delay = config[self.CS_IPMI].getint(self.CV_IPMI_FAN_MODE_DELAY, fallback=10)
        self.fan_level_delay = config[self.CS_IPMI].getint(self.CV_IPMI_FAN_LEVEL_DELAY, fallback=2)
        self.swapped_zones = config[self.CS_IPMI].getboolean(self.CV_IPMI_SWAPPED_ZONES, fallback=False)
        self.remote_parameters = config[self.CS_IPMI].get(self.CV_IPMI_REMOTE_PARAMETERS, fallback='')

        # Validate configuration
        # Check 1: a valid command can be executed successfully.
        try:
            subprocess.run([self.command, 'sdr'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError as e:
            raise e
        # Check 2: fan_mode_delay must be positive.
        if self.fan_mode_delay < 0:
            raise ValueError(f'Negative fan_mode_delay ({self.fan_mode_delay})')
        # Check 3: fan_mode_delay must be positive.
        if self.fan_level_delay < 0:
            raise ValueError(f'Negative fan_level_delay ({self.fan_level_delay})')
        # Print the configuration out at DEBUG log level.
        if self.log.log_level >= self.log.LOG_CONFIG:
            self.log.msg(self.log.LOG_CONFIG, 'Ipmi module was initialized with:')
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_IPMI_COMMAND} = {self.command}')
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_IPMI_FAN_MODE_DELAY} = {self.fan_mode_delay}')
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_IPMI_FAN_LEVEL_DELAY} = {self.fan_level_delay}')
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_IPMI_SWAPPED_ZONES} = {self.swapped_zones}')
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_IPMI_REMOTE_PARAMETERS} = {self.remote_parameters}')

    def get_fan_mode(self) -> int:
        """Get the current IPMI fan mode.

        Returns:
            int: fan mode (ERROR, STANDARD_MODE, FULL_MODE, OPTIMAL_MODE, HEAVY_IO_MODE)

        Raises:
            FileNotFoundError: ipmitool command cannot be found
            ValueError: output of the ipmitool cannot be interpreted/converted
            RuntimeError: ipmitool execution problem in IPMI (e.g. non-root user, incompatible IPMI systems
                or motherboards)
        """
        r: subprocess.CompletedProcess  # result of the executed process
        arguments: List[str]            # Command arguments
        m: int                          # fan mode

        # Read the current IPMI fan mode.
        try:
            arguments = [self.command]
            if self.remote_parameters:
                arguments.extend(self.remote_parameters.split())
            arguments.extend(['raw', '0x30', '0x45', '0x00'])
            r = subprocess.run(arguments, check=False, capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr)
            m = int(r.stdout)
        except (FileNotFoundError, ValueError) as e:
            raise e
        return m

    def get_fan_mode_name(self, mode: int) -> str:
        """Get the name of the specified IPMI fan mode.

        Args:
            mode (int): fan mode
        Returns:
            str: name of the fan mode ('ERROR', 'STANDARD MODE', 'FULL MODE', 'OPTIMAL MODE', 'HEAVY IO MODE')
        """
        fan_mode_name: str              # Name of the fan mode

        fan_mode_name = 'ERROR'
        if mode == self.STANDARD_MODE:
            fan_mode_name = 'STANDARD_MODE'
        elif mode == self.FULL_MODE:
            fan_mode_name = 'FULL_MODE'
        elif mode == self.OPTIMAL_MODE:
            fan_mode_name = 'OPTIMAL_MODE'
        elif mode == self.HEAVY_IO_MODE:
            fan_mode_name = 'HEAVY IO MODE'
        return fan_mode_name

    def set_fan_mode(self, mode: int) -> None:
        """Set the IPMI fan mode.

        Args:
            mode (int): fan mode (STANDARD_MODE, FULL_MODE, OPTIMAL_MODE, HEAVY_IO_MODE)
        """
        arguments: List[str]    # Command arguments

        # Validate mode parameter.
        if mode not in {self.STANDARD_MODE, self.FULL_MODE, self.OPTIMAL_MODE, self.HEAVY_IO_MODE}:
            raise ValueError(f'Invalid fan mode value ({mode}).')
        # Call ipmitool command and set the new IPMI fan mode.
        try:
            arguments = [self.command]
            if self.remote_parameters:
                arguments.extend(self.remote_parameters.split())
            arguments.extend(['raw', '0x30', '0x45', '0x01', str(mode)])
            subprocess.run(arguments, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError as e:
            raise e
        # Give time for IPMI system/fans to apply changes in the new fan mode.
        time.sleep(self.fan_mode_delay)

    def set_fan_level(self, zone: int, level: int) -> None:
        """Set the IPMI fan level in a specific zone. Raise an exception in case of invalid parameters.

        Args:
            zone (int): fan zone (CPU_ZONE, HD_ZONE)
            level (int): fan level in % (0-100)
        """
        arguments: List[str]  # Command arguments

        # Validate zone parameter
        if zone not in {self.CPU_ZONE, self.HD_ZONE}:
            raise ValueError(f'Invalid value: zone ({zone}).')
        # Handle swapped zones
        if self.swapped_zones:
            zone = 1 - zone
        # Validate level parameter (must be in the interval [0..100%])
        if level not in range(0, 101):
            raise ValueError(f'Invalid value: level ({level}).')
        # Set the new IPMI fan level in the specific zone
        try:
            arguments = [self.command]
            if self.remote_parameters:
                arguments.extend(self.remote_parameters.split())
            arguments.extend(['raw', '0x30', '0x70', '0x66', '0x01', str(zone), str(level)])
            subprocess.run(arguments, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError as e:
            raise e
        # Give time for IPMI and fans to spin up/down.
        time.sleep(self.fan_level_delay)


class FanController:
    """Generic fan controller class for an IPMI zone."""

    # Constant values for temperature calculation
    CALC_MIN: int = 0
    CALC_AVG: int = 1
    CALC_MAX: int = 2

    # Error messages.
    ERROR_MSG_FILE_IO: str = 'Cannot read file ({}).'

    # Configuration parameters
    log: Log                # Reference to a Log class instance
    udevc: Context          # Reference to an udev database connection (instance of Context from pyudev)
    ipmi: Ipmi              # Reference to an Ipmi class instance
    ipmi_zone: int          # IPMI zone identifier
    name: str               # Name of the controller
    count: int              # Number of controlled entities
    temp_calc: int          # Calculate of the temperature (0-min, 1-avg, 2-max)
    steps: int              # Discrete steps in temperatures and fan levels
    sensitivity: float      # Temperature change to activate fan controller (C)
    polling: float          # Polling interval to read temperature (sec)
    min_temp: float         # Minimum temperature value (C)
    max_temp: float         # Maximum temperature value (C)
    min_level: int          # Minimum fan level (0..100%)
    max_level: int          # Maximum fan level (0..100%)
    hwmon_dev: List[Device] # List of HWMON devices

    # Measured or calculated attributes
    temp_step: float        # A temperature steps value (C)
    level_step: float       # A fan level step value (0..100%)
    last_time: float        # Last system time we polled temperature (timestamp)
    last_temp: float        # Last measured temperature value (C)
    last_level: int         # Last configured fan level (0..100%)

    # Function variable for selected temperature calculation method
    get_temp_func: Callable[[], float]

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, ipmi_zone: int, name: str, temp_calc: int, steps: int,
                 sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                 max_level: int) -> None:
        """Initialize the FanController class. Will raise an exception in case of invalid parameters.

        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to a udev database connection (pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            ipmi_zone (int): IPMI zone identifier
            name (str): name of the controller
            temp_calc (int): calculation of temperature
            steps (int): discrete steps in temperatures and fan levels
            sensitivity (float): temperature change to activate fan controller (C)
            polling (float): polling time interval for reading temperature (sec)
            min_temp (float): minimum temperature value (C)
            max_temp (float): maximum temperature value (C)
            min_level (int): minimum fan level value [0..100%]
            max_level (int): maximum fan level value [0..100%]
        """
        # Save and validate configuration parameters.
        self.log = log
        self.udevc = udevc
        self.ipmi = ipmi
        self.ipmi_zone = ipmi_zone
        if self.ipmi_zone not in {Ipmi.CPU_ZONE, Ipmi.HD_ZONE}:
            raise ValueError('invalid value: ipmi_zone')
        self.name = name
        self.temp_calc = temp_calc
        if self.temp_calc not in {self.CALC_MIN, self.CALC_AVG, self.CALC_MAX}:
            raise ValueError('invalid value: temp_calc')
        self.steps = steps
        if self.steps <= 0:
            raise ValueError('steps <= 0')
        self.sensitivity = sensitivity
        if self.sensitivity <= 0:
            raise ValueError('sensitivity <= 0')
        self.polling = polling
        if self.polling < 0:
            raise ValueError('polling < 0')
        if max_temp < min_temp:
            raise ValueError('max_temp < min_temp')
        self.min_temp = min_temp
        self.max_temp = max_temp
        if max_level < min_level:
            raise ValueError('max_level < min_level')
        self.min_level = min_level
        self.max_level = max_level

        # Set the proper temperature function.
        if self.count == 1:
            self.get_temp_func = self.get_1_temp
        else:
            self.get_temp_func = self.get_avg_temp
            if self.temp_calc == self.CALC_MIN:
                self.get_temp_func = self.get_min_temp
            elif self.temp_calc == self.CALC_MAX:
                self.get_temp_func = self.get_max_temp
        # Check if temperature can be read successfully.
        if len(self.hwmon_dev):
            self.get_temp_func()
        # Initialize calculated values.
        self.temp_step = (max_temp - min_temp) / steps
        self.level_step = (max_level - min_level) / steps
        self.last_temp = 0
        self.last_level = 0
        self.last_time = time.monotonic() - (polling + 1)
        # Print configuration at DEBUG log level.
        if self.log.log_level >= self.log.LOG_CONFIG:
            self.log.msg(self.log.LOG_CONFIG, f'{self.name} fan controller was initialized with:')
            self.log.msg(self.log.LOG_CONFIG, f'   ipmi zone = {self.ipmi_zone}')
            self.log.msg(self.log.LOG_CONFIG, f'   count = {self.count}')
            self.log.msg(self.log.LOG_CONFIG, f'   temp_calc = {self.temp_calc}')
            self.log.msg(self.log.LOG_CONFIG, f'   steps = {self.steps}')
            self.log.msg(self.log.LOG_CONFIG, f'   sensitivity = {self.sensitivity}')
            self.log.msg(self.log.LOG_CONFIG, f'   polling = {self.polling}')
            self.log.msg(self.log.LOG_CONFIG, f'   min_temp = {self.min_temp}')
            self.log.msg(self.log.LOG_CONFIG, f'   max_temp = {self.max_temp}')
            self.log.msg(self.log.LOG_CONFIG, f'   min_level = {self.min_level}')
            self.log.msg(self.log.LOG_CONFIG, f'   max_level = {self.max_level}')
            result=[]
            for d in self.hwmon_dev:
                if d is not None:
                    result.append(os.path.join(d.sys_path, 'temp1_input'))
                else:
                    result.append('smartctl')
            self.log.msg(self.log.LOG_CONFIG, f'   hwmon_dev = {result}')
            self.print_temp_level_mapping()

    @staticmethod
    def get_hwmon_dev(udevc: Context, parent_dev: Device) -> Device:
        """A helper function to get HWMON device of a given parent device's associated hwmon

        Args:
            udevc (Context): reference to pyudev Context
            parent_dev (Device): parent device

        Returns:
            Device: HWMON device
        """
        try:
            [hwmon_device] = udevc.list_devices(subsystem='hwmon', parent=parent_dev)
        except ValueError as e:
            # if parent_dev does not have exactly one hwmon device in its subtree
            hwmon_device = None
        return hwmon_device

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the 'nth' element in the hwmon list. This is an empty implementation."""

    def get_1_temp(self) -> float:
        """Get a single temperature of a controlled entity in the IPMI zone.

        Returns:
            float: single temperature of a controlled entity (C)
        """
        return self._get_nth_temp(0)

    # pylint: disable=R1730
    def get_min_temp(self) -> float:
        """Get the minimum temperature of multiple controlled entities.

        Returns:
            float: minimum temperature of the controlled entities (C)
        """
        minimum: float      # Minimum temperature value
        value: float        # Float value

        # Calculate minimum temperature.
        minimum = 1000.0
        for i in range(self.count):
            value = self._get_nth_temp(i)
            if value < minimum:
                minimum = value
        return minimum

    def get_avg_temp(self):
        """Get the average temperature of the controlled entities in the IPMI zone.

           Returns:
                float: average temperature of the controlled entities (C)
        """
        average: float      # Average temperature
        counter: int        # Value counter

        # Calculate average temperature.
        average = 0.0
        counter = 0
        for i in range(self.count):
            average += self._get_nth_temp(i)
            counter += 1
        return average / counter

    # pylint: disable=R1731
    def get_max_temp(self) -> float:
        """Get the maximum temperature of the controlled entities in the IPMI zone.

           Returns:
                float: maximum temperature of the controlled entities (C)
        """
        maximum: float      # Maximum temperature value
        value: float        # Float value

        # Calculate minimum temperature.
        maximum = -1.0
        for i in range(self.count):
            value = self._get_nth_temp(i)
            if value > maximum:
                maximum = value
        return maximum

    def set_fan_level(self, level: int) -> None:
        """Set the new fan level in an IPMI zone. Can raise exception (ValueError).

        Args:
            level (int): new fan level [0..100]
        Returns:
            int: result (Ipmi.SUCCESS, Ipmi.ERROR)
        """
        return self.ipmi.set_fan_level(self.ipmi_zone, level)

    def callback_func(self) -> None:
        """Call-back function for a child class."""

    def run(self) -> None:
        """Run IPMI zone controller function with the following steps:

            * Step 1: Read current time. If the elapsed time is bigger than the polling time period
              then go to step 2, otherwise return.
            * Step 2: Read the current temperature. If the change of the temperature goes beyond
              the sensitivity limit then go to step 3, otherwise return
            * Step 3: Calculate the current gain and fan level based on the measured temperature
            * Step 4: If the new fan level is different it will be set and logged
        """
        current_time: float     # Current system timestamp (measured)
        current_temp: float     # Current temperature (measured)
        current_level: int      # Current fan level (calculated)
        current_gain: int       # Current gain level (calculated)

        # Step 1: check the elapsed time.
        current_time = time.monotonic()
        if current_time - self.last_time >= self.polling:
            self.last_time = current_time

            # Step 2: read temperature and sensitivity gap.
            self.callback_func()
            current_temp = self.get_temp_func()
            self.log.msg(self.log.LOG_DEBUG, f'{self.name}: new temperature > {current_temp:.1f}C')
            if abs(current_temp - self.last_temp) < self.sensitivity:
                return
            self.last_temp = current_temp

            # Step 3: calculate gain and fan level.
            if current_temp <= self.min_temp:
                current_gain = 0
                current_level = self.min_level
            elif current_temp >= self.max_temp:
                current_gain = self.steps
                current_level = self.max_level
            else:
                current_gain = int(round((current_temp - self.min_temp) / self.temp_step))
                current_level = int(round(float(current_gain) * self.level_step)) + self.min_level

            # Step 4: the new fan level will be set and logged.
            if current_level != self.last_level:
                self.last_level = current_level
                self.set_fan_level(current_level)
                self.log.msg(self.log.LOG_INFO, f'{self.name}: new fan level > {current_level}%/{current_temp:.1f}C')

    def print_temp_level_mapping(self) -> None:
        """Print out the user-defined temperature to level mapping value in log DEBUG level."""
        self.log.msg(self.log.LOG_CONFIG, '   Temperature to level mapping:')
        for i in range(self.steps + 1):
            self.log.msg(self.log.LOG_CONFIG, f'   {i}. [T:{self.min_temp+(i*self.temp_step):.1f}C - '
                         f'L:{int(self.min_level + (i * self.level_step))}%]')


class CpuZone(FanController):
    """CPU zone fan control."""

    # Constant values for the configuration parameters.
    CS_CPU_ZONE: str = 'CPU zone'
    CV_CPU_ZONE_ENABLED: str = 'enabled'
    CV_CPU_ZONE_COUNT: str = 'count'
    CV_CPU_ZONE_TEMP_CALC: str = 'temp_calc'
    CV_CPU_ZONE_STEPS: str = 'steps'
    CV_CPU_ZONE_SENSITIVITY: str = 'sensitivity'
    CV_CPU_ZONE_POLLING: str = 'polling'
    CV_CPU_ZONE_MIN_TEMP: str = 'min_temp'
    CV_CPU_ZONE_MAX_TEMP: str = 'max_temp'
    CV_CPU_ZONE_MIN_LEVEL: str = 'min_level'
    CV_CPU_ZONE_MAX_LEVEL: str = 'max_level'
    CV_CPU_ZONE_HWMON_PATH: str = 'hwmon_path'

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, config: configparser.ConfigParser) -> None:
        """Initialize the CpuZone class and raise exception in case of invalid configuration.

        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to a udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            config (configparser.ConfigParser): reference to the configuration (default=None)

        Raises:
            ValueError: multiple hwmon devices reported, one expected
            RuntimeError: No HWMON device found for CPU(s)
        """

        # Build the list of hwmon devices and set count.
        self.hwmon_dev = []
        # We are looking for either Intel (coretemp) or AMD (k10temp) CPUs.
        for dev_filter in [{'MODALIAS':'platform:coretemp'}, {'DRIVER':'k10temp'}]:
            try:
                self.hwmon_dev = [self.get_hwmon_dev(udevc, dev) for dev in udevc.list_devices(**dev_filter)]
            except ValueError as e:
                raise e
            # If we found results.
            if len(self.hwmon_dev):
                break
        if not len(self.hwmon_dev):
            raise RuntimeError('pyudev: No HWMON device can be found for CPU.')
        self.count = len(self.hwmon_dev)

        # Initialize FanController class.
        super().__init__(
            log, udevc, ipmi, Ipmi.CPU_ZONE, self.CS_CPU_ZONE,
            config[self.CS_CPU_ZONE].getint(self.CV_CPU_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[self.CS_CPU_ZONE].getint(self.CV_CPU_ZONE_STEPS, fallback=6),
            config[self.CS_CPU_ZONE].getfloat(self.CV_CPU_ZONE_SENSITIVITY, fallback=3.0),
            config[self.CS_CPU_ZONE].getfloat(self.CV_CPU_ZONE_POLLING, fallback=2),
            config[self.CS_CPU_ZONE].getfloat(self.CV_CPU_ZONE_MIN_TEMP, fallback=30.0),
            config[self.CS_CPU_ZONE].getfloat(self.CV_CPU_ZONE_MAX_TEMP, fallback=60.0),
            config[self.CS_CPU_ZONE].getint(self.CV_CPU_ZONE_MIN_LEVEL, fallback=35),
            config[self.CS_CPU_ZONE].getint(self.CV_CPU_ZONE_MAX_LEVEL, fallback=100)
        )

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the 'nth' element in the hwmon list.

        Args:
            index (int): index in hwmon list

        Returns:
            float: temperature value

        Raises:
            FileNotFoundError:  file not found
            IOError:            file cannot be opened
            ValueError:         invalid index
        """

        value: float    # Temperature value
        b: bytes

        b = self.hwmon_dev[index].attributes.get('temp1_input')
        value = float(b.decode('utf-8'))/1000.0
        return value


class HdZone(FanController):
    """Class for HD zone fan control."""

    # HdZone specific parameters.
    hd_device_names: List[str]          # Device names of the hard disks (e.g. '/dev/disk/by-id/...').

    # Standby guard specific parameters.
    standby_guard_enabled: bool         # Standby guard feature enabled
    standby_hd_limit: int               # Number of HDs in STANDBY state before the full RAID array will go STANDBY
    smartctl_path: str                  # Path for 'smartctl' command
    standby_flag: bool                  # The actual state of the whole HD array
    standby_change_timestamp: float     # Timestamp of the latest change in STANDBY mode
    standby_array_states: List[bool]    # Standby states of HDs

    # Error message.
    ERROR_MSG_SMARTCTL: str = 'Unknown smartctl return value {}'

    # Constant values for the configuration parameters.
    CS_HD_ZONE: str = 'HD zone'
    CV_HD_ZONE_ENABLED: str = 'enabled'
    CV_HD_ZONE_TEMP_CALC: str = 'temp_calc'
    CV_HD_ZONE_STEPS: str = 'steps'
    CV_HD_ZONE_SENSITIVITY: str = 'sensitivity'
    CV_HD_ZONE_POLLING: str = 'polling'
    CV_HD_ZONE_MIN_TEMP: str = 'min_temp'
    CV_HD_ZONE_MAX_TEMP: str = 'max_temp'
    CV_HD_ZONE_MIN_LEVEL: str = 'min_level'
    CV_HD_ZONE_MAX_LEVEL: str = 'max_level'
    CV_HD_ZONE_HD_NAMES: str = 'hd_names'
    CV_HD_ZONE_STANDBY_GUARD_ENABLED: str = 'standby_guard_enabled'
    CV_HD_ZONE_STANDBY_HD_LIMIT: str = 'standby_hd_limit'
    CV_HD_ZONE_SMARTCTL_PATH: str = 'smartctl_path'

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, config: configparser.ConfigParser) -> None:
        """Initialize the HdZone class. Abort in case of configuration errors.

        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to a udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            config (configparser.ConfigParser): reference to the configuration (default=None)

        Raises:
            ValueError: Parameter `hd_names=` is not specified in the configuration
        """
        count: int      # HD count
        hd_names: str   # String for hd_names=

        # Save and validate HdZone class specific parameters.
        hd_names = config[self.CS_HD_ZONE].get(self.CV_HD_ZONE_HD_NAMES)
        if not hd_names:
            raise ValueError('Parameter hd_names= is not specified.')
        if "\n" in hd_names:
            self.hd_device_names = hd_names.splitlines()
        else:
            self.hd_device_names = hd_names.split()
        # Set count.
        self.count = len(self.hd_device_names)

        # Iterate through each disk.
        self.hwmon_dev=[]
        for i in range(self.count):
            # Find udev device based on device name.
            try:
                block_dev = Devices.from_device_file(udevc, self.hd_device_names[i])
            except DeviceNotFoundByFileError as e:
                raise ValueError(f'ERROR: {self.hd_device_names[i]} cannot be accessed.')

            # Add hwmon device for NVME/SATA/HDD disks or None for SAS/SCSI disks.
            try:
                self.hwmon_dev.append(self.get_hwmon_dev(udevc, block_dev.parent))
            except ValueError as e:
                raise e

        # Initialize FanController class.
        super().__init__(
            log, udevc, ipmi, Ipmi.HD_ZONE, self.CS_HD_ZONE,
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_STEPS, fallback=4),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_SENSITIVITY, fallback=2),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_POLLING, fallback=10),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_MIN_TEMP, fallback=32),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_MAX_TEMP, fallback=46),
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_MIN_LEVEL, fallback=35),
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_MAX_LEVEL, fallback=100)
        )

        # Read and validate the configuration of standby guard if enabled.
        self.standby_guard_enabled = config[self.CS_HD_ZONE].getboolean(self.CV_HD_ZONE_STANDBY_GUARD_ENABLED,
                                                                        fallback=False)
        self.smartctl_path = config[self.CS_HD_ZONE].get(self.CV_HD_ZONE_SMARTCTL_PATH, '/usr/sbin/smartctl')

        if self.count == 1:
            self.log.msg(self.log.LOG_INFO, '   WARNING: Standby guard is disabled ([HD zone] count=1')
            self.standby_guard_enabled = False
        if self.standby_guard_enabled:
            self.standby_array_states = [False] * self.count
            # Read and validate further parameters.
            self.standby_hd_limit = config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_STANDBY_HD_LIMIT, fallback=1)
            if self.standby_hd_limit < 0:
                raise ValueError('standby_hd_limit < 0')
            if self.standby_hd_limit > self.count:
                raise ValueError('standby_hd_limit > count')
            # Get the current power state of the HD array.
            n = self.check_standby_state()
            # Set calculated parameters.
            self.standby_change_timestamp = time.monotonic()
            self.standby_flag = n == self.count

        # Print configuration in DEBUG log level (or higher).
        if self.log.log_level >= self.log.LOG_CONFIG:
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_HD_ZONE_HD_NAMES} = {self.hd_device_names}')
            if self.standby_guard_enabled:
                self.log.msg(self.log.LOG_CONFIG, '   Standby guard is enabled:')
                self.log.msg(self.log.LOG_CONFIG, f'     {self.CV_HD_ZONE_STANDBY_HD_LIMIT} = {self.standby_hd_limit}')
                self.log.msg(self.log.LOG_CONFIG, f'     {self.CV_HD_ZONE_SMARTCTL_PATH} = {self.smartctl_path}')
            else:
                self.log.msg(self.log.LOG_CONFIG, '   Standby guard is disabled')

    def callback_func(self) -> None:
        """Call-back function execute standby guard."""
        if self.standby_guard_enabled:
            self.run_standby_guard()

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the `nth` element in the hwmon list. This is a specific implementation for HD zone.

        Args:
            index (int): index in hwmon list

        Returns:
            float: temperature value

        Raises:
            FileNotFoundError:  file or command cannot be found
            IOError:            file cannot be opened
            ValueError:         invalid temperature value
            IndexError:         invalid index
        """
        value: float                    # Float value to calculate the temperature.
        b: bytes
        sd: pySMART.Device

        # Read temperature with `smartctl` command.
        if self.hwmon_dev[index] is None:

            # Read disk temperature from `smartctl` command.
            pySMART.SMARTCTL.options = []
            pySMART.SMARTCTL.smartctl_path = self.smartctl_path
            pySMART.SMARTCTL.sudo = True
            sd = pySMART.Device(self.hd_device_names[index])
            value = sd.temperature
            if not value:
                raise ValueError(f'ERROR: smartctl cannot read temperature from device {self.hd_device_names[index]}.')

        # Read temperature from a HWMON device.
        else:
            b = bytes(self.hwmon_dev[index].attributes.get('temp1_input'))
            value = float(b.decode('utf-8'))/1000.0

        return value

    def get_standby_state_str(self) -> str:
        """Get a string representing the power state of the HD array with a character.

        Returns:
            str:   standby state string where all HD represented with a character (A-ACTIVE, S-STANDBY)
        """
        result: str = ''    # Result string

        for i in range(self.count):
            if self.standby_array_states[i]:
                result += 'S'
            else:
                result += 'A'
        return result

    def check_standby_state(self):
        """Check the actual power state of the HDs in the array and store them in 'standby_states'.

        Returns:
            int:   number of HDs in STANDBY mode
        """
        r: subprocess.CompletedProcess      # Result of the executed process.

        # Check the current power state of the HDs
        for i in range(self.count):
            self.standby_array_states[i] = False
            r = subprocess.run([self.smartctl_path, '-i', '-n', 'standby', self.hd_device_names[i]],
                               check=False, capture_output=True, text=True)
            if r.returncode not in {0, 2}:
                raise ValueError(self.ERROR_MSG_SMARTCTL.format(r.returncode))
            if str(r.stdout).find("STANDBY") != -1:
                self.standby_array_states[i] = True
        return self.standby_array_states.count(True)

    def go_standby_state(self):
        """Put active HDs to STANDBY state in the array (based on the actual state of 'standby_states').
        """
        r: subprocess.CompletedProcess      # Result of the executed process.

        # Iterate through HDs list
        for i in range(self.count):
            # if the HD is ACTIVE
            if not self.standby_array_states[i]:
                # then move it to STANDBY state
                r = subprocess.run([self.smartctl_path, '-s', 'standby,now', self.hd_device_names[i]],
                                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if r.returncode != 0:
                    raise ValueError(self.ERROR_MSG_SMARTCTL.format(r.returncode))
                self.standby_array_states[i] = True

    def run_standby_guard(self):
        """Monitor changes in the power state of an HD array and help them to move to STANDBY state together.
        This feature is implemented in the following way:
            * step 1: Checks the power state of all HDs in array
            * step 2: Check if the array is going to STANDBY (i.e. was ACTIVE before and reached the limit with number
                      of HDs in STANDBY state), put the remaining active members to STANDBY state and log the event
            * step 3: Check if the array is waking up (i.e. was in STANDBY state before and there is any ACTIVE
                      HD(s) in the array) and log the event
        """
        hds_in_standby: int     # HDs in standby mode
        minutes: float          # Elapsed time in minutes
        cur_time: float         # New timestamp for STANDBY change

        # Step 1: check the current power state of the HD array
        hds_in_standby = self.check_standby_state()
        cur_time = time.monotonic()

        # Step 2: check if the array is going to STANDBY state.
        if not self.standby_flag and hds_in_standby >= self.standby_hd_limit:
            minutes = (cur_time - self.standby_change_timestamp) / float(3600)
            self.log.msg(self.log.LOG_INFO, f'Standby guard: Change ACTIVE to STANDBY after {minutes:.1f} hour(s)'
                         f'[{self.get_standby_state_str()}]')
            self.go_standby_state()
            self.standby_flag = True
            self.standby_change_timestamp = cur_time

        # Step 3: check if the array is waking up.
        elif self.standby_flag and hds_in_standby < self.count:
            minutes = (cur_time - self.standby_change_timestamp) / float(3600)
            self.log.msg(self.log.LOG_INFO, f'Standby guard: Change STANDBY to ACTIVE after {minutes:.1f} hour(s)'
                         f'[{self.get_standby_state_str()}]')
            self.standby_flag = False
            self.standby_change_timestamp = cur_time


class Service:
    """Service class contains all resources/functions for the execution."""

    config: configparser.ConfigParser   # Instance for a parsed configuration
    log: Log                            # Instance for a Log class
    udev_context: Context               # Reference to a udev database connection (instance of Context from pyudev)
    ipmi: Ipmi                          # Instance for an Ipmi class
    cpu_zone: CpuZone                   # Instance for a CPU Zone fan controller class
    hd_zone: HdZone                     # Instance for an HD Zone fan controller class
    cpu_zone_enabled: bool              # CPU zone fan controller enabled
    hd_zone_enabled: bool               # HD zone fan controller enabled

    def exit_func(self) -> None:
        """This function is called at exit (in case of exceptions or runtime errors cannot be handled), and it switches
           all fans back to rhw default speed 100%, in order to avoid system overheating while `smfc` is not running."""
        # Configure fans.
        if hasattr(self, "ipmi"):
            self.ipmi.set_fan_level(Ipmi.CPU_ZONE, 100)
            self.ipmi.set_fan_level(Ipmi.HD_ZONE, 100)
            if hasattr(self, "log"):
                self.log.msg(Log.LOG_INFO, 'smfc terminated: all fans are switched back to the 100% speed.')

        # Unregister this function.
        atexit.unregister(self.exit_func)

    def check_dependencies(self) -> str:
        """Check run-time dependencies of smfc:

              - ipmitool command
              - if CPU zone enabled: coretemp or k10temp kernel module
              - if HD zone enabled: drivetemp kernel module or hddtemp command

        Returns:
            (str): error string:

                - empty: dependencies are OK
                - otherwise: the error message

        """
        path: str

        # Check if ipmitool command is available.
        path = self.config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_COMMAND, '/usr/bin/ipmitool')
        if not os.path.exists(path):
            return f"ERROR: ipmitool command cannot be found {path}!"

        # Load list of kernel modules.
        with open("/proc/modules", "rt", encoding="utf-8") as file:
            modules = file.read()

        # Check kernel modules for CPUs
        if self.cpu_zone_enabled:
            if "coretemp" not in modules and "k10temp" not in modules:
                return "ERROR: coretemp or k10temp kernel module needs to be loaded!"

        """
        # Check dependencies for disks
        if self.hd_zone_enabled:
            check_hddtemp: bool = False
            check_drivetemp: bool = False
            hwmon_path: List[str] = []

            # Scan HWMON configuration for dependencies.
            hwmon_str = self.config[HdZone.CS_HD_ZONE].get(HdZone.CV_HD_ZONE_HWMON_PATH)
            if hwmon_str:
                if "\n" in hwmon_str:
                    hwmon_path = hwmon_str.splitlines()
                else:
                    hwmon_path = hwmon_str.split()
            if hwmon_path:
                for path in hwmon_path:
                    if path == HdZone.STR_HDD_TEMP:
                        check_hddtemp = True
                    else:
                        check_drivetemp = True
            else:
                check_drivetemp = True

            # Check if drivetemp kernel module is loaded
            if check_drivetemp:
                if "drivetemp" not in modules:
                    return "ERROR: drivetemp kernel module is not loaded!"

            # Check if hddtemp command is available
            if check_hddtemp:
                path = self.config[HdZone.CS_HD_ZONE].get(HdZone.CV_HD_ZONE_HDDTEMP_PATH, '/usr/sbin/hddtemp')
                if not os.path.exists(path):
                    return f"ERROR: hddtemp command cannot be found {path}!"

            # Optional: check if smartctl command is available.
            if self.config[HdZone.CS_HD_ZONE].getboolean(HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED, False):
                path = self.config[HdZone.CS_HD_ZONE].get(HdZone.CV_HD_ZONE_SMARTCTL_PATH, '/usr/sbin/smartctl')
                if not os.path.exists(path):
                    return f"ERROR: smartctl command cannot be found {path}!"
        """
        # All required run-time dependencies seems to be available.
        return ""

    def run(self) -> None:
        """Run function: main execution function of the systemd service."""
        app_parser: argparse.ArgumentParser     # Instance for an ArgumentParser class
        parsed_results: argparse.Namespace      # Results of parsed command line arguments
        old_mode: int                           # Old IPMI fan mode

        # Register the emergency exit function for service termination.
        atexit.register(self.exit_func)

        # Parse the command line arguments.
        app_parser = argparse.ArgumentParser()
        app_parser.add_argument('-c', action='store', dest='config_file', default='smfc.conf',
                                help='configuration file')
        app_parser.add_argument('-v', action='version', version='%(prog)s ' + version_str)
        app_parser.add_argument('-l', type=int, choices=[0, 1, 2, 3, 4], default=1,
                                help='log level: 0-NONE, 1-ERROR(default), 2-CONFIG, 3-INFO, 4-DEBUG')
        app_parser.add_argument('-o', type=int, choices=[0, 1, 2], default=2,
                                help='log output: 0-stdout, 1-stderr, 2-syslog(default)')
        # Note: the argument parser can exit here with the following exit codes:
        # 0 - printing help or version text
        # 2 - invalid parameter
        parsed_results = app_parser.parse_args()

        # Create a Log class instance (in theory this cannot fail).
        try:
            self.log = Log(parsed_results.l, parsed_results.o)
        except ValueError as e:
            print(f'ERROR: {e}.', flush=True, file=sys.stdout)
            sys.exit(5)

        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, 'Command line arguments:')
            self.log.msg(Log.LOG_CONFIG, f'   original arguments: {" ".join(sys.argv[:])}')
            self.log.msg(Log.LOG_CONFIG, f'   parsed config file = {parsed_results.config_file}')
            self.log.msg(Log.LOG_CONFIG, f'   parsed log level = {parsed_results.l}')
            self.log.msg(Log.LOG_CONFIG, f'   parsed log output = {parsed_results.o}')

        # Parse and load configuration file.
        self.config = configparser.ConfigParser()
        if not self.config or not self.config.read(parsed_results.config_file):
            self.log.msg(Log.LOG_ERROR, f'Cannot load configuration file ({parsed_results.config_file})')
            sys.exit(6)
        self.cpu_zone_enabled = self.config[CpuZone.CS_CPU_ZONE].getboolean(CpuZone.CV_CPU_ZONE_ENABLED, fallback=False)
        self.hd_zone_enabled = self.config[HdZone.CS_HD_ZONE].getboolean(HdZone.CV_HD_ZONE_ENABLED, fallback=False)
        self.log.msg(Log.LOG_DEBUG, f'Configuration file ({parsed_results.config_file}) loaded')

        # Check run-time dependencies (commands, kernel modules).
        error_msg = self.check_dependencies()
        if error_msg:
            self.log.msg(Log.LOG_ERROR, error_msg)
            sys.exit(4)

        # Create an Ipmi class instances and set required IPMI fan mode.
        try:
            self.ipmi = Ipmi(self.log, self.config)
            old_mode = self.ipmi.get_fan_mode()
        except (ValueError, FileNotFoundError) as e:
            self.log.msg(Log.LOG_ERROR, f'{e}.')
            sys.exit(7)
        self.log.msg(Log.LOG_DEBUG, f'Old IPMI fan mode = {self.ipmi.get_fan_mode_name(old_mode)}')
        if old_mode != Ipmi.FULL_MODE:
            self.ipmi.set_fan_mode(Ipmi.FULL_MODE)
            self.log.msg(Log.LOG_DEBUG,
                         f'New IPMI fan mode = {self.ipmi.get_fan_mode_name(Ipmi.FULL_MODE)}')

        # Initialize connection to udev database
        try:
            self.udev_context = Context()
        except ImportError as e:
            self.log.msg(Log.LOG_ERROR, f'Could not interface with libudev. Check your installation: {e}.')
            sys.exit(7)

        # Create an instance for CPU zone fan controller if enabled.
        # self.cpu_zone = None
        if self.cpu_zone_enabled:
            self.log.msg(Log.LOG_DEBUG, 'CPU zone fan controller enabled')
            self.cpu_zone = CpuZone(self.log, self.udev_context, self.ipmi, self.config)

        # Create an instance for HD zone fan controller if enabled.
        # self.hd_zone = None
        if self.hd_zone_enabled:
            self.log.msg(Log.LOG_DEBUG, 'HD zone fan controller enabled')
            self.hd_zone = HdZone(self.log, self.udev_context, self.ipmi, self.config)

        # Calculate the default sleep time for the main loop.
        if self.cpu_zone_enabled and self.hd_zone_enabled:
            wait = min(self.cpu_zone.polling, self.hd_zone.polling) / 2
        elif self.cpu_zone_enabled and not self.hd_zone_enabled:
            wait = self.cpu_zone.polling / 2
        elif not self.cpu_zone_enabled and self.hd_zone_enabled:
            wait = self.hd_zone.polling / 2
        else:  # elif not cpu_zone_enabled and not hd_controller_enabled:
            self.log.msg(Log.LOG_ERROR, 'None of the fan controllers are enabled, service terminated.')
            sys.exit(8)
        self.log.msg(Log.LOG_DEBUG, f'Main loop wait time = {wait} sec')

        # Main execution loop.
        while True:
            if self.cpu_zone_enabled:
                self.cpu_zone.run()
            if self.hd_zone_enabled:
                self.hd_zone.run()
            time.sleep(wait)


if __name__ == '__main__':
    service = Service()
    service.run()
