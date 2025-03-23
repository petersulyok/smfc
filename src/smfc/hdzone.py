#
#   hdzone.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.HdZone() class implementation.
#
import configparser
import subprocess
import time
from typing import List
from pyudev import Context, Devices, DeviceNotFoundByFileError
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class HdZone(FanController):
    """Class for HD zone fan control."""

    # HdZone specific parameters.
    hd_device_names: List[str]          # Device names of the hard disks (e.g. '/dev/disk/by-id/...').

    # Standby guard specific parameters.
    standby_guard_enabled: bool         # Standby guard feature enabled
    standby_hd_limit: int               # Number of HDs in STANDBY state before the full RAID array will go STANDBY
    smartctl_path: str                  # Path for 'smartctl' command
    standby_flag: bool                  # The actual state of the whole HD array
    standby_change_timestamp: float     # Timestamp of the latest change in STANDBY mode
    standby_array_states: List[bool]    # Standby states of HDs

    # Error message.
    ERROR_MSG_SMARTCTL: str = 'smartctl error ({err_no}): {err_msg}.'

    # Constant values for the configuration parameters.
    CS_HD_ZONE: str = 'HD zone'
    CV_HD_ZONE_ENABLED: str = 'enabled'
    CV_HD_ZONE_TEMP_CALC: str = 'temp_calc'
    CV_HD_ZONE_STEPS: str = 'steps'
    CV_HD_ZONE_SENSITIVITY: str = 'sensitivity'
    CV_HD_ZONE_POLLING: str = 'polling'
    CV_HD_ZONE_MIN_TEMP: str = 'min_temp'
    CV_HD_ZONE_MAX_TEMP: str = 'max_temp'
    CV_HD_ZONE_MIN_LEVEL: str = 'min_level'
    CV_HD_ZONE_MAX_LEVEL: str = 'max_level'
    CV_HD_ZONE_HD_NAMES: str = 'hd_names'
    CV_HD_ZONE_STANDBY_GUARD_ENABLED: str = 'standby_guard_enabled'
    CV_HD_ZONE_STANDBY_HD_LIMIT: str = 'standby_hd_limit'
    CV_HD_ZONE_SMARTCTL_PATH: str = 'smartctl_path'

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, config: configparser.ConfigParser) -> None:
        """Initialize the HdZone class. Abort in case of configuration errors.

        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            config (configparser.ConfigParser): reference to the configuration (default=None)

        Raises:
            ValueError: Parameter `hd_names=` is not specified in the configuration
        """
        hd_names: str   # String for hd_names=

        # Save and validate HdZone class specific parameters.
        hd_names = config[self.CS_HD_ZONE].get(self.CV_HD_ZONE_HD_NAMES)
        if not hd_names:
            raise ValueError('Parameter hd_names= is not specified.')
        if "\n" in hd_names:
            self.hd_device_names = hd_names.splitlines()
        else:
            self.hd_device_names = hd_names.split()
        # Set count.
        self.count = len(self.hd_device_names)

        # Iterate through each disk.
        self.udevc = udevc
        self.hwmon_path=[]
        for i in range(self.count):
            # Find udev device based on device name.
            try:
                block_dev = Devices.from_device_file(self.udevc, self.hd_device_names[i])
            except DeviceNotFoundByFileError:
                raise ValueError(f'ERROR: {self.hd_device_names[i]} cannot be accessed.') \
                    from DeviceNotFoundByFileError
            # Add the hwmon path string for NVME/SATA/HDD disks or '' for SAS/SCSI disks.
            self.hwmon_path.append(self.get_hwmon_path(block_dev.parent))

        # Save path for `smartctl` command.
        self.smartctl_path = config[self.CS_HD_ZONE].get(self.CV_HD_ZONE_SMARTCTL_PATH, '/usr/sbin/smartctl')

        # Initialize FanController class.
        super().__init__(
            log, ipmi, Ipmi.HD_ZONE, self.CS_HD_ZONE,
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_STEPS, fallback=4),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_SENSITIVITY, fallback=2),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_POLLING, fallback=10),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_MIN_TEMP, fallback=32),
            config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_MAX_TEMP, fallback=46),
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_MIN_LEVEL, fallback=35),
            config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_MAX_LEVEL, fallback=100)
        )

        # Read and validate the configuration of standby guard if enabled.
        self.standby_guard_enabled = config[self.CS_HD_ZONE].getboolean(self.CV_HD_ZONE_STANDBY_GUARD_ENABLED,
                                                                        fallback=False)
        if self.count == 1:
            self.log.msg(self.log.LOG_INFO, '   WARNING: Standby guard is disabled ([HD zone] count=1')
            self.standby_guard_enabled = False
        if self.standby_guard_enabled:
            self.standby_array_states = [False] * self.count
            # Read and validate further parameters.
            self.standby_hd_limit = config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_STANDBY_HD_LIMIT, fallback=1)
            if self.standby_hd_limit < 0:
                raise ValueError('standby_hd_limit < 0')
            if self.standby_hd_limit > self.count:
                raise ValueError('standby_hd_limit > count')
            # Get the current power state of the HD array.
            n = self.check_standby_state()
            # Set calculated parameters.
            self.standby_change_timestamp = time.monotonic()
            self.standby_flag = n == self.count

        # Print configuration in DEBUG log level (or higher).
        if self.log.log_level >= self.log.LOG_CONFIG:
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_HD_ZONE_HD_NAMES} = {self.hd_device_names}')
            self.log.msg(self.log.LOG_CONFIG, f'   {self.CV_HD_ZONE_SMARTCTL_PATH} = {self.smartctl_path}')
            if self.standby_guard_enabled:
                self.log.msg(self.log.LOG_CONFIG, '   Standby guard is enabled:')
                self.log.msg(self.log.LOG_CONFIG, f'     {self.CV_HD_ZONE_STANDBY_HD_LIMIT} = {self.standby_hd_limit}')
            else:
                self.log.msg(self.log.LOG_CONFIG, '   Standby guard is disabled')

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
        value: float = -1.0     # Float value to calculate the temperature.

        # Use 'smartctl' command for reading HD temperature in case of empty HWMON path.
        if not self.hwmon_path[index]:
            r: subprocess.CompletedProcess  # result of the executed process
            lines: List[str]  # Output lines.
            found: bool  # Temperature value was found.

            # Read disk temperature with calling `smartctl -a /dev/...` command.
            try:
                r = subprocess.run([self.smartctl_path, '-a', self.hd_device_names[index]],
                                   check=False, capture_output=True, text=True)
                if r.returncode not in {0, 2}:
                    raise RuntimeError(self.ERROR_MSG_SMARTCTL.format(err_no=r.returncode, err_msg=r.stderr))

                # Parse the output of smartctl.
                lines = str(r.stdout).splitlines()
                found = False
                for l in lines:

                    # SCSI type of temperature reporting:
                    # `Current Drive Temperature:     37 C`
                    if 'Current Drive Temperature' in l:
                        value = float(l.split(':')[-1].strip().split()[0])
                        found = True
                        break

                    # ATA/SATA type of temperature reporting:
                    # `190 Airflow_Temperature_Cel 0x0032   075   045   000    Old_age   Always       -       25`
                    # `194 Temperature_Celsius     0x0002   232   232   000    Old_age   Always       -       28 (Min/Max 17/45)`
                    if 'Temperature' in l:
                        s = l.split()
                        value = float(s[9])
                        found = True
                        break

                # If we did not find any matching temperature pattern.
                if not found:
                    raise ValueError(f'smartctl output: Temperature value cannot be found!')

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
                raise ValueError(self.ERROR_MSG_SMARTCTL.format(err_no=r.returncode, err_msg=r.stderr))
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
                if r.returncode not in {0, 2}:
                    raise ValueError(self.ERROR_MSG_SMARTCTL.format(err_no=r.returncode, err_msg=r.stderr))
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
            self.log.msg(self.log.LOG_INFO,
                        f'Standby guard: Status change ACTIVE > STANDBY (after {minutes:.1f} hours, '
                         f'{self.get_standby_state_str()})')
            self.go_standby_state()
            self.standby_flag = True
            self.standby_change_timestamp = cur_time

        # Step 3: check if the array is waking up.
        elif self.standby_flag and hds_in_standby < self.count:
            minutes = (cur_time - self.standby_change_timestamp) / float(3600)
            self.log.msg(self.log.LOG_INFO,
                        f'Standby guard: Status change STANDBY > ACTIVE (after {minutes:.1f} hours, '
                         f'{self.get_standby_state_str()})')
            self.standby_flag = False
            self.standby_change_timestamp = cur_time

# End.
