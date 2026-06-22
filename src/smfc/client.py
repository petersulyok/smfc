#
#   client.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc-client: read-only one-shot snapshot of smfc-managed state.
#
import argparse
import json
import os
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
YELLOW: str = "\x1b[33m"   # warm — upper 30 % of a controller's steering window
RED: str = "\x1b[31m"
CYAN: str = "\x1b[1;36m"   # bold cyan — section headers (BMC, Fan controllers, blocks, IPMI zones)
RESET: str = "\x1b[0m"

# Where the GREEN→YELLOW transition lands inside a steering window. 0.7 means the upper 30 % of
# the window is YELLOW ("warm, fans ramping"); below the threshold is GREEN ("working in range").
BAND_WARN_FRACTION: float = 0.7

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


def _display_device_name(name: str, type_label: str) -> str:
    """Shorten a device name for verbose display.

    HD and NVMe controllers store full /dev/disk/by-id/... paths to keep udev mappings stable
    across reboots; that's useful in config but noisy in the verbose block where every row
    repeats the same prefix. Strip to the basename for these two types so the per-device list
    stays scannable. CPU/GPU (and CONST) keep their synthesized labels unchanged.

    Args:
        name (str): the raw device name (path or label)
        type_label (str): controller type ("hd" / "nvme" / "cpu" / "gpu" / "const")

    Returns:
        str: display-friendly name
    """
    if type_label in ("hd", "nvme") and name:
        return os.path.basename(name)
    return name


def _band_color(value: float, lo: float, hi: float) -> str:
    """Return the ANSI escape for `value`'s band inside the steering window [lo, hi].

    Four bands, applied uniformly to temps and levels:
      - value <  lo                            → DIM    (below floor — idle)
      - lo <= value < lo + 0.7*(hi - lo)       → GREEN  (working in range)
      - upper 30 % of the window               → YELLOW (warm — fans ramping)
      - value >= hi                            → RED    (at/over ceiling — no headroom)

    Returns an empty string when the window is degenerate (hi <= lo) — callers render the
    default colour in that case. CONST controllers (level_min == level_max, no temp window)
    fall into this path on purpose, since they have no curve to be hot or cold against.

    Args:
        value (float): the metric to band (temperature C or level %)
        lo (float):    the configured floor of the window
        hi (float):    the configured ceiling of the window

    Returns:
        str: ANSI escape (DIM/GREEN/YELLOW/RED) or "" when the window is degenerate.
    """
    if hi <= lo:
        return ""
    if value < lo:
        return DIM
    if value >= hi:
        return RED
    if (value - lo) / (hi - lo) >= BAND_WARN_FRACTION:
        return YELLOW
    return GREEN


def _parse_temp_cell(cell: str) -> Optional[float]:
    """Parse a formatted temperature cell back to its numeric value.

    Cells render as e.g. "42.3 C", "-", "ERROR". Returns None for the non-numeric cases so
    callers can decide whether to skip colouring rather than band a sentinel.
    """
    if not cell or cell in ("-", "ERROR"):
        return None
    try:
        return float(cell.split()[0])
    except (ValueError, IndexError):
        return None


def _parse_level_cell(cell: str) -> Optional[float]:
    """Parse a formatted level cell back to its numeric value (mirror of _parse_temp_cell).

    Cells render as e.g. " 55 %", "-", "ERROR". Returns None for non-numeric cases.
    """
    if not cell or cell in ("-", "ERROR"):
        return None
    try:
        return float(cell.split()[0])
    except (ValueError, IndexError):
        return None


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
    lines.append(_wrap("Fan controllers", CYAN, use_color))
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
            temp_cell = f"{temp_str:<10}"
            level_cell = level_str
        else:
            devices_str = str(count) if count is not None else "-"
            temp_str = _safe_temp_str(controller, type_label)
            # Level: use the first zone (controllers usually own a single zone or share).
            first_zone = controller.config.ipmi_zone[0] if controller.config.ipmi_zone else None
            level_str = _safe_zone_level(ipmi, first_zone) if first_zone is not None else "-"
            # Pad first, THEN colour: ANSI escapes are zero-width on screen but real characters
            # in the string, so colouring before padding tears the table's grid. Parse the
            # *already-fetched* string back to a number for banding so we don't double the
            # ipmitool / smartctl call count just to colour the cell.
            temp_cell = f"{temp_str:<10}"
            level_cell = level_str
            cfg = controller.config
            t_now = _parse_temp_cell(temp_str)
            if t_now is not None:
                temp_cell = _wrap(temp_cell, _band_color(t_now, float(cfg.min_temp), float(cfg.max_temp)),
                                  use_color)
            l_now = _parse_level_cell(level_str)
            if l_now is not None:
                level_cell = _wrap(level_cell, _band_color(l_now, float(cfg.min_level), float(cfg.max_level)),
                                   use_color)
        lines.append(f"  {section:<10}{type_label:<8}{zones_str:<10}{devices_str:<9}{temp_cell}{level_cell}")
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
    lines.append(_wrap("IPMI zones (live)", CYAN, use_color))
    lines.append(f"  {'Zone':<8}Level")
    lines.append(f"  {'-' * 6:<8}-----")
    for z in zones:
        lines.append(f"  {z:<8}{_safe_zone_level(ipmi, z)}")
    return lines


def _format_controller_block(section: str, type_label: str, zones: List[int], polling: float, deferred: bool,
                             temp_min: float, temp_max: float, level_min: int, level_max: int,
                             last_temp_str: str, last_level_str: str,
                             devices: List[Tuple[str, str, Optional[str], str]],
                             standby: Optional[Tuple[int, str, int, int]],
                             use_color: bool) -> List[str]:
    """Format a single fan controller's verbose block (Proposal A).

    Each block is a self-contained view of one controller: header line with zone / polling /
    deferred flags, a steering-window line (T window → L window), the current temperature →
    current level pair, an optional Standby Guard line (HD only), and an indented per-device
    list with an optional STANDBY/ACTIVE column.

    Args:
        section (str): controller's section name (e.g. "CPU", "HD")
        type_label (str): short type label ("cpu", "hd", "nvme", "gpu")
        zones (List[int]): IPMI zones the controller drives
        polling (float): configured polling interval in seconds
        deferred (bool): whether deferred_apply is set on the controller
        temp_min (float): configured temperature window floor (C)
        temp_max (float): configured temperature window ceiling (C)
        level_min (int): configured level window floor (%)
        level_max (int): configured level window ceiling (%)
        last_temp_str (str): pre-formatted current temperature (e.g. "35.0 C", "ERROR")
        last_level_str (str): pre-formatted current level (e.g. "35 %", "ERROR")
        devices (List[Tuple[str, str, Optional[str], str]]): per-device rows
            (name, temp_str, state_str_or_None, temp_color_escape_or_empty). The temp colour
            arrives separately from temp_str so the formatter can pad the *visible* temp_str
            to the Temp-column width and wrap colour around the padded result — ANSI escapes
            are otherwise zero-width and would break alignment.
        standby (Optional[Tuple[int, str, int, int]]): HD standby guard info as
            (limit, array_state, standby_count, total) or None
        use_color (bool): whether to emit ANSI colors

    Returns:
        List[str]: list of output lines for this block (no trailing blank line)
    """
    lines: List[str] = []
    zones_str = str(zones) if zones else "[]"
    deferred_str = "yes" if deferred else "no"
    # Cyan-paint just the [SECTION] tag — it carries the navigational signal. The rest of the
    # header line (type, zones, polling, deferred) stays in default colour so the eye lands on
    # the section name first instead of the whole row.
    tag = _wrap(f"[{section}]", CYAN, use_color)
    lines.append(f"{tag}  {type_label}  zone(s)={zones_str}  polling={polling:.1f}s  "
                 f"deferred={deferred_str}")
    lines.append(f"  Window: T=[{temp_min:g}..{temp_max:g}]C → L=[{level_min}..{level_max}]%")
    lines.append(f"  Temp:   {last_temp_str}  →  Level: {last_level_str}")
    if standby is not None:
        limit, array_state, standby_count, total = standby
        lines.append(
            f"  Standby Guard: enabled (limit={limit})  Array: {array_state}  "
            f"({standby_count}/{total} standby)"
        )
    if devices:
        has_state = any(d[2] is not None for d in devices)
        name_w = max(len("Device"), max(len(d[0]) for d in devices))
        temp_w = 10  # matches the data-row format string below
        # The Devices subsection: a 'Devices:' lead-in, then column headers aligned to the data
        # rows (same 4-space indent, same column widths). 'State' is only shown for HD with
        # standby guard enabled — the data rows decide that with has_state.
        lines.append("  Devices:")
        if has_state:
            lines.append(f"    {'Device':<{name_w + 2}}{'Temp':<{temp_w}}State")
        else:
            lines.append(f"    {'Device':<{name_w + 2}}Temp")
        for name, temp_str, state_str, temp_color in devices:
            # Pad the visible temp_str to the column width, THEN wrap colour. ANSI escapes are
            # zero-width on screen but real characters in the string, so colouring before padding
            # over-pads and tears the grid.
            temp_cell = _wrap(f"{temp_str:<{temp_w}}", temp_color, use_color)
            if has_state:
                state_cell = state_str if state_str is not None else ""
                if state_cell == "STANDBY":
                    state_cell = _wrap("STANDBY", DIM, use_color)
                elif state_cell == "ACTIVE":
                    state_cell = _wrap("ACTIVE", GREEN, use_color)
                lines.append(f"    {name:<{name_w + 2}}{temp_cell}{state_cell}")
            else:
                lines.append(f"    {name:<{name_w + 2}}{temp_cell}")
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
    lines.append(_wrap(f"  config: {config_path}", DIM, use_color))
    lines.append(_format_source_line(online=False, use_color=use_color))
    lines.append("")

    # BMC section. Non-verbose mode shows only Product + Fan mode (the two lines that matter
    # for "is smfc running and on the right hardware?"); --verbose unfolds the full block with
    # Manufacturer / Firmware / IPMI version / Platform (factory class) sandwiched between them.
    lines.append(_wrap("BMC", CYAN, use_color))
    if verbose:
        lines.append(f"  Manufacturer  : {ipmi.bmc_manufacturer_name} ({ipmi.bmc_manufacturer_id})")
    lines.append(f"  Product       : {ipmi.bmc_product_name} ({ipmi.bmc_product_id})")
    if verbose:
        lines.append(f"  Firmware      : {ipmi.bmc_firmware_rev}")
        lines.append(f"  IPMI version  : {ipmi.bmc_ipmi_version}")
        # Platform shows the factory class only — the product name is already on the line above.
        lines.append(f"  Platform      : {type(ipmi.platform).__name__}")
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

    # Per-controller verbose blocks (Proposal A). One block per non-CONST controller, in the
    # order they appear in `entries`. Each block carries the controller's steering window,
    # current temp/level, optional Standby Guard line (HD only), and indented devices list.
    # The standalone path still issues one _get_nth_temp() per device — same cost as the old
    # flat Devices table — but groups them under their owning controller.
    if verbose:
        for section, type_label, controller, _error in entries:
            if controller is None or type_label == "const":
                continue
            cfg = controller.config
            try:
                names = list(controller.device_names())
            except Exception:  # pylint: disable=broad-except
                names = []
            # Build per-device rows. For HDs with standby guard enabled, fold the per-disk
            # STANDBY/ACTIVE annotation into the row's third element. CONST is filtered above.
            # The 4th tuple slot carries the temp colour: standby disks render DIM (stale read),
            # everything else gets banded against the controller's own steering window.
            states: List[bool] = []
            if type_label == "hd" and getattr(cfg, "standby_guard_enabled", False):
                states = list(getattr(controller, "standby_array_states", None) or [])
            dev_t_min = float(getattr(cfg, "min_temp", 0.0))
            dev_t_max = float(getattr(cfg, "max_temp", 0.0))
            device_rows: List[Tuple[str, str, Optional[str], str]] = []
            for i, name in enumerate(names):
                temp_str = _safe_nth_temp_str(controller, i)
                state_str: Optional[str] = None
                if states and i < len(states):
                    state_str = "STANDBY" if states[i] else "ACTIVE"
                if state_str == "STANDBY":
                    temp_color = DIM
                else:
                    t_dev = _parse_temp_cell(temp_str)
                    temp_color = _band_color(t_dev, dev_t_min, dev_t_max) if t_dev is not None else ""
                device_rows.append((_display_device_name(name, type_label), temp_str, state_str, temp_color))
            # Standby Guard summary line (HD only, when enabled and we have a usable state string).
            standby: Optional[Tuple[int, str, int, int]] = None
            if (type_label == "hd" and getattr(cfg, "standby_guard_enabled", False)
                    and states and getattr(controller, "count", 0) > 1):
                try:
                    arr_str = controller.get_standby_state_str()
                    standby_count = sum(1 for s in states if s)
                    standby = (int(cfg.standby_hd_limit), arr_str, standby_count, controller.count)
                except Exception:  # pylint: disable=broad-except
                    standby = None
            # Aggregated current temperature/level — use the same helpers as the Controllers table
            # so the block stays consistent with the row above it on the standalone path (where
            # the controller loop hasn't run so last_temp/last_level aren't populated). Band the
            # result against the controller's window using the *parsed* numeric to avoid a second
            # ipmitool / smartctl call per row.
            last_temp_str = _safe_temp_str(controller, type_label)
            first_zone = cfg.ipmi_zone[0] if cfg.ipmi_zone else None
            last_level_str = _safe_zone_level(ipmi, first_zone) if first_zone is not None else "-"
            t_now = _parse_temp_cell(last_temp_str)
            if t_now is not None:
                last_temp_str = _wrap(last_temp_str, _band_color(t_now, dev_t_min, dev_t_max), use_color)
            l_now = _parse_level_cell(last_level_str)
            if l_now is not None:
                last_level_str = _wrap(last_level_str,
                                       _band_color(l_now, float(getattr(cfg, "min_level", 0)),
                                                   float(getattr(cfg, "max_level", 0))),
                                       use_color)
            block = _format_controller_block(
                section=section,
                type_label=type_label,
                zones=list(cfg.ipmi_zone),
                polling=float(getattr(cfg, "polling", 0.0)),
                deferred=bool(getattr(controller, "deferred_apply", False)),
                temp_min=float(getattr(cfg, "min_temp", 0.0)),
                temp_max=float(getattr(cfg, "max_temp", 0.0)),
                level_min=int(getattr(cfg, "min_level", 0)),
                level_max=int(getattr(cfg, "max_level", 0)),
                last_temp_str=last_temp_str,
                last_level_str=last_level_str,
                devices=device_rows,
                standby=standby,
                use_color=use_color,
            )
            lines.extend(block)
            lines.append("")

    # Live IPMI zones
    zone_lines = _format_zones_table(entries, ipmi, use_color)
    if zone_lines:
        lines.extend(zone_lines)
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
    return _wrap(f"  source: {label}", DIM, use_color)


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
    lines.append(_wrap(f"  config: {config_path}", DIM, use_color))
    lines.append(_format_source_line(online=True, use_color=use_color))
    # Service uptime (online only, verbose only): the daemon tracks start_time; the snapshot
    # carries generated_at. Keep the non-verbose header to just `config:` and `source:` so
    # short reports stay compact, and surface uptime only when the user asks for verbose.
    if verbose:
        start_time = float(snapshot.get("start_time", 0.0) or 0.0)
        generated_at = float(snapshot.get("generated_at", 0.0) or 0.0)
        if start_time and generated_at >= start_time:
            lines.append(_wrap(f"  uptime: {_format_uptime(generated_at - start_time)}", DIM, use_color))
    lines.append("")

    # BMC section. See the standalone-path comment above for the non-verbose / verbose split:
    # non-verbose shows just Product + Fan mode; verbose adds Manufacturer / Firmware / IPMI
    # version / Platform (factory class only).
    bmc = snapshot.get("bmc", {}) or {}
    lines.append(_wrap("BMC", CYAN, use_color))
    if verbose:
        lines.append(f"  Manufacturer  : {bmc.get('manufacturer_name', '?')} ({bmc.get('manufacturer_id', '?')})")
    lines.append(f"  Product       : {bmc.get('product_name', '?')} ({bmc.get('product_id', '?')})")
    if verbose:
        lines.append(f"  Firmware      : {bmc.get('firmware_rev', '?')}")
        lines.append(f"  IPMI version  : {bmc.get('ipmi_version', '?')}")
        # Platform shows the factory class only — the product name is already on the line above.
        lines.append(f"  Platform      : {bmc.get('platform_class', '?')}")
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
    lines.append(_wrap("Fan controllers", CYAN, use_color))
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
        # Pre-pad temp / level to their column widths, THEN wrap colour around the result so the
        # invisible ANSI escapes don't disturb the table's character grid. CONST has no curve, so
        # `_band_color` returns "" (no escape) and the cell renders in default colour.
        temp_cell = f"{temp_str:<10}"
        level_cell = level_str
        if type_label != "const":
            t_min = float(c.get("temp_min_c", 0.0))
            t_max = float(c.get("temp_max_c", 0.0))
            l_min = int(c.get("level_min_pct", 0))
            l_max = int(c.get("level_max_pct", 0))
            temp_cell = _wrap(temp_cell, _band_color(float(c.get("last_temp_c", 0.0)), t_min, t_max),
                              use_color)
            level_int = int(level) if level is not None else int(c.get("last_level_pct", 0))
            level_cell = _wrap(level_cell, _band_color(float(level_int), float(l_min), float(l_max)),
                               use_color)
        lines.append(f"  {section:<10}{type_label:<8}{zones_str:<10}{devices_str:<9}{temp_cell}{level_cell}")
    lines.append("")

    # Per-controller verbose blocks (Proposal A). All fields are already in the snapshot, so
    # this path issues no subprocesses — the request-thread contract from CLIENT_SERVER.md
    # is preserved. CONST controllers are skipped (no devices) but stay in the Controllers
    # table above.
    if verbose:
        for c in controllers:
            type_label = c.get("type", "?")
            if type_label == "const":
                continue
            section = c.get("section", "?")
            ipmi_zones = list(c.get("ipmi_zones", []) or [])
            # Per-device rows + (HD) STANDBY/ACTIVE annotation from the snapshot's states list.
            sb = c.get("standby_guard") or {}
            states = list(sb.get("states", []) or []) if sb.get("enabled") else []
            devices = c.get("devices", []) or []
            # Defensive: truncate to the shorter of devices/states so a state-shorter-than-devices
            # snapshot doesn't surface phantom rows (matches the standalone path's behaviour).
            if states:
                devices = devices[:len(states)]
            # Per-device temp colour uses the parent controller's steering window — that's the
            # only honest baseline (an HD at 38 C is hot, a CPU at 38 C is cold). Standby disks
            # render DIM regardless: the reading is stale and the disk isn't contributing.
            dev_t_min = float(c.get("temp_min_c", 0.0))
            dev_t_max = float(c.get("temp_max_c", 0.0))
            device_rows: List[Tuple[str, str, Optional[str], str]] = []
            for i, d in enumerate(devices):
                name = str(d.get("name", ""))
                t_dev = float(d.get("temp_c", 0.0))
                temp_str = f"{t_dev:.1f} C"
                state_str: Optional[str] = None
                if states and i < len(states):
                    state_str = "STANDBY" if states[i] else "ACTIVE"
                temp_color = DIM if state_str == "STANDBY" else _band_color(t_dev, dev_t_min, dev_t_max)
                device_rows.append((_display_device_name(name, type_label), temp_str, state_str, temp_color))
            # Standby Guard summary line (HD with standby_guard.enabled=True only).
            standby: Optional[Tuple[int, str, int, int]] = None
            if type_label == "hd" and sb.get("enabled"):
                arr_str = sb.get("array_state", "")
                standby_count = int(sb.get("standby_count", sum(1 for s in states if s)))
                standby = (int(sb.get("limit", 1)), arr_str, standby_count, len(states))
            # Current temp/level — pulled from the snapshot's cached aggregates, with the live
            # zone level taking precedence (matches the Controllers table's level cell).
            t_now = float(c.get("last_temp_c", 0.0))
            t_min = float(c.get("temp_min_c", 0.0))
            t_max = float(c.get("temp_max_c", 0.0))
            l_min = int(c.get("level_min_pct", 0))
            l_max = int(c.get("level_max_pct", 0))
            last_temp_str = _wrap(f"{t_now:.1f} C", _band_color(t_now, t_min, t_max), use_color)
            first_zone = ipmi_zones[0] if ipmi_zones else None
            zone_info = zones.get(str(first_zone), {}) if first_zone is not None else {}
            level = zone_info.get("applied_level_pct")
            level_int = int(level) if level is not None else int(c.get("last_level_pct", 0))
            last_level_str = _wrap(f"{level_int:3d} %",
                                   _band_color(float(level_int), float(l_min), float(l_max)),
                                   use_color)
            block = _format_controller_block(
                section=section,
                type_label=type_label,
                zones=ipmi_zones,
                polling=float(c.get("polling", 0.0)),
                deferred=bool(c.get("deferred_apply", False)),
                temp_min=t_min,
                temp_max=t_max,
                level_min=l_min,
                level_max=l_max,
                last_temp_str=last_temp_str,
                last_level_str=last_level_str,
                devices=device_rows,
                standby=standby,
                use_color=use_color,
            )
            lines.extend(block)
            lines.append("")

    # IPMI zones (live) — applied levels straight from the snapshot.
    if zones:
        lines.append(_wrap("IPMI zones (live)", CYAN, use_color))
        lines.append(f"  {'Zone':<8}Level")
        lines.append(f"  {'-' * 6:<8}-----")
        for zone_str, info in sorted(zones.items(), key=lambda kv: int(kv[0])):
            level = info.get("applied_level_pct")
            level_fmt = f"{int(level):3d} %" if level is not None else "-"
            lines.append(f"  {zone_str:<8}{level_fmt}")
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
