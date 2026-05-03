#
#   nvmefc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.NvmeFc() class implementation.
#
from typing import List
from pyudev import Context, Devices, DeviceNotFoundByFileError
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import NvmeConfig


class NvmeFc(FanController):
    """Class for NVMe fan controller."""

    config: NvmeConfig

    # NvmeFc specific parameters.
    nvme_device_names: List[str]    # Device names of the NVMe drives in '/dev/disk/by-id/...' format.

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: NvmeConfig) -> None:
        """Initialize the NVME fan controller class and raise exception in case of invalid configuration.

        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            cfg (NvmeConfig): NVME fan controller configuration

        Raises:
            ValueError: invalid configuration parameters (e.g. device not reachable)
        """
        # Store config reference first (required by base class)
        self.config = cfg

        # Save NvmeFc class-specific parameters (validation done in Config).
        self.nvme_device_names = cfg.nvme_names

        # Iterate through each NVMe device.
        self.hwmon_path = []
        for i in range(len(self.nvme_device_names)):
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
        super().__init__(log, ipmi, cfg.section, len(self.nvme_device_names))

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   nvme_names = {self.nvme_device_names}")


# End.
