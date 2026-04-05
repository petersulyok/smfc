#
#   cpufc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.CpuFc() class implementation.
#
from configparser import ConfigParser
from pyudev import Context
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class CpuFc(FanController):
    """Class for CPU fan controller."""

    # Constant values for the configuration parameters.
    CS_CPU_FC: str = "CPU"
    CV_CPU_FC_ENABLED: str = "enabled"
    CV_CPU_FC_IPMI_ZONE: str = "ipmi_zone"
    CV_CPU_FC_TEMP_CALC: str = "temp_calc"
    CV_CPU_FC_STEPS: str = "steps"
    CV_CPU_FC_SENSITIVITY: str = "sensitivity"
    CV_CPU_FC_POLLING: str = "polling"
    CV_CPU_FC_MIN_TEMP: str = "min_temp"
    CV_CPU_FC_MAX_TEMP: str = "max_temp"
    CV_CPU_FC_MIN_LEVEL: str = "min_level"
    CV_CPU_FC_MAX_LEVEL: str = "max_level"
    CV_CPU_FC_SMOOTHING: str = "smoothing"

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser) -> None:
        """Initialize the CPU fan controller class and raise exception in case of invalid configuration.
        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            config (ConfigParser): reference to the configuration
        Raises:
            ValueError: multiple hwmon devices reported, one expected
            RuntimeError: No HWMON device found for CPU(s)
        """
        count: int  # CPU count.

        # Build the list of paths for hwmon devices.
        self.hwmon_path = []
        # We are looking for either Intel (coretemp) or AMD (k10temp) CPUs.
        for dev_filter in [{"MODALIAS":"platform:coretemp"}, {"DRIVER":"k10temp"}]:
            self.hwmon_path = [self.get_hwmon_path(udevc, dev) for dev in udevc.list_devices(**dev_filter)]
            # If we found results.
            if self.hwmon_path:
                break
        if not self.hwmon_path:
            raise RuntimeError("pyudev: No HWMON device(s) can be found for the CPU.")
        # Calculate count.
        count = len(self.hwmon_path)

        # Initialize FanController class.
        super().__init__(
            log, ipmi,
            config[CpuFc.CS_CPU_FC].get(CpuFc.CV_CPU_FC_IPMI_ZONE, fallback=f"{Ipmi.CPU_ZONE}"),
            CpuFc.CS_CPU_FC, count,
            config[CpuFc.CS_CPU_FC].getint(CpuFc.CV_CPU_FC_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[CpuFc.CS_CPU_FC].getint(CpuFc.CV_CPU_FC_STEPS, fallback=6),
            config[CpuFc.CS_CPU_FC].getfloat(CpuFc.CV_CPU_FC_SENSITIVITY, fallback=3.0),
            config[CpuFc.CS_CPU_FC].getfloat(CpuFc.CV_CPU_FC_POLLING, fallback=2),
            config[CpuFc.CS_CPU_FC].getfloat(CpuFc.CV_CPU_FC_MIN_TEMP, fallback=30.0),
            config[CpuFc.CS_CPU_FC].getfloat(CpuFc.CV_CPU_FC_MAX_TEMP, fallback=60.0),
            config[CpuFc.CS_CPU_FC].getint(CpuFc.CV_CPU_FC_MIN_LEVEL, fallback=35),
            config[CpuFc.CS_CPU_FC].getint(CpuFc.CV_CPU_FC_MAX_LEVEL, fallback=100),
            config[CpuFc.CS_CPU_FC].getint(CpuFc.CV_CPU_FC_SMOOTHING, fallback=1),
        )


# End.
