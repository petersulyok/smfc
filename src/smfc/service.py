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
from smfc.fancontroller import FanController
from smfc.constzone import ConstZone
from smfc.gpuzone import GpuZone
from smfc.cpuzone import CpuZone
from smfc.hdzone import HdZone
from smfc.ipmi import Ipmi
from smfc.log import Log
from typing import List
CV_ZONE_ENABLED: str = 'enabled'

class Service:
    """Service class contains all resources/functions for the execution."""

    # Service data.
    config: ConfigParser                # Instance for a parsed configuration
    sudo: bool                          # Use sudo command
    log: Log                            # Instance for a Log class
    udevc: Context                      # Reference to a pyudev Context instance (i.e. udev database connection)
    ipmi: Ipmi                          # Instance for an Ipmi class
    fan_zones: List[FanController]

    def exit_func(self) -> None:
        """This function is called at exit (in case of exceptions or runtime errors cannot be handled), and it switches
           all fans back to rhw default speed 100% to avoid overheating while `smfc` is not running."""
        # Configure fans.
        if hasattr(self, 'ipmi'):
            self.ipmi.set_fan_mode(Ipmi.FULL_MODE)
            if hasattr(self, 'log'):
                self.log.msg(Log.LOG_INFO, 'smfc terminated: all fans are switched back to the 100% speed.')

        # Unregister this function.
        atexit.unregister(self.exit_func)

    def check_dependencies(self) -> str:
        """Check run-time dependencies of smfc:
              - ipmitool command
              - if CPU zone enabled: `coretemp` or `k10temp` kernel module
              - if HD zone enabled: `drivetemp` kernel module or `smartctl` command
              - if GPU zone enabled: `nvidia-smi` command
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

        # Load the list of kernel modules.
        with open('/proc/modules', 'rt', encoding='utf-8') as file:
            modules = file.read()

        for zone in self.fan_zones:
            if isinstance(zone, CpuZone):
                # Check the kernel modules for CPU zone.
                if 'coretemp' not in modules and 'k10temp' not in modules:
                    return 'ERROR: coretemp or k10temp kernel module must be loaded!'
            elif isinstance(zone, HdZone):
                # Check if `smartctl` command is available.
                path = self.config[zone.config_section].get(HdZone.CV_HD_ZONE_SMARTCTL_PATH, '/usr/sbin/smartctl')
                if not os.path.exists(path):
                    no_smartctl = True

                # Check if `drivetemp` modules is loaded.
                if 'drivetemp' not in modules:
                    no_drivetemp = True

                # If neither `drivetemp` nor `smartctl` is available.
                if no_smartctl and no_drivetemp:
                    return f'ERROR: drivetemp kernel module must be loaded or smartctl command ({path}) must be installed!'

                # If Standby Guard feature enabled, `smartctl` command should be available
                sge = self.config[zone.config_section].getboolean(HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED, fallback=False)
                if sge and no_smartctl:
                    return f'ERROR: smartctl command ({path}) must be installed for Standby Guard feature!'

            elif isinstance(zone, GpuZone):
                # Check if `nvidia-smi` command is available.
                path = self.config[zone.config_section].get(GpuZone.CV_GPU_ZONE_NVIDIA_SMI_PATH, '/usr/bin/nvidia-smi')
                if not os.path.exists(path):
                    return f'ERROR: nvidia-smi command cannot be found {path}!'

        # All required run-time dependencies are available.
        return ''

    def load_zone_config(self) -> None:
        # Read the config sections to determine which zones to enable
        # Multiple instances of zones are supported
        self.fan_zones = []
        for section_key in self.config.sections():
            if section_key == "Ipmi":
                continue

            if ":" in section_key:
                if len(section_key.split(":")) == 2:
                    zone_type, instance_identifier = section_key.split(":")
                else:
                    self.log.msg(Log.LOG_ERROR, f'Invalid config section: {section_key} (too many semi-colons)')
                    sys.exit(6)
            else:
                zone_type = section_key
                instance_identifier = ""
            zone_enabled = (self.config[section_key].
                                 getboolean(CV_ZONE_ENABLED, fallback=False))
            if not zone_enabled:
                continue

            if instance_identifier:
                instance_identifier = f": {instance_identifier}"  # prefix as it will be concatenated with name

            if zone_type == CpuZone.CS_CPU_ZONE:
                zone = CpuZone(self.log, self.udevc, self.ipmi, self.config, section_key, instance_identifier)
            elif zone_type == HdZone.CS_HD_ZONE:
                zone = HdZone(self.log, self.udevc, self.ipmi, self.config, section_key, instance_identifier, self.sudo)
            elif zone_type == GpuZone.CS_GPU_ZONE:
                zone = GpuZone(self.log, self.ipmi, self.config, section_key, instance_identifier)
            elif zone_type == ConstZone.CS_CONST_ZONE:
                zone = ConstZone(self.log, self.ipmi, self.config, section_key, instance_identifier)
            else:
                self.log.msg(Log.LOG_ERROR, f'Invalid config section: {section_key} (not a valid zone type)')
                sys.exit(6)
            self.log.msg(Log.LOG_DEBUG, f'{zone_type} fan controller enabled')
            self.fan_zones.append(zone)
            time.sleep(self.ipmi.fan_level_delay)


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
        10 - none of the fan controllers is enabled
        """
        app_parser: ArgumentParser     # Instance for an ArgumentParser class
        parsed_results: Namespace      # Results of parsed command line arguments
        old_mode: int                  # Old IPMI fan mode

        # Handling of the command line arguments.
        app_parser = ArgumentParser()
        # Syntax definition of the command-line parameters.
        app_parser.add_argument('-c', action='store', dest='config_file', default='smfc.conf',
                                help='configuration file (default is /etc/smfc/smfc.conf)')
        app_parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + version("smfc"))
        app_parser.add_argument('-l', type=int, choices=[0, 1, 2, 3, 4], default=1,
                                help='set log level: 0-NONE, 1-ERROR(default), 2-CONFIG, 3-INFO, 4-DEBUG')
        app_parser.add_argument('-o', type=int, choices=[0, 1, 2], default=2,
                                help='set log output: 0-stdout, 1-stderr, 2-syslog(default)')
        app_parser.add_argument('-nd', action='store_true', default=False,
                                help='no dependency checking at start')
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
            self.log.msg(Log.LOG_DEBUG, f'Old CPU zone (0) level = {self.ipmi.get_fan_level(Ipmi.CPU_ZONE)}%')
            self.log.msg(Log.LOG_DEBUG, f'Old HD zone (1) level = {self.ipmi.get_fan_level(Ipmi.HD_ZONE)}%')
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

        # Load zone config
        self.load_zone_config()

        # Check run-time dependencies (commands, kernel modules) if `-nd` command line option is not specified.
        if not parsed_results.nd:
            error_msg = self.check_dependencies()
            if error_msg:
                self.log.msg(Log.LOG_ERROR, error_msg)
                sys.exit(7)

        # Handle multiple controllers sharing the same IPMI zone
        shared_ipmi_zones = []
        for zone in self.ipmi.ipmi_zone_users.keys():
            if self.ipmi.is_ipmi_zone_shared(zone):
                shared_ipmi = SharedIpmiZone(zone, self.ipmi, self.log)
                shared_ipmi_zones.append(shared_ipmi)
                self.log.msg(Log.LOG_INFO, f'IPMI Zone {zone} is shared with multiple controllers')
        if not shared_ipmi_zones:
            self.log.msg(Log.LOG_DEBUG, 'No IPMI zones are shared')

        # Calculate the default sleep time for the main loop.
        polling_set = set()
        for zone in self.fan_zones:
            polling_set.add(zone.polling)

        # If none of the fan controller zones is enabled.
        if len(polling_set) == 0:
            self.log.msg(Log.LOG_ERROR, 'None of the zones / fan controllers are enabled, service terminated.')
            sys.exit(10)

        # Calculate the wait time in the main loop.
        wait = min(polling_set) / 2
        self.log.msg(Log.LOG_DEBUG, f'Main loop sleep time = {wait} sec')

        # Main execution loop.
        while True:
            for zone in self.fan_zones:
                zone.run()

            if shared_ipmi_zones:
                for shared_zone in shared_ipmi_zones:
                    shared_zone.run()
            time.sleep(wait)


# End.
