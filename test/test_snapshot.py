#!/usr/bin/env python3
#
#   test_snapshot.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.snapshot.build_snapshot().
#
# pylint: disable=protected-access
import time
from unittest.mock import MagicMock
import pytest
from smfc.ipmi import Ipmi
from smfc.snapshot import SNAPSHOT_SCHEMA_VERSION, build_snapshot


def _make_ipmi() -> MagicMock:
    """Build a fully-mocked Ipmi instance with the static BMC info attributes the snapshot reads."""
    ipmi = MagicMock(spec=Ipmi)
    ipmi.bmc_manufacturer_name = "Super Micro Computer Inc."
    ipmi.bmc_manufacturer_id = 10876
    ipmi.bmc_product_name = "X11SCH-LN4F"
    ipmi.bmc_product_id = 6929
    ipmi.bmc_firmware_rev = "1.74"
    ipmi.bmc_ipmi_version = "2.0"
    ipmi.platform = MagicMock()
    ipmi.platform.name = "X11SCH-LN4F"
    type(ipmi.platform).__name__ = "GenericPlatform"
    return ipmi


def _make_cpu_fc(zones=None, last_temp=42.3, last_level=45, polling=2.0,
                 per_device_temps=None) -> MagicMock:
    """Build a fake CpuFc-like controller (last_temp/last_level/count populated)."""
    from smfc.cpufc import CpuFc as _CpuFc  # pylint: disable=import-outside-toplevel
    zones = zones or [0]
    fc = MagicMock(spec=_CpuFc)
    fc.config = MagicMock()
    fc.config.section = "CPU"
    fc.config.enabled = True
    fc.config.ipmi_zone = zones
    fc.config.polling = polling
    fc.config.min_temp = 30.0
    fc.config.max_temp = 70.0
    fc.config.min_level = 25
    fc.config.max_level = 100
    fc.count = 1
    fc.last_temp = last_temp
    fc.last_level = last_level
    fc.deferred_apply = False
    fc.last_per_device_temps = per_device_temps if per_device_temps is not None else [last_temp]
    fc.device_names.return_value = [f"cpu{i}" for i in range(fc.count)]
    return fc


def _make_hd_fc(zones=None, count=4, last_temp=34.1, last_level=55, standby_enabled=False,
                standby_states=None, hd_names=None, per_device_temps=None) -> MagicMock:
    """Build a fake HdFc-like controller. To make isinstance(fc, HdFc) work, use a real HdFc spec."""
    from smfc.hdfc import HdFc as _HdFc  # pylint: disable=import-outside-toplevel
    zones = zones or [1]
    hd_names = hd_names if hd_names is not None else [f"/dev/sd{chr(ord('a') + i)}" for i in range(count)]
    fc = MagicMock(spec=_HdFc)
    fc.config = MagicMock()
    fc.config.section = "HD"
    fc.config.enabled = True
    fc.config.ipmi_zone = zones
    fc.config.polling = 10.0
    fc.config.standby_guard_enabled = standby_enabled
    fc.config.standby_hd_limit = 1
    fc.config.min_temp = 32.0
    fc.config.max_temp = 50.0
    fc.config.min_level = 35
    fc.config.max_level = 100
    fc.count = count
    fc.last_temp = last_temp
    fc.last_level = last_level
    fc.deferred_apply = False
    fc.hd_device_names = hd_names
    fc.last_per_device_temps = (per_device_temps if per_device_temps is not None
                                else [last_temp + i * 0.5 for i in range(count)])
    fc.device_names.return_value = list(hd_names)
    if standby_enabled and standby_states is not None:
        fc.standby_array_states = standby_states
    return fc


def _make_const_fc(zones=None, level=50) -> MagicMock:
    """Build a fake ConstFc-like controller. Real spec so isinstance() works."""
    from smfc.constfc import ConstFc as _ConstFc  # pylint: disable=import-outside-toplevel
    zones = zones or [2]
    fc = MagicMock(spec=_ConstFc)
    fc.config = MagicMock()
    fc.config.section = "CONST"
    fc.config.enabled = True
    fc.config.ipmi_zone = zones
    fc.config.polling = 30.0
    fc.config.level = level
    fc.last_temp = 0.0
    fc.last_level = level
    fc.deferred_apply = False
    return fc


def _make_nvme_fc(zones=None, count=2, last_temp=48.5, last_level=55,
                  per_device_temps=None, nvme_names=None) -> MagicMock:
    """Build a fake NvmeFc-like controller (real spec so the snapshot's isinstance check finds it)."""
    from smfc.nvmefc import NvmeFc as _NvmeFc  # pylint: disable=import-outside-toplevel
    zones = zones or [1]
    nvme_names = nvme_names if nvme_names is not None else [f"/dev/nvme{i}n1" for i in range(count)]
    fc = MagicMock(spec=_NvmeFc)
    fc.config = MagicMock()
    fc.config.section = "NVME"
    fc.config.enabled = True
    fc.config.ipmi_zone = zones
    fc.config.polling = 2.0
    fc.config.min_temp = 40.0
    fc.config.max_temp = 75.0
    fc.config.min_level = 35
    fc.config.max_level = 100
    fc.count = count
    fc.last_temp = last_temp
    fc.last_level = last_level
    fc.deferred_apply = False
    fc.nvme_device_names = nvme_names
    fc.last_per_device_temps = (per_device_temps if per_device_temps is not None
                                else [last_temp + i * 0.7 for i in range(count)])
    fc.device_names.return_value = list(nvme_names)
    return fc


def _make_gpu_fc(zones=None, count=1, last_temp=55.0, last_level=60,
                 per_device_temps=None, gpu_device_ids=None) -> MagicMock:
    """Build a fake GpuFc-like controller (real spec so the snapshot's isinstance check finds it)."""
    from smfc.gpufc import GpuFc as _GpuFc  # pylint: disable=import-outside-toplevel
    zones = zones or [3]
    gpu_device_ids = gpu_device_ids if gpu_device_ids is not None else list(range(count))
    fc = MagicMock(spec=_GpuFc)
    fc.config = MagicMock()
    fc.config.section = "GPU"
    fc.config.enabled = True
    fc.config.ipmi_zone = zones
    fc.config.polling = 2.0
    fc.config.min_temp = 40.0
    fc.config.max_temp = 80.0
    fc.config.min_level = 35
    fc.config.max_level = 100
    fc.config.gpu_device_ids = gpu_device_ids
    fc.count = count
    fc.last_temp = last_temp
    fc.last_level = last_level
    fc.deferred_apply = False
    fc.last_per_device_temps = (per_device_temps if per_device_temps is not None
                                else [last_temp + i * 1.5 for i in range(count)])
    fc.device_names.return_value = [f"gpu{gid}" for gid in gpu_device_ids]
    return fc


def _make_service(controllers=None, applied_levels=None,
                  last_fan_mode=Ipmi.FULL_MODE, last_fan_mode_at=None,
                  start_time=1716902400.0, fan_mode_enforced_count=0) -> MagicMock:
    """Build a fake Service with attributes the snapshot reads."""
    service = MagicMock()
    service.ipmi = _make_ipmi()
    service.controllers = controllers or []
    service.applied_levels = applied_levels if applied_levels is not None else {}
    service.last_fan_mode = last_fan_mode
    service.last_fan_mode_at = last_fan_mode_at if last_fan_mode_at is not None else time.monotonic()
    service.start_time = start_time
    service.fan_mode_enforced_count = fan_mode_enforced_count
    return service


class TestBuildSnapshot:
    """Unit tests for smfc.snapshot.build_snapshot()."""

    def test_schema_and_version(self) -> None:
        """The top-level dict carries the schema version and BMC info."""
        service = _make_service()
        snap = build_snapshot(service)
        assert snap["version"] == SNAPSHOT_SCHEMA_VERSION
        assert "generated_at" in snap
        assert "smfc_version" in snap
        assert snap["bmc"]["manufacturer_name"] == "Super Micro Computer Inc."
        assert snap["bmc"]["product_name"] == "X11SCH-LN4F"
        assert snap["bmc"]["platform_name"] == "X11SCH-LN4F"
        assert snap["bmc"]["platform_class"] == "GenericPlatform"

    def test_start_time_and_enforcement_count(self) -> None:
        """The snapshot surfaces the service start time and the fan-mode enforcement counter."""
        service = _make_service(start_time=1716902400.0, fan_mode_enforced_count=3)
        snap = build_snapshot(service)
        assert snap["start_time"] == pytest.approx(1716902400.0)
        assert snap["fan_mode_enforced_count"] == 3

    def test_fan_mode_block(self) -> None:
        """fan_mode reflects service.last_fan_mode and reports a non-negative age."""
        before = time.monotonic() - 5.0  # 5 s ago
        service = _make_service(last_fan_mode=Ipmi.FULL_MODE, last_fan_mode_at=before)
        snap = build_snapshot(service)
        fm = snap["fan_mode"]
        assert fm["id"] == int(Ipmi.FULL_MODE)
        assert fm["name"] == "FULL"
        assert fm["age_s"] >= 5.0
        assert fm["age_s"] < 60.0  # sanity bound for the test environment

    def test_cpu_controller_entry(self) -> None:
        """A CpuFc-like controller produces a complete entry with type 'cpu'."""
        cpu = _make_cpu_fc(zones=[0])
        service = _make_service(controllers=[cpu], applied_levels={0: 45})
        snap = build_snapshot(service)
        assert len(snap["controllers"]) == 1
        entry = snap["controllers"][0]
        assert entry["section"] == "CPU"
        assert entry["type"] == "cpu"
        assert entry["ipmi_zones"] == [0]
        assert entry["device_count"] == 1
        assert entry["last_temp_c"] == pytest.approx(42.3)
        assert entry["last_level_pct"] == 45
        assert entry["deferred_apply"] is False
        assert entry["enabled"] is True
        # Static steering window [T_min,T_max] -> [L_min,L_max].
        assert entry["temp_min_c"] == pytest.approx(30.0)
        assert entry["temp_max_c"] == pytest.approx(70.0)
        assert entry["level_min_pct"] == 25
        assert entry["level_max_pct"] == 100

    def test_const_controller_entry(self) -> None:
        """A ConstFc entry has device_count=0 and a target_level_pct field; standby block is absent."""
        const = _make_const_fc(zones=[2], level=50)
        service = _make_service(controllers=[const], applied_levels={2: 50})
        snap = build_snapshot(service)
        entry = snap["controllers"][0]
        assert entry["type"] == "const"
        assert entry["device_count"] == 0
        assert entry["target_level_pct"] == 50
        # CONST has no temperature window; its level window collapses to the fixed level.
        assert "temp_min_c" not in entry
        assert "temp_max_c" not in entry
        assert entry["level_min_pct"] == 50
        assert entry["level_max_pct"] == 50
        assert "standby" not in entry  # only HdFc emits a standby block

    def test_hd_controller_entry_no_standby(self) -> None:
        """An HdFc with standby disabled emits standby={'enabled': False} and device_names list."""
        hd = _make_hd_fc(zones=[1], count=4, standby_enabled=False)
        service = _make_service(controllers=[hd], applied_levels={1: 55})
        snap = build_snapshot(service)
        entry = snap["controllers"][0]
        assert entry["type"] == "hd"
        assert entry["device_count"] == 4
        assert entry["device_names"] == [f"/dev/sd{c}" for c in "abcd"]
        assert entry["standby"] == {"enabled": False}

    def test_hd_controller_entry_standby_enabled(self) -> None:
        """An HdFc with standby enabled emits the full standby block, including array_state and counts."""
        states = [False, False, True, True]
        hd = _make_hd_fc(zones=[1], count=4, standby_enabled=True, standby_states=states)
        service = _make_service(controllers=[hd])
        snap = build_snapshot(service)
        sb = snap["controllers"][0]["standby"]
        assert sb["enabled"] is True
        assert sb["limit"] == 1
        assert sb["states"] == states
        assert sb["array_state"] == "AASS"
        assert sb["standby_count"] == 2

    def test_hd_controller_standby_states_copied(self) -> None:
        """The standby_array_states list is copied; mutating the original after build does not change the snapshot."""
        states = [False, False, True, True]
        hd = _make_hd_fc(zones=[1], count=4, standby_enabled=True, standby_states=states)
        service = _make_service(controllers=[hd])
        snap = build_snapshot(service)
        states.clear()
        states.append(True)
        # Snapshot still has the original four entries.
        assert snap["controllers"][0]["standby"]["states"] == [False, False, True, True]

    def test_zones_block(self) -> None:
        """Zones mirrors applied_levels with stringified keys for JSON friendliness."""
        cpu = _make_cpu_fc(zones=[0])
        hd = _make_hd_fc(zones=[1])
        service = _make_service(controllers=[cpu, hd], applied_levels={1: 55, 0: 45})
        snap = build_snapshot(service)
        # JSON keys must be strings; entries must round-trip the levels.
        assert snap["zones"] == {"0": {"applied_level_pct": 45}, "1": {"applied_level_pct": 55}}

    def test_applied_levels_copied(self) -> None:
        """Mutating service.applied_levels after build does not affect the snapshot."""
        cpu = _make_cpu_fc(zones=[0])
        applied = {0: 45}
        service = _make_service(controllers=[cpu], applied_levels=applied)
        snap = build_snapshot(service)
        applied[0] = 99
        applied[1] = 100
        assert snap["zones"] == {"0": {"applied_level_pct": 45}}

    def test_multiple_controllers_order_preserved(self) -> None:
        """Controllers appear in the snapshot in the order present on Service.controllers."""
        cpu = _make_cpu_fc(zones=[0])
        hd = _make_hd_fc(zones=[1])
        const = _make_const_fc(zones=[2])
        service = _make_service(controllers=[cpu, hd, const])
        snap = build_snapshot(service)
        assert [c["section"] for c in snap["controllers"]] == ["CPU", "HD", "CONST"]

    def test_nvme_controller_entry(self) -> None:
        """An NvmeFc-like controller produces a complete entry with type 'nvme'."""
        nvme = _make_nvme_fc(zones=[1])
        service = _make_service(controllers=[nvme])
        snap = build_snapshot(service)
        entry = snap["controllers"][0]
        assert entry["type"] == "nvme"
        assert entry["section"] == "NVME"
        assert entry["device_count"] == 2
        assert entry["last_temp_c"] == pytest.approx(48.5)

    def test_gpu_controller_entry(self) -> None:
        """A GpuFc-like controller produces a complete entry with type 'gpu'."""
        gpu = _make_gpu_fc(zones=[3])
        service = _make_service(controllers=[gpu])
        snap = build_snapshot(service)
        entry = snap["controllers"][0]
        assert entry["type"] == "gpu"
        assert entry["section"] == "GPU"
        assert entry["last_temp_c"] == pytest.approx(55.0)

    def test_hd_per_device_temperatures(self) -> None:
        """An HdFc entry carries a `devices` array pairing each hd_name with its cached per-device temp."""
        per_dev = [33.0, 34.5, 36.1, 39.0]
        hd = _make_hd_fc(zones=[1], count=4, per_device_temps=per_dev,
                         hd_names=["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"])
        service = _make_service(controllers=[hd])
        snap = build_snapshot(service)
        devices = snap["controllers"][0]["devices"]
        assert [d["name"] for d in devices] == ["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"]
        assert [d["temp_c"] for d in devices] == pytest.approx(per_dev)

    def test_cpu_per_device_temperatures(self) -> None:
        """A CpuFc entry's `devices` array uses synthesized cpu0/cpu1/... labels."""
        cpu = _make_cpu_fc(zones=[0], per_device_temps=[42.3])
        cpu.count = 1
        service = _make_service(controllers=[cpu])
        snap = build_snapshot(service)
        devices = snap["controllers"][0]["devices"]
        assert devices == [{"name": "cpu0", "temp_c": pytest.approx(42.3)}]

    def test_nvme_per_device_temperatures(self) -> None:
        """An NvmeFc entry's `devices` array exposes the configured nvme_names with cached temps."""
        nvme = _make_nvme_fc(zones=[1], count=2, per_device_temps=[47.5, 49.5],
                             nvme_names=["/dev/nvme0n1", "/dev/nvme1n1"])
        service = _make_service(controllers=[nvme])
        snap = build_snapshot(service)
        devices = snap["controllers"][0]["devices"]
        assert [d["name"] for d in devices] == ["/dev/nvme0n1", "/dev/nvme1n1"]
        assert [d["temp_c"] for d in devices] == pytest.approx([47.5, 49.5])

    def test_gpu_per_device_temperatures(self) -> None:
        """A GpuFc entry's `devices` array uses gpu<id> labels matching the configured device IDs."""
        gpu = _make_gpu_fc(zones=[3], count=2, per_device_temps=[55.0, 62.5],
                           gpu_device_ids=[0, 2])
        service = _make_service(controllers=[gpu])
        snap = build_snapshot(service)
        devices = snap["controllers"][0]["devices"]
        assert [d["name"] for d in devices] == ["gpu0", "gpu2"]
        assert [d["temp_c"] for d in devices] == pytest.approx([55.0, 62.5])

    def test_const_has_no_devices(self) -> None:
        """A ConstFc entry never carries a `devices` array — CONST has no temperature concept."""
        const = _make_const_fc(zones=[2], level=50)
        service = _make_service(controllers=[const])
        snap = build_snapshot(service)
        assert "devices" not in snap["controllers"][0]

    def test_per_device_temps_shorter_than_names(self) -> None:
        """When the loop hasn't run yet, last_per_device_temps may be empty; entries get 0.0 fallback."""
        hd = _make_hd_fc(zones=[1], count=2, per_device_temps=[], hd_names=["/dev/sda", "/dev/sdb"])
        service = _make_service(controllers=[hd])
        snap = build_snapshot(service)
        devices = snap["controllers"][0]["devices"]
        assert [d["name"] for d in devices] == ["/dev/sda", "/dev/sdb"]
        assert [d["temp_c"] for d in devices] == [0.0, 0.0]


# End.
