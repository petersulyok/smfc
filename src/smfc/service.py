#
#   service.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.Service() class implementation.
#
import atexit
import os
import sys
import time
from importlib.metadata import version
from configparser import ConfigParser
from argparse import ArgumentParser, Namespace
from pyudev import Context
from smfc.cpuzone import CpuZone
from smfc.hdzone import HdZone
from smfc.ipmi import Ipmi
from smfc.log import Log


class Service:
    """Service class contains all resources/functions for the execution."""

    # Service data.
    config: ConfigParser    # Instance for a parsed configuration
    sudo: bool              # Use sudo command
    log: Log                # Instance for a Log class
    udevc: Context          # Reference to a pyudev Context instance (i.e. udev database connection)
    ipmi: Ipmi              # Instance for an Ipmi class
    cpu_zone: CpuZone       # Instance for a CPU Zone fan controller class
    hd_zone: HdZone         # Instance for an HD Zone fan controller class
    cpu_zone_enabled: bool  # CPU zone fan controller enabled
    hd_zone_enabled: bool   # HD zone fan controller enabled


    def exit_func(self) -> None:
        """This function is called at exit (in case of exceptions or runtime errors cannot be handled), and it switches
           all fans back to rhw default speed 100%, in order to avoid system overheating while `smfc` is not running."""
        # Configure fans.
        if hasattr(self, 'ipmi'):
            self.ipmi.set_fan_level(Ipmi.CPU_ZONE, 100)
            self.ipmi.set_fan_level(Ipmi.HD_ZONE, 100)
            if hasattr(self, 'log'):
                self.log.msg(Log.LOG_INFO, 'smfc terminated: all fans are switched back to the 100% speed.')

        # Unregister this function.
        atexit.unregister(self.exit_func)

    def check_dependencies(self) -> str:
        """Check run-time dependencies of smfc:
              - ipmitool command
              - if CPU zone enabled: `coretemp` or `k10temp` kernel module
              - if HD zone enabled: `drivetemp` kernel module or `smartctl` command
        Returns:
             (str): error string (empty = no errors)

        """
        path: str
        no_smartctl: bool = False
        no_drivetemp: bool = False

        # Check if `ipmitool` command is available.
        path = self.config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_COMMAND, '/usr/bin/ipmitool')
        if not os.path.exists(path):
            return f'ERROR: ipmitool command cannot be found {path}!'

        # Load list of kernel modules.
        with open('/proc/modules', 'rt', encoding='utf-8') as file:
            modules = file.read()

        # Check kernel modules for CPUs
        if self.cpu_zone_enabled:
            if 'coretemp' not in modules and 'k10temp' not in modules:
                return 'ERROR: coretemp or k10temp kernel module must be loaded!'

        # Check dependencies for disks
        if self.hd_zone_enabled:

            # Check if `smartctl` command is available.
            path = self.config[HdZone.CS_HD_ZONE].get(HdZone.CV_HD_ZONE_SMARTCTL_PATH, '/usr/sbin/smartctl')
            if not os.path.exists(path):
                no_smartctl = True

            # Check if `drivetemp` modules is loaded.
            if 'drivetemp' not in modules:
                no_drivetemp = True

            # If neither `drivetemp` nor `smartctl` is available.
            if no_smartctl and no_drivetemp:
                return f'ERROR: drivetemp kernel module must be loaded or smartctl command ({path}) must be installed!'

        # If Standby Guard feature enabled, `smartctl` command should be available
        sge = self.config[HdZone.CS_HD_ZONE].getboolean(HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED, fallback=False)
        if sge and no_smartctl:
            return f'ERROR: smartctl command ({path}) must be installed for Standby Guard feature!'

        # All required run-time dependencies are available.
        return ''

    def run(self) -> None:
        """Run function: main execution function of the systemd service.

        Program exit codes:
        0 - printing help or version text (argument parser)
        2 - invalid parameter (argument parser)
        5 - log system initialization error
        6 - config file error
        7 - runtime dependency error
        8 - IPMI initialization error
        9 - udev initialization error
        10 - none of the zones is enabled
        """
        app_parser: ArgumentParser     # Instance for an ArgumentParser class
        parsed_results: Namespace      # Results of parsed command line arguments
        old_mode: int                  # Old IPMI fan mode

        # Handling of the command line arguments.
        app_parser = ArgumentParser()
        # Syntax definition of the command-line parameters.
        app_parser.add_argument('-c', action='store', dest='config_file', default='smfc.conf',
                                help='configuration file')
        app_parser.add_argument('-v', action='version', version='%(prog)s ' + version("smfc"))
        app_parser.add_argument('-l', type=int, choices=[0, 1, 2, 3, 4], default=1,
                                help='log level: 0-NONE, 1-ERROR(default), 2-CONFIG, 3-INFO, 4-DEBUG')
        app_parser.add_argument('-o', type=int, choices=[0, 1, 2], default=2,
                                help='log output: 0-stdout, 1-stderr, 2-syslog(default)')
        app_parser.add_argument('-nd', action='store_true', default=False,
                                help='no dependency checking')
        app_parser.add_argument('-s', action='store_true', default=False,
                                help='use sudo command')
        app_parser.add_argument('-ne', action='store_true', default=False,
                                help='no fan speed recovery at exit')
        # Parsing of the current arguments.
        parsed_results = app_parser.parse_args()

        # Register the emergency exit function for service termination.
        if not parsed_results.ne:
            atexit.register(self.exit_func)

        # Store `sudo` option.
        self.sudo = parsed_results.s

        # Create a Log class instance (in theory, this cannot fail).
        try:
            self.log = Log(parsed_results.l, parsed_results.o)
        except ValueError as e:
            print(f'ERROR: {e}.', flush=True, file=sys.stdout)
            sys.exit(5)

        # Log command line parameters.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f'Smfc version {version("smfc")} started')
            self.log.msg(Log.LOG_CONFIG, 'Command line arguments:')
            self.log.msg(Log.LOG_CONFIG, f'   original arguments: {" ".join(sys.argv[:])}')
            self.log.msg(Log.LOG_CONFIG, f'   parsed config file = {parsed_results.config_file}')
            self.log.msg(Log.LOG_CONFIG, 'Logging was initialized with:')
            self.log.msg(Log.LOG_CONFIG, f'   log_level = {self.log.log_level}')
            self.log.msg(Log.LOG_CONFIG, f'   log_output = {self.log.log_output}')

        # Parse and load configuration file.
        self.config = ConfigParser()
        if not self.config or not self.config.read(parsed_results.config_file):
            self.log.msg(Log.LOG_ERROR, f'Cannot load configuration file ({parsed_results.config_file})')
            sys.exit(6)
        self.cpu_zone_enabled = self.config[CpuZone.CS_CPU_ZONE].getboolean(CpuZone.CV_CPU_ZONE_ENABLED, fallback=False)
        self.hd_zone_enabled = self.config[HdZone.CS_HD_ZONE].getboolean(HdZone.CV_HD_ZONE_ENABLED, fallback=False)
        self.log.msg(Log.LOG_DEBUG, f'Configuration file ({parsed_results.config_file}) loaded')

        # Check run-time dependencies (commands, kernel modules) if `-nd` command line option is not specified.
        if not parsed_results.nd:
            error_msg = self.check_dependencies()
            if error_msg:
                self.log.msg(Log.LOG_ERROR, error_msg)
                sys.exit(7)

        # Create an Ipmi class instances.
        try:
            self.ipmi = Ipmi(self.log, self.config, self.sudo)
            old_mode = self.ipmi.get_fan_mode()
        except (ValueError, FileNotFoundError) as e:
            self.log.msg(Log.LOG_ERROR, f'{e}.')
            sys.exit(8)
        # Log the old fan mode and zone levels in DEBUG log mode.
        if self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f'Old IPMI fan mode = {self.ipmi.get_fan_mode_name(old_mode)} ({old_mode})')
            self.log.msg(Log.LOG_DEBUG, f'Old CPU zone level = {self.ipmi.get_fan_level(Ipmi.CPU_ZONE)}%%')
            self.log.msg(Log.LOG_DEBUG, f'Old HD zone level = {self.ipmi.get_fan_level(Ipmi.HD_ZONE)}%%')
        #  Set the FULL IPMI fan mode if it is not the current fan mode.
        if old_mode != Ipmi.FULL_MODE:
            self.ipmi.set_fan_mode(Ipmi.FULL_MODE)
            self.log.msg(Log.LOG_DEBUG,
                         f'New IPMI fan mode = {self.ipmi.get_fan_mode_name(Ipmi.FULL_MODE)}')

        # Initialize connection to udev database
        try:
            self.udevc = Context()
        except ImportError as e:
            self.log.msg(Log.LOG_ERROR, f'pyudev error: Could not interface with libudev: {e}.')
            sys.exit(9)

        # Create an instance for CPU zone fan controller if enabled.
        if self.cpu_zone_enabled:
            self.log.msg(Log.LOG_DEBUG, 'CPU zone fan controller enabled')
            self.cpu_zone = CpuZone(self.log, self.udevc, self.ipmi, self.config)

        # Create an instance for HD zone fan controller if enabled.
        if self.hd_zone_enabled:
            self.log.msg(Log.LOG_DEBUG, 'HD zone fan controller enabled')
            self.hd_zone = HdZone(self.log, self.udevc, self.ipmi, self.config, self.sudo)

        # Calculate the default sleep time for the main loop.
        if self.cpu_zone_enabled and self.hd_zone_enabled:
            wait = min(self.cpu_zone.polling, self.hd_zone.polling) / 2
        elif self.cpu_zone_enabled and not self.hd_zone_enabled:
            wait = self.cpu_zone.polling / 2
        elif not self.cpu_zone_enabled and self.hd_zone_enabled:
            wait = self.hd_zone.polling / 2
        else:  # elif not cpu_zone_enabled and not hd_controller_enabled:
            self.log.msg(Log.LOG_ERROR, 'None of the zones are enabled, service terminated.')
            sys.exit(10)
        self.log.msg(Log.LOG_DEBUG, f'Main loop sleep time = {wait} sec')

        # Main execution loop.
        while True:
            if self.cpu_zone_enabled:
                self.cpu_zone.run()
            if self.hd_zone_enabled:
                self.hd_zone.run()
            time.sleep(wait)

# End.
