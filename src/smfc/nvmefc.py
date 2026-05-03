#
#   nvmefc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.NvmeFc() class implementation.
#
from configparser import ConfigParser
from typing import List
from pyudev import Context, Devices, DeviceNotFoundByFileError
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class NvmeFc(FanController):
    """Class for NVMe fan controller."""

    # NvmeFc specific parameters.
    nvme_device_names: List[str]    # Device names of the NVMe drives in '/dev/disk/by-id/...' format.

    # Constant values for the configuration parameters.
    CS_NVME_FC: str = "NVME"
    CV_NVME_FC_ENABLED: str = "enabled"
    CV_NVME_FC_IPMI_ZONE: str = "ipmi_zone"
    CV_NVME_FC_TEMP_CALC: str = "temp_calc"
    CV_NVME_FC_STEPS: str = "steps"
    CV_NVME_FC_SENSITIVITY: str = "sensitivity"
    CV_NVME_FC_POLLING: str = "polling"
    CV_NVME_FC_MIN_TEMP: str = "min_temp"
    CV_NVME_FC_MAX_TEMP: str = "max_temp"
    CV_NVME_FC_MIN_LEVEL: str = "min_level"
    CV_NVME_FC_MAX_LEVEL: str = "max_level"
    CV_NVME_FC_SMOOTHING: str = "smoothing"
    CV_NVME_FC_NVME_NAMES: str = "nvme_names"

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser,
                 section: str = CS_NVME_FC) -> None:
        """Initialize the NVME fan controller class and raise exception in case of invalid configuration.

        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            config (ConfigParser): reference to the configuration
            section (str): configuration section name (default: CS_NVME_FC)

        Raises:
            ValueError: invalid configuration parameters (e.g. missing nvme_names)
        """
        nvme_names: str  # String for nvme_names=
        count: int  # NVMe count.

        # Save and validate NvmeFc class-specific parameters.
        nvme_names = config[section].get(self.CV_NVME_FC_NVME_NAMES)
        if not nvme_names:
            raise ValueError("Parameter nvme_names= is not specified.")
        if "\n" in nvme_names:
            self.nvme_device_names = nvme_names.splitlines()
        else:
            self.nvme_device_names = nvme_names.split()
        # Set count.
        count = len(self.nvme_device_names)

        # Iterate through each NVMe device.
        self.hwmon_path = []
        for i in range(count):
            # Find a device in udev database based on device name.
            try:
                block_dev = Devices.from_device_file(udevc, self.nvme_device_names[i])
            except DeviceNotFoundByFileError:
                raise ValueError(f"nvme_names= parameter error: '{self.nvme_device_names[i]}' cannot be reached."
                        ) from DeviceNotFoundByFileError
            # Get the hwmon path for NVMe device.
            hwmon = self.get_hwmon_path(udevc, block_dev.parent)
            if not hwmon:
                raise ValueError(f"nvme_names= parameter error: '{self.nvme_device_names[i]}' has no hwmon path.")
            self.hwmon_path.append(hwmon)

        # Initialize FanController class.
        super().__init__(
            log, ipmi,
            config[section].get(NvmeFc.CV_NVME_FC_IPMI_ZONE, fallback=f"{Ipmi.HD_ZONE}"),
            section, count,
            config[section].getint(NvmeFc.CV_NVME_FC_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[section].getint(NvmeFc.CV_NVME_FC_STEPS, fallback=4),
            config[section].getfloat(NvmeFc.CV_NVME_FC_SENSITIVITY, fallback=2),
            config[section].getfloat(NvmeFc.CV_NVME_FC_POLLING, fallback=10),
            config[section].getfloat(NvmeFc.CV_NVME_FC_MIN_TEMP, fallback=35),
            config[section].getfloat(NvmeFc.CV_NVME_FC_MAX_TEMP, fallback=70),
            config[section].getint(NvmeFc.CV_NVME_FC_MIN_LEVEL, fallback=35),
            config[section].getint(NvmeFc.CV_NVME_FC_MAX_LEVEL, fallback=100),
            config[section].getint(NvmeFc.CV_NVME_FC_SMOOTHING, fallback=1),
        )

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   {self.CV_NVME_FC_NVME_NAMES} = {self.nvme_device_names}")


# End.
