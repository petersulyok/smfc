#
#   cpuzone.py (C) 2020-2024, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.CpuZone() class implementation.
#
import configparser
import glob
from typing import List

from .fancontroller import FanController
from .ipmi import Ipmi
from .log import Log


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

    def __init__(self, log: Log, ipmi: Ipmi, config: configparser.ConfigParser) -> None:
        """Initialize the CpuZone class and raise exception in case of invalid configuration.

        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            config (configparser.ConfigParser): reference to the configuration (default=None)
        """

        # Initialize FanController class.
        super().__init__(
            log, ipmi, Ipmi.CPU_ZONE, self.CS_CPU_ZONE,
            config[self.CS_CPU_ZONE].getint(self.CV_CPU_ZONE_COUNT, fallback=1),
            config[self.CS_CPU_ZONE].getint(self.CV_CPU_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[self.CS_CPU_ZONE].getint(self.CV_CPU_ZONE_STEPS, fallback=6),
            config[self.CS_CPU_ZONE].getfloat(self.CV_CPU_ZONE_SENSITIVITY, fallback=3.0),
            config[self.CS_CPU_ZONE].getfloat(self.CV_CPU_ZONE_POLLING, fallback=2),
            config[self.CS_CPU_ZONE].getfloat(self.CV_CPU_ZONE_MIN_TEMP, fallback=30.0),
            config[self.CS_CPU_ZONE].getfloat(self.CV_CPU_ZONE_MAX_TEMP, fallback=60.0),
            config[self.CS_CPU_ZONE].getint(self.CV_CPU_ZONE_MIN_LEVEL, fallback=35),
            config[self.CS_CPU_ZONE].getint(self.CV_CPU_ZONE_MAX_LEVEL, fallback=100),
            config[self.CS_CPU_ZONE].get(self.CV_CPU_ZONE_HWMON_PATH),
            set()
        )

    def build_hwmon_path(self, hwmon_str: str) -> None:
        """Build hwmon_path[] list for the CPU zone."""
        path: str               # Path string
        file_names: List[str]   # Result list of glob.glob()

        # If the user specified the hwmon_path= configuration item.
        if hwmon_str:
            # Convert the string into a list of path.
            super().build_hwmon_path(hwmon_str)
        # If the hwmon_path string was not specified it will be created automatically.
        else:
            # Construct hwmon_path with the resolution of wildcard characters.
            self.hwmon_path = []
            for i in range(self.count):
                path = '/sys/devices/platform/coretemp.' + str(i) + '/hwmon/hwmon*/temp1_input'
                file_names = glob.glob(path)
                if not file_names:
                    raise ValueError(self.ERROR_MSG_FILE_IO.format(path))
                self.hwmon_path.append(file_names[0])

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

        try:
            with open(self.hwmon_path[index], "r", encoding="UTF-8") as f:
                value = float(f.read()) / 1000
        except (IOError, FileNotFoundError, ValueError) as e:
            raise e
        return value


# End.
