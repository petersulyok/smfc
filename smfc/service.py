#
#   service.py (C) 2020-2024, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.Service() class implementation.
#
import argparse
import atexit
import configparser
import os
import sys
import time
from typing import List

from .cpuzone import CpuZone
from .hdzone import HdZone
from .ipmi import Ipmi
from .log import Log


# Program version string
version_str: str = '3.5.1'


class Service:
    """Service class contains all resources/functions for the execution."""

    config: configparser.ConfigParser   # Instance for a parsed configuration
    log: Log                            # Instance for a Log class
    ipmi: Ipmi                          # Instance for an Ipmi class
    cpu_zone: CpuZone                   # Instance for a CPU Zone fan controller class
    hd_zone: HdZone                     # Instance for an HD Zone fan controller class
    cpu_zone_enabled: bool              # CPU zone fan controller enabled
    hd_zone_enabled: bool               # HD zone fan controller enabled

    def exit_func(self) -> None:
        """This function is called at exit (in case of exceptions or runtime errors cannot be handled), and it switches
           all fans back to rhw default speed 100%, in order to avoid system overheating while `smfc` is not running."""
        # Configure fans.
        if hasattr(self, "ipmi"):
            self.ipmi.set_fan_level(Ipmi.CPU_ZONE, 100)
            self.ipmi.set_fan_level(Ipmi.HD_ZONE, 100)
            if hasattr(self, "log"):
                self.log.msg(Log.LOG_INFO, 'smfc terminated: all fans are switched back to the 100% speed.')

        # Unregister this function.
        atexit.unregister(self.exit_func)

    def check_dependencies(self) -> str:
        """Check run-time dependencies of smfc:

              - ipmitool command
              - if CPU zone enabled: coretemp or k10temp kernel module
              - if HD zone enabled: drivetemp kernel module or hddtemp command

        Returns:
            (str): error string:

                - empty: dependencies are OK
                - otherwise: the error message

        """
        path: str

        # Check if ipmitool command is available.
        path = self.config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_COMMAND, '/usr/bin/ipmitool')
        if not os.path.exists(path):
            return f"ERROR: ipmitool command cannot be found {path}!"

        # Load list of kernel modules.
        with open("/proc/modules", "rt", encoding="utf-8") as file:
            modules = file.read()

        # Check kernel modules for CPUs
        if self.cpu_zone_enabled:
            if "coretemp" not in modules and "k10temp" not in modules:
                return "ERROR: coretemp or k10temp kernel module is not loaded!"

        # Check dependencies for disks
        if self.hd_zone_enabled:
            check_hddtemp: bool = False
            check_drivetemp: bool = False
            hwmon_path: List[str] = []

            # Scan HWMON configuration for dependencies.
            hwmon_str = self.config[HdZone.CS_HD_ZONE].get(HdZone.CV_HD_ZONE_HWMON_PATH)
            if hwmon_str:
                if "\n" in hwmon_str:
                    hwmon_path = hwmon_str.splitlines()
                else:
                    hwmon_path = hwmon_str.split()
            if hwmon_path:
                for path in hwmon_path:
                    if path == HdZone.STR_HDD_TEMP:
                        check_hddtemp = True
                    else:
                        check_drivetemp = True
            else:
                check_drivetemp = True

            # Check if drivetemp kernel module is loaded
            if check_drivetemp:
                if "drivetemp" not in modules:
                    return "ERROR: drivetemp kernel module is not loaded!"

            # Check if hddtemp command is available
            if check_hddtemp:
                path = self.config[HdZone.CS_HD_ZONE].get(HdZone.CV_HD_ZONE_HDDTEMP_PATH, '/usr/sbin/hddtemp')
                if not os.path.exists(path):
                    return f"ERROR: hddtemp command cannot be found {path}!"

            # Optional: check if smartctl command is available.
            if self.config[HdZone.CS_HD_ZONE].getboolean(HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED, False):
                path = self.config[HdZone.CS_HD_ZONE].get(HdZone.CV_HD_ZONE_SMARTCTL_PATH, '/usr/sbin/hddtemp')
                if not os.path.exists(path):
                    return f"ERROR: smartctl command cannot be found {path}!"

        # All required run-time dependencies seems to be available.
        return ""

    def run(self) -> None:
        """Run function: main execution function of the systemd service."""
        app_parser: argparse.ArgumentParser     # Instance for an ArgumentParser class
        parsed_results: argparse.Namespace      # Results of parsed command line arguments
        old_mode: int                           # Old IPMI fan mode

        # Register the emergency exit function for service termination.
        atexit.register(self.exit_func)

        # Parse the command line arguments.
        app_parser = argparse.ArgumentParser()
        app_parser.add_argument('-c', action='store', dest='config_file', default='smfc.conf',
                                help='configuration file')
        app_parser.add_argument('-v', action='version', version='%(prog)s ' + version_str)
        app_parser.add_argument('-l', type=int, choices=[0, 1, 2, 3, 4], default=1,
                                help='log level: 0-NONE, 1-ERROR(default), 2-CONFIG, 3-INFO, 4-DEBUG')
        app_parser.add_argument('-o', type=int, choices=[0, 1, 2], default=2,
                                help='log output: 0-stdout, 1-stderr, 2-syslog(default)')
        # Note: the argument parser can exit here with the following exit codes:
        # 0 - printing help or version text
        # 2 - invalid parameter
        parsed_results = app_parser.parse_args()

        # Create a Log class instance (in theory this cannot fail).
        try:
            self.log = Log(parsed_results.l, parsed_results.o)
        except ValueError as e:
            print(f'ERROR: {e}.', flush=True, file=sys.stdout)
            sys.exit(5)

        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, 'Command line arguments:')
            self.log.msg(Log.LOG_CONFIG, f'   original arguments: {" ".join(sys.argv[:])}')
            self.log.msg(Log.LOG_CONFIG, f'   parsed config file = {parsed_results.config_file}')
            self.log.msg(Log.LOG_CONFIG, f'   parsed log level = {parsed_results.l}')
            self.log.msg(Log.LOG_CONFIG, f'   parsed log output = {parsed_results.o}')

        # Parse and load configuration file.
        self.config = configparser.ConfigParser()
        if not self.config or not self.config.read(parsed_results.config_file):
            self.log.msg(Log.LOG_ERROR, f'Cannot load configuration file ({parsed_results.config_file})')
            sys.exit(6)
        self.cpu_zone_enabled = self.config[CpuZone.CS_CPU_ZONE].getboolean(CpuZone.CV_CPU_ZONE_ENABLED, fallback=False)
        self.hd_zone_enabled = self.config[HdZone.CS_HD_ZONE].getboolean(HdZone.CV_HD_ZONE_ENABLED, fallback=False)
        self.log.msg(Log.LOG_DEBUG, f'Configuration file ({parsed_results.config_file}) loaded')

        # Check run-time dependencies (commands, kernel modules).
        error_msg = self.check_dependencies()
        if error_msg:
            self.log.msg(Log.LOG_ERROR, error_msg)
            sys.exit(4)

        # Create an Ipmi class instances and set required IPMI fan mode.
        try:
            self.ipmi = Ipmi(self.log, self.config)
            old_mode = self.ipmi.get_fan_mode()
        except (ValueError, FileNotFoundError) as e:
            self.log.msg(Log.LOG_ERROR, f'{e}.')
            sys.exit(7)
        self.log.msg(Log.LOG_DEBUG, f'Old IPMI fan mode = {self.ipmi.get_fan_mode_name(old_mode)}')
        if old_mode != Ipmi.FULL_MODE:
            self.ipmi.set_fan_mode(Ipmi.FULL_MODE)
            self.log.msg(Log.LOG_DEBUG,
                         f'New IPMI fan mode = {self.ipmi.get_fan_mode_name(Ipmi.FULL_MODE)}')

        # Create an instance for CPU zone fan controller if enabled.
        # self.cpu_zone = None
        if self.cpu_zone_enabled:
            self.log.msg(Log.LOG_DEBUG, 'CPU zone fan controller enabled')
            self.cpu_zone = CpuZone(self.log, self.ipmi, self.config)

        # Create an instance for HD zone fan controller if enabled.
        # self.hd_zone = None
        if self.hd_zone_enabled:
            self.log.msg(Log.LOG_DEBUG, 'HD zone fan controller enabled')
            self.hd_zone = HdZone(self.log, self.ipmi, self.config)

        # Calculate the default sleep time for the main loop.
        if self.cpu_zone_enabled and self.hd_zone_enabled:
            wait = min(self.cpu_zone.polling, self.hd_zone.polling) / 2
        elif self.cpu_zone_enabled and not self.hd_zone_enabled:
            wait = self.cpu_zone.polling / 2
        elif not self.cpu_zone_enabled and self.hd_zone_enabled:
            wait = self.hd_zone.polling / 2
        else:  # elif not cpu_zone_enabled and not hd_controller_enabled:
            self.log.msg(Log.LOG_ERROR, 'None of the fan controllers are enabled, service terminated.')
            sys.exit(8)
        self.log.msg(Log.LOG_DEBUG, f'Main loop wait time = {wait} sec')

        # Main execution loop.
        while True:
            if self.cpu_zone_enabled:
                self.cpu_zone.run()
            if self.hd_zone_enabled:
                self.hd_zone.run()
            time.sleep(wait)

# End.
