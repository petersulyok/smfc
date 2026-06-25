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


def _make_ipmi(enforce_fan_mode: bool = True, platform_name: str = "auto") -> MagicMock:
    """Build a fully-mocked Ipmi instance with the static BMC info attributes the snapshot reads."""
    ipmi = MagicMock(spec=Ipmi)
    ipmi.bmc_manufacturer_name = "Super Micro Computer Inc."
    ipmi.bmc_manufacturer_id = 10876
    ipmi.bmc_product_name = "X11SCH-LN4F"
    ipmi.bmc_product_id = 6929
    ipmi.bmc_firmware_rev = "1.74"
    ipmi.bmc_ipmi_version = "2.0"
    ipmi.platform = MagicMock()
    type(ipmi.platform).__name__ = "GenericPlatform"
    ipmi.config = MagicMock()
    ipmi.config.enforce_fan_mode = enforce_fan_mode
    ipmi.config.platform_name = platform_name
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
                  start_time=1716902400.0, fan_mode_enforced_count=0,
                  enforce_fan_mode=True) -> MagicMock:
    """Build a fake Service with attributes the snapshot reads."""
    service = MagicMock()
    service.ipmi = _make_ipmi(enforce_fan_mode=enforce_fan_mode)
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
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock Service with MagicMock-based Ipmi stub (via _make_service / _make_ipmi helpers)
        - call build_snapshot() with the fake service
        - ASSERT: snapshot version equals SNAPSHOT_SCHEMA_VERSION
        - ASSERT: generated_at key is present
        - ASSERT: smfc_version key is present
        - ASSERT: bmc.manufacturer_name matches the stub
        - ASSERT: bmc.product_name matches the stub
        - ASSERT: bmc.platform shows "<platform_name> -> <platform_class>"
        - ASSERT: legacy bmc.platform_name key is absent
        - ASSERT: legacy bmc.platform_class key is absent
        """
        service = _make_service()
        snap = build_snapshot(service)
        assert snap["version"] == SNAPSHOT_SCHEMA_VERSION
        assert "generated_at" in snap
        assert "smfc_version" in snap
        assert snap["bmc"]["manufacturer_name"] == "Super Micro Computer Inc."
        assert snap["bmc"]["product_name"] == "X11SCH-LN4F"
        assert snap["bmc"]["platform"] == "auto -> GenericPlatform"
        assert "platform_name" not in snap["bmc"]
        assert "platform_class" not in snap["bmc"]

    def test_start_time_and_enforcement_count(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock Service with start_time and fan_mode_enforced_count fields (via _make_service helper)
        - call build_snapshot() with the fake service
        - ASSERT: snapshot.start_time matches service.start_time
        - ASSERT: snapshot.fan_mode_enforced_count matches the counter on service
        """
        service = _make_service(start_time=1716902400.0, fan_mode_enforced_count=3)
        snap = build_snapshot(service)
        assert snap["start_time"] == pytest.approx(1716902400.0)
        assert snap["fan_mode_enforced_count"] == 3

    def test_fan_mode_block(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock Service with last_fan_mode=FULL_MODE and last_fan_mode_at 5 s in the past
          (via _make_service / _make_ipmi helpers)
        - call build_snapshot() with the fake service
        - ASSERT: fan_mode.id equals int(Ipmi.FULL_MODE)
        - ASSERT: fan_mode.name equals "FULL"
        - ASSERT: fan_mode.age_s is at least 5.0 seconds
        - ASSERT: fan_mode.age_s stays under 60.0 (sanity bound)
        - ASSERT: fan_mode.enforce_fan_mode is True
        """
        before = time.monotonic() - 5.0  # 5 s ago
        service = _make_service(last_fan_mode=Ipmi.FULL_MODE, last_fan_mode_at=before)
        snap = build_snapshot(service)
        fm = snap["fan_mode"]
        assert fm["id"] == int(Ipmi.FULL_MODE)
        assert fm["name"] == "FULL"
        assert fm["age_s"] >= 5.0
        assert fm["age_s"] < 60.0  # sanity bound for the test environment
        assert fm["enforce_fan_mode"] is True

    def test_fan_mode_block_enforcement_disabled(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock Service with enforce_fan_mode=False (via _make_service / _make_ipmi helpers)
        - call build_snapshot() with the fake service
        - ASSERT: fan_mode.enforce_fan_mode is False
        """
        service = _make_service(enforce_fan_mode=False)
        snap = build_snapshot(service)
        assert snap["fan_mode"]["enforce_fan_mode"] is False

    def test_cpu_controller_entry(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock a CpuFc controller (via _make_cpu_fc) and a Service (via _make_service)
          with applied_levels mapping zone 0 to 45
        - call build_snapshot() with the fake service
        - ASSERT: fan_controllers list has exactly one entry
        - ASSERT: entry.section equals "CPU"
        - ASSERT: entry.type equals "cpu"
        - ASSERT: entry.ipmi_zones equals [0]
        - ASSERT: entry.device_count equals 1
        - ASSERT: entry.last_temp_c matches the fixture temperature
        - ASSERT: entry.last_level_pct equals 45
        - ASSERT: entry.deferred_apply is False
        - ASSERT: entry.enabled is True
        - ASSERT: entry.temp_min_c / temp_max_c match the configured static window
        - ASSERT: entry.level_min_pct / level_max_pct match the configured level window
        - ASSERT: entry.control_function is an empty list (legacy linear mode)
        """
        cpu = _make_cpu_fc(zones=[0])
        service = _make_service(controllers=[cpu], applied_levels={0: 45})
        snap = build_snapshot(service)
        assert len(snap["fan_controllers"]) == 1
        entry = snap["fan_controllers"][0]
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
        # No control_function configured for this fake — the field is present (so consumers
        # can rely on its existence) but empty (signals legacy linear mode).
        assert entry["control_function"] == []

    def test_controller_entry_curve_overrides_legacy_min_max(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock a CpuFc controller (via _make_cpu_fc) with control_function breakpoints overriding
          the legacy min/max defaults, and a Service (via _make_service) with applied_levels
        - call build_snapshot() with the fake service
        - ASSERT: entry.temp_min_c equals the curve's first temperature breakpoint
        - ASSERT: entry.temp_max_c equals the curve's last temperature breakpoint
        - ASSERT: entry.level_min_pct equals the curve's first level breakpoint
        - ASSERT: entry.level_max_pct equals the curve's last level breakpoint
        - ASSERT: entry.control_function round-trips the breakpoints as nested lists
        """
        cpu = _make_cpu_fc(zones=[0])
        # Override the fake's config to declare a curve. The legacy min/max keys are left at
        # their fixture defaults (30/70/25/100) — the snapshot must IGNORE them and use the
        # curve instead, since that's what the runtime LUT is built from.
        cpu.config.control_function = [(35, 35), (55, 50), (70, 80), (85, 100)]
        service = _make_service(controllers=[cpu], applied_levels={0: 45})
        entry = build_snapshot(service)["fan_controllers"][0]
        # Window fields are the curve's endpoints, not the legacy 30/70/25/100.
        assert entry["temp_min_c"] == pytest.approx(35.0)
        assert entry["temp_max_c"] == pytest.approx(85.0)
        assert entry["level_min_pct"] == 35
        assert entry["level_max_pct"] == 100
        # Pairs round-trip as nested lists (JSON-friendly).
        assert entry["control_function"] == [[35, 35], [55, 50], [70, 80], [85, 100]]

    def test_const_controller_entry(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock a ConstFc controller (via _make_const_fc) with level=50 and a Service
          (via _make_service) with applied_levels mapping zone 2 to 50
        - call build_snapshot() with the fake service
        - ASSERT: entry.type equals "const"
        - ASSERT: entry.device_count equals 0
        - ASSERT: entry.target_level_pct equals 50
        - ASSERT: entry.temp_min_c key is absent (CONST has no temperature window)
        - ASSERT: entry.temp_max_c key is absent
        - ASSERT: entry.level_min_pct equals the fixed level
        - ASSERT: entry.level_max_pct equals the fixed level
        - ASSERT: entry.standby_guard key is absent (only HdFc emits a standby block)
        """
        const = _make_const_fc(zones=[2], level=50)
        service = _make_service(controllers=[const], applied_levels={2: 50})
        snap = build_snapshot(service)
        entry = snap["fan_controllers"][0]
        assert entry["type"] == "const"
        assert entry["device_count"] == 0
        assert entry["target_level_pct"] == 50
        # CONST has no temperature window; its level window collapses to the fixed level.
        assert "temp_min_c" not in entry
        assert "temp_max_c" not in entry
        assert entry["level_min_pct"] == 50
        assert entry["level_max_pct"] == 50
        assert "standby_guard" not in entry  # only HdFc emits a standby_guard block

    def test_hd_controller_entry_no_standby(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock an HdFc controller (via _make_hd_fc) with 4 disks and standby_guard disabled,
          and a Service (via _make_service) with applied_levels mapping zone 1 to 55
        - call build_snapshot() with the fake service
        - ASSERT: entry.type equals "hd"
        - ASSERT: entry.device_count equals 4
        - ASSERT: legacy entry.device_names key is absent (canonical names live in entry.devices)
        - ASSERT: entry.devices[].name matches /dev/sda..sdd in order
        - ASSERT: entry.standby_guard equals {"enabled": False}
        """
        hd = _make_hd_fc(zones=[1], count=4, standby_enabled=False)
        service = _make_service(controllers=[hd], applied_levels={1: 55})
        snap = build_snapshot(service)
        entry = snap["fan_controllers"][0]
        assert entry["type"] == "hd"
        assert entry["device_count"] == 4
        assert "device_names" not in entry  # canonical names are now in entry["devices"]
        assert [d["name"] for d in entry["devices"]] == [f"/dev/sd{c}" for c in "abcd"]
        assert entry["standby_guard"] == {"enabled": False}

    def test_hd_controller_entry_standby_enabled(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock an HdFc controller (via _make_hd_fc) with 4 disks, standby_guard enabled, and
          per-disk standby states [False, False, True, True], plus a Service (via _make_service)
        - call build_snapshot() with the fake service
        - ASSERT: standby_guard.enabled is True
        - ASSERT: standby_guard.limit equals 1
        - ASSERT: standby_guard.states matches the input list
        - ASSERT: standby_guard.array_state equals "AASS"
        - ASSERT: standby_guard.standby_count equals 2
        """
        states = [False, False, True, True]
        hd = _make_hd_fc(zones=[1], count=4, standby_enabled=True, standby_states=states)
        service = _make_service(controllers=[hd])
        snap = build_snapshot(service)
        sb = snap["fan_controllers"][0]["standby_guard"]
        assert sb["enabled"] is True
        assert sb["limit"] == 1
        assert sb["states"] == states
        assert sb["array_state"] == "AASS"
        assert sb["standby_count"] == 2

    def test_hd_controller_standby_states_copied(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock an HdFc controller (via _make_hd_fc) with standby_guard enabled and a mutable
          standby_states list, plus a Service (via _make_service)
        - call build_snapshot() with the fake service
        - mutate the original standby_states list after the snapshot is built
        - ASSERT: snapshot.standby_guard.states still holds the original four entries
          (proves the list was copied, not aliased)
        """
        states = [False, False, True, True]
        hd = _make_hd_fc(zones=[1], count=4, standby_enabled=True, standby_states=states)
        service = _make_service(controllers=[hd])
        snap = build_snapshot(service)
        states.clear()
        states.append(True)
        # Snapshot still has the original four entries.
        assert snap["fan_controllers"][0]["standby_guard"]["states"] == [False, False, True, True]

    def test_zones_block(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock a CpuFc (zone 0) and an HdFc (zone 1) controller (via _make_cpu_fc / _make_hd_fc),
          and a Service (via _make_service) with applied_levels={1: 55, 0: 45}
        - call build_snapshot() with the fake service
        - ASSERT: snapshot.zones equals {"0": {"applied_level_pct": 45}, "1": {"applied_level_pct": 55}}
          (string keys, levels round-tripped)
        """
        cpu = _make_cpu_fc(zones=[0])
        hd = _make_hd_fc(zones=[1])
        service = _make_service(controllers=[cpu, hd], applied_levels={1: 55, 0: 45})
        snap = build_snapshot(service)
        # JSON keys must be strings; entries must round-trip the levels.
        assert snap["zones"] == {"0": {"applied_level_pct": 45}, "1": {"applied_level_pct": 55}}

    def test_applied_levels_copied(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock a CpuFc controller (via _make_cpu_fc) and a Service (via _make_service) with a
          mutable applied_levels dict
        - call build_snapshot() with the fake service
        - mutate the original applied_levels dict after the snapshot is built
        - ASSERT: snapshot.zones still equals {"0": {"applied_level_pct": 45}}
          (proves the dict was copied, not aliased)
        """
        cpu = _make_cpu_fc(zones=[0])
        applied = {0: 45}
        service = _make_service(controllers=[cpu], applied_levels=applied)
        snap = build_snapshot(service)
        applied[0] = 99
        applied[1] = 100
        assert snap["zones"] == {"0": {"applied_level_pct": 45}}

    def test_multiple_controllers_order_preserved(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock CpuFc, HdFc, and ConstFc controllers (via _make_cpu_fc / _make_hd_fc / _make_const_fc)
          and a Service (via _make_service) with controllers=[cpu, hd, const]
        - call build_snapshot() with the fake service
        - ASSERT: fan_controllers section names appear in input order ["CPU", "HD", "CONST"]
        """
        cpu = _make_cpu_fc(zones=[0])
        hd = _make_hd_fc(zones=[1])
        const = _make_const_fc(zones=[2])
        service = _make_service(controllers=[cpu, hd, const])
        snap = build_snapshot(service)
        assert [c["section"] for c in snap["fan_controllers"]] == ["CPU", "HD", "CONST"]

    def test_nvme_controller_entry(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock an NvmeFc controller (via _make_nvme_fc) and a Service (via _make_service)
        - call build_snapshot() with the fake service
        - ASSERT: entry.type equals "nvme"
        - ASSERT: entry.section equals "NVME"
        - ASSERT: entry.device_count equals 2
        - ASSERT: entry.last_temp_c matches the fixture temperature
        """
        nvme = _make_nvme_fc(zones=[1])
        service = _make_service(controllers=[nvme])
        snap = build_snapshot(service)
        entry = snap["fan_controllers"][0]
        assert entry["type"] == "nvme"
        assert entry["section"] == "NVME"
        assert entry["device_count"] == 2
        assert entry["last_temp_c"] == pytest.approx(48.5)

    def test_gpu_controller_entry(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock a GpuFc controller (via _make_gpu_fc) and a Service (via _make_service)
        - call build_snapshot() with the fake service
        - ASSERT: entry.type equals "gpu"
        - ASSERT: entry.section equals "GPU"
        - ASSERT: entry.last_temp_c matches the fixture temperature
        """
        gpu = _make_gpu_fc(zones=[3])
        service = _make_service(controllers=[gpu])
        snap = build_snapshot(service)
        entry = snap["fan_controllers"][0]
        assert entry["type"] == "gpu"
        assert entry["section"] == "GPU"
        assert entry["last_temp_c"] == pytest.approx(55.0)

    def test_hd_per_device_temperatures(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock an HdFc controller (via _make_hd_fc) with 4 disks, explicit hd_names and a
          per_device_temps list, plus a Service (via _make_service)
        - call build_snapshot() with the fake service
        - ASSERT: entry.devices[].name matches the configured hd_names in order
        - ASSERT: entry.devices[].temp_c matches the per_device_temps list element-wise
        """
        per_dev = [33.0, 34.5, 36.1, 39.0]
        hd = _make_hd_fc(zones=[1], count=4, per_device_temps=per_dev,
                         hd_names=["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"])
        service = _make_service(controllers=[hd])
        snap = build_snapshot(service)
        devices = snap["fan_controllers"][0]["devices"]
        assert [d["name"] for d in devices] == ["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"]
        assert [d["temp_c"] for d in devices] == pytest.approx(per_dev)

    def test_cpu_per_device_temperatures(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock a CpuFc controller (via _make_cpu_fc) with count=1 and per_device_temps=[42.3],
          plus a Service (via _make_service)
        - call build_snapshot() with the fake service
        - ASSERT: entry.devices equals [{"name": "cpu0", "temp_c": 42.3}]
          (synthesized cpu<index> label paired with the cached temperature)
        """
        cpu = _make_cpu_fc(zones=[0], per_device_temps=[42.3])
        cpu.count = 1
        service = _make_service(controllers=[cpu])
        snap = build_snapshot(service)
        devices = snap["fan_controllers"][0]["devices"]
        assert devices == [{"name": "cpu0", "temp_c": pytest.approx(42.3)}]

    def test_nvme_per_device_temperatures(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock an NvmeFc controller (via _make_nvme_fc) with count=2, explicit nvme_names and a
          per_device_temps list, plus a Service (via _make_service)
        - call build_snapshot() with the fake service
        - ASSERT: entry.devices[].name matches the configured nvme_names in order
        - ASSERT: entry.devices[].temp_c matches the per_device_temps list element-wise
        """
        nvme = _make_nvme_fc(zones=[1], count=2, per_device_temps=[47.5, 49.5],
                             nvme_names=["/dev/nvme0n1", "/dev/nvme1n1"])
        service = _make_service(controllers=[nvme])
        snap = build_snapshot(service)
        devices = snap["fan_controllers"][0]["devices"]
        assert [d["name"] for d in devices] == ["/dev/nvme0n1", "/dev/nvme1n1"]
        assert [d["temp_c"] for d in devices] == pytest.approx([47.5, 49.5])

    def test_gpu_per_device_temperatures(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock a GpuFc controller (via _make_gpu_fc) with count=2, gpu_device_ids=[0, 2] and a
          per_device_temps list, plus a Service (via _make_service)
        - call build_snapshot() with the fake service
        - ASSERT: entry.devices[].name matches the gpu<id> labels for the configured IDs
        - ASSERT: entry.devices[].temp_c matches the per_device_temps list element-wise
        """
        gpu = _make_gpu_fc(zones=[3], count=2, per_device_temps=[55.0, 62.5],
                           gpu_device_ids=[0, 2])
        service = _make_service(controllers=[gpu])
        snap = build_snapshot(service)
        devices = snap["fan_controllers"][0]["devices"]
        assert [d["name"] for d in devices] == ["gpu0", "gpu2"]
        assert [d["temp_c"] for d in devices] == pytest.approx([55.0, 62.5])

    def test_const_has_no_devices(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock a ConstFc controller (via _make_const_fc) and a Service (via _make_service)
        - call build_snapshot() with the fake service
        - ASSERT: entry.devices key is absent (CONST has no temperature concept)
        """
        const = _make_const_fc(zones=[2], level=50)
        service = _make_service(controllers=[const])
        snap = build_snapshot(service)
        assert "devices" not in snap["fan_controllers"][0]

    def test_per_device_temps_shorter_than_names(self) -> None:
        """Positive unit test for build_snapshot() function. It contains the following steps:
        - mock an HdFc controller (via _make_hd_fc) with count=2, explicit hd_names, and an empty
          per_device_temps list (simulating the pre-first-loop state), plus a Service
        - call build_snapshot() with the fake service
        - ASSERT: entry.devices[].name matches the configured hd_names in order
        - ASSERT: entry.devices[].temp_c falls back to [0.0, 0.0] when no cached temps exist
        """
        hd = _make_hd_fc(zones=[1], count=2, per_device_temps=[], hd_names=["/dev/sda", "/dev/sdb"])
        service = _make_service(controllers=[hd])
        snap = build_snapshot(service)
        devices = snap["fan_controllers"][0]["devices"]
        assert [d["name"] for d in devices] == ["/dev/sda", "/dev/sdb"]
        assert [d["temp_c"] for d in devices] == [0.0, 0.0]


# End.
