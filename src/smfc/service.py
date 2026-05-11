#
#   service.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.Service() class implementation.
#
import atexit
import os
import sys
import time
from typing import Dict, List, Set, Tuple, Union
from importlib.metadata import version
from argparse import ArgumentParser, Namespace
from pyudev import Context
from smfc.constfc import ConstFc
from smfc.fancontroller import FanController
from smfc.gpufc import GpuFc
from smfc.cpufc import CpuFc
from smfc.hdfc import HdFc
from smfc.nvmefc import NvmeFc
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import Config


class Service:
    """Service class contains all resources/functions for the execution."""

    # Service data.
    config: Config                                             # Instance for a parsed configuration
    sudo: bool                                                 # Use sudo command
    log: Log                                                   # Instance for a Log class
    udevc: Context                                             # Reference to a pyudev Context instance
    ipmi: Ipmi                                                 # Instance for an Ipmi class
    controllers: List[Union[FanController, ConstFc]]           # List of enabled fan controller instances
    applied_levels: Dict[int, int]                             # Cache of last applied fan levels per IPMI zone
    shared_zones: Set[int]                                     # Set of IPMI zone IDs shared between controllers
    last_desired: List[Tuple[str, List[int], int, float]]      # Cache of last desired levels for change detection

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

    def check_dependencies(self) -> str:  # pylint: disable=too-many-return-statements
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
        path = self.config.ipmi.command
        if not os.path.exists(path):
            return f"ERROR: ipmitool command cannot be found {path}!"

        # Load the list of kernel modules.
        with open("/proc/modules", "rt", encoding="utf-8") as file:
            modules = file.read()

        # Check the kernel modules for CPU fan controller.
        if any(cfg.enabled for cfg in self.config.cpu):
            if "coretemp" not in modules and "k10temp" not in modules:
                return "ERROR: coretemp or k10temp kernel module must be loaded!"

        # Check dependencies for HD fan controller.
        enabled_hd_configs = [cfg for cfg in self.config.hd if cfg.enabled]
        if enabled_hd_configs:
            # Check if `drivetemp` module is loaded.
            if "drivetemp" not in modules:
                no_drivetemp = True
            for cfg in enabled_hd_configs:
                # Check if `smartctl` command is available.
                path = cfg.smartctl_path
                if not os.path.exists(path):
                    no_smartctl = True
                # If neither `drivetemp` nor `smartctl` is available.
                if no_smartctl and no_drivetemp:
                    return (f"ERROR: drivetemp kernel module must be loaded or "
                            f"smartctl command ({path}) must be installed!")
                # If Standby Guard feature enabled, `smartctl` command should be available.
                if cfg.standby_guard_enabled and no_smartctl:
                    return f"ERROR: smartctl command ({path}) must be installed for Standby Guard feature!"

        # Check dependencies for GPU fan controller.
        for cfg in self.config.gpu:
            if not cfg.enabled:
                continue
            if cfg.gpu_type == "nvidia":
                path = cfg.nvidia_smi_path
            else:
                path = cfg.rocm_smi_path
            if not os.path.exists(path):
                return f"ERROR: {path} command cannot be found!"

        # All required run-time dependencies are available.
        return ""

    def _collect_desired_levels(self) -> List[Tuple[str, List[int], int, float]]:
        """Collect desired fan levels from deferred controllers only (non-deferred controllers handle their own zones).

        Returns:
            List[Tuple[str, List[int], int, float]]: list of (name, ipmi_zones, last_level, last_temp) tuples
        """
        levels: List[Tuple[str, List[int], int, float]] = []
        for fc in self.controllers:
            if fc.deferred_apply and (fc.last_level > 0 or isinstance(fc, ConstFc)):
                levels.append((fc.name, fc.config.ipmi_zone, fc.last_level, fc.last_temp))
        return levels

    def _apply_fan_levels(self) -> None:
        """Apply the maximum desired fan level per IPMI zone across all controllers."""
        desired = self._collect_desired_levels()
        if self.log.log_level >= Log.LOG_DEBUG and desired != self.last_desired:
            self.log.msg(Log.LOG_DEBUG, f"Arbitration desired levels: "
                         f"{[(n, z, l, f'{t:.1f}C') for n, z, l, t in desired]}")
            self.last_desired = desired
        # Build zone -> (max_level, winner_name) mapping and collect all contributors per zone
        zone_levels: Dict[int, Tuple[int, str]] = {}
        zone_contributors: Dict[int, List[Tuple[str, int, float]]] = {}
        for name, zones, level, temp in desired:
            for zone in zones:
                zone_contributors.setdefault(zone, []).append((name, level, temp))
                if zone not in zone_levels or level > zone_levels[zone][0]:
                    zone_levels[zone] = (level, name)
        # Apply only changed levels (non-deferred controllers handle their own zones directly).
        for zone, (level, winner) in zone_levels.items():
            if self.applied_levels.get(zone) == level:
                continue
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
        for fc in self.controllers:
            for zone in fc.config.ipmi_zone:
                zone_owners.setdefault(zone, []).append(fc.name)
        if self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f"IPMI zone ownership: {dict(zone_owners)}")
        shared: Set[int] = set()
        for zone, names in zone_owners.items():
            if len(names) > 1:
                self.log.msg(Log.LOG_INFO, f"Shared IPMI zone {zone}: {names}")
                shared.add(zone)
        return shared

    @staticmethod
    def _parse_args() -> Namespace:
        """Parse command-line arguments.

        Returns:
            Namespace: parsed arguments
        """
        parser = ArgumentParser()
        parser.add_argument("-c", action="store", dest="config_file", default="smfc.conf",
                            help="configuration file (default is /etc/smfc/smfc.conf)")
        parser.add_argument("-v", "--version", action="version", version="%(prog)s " + version("smfc"))
        parser.add_argument("-l", type=int, choices=[0, 1, 2, 3, 4], default=1,
                            help="set log level: 0-NONE, 1-ERROR(default), 2-CONFIG, 3-INFO, 4-DEBUG")
        parser.add_argument("-o", type=int, choices=[0, 1, 2], default=2,
                            help="set log output: 0-stdout, 1-stderr, 2-syslog(default)")
        parser.add_argument("-nd", action="store_true", default=False, help="no dependency checking at start")
        parser.add_argument("-s", action="store_true", default=False, help="use sudo command")
        parser.add_argument("-ne", action="store_true", default=False, help="no fan speed recovery at exit")
        return parser.parse_args()

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
        old_mode: int               # Old IPMI fan mode

        # Parse command line arguments.
        parsed_results = self._parse_args()

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
        try:
            self.config = Config(parsed_results.config_file)
        except (FileNotFoundError, ValueError) as e:
            self.log.msg(Log.LOG_ERROR, f"Configuration error: {e}")
            sys.exit(6)
        self.log.msg(Log.LOG_DEBUG, f"Configuration file ({parsed_results.config_file}) loaded")

        # Check run-time dependencies (commands, kernel modules) if `-nd` command line option is not specified.
        if not parsed_results.nd:
            error_msg = self.check_dependencies()
            if error_msg:
                self.log.msg(Log.LOG_ERROR, error_msg)
                sys.exit(7)

        # Create an Ipmi class instance.
        try:
            self.ipmi = Ipmi(self.log, self.config.ipmi, self.sudo)
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
        self.last_desired = []

        # Create enabled fan controller instances.
        self.controllers = []
        for cfg in self.config.cpu:
            if cfg.enabled:
                self.log.msg(Log.LOG_DEBUG, f"CPU fan controller [{cfg.section}] enabled")
                self.controllers.append(CpuFc(self.log, self.udevc, self.ipmi, cfg))
                time.sleep(self.config.ipmi.fan_level_delay)
        for cfg in self.config.hd:
            if cfg.enabled:
                self.log.msg(Log.LOG_DEBUG, f"HD fan controller [{cfg.section}] enabled")
                self.controllers.append(HdFc(self.log, self.udevc, self.ipmi, cfg, self.sudo))
                time.sleep(self.config.ipmi.fan_level_delay)
        for cfg in self.config.nvme:
            if cfg.enabled:
                self.log.msg(Log.LOG_DEBUG, f"NVME fan controller [{cfg.section}] enabled")
                self.controllers.append(NvmeFc(self.log, self.udevc, self.ipmi, cfg))
                time.sleep(self.config.ipmi.fan_level_delay)
        for cfg in self.config.gpu:
            if cfg.enabled:
                self.log.msg(Log.LOG_DEBUG, f"GPU fan controller [{cfg.section}] enabled")
                self.controllers.append(GpuFc(self.log, self.ipmi, cfg))
                time.sleep(self.config.ipmi.fan_level_delay)
        for cfg in self.config.const:
            if cfg.enabled:
                self.log.msg(Log.LOG_DEBUG, f"CONST fan controller [{cfg.section}] enabled")
                self.controllers.append(ConstFc(self.log, self.ipmi, cfg))
                time.sleep(self.config.ipmi.fan_level_delay)

        # If none of the fan controllers is enabled.
        if not self.controllers:
            self.log.msg(Log.LOG_ERROR, "None of the fan controllers are enabled, service terminated.")
            sys.exit(10)

        # Check for shared IPMI zones and enable deferred apply only for affected controllers.
        self.shared_zones = self._check_shared_zones()
        if self.shared_zones:
            for fc in self.controllers:
                if set(fc.config.ipmi_zone) & self.shared_zones:
                    fc.deferred_apply = True

        # Calculate the wait time in the main loop.
        wait = min(fc.config.polling for fc in self.controllers) / 2
        self.log.msg(Log.LOG_DEBUG, f"Main loop sleep time = {wait} sec")

        # Main execution loop.
        while True:
            for fc in self.controllers:
                fc.run()
            if self.shared_zones:
                self._apply_fan_levels()
            time.sleep(wait)


# End.
