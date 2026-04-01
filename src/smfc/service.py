#
#   service.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.Service() class implementation.
#
import atexit
import os
import sys
import time
from typing import Dict, List, Set, Tuple
from importlib.metadata import version
from configparser import ConfigParser
from argparse import ArgumentParser, Namespace
from pyudev import Context
from smfc.constfc import ConstFc
from smfc.gpufc import GpuFc
from smfc.cpufc import CpuFc
from smfc.hdfc import HdFc
from smfc.nvmefc import NvmeFc
from smfc.ipmi import Ipmi
from smfc.log import Log


class Service:
    """Service class contains all resources/functions for the execution."""

    # Service data.
    config: ConfigParser            # Instance for a parsed configuration
    sudo: bool                      # Use sudo command
    log: Log                        # Instance for a Log class
    udevc: Context                  # Reference to a pyudev Context instance (i.e. udev database connection)
    ipmi: Ipmi                      # Instance for an Ipmi class
    cpu_fc: CpuFc                   # Instance for a CPU fan controller class
    hd_fc: HdFc                     # Instance for an HD fan controller class
    nvme_fc: NvmeFc                 # Instance for an NVME fan controller class
    gpu_fc: GpuFc                   # Instance for a GPU fan controller class
    const_fc: ConstFc               # Instance for a CONST fan controller class
    cpu_fc_enabled: bool            # CPU fan controller enabled
    hd_fc_enabled: bool             # HD fan controller enabled
    nvme_fc_enabled: bool           # NVME fan controller enabled
    gpu_fc_enabled: bool            # GPU fan controller enabled
    const_fc_enabled: bool          # CONST fan controller enabled
    applied_levels: Dict[int, int]  # Cache of last applied fan levels per IPMI zone
    shared_zones: Set[int]          # Set of IPMI zone IDs shared between controllers

    def exit_func(self) -> None:
        """This function is called at exit (in case of exceptions or runtime errors cannot be handled), and it switches
        all fans back to the default speed 100% to avoid overheating while `smfc` is not running."""
        # Configure fans.
        if hasattr(self, "ipmi"):
            self.ipmi.set_fan_mode(Ipmi.FULL_MODE)
            if hasattr(self, "log"):
                self.log.msg(Log.LOG_INFO, "smfc terminated: all fans set to the 100% speed.")

        # Unregister this function.
        atexit.unregister(self.exit_func)

    def check_dependencies(self) -> str:
        """Check run-time dependencies of smfc:
              - ipmitool command
              - if CPU fan controller enabled: either `coretemp` or `k10temp` kernel module
              - if HD fan controller enabled: either `drivetemp` kernel module or `smartctl` command
              - if GPU fan controller enabled: `nvidia-smi` command
        Returns:
            str: error string (empty = no errors)
        """
        path: str
        no_smartctl: bool = False
        no_drivetemp: bool = False

        # Check if `ipmitool` command is available.
        path = self.config[Ipmi.CS_IPMI].get(Ipmi.CV_IPMI_COMMAND, "/usr/bin/ipmitool")
        if not os.path.exists(path):
            return f"ERROR: ipmitool command cannot be found {path}!"

        # Load the list of kernel modules.
        with open("/proc/modules", "rt", encoding="utf-8") as file:
            modules = file.read()

        # Check the kernel modules for CPU fan controller.
        if self.cpu_fc_enabled:
            if "coretemp" not in modules and "k10temp" not in modules:
                return "ERROR: coretemp or k10temp kernel module must be loaded!"

        # Check dependencies for HD fan controller.
        if self.hd_fc_enabled:
            # Check if `smartctl` command is available.
            path = self.config[HdFc.CS_HD_FC].get(HdFc.CV_HD_FC_SMARTCTL_PATH, "/usr/sbin/smartctl")
            if not os.path.exists(path):
                no_smartctl = True

            # Check if `drivetemp` modules is loaded.
            if "drivetemp" not in modules:
                no_drivetemp = True

            # If neither `drivetemp` nor `smartctl` is available.
            if no_smartctl and no_drivetemp:
                return f"ERROR: drivetemp kernel module must be loaded or smartctl command ({path}) must be installed!"

            # If Standby Guard feature enabled, `smartctl` command should be available
            sge = self.config[HdFc.CS_HD_FC].getboolean(HdFc.CV_HD_FC_STANDBY_GUARD_ENABLED, fallback=False)
            if sge and no_smartctl:
                return f"ERROR: smartctl command ({path}) must be installed for Standby Guard feature!"

        # Check dependencies for GPU fancontroller.
        if self.gpu_fc_enabled:
            # Check if `nvidia-smi` command is available.
            path = self.config[GpuFc.CS_GPU_FC].get(GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH, "/usr/bin/nvidia-smi")
            if not os.path.exists(path):
                return f"ERROR: nvidia-smi command cannot be found {path}!"

        # All required run-time dependencies are available.
        return ""

    def _collect_desired_levels(self) -> List[Tuple[str, List[int], int, float]]:
        """Collect desired fan levels from all enabled controllers.

        Returns:
            List[Tuple[str, List[int], int, float]]: list of (name, ipmi_zones, last_level, last_temp) tuples
        """
        levels: List[Tuple[str, List[int], int, float]] = []
        if self.cpu_fc_enabled and self.cpu_fc.last_level > 0:
            levels.append((CpuFc.CS_CPU_FC, self.cpu_fc.ipmi_zone, self.cpu_fc.last_level, self.cpu_fc.last_temp))
        if self.hd_fc_enabled and self.hd_fc.last_level > 0:
            levels.append((HdFc.CS_HD_FC, self.hd_fc.ipmi_zone, self.hd_fc.last_level, self.hd_fc.last_temp))
        if self.nvme_fc_enabled and self.nvme_fc.last_level > 0:
            levels.append((NvmeFc.CS_NVME_FC, self.nvme_fc.ipmi_zone, self.nvme_fc.last_level, self.nvme_fc.last_temp))
        if self.gpu_fc_enabled and self.gpu_fc.last_level > 0:
            levels.append((GpuFc.CS_GPU_FC, self.gpu_fc.ipmi_zone, self.gpu_fc.last_level, self.gpu_fc.last_temp))
        if self.const_fc_enabled:
            levels.append((ConstFc.CS_CONST_FC, self.const_fc.ipmi_zone, self.const_fc.last_level, 0.0))
        return levels

    def _apply_fan_levels(self) -> None:
        """Apply the maximum desired fan level per IPMI zone across all controllers."""
        desired = self._collect_desired_levels()
        # Build zone -> (max_level, winner_name) mapping and collect all contributors per zone
        zone_levels: Dict[int, Tuple[int, str]] = {}
        zone_contributors: Dict[int, List[Tuple[str, int, float]]] = {}
        for name, zones, level, temp in desired:
            for zone in zones:
                zone_contributors.setdefault(zone, []).append((name, level, temp))
                if zone not in zone_levels or level > zone_levels[zone][0]:
                    zone_levels[zone] = (level, name)
        # Apply only changed levels
        for zone, (level, winner) in zone_levels.items():
            if self.applied_levels.get(zone) != level:
                self.ipmi.set_fan_level(zone, level)
                self.applied_levels[zone] = level
                contributors = zone_contributors.get(zone, [])
                if len(contributors) > 1:
                    winner_str = ""
                    loser_parts = []
                    for n, l, t in contributors:
                        s = f"{n}={l}%/{t:.1f}C" if t > 0.0 else f"{n}={l}%"
                        if n == winner:
                            winner_str = s
                        else:
                            loser_parts.append(s)
                    msg = f"Shared IPMI zone [{zone}]: new level = {level}% (winner: {winner_str},"\
                          f" losers: {', '.join(loser_parts)})"
                    self.log.msg(Log.LOG_INFO, msg)
                elif len(contributors) == 1:
                    n, l, t = contributors[0]
                    detail = f"{n}={t:.1f}C" if t > 0.0 else f"{n}"
                    self.log.msg(Log.LOG_INFO, f"IPMI zone [{zone}]: new level = {l}% ({detail})")


    def _check_shared_zones(self) -> Set[int]:
        """Check if any IPMI zones are shared between enabled controllers.

        Returns:
            Set[int]: set of zone IDs used by 2+ controllers (empty if none shared)
        """
        zone_owners: Dict[int, List[str]] = {}
        if self.cpu_fc_enabled:
            for zone in self.cpu_fc.ipmi_zone:
                zone_owners.setdefault(zone, []).append(CpuFc.CS_CPU_FC)
        if self.hd_fc_enabled:
            for zone in self.hd_fc.ipmi_zone:
                zone_owners.setdefault(zone, []).append(HdFc.CS_HD_FC)
        if self.nvme_fc_enabled:
            for zone in self.nvme_fc.ipmi_zone:
                zone_owners.setdefault(zone, []).append(NvmeFc.CS_NVME_FC)
        if self.gpu_fc_enabled:
            for zone in self.gpu_fc.ipmi_zone:
                zone_owners.setdefault(zone, []).append(GpuFc.CS_GPU_FC)
        if self.const_fc_enabled:
            for zone in self.const_fc.ipmi_zone:
                zone_owners.setdefault(zone, []).append(ConstFc.CS_CONST_FC)
        shared: Set[int] = set()
        for zone, names in zone_owners.items():
            if len(names) > 1:
                self.log.msg(Log.LOG_INFO, f"Shared IPMI zone {zone}: {names}")
                shared.add(zone)
        return shared

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
        app_parser: ArgumentParser  # Instance for an ArgumentParser class
        parsed_results: Namespace   # Results of parsed command line arguments
        old_mode: int               # Old IPMI fan mode

        # Handling of the command line arguments.
        app_parser = ArgumentParser()
        # Syntax definition of the command-line parameters.
        app_parser.add_argument("-c", action="store", dest="config_file", default="smfc.conf",
                                help="configuration file (default is /etc/smfc/smfc.conf)",)
        app_parser.add_argument("-v", "--version", action="version", version="%(prog)s " + version("smfc"))
        app_parser.add_argument("-l", type=int, choices=[0, 1, 2, 3, 4], default=1,
                                help="set log level: 0-NONE, 1-ERROR(default), 2-CONFIG, 3-INFO, 4-DEBUG",)
        app_parser.add_argument("-o", type=int, choices=[0, 1, 2], default=2,
                                help="set log output: 0-stdout, 1-stderr, 2-syslog(default)",)
        app_parser.add_argument("-nd", action="store_true", default=False,
                                help="no dependency checking at start",)
        app_parser.add_argument("-s", action="store_true", default=False, help="use sudo command")
        app_parser.add_argument("-ne", action="store_true", default=False, help="no fan speed recovery at exit",)
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
            print(f"ERROR: {e}.", flush=True, file=sys.stdout)
            sys.exit(5)

        # Log command line parameters.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"Smfc version {version('smfc')} started")
            self.log.msg(Log.LOG_CONFIG, "Command line arguments:")
            self.log.msg(Log.LOG_CONFIG, f"   original arguments: {' '.join(sys.argv[:])}")
            self.log.msg(Log.LOG_CONFIG, f"   parsed config file = {parsed_results.config_file}")
            self.log.msg(Log.LOG_CONFIG, "Logging was initialized with:")
            self.log.msg(Log.LOG_CONFIG, f"   log_level = {self.log.log_level}")
            self.log.msg(Log.LOG_CONFIG, f"   log_output = {self.log.log_output}")

        # Parse and load configuration file.
        self.config = ConfigParser()
        if not self.config or not self.config.read(parsed_results.config_file):
            self.log.msg(Log.LOG_ERROR, f"Cannot load configuration file ({parsed_results.config_file})")
            sys.exit(6)
        # Backward compatibility: accept old section names (with 'zone' tag).
        for old_name, new_name in {
            "CPU zone": CpuFc.CS_CPU_FC,
            "HD zone": HdFc.CS_HD_FC,
            "NVME zone": NvmeFc.CS_NVME_FC,
            "GPU zone": GpuFc.CS_GPU_FC,
            "CONST zone": ConstFc.CS_CONST_FC
        }.items():
            if self.config.has_section(old_name) and not self.config.has_section(new_name):
                self.config[new_name] = self.config[old_name]
                self.config.remove_section(old_name)
                self.log.msg(Log.LOG_INFO, f"Deprecated section name [{old_name}], " \
                                           "please update your configuration file.")
        # Read [CPU] enabled= parameter if the section exists.
        self.cpu_fc_enabled = (
            (self.config[CpuFc.CS_CPU_FC].getboolean(CpuFc.CV_CPU_FC_ENABLED, fallback=False))
            if self.config.has_section(CpuFc.CS_CPU_FC) else False
        )
        # Read [HD] enabled= parameter if the section exists.
        self.hd_fc_enabled = (
            (self.config[HdFc.CS_HD_FC].getboolean(HdFc.CV_HD_FC_ENABLED, fallback=False))
            if self.config.has_section(HdFc.CS_HD_FC) else False
        )
        # Read [NVME] enabled= parameter if the section exists.
        self.nvme_fc_enabled = (
            (self.config[NvmeFc.CS_NVME_FC].getboolean(NvmeFc.CV_NVME_FC_ENABLED, fallback=False))
            if self.config.has_section(NvmeFc.CS_NVME_FC) else False
        )
        # Read [GPU] enabled= parameter if the section exists.
        self.gpu_fc_enabled = (
            (self.config[GpuFc.CS_GPU_FC].getboolean(GpuFc.CV_GPU_FC_ENABLED, fallback=False))
            if self.config.has_section(GpuFc.CS_GPU_FC) else False
        )
        # Read [CONST] enabled= parameter if the section exists.
        self.const_fc_enabled = (
            (self.config[ConstFc.CS_CONST_FC].getboolean(ConstFc.CV_CONST_FC_ENABLED, fallback=False))
            if self.config.has_section(ConstFc.CS_CONST_FC) else False
        )
        self.log.msg(Log.LOG_DEBUG, f"Configuration file ({parsed_results.config_file}) loaded")

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
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            self.log.msg(Log.LOG_ERROR, f"{e}.")
            sys.exit(8)
        # Log the old fan mode and zone levels in DEBUG log mode.
        if self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f"Old IPMI fan mode = {self.ipmi.get_fan_mode_name(old_mode)} ({old_mode})")
            self.log.msg(Log.LOG_DEBUG, f"Old CPU zone (0) level = {self.ipmi.get_fan_level(Ipmi.CPU_ZONE)}%")
            self.log.msg(Log.LOG_DEBUG, f"Old HD zone (1) level = {self.ipmi.get_fan_level(Ipmi.HD_ZONE)}%")
        #  Set the FULL IPMI fan mode if it is not the current fan mode.
        if old_mode != Ipmi.FULL_MODE:
            self.ipmi.set_fan_mode(Ipmi.FULL_MODE)
            self.log.msg(Log.LOG_DEBUG, f"New IPMI fan mode = {self.ipmi.get_fan_mode_name(Ipmi.FULL_MODE)}")

        # Initialize connection to udev database
        try:
            self.udevc = Context()
        except ImportError as e:
            self.log.msg(Log.LOG_ERROR, f"pyudev error: Could not interface with libudev: {e}.")
            sys.exit(9)

        # Initialize the applied levels cache for zone arbitration.
        self.applied_levels = {}

        # Create an instance for CPU fan controller if enabled.
        if self.cpu_fc_enabled:
            self.log.msg(Log.LOG_DEBUG, "CPU fan controller enabled")
            self.cpu_fc = CpuFc(self.log, self.udevc, self.ipmi, self.config)
            time.sleep(self.ipmi.fan_level_delay)

        # Create an instance for HD fan controller if enabled.
        if self.hd_fc_enabled:
            self.log.msg(Log.LOG_DEBUG, "HD fan controller enabled")
            self.hd_fc = HdFc(self.log, self.udevc, self.ipmi, self.config, self.sudo)
            time.sleep(self.ipmi.fan_level_delay)

        # Create an instance for NVME fan controller if enabled.
        if self.nvme_fc_enabled:
            self.log.msg(Log.LOG_DEBUG, "NVME fan controller enabled")
            self.nvme_fc = NvmeFc(self.log, self.udevc, self.ipmi, self.config)
            time.sleep(self.ipmi.fan_level_delay)

        # Create an instance for GPU fan controller if enabled.
        if self.gpu_fc_enabled:
            self.log.msg(Log.LOG_DEBUG, "GPU fan controller enabled")
            self.gpu_fc = GpuFc(self.log, self.ipmi, self.config)
            time.sleep(self.ipmi.fan_level_delay)

        # Create an instance for CONST fan controller if enabled.
        if self.const_fc_enabled:
            self.log.msg(Log.LOG_DEBUG, "CONST fan controller enabled")
            self.const_fc = ConstFc(self.log, self.ipmi, self.config)
            time.sleep(self.ipmi.fan_level_delay)

        # Check for shared IPMI zones and enable deferred apply only for affected controllers.
        self.shared_zones = self._check_shared_zones()
        if self.shared_zones:
            if self.cpu_fc_enabled and set(self.cpu_fc.ipmi_zone) & self.shared_zones:
                self.cpu_fc.deferred_apply = True
            if self.hd_fc_enabled and set(self.hd_fc.ipmi_zone) & self.shared_zones:
                self.hd_fc.deferred_apply = True
            if self.nvme_fc_enabled and set(self.nvme_fc.ipmi_zone) & self.shared_zones:
                self.nvme_fc.deferred_apply = True
            if self.gpu_fc_enabled and set(self.gpu_fc.ipmi_zone) & self.shared_zones:
                self.gpu_fc.deferred_apply = True
            if self.const_fc_enabled and set(self.const_fc.ipmi_zone) & self.shared_zones:
                self.const_fc.deferred_apply = True

        # Calculate the default sleep time for the main loop.
        polling_set = set()
        if self.cpu_fc_enabled:
            polling_set.add(self.cpu_fc.polling)
        if self.hd_fc_enabled:
            polling_set.add(self.hd_fc.polling)
        if self.nvme_fc_enabled:
            polling_set.add(self.nvme_fc.polling)
        if self.gpu_fc_enabled:
            polling_set.add(self.gpu_fc.polling)
        if self.const_fc_enabled:
            polling_set.add(self.const_fc.polling)

        # If none of the fan controllers is enabled.
        if len(polling_set) == 0:
            self.log.msg(Log.LOG_ERROR, "None of the fan controllers are enabled, service terminated.")
            sys.exit(10)

        # Calculate the wait time in the main loop.
        wait = min(polling_set) / 2
        self.log.msg(Log.LOG_DEBUG, f"Main loop sleep time = {wait} sec")

        # Main execution loop.
        while True:
            if self.cpu_fc_enabled:
                self.cpu_fc.run()
            if self.hd_fc_enabled:
                self.hd_fc.run()
            if self.nvme_fc_enabled:
                self.nvme_fc.run()
            if self.gpu_fc_enabled:
                self.gpu_fc.run()
            if self.const_fc_enabled:
                self.const_fc.run()
            if self.shared_zones:
                self._apply_fan_levels()
            time.sleep(wait)


# End.
