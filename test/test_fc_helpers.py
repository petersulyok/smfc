#!/usr/bin/env python3
#
#   test_fc_helpers.py (C) 2026, Peter Sulyok
#   Shared builders and assertions for FanController subclass unit tests.
#
#   The FanController subclasses (CpuFc, HdFc, NvmeFc, GpuFc) all share the same
#   base-class contract but differ in how they discover devices. These helpers
#   factor out the repeated "mock the discovery layer, construct, assert the base
#   attributes" boilerplate so each test module keeps only its device-specific
#   surface. One build_<controller>() per controller is added as the migration
#   rolls out; assert_fc_base_contract() and FcHarness are shared by all of them.
#
import json
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import pyudev
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, CpuFc, HdFc, NvmeFc, GpuFc
from smfc.fancontroller import FanController
from smfc.config import Config
from .test_config_builders import create_cpu_config, create_hd_config, create_nvme_config, create_gpu_config
from .test_fixtures import TestData
from .test_mocks import MockDevices, factory_mockdevice

# Config fields set on every FanController subclass; checked by assert_fc_base_contract().
BASE_CONFIG_FIELDS = ["ipmi_zone", "temp_calc", "steps", "sensitivity", "polling", "min_temp", "max_temp",
                      "min_level", "max_level", "smoothing"]


@dataclass
class FcHarness:
    """A constructed fan controller together with the test data and references used to build it."""
    fc: Any                 # the constructed controller (concrete subclass, e.g. NvmeFc)
    td: Optional[TestData]  # test data owning the temporary hwmon tree (None for GPU, which has no hwmon)
    cfg: Any                # the config the controller was built from
    log: Log                # the Log reference passed to the controller
    ipmi: Ipmi              # the Ipmi reference passed to the controller


def assert_fc_base_contract(fc: FanController, cfg: Any, *, count: int, expected: Dict[str, Any],
                            log: Optional[Log] = None, ipmi: Optional[Ipmi] = None,
                            has_hwmon: bool = True) -> None:
    """Assert the FanController base-class contract shared by every subclass.

    Args:
        fc (FanController): the constructed controller
        cfg (Any): the config object the controller was built from
        count (int): expected device count
        expected (Dict[str, Any]): expected values for the shared config fields (see BASE_CONFIG_FIELDS)
        log (Optional[Log]): if given, assert the controller kept this reference
        ipmi (Optional[Ipmi]): if given, assert the controller kept this reference
        has_hwmon (bool): assert a non-empty hwmon_path list (False for GPU which has no hwmon)
    """
    if log is not None:
        assert fc.log is log
    if ipmi is not None:
        assert fc.ipmi is ipmi
    assert fc.config is cfg
    assert fc.name == cfg.section
    assert fc.count == count
    for field, value in expected.items():
        assert getattr(fc.config, field) == value, field
    if has_hwmon:
        assert fc.hwmon_path


def build_cpu_fc(mocker: MockerFixture, td: TestData, *, count: int, temps: Optional[List[float]] = None,
                 **cfg_kwargs) -> FcHarness:
    """Build a fully-initialized CpuFc with the udev/hwmon discovery layer mocked.

    Args:
        mocker (MockerFixture): pytest-mock fixture
        td (TestData): test data instance owning the temporary hwmon tree
        count (int): number of CPU hwmon devices to materialize (0 => no devices discovered)
        temps (Optional[List[float]]): optional fixed per-device temperatures
        **cfg_kwargs: forwarded to create_cpu_config()
    Returns:
        FcHarness: the controller plus the references used to build it
    """
    td.create_cpu_data(count, temps)
    mocker.patch("builtins.print", MagicMock())
    dev_list = [f"DEV{i}" for i in range(count)]
    mocker.patch("pyudev.Context.list_devices", MagicMock(return_value=dev_list))
    mocker.patch("smfc.FanController.get_hwmon_path", MagicMock(side_effect=td.cpu_files))
    cfg = create_cpu_config(enabled=True, **cfg_kwargs)
    log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
    ipmi = Ipmi.__new__(Ipmi)
    udevc = pyudev.Context.__new__(pyudev.Context)
    fc = CpuFc(log, udevc, ipmi, cfg)
    return FcHarness(fc=fc, td=td, cfg=cfg, log=log, ipmi=ipmi)


def build_nvme_fc(mocker: MockerFixture, td: TestData, *, count: int, temps: Optional[List[float]] = None,
                  names: Optional[List[str]] = None, hwmon: str = "files", **cfg_kwargs) -> FcHarness:
    """Build a fully-initialized NvmeFc with the udev/hwmon discovery layer mocked.

    Args:
        mocker (MockerFixture): pytest-mock fixture
        td (TestData): test data instance owning the temporary hwmon tree
        count (int): number of NVMe data devices to materialize
        temps (Optional[List[float]]): optional fixed per-device temperatures
        names (Optional[List[str]]): override the nvme_names list (default: the generated device names)
        hwmon (str): "files" wires get_hwmon_path to the generated files; "empty" returns "" (no hwmon)
        **cfg_kwargs: forwarded to create_nvme_config()
    Returns:
        FcHarness: the controller plus the references used to build it
    """
    td.create_nvme_data(count, temps)
    name_list = names if names is not None else td.nvme_name_list
    mocker.patch("builtins.print", MagicMock())
    mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
    mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
    hwmon_mock = MagicMock(return_value="") if hwmon == "empty" else MagicMock(side_effect=td.nvme_files)
    mocker.patch("smfc.FanController.get_hwmon_path", hwmon_mock)
    cfg = create_nvme_config(enabled=True, nvme_names=name_list, **cfg_kwargs)
    log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
    ipmi = Ipmi.__new__(Ipmi)
    udevc = pyudev.Context.__new__(pyudev.Context)
    fc = NvmeFc(log, udevc, ipmi, cfg)
    return FcHarness(fc=fc, td=td, cfg=cfg, log=log, ipmi=ipmi)


def build_hd_fc(mocker: MockerFixture, td: TestData, *, count: int, sudo: bool = False,
                temps: Optional[List[float]] = None, names: Optional[List[str]] = None, hwmon: str = "files",
                **cfg_kwargs) -> FcHarness:
    """Build a fully-initialized HdFc with the udev/hwmon discovery layer and smartctl mocked.

    Args:
        mocker (MockerFixture): pytest-mock fixture
        td (TestData): test data instance owning the temporary hwmon tree
        count (int): number of HD data devices to materialize
        sudo (bool): sudo flag passed to HdFc
        temps (Optional[List[float]]): optional fixed per-device temperatures
        names (Optional[List[str]]): override the hd_names list (default: the generated device names)
        hwmon (str): "files" wires get_hwmon_path to the generated files; "empty" returns "" (smartctl fallback)
        **cfg_kwargs: forwarded to create_hd_config() (e.g. smartctl_path, standby_guard_enabled, standby_hd_limit)
    Returns:
        FcHarness: the controller plus the references used to build it
    """
    td.create_hd_data(count, temps)
    name_list = names if names is not None else td.hd_name_list
    mocker.patch("builtins.print", MagicMock())
    mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
    mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
    mocker.patch("smfc.HdFc._exec_smartctl", MagicMock(return_value=subprocess.CompletedProcess([], returncode=0)))
    hwmon_mock = MagicMock(return_value="") if hwmon == "empty" else MagicMock(side_effect=td.hd_files)
    mocker.patch("smfc.FanController.get_hwmon_path", hwmon_mock)
    cfg = create_hd_config(enabled=True, hd_names=name_list, **cfg_kwargs)
    log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
    ipmi = Ipmi.__new__(Ipmi)
    udevc = pyudev.Context.__new__(pyudev.Context)
    fc = HdFc(log, udevc, ipmi, cfg, sudo)
    return FcHarness(fc=fc, td=td, cfg=cfg, log=log, ipmi=ipmi)


def make_bare_hd_fc(*, config=None, smartctl_path: str = "/usr/sbin/smartctl", sudo: bool = False,
                    count: Optional[int] = None, hd_device_names: Optional[List[str]] = None,
                    hwmon_path: Optional[List[str]] = None, standby_array_states: Optional[List[bool]] = None,
                    log: Optional[Log] = None) -> HdFc:
    """Build an uninitialized HdFc with only the attributes the HD-specific methods need (no udev/super().__init__).

    Only the attributes passed are set; tests set any further attributes (e.g. standby_flag) themselves.
    """
    fc = HdFc.__new__(HdFc)
    fc.config = config if config is not None else create_hd_config(smartctl_path=smartctl_path)
    fc.sudo = sudo
    if count is not None:
        fc.count = count
    if hd_device_names is not None:
        fc.hd_device_names = hd_device_names
    if hwmon_path is not None:
        fc.hwmon_path = hwmon_path
    if standby_array_states is not None:
        fc.standby_array_states = standby_array_states
    if log is not None:
        fc.log = log
    return fc


def make_bare_nvme_fc(td: TestData) -> NvmeFc:
    """Build an uninitialized NvmeFc with only the attributes _get_nth_temp() needs (no udev/super().__init__)."""
    fc = NvmeFc.__new__(NvmeFc)
    fc.hwmon_path = td.nvme_files
    fc.nvme_device_names = td.nvme_name_list
    return fc


def build_gpu_fc(mocker: MockerFixture, *, gpu_type: str = "nvidia", gpu_device_ids: Optional[List[int]] = None,
                 **cfg_kwargs) -> FcHarness:
    """Build a fully-initialized GpuFc with _exec_smi() mocked (GPU has no udev/hwmon discovery).

    The base FanController.__init__ reads an initial temperature, so _exec_smi() is mocked to return a
    constant 40C reading per device in the format the configured gpu_type expects.

    Args:
        mocker (MockerFixture): pytest-mock fixture
        gpu_type (str): "nvidia" or "amd"
        gpu_device_ids (Optional[List[int]]): GPU device ids (default: the GPU config default ids)
        **cfg_kwargs: forwarded to create_gpu_config() (e.g. nvidia_smi_path, rocm_smi_path, amd_temp_sensor)
    Returns:
        FcHarness: the controller plus the references used to build it (td is None for GPU)
    """
    device_ids = gpu_device_ids if gpu_device_ids is not None else Config.parse_gpu_ids(Config.DV_GPU_DEVICE_IDS)
    mocker.patch("builtins.print", MagicMock())
    if gpu_type == "nvidia":
        stdout = "40\n" * len(device_ids)
    else:
        stdout = json.dumps({f"card{gid}": {"Temperature (Sensor junction) (C)": "40.0"} for gid in device_ids})
    smi_result = subprocess.CompletedProcess([], returncode=0, stdout=stdout)
    mocker.patch("smfc.GpuFc._exec_smi", MagicMock(return_value=smi_result))
    cfg = create_gpu_config(enabled=True, gpu_type=gpu_type, gpu_device_ids=device_ids, **cfg_kwargs)
    log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
    ipmi = Ipmi.__new__(Ipmi)
    fc = GpuFc(log, ipmi, cfg)
    return FcHarness(fc=fc, td=None, cfg=cfg, log=log, ipmi=ipmi)


def make_bare_gpu_fc(config=None) -> GpuFc:
    """Build an uninitialized GpuFc with no super().__init__(); sets config + smi_called when a config is given."""
    fc = GpuFc.__new__(GpuFc)
    if config is not None:
        fc.config = config
        fc.smi_called = 0
    return fc


# End.
