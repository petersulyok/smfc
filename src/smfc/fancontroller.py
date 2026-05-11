#
#   fancontroller.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.FanController() class implementation.
#
import os
import time
from collections import deque
from typing import List, Union
from pyudev import Context, Device
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import CpuConfig, HdConfig, NvmeConfig, GpuConfig


class FanController:
    """Generic fan controller class."""

    # Constant values for temperature calculation
    CALC_MIN: int = 0
    CALC_AVG: int = 1
    CALC_MAX: int = 2

    # Configuration reference (set by derived classes before calling super().__init__())
    config: Union[CpuConfig, HdConfig, NvmeConfig, GpuConfig]

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
        if self.config.temp_calc == self.CALC_MIN:
            result = min(temps)
        elif self.config.temp_calc == self.CALC_MAX:
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
