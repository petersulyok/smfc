#
#   cpuzone.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.CpuZone() class implementation.
#
from configparser import ConfigParser
from pyudev import Context
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class CpuZone(FanController):
    """CPU zone fan control."""

    # Constant values for the configuration parameters.
    CS_CPU_ZONE: str = 'CPU zone'
    CV_CPU_ZONE_ENABLED: str = 'enabled'
    CV_CPU_IPMI_ZONE: str = 'ipmi_zone'
    CV_CPU_ZONE_TEMP_CALC: str = 'temp_calc'
    CV_CPU_ZONE_STEPS: str = 'steps'
    CV_CPU_ZONE_SENSITIVITY: str = 'sensitivity'
    CV_CPU_ZONE_POLLING: str = 'polling'
    CV_CPU_ZONE_MIN_TEMP: str = 'min_temp'
    CV_CPU_ZONE_MAX_TEMP: str = 'max_temp'
    CV_CPU_ZONE_MIN_LEVEL: str = 'min_level'
    CV_CPU_ZONE_MAX_LEVEL: str = 'max_level'

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, config:ConfigParser) -> None:
        """Initialize the CpuZone class and raise exception in case of invalid configuration.
        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            config (ConfigParser): reference to the configuration (default=None)
        Raises:
            ValueError: multiple hwmon devices reported, one expected
            RuntimeError: No HWMON device found for CPU(s)
        """
        count: int  # CPU count.

        # Build the list of paths for hwmon devices.
        self.hwmon_path = []
        # We are looking for either Intel (coretemp) or AMD (k10temp) CPUs.
        for dev_filter in [{'MODALIAS':'platform:coretemp'}, {'DRIVER':'k10temp'}]:
            self.hwmon_path = [self.get_hwmon_path(udevc, dev) for dev in udevc.list_devices(**dev_filter)]
            # If we found results.
            if self.hwmon_path:
                break
        if not self.hwmon_path:
            raise RuntimeError('pyudev: No HWMON device(s) can be found for the CPU.')
        # Calculate count.
        count = len(self.hwmon_path)

        # Initialize FanController class.
        super().__init__(log, ipmi,
            config[CpuZone.CS_CPU_ZONE].get(CpuZone.CV_CPU_IPMI_ZONE, fallback=f'{Ipmi.CPU_ZONE}'),
            CpuZone.CS_CPU_ZONE, count,
            config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_STEPS, fallback=6),
            config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_SENSITIVITY, fallback=3.0),
            config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_POLLING, fallback=2),
            config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_MIN_TEMP, fallback=30.0),
            config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_MAX_TEMP, fallback=60.0),
            config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_MIN_LEVEL, fallback=35),
            config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_MAX_LEVEL, fallback=100)
        )

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the 'nth' element in the hwmon list.
           Args:
               index (int): index in hwmon list
           Returns:
               float: temperature value
           Raises:
               FileNotFoundError:   file not found
               IOError:             file cannot be opened
               ValueError:          invalid value read from file
               IndexError:          invalid index
           """
        value: float  # Temperature value

        try:
            with open(self.hwmon_path[index], "r", encoding="UTF-8") as f:
                value = float(f.read()) / 1000
        except (IOError, FileNotFoundError, ValueError) as e:
            raise e
        return value

# End.
