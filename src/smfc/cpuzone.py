#
#   cpuzone.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.CpuZone() class implementation.
#
import configparser
from pyudev import Context
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


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
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            config (configparser.ConfigParser): reference to the configuration (default=None)

        Raises:
            ValueError: multiple hwmon devices reported, one expected
            RuntimeError: No HWMON device found for CPU(s)
        """

        # Build the list of paths for hwmon devices.
        self.udevc = udevc
        self.hwmon_dev = []
        # We are looking for either Intel (coretemp) or AMD (k10temp) CPUs.
        for dev_filter in [{'MODALIAS':'platform:coretemp'}, {'DRIVER':'k10temp'}]:
            try:
                self.hwmon_path = [self.get_hwmon_path(dev) for dev in self.udevc.list_devices(**dev_filter)]
            except ValueError as e:
                raise e
            # If we found results.
            if self.hwmon_dev:
                break
        if not self.hwmon_dev:
            raise RuntimeError('pyudev: No HWMON device(s) can be found for CPU.')
        # Set count.
        self.count = len(self.hwmon_dev)

        # Initialize FanController class.
        super().__init__(
            log, ipmi, Ipmi.CPU_ZONE, self.CS_CPU_ZONE,
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
        value: float  # Temperature value

        try:
            with open(self.hwmon_path[index], "r", encoding="UTF-8") as f:
                value = float(f.read()) / 1000
        except (IOError, FileNotFoundError, ValueError) as e:
            raise e
        return value

# End.
