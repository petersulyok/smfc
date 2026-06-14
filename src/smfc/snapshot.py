#
#   snapshot.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   build_snapshot(): produce the live-state dict consumed by smfc-client and the Prometheus exporter.
#
import time
from importlib.metadata import version
from typing import TYPE_CHECKING, Any, Dict, List

from smfc.constfc import ConstFc
from smfc.cpufc import CpuFc
from smfc.gpufc import GpuFc
from smfc.hdfc import HdFc
from smfc.ipmi import Ipmi
from smfc.nvmefc import NvmeFc

if TYPE_CHECKING:  # pragma: no cover
    from smfc.service import Service


SNAPSHOT_SCHEMA_VERSION: int = 1


def _controller_type_label(controller) -> str:
    """Map a controller instance to its short type label used in the JSON schema and metric labels.

    The Service.controllers list is closed: it only holds CpuFc, HdFc, NvmeFc, GpuFc, ConstFc.
    """
    if isinstance(controller, ConstFc):
        return "const"
    if isinstance(controller, HdFc):
        return "hd"
    if isinstance(controller, NvmeFc):
        return "nvme"
    if isinstance(controller, GpuFc):
        return "gpu"
    assert isinstance(controller, CpuFc), f"unknown controller type: {type(controller).__name__}"
    return "cpu"


def _build_controller_entry(controller) -> Dict[str, Any]:
    """Build the JSON dict for a single controller (FanController subclass or ConstFc)."""
    type_label = _controller_type_label(controller)
    cfg = controller.config
    entry: Dict[str, Any] = {
        "section": cfg.section,
        "type": type_label,
        "enabled": bool(cfg.enabled),
        "ipmi_zones": list(cfg.ipmi_zone),
        "polling": float(cfg.polling),
        "deferred_apply": bool(getattr(controller, "deferred_apply", False)),
        "last_temp_c": float(getattr(controller, "last_temp", 0.0)),
        "last_level_pct": int(getattr(controller, "last_level", 0)),
    }
    if type_label == "const":
        # ConstFc has no underlying device set; expose its target level explicitly.
        entry["device_count"] = 0
        entry["target_level_pct"] = int(cfg.level)
        # Static steering window: CONST drives a single fixed level and has no temperature window.
        entry["level_min_pct"] = int(cfg.level)
        entry["level_max_pct"] = int(cfg.level)
    else:
        entry["device_count"] = int(getattr(controller, "count", 0))
        # Static steering window: [T_min, T_max] mapped onto [L_min, L_max] (static config).
        entry["temp_min_c"] = float(cfg.min_temp)
        entry["temp_max_c"] = float(cfg.max_temp)
        entry["level_min_pct"] = int(cfg.min_level)
        entry["level_max_pct"] = int(cfg.max_level)
        # Per-device temperature readings cached by the loop's last get_temp() call. Names come
        # from the controller (HD/NVMe expose configured paths; CPU/GPU synthesize ordinal labels).
        # When the loop hasn't run yet temps may be shorter than names — pad with 0.0 so the
        # array length always matches device_count.
        names = list(controller.device_names())
        temps = list(getattr(controller, "last_per_device_temps", []) or [])
        entry["devices"] = [
            {"name": names[i], "temp_c": float(temps[i]) if i < len(temps) else 0.0}
            for i in range(len(names))
        ]

    if isinstance(controller, HdFc):
        # Per-disk paths live in entry["devices"][i]["name"] (built above); the standby block
        # below indexes states[i] positionally against that list.
        if cfg.standby_guard_enabled and controller.count > 1:
            states = list(getattr(controller, "standby_array_states", []))
            entry["standby_guard"] = {
                "enabled": True,
                "limit": int(cfg.standby_hd_limit),
                "states": states,
                "array_state": "".join("S" if s else "A" for s in states),
                "standby_count": sum(1 for s in states if s),
            }
        else:
            entry["standby_guard"] = {"enabled": False}

    return entry


def build_snapshot(service: "Service") -> Dict[str, Any]:
    """Build a JSON-serializable snapshot of the live smfc service state.

    The function reads only already-cached state on the Service, its controllers, and the Ipmi
    instance. It issues no subprocesses (no ipmitool, no smartctl) and is safe to call from a
    non-loop thread (e.g. an HTTP request handler) without any synchronization primitive — see
    "Concurrency & freshness" in CLIENT_SERVER.md for the design rationale.

    Args:
        service (Service): the running Service instance.

    Returns:
        dict: JSON-serializable snapshot dict with schema version SNAPSHOT_SCHEMA_VERSION.
    """
    ipmi: Ipmi = service.ipmi
    now = time.time()

    last_fan_mode = int(service.last_fan_mode)
    last_fan_mode_at = float(service.last_fan_mode_at)
    age_s = max(0.0, time.monotonic() - last_fan_mode_at)

    controllers_section: List[Dict[str, Any]] = [
        _build_controller_entry(fc) for fc in service.controllers
    ]

    # Defensive copy: applied_levels is mutated by the main loop on every iteration.
    applied_levels = dict(service.applied_levels)
    zones_section: Dict[str, Dict[str, int]] = {
        str(zone): {"applied_level_pct": int(level)}
        for zone, level in sorted(applied_levels.items())
    }

    return {
        "version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": now,
        "smfc_version": version("smfc"),
        "start_time": float(getattr(service, "start_time", 0.0)),
        "fan_mode_enforced_count": int(getattr(service, "fan_mode_enforced_count", 0)),
        "bmc": {
            "manufacturer_name": ipmi.bmc_manufacturer_name,
            "manufacturer_id": int(ipmi.bmc_manufacturer_id),
            "product_name": ipmi.bmc_product_name,
            "product_id": int(ipmi.bmc_product_id),
            "firmware_rev": ipmi.bmc_firmware_rev,
            "ipmi_version": ipmi.bmc_ipmi_version,
            "platform_name": ipmi.platform.name,
            "platform_class": type(ipmi.platform).__name__,
        },
        "fan_mode": {
            "id": last_fan_mode,
            "name": Ipmi.get_fan_mode_name(last_fan_mode),
            "age_s": round(age_s, 3),
        },
        "fan_controllers": controllers_section,
        "zones": zones_section,
    }


# End.
