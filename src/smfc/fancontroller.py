#
#   fancontroller.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.FanController() class implementation.
#
import os
import time
from collections import deque
from typing import List, Protocol
from pyudev import Context, Device
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import Config


class FanControllerConfig(Protocol):  # pylint: disable=too-few-public-methods
    """Protocol for fan controller configuration (shared fields across CPU, HD, NVME, GPU configs)."""
    ipmi_zone: List[int]    # IPMI zone(s) assigned to the controller
    temp_calc: int          # Temperature calculation method (0-min, 1-avg, 2-max)
    steps: int              # Discrete steps in temperatures and fan levels
    sensitivity: float      # Temperature change to activate fan controller (C)
    polling: float          # Polling interval to read temperature (sec)
    min_temp: float         # Minimum temperature value (C)
    max_temp: float         # Maximum temperature value (C)
    min_level: int          # Minimum fan level (0..100%)
    max_level: int          # Maximum fan level (0..100%)
    smoothing: int          # Moving average window size for temperature readings (1=disabled)


class FanController:
    """Generic fan controller class."""

    # Configuration reference (set by derived classes before calling super().__init__())
    config: FanControllerConfig

    # Core references
    log: Log                # Reference to a Log class instance
    ipmi: Ipmi              # Reference to an Ipmi class instance
    name: str               # Name of the controller
    count: int              # Number of controlled entities
    hwmon_path: List[str]   # List of paths for HWMON devices

    # Measured or calculated attributes
    temp_step: float        # A temperature steps value (C)
    level_step: float       # A fan level step value (0..100%)
    last_time: float        # Last system time we polled temperature (timestamp)
    last_temp: float        # Last measured temperature value (C)
    last_level: int         # Last configured fan level (0..100%)
    deferred_apply: bool    # If True, skip IPMI calls (used for zone arbitration)
    _temp_history: deque    # Circular buffer storing recent temperature readings

    def __init__(self, log: Log, ipmi: Ipmi, name: str, count: int) -> None:
        """Initialize the FanController class. Derived classes must set self.config before calling this.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            name (str): name of the controller
            count (int): number of devices
        Raises:
            ValueError: invalid count parameter
            RuntimeError: temperature reading failed
        """
        self.log = log
        self.ipmi = ipmi
        self.name = name
        self.count = count

        # Validate count parameter (config parameters are validated in Config class).
        if self.count <= 0:
            raise ValueError("invalid value: count <= 0")

        # Try to read device temperature (the hwmon_path[] list has already been created by a child class).
        # If there is any problem with reading temperature, the program will stop here with an exception.
        self.get_temp()

        # Initialize calculated values using config values.
        self.temp_step = (self.config.max_temp - self.config.min_temp) / self.config.steps
        self.level_step = (self.config.max_level - self.config.min_level) / self.config.steps
        self.last_temp = 0
        self.last_level = 0
        self.last_time = time.monotonic() - (self.config.polling + 1)
        self.deferred_apply = False
        self._temp_history = deque(maxlen=self.config.smoothing)

        # Print configuration at CONFIG log level.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"{self.name} fan controller was initialized with:")
            self.log.msg(Log.LOG_CONFIG, f"   ipmi zone = {self.config.ipmi_zone}")
            self.log.msg(Log.LOG_CONFIG, f"   count = {self.count}")
            self.log.msg(Log.LOG_CONFIG, f"   temp_calc = {self.config.temp_calc}")
            self.log.msg(Log.LOG_CONFIG, f"   steps = {self.config.steps}")
            self.log.msg(Log.LOG_CONFIG, f"   sensitivity = {self.config.sensitivity}")
            self.log.msg(Log.LOG_CONFIG, f"   polling = {self.config.polling}")
            self.log.msg(Log.LOG_CONFIG, f"   min_temp = {self.config.min_temp}")
            self.log.msg(Log.LOG_CONFIG, f"   max_temp = {self.config.max_temp}")
            self.log.msg(Log.LOG_CONFIG, f"   min_level = {self.config.min_level}")
            self.log.msg(Log.LOG_CONFIG, f"   max_level = {self.config.max_level}")
            self.log.msg(Log.LOG_CONFIG, f"   smoothing = {self.config.smoothing}")
            if hasattr(self, "hwmon_path"):
                self.log.msg(Log.LOG_CONFIG, f"   hwmon_path = {[p if p else 'smartctl' for p in self.hwmon_path]}")
            self.print_temp_level_mapping()

    @staticmethod
    def get_hwmon_path(udevc: Context, parent_dev: Device) -> str:
        """Get the HWMON path of a given parent device.

        Args:
            udevc (Context): pyudev Context
            parent_dev (Device): parent device

        Returns:
            str: path for a HWMON device (empty string if not found)
        """
        try:
            [hwmon_device] = udevc.list_devices(subsystem="hwmon", parent=parent_dev)
        except ValueError:
            # If parent_dev has zero (or more?) hwmon device in its subtree
            hwmon_device = None
        return (os.path.join(hwmon_device.sys_path, "temp1_input") if hwmon_device is not None else "")

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the nth element in the hwmon list. Can be overridden by child classes.

        Args:
            index (int): index in hwmon list

        Returns:
            float: temperature value (C)
        """
        with open(self.hwmon_path[index], "r", encoding="UTF-8") as f:
            return float(f.read()) / 1000

    def get_temp(self) -> float:
        """Get the aggregated temperature of the controlled entities using the configured calculation method.

        Returns:
            float: aggregated temperature value (C)
        """
        if self.count == 1:
            return self._get_nth_temp(0)
        temps = [self._get_nth_temp(i) for i in range(self.count)]
        if self.config.temp_calc == Config.CALC_MIN:
            result = min(temps)
        elif self.config.temp_calc == Config.CALC_MAX:
            result = max(temps)
        else:
            result = sum(temps) / len(temps)
        if hasattr(self, "log") and self.log.log_level >= Log.LOG_DEBUG:
            label = ("min", "avg", "max")[self.config.temp_calc]
            self.log.msg(Log.LOG_DEBUG,
                         f"{self.name}: per-device temps={[f'{t:.1f}' for t in temps]} {label}={result:.1f}C")
        return result

    def set_fan_level(self, level: int) -> None:
        """Set the new fan level in all IPMI zones of the controller.

        Args:
            level (int): new fan level [0..100]
        """
        if not self.deferred_apply:
            self.ipmi.set_multiple_fan_levels(self.config.ipmi_zone, level)

    def callback_func(self) -> None:
        """Call-back function for a child class."""

    def create_control_function(input_str: str, steps: int) -> List[int]:
        '''
        Creates user-defined control function based ont input string from configuration file.
        Args:
            input_str (str): comma or space separated list of temperature-level values (e.g. "30-35, 50-38, 60-50, 70-100")
            steps (int): discrete steps for digitalization
        Return:
            List[int]: user-defined control function (values IPMI zone levels, index temperature
        Raise:
            ValueError: invalid input string
        '''
        tl_pairs_str: List[List[str]]    # List of temperature-level string value pairs
        tl_pairs: List[List[int]]        # List of temperature-level integer value pairs
        levels: List[int]                # User-defined control function.

        if steps < 1:
            raise ValueError(f"ERROR: Invalid steps value ({steps})!")
        
        # Step 1: Split the list to value pair strings.
        split_char = "," if "," in input_str else " "
        tl_pairs_str = input_str.split(split_char)
        if len(tl_pairs_str) < 2:
            raise ValueError(f"ERROR: User-defined control function should have minimum 2 points ({input_str})!")

        # Step 2: Convert list of [temperature, level] strings to list of [temperature, level] integer values.
        tl_pairs=[]
        for i in range(len(tl_pairs_str)):
            temp_str, level_str=tl_pairs_str[i].split("-")
            temp=int(temp_str.strip())
            level=int(level_str.strip())
            tl_pairs.append([temp, level])

        if (tl_pairs[-1][0]-tl_pairs[0][0]+1) < steps:
            raise ValueError(f"ERROR: Too many steps for a small temperature intervall ({steps})!")
        
        # Step 3: Create the user-defined control function for temperature-level mapping. This function has a list of fan levels (%)
        # and the indices of the list are the temperature values.
        levels=[]
        # Step 3.1: Fill level values on interval [0..t1-1]
        levels.extend([tl_pairs[0][1]] * tl_pairs[0][0])
        # Step 3.2: Calculate level values on the [t1..tn] interval.
        for i in range(len(tl_pairs)-1):
            t1,l1=tl_pairs[i]
            t2,l2=tl_pairs[i+1]
            temps=t2-t1
            levels.extend([int(l1 + (i * (l2-l1) / temps)) for i in range(temps)])
        # Step 3.3: Fill level values on last [tn..100] interval 
        levels.extend([l2] * (100-t2+1))

        # Step 4: Create temperature intervals for digitalization based on steps parameter.
        length = tl_pairs[-1][0] - tl_pairs[0][0] + 1  # number of discrete points
        base = length // steps
        remainder = length % steps
        digitalized_levels = levels.copy()
        start = tl_pairs[0][0]
        for i in range(steps):
            size = base + (1 if i < remainder else 0)
            end = start + size - 1  # inclusive end
            # Calculate average level value on the given temperature sub-interval.
            average=0
            for t in range(start, end+1):
                average+=levels[t]
            average=int(average / size)
            # Fill the given temperature sub-interval with the average level value.
            for t in range(start, end+1):
                digitalized_levels[t]=average
            start = end + 1
   
        return digitalized_levels

    def run(self) -> None:
        """Run IPMI zone controller function with the following steps:

        * Step 1: Read current time. If the elapsed time is bigger than the polling time period
          then go to step 2, otherwise return.
        * Step 2: Read the current temperature. If the change of the temperature goes beyond
          the sensitivity limit then go to step 3, otherwise return
        * Step 3: Calculate the current gain and fan level based on the measured temperature
        * Step 4: If the new fan level is different it will be set and logged
        """
        current_time: float  # Current system timestamp (measured)
        current_temp: float  # Current temperature (measured)
        current_level: int   # Current fan level (calculated)
        current_gain: int    # Current gain (calculated)

        # Step 1: check the elapsed time.
        current_time = time.monotonic()
        if (current_time - self.last_time) >= self.config.polling:
            self.last_time = current_time

            # Step 2: read the temperature, apply smoothing, and check the sensitivity gap.
            self.callback_func()
            raw_temp = self.get_temp()
            self._temp_history.append(raw_temp)
            current_temp = sum(self._temp_history) / len(self._temp_history)
            if self.log.log_level >= Log.LOG_DEBUG:
                if self.config.smoothing > 1:
                    self.log.msg(Log.LOG_DEBUG, f"{self.name}: raw={raw_temp:.1f}C smoothed={current_temp:.1f}C "
                                 f"(window {len(self._temp_history)}/{self.config.smoothing})")
                else:
                    self.log.msg(Log.LOG_DEBUG, f"{self.name}: new temperature > {current_temp:.1f}C")
            if abs(current_temp - self.last_temp) >= self.config.sensitivity:
                self.last_temp = current_temp

                # Step 3: calculate gain and fan level.
                if current_temp <= self.config.min_temp:
                    current_level = self.config.min_level
                elif current_temp >= self.config.max_temp:
                    current_level = self.config.max_level
                else:
                    current_gain = int(round((current_temp - self.config.min_temp) / self.temp_step))
                    current_level = (int(round(float(current_gain) * self.level_step)) + self.config.min_level)
                if self.log.log_level >= Log.LOG_DEBUG:
                    self.log.msg(Log.LOG_DEBUG, f"{self.name}: calculated level={current_level}% "
                                 f"for temp={current_temp:.1f}C")

                # Step 4: the new fan level will be set and logged.
                if current_level != self.last_level:
                    self.last_level = current_level
                    self.set_fan_level(current_level)
                    if not self.deferred_apply:
                        self.log.msg(Log.LOG_INFO,
                                     f"IPMI zone {self.config.ipmi_zone}: new level = {current_level}% "
                                     f"({self.name}={current_temp:.1f}C)")
                elif self.log.log_level >= Log.LOG_DEBUG:
                    self.log.msg(Log.LOG_DEBUG, f"{self.name}: level unchanged at {current_level}%")
            elif self.log.log_level >= Log.LOG_DEBUG:
                self.log.msg(Log.LOG_DEBUG, f"{self.name}: sensitivity not reached "
                             f"(delta={abs(current_temp - self.last_temp):.1f}C < {self.config.sensitivity:.1f}C)")
        elif self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f"{self.name}: polling skipped "
                         f"(remaining={self.config.polling - (current_time - self.last_time):.1f}s)")

    def print_temp_level_mapping(self) -> None:
        """Print out the user-defined temperature to level mapping value in log DEBUG level."""
        self.log.msg(Log.LOG_CONFIG, "   User-defined control function:")
        for i in range(self.config.steps + 1):
            self.log.msg(Log.LOG_CONFIG, f"   {i}. [T:{self.config.min_temp + (i * self.temp_step):.1f}C - "
                         f"L:{int(self.config.min_level + (i * self.level_step))}%]")


# End.
