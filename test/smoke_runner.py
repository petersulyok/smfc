#!/usr/bin/env python3
#
#   smoke_runner.py (C) 2021-2026, Peter Sulyok
#   Smoke test runner for smfc service.
#
#   Boots the real Service.run() loop against mocked devices for one scenario
#   (selected with --scenario; see SCENARIOS below). The run continues until the
#   user presses CTRL-C. A background thread drifts the fake hwmon temperatures.
#
import atexit
import os
import sys
import threading
from collections import namedtuple
from configparser import ConfigParser
from pytest import fixture, UsageError
from pyudev import Context
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, Service
from smfc.config import Config, CpuConfig, HdConfig, NvmeConfig, GpuConfig
from .test_data import TestData, MockedContextGood

# Smoke scenario matrix — single source of truth (replaces the per-scenario run_test_*.sh wrappers).
# Each scenario maps a name to device counts plus the config template (in this directory) under test.
Scenario = namedtuple("Scenario", ["cpu", "hd", "gpu", "nvme", "conf"])

SCENARIOS = {
    "cpu_1":            Scenario(1, 1, 0, 0, "cpu_1.conf"),
    "cpu_2":            Scenario(2, 0, 1, 0, "cpu_2.conf"),
    "cpu_4":            Scenario(4, 4, 4, 0, "cpu_4.conf"),
    "hd_1":             Scenario(0, 1, 0, 0, "hd_1.conf"),
    "hd_2":             Scenario(1, 2, 0, 0, "hd_2.conf"),
    "hd_4":             Scenario(0, 4, 4, 0, "hd_4.conf"),
    "hd_8":             Scenario(4, 8, 0, 0, "hd_8.conf"),
    "nvme_4":           Scenario(2, 0, 0, 4, "nvme_4.conf"),
    "const_level":      Scenario(1, 0, 0, 0, "const_level.conf"),
    "gpu_8_nvidia":     Scenario(1, 0, 8, 0, "gpu_8_nvidia.conf"),
    "gpu_8_amd":        Scenario(1, 0, 8, 0, "gpu_8_amd.conf"),
    "shared_zones":     Scenario(1, 0, 0, 2, "shared_zones.conf"),
    "shared_zones_2":   Scenario(2, 2, 0, 0, "shared_zones_2.conf"),
    "control_function": Scenario(2, 2, 0, 0, "control_function.conf"),
}


@fixture()
def scenario(request) -> Scenario:
    """Resolve the --scenario command-line option into a SCENARIOS entry (fails loudly if unknown)."""
    name = request.config.getoption("--scenario")
    if name not in SCENARIOS:
        valid = ", ".join(SCENARIOS)
        raise UsageError(f"--scenario must be one of: {valid} (got: {name!r})")
    return SCENARIOS[name]


# --- Mocked controller __init__ factories ------------------------------------
# Each factory returns a replacement __init__ (matching the real signature) that bypasses device
# discovery and injects the fake hwmon paths / device names / SMI commands from TestData. They replace
# (not wrap) the real __init__, so they are deliberately distinct from the test_fc_helpers builders.

def _make_cpufc_init(td: TestData):
    """Build a CpuFc.__init__ replacement that uses the fake CPU hwmon files."""
    # pylint: disable=unused-argument
    def _init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: CpuConfig) -> None:
        self.config = cfg
        self.hwmon_path = td.cpu_files
        FanController.__init__(self, log, ipmi, cfg.section, len(td.cpu_files))
    return _init


def _make_hdfc_init(td: TestData, smartctl_cmd: str):
    """Build an HdFc.__init__ replacement using the fake HD hwmon files and smartctl command."""
    # pylint: disable=unused-argument
    def _init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: HdConfig, sudo: bool) -> None:
        self.config = cfg
        self.hd_device_names = td.hd_name_list
        self.hwmon_path = td.hd_files
        self.sudo = sudo
        cfg.smartctl_path = smartctl_cmd
        FanController.__init__(self, log, ipmi, cfg.section, len(td.hd_files))
        if self.count == 1:
            self.log.msg(Log.LOG_INFO, "   WARNING: Standby guard is disabled ([HD] count=1")
        # Standby guard is disabled in smoke tests (it would repeatedly drive the fake smartctl command).
        self.config.standby_guard_enabled = False
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   hd_names = {self.hd_device_names}")
            self.log.msg(Log.LOG_CONFIG, f"   smartctl_path = {self.config.smartctl_path}")
            self.log.msg(Log.LOG_CONFIG, "   Standby guard is disabled")
    return _init


def _make_nvmefc_init(td: TestData):
    """Build an NvmeFc.__init__ replacement that uses the fake NVMe hwmon files."""
    # pylint: disable=unused-argument
    def _init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: NvmeConfig) -> None:
        self.config = cfg
        self.nvme_device_names = td.nvme_name_list
        self.hwmon_path = td.nvme_files
        FanController.__init__(self, log, ipmi, cfg.section, len(td.nvme_files))
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   nvme_names = {self.nvme_device_names}")
    return _init


def _make_gpufc_init(nvidia_cmd: str, rocm_cmd: str, gpu_count: int):
    """Build a GpuFc.__init__ replacement that uses the fake SMI commands and GPU count."""
    def _init(self, log: Log, ipmi: Ipmi, cfg: GpuConfig) -> None:
        cfg.gpu_device_ids = list(range(gpu_count))
        cfg.nvidia_smi_path = nvidia_cmd
        cfg.rocm_smi_path = rocm_cmd
        self.config = cfg
        self.smi_called = 0
        self.hwmon_path = []
        FanController.__init__(self, log, ipmi, cfg.section, len(cfg.gpu_device_ids))
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   gpu_type = {self.config.gpu_type}")
            self.log.msg(Log.LOG_CONFIG, f"   gpu_device_ids = {self.config.gpu_device_ids}")
            if self.config.gpu_type == "nvidia":
                self.log.msg(Log.LOG_CONFIG, f"   nvidia_smi_path = {self.config.nvidia_smi_path}")
            else:
                self.log.msg(Log.LOG_CONFIG, f"   rocm_smi_path = {self.config.rocm_smi_path}")
                self.log.msg(Log.LOG_CONFIG, f"   amd_temp_sensor = {self.config.amd_temp_sensor}")
    return _init


def _section_temp_range(config: ConfigParser, section: str, dv_min: float, dv_max: float) -> tuple:
    """Return the (min_temp, max_temp) of a controller section, tolerating numbered sections (e.g. CPU:0)."""
    sec = next((s for s in config.sections() if s == section or s.startswith(section + ":")), section)
    return (config[sec].getfloat(Config.CV_MIN_TEMP, fallback=dv_min),
            config[sec].getfloat(Config.CV_MAX_TEMP, fallback=dv_max))


# pylint: disable=too-few-public-methods
class TestSmoke:
    """Smoke test class."""

    # pylint: disable=redefined-outer-name
    def test_smoke(self, mocker: MockerFixture, scenario: Scenario):
        """Smoke test for the smfc service. It contains the following steps:
        - materialize fake hwmon files and ipmitool/smartctl/SMI commands for the scenario
        - mock pyudev.Context and each *Fc.__init__ to inject the fake devices
        - load the scenario config, inject the generated command paths / device names
        - run Service.run(); the main loop runs until CTRL-C while a thread drifts temperatures
        """
        my_td: TestData = TestData()
        temp_updater_stop: threading.Event = threading.Event()
        temp_ranges: dict = {}

        def exit_func() -> None:
            nonlocal my_td
            temp_updater_stop.set()
            del my_td

        def temperature_updater() -> None:
            """Background thread that periodically updates hwmon temperature files."""
            while not temp_updater_stop.is_set():
                if my_td.cpu_files and "cpu" in temp_ranges:
                    my_td.update_hwmon_temperatures(my_td.cpu_files, *temp_ranges["cpu"])
                if my_td.hd_files and "hd" in temp_ranges:
                    my_td.update_hwmon_temperatures(my_td.hd_files, *temp_ranges["hd"])
                if my_td.nvme_files and "nvme" in temp_ranges:
                    my_td.update_hwmon_temperatures(my_td.nvme_files, *temp_ranges["nvme"])
                temp_updater_stop.wait(1.0)

        atexit.register(exit_func)
        cmd_ipmi = my_td.create_ipmi_command()
        cmd_smart = my_td.create_smart_command()
        cmd_nvidia = ""
        cmd_rocm = ""
        if scenario.cpu:
            my_td.create_cpu_data(scenario.cpu)
        if scenario.hd:
            my_td.create_hd_data(scenario.hd)
        if scenario.nvme:
            my_td.create_nvme_data(scenario.nvme)

        # Load the scenario configuration file (resolved relative to this test module).
        my_config = ConfigParser()
        my_config.read(os.path.join(os.path.dirname(__file__), scenario.conf))
        # Add generated parameters.
        my_config[Config.CS_IPMI][Config.CV_IPMI_COMMAND] = cmd_ipmi
        if scenario.hd:
            my_config[Config.CS_HD][Config.CV_HD_NAMES] = my_td.hd_names
            my_config[Config.CS_HD][Config.CV_HD_SMARTCTL_PATH] = cmd_smart
        if scenario.nvme:
            my_config[Config.CS_NVME][Config.CV_NVME_NAMES] = my_td.nvme_names
        if scenario.gpu:
            gpu_type = my_config[Config.CS_GPU].get(Config.CV_GPU_TYPE, Config.DV_GPU_TYPE).lower()
            gpu_min = my_config[Config.CS_GPU].getfloat(Config.CV_MIN_TEMP, fallback=Config.DV_GPU_MIN_TEMP)
            gpu_max = my_config[Config.CS_GPU].getfloat(Config.CV_MAX_TEMP, fallback=Config.DV_GPU_MAX_TEMP)
            cmd_nvidia = my_td.create_nvidia_smi_command(scenario.gpu, min_temp=gpu_min, max_temp=gpu_max)
            cmd_rocm = my_td.create_rocm_smi_command(scenario.gpu, min_temp=gpu_min, max_temp=gpu_max)
            if gpu_type == "nvidia":
                my_config[Config.CS_GPU][Config.CV_GPU_NVIDIA_SMI_PATH] = cmd_nvidia
            else:
                my_config[Config.CS_GPU][Config.CV_GPU_ROCM_SMI_PATH] = cmd_rocm

        # Extract temperature ranges from config so the updater thread can drift them realistically.
        if scenario.cpu:
            temp_ranges["cpu"] = _section_temp_range(my_config, Config.CS_CPU, Config.DV_CPU_MIN_TEMP,
                                                     Config.DV_CPU_MAX_TEMP)
        if scenario.hd:
            temp_ranges["hd"] = _section_temp_range(my_config, Config.CS_HD, Config.DV_HD_MIN_TEMP,
                                                    Config.DV_HD_MAX_TEMP)
        if scenario.nvme:
            temp_ranges["nvme"] = _section_temp_range(my_config, Config.CS_NVME, Config.DV_NVME_MIN_TEMP,
                                                      Config.DV_NVME_MAX_TEMP)

        # Create a new config file and patch device discovery + controller construction.
        new_config_file = my_td.create_config_file(my_config)
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        mocker.patch("smfc.CpuFc.__init__", _make_cpufc_init(my_td))
        mocker.patch("smfc.HdFc.__init__", _make_hdfc_init(my_td, cmd_smart))
        mocker.patch("smfc.NvmeFc.__init__", _make_nvmefc_init(my_td))
        mocker.patch("smfc.GpuFc.__init__", _make_gpufc_init(cmd_nvidia, cmd_rocm, scenario.gpu))
        sys.argv = ("smfc -o 0 -l 4 -ne -nd -c " + new_config_file).split()
        service = Service()

        # Start background thread to update temperatures periodically.
        temp_thread = threading.Thread(target=temperature_updater, daemon=True)
        temp_thread.start()

        service.run()

    # pylint: enable=redefined-outer-name


# pylint: enable=too-few-public-methods


# End.
