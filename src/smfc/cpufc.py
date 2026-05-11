#
#   cpufc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.CpuFc() class implementation.
#
from pyudev import Context
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import CpuConfig


class CpuFc(FanController):
    """Class for CPU fan controller."""

    config: CpuConfig

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: CpuConfig) -> None:
        """Initialize the CPU fan controller class and raise exception in case of invalid configuration.
        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            cfg (CpuConfig): CPU fan controller configuration
        Raises:
            ValueError: multiple hwmon devices reported, one expected
            RuntimeError: No HWMON device found for CPU(s)
        """
        # Store config reference first (required by base class)
        self.config = cfg

        # Build the list of paths for hwmon devices.
        self.hwmon_path = []
        # We are looking for either Intel (coretemp) or AMD (k10temp) CPUs.
        for dev_filter in [{"MODALIAS": "platform:coretemp"}, {"DRIVER": "k10temp"}]:
            self.hwmon_path = [self.get_hwmon_path(udevc, dev) for dev in udevc.list_devices(**dev_filter)]
            # If we found results.
            if self.hwmon_path:
                break
        if not self.hwmon_path:
            raise RuntimeError("pyudev: No HWMON device(s) can be found for the CPU.")

        # Initialize FanController class.
        super().__init__(log, ipmi, cfg.section, len(self.hwmon_path))


# End.
