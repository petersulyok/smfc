#
#   client.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc-client: read-only one-shot snapshot of smfc-managed state.
#
import argparse
import json
import sys
import urllib.error
import urllib.request
from importlib.metadata import version
from typing import Any, Dict, List, Optional, Tuple, Union
from pyudev import Context
from smfc.config import Config, ExporterConfig
from smfc.constfc import ConstFc
from smfc.cpufc import CpuFc
from smfc.fancontroller import FanController
from smfc.gpufc import GpuFc
from smfc.hdfc import HdFc
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.nvmefc import NvmeFc


# Exit codes (aligned with the service: 6=config, 8=ipmi, 9=udev).
EXIT_OK: int = 0
EXIT_CONFIG_ERROR: int = 6
EXIT_IPMI_ERROR: int = 8
EXIT_UDEV_ERROR: int = 9

# BMC init timeout for the client (default service uses 120 s).
CLIENT_BMC_INIT_TIMEOUT: float = 5.0

# Snapshot fetch timeout (used when the exporter is enabled in config).
SNAPSHOT_FETCH_TIMEOUT: float = 1.0

# Default configuration file path (matches systemd unit).
DEFAULT_CONFIG_PATH: str = "/etc/smfc/smfc.conf"

# ANSI escape sequences.
BOLD: str = "\x1b[1m"
DIM: str = "\x1b[2m"
GREEN: str = "\x1b[32m"
RED: str = "\x1b[31m"
RESET: str = "\x1b[0m"

# Type alias for a controller entry: (section_name, type_label, controller_or_None, error_or_None).
ControllerEntry = Tuple[str, str, Optional[Union[FanController, ConstFc]], Optional[str]]


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for smfc-client.
    Args:
        argv (Optional[List[str]]): argument list (None = sys.argv[1:])
    Returns:
        argparse.Namespace: parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="smfc-client",
        description="Print a one-shot snapshot of smfc-managed fans and temperatures. "
                    "Reads /snapshot from the smfc service when [Exporter] is enabled in the "
                    "config; otherwise (or with --standalone) reads sensors directly.",
        epilog="Exit codes: 0=ok  6=config error  8=ipmi error  9=udev error",
    )
    parser.add_argument("-c", "--config", action="store", dest="config_file", default=DEFAULT_CONFIG_PATH,
                        metavar="FILE", help=f"configuration file (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("-s", "--sudo", action="store_true", default=False,
                        help="run ipmitool and smartctl with sudo")
    parser.add_argument("-nc", "--no-color", action="store_true", default=False,
                        dest="no_color", help="disable ANSI colors in output")
    parser.add_argument("-V", "--verbose", action="store_true", default=False,
                        help="show per-device temperatures")
    parser.add_argument("--standalone", action="store_true", default=False, dest="standalone",
                        help="bypass the smfc service and read sensors directly")
    parser.add_argument("-v", "--version", action="version", version="%(prog)s " + version("smfc"))
    return parser.parse_args(argv)


def _build_silent_log() -> Log:
    """Build a Log instance that suppresses all output (used to silence Ipmi/controller __init__ chatter).
    Returns:
        Log: a silent Log instance routed to stderr
    """
    return Log(Log.LOG_NONE, Log.LOG_STDERR)


def _use_color(no_color_flag: bool) -> bool:
    """Decide whether ANSI colors should be emitted.
    Args:
        no_color_flag (bool): user-supplied --no-color flag
    Returns:
        bool: True when colors should be emitted
    """
    if no_color_flag:
        return False
    try:
        return bool(sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def _wrap(text: str, color: str, enabled: bool) -> str:
    """Wrap text with an ANSI color sequence when enabled.
    Args:
        text (str): text to wrap
        color (str): ANSI color escape sequence
        enabled (bool): whether colors are enabled
    Returns:
        str: optionally wrapped text
    """
    if not enabled or not color:
        return text
    return f"{color}{text}{RESET}"


def _construct_controllers(log: Log, cfg: Config, ipmi: Ipmi, udevc: Optional[Context],
                           sudo: bool) -> List[ControllerEntry]:
    """Iterate enabled fan controller configs and instantiate each in a passive way.
    Each controller construction is wrapped in try/except so a failure on one controller
    (e.g. missing device) does not abort the whole report.
    Args:
        log (Log): a (silent) Log instance
        cfg (Config): parsed configuration
        ipmi (Ipmi): an Ipmi instance (read-only)
        udevc (Optional[Context]): pyudev Context, shared across controllers that need it
        sudo (bool): sudo flag (passed to HdFc)
    Returns:
        List[ControllerEntry]: list of (section, type_label, controller, error) tuples
    """
    entries: List[ControllerEntry] = []

    for cpu_cfg in cfg.cpu:
        if not cpu_cfg.enabled:
            continue
        try:
            controller = CpuFc(log, udevc, ipmi, cpu_cfg)
            entries.append((cpu_cfg.section, "cpu", controller, None))
        except Exception as e:  # pylint: disable=broad-except
            entries.append((cpu_cfg.section, "cpu", None, str(e)))

    for hd_cfg in cfg.hd:
        if not hd_cfg.enabled:
            continue
        try:
            controller = HdFc(log, udevc, ipmi, hd_cfg, sudo)
            entries.append((hd_cfg.section, "hd", controller, None))
        except Exception as e:  # pylint: disable=broad-except
            entries.append((hd_cfg.section, "hd", None, str(e)))

    for nvme_cfg in cfg.nvme:
        if not nvme_cfg.enabled:
            continue
        try:
            controller = NvmeFc(log, udevc, ipmi, nvme_cfg)
            entries.append((nvme_cfg.section, "nvme", controller, None))
        except Exception as e:  # pylint: disable=broad-except
            entries.append((nvme_cfg.section, "nvme", None, str(e)))

    for gpu_cfg in cfg.gpu:
        if not gpu_cfg.enabled:
            continue
        try:
            controller = GpuFc(log, ipmi, gpu_cfg)
            entries.append((gpu_cfg.section, "gpu", controller, None))
        except Exception as e:  # pylint: disable=broad-except
            entries.append((gpu_cfg.section, "gpu", None, str(e)))

    for const_cfg in cfg.const:
        if not const_cfg.enabled:
            continue
        try:
            controller = ConstFc(log, ipmi, const_cfg)
            entries.append((const_cfg.section, "const", controller, None))
        except Exception as e:  # pylint: disable=broad-except
            entries.append((const_cfg.section, "const", None, str(e)))

    return entries


def _safe_temp_str(controller: Union[FanController, ConstFc, None], type_label: str) -> str:
    """Read fresh temperature from a controller, gracefully handling errors.
    Args:
        controller: controller instance (or None)
        type_label (str): controller type label
    Returns:
        str: formatted temperature string (e.g. "42.3 C", "ERROR", "-")
    """
    if controller is None:
        return "-"
    if type_label == "const":
        return "-"
    try:
        temp = controller.get_temp()
        return f"{temp:.1f} C"
    except Exception:  # pylint: disable=broad-except
        return "ERROR"


def _safe_nth_temp_str(controller: Union[FanController, None], index: int) -> str:
    """Read a single per-device temperature via the controller's _get_nth_temp(), formatted defensively.
    Args:
        controller: controller instance (or None)
        index (int): device index in the controller's hwmon/device list
    Returns:
        str: formatted temperature string (e.g. "42.3 C", "ERROR", "-")
    """
    if controller is None:
        return "-"
    try:
        # pylint: disable=protected-access
        return f"{controller._get_nth_temp(index):.1f} C"
    except Exception:  # pylint: disable=broad-except
        return "ERROR"


def _safe_zone_level(ipmi: Ipmi, zone: int) -> str:
    """Read the current fan level for an IPMI zone, returning a friendly string on failure.
    Args:
        ipmi (Ipmi): Ipmi instance
        zone (int): IPMI zone id
    Returns:
        str: formatted level string (e.g. "55 %", "ERROR")
    """
    try:
        return f"{ipmi.get_fan_level(zone):3d} %"
    except Exception:  # pylint: disable=broad-except
        return "ERROR"


def _format_controllers_table(entries: List[ControllerEntry], ipmi: Ipmi, use_color: bool) -> List[str]:
    """Format the Controllers table.
    Args:
        entries (List[ControllerEntry]): controllers
        ipmi (Ipmi): Ipmi instance
        use_color (bool): whether to emit ANSI colors
    Returns:
        List[str]: list of output lines
    """
    lines: List[str] = []
    lines.append(_wrap("Controllers", BOLD, use_color))
    header = f"  {'Section':<10}{'Type':<8}{'Zones':<10}{'Devices':<9}{'Temp':<10}Level"
    sep = f"  {'-' * 8:<10}{'-' * 6:<8}{'-' * 8:<10}{'-' * 7:<9}{'-' * 8:<10}{'-' * 6}"
    lines.append(header)
    lines.append(sep)
    for section, type_label, controller, error in entries:
        if controller is None:
            # Construction failed: only Section and Type are known, so let the error message
            # run free from the Zones column to the end of the line.
            err_cell = _wrap(f"ERROR: {error}", RED, use_color)
            lines.append(f"  {section:<10}{type_label:<8}{err_cell}")
            continue
        zones_str = str(controller.config.ipmi_zone)
        count = getattr(controller, "count", None)
        if type_label == "const":
            devices_str = "-"
            temp_str = "-"
            level_str = f"{controller.config.level:3d} %"
        else:
            devices_str = str(count) if count is not None else "-"
            temp_str = _safe_temp_str(controller, type_label)
            # Level: use the first zone (controllers usually own a single zone or share).
            first_zone = controller.config.ipmi_zone[0] if controller.config.ipmi_zone else None
            level_str = _safe_zone_level(ipmi, first_zone) if first_zone is not None else "-"
        lines.append(f"  {section:<10}{type_label:<8}{zones_str:<10}{devices_str:<9}{temp_str:<10}{level_str}")
    return lines


def _format_zones_table(entries: List[ControllerEntry], ipmi: Ipmi, use_color: bool) -> List[str]:
    """Format the live IPMI zone level table (union of zones across enabled controllers).
    Args:
        entries (List[ControllerEntry]): controllers
        ipmi (Ipmi): Ipmi instance
        use_color (bool): whether to emit ANSI colors
    Returns:
        List[str]: list of output lines
    """
    lines: List[str] = []
    zones: List[int] = []
    for _section, _type_label, controller, _error in entries:
        if controller is None:
            continue
        for z in controller.config.ipmi_zone:
            if z not in zones:
                zones.append(z)
    if not zones:
        return lines
    zones.sort()
    lines.append(_wrap("IPMI zones (live)", BOLD, use_color))
    lines.append(f"  {'Zone':<8}Level")
    lines.append(f"  {'-' * 6:<8}-----")
    for z in zones:
        lines.append(f"  {z:<8}{_safe_zone_level(ipmi, z)}")
    return lines


def _format_devices_table(rows: List[Tuple[str, str, str]], use_color: bool) -> List[str]:
    """Format a Devices table. Each row is (section, device-name, temp-string).

    Both the online (snapshot) and standalone paths build the same row tuples and share this
    renderer to keep verbose output consistent regardless of source.

    Args:
        rows (List[Tuple[str, str, str]]): per-device rows (section, name, temp_str)
        use_color (bool): whether to emit ANSI colors

    Returns:
        List[str]: list of output lines (empty when rows is empty)
    """
    if not rows:
        return []
    # Width the Device column to the longest device name so /dev/disk/by-id/... paths line up.
    name_w = max(len("Device"), max(len(r[1]) for r in rows))
    lines: List[str] = []
    lines.append(_wrap("Devices", BOLD, use_color))
    lines.append(f"  {'Section':<10}{'Device':<{name_w + 2}}Temp")
    lines.append(f"  {'-' * 8:<10}{'-' * name_w:<{name_w + 2}}-----")
    for section, name, temp_str in rows:
        lines.append(f"  {section:<10}{name:<{name_w + 2}}{temp_str}")
    return lines


def _format_standby_section(entries: List[ControllerEntry], use_color: bool) -> List[str]:
    """Format the Standby Guard section, when at least one HD controller has it enabled.
    Args:
        entries (List[ControllerEntry]): controllers
        use_color (bool): whether to emit ANSI colors
    Returns:
        List[str]: list of output lines (empty when no eligible HD controller)
    """
    lines: List[str] = []
    for section, type_label, controller, _error in entries:
        if type_label != "hd" or controller is None:
            continue
        cfg = controller.config
        if not (cfg.standby_guard_enabled and getattr(controller, "count", 0) > 1):
            continue
        states = getattr(controller, "standby_array_states", None)
        if states is None:
            continue
        title = f"Standby Guard ([{section}], standby_hd_limit={cfg.standby_hd_limit})"
        lines.append(_wrap(title, BOLD, use_color))
        for i, name in enumerate(controller.hd_device_names):
            if i >= len(states):
                break
            if states[i]:
                state_str = _wrap("STANDBY", DIM, use_color)
            else:
                state_str = _wrap("ACTIVE", GREEN, use_color)
            lines.append(f"  {name}  {state_str}")
        try:
            arr_str = controller.get_standby_state_str()
            standby_count = states.count(True)
            lines.append(f"  Array state: {arr_str}  ({standby_count}/{controller.count} standby)")
        except Exception:  # pylint: disable=broad-except
            pass
    return lines


def _format_report(ipmi: Ipmi, entries: List[ControllerEntry], config_path: str, use_color: bool,
                   verbose: bool = False) -> str:
    """Build the full snapshot report (standalone path: reads ipmitool/smartctl directly).
    Args:
        ipmi (Ipmi): Ipmi instance
        entries (List[ControllerEntry]): controllers
        config_path (str): path to the loaded configuration file
        use_color (bool): whether to emit ANSI colors
        verbose (bool): whether to include the per-device Devices section
    Returns:
        str: full report text
    """
    pkg_version = version("smfc")
    lines: List[str] = []
    banner = _wrap(f"smfc-client {pkg_version}", BOLD, use_color)
    lines.append(banner)
    lines.append(_wrap(f"    config: {config_path}", DIM, use_color))
    lines.append(_format_source_line(online=False, use_color=use_color))
    lines.append("")

    # BMC section
    lines.append(_wrap("BMC", BOLD, use_color))
    lines.append(f"  Manufacturer  : {ipmi.bmc_manufacturer_name} ({ipmi.bmc_manufacturer_id})")
    lines.append(f"  Product       : {ipmi.bmc_product_name} ({ipmi.bmc_product_id})")
    lines.append(f"  Firmware      : {ipmi.bmc_firmware_rev}")
    lines.append(f"  IPMI version  : {ipmi.bmc_ipmi_version}")
    lines.append(f"  Platform      : {ipmi.platform.name} ({type(ipmi.platform).__name__})")
    # Fan mode (live read) closes the BMC block.
    try:
        mode = ipmi.get_fan_mode()
        mode_name = Ipmi.get_fan_mode_name(mode)
        if mode == int(Ipmi.FULL_MODE):
            mode_str = _wrap(mode_name, GREEN, use_color)
            lines.append(f"  Fan mode      : {mode_str} ({mode})")
        else:
            mode_str = _wrap(mode_name, RED, use_color)
            warn = _wrap("  ! not in FULL mode - smfc may not be controlling the fans", RED, use_color)
            lines.append(f"  Fan mode      : {mode_str} ({mode}){warn}")
    except Exception as e:  # pylint: disable=broad-except
        err_str = _wrap(f"ERROR: {e}", RED, use_color)
        lines.append(f"  Fan mode      : {err_str}")
    lines.append("")

    # Controllers table
    lines.extend(_format_controllers_table(entries, ipmi, use_color))
    lines.append("")

    # Per-device temperatures (verbose only). Standalone path issues one _get_nth_temp() per
    # device, so this section adds a smartctl/nvidia-smi call per device — gated behind --verbose.
    if verbose:
        device_rows: List[Tuple[str, str, str]] = []
        for section, type_label, controller, _error in entries:
            if controller is None or type_label == "const":
                continue
            try:
                names = controller.device_names()
            except Exception:  # pylint: disable=broad-except
                names = []
            for i, name in enumerate(names):
                device_rows.append((section, name, _safe_nth_temp_str(controller, i)))
        device_lines = _format_devices_table(device_rows, use_color)
        if device_lines:
            lines.extend(device_lines)
            lines.append("")

    # Live IPMI zones
    zone_lines = _format_zones_table(entries, ipmi, use_color)
    if zone_lines:
        lines.extend(zone_lines)
        lines.append("")

    # Standby Guard
    standby_lines = _format_standby_section(entries, use_color)
    if standby_lines:
        lines.extend(standby_lines)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _format_source_line(online: bool, use_color: bool) -> str:
    """Render the tabbed "source:" line printed below the banner.

    Args:
        online (bool): True if the snapshot came from the smfc service exporter.
        use_color (bool): whether to emit ANSI colors.

    Returns:
        str: the formatted line (without trailing newline).
    """
    label = "smfc service (live snapshot)" if online else "ipmitool (smfc service is not reachable)"
    return _wrap(f"    source: {label}", DIM, use_color)


def _format_uptime(seconds: float) -> str:
    """Format an uptime duration as 'Nd HH:MM:SS' (the day field is omitted when zero).
    Args:
        seconds (float): elapsed time in seconds
    Returns:
        str: human-friendly duration string
    """
    secs = int(max(0.0, seconds))
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{hours:02d}:{minutes:02d}:{sec:02d}"


def _try_fetch_snapshot(exporter_cfg: ExporterConfig,
                        timeout: float = SNAPSHOT_FETCH_TIMEOUT) -> Optional[Dict[str, Any]]:
    """Attempt to fetch /snapshot from the smfc service exporter.

    Args:
        exporter_cfg (ExporterConfig): exporter section of the config (read for bind_address/port).
        timeout (float): per-request timeout in seconds.

    Returns:
        Optional[Dict[str, Any]]: parsed snapshot dict on HTTP 200, or None on any failure
            (connection refused, timeout, non-200 status, malformed JSON).
    """
    # Pick a host string the urllib will accept: 0.0.0.0 / :: aren't valid client addresses,
    # so when the service binds to those, talk to localhost instead.
    host = exporter_cfg.bind_address
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    url = f"http://{host}:{exporter_cfg.port}/snapshot"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = resp.read()
        snapshot = json.loads(data.decode("utf-8"))
        if not isinstance(snapshot, dict):
            return None
        return snapshot
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
        return None


def _format_report_from_snapshot(snapshot: Dict[str, Any], config_path: str, use_color: bool,
                                 verbose: bool = False) -> str:
    """Build the full report from a snapshot dict served by the smfc exporter.

    The output mirrors the standalone path's structure (banner, BMC, IPMI fan mode, Controllers
    table, IPMI zones, Standby Guard) but is built from already-cached state — no ipmitool
    subprocesses, no smartctl, no controller instantiation. The data source is identified by the
    `source: smfc service (live snapshot)` line below the banner.

    Args:
        snapshot (Dict[str, Any]): parsed snapshot dict from the exporter's /snapshot endpoint.
        config_path (str): path to the loaded configuration file.
        use_color (bool): whether to emit ANSI colors.
        verbose (bool): whether to include the per-device Devices section.

    Returns:
        str: full report text (with a trailing newline).
    """
    lines: List[str] = []
    pkg_version = snapshot.get("smfc_version", version("smfc"))
    banner = _wrap(f"smfc-client {pkg_version}", BOLD, use_color)
    lines.append(banner)
    lines.append(_wrap(f"    config: {config_path}", DIM, use_color))
    lines.append(_format_source_line(online=True, use_color=use_color))
    # Service uptime (online only): the daemon tracks start_time; the snapshot carries generated_at.
    start_time = float(snapshot.get("start_time", 0.0) or 0.0)
    generated_at = float(snapshot.get("generated_at", 0.0) or 0.0)
    if start_time and generated_at >= start_time:
        lines.append(_wrap(f"    uptime: {_format_uptime(generated_at - start_time)}", DIM, use_color))
    lines.append("")

    # BMC section.
    bmc = snapshot.get("bmc", {}) or {}
    lines.append(_wrap("BMC", BOLD, use_color))
    lines.append(f"  Manufacturer  : {bmc.get('manufacturer_name', '?')} ({bmc.get('manufacturer_id', '?')})")
    lines.append(f"  Product       : {bmc.get('product_name', '?')} ({bmc.get('product_id', '?')})")
    lines.append(f"  Firmware      : {bmc.get('firmware_rev', '?')}")
    lines.append(f"  IPMI version  : {bmc.get('ipmi_version', '?')}")
    lines.append(f"  Platform      : {bmc.get('platform_name', '?')} ({bmc.get('platform_class', '?')})")
    # Fan mode (service-cached) closes the BMC block. It is always FULL when smfc is running with
    # enforce_fan_mode=true; the exporter served whatever was cached on the loop's last poll.
    fan_mode = snapshot.get("fan_mode", {}) or {}
    mode_id = fan_mode.get("id", -1)
    mode_name = fan_mode.get("name", "?")
    mode_color = GREEN if mode_id == int(Ipmi.FULL_MODE) else RED
    enforced = int(snapshot.get("fan_mode_enforced_count", 0) or 0)
    age_s = float(fan_mode.get("age_s", 0.0) or 0.0)
    detail = _wrap(f"  (enforced {enforced}x, read {age_s:.1f}s ago)", DIM, use_color)
    lines.append(f"  Fan mode      : {_wrap(str(mode_name), mode_color, use_color)} ({mode_id}){detail}")
    lines.append("")

    # Controllers table.
    controllers = snapshot.get("fan_controllers", []) or []
    lines.append(_wrap("Controllers", BOLD, use_color))
    header = f"  {'Section':<10}{'Type':<8}{'Zones':<10}{'Devices':<9}{'Temp':<10}Level"
    sep = f"  {'-' * 8:<10}{'-' * 6:<8}{'-' * 8:<10}{'-' * 7:<9}{'-' * 8:<10}{'-' * 6}"
    lines.append(header)
    lines.append(sep)
    zones = snapshot.get("zones", {}) or {}
    for c in controllers:
        section = c.get("section", "?")
        type_label = c.get("type", "?")
        ipmi_zones = c.get("ipmi_zones", []) or []
        zones_str = str(ipmi_zones) if ipmi_zones else "-"
        if type_label == "const":
            devices_str = "-"
            temp_str = "-"
            level_str = f"{int(c.get('target_level_pct', c.get('last_level_pct', 0))):3d} %"
        else:
            devices_str = str(int(c.get("device_count", 0)))
            temp_str = f"{float(c.get('last_temp_c', 0.0)):.1f} C"
            first_zone = ipmi_zones[0] if ipmi_zones else None
            zone_info = zones.get(str(first_zone), {}) if first_zone is not None else {}
            level = zone_info.get("applied_level_pct")
            level_str = f"{int(level):3d} %" if level is not None else f"{int(c.get('last_level_pct', 0)):3d} %"
        lines.append(f"  {section:<10}{type_label:<8}{zones_str:<10}{devices_str:<9}{temp_str:<10}{level_str}")
    lines.append("")

    # Per-device temperatures (verbose only). Pulled from the snapshot's `devices` array — the
    # service has already cached them on the loop's last get_temp(); this path issues no
    # subprocesses (preserving the request-thread contract from CLIENT_SERVER.md).
    if verbose:
        device_rows: List[Tuple[str, str, str]] = []
        for c in controllers:
            if c.get("type") == "const":
                continue
            section = c.get("section", "?")
            for d in c.get("devices", []) or []:
                device_rows.append((section, str(d.get("name", "")), f"{float(d.get('temp_c', 0.0)):.1f} C"))
        device_lines = _format_devices_table(device_rows, use_color)
        if device_lines:
            lines.extend(device_lines)
            lines.append("")

    # IPMI zones (live) — applied levels straight from the snapshot.
    if zones:
        lines.append(_wrap("IPMI zones (live)", BOLD, use_color))
        lines.append(f"  {'Zone':<8}Level")
        lines.append(f"  {'-' * 6:<8}-----")
        for zone_str, info in sorted(zones.items(), key=lambda kv: int(kv[0])):
            level = info.get("applied_level_pct")
            level_fmt = f"{int(level):3d} %" if level is not None else "-"
            lines.append(f"  {zone_str:<8}{level_fmt}")
        lines.append("")

    # Standby Guard — show a section per HD controller that has it enabled.
    standby_lines: List[str] = []
    for c in controllers:
        if c.get("type") != "hd":
            continue
        sb = c.get("standby_guard") or {}
        if not sb.get("enabled"):
            continue
        section = c.get("section", "HD")
        device_names = [d.get("name", "") for d in (c.get("devices", []) or [])]
        states = sb.get("states", []) or []
        title = f"Standby Guard ([{section}], standby_hd_limit={sb.get('limit', 1)})"
        standby_lines.append(_wrap(title, BOLD, use_color))
        for i, name in enumerate(device_names):
            if i >= len(states):
                break
            state_str = (_wrap("STANDBY", DIM, use_color) if states[i]
                         else _wrap("ACTIVE", GREEN, use_color))
            standby_lines.append(f"  {name}  {state_str}")
        arr_str = sb.get("array_state", "")
        standby_count = sb.get("standby_count", sum(1 for s in states if s))
        if arr_str:
            standby_lines.append(f"  Array state: {arr_str}  ({standby_count}/{len(states)} standby)")
    if standby_lines:
        lines.extend(standby_lines)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the smfc-client console script.
    Args:
        argv (Optional[List[str]]): argument list (None = sys.argv[1:])
    Returns:
        int: process exit code
    """
    args = _parse_args(argv)

    # Load configuration.
    try:
        cfg = Config(args.config_file)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: config: {e}", file=sys.stderr, flush=True)
        return EXIT_CONFIG_ERROR

    use_color = _use_color(args.no_color)

    # Online path: when [Exporter] is enabled in config and --standalone wasn't passed,
    # try /snapshot first. On any failure (connection refused, timeout, malformed JSON),
    # transparently fall back to the standalone path below.
    if cfg.exporter.enabled and not args.standalone:
        snapshot = _try_fetch_snapshot(cfg.exporter)
        if snapshot is not None:
            report = _format_report_from_snapshot(snapshot, args.config_file, use_color, args.verbose)
            sys.stdout.write(report)
            sys.stdout.flush()
            return EXIT_OK

    # Standalone path: reach the BMC and disks directly.
    log = _build_silent_log()

    # Connect to IPMI in read-only mode with a short BMC timeout.
    try:
        ipmi = Ipmi(log, cfg.ipmi, args.sudo, in_client=True, bmc_init_timeout=CLIENT_BMC_INIT_TIMEOUT)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"ERROR: ipmi: {e}", file=sys.stderr, flush=True)
        # Tailor the hint to the failure: a missing binary needs installing, while an
        # execution error is most often a permissions problem on an existing ipmitool.
        if isinstance(e, FileNotFoundError):
            print("hint: ipmitool not found; install it or fix `ipmi_command=` in the config.",
                  file=sys.stderr, flush=True)
        elif isinstance(e, RuntimeError):
            print("hint: ipmitool typically requires root; try `sudo smfc-client -s`.",
                  file=sys.stderr, flush=True)
        return EXIT_IPMI_ERROR

    # Initialize udev (required by CPU/HD/NVME controllers; GPU and CONST do not need it).
    udevc: Optional[Context]
    try:
        udevc = Context()
    except (ImportError, OSError) as e:
        print(f"ERROR: udev: {e}", file=sys.stderr, flush=True)
        return EXIT_UDEV_ERROR

    entries = _construct_controllers(log, cfg, ipmi, udevc, args.sudo)
    report = _format_report(ipmi, entries, args.config_file, use_color, args.verbose)
    sys.stdout.write(report)
    sys.stdout.flush()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

# End.
