#
#   fancontroller.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.FanController() class implementation.
#
import os
import time
from collections import deque
from typing import List, Protocol, Tuple
from pyudev import Context, Device
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import Config


class FanControllerConfig(Protocol):  # pylint: disable=too-few-public-methods
    """Protocol for fan controller configuration (shared fields across CPU, HD, NVME, GPU configs)."""
    ipmi_zone: List[int]                    # IPMI zone(s) assigned to the controller
    temp_calc: int                          # Temperature calculation method (0-min, 1-avg, 2-max)
    steps: int                              # Discrete steps in temperatures and fan levels
    sensitivity: float                      # Temperature change to activate fan controller (C)
    polling: float                          # Polling interval to read temperature (sec)
    min_temp: float                         # Minimum temperature value (C)
    max_temp: float                         # Maximum temperature value (C)
    min_level: int                          # Minimum fan level (0..100%)
    max_level: int                          # Maximum fan level (0..100%)
    smoothing: int                          # Moving average window size (1=disabled)
    control_function: List[Tuple[int, int]] # User-defined (T,L) breakpoints; empty = legacy mode


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
    temp_step: float        # A temperature steps value (C) — legacy mode only, used for logging
    level_step: float       # A fan level step value (0..100%) — legacy mode only, used for logging
    levels_lut: List[int]   # 101-element temperature->level lookup table (index = T in C)
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
        self.levels_lut = FanController.build_lut(self.config)
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

    @staticmethod
    def create_legacy_lut(min_temp: float, max_temp: float, min_level: int, max_level: int, steps: int) -> List[int]:
        """Build a 101-element LUT from the legacy min/max temp+level keys using the original staircase formula.

        Each integer temperature T in [0..100] gets mapped to its fan level the same way the previous
        run() did at runtime:
            T <= min_temp        -> min_level
            T >= max_temp        -> max_level
            otherwise            -> round((T - min_temp) / temp_step) * level_step + min_level
        Args:
            min_temp (float): minimum temperature (C)
            max_temp (float): maximum temperature (C)
            min_level (int): minimum fan level (%)
            max_level (int): maximum fan level (%)
            steps (int): discrete staircase steps
        Returns:
            List[int]: 101-element LUT (index = temperature in C, value = fan level in %)
        """
        temp_step = (max_temp - min_temp) / steps
        level_step = (max_level - min_level) / steps
        lut: List[int] = [0] * 101
        for t in range(101):
            if t <= min_temp:
                lut[t] = min_level
            elif t >= max_temp:
                lut[t] = max_level
            else:
                gain = int(round((t - min_temp) / temp_step))
                lut[t] = int(round(gain * level_step)) + min_level
        return lut

    @staticmethod
    def create_control_function(pairs: List[Tuple[int, int]], steps: int) -> List[int]:
        """Build a 101-element LUT from validated (T, L) breakpoints using interior-only digitalization
        with endpoint pinning. Produces `steps + 2` plateaus: 1 at t_first, `steps` in the interior,
        1 at t_last.
        Args:
            pairs (List[Tuple[int, int]]): validated breakpoints (already range-checked and strictly
                ascending in T; see Config.parse_control_function)
            steps (int): number of interior plateaus
        Returns:
            List[int]: 101-element LUT (index = temperature in C, value = fan level in %)
        """
        t_first, l_first = pairs[0]
        t_last, l_last = pairs[-1]

        # Step 1: per-degree piecewise-linear LUT, with the head and tail padded to their endpoint levels.
        levels: List[int] = [l_first] * t_first
        for i in range(len(pairs) - 1):
            t1, l1 = pairs[i]
            t2, l2 = pairs[i + 1]
            dt = t2 - t1
            levels.extend([round(l1 + (di * (l2 - l1) / dt)) for di in range(dt)])
        levels.extend([l_last] * (100 - t_last + 1))

        # Step 2: digitalize the interior [t_first+1 .. t_last-1] into `steps` equal-width plateaus.
        interior_len = t_last - t_first - 1
        if interior_len > 0 and steps >= 1:
            base = interior_len // steps
            remainder = interior_len % steps
            start = t_first + 1
            for i in range(steps):
                size = base + (1 if i < remainder else 0)
                if size == 0:
                    continue
                end = start + size - 1
                avg = round(sum(levels[start:end + 1]) / size)
                for t in range(start, end + 1):
                    levels[t] = avg
                start = end + 1

        # Step 3: pin the user-defined endpoints (Step 2 leaves these untouched; explicit writes
        # make the endpoint contract obvious to future readers).
        levels[t_first] = l_first
        levels[t_last] = l_last
        return levels

    @classmethod
    def build_lut(cls, config: FanControllerConfig) -> List[int]:
        """Build the 101-element temperature->level LUT for a fan controller config.

        Dispatches between the legacy staircase formula and the new piecewise-linear control function
        based on whether `control_function` was specified in the config.
        Args:
            config (FanControllerConfig): controller config (CPU/HD/NVME/GPU)
        Returns:
            List[int]: 101-element LUT (index = temperature in C, value = fan level in %)
        """
        if config.control_function:
            return cls.create_control_function(config.control_function, config.steps)
        return cls.create_legacy_lut(config.min_temp, config.max_temp,
                                     config.min_level, config.max_level, config.steps)

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
        current_level: int   # Current fan level (looked up from LUT)

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

                # Step 3: look up the fan level for the (clamped, integer-rounded) temperature.
                idx = max(0, min(100, int(round(current_temp))))
                current_level = self.levels_lut[idx]
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
        """Print the temperature->level mapping at LOG_CONFIG level by walking the LUT and emitting
        one line per plateau (consecutive temperatures sharing the same level)."""
        if self.config.control_function:
            self.log.msg(Log.LOG_CONFIG, f"   control_function = {self.config.control_function}")
        else:
            self.log.msg(Log.LOG_CONFIG, "   Temperature to level mapping (from legacy min/max keys):")
        plateau_start = 0
        for t in range(1, 102):
            if t == 101 or self.levels_lut[t] != self.levels_lut[plateau_start]:
                end = t - 1
                lvl = self.levels_lut[plateau_start]
                if plateau_start == end:
                    self.log.msg(Log.LOG_CONFIG, f"   T={plateau_start}C -> L={lvl}%")
                else:
                    self.log.msg(Log.LOG_CONFIG, f"   T=[{plateau_start}..{end}]C -> L={lvl}%")
                plateau_start = t


# End.
