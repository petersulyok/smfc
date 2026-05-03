#
#   hdfc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.HdFc() class implementation.
#
import subprocess
import time
from configparser import ConfigParser
from typing import List
from pyudev import Context, Devices, DeviceNotFoundByFileError
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class HdFc(FanController):
    """Class for HD fan controller."""

    # HdFc specific parameters.
    hd_device_names: List[str]          # Device names of the hard disks (e.g. '/dev/disk/by-id/...').

    # Standby guard specific parameters.
    standby_guard_enabled: bool         # Standby guard feature enabled
    standby_hd_limit: int               # Number of HDs in STANDBY state before the full RAID array will go STANDBY
    smartctl_path: str                  # Path for 'smartctl' command
    standby_flag: bool                  # The actual state of the whole HD array
    standby_change_timestamp: float     # Timestamp of the latest change in STANDBY mode
    standby_array_states: List[bool]    # Standby states of HDs
    sudo: bool                          # Use `sudo` command

    # Constant values for the configuration parameters.
    CS_HD_FC: str = "HD"
    CV_HD_FC_ENABLED: str = "enabled"
    CV_HD_FC_IPMI_ZONE: str = "ipmi_zone"
    CV_HD_FC_TEMP_CALC: str = "temp_calc"
    CV_HD_FC_STEPS: str = "steps"
    CV_HD_FC_SENSITIVITY: str = "sensitivity"
    CV_HD_FC_POLLING: str = "polling"
    CV_HD_FC_MIN_TEMP: str = "min_temp"
    CV_HD_FC_MAX_TEMP: str = "max_temp"
    CV_HD_FC_MIN_LEVEL: str = "min_level"
    CV_HD_FC_MAX_LEVEL: str = "max_level"
    CV_HD_FC_SMOOTHING: str = "smoothing"
    CV_HD_FC_HD_NAMES: str = "hd_names"
    CV_HD_FC_SMARTCTL_PATH: str = "smartctl_path"
    CV_HD_FC_STANDBY_GUARD_ENABLED: str = "standby_guard_enabled"
    CV_HD_FC_STANDBY_HD_LIMIT: str = "standby_hd_limit"

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser, sudo: bool,
                 section: str = CS_HD_FC) -> None:
        """Initialize the HD fan controller class and raise exception in case of invalid configuration.

        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            config (ConfigParser): reference to the configuration
            sudo (bool): sudo flag
            section (str): configuration section name (default: CS_HD_FC)

        Raises:
            ValueError: invalid configuration parameters (e.g. missing hd_names, NVMe drives specified)
        """
        hd_names: str   # String for hd_names=
        count: int      # HDD count.

        # Save and validate HdFc class-specific parameters.
        hd_names = config[section].get(self.CV_HD_FC_HD_NAMES)
        if not hd_names:
            raise ValueError("Parameter hd_names= is not specified.")
        if "\n" in hd_names:
            self.hd_device_names = hd_names.splitlines()
        else:
            self.hd_device_names = hd_names.split()
        # Validate that no NVMe drives are specified (they belong to NVME fan controller).
        for name in self.hd_device_names:
            if "nvme" in name.lower():
                raise ValueError(f"NVMe drives are not allowed in [HD], use [NVME] instead: '{name}'")
        # Set count.
        count = len(self.hd_device_names)
        # Save sudo flag.
        self.sudo = sudo

        # Iterate through each disk.
        self.hwmon_path = []
        for i in range(count):
            # Find a device in udev database based on disk name.
            try:
                block_dev = Devices.from_device_file(udevc, self.hd_device_names[i])
            except DeviceNotFoundByFileError:
                raise ValueError(f"hd_names= parameter error: '{self.hd_device_names[i]}' cannot be reached.") \
                    from DeviceNotFoundByFileError
            # Add the hwmon path string for NVME/SATA/HDD disks or '' for SAS/SCSI disks.
            self.hwmon_path.append(self.get_hwmon_path(udevc, block_dev.parent))

        # Save path for `smartctl` command.
        self.smartctl_path = config[section].get(HdFc.CV_HD_FC_SMARTCTL_PATH, "/usr/sbin/smartctl")

        # Initialize FanController class.
        super().__init__(
            log, ipmi,
            config[section].get(HdFc.CV_HD_FC_IPMI_ZONE, fallback=f"{Ipmi.HD_ZONE}"),
            section, count,
            config[section].getint(HdFc.CV_HD_FC_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[section].getint(HdFc.CV_HD_FC_STEPS, fallback=4),
            config[section].getfloat(HdFc.CV_HD_FC_SENSITIVITY, fallback=2),
            config[section].getfloat(HdFc.CV_HD_FC_POLLING, fallback=10),
            config[section].getfloat(HdFc.CV_HD_FC_MIN_TEMP, fallback=32),
            config[section].getfloat(HdFc.CV_HD_FC_MAX_TEMP, fallback=46),
            config[section].getint(HdFc.CV_HD_FC_MIN_LEVEL, fallback=35),
            config[section].getint(HdFc.CV_HD_FC_MAX_LEVEL, fallback=100),
            config[section].getint(HdFc.CV_HD_FC_SMOOTHING, fallback=1),
        )

        # Read and validate the configuration of standby guard if enabled.
        self.standby_guard_enabled = config[section].getboolean(HdFc.CV_HD_FC_STANDBY_GUARD_ENABLED,
                                                                fallback=False)
        if self.count == 1:
            self.log.msg(Log.LOG_INFO, "   WARNING: Standby guard is disabled ([HD] count=1")
            self.standby_guard_enabled = False
        if self.standby_guard_enabled:
            self.standby_array_states = [False] * self.count
            # Read and validate further parameters.
            self.standby_hd_limit = config[section].getint(HdFc.CV_HD_FC_STANDBY_HD_LIMIT, fallback=1)
            if self.standby_hd_limit < 0:
                raise ValueError("standby_hd_limit < 0")
            if self.standby_hd_limit > self.count:
                raise ValueError("standby_hd_limit > count")
            # Get the current power state of the HD array.
            n = self.check_standby_state()
            # Set calculated parameters.
            self.standby_change_timestamp = time.monotonic()
            self.standby_flag = n == self.count

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   {self.CV_HD_FC_HD_NAMES} = {self.hd_device_names}")
            self.log.msg(Log.LOG_CONFIG, f"   {self.CV_HD_FC_SMARTCTL_PATH} = {self.smartctl_path}")
            if self.standby_guard_enabled:
                self.log.msg(Log.LOG_CONFIG, "   Standby guard is enabled:")
                self.log.msg(Log.LOG_CONFIG, f"     {self.CV_HD_FC_STANDBY_HD_LIMIT} = {self.standby_hd_limit}")
            else:
                self.log.msg(Log.LOG_CONFIG, "   Standby guard is disabled")

    def callback_func(self) -> None:
        """Call-back function to execute standby guard."""
        if self.standby_guard_enabled:
            self.run_standby_guard()

    def _exec_smartctl(self, arguments: List[str]) -> subprocess.CompletedProcess:
        """Execute the `smartctl` command.
        Args:
            arguments (List[str]): list of arguments of `smartctl` command
        Returns:
            subprocess.CompletedProcess: result of the executed subprocess
        Raises:
            FileNotFoundError: command not found
            RuntimeError: sudo error
        """
        r: subprocess.CompletedProcess
        args: List[str]

        # Execute `smartctl` command.
        # Build argument list.
        args = []
        if self.sudo:
            args.append("sudo")
        args.append(self.smartctl_path)
        args.extend(arguments)
        # May raise FileNotFoundError if smartctl is not found.
        r = subprocess.run(args, check=False, capture_output=True, text=True)
        # In case if sudo return code report execution problem (for smartctl it could be any SMART error)
        if r.returncode != 0 and self.sudo and "sudo" in r.stderr:
            raise RuntimeError(f"sudo error ({r.returncode}): {r.stderr}!")
        return r

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the nth element in the hwmon list. This is a specific implementation for HD
        fan controller.
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
        value: float = 100  # Read temperature value.

        # Use 'smartctl' command for reading HD temperature in case of empty HWMON path.
        if not self.hwmon_path[index]:
            if hasattr(self, "log") and self.log.log_level >= Log.LOG_DEBUG:
                self.log.msg(Log.LOG_DEBUG, f"HD: using smartctl for {self.hd_device_names[index]}")
            r: subprocess.CompletedProcess  # result of the executed process
            output_lines: List[str]  # Lines of the output text.
            line: str  # One line.
            found: bool  # Temperature value was found.

            # Read disk temperature with calling `smartctl -a /dev/...` command.
            try:
                r = self._exec_smartctl(["-a", self.hd_device_names[index]])
                # Parse the output of `smartctl` command.
                output_lines = str(r.stdout).splitlines()
                found = False
                for line in output_lines:
                    # SCSI type of temperature reporting, like:
                    # `Current Drive Temperature:     37 C`
                    if "Current Drive Temperature" in line:
                        value = float(line.split(":")[-1].strip().split()[0])
                        found = True
                        break

                    # pylint: disable=C0301
                    # ATA/SATA type of temperature reporting, like:
                    # `190 Airflow_Temperature_Cel 0x0032   075   045   000    Old_age   Always       -       25`
                    # `194 Temperature_Celsius     0x0002   232   232   000    Old_age   Always       -       28 (Min/Max 17/45)`
                    # Fix issue #76: Number of words in the line is also checked to avoid such a case for SCSI disks:
                    # `Temperature Warning:  Enabled`
                    # pylint: enable=C0301
                    s = line.split()
                    if "Temperature" in line and len(s) >= 9:
                        value = float(s[9])
                        found = True
                        break

                # If we did not find any matching temperature pattern.
                if not found:
                    raise ValueError(
                        f"ERROR: Temperature cannot found in smartctl output "
                        f"(disk={self.hd_device_names[index]})!"
                    )

            except (FileNotFoundError, RuntimeError, ValueError, IndexError) as e:
                raise type(e)(
                    f"ERROR: Cannot read temperature from smartctl "
                    f"(disk={self.hd_device_names[index]})!"
                ) from e

        # Read temperature from a HWMON file.
        else:
            try:
                with open(self.hwmon_path[index], "r", encoding="UTF-8") as f:
                    value = float(f.read()) / 1000
            except (IOError, FileNotFoundError, ValueError, IndexError) as e:
                raise type(e)(f"ERROR: Cannot read temperature from HWMON file "
                              f"(disk={self.hd_device_names[index]})!") from e

        return value

    def get_standby_state_str(self) -> str:
        """Get a string representing the power state of the HD array with a character.
        Returns:
            str:   standby state string where all HD represented with a character (A-ACTIVE, S-STANDBY)
        """
        result: str = ""  # Result string

        for i in range(self.count):
            if self.standby_array_states[i]:
                result += "S"
            else:
                result += "A"
        return result

    def check_standby_state(self) -> int:
        """Check the actual power state of the HDs in the array and store them in 'standby_states'.

        Returns:
            int:   number of HDs in STANDBY mode
        """
        r: subprocess.CompletedProcess  # Result of the executed process.

        # Check the current power state of the HDs
        for i in range(self.count):
            self.standby_array_states[i] = False
            r = self._exec_smartctl(["-i", "-n", "standby", self.hd_device_names[i]])
            if str(r.stdout).find("STANDBY") != -1:
                self.standby_array_states[i] = True
        self.log.msg(Log.LOG_DEBUG, f"Standby guard: current state is {self.get_standby_state_str()}.")
        return self.standby_array_states.count(True)

    def go_standby_state(self):
        """Put active HDs to STANDBY state in the array (based on the actual state of 'standby_states')."""
        # Iterate through HDs list
        for i in range(self.count):
            # if the HD is ACTIVE
            if not self.standby_array_states[i]:
                # then move it to STANDBY state
                self._exec_smartctl(["-s", "standby,now", self.hd_device_names[i]])
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
        hds_in_standby: int  # HDDs in standby mode
        hours: float  # Elapsed time in minutes
        cur_time: float  # New timestamp for STANDBY change

        # Step 1: check the current power state of the HD array
        hds_in_standby = self.check_standby_state()
        cur_time = time.monotonic()

        # Step 2: check if the array is going to STANDBY state.
        if self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f"Standby guard: standby_flag={self.standby_flag} "
                         f"hds_in_standby={hds_in_standby}/{self.count}")
        if not self.standby_flag and hds_in_standby >= self.standby_hd_limit:
            hours = (cur_time - self.standby_change_timestamp) / float(3600)
            self.log.msg(Log.LOG_INFO, f"Standby guard: Status change ACTIVE > STANDBY (after {hours:.1f} hours, "
                         f"{self.get_standby_state_str()})")
            self.go_standby_state()
            self.standby_flag = True
            self.standby_change_timestamp = cur_time

        # Step 3: check if the array is waking up.
        elif self.standby_flag and hds_in_standby < self.count:
            hours = (cur_time - self.standby_change_timestamp) / float(3600)
            self.log.msg(Log.LOG_INFO, f"Standby guard: Status change STANDBY > ACTIVE (after {hours:.1f} hours, "
                         f"{self.get_standby_state_str()})")
            self.standby_flag = False
            self.standby_change_timestamp = cur_time


# End.
