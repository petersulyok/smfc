#
#   service.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.Service() class implementation.
#
import atexit
import os
import signal
import sys
import time
from typing import Dict, List, Optional, Set, Tuple, Union
from importlib.metadata import version
from argparse import ArgumentParser, Namespace
from pyudev import Context
from smfc.constfc import ConstFc
from smfc.exporter import Exporter
from smfc.fancontroller import FanController
from smfc.gpufc import GpuFc
from smfc.cpufc import CpuFc
from smfc.hdfc import HdFc
from smfc.nvmefc import NvmeFc
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import Config
from smfc.platform import ControlState, IpmiError
from smfc.snapshot import build_snapshot


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
    controlled_zones: List[int]                                # Sorted list of IPMI zones smfc controls
    last_desired: List[Tuple[str, List[int], int, float]]      # Cache of last desired levels for change detection
    last_fan_mode: int                                         # Last observed BMC fan mode (from _check_fan_mode)
    last_fan_mode_at: float                                    # monotonic() timestamp of last_fan_mode
    start_time: float                                          # Unix wall-clock start time of the service
    fan_mode_enforced_count: int                               # Count of detected drift-from-FULL corrections
    exporter: Optional[Exporter]                               # HTTP exporter (None when disabled or bind failed)

    def _sigterm_handler(self, signum, frame) -> None:  # pylint: disable=unused-argument
        """Handle SIGTERM (the default kill signal of systemd) by requesting a normal interpreter shutdown, so
        the registered `atexit` handler runs. `time.sleep()` in the main loop is interrupted by the signal and
        the raised SystemExit propagates out of it.
        Args:
            signum (int): signal number (unused)
            frame: current stack frame (unused)
        """
        sys.exit(0)

    def _exit_zones(self) -> List[int]:
        """Collect the IPMI zones the exit level has to be applied to.

        The fan controllers are the authoritative source, but `exit_func()` also runs on early exits (config,
        dependency, IPMI or udev errors) where they do not exist yet, so the configuration is scanned directly
        in that case.
        Returns:
            List[int]: sorted list of configured IPMI zones (empty if the configuration is not loaded yet)
        """
        zones: Set[int] = set()
        for fc in getattr(self, "controllers", []):
            zones.update(fc.config.ipmi_zone)
        if not zones and hasattr(self, "config"):
            for cfg_list in (self.config.cpu, self.config.hd, self.config.nvme, self.config.gpu, self.config.const):
                for cfg in cfg_list:
                    if cfg.enabled:
                        zones.update(cfg.ipmi_zone)
        return sorted(zones)

    def exit_func(self) -> None:
        """This function is called at exit (both on a normal service stop and when exceptions or runtime errors
        cannot be handled), and it applies the configured `[Ipmi] exit_level=` to all configured zones to avoid
        overheating while `smfc` is not running.

        What the fans are left under is platform-specific. On the FULL-mode platforms the BMC stays in FULL, so
        the exit level is what the fans keep; no mode change is needed, the BMC is in FULL already. On X14/H14
        `Platform.end()` also releases the manual mode latch or the global bypass, which hands the fans back to
        the BMC's own curve within about a second - so there the exit level is only a transition."""
        # Stop the exporter first so no /snapshot request can race with the BMC access below.
        if getattr(self, "exporter", None) is not None:
            try:
                self.exporter.stop()
            except Exception:  # pylint: disable=broad-except
                pass
        # Configure fans. The configuration is always loaded before the Ipmi instance is created, so both
        # attributes are present together in practice.
        if hasattr(self, "ipmi") and hasattr(self, "config"):
            level = self.config.ipmi.exit_level
            zones = self._exit_zones()
            # `end()` is called unconditionally, `exit_level=-1` included. It is not only a fan level write:
            # on X14/H14 it also releases the manual mode latch or the global bypass, and a platform state
            # that is never released leaves the fans frozen at their last duty with nothing regulating them.
            # The level itself is applied by `Platform.end()` only when it is not -1.
            # An ipmitool failure must not turn into a traceback during interpreter shutdown.
            try:
                self.ipmi.platform.end(zones, level)
                if hasattr(self, "log"):
                    if level != Config.EXIT_LEVEL_NONE and zones:
                        self.log.msg(Log.LOG_INFO, f"smfc terminated: fans set to {level}% in zone(s) {zones}.")
                    else:
                        reason = "no IPMI zone was controlled" if not zones else f"{Config.CV_IPMI_EXIT_LEVEL}=-1"
                        self.log.msg(Log.LOG_INFO, f"smfc terminated: fan levels left unchanged ({reason}), "
                                                   f"BMC fan control state released.")
            except Exception as e:  # pylint: disable=broad-except
                if hasattr(self, "log"):
                    self.log.msg(Log.LOG_ERROR, "Error while applying the exit fan level or releasing "
                                                f"BMC fan control: {e}")

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
            if fc.deferred_apply and fc.last_level > 0:
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

    def _check_fan_mode(self) -> None:
        """Ask the platform whether smfc is still in control of the fans, cache the observed BMC fan mode, and
        react when control was lost.

        What "in control" means is platform-specific: FULL fan mode on most Supermicro boards, latched per-zone
        manual mode on X14. When `enforce_fan_mode` is enabled (default), a lost control state is re-acquired
        and all cached per-zone levels are re-applied (some BMC firmwares reset zone levels when the mode
        changes). When it is disabled, a lost control state triggers a clean exit with code 11.

        A state that could not be read at all is reported by the platform as lost but unconfirmed: smfc still
        tries to re-acquire (an unreachable BMC makes those writes fail too, and the next loop iteration is the
        retry), but nothing was observed to drift, so it is neither counted as an enforcement nor a reason to
        exit.
        """
        status = self.ipmi.platform.check_fan_mode(self.controlled_zones)
        if status.fan_mode != -1:
            self.last_fan_mode = status.fan_mode
            self.last_fan_mode_at = time.monotonic()

        if status.state == ControlState.OK:
            return

        if not self.config.ipmi.enforce_fan_mode:
            if status.confirmed:
                self.log.msg(Log.LOG_ERROR, f"{status.detail}; enforce_fan_mode is disabled, smfc exiting.")
                sys.exit(11)
            self.log.msg(Log.LOG_ERROR, status.detail)
            return

        if status.confirmed:
            self.fan_mode_enforced_count += 1
            self.log.msg(Log.LOG_INFO, f"{status.detail}; restoring fan control.")
        else:
            self.log.msg(Log.LOG_ERROR, status.detail)
        try:
            if self.ipmi.platform.start(self.controlled_zones):
                self.last_fan_mode = Ipmi.FULL_MODE
                self.last_fan_mode_at = time.monotonic()
                time.sleep(self.config.ipmi.fan_mode_delay)
            for zone, level in self.applied_levels.items():
                self.ipmi.set_fan_level(zone, level)
        except (RuntimeError, ValueError) as e:
            # Recovery itself failed transiently; the next loop iteration will try again.
            self.log.msg(Log.LOG_ERROR, f"Fan mode recovery failed: {e}")

    def _start_exporter(self) -> None:
        """Build and start the HTTP exporter; tolerate bind failures.

        Stores the live `Exporter` on `self.exporter`, or `None` if bind failed.
        """
        self.exporter = None
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, "HTTP Exporter was initialized with:")
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_EXPORTER_BIND_ADDRESS} = {self.config.exporter.bind_address}")
            self.log.msg(Log.LOG_CONFIG, f"   {Config.CV_EXPORTER_PORT} = {self.config.exporter.port}")
        try:
            self.exporter = Exporter(
                log=self.log,
                bind_address=self.config.exporter.bind_address,
                port=self.config.exporter.port,
                snapshot_fn=lambda: build_snapshot(self),
            )
            self.exporter.start()
        except OSError as e:
            self.log.msg(Log.LOG_ERROR, f"Exporter failed to start ({e}); continuing without it.")
            self.exporter = None

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
        parser.add_argument("-ne", action="store_true", default=False,
                            help="deprecated, use [Ipmi] exit_level=-1 instead")
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
        11 - fan mode changed from FULL
        """

        # Parse command line arguments.
        parsed_results = self._parse_args()

        # Register the exit function for service termination. `atexit` handlers do not run when the process is
        # terminated by SIGTERM (systemd's default kill signal), so SIGTERM is translated to a normal interpreter
        # shutdown. SIGINT already behaves that way through KeyboardInterrupt.
        atexit.register(self.exit_func)
        signal.signal(signal.SIGTERM, self._sigterm_handler)

        # Store `sudo` option.
        self.sudo = parsed_results.s

        # Record service start time and reset the fan-mode enforcement counter (exposed via /metrics).
        self.start_time = time.time()
        self.fan_mode_enforced_count = 0

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
            level_str = Log.level_to_str(self.log.log_level)
            output_str = Log.output_to_str(self.log.log_output)
            self.log.msg(Log.LOG_CONFIG, "Logging was initialized with:")
            self.log.msg(Log.LOG_CONFIG, f"   log_level = {self.log.log_level} ({level_str})")
            self.log.msg(Log.LOG_CONFIG, f"   log_output = {self.log.log_output} ({output_str})")

        # Parse and load configuration file.
        try:
            self.config = Config(parsed_results.config_file)
        except (FileNotFoundError, ValueError) as e:
            self.log.msg(Log.LOG_ERROR, f"Configuration error: {e}")
            sys.exit(6)
        self.log.msg(Log.LOG_DEBUG, f"Configuration file ({parsed_results.config_file}) loaded")

        # The deprecated `-ne` option is still honored (it is equivalent to `exit_level=-1`) but it will be
        # removed in a future release.
        if parsed_results.ne:
            self.log.msg(Log.LOG_ERROR, "WARNING: the -ne option is deprecated, "
                                        "use the [Ipmi] exit_level=-1 configuration parameter instead.")
            self.config.ipmi.exit_level = Config.EXIT_LEVEL_NONE

        # Check run-time dependencies (commands, kernel modules) if `-nd` command line option is not specified.
        if not parsed_results.nd:
            error_msg = self.check_dependencies()
            if error_msg:
                self.log.msg(Log.LOG_ERROR, error_msg)
                sys.exit(7)

        # Create an Ipmi class instance.
        try:
            self.ipmi = Ipmi(self.log, self.config.ipmi, self.sudo)
            self.last_fan_mode = self.ipmi.get_fan_mode()
            self.last_fan_mode_at = time.monotonic()
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            self.log.msg(Log.LOG_ERROR, f"{e}.")
            sys.exit(8)
        # Log the old fan mode and zone levels in DEBUG log mode.
        if self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, f"Old IPMI fan mode = "
                                        f"{self.ipmi.get_fan_mode_name(self.last_fan_mode)} ({self.last_fan_mode})")
            configured_zones: Set[int] = set()
            for cfg_list in (self.config.cpu, self.config.hd, self.config.nvme,
                             self.config.gpu, self.config.const):
                for cfg in cfg_list:
                    if cfg.enabled:
                        configured_zones.update(cfg.ipmi_zone)
            for zone in sorted(configured_zones):
                self.log.msg(Log.LOG_DEBUG, f"Old level in IPMI zone {zone} = {self.ipmi.get_fan_level(zone)}%")
        # Acquire fan control. What that means is platform-specific: most Supermicro boards are switched into
        # FULL fan mode (and only if they are not in FULL already - skipping the redundant write avoids a
        # needless fan_mode_delay sleep and the momentary fan blip some firmware produces when FULL is
        # re-latched), while X14 latches its per-zone manual mode instead. The BMC readiness gate in
        # Ipmi.__init__ waits out the cold-boot settling window, so the state the platform observes here is a
        # settled one. Runtime drift is still caught by _check_fan_mode().
        try:
            if self.ipmi.platform.start(self._exit_zones()):
                self.last_fan_mode = Ipmi.FULL_MODE
                self.last_fan_mode_at = time.monotonic()
                self.log.msg(Log.LOG_DEBUG, f"Set IPMI fan mode = {self.ipmi.get_fan_mode_name(Ipmi.FULL_MODE)}")
                time.sleep(self.config.ipmi.fan_mode_delay)
        except (RuntimeError, ValueError) as e:
            self.log.msg(Log.LOG_ERROR, f"{e}.")
            sys.exit(8)

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
        for cfg in self.config.hd:
            if cfg.enabled:
                self.log.msg(Log.LOG_DEBUG, f"HD fan controller [{cfg.section}] enabled")
                self.controllers.append(HdFc(self.log, self.udevc, self.ipmi, cfg, self.sudo))
        for cfg in self.config.nvme:
            if cfg.enabled:
                self.log.msg(Log.LOG_DEBUG, f"NVME fan controller [{cfg.section}] enabled")
                self.controllers.append(NvmeFc(self.log, self.udevc, self.ipmi, cfg))
        for cfg in self.config.gpu:
            if cfg.enabled:
                self.log.msg(Log.LOG_DEBUG, f"GPU fan controller [{cfg.section}] enabled")
                self.controllers.append(GpuFc(self.log, self.ipmi, cfg))
        for cfg in self.config.const:
            if cfg.enabled:
                self.log.msg(Log.LOG_DEBUG, f"CONST fan controller [{cfg.section}] enabled")
                self.controllers.append(ConstFc(self.log, self.ipmi, cfg))

        # If none of the fan controllers is enabled.
        if not self.controllers:
            self.log.msg(Log.LOG_ERROR, "None of the fan controllers are enabled, service terminated.")
            sys.exit(10)

        # Cache the controlled zone list: _check_fan_mode() needs it on every poll and it cannot change while
        # the service runs.
        self.controlled_zones = self._exit_zones()

        # Check for shared IPMI zones and enable deferred apply only for affected controllers.
        self.shared_zones = self._check_shared_zones()
        if self.shared_zones:
            for fc in self.controllers:
                if set(fc.config.ipmi_zone) & self.shared_zones:
                    fc.deferred_apply = True

        # Calculate the wait time in the main loop.
        wait = min(fc.config.polling for fc in self.controllers) / 2
        self.log.msg(Log.LOG_DEBUG, f"Main loop sleep time = {wait} sec")

        # Start the HTTP exporter if enabled (smfc-client + Prometheus). Bind failure is logged
        # and the daemon continues — fan-control behavior must not be gated on the listener.
        if self.config.exporter.enabled:
            self._start_exporter()

        # Main execution loop.
        while True:
            # A BMC or ipmitool failure while applying fan levels - a transient rejection, an unreachable
            # BMC, or an `ipmitool_timeout` expiry on a wedged /dev/ipmi0 - must not terminate the daemon.
            # Only IpmiError is caught, deliberately: a controller fault (a vanished sensor, a bad value) is
            # not an IPMI problem, and it still terminates the service as it always has.
            # Exiting would leave the fans wherever they happen to be with nothing regulating them, which is
            # strictly worse than staying up and retrying: the BMC may come back, and _check_fan_mode()
            # re-acquires control if it was lost meanwhile. The iteration is abandoned, not the service.
            try:
                for fc in self.controllers:
                    fc.run()
                    # Record applied levels for non-deferred controllers so every zone shows up in the
                    # snapshot. Deferred controllers (shared zones) are recorded by _apply_fan_levels().
                    if not fc.deferred_apply:
                        for zone in fc.config.ipmi_zone:
                            self.applied_levels[zone] = fc.last_level
                if self.shared_zones:
                    self._apply_fan_levels()
            except IpmiError as e:
                self.log.msg(Log.LOG_ERROR, f"Fan level update failed: {e}")
            self._check_fan_mode()
            time.sleep(wait)


# End.
