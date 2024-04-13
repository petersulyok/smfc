from typing import List

import configparser
import glob
import os
import subprocess
import time 

from .fans import FanController
from .logger import Log
from .bmc import Ipmi

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

class HdZone(FanController):
    """Class for HD zone fan control."""

    # HdZone specific parameters.
    hd_device_names: List[str]          # Device names of the hard disks (e.g. '/dev/disk/by-id/...').

    # Standby guard specific parameters.
    standby_guard_enabled: bool         # Standby guard feature enabled
    standby_hd_limit: int               # Number of HDs in STANDBY state before the full RAID array will go STANDBY
    smartctl_path: str                  # Path for 'smartctl' command
    hddtemp_path: str                   # Path for 'hddtemp' command
    standby_flag: bool                  # The actual state of the whole HD array
    standby_change_timestamp: float     # Timestamp of the latest change in STANDBY mode
    standby_array_states: List[bool]    # Standby states of HDs

    # Error message.
    ERROR_MSG_SMARTCTL: str = 'Unknown smartctl return value {}'

    # Constant values for the configuration parameters.
    CS_HD_ZONE: str = 'HD zone'
    CV_HD_ZONE_ENABLED: str = 'enabled'
    CV_HD_ZONE_COUNT: str = 'count'
    CV_HD_ZONE_TEMP_CALC: str = 'temp_calc'
    CV_HD_ZONE_STEPS: str = 'steps'
    CV_HD_ZONE_SENSITIVITY: str = 'sensitivity'
    CV_HD_ZONE_POLLING: str = 'polling'
    CV_HD_ZONE_MIN_TEMP: str = 'min_temp'
    CV_HD_ZONE_MAX_TEMP: str = 'max_temp'
    CV_HD_ZONE_MIN_LEVEL: str = 'min_level'
    CV_HD_ZONE_MAX_LEVEL: str = 'max_level'
    CV_HD_ZONE_HD_NAMES: str = 'hd_names'
    CV_HD_ZONE_HWMON_PATH: str = 'hwmon_path'
    CV_HD_ZONE_STANDBY_GUARD_ENABLED: str = 'standby_guard_enabled'
    CV_HD_ZONE_STANDBY_HD_LIMIT: str = 'standby_hd_limit'
    CV_HD_ZONE_SMARTCTL_PATH: str = 'smartctl_path'
    CV_HD_ZONE_HDDTEMP_PATH: str = 'hddtemp_path'

    # Constant for using 'hddtemp'
    STR_HDD_TEMP: str = 'hddtemp'

    def __init__(self, log: Log, ipmi: Ipmi, config: configparser.ConfigParser) -> None:
        """Initialize the HdZone class. Abort in case of configuration errors.

        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            config (configparser.ConfigParser): reference to the configuration (default=None)
        """
        count: int      # HD count
        hd_names: str   # String for hd_names=

        # Read count parameter.
        count = config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_COUNT, fallback=1)
        if count <= 0:
            raise ValueError('count <= 0')
        # Save and validate further HdZone class specific parameters.
        hd_names = config[self.CS_HD_ZONE].get(self.CV_HD_ZONE_HD_NAMES)
        if not hd_names:
            raise ValueError('Parameter hd_names= is not specified.')
        if "\n" in hd_names:
            self.hd_device_names = hd_names.splitlines()
        else:
            self.hd_device_names = hd_names.split()
        if len(self.hd_device_names) != count:
            raise ValueError(f'Inconsistent count ({count}) and size of hd_names ({len(self.hd_device_names)})')
        # Read the path of the 'hddtemp' command.
        self.hddtemp_path = config[self.CS_HD_ZONE].get(self.CV_HD_ZONE_HDDTEMP_PATH, '/usr/sbin/hddtemp')
        # Initialize FanController class.
        super().__init__(
            log, ipmi, Ipmi.HD_ZONE, self.CS_HD_ZONE, count,
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_STEPS, fallback=4),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_SENSITIVITY, fallback=2),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_POLLING, fallback=10),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_MIN_TEMP, fallback=32),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_MAX_TEMP, fallback=46),
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_MIN_LEVEL, fallback=35),
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_MAX_LEVEL, fallback=100),
            config[self.CS_HD_ZONE].get(self.CV_HD_ZONE_HWMON_PATH),
            {self.STR_HDD_TEMP}
        )
        # Read and validate the configuration of standby guard if enabled.
        self.standby_guard_enabled = config[self.CS_HD_ZONE].getboolean(self.CV_HD_ZONE_STANDBY_GUARD_ENABLED,
                                                                        fallback=False)
        if self.count == 1:
            self.log.msg(self.log.LOG_INFO, '   WARNING: Standby guard is disabled ([HD zone] count=1')
            self.standby_guard_enabled = False
        if self.standby_guard_enabled:
            self.standby_array_states = [False] * count
            # Read and validate further parameters.
            self.standby_hd_limit = config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_STANDBY_HD_LIMIT, fallback=1)
            if self.standby_hd_limit < 0:
                raise ValueError('standby_hd_limit < 0')
            if self.standby_hd_limit > self.count:
                raise ValueError('standby_hd_limit > count')
            self.smartctl_path = config[self.CS_HD_ZONE].get(self.CV_HD_ZONE_SMARTCTL_PATH, '/usr/sbin/smartctl')
            # Get the current power state of the HD array.
            n = self.check_standby_state()
            # Set calculated parameters.
            self.standby_change_timestamp = time.monotonic()
            self.standby_flag = n == self.count

        # Print configuration in DEBUG log level (or higher).
        if self.log.log_level >= self.log.LOG_CONFIG:
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_HD_ZONE_HD_NAMES} = {self.hd_device_names}')
            if self.standby_guard_enabled:
                self.log.msg(self.log.LOG_CONFIG, '   Standby guard is enabled:')
                self.log.msg(self.log.LOG_CONFIG, f'     {self.CV_HD_ZONE_STANDBY_HD_LIMIT} = {self.standby_hd_limit}')
                self.log.msg(self.log.LOG_CONFIG, f'     {self.CV_HD_ZONE_SMARTCTL_PATH} = {self.smartctl_path}')
            else:
                self.log.msg(self.log.LOG_CONFIG, '   Standby guard is disabled')
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_HD_ZONE_HDDTEMP_PATH} = {self.hddtemp_path}')

    def build_hwmon_path(self, hwmon_str: str) -> None:
        """Build hwmon_path[] list for the HD zone."""
        disk_name: str          # Disk name
        search_str: str         # Search string
        file_names: List[str]   # Result list for glob.glob()

        # If the user specified hwmon_path= configuration parameter.
        if hwmon_str:
            # Convert the string into a string array (respecting multi-line strings).
            super().build_hwmon_path(hwmon_str)

        # If hwmon_path string has not been specified by the user then it will be constructed.
        else:

            # Iterate through each disk.
            for i in range(self.count):

                # If the current one is an NVME SSD disk.
                # NOTE: kernel provides this, no extra modules required
                if "nvme-" in self.hd_device_names[i]:
                    disk_name = os.path.basename(os.readlink(self.hd_device_names[i]))
                    search_str = os.path.join('/sys/class/nvme', disk_name, disk_name + "n1", 'hwmon*/temp1_input')
                    file_names = glob.glob(search_str)
                    if not file_names:
                        raise ValueError(self.ERROR_MSG_FILE_IO.format(search_str))
                    self.hwmon_path.append(file_names[0])

                # If the current one is a SATA disk.
                # NOTE: 'drivetemp' kernel module must be loaded otherwise this path does not exist!
                elif "ata-" in self.hd_device_names[i] or "-SATA" in self.hd_device_names[i]:
                    disk_name = os.path.basename(os.readlink(self.hd_device_names[i]))
                    search_str = os.path.join('/sys/class/scsi_disk/*', 'device/block', disk_name)
                    file_names = glob.glob(search_str)
                    if not file_names:
                        raise ValueError(self.ERROR_MSG_FILE_IO.format(search_str))
                    file_names[0] = file_names[0].replace("/device/block/" + disk_name, "")
                    search_str = os.path.join(file_names[0], 'device/hwmon/hwmon*/temp1_input')
                    file_names = glob.glob(search_str)
                    if not file_names:
                        raise ValueError(self.ERROR_MSG_FILE_IO.format(search_str))
                    self.hwmon_path.append(file_names[0])

                # Otherwise we assume it is a SAS/SCSI disk.
                # 'hddtemp' command will be used to read HD temperature.
                else:
                    self.hwmon_path.append(self.STR_HDD_TEMP)

            # Check the size of hwmon_path array
            if len(self.hwmon_path) != self.count:
                raise ValueError(f'Invalid hd_names= parameter(s), not all hwmon files was found ({self.hwmon_path})')

    def callback_func(self) -> None:
        """Call-back function execute standby guard."""
        if self.standby_guard_enabled:
            self.run_standby_guard()

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the nth element in the hwmon list. This is a specific implementation for HD zone.

        Args:
            index (int): index in hwmon list

        Returns:
            float: temperature value

        Raises:
            FileNotFoundError:  file or command cannot be found
            IOError:            file cannot be opened
            ValueError:         invalid temperature value
            IndexError:         invalid index
        """
        r: subprocess.CompletedProcess  # result of the executed process
        value: float                    # Float value to calculate the temperature.

        # Use 'hddtemp' command for reading HD temperature.
        if self.hwmon_path[index] == self.STR_HDD_TEMP:

            # Read disk temperature with calling 'hddtemp' command.
            try:
                r = subprocess.run([self.hddtemp_path, '-q', '-n', self.hd_device_names[index]],
                                   check=False, capture_output=True, text=True)
                if r.returncode != 0:
                    raise RuntimeError(r.stderr)
                value = float(r.stdout)
            except (FileNotFoundError, ValueError, IndexError) as e:
                raise e

        # Read temperature from HWMON file in sysfs.
        else:
            try:
                with open(self.hwmon_path[index], "r", encoding="UTF-8") as f:
                    value = float(f.read()) / 1000
            except (IOError, FileNotFoundError, ValueError, IndexError) as e:
                raise e

        return value

    def get_standby_state_str(self) -> str:
        """Get a string representing the power state of the HD array with a character.

        Returns:
            str:   standby state string where all HD represented with a character (A-ACTIVE, S-STANDBY)
        """
        result: str = ''    # Result string

        for i in range(self.count):
            if self.standby_array_states[i]:
                result += 'S'
            else:
                result += 'A'
        return result

    def check_standby_state(self):
        """Check the actual power state of the HDs in the array and store them in 'standby_states'.

        Returns:
            int:   number of HDs in STANDBY mode
        """
        r: subprocess.CompletedProcess      # Result of the executed process.

        # Check the current power state of the HDs
        for i in range(self.count):
            self.standby_array_states[i] = False
            r = subprocess.run([self.smartctl_path, '-i', '-n', 'standby', self.hd_device_names[i]],
                               check=False, capture_output=True, text=True)
            if r.returncode not in {0, 2}:
                raise ValueError(self.ERROR_MSG_SMARTCTL.format(r.returncode))
            if str(r.stdout).find("STANDBY") != -1:
                self.standby_array_states[i] = True
        return self.standby_array_states.count(True)

    def go_standby_state(self):
        """Put active HDs to STANDBY state in the array (based on the actual state of 'standby_states').
        """
        r: subprocess.CompletedProcess      # Result of the executed process.

        # Iterate through HDs list
        for i in range(self.count):
            # if the HD is ACTIVE
            if not self.standby_array_states[i]:
                # then move it to STANDBY state
                r = subprocess.run([self.smartctl_path, '-s', 'standby,now', self.hd_device_names[i]],
                                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if r.returncode != 0:
                    raise ValueError(self.ERROR_MSG_SMARTCTL.format(r.returncode))
                self.standby_array_states[i] = True

    def run_standby_guard(self):
        """Monitor changes in the power state of an HD array and help them to move to STANDBY state together.
        This feature is implemented in the following way:
            * step 1: Checks the power state of all HDs in array
            * step 2: Check if the array is going to STANDBY (i.e. was ACTIVE before and reached the limit with number
                      of HDs in STANDBY state), put the remaining active members to STANDBY state and log the event
            * step 3: Check if the array is waking up (i.e. was in STANDBY state before and there is any ACTIVE
                      HD(s) in the array) and log the event
        """
        hds_in_standby: int     # HDs in standby mode
        minutes: float          # Elapsed time in minutes
        cur_time: float         # New timestamp for STANDBY change

        # Step 1: check the current power state of the HD array
        hds_in_standby = self.check_standby_state()
        cur_time = time.monotonic()

        # Step 2: check if the array is going to STANDBY state.
        if not self.standby_flag and hds_in_standby >= self.standby_hd_limit:
            minutes = (cur_time - self.standby_change_timestamp) / float(3600)
            self.log.msg(self.log.LOG_INFO, f'Standby guard: Change ACTIVE to STANDBY after {minutes:.1f} hour(s)'
                         f'[{self.get_standby_state_str()}]')
            self.go_standby_state()
            self.standby_flag = True
            self.standby_change_timestamp = cur_time

        # Step 3: check if the array is waking up.
        elif self.standby_flag and hds_in_standby < self.count:
            minutes = (cur_time - self.standby_change_timestamp) / float(3600)
            self.log.msg(self.log.LOG_INFO, f'Standby guard: Change STANDBY to ACTIVE after {minutes:.1f} hour(s)'
                         f'[{self.get_standby_state_str()}]')
            self.standby_flag = False
            self.standby_change_timestamp = cur_time

