#
#   hdfc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.HdFc() class implementation.
#
import subprocess
import time
from typing import List
from pyudev import Context, Devices, DeviceNotFoundByFileError
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import HdConfig


class HdFc(FanController):
    """Class for HD fan controller."""

    config: HdConfig

    # HdFc specific parameters.
    hd_device_names: List[str]          # Device names of the hard disks (e.g. '/dev/disk/by-id/...').

    # Standby guard specific parameters.
    standby_flag: bool                  # The actual state of the whole HD array
    standby_change_timestamp: float     # Timestamp of the latest change in STANDBY mode
    standby_array_states: List[bool]    # Standby states of HDs
    sudo: bool                          # Use `sudo` command

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: HdConfig, sudo: bool) -> None:
        """Initialize the HD fan controller class and raise exception in case of invalid configuration.

        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            cfg (HdConfig): HD fan controller configuration
            sudo (bool): sudo flag

        Raises:
            ValueError: invalid configuration parameters (e.g. device not reachable)
        """
        # Store config reference first (required by base class)
        self.config = cfg

        # Save HdFc class-specific parameters (validation done in Config).
        self.hd_device_names = cfg.hd_names
        # Save sudo flag.
        self.sudo = sudo

        # Iterate through each disk.
        self.hwmon_path = []
        for i in range(len(self.hd_device_names)):
            # Find a device in udev database based on disk name.
            try:
                block_dev = Devices.from_device_file(udevc, self.hd_device_names[i])
            except DeviceNotFoundByFileError:
                raise ValueError(f"hd_names= parameter error: '{self.hd_device_names[i]}' cannot be reached.") \
                    from DeviceNotFoundByFileError
            # Add the hwmon path string for NVME/SATA/HDD disks or '' for SAS/SCSI disks.
            self.hwmon_path.append(self.get_hwmon_path(udevc, block_dev.parent))

        # Initialize FanController class.
        super().__init__(log, ipmi, cfg.section, len(self.hd_device_names))

        # Read and validate the configuration of standby guard if enabled.
        if self.count == 1:
            self.log.msg(Log.LOG_INFO, "   WARNING: Standby guard is disabled ([HD] count=1")
        if cfg.standby_guard_enabled and self.count > 1:
            self.standby_array_states = [False] * self.count
            # Validate standby_hd_limit against count.
            if cfg.standby_hd_limit > self.count:
                raise ValueError("standby_hd_limit > count")
            # Get the current power state of the HD array.
            n = self.check_standby_state()
            # Set calculated parameters.
            self.standby_change_timestamp = time.monotonic()
            self.standby_flag = n == self.count

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   hd_names = {self.hd_device_names}")
            self.log.msg(Log.LOG_CONFIG, f"   smartctl_path = {self.config.smartctl_path}")
            if self.config.standby_guard_enabled and self.count > 1:
                self.log.msg(Log.LOG_CONFIG, "   Standby guard is enabled:")
                self.log.msg(Log.LOG_CONFIG, f"     standby_hd_limit = {self.config.standby_hd_limit}")
            else:
                self.log.msg(Log.LOG_CONFIG, "   Standby guard is disabled")

    def callback_func(self) -> None:
        """Call-back function to execute standby guard."""
        if self.config.standby_guard_enabled and self.count > 1:
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
        args.append(self.config.smartctl_path)
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
        if not self.standby_flag and hds_in_standby >= self.config.standby_hd_limit:
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
