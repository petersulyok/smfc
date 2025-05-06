#
#   fancontroller.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.FanController() class implementation.
#
import os
import time
import re
from typing import List, Callable
from pyudev import Context, Device
from smfc.ipmi import Ipmi
from smfc.log import Log


class FanController:
    """Generic fan controller class for an IPMI zone."""

    # Constant values for temperature calculation
    CALC_MIN: int = 0
    CALC_AVG: int = 1
    CALC_MAX: int = 2

    # Configuration parameters
    log: Log                # Reference to a Log class instance
    ipmi: Ipmi              # Reference to an Ipmi class instance
    ipmi_zone: List[int]    # List of IPMI zones assigned to this fan controller
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
    hwmon_path: List[str]   # List of paths for HWMON devices

    # Measured or calculated attributes
    temp_step: float        # A temperature steps value (C)
    level_step: float       # A fan level step value (0..100%)
    last_time: float        # Last system time we polled temperature (timestamp)
    last_temp: float        # Last measured temperature value (C)
    last_level: int         # Last configured fan level (0..100%)

    # Function variable for selected temperature calculation method
    get_temp_func: Callable[[], float]

    def __init__(self, log: Log, ipmi: Ipmi, ipmi_zone: str, name: str, count: int, temp_calc: int,
                 steps: int, sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                 max_level: int) -> None:
        """Initialize the FanController class. Will raise an exception in case of invalid parameters.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            ipmi_zone (str): IPMI zone(s) assigned to the controller
            name (str): name of the controller
            count (int): number of devices
            temp_calc (int): calculation of temperature
            steps (int): discrete steps in temperatures and fan levels
            sensitivity (float): temperature change to activate fan controller (C)
            polling (float): polling time interval for reading temperature (sec)
            min_temp (float): minimum temperature value (C)
            max_temp (float): maximum temperature value (C)
            min_level (int): minimum fan level value [0..100%]
            max_level (int): maximum fan level value [0..100%]
        Raises:
            ValueError: invalid input parameter
        """
        # Save and validate configuration parameters.
        self.log = log
        self.ipmi = ipmi
        # Read the list of IPMI zones from a string (trim and remove multiple spaces, convert strings to integers)
        zone_str = re.sub(' +', ' ', ipmi_zone.strip())
        try:
            self.ipmi_zone = [int(s) for s in zone_str.split(',' if ',' in ipmi_zone else ' ')]
        except ValueError as e:
            raise e
        for zone in self.ipmi_zone:
            if zone not in range(0, 101):
                raise ValueError(f'invalid value: ipmi_zone={ipmi_zone}.')
        self.name = name
        self.count = count
        if self.count <= 0:
            raise ValueError('invalid value: count <= 0')
        self.temp_calc = temp_calc
        if self.temp_calc not in {self.CALC_MIN, self.CALC_AVG, self.CALC_MAX}:
            raise ValueError(f'invalid value: temp_calc ({temp_calc}).')
        self.steps = steps
        if self.steps <= 0:
            raise ValueError('invalid value: steps <= 0')
        self.sensitivity = sensitivity
        if self.sensitivity <= 0:
            raise ValueError('invalid value: sensitivity <= 0')
        self.polling = polling
        if self.polling < 0:
            raise ValueError('polling < 0')
        if max_temp < min_temp:
            raise ValueError('invalid value: max_temp < min_temp')
        self.min_temp = min_temp
        self.max_temp = max_temp
        if max_level < min_level:
            raise ValueError('invalid value: max_level < min_level')
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

        # Try to read device temperature (the hwmon_path[] list has already been created by a child class).
        # If there is any problem with reading temperature, the program will stop here with an exception.
        self.get_temp_func()

        # Initialize calculated values.
        self.temp_step = (max_temp - min_temp) / steps
        self.level_step = (max_level - min_level) / steps
        self.last_temp = 0
        self.last_level = 0
        self.last_time = time.monotonic() - (polling + 1)
        # Print configuration at DEBUG log level.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f'{self.name} fan controller was initialized with:')
            self.log.msg(Log.LOG_CONFIG, f'   ipmi zone = {self.ipmi_zone}')
            self.log.msg(Log.LOG_CONFIG, f'   count = {self.count}')
            self.log.msg(Log.LOG_CONFIG, f'   temp_calc = {self.temp_calc}')
            self.log.msg(Log.LOG_CONFIG, f'   steps = {self.steps}')
            self.log.msg(Log.LOG_CONFIG, f'   sensitivity = {self.sensitivity}')
            self.log.msg(Log.LOG_CONFIG, f'   polling = {self.polling}')
            self.log.msg(Log.LOG_CONFIG, f'   min_temp = {self.min_temp}')
            self.log.msg(Log.LOG_CONFIG, f'   max_temp = {self.max_temp}')
            self.log.msg(Log.LOG_CONFIG, f'   min_level = {self.min_level}')
            self.log.msg(Log.LOG_CONFIG, f'   max_level = {self.max_level}')
            if hasattr(self, 'hwmon_path'):
                self.log.msg(Log.LOG_CONFIG, f'   hwmon_path = {[p if p else "smartctl" for p in self.hwmon_path]}')
            self.print_temp_level_mapping()

    @staticmethod
    def get_hwmon_path(udevc: Context, parent_dev: Device) -> str:
        """A helper function to get HWMON path of a given parent device's associated hwmon

        Args:
            udevc (Context): pyudev Context
            parent_dev (Device): parent device
        Returns:
            str: path for a HWMON device
        """
        try:
            [hwmon_device] = udevc.list_devices(subsystem='hwmon', parent=parent_dev)
        except ValueError:
            # If parent_dev has zero (or more?) hwmon device in its subtree
            hwmon_device = None
        return os.path.join(hwmon_device.sys_path, 'temp1_input') if hwmon_device is not None else ''

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the 'nth' element in the hwmon list. This is an empty implementation."""

    def get_1_temp(self) -> float:
        """Get a single temperature of a controlled entity in the IPMI zone.

        Returns:
            float: single temperature of a controlled entity (C)
        """
        return self._get_nth_temp(0)

    def get_min_temp(self) -> float:
        """Get the minimum temperature of multiple controlled entities.

        Returns:
            float: minimum temperature of the controlled entities (C)
        """
        minimum: float      # Minimum temperature value

        # Calculate minimum temperature.
        minimum = 1000.0
        for i in range(self.count):
            minimum = min(self._get_nth_temp(i), minimum)
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

    def get_max_temp(self) -> float:
        """Get the maximum temperature of the controlled entities in the IPMI zone.

           Returns:
                float: maximum temperature of the controlled entities (C)
        """
        maximum: float      # Maximum temperature value

        # Calculate minimum temperature.
        maximum = -1.0
        for i in range(self.count):
            maximum = max(self._get_nth_temp(i), maximum)
        return maximum

    def set_fan_level(self, level: int) -> None:
        """Set the new fan level in all IPMI zones of the controller.

        Args:
            level (int): new fan level [0..100]
        """
        self.ipmi.set_multiple_fan_levels(self.ipmi_zone, level)

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
        current_gain: int       # Current gain (calculated)

        # Step 1: check the elapsed time.
        current_time = time.monotonic()
        if (current_time - self.last_time) >= self.polling:
            self.last_time = current_time

            # Step 2: read the temperature and check the sensitivity gap.
            self.callback_func()
            current_temp = self.get_temp_func()
            self.log.msg(Log.LOG_DEBUG, f'{self.name}: new temperature > {current_temp:.1f}C')
            if abs(current_temp - self.last_temp) >= self.sensitivity:
                self.last_temp = current_temp

                # Step 3: calculate gain and fan level.
                if current_temp <= self.min_temp:
                    current_level = self.min_level
                elif current_temp >= self.max_temp:
                    current_level = self.max_level
                else:
                    current_gain = int(round((current_temp - self.min_temp) / self.temp_step))
                    current_level = int(round(float(current_gain) * self.level_step)) + self.min_level

                # Step 4: the new fan level will be set and logged.
                if current_level != self.last_level:
                    self.last_level = current_level
                    self.set_fan_level(current_level)
                    self.log.msg(Log.LOG_INFO, f'{self.name}: new fan level > {current_level}%/{current_temp:.1f}C'
                                 f' @ IPMI {self.ipmi_zone} zone(s).')

    def print_temp_level_mapping(self) -> None:
        """Print out the user-defined temperature to level mapping value in log DEBUG level."""
        self.log.msg(Log.LOG_CONFIG, '   User-defined control function:')
        for i in range(self.steps + 1):
            self.log.msg(Log.LOG_CONFIG, f'   {i}. [T:{self.min_temp+(i*self.temp_step):.1f}C - '
                         f'L:{int(self.min_level + (i * self.level_step))}%]')

# End.
