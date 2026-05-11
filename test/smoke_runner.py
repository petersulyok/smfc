#!/usr/bin/env python3
#
#   smoke_runner.py (C) 2021-2026, Peter Sulyok
#   Smoke test runner for smfc service.
#
import atexit
import sys
import threading
from configparser import ConfigParser
from pytest import fixture
from pyudev import Context
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, Service
from smfc.config import Config, CpuConfig, HdConfig, NvmeConfig, GpuConfig
from .test_data import TestData, MockedContextGood

# In case of adding a new command line parameter, see `conftest.py` as well.


@fixture()
def cpu_num(request) -> int:
    """Read number of CPUs from command-line."""
    return int(request.config.getoption("--cpu-num"))


@fixture()
def hd_num(request) -> int:
    """Read number of HDDs from command-line."""
    return int(request.config.getoption("--hd-num"))


@fixture()
def gpu_num(request) -> int:
    """Read number of GPU from command-line."""
    return int(request.config.getoption("--gpu-num"))


@fixture()
def nvme_num(request) -> int:
    """Read number of NVMe drives from command-line."""
    return int(request.config.getoption("--nvme-num"))


@fixture()
def config_file(request) -> str:
    """Read the configuration file name from the command-line."""
    return request.config.getoption("--conf-file")


# pylint: disable=too-few-public-methods
class TestSmoke:
    """Smoke test class."""

    # pylint: disable=redefined-outer-name
    def test_smoke(self, mocker: MockerFixture, cpu_num, hd_num, gpu_num, nvme_num, config_file):
        """This is a smoke test for smfc program. It contains the following steps:
        - mock pyudev.Context.__init__(), CpuFc.__init__(), HdFc.__init__(), NvmeFc.__init__(),
          GpuFc.__init__() functions
        - execute smfc.run()
        - The main loop will be stopped if the user presses CTRL-C
        """
        my_td: TestData = None  # Test data
        temp_updater_stop: threading.Event = threading.Event()
        temp_ranges: dict = {}  # Temperature ranges from config

        def exit_func() -> None:
            nonlocal my_td, temp_updater_stop
            temp_updater_stop.set()
            del my_td

        def temperature_updater() -> None:
            """Background thread that periodically updates hwmon temperature files."""
            nonlocal my_td, temp_updater_stop, temp_ranges
            while not temp_updater_stop.is_set():
                if my_td.cpu_files and "cpu" in temp_ranges:
                    my_td.update_hwmon_temperatures(my_td.cpu_files, *temp_ranges["cpu"])
                if my_td.hd_files and "hd" in temp_ranges:
                    my_td.update_hwmon_temperatures(my_td.hd_files, *temp_ranges["hd"])
                if my_td.nvme_files and "nvme" in temp_ranges:
                    my_td.update_hwmon_temperatures(my_td.nvme_files, *temp_ranges["nvme"])
                temp_updater_stop.wait(1.0)

        # pylint: disable=unused-argument, duplicate-code
        def mocked_cpufc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: CpuConfig) -> None:
            nonlocal my_td
            self.config = cfg
            self.hwmon_path = my_td.cpu_files
            count = len(my_td.cpu_files)
            FanController.__init__(self, log, ipmi, cfg.section, count)

        def mocked_hdfc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: HdConfig, sudo: bool) -> None:
            nonlocal my_td, cmd_smart
            self.config = cfg
            self.hd_device_names = my_td.hd_name_list
            self.hwmon_path = my_td.hd_files
            count = len(my_td.hd_files)
            self.sudo = sudo
            cfg.smartctl_path = cmd_smart
            FanController.__init__(self, log, ipmi, cfg.section, count)
            if self.count == 1:
                self.log.msg(Log.LOG_INFO, "   WARNING: Standby guard is disabled ([HD] count=1")
            self.config.standby_guard_enabled = False
            if self.log.log_level >= Log.LOG_CONFIG:
                self.log.msg(Log.LOG_CONFIG, f"   hd_names = {self.hd_device_names}")
                self.log.msg(Log.LOG_CONFIG, f"   smartctl_path = {self.config.smartctl_path}")
                self.log.msg(Log.LOG_CONFIG, "   Standby guard is disabled")

        def mocked_nvmefc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: NvmeConfig) -> None:
            nonlocal my_td
            self.config = cfg
            self.nvme_device_names = my_td.nvme_name_list
            self.hwmon_path = my_td.nvme_files
            count = len(my_td.nvme_files)
            FanController.__init__(self, log, ipmi, cfg.section, count)
            if self.log.log_level >= Log.LOG_CONFIG:
                self.log.msg(Log.LOG_CONFIG, f"   nvme_names = {self.nvme_device_names}")

        def mocked_gpufc_init(self, log: Log, ipmi: Ipmi, cfg: GpuConfig) -> None:
            nonlocal cmd_nvidia, cmd_rocm
            cfg.gpu_device_ids = list(range(gpu_num))
            cfg.nvidia_smi_path = cmd_nvidia
            cfg.rocm_smi_path = cmd_rocm
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
            # pragma pylint: enable=unused-argument, duplicate-code

        my_td = TestData()
        atexit.register(exit_func)
        # Force mode initial fan mode 0 for setting new FULL mode during the test.
        cmd_ipmi = my_td.create_ipmi_command()
        cmd_smart = my_td.create_smart_command()
        cmd_nvidia = ""
        cmd_rocm = ""
        if cpu_num:
            my_td.create_cpu_data(cpu_num)
        if hd_num:
            my_td.create_hd_data(hd_num)
        if nvme_num:
            my_td.create_nvme_data(nvme_num)

        # Load the original configuration file
        my_config = ConfigParser()
        my_config.read(config_file)
        # Add generated parameters.
        my_config[Config.CS_IPMI][Config.CV_IPMI_COMMAND] = cmd_ipmi
        if hd_num:
            my_config[Config.CS_HD][Config.CV_HD_NAMES] = my_td.hd_names
            my_config[Config.CS_HD][Config.CV_HD_SMARTCTL_PATH] = cmd_smart
        if nvme_num:
            my_config[Config.CS_NVME][Config.CV_NVME_NAMES] = my_td.nvme_names
        if gpu_num:
            gpu_type = my_config[Config.CS_GPU].get(Config.CV_GPU_TYPE, Config.DV_GPU_TYPE).lower()
            gpu_min = my_config[Config.CS_GPU].getfloat(Config.CV_MIN_TEMP, fallback=Config.DV_GPU_MIN_TEMP)
            gpu_max = my_config[Config.CS_GPU].getfloat(Config.CV_MAX_TEMP, fallback=Config.DV_GPU_MAX_TEMP)
            cmd_nvidia = my_td.create_nvidia_smi_command(gpu_num, min_temp=gpu_min, max_temp=gpu_max)
            cmd_rocm = my_td.create_rocm_smi_command(gpu_num, min_temp=gpu_min, max_temp=gpu_max)
            if gpu_type == "nvidia":
                my_config[Config.CS_GPU][Config.CV_GPU_NVIDIA_SMI_PATH] = cmd_nvidia
            else:
                my_config[Config.CS_GPU][Config.CV_GPU_ROCM_SMI_PATH] = cmd_rocm

        # Extract temperature ranges from config for dynamic updates.
        # Use next() to handle both plain [CPU] and multi-section [CPU:0], [CPU:1] configs.
        if cpu_num:
            cpu_prefix = Config.CS_CPU + ":"
            cpu_sec = next((s for s in my_config.sections() if s == Config.CS_CPU or s.startswith(cpu_prefix)),
                           Config.CS_CPU)
            temp_ranges["cpu"] = (
                my_config[cpu_sec].getfloat(Config.CV_MIN_TEMP, fallback=Config.DV_CPU_MIN_TEMP),
                my_config[cpu_sec].getfloat(Config.CV_MAX_TEMP, fallback=Config.DV_CPU_MAX_TEMP)
            )
        if hd_num:
            hd_prefix = Config.CS_HD + ":"
            hd_sec = next((s for s in my_config.sections() if s == Config.CS_HD or s.startswith(hd_prefix)),
                          Config.CS_HD)
            temp_ranges["hd"] = (
                my_config[hd_sec].getfloat(Config.CV_MIN_TEMP, fallback=Config.DV_HD_MIN_TEMP),
                my_config[hd_sec].getfloat(Config.CV_MAX_TEMP, fallback=Config.DV_HD_MAX_TEMP)
            )
        if nvme_num:
            nvme_prefix = Config.CS_NVME + ":"
            nvme_sec = next((s for s in my_config.sections() if s == Config.CS_NVME or s.startswith(nvme_prefix)),
                            Config.CS_NVME)
            temp_ranges["nvme"] = (
                my_config[nvme_sec].getfloat(Config.CV_MIN_TEMP, fallback=Config.DV_NVME_MIN_TEMP),
                my_config[nvme_sec].getfloat(Config.CV_MAX_TEMP, fallback=Config.DV_NVME_MAX_TEMP)
            )

        # Create a new config file
        new_config_file = my_td.create_config_file(my_config)
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        mocker.patch("smfc.CpuFc.__init__", mocked_cpufc_init)
        mocker.patch("smfc.HdFc.__init__", mocked_hdfc_init)
        mocker.patch("smfc.NvmeFc.__init__", mocked_nvmefc_init)
        mocker.patch("smfc.GpuFc.__init__", mocked_gpufc_init)
        sys.argv = ("smfc -o 0 -l 4 -ne -nd -c " + new_config_file).split()
        service = Service()

        # Start background thread to update temperatures periodically.
        temp_thread = threading.Thread(target=temperature_updater, daemon=True)
        temp_thread.start()

        service.run()

    # pylint: enable=redefined-outer-name


# pylint: enable=too-few-public-methods


# End.
