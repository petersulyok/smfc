#!/usr/bin/env python3
#
#   smoke_runner.py (C) 2021-2026, Peter Sulyok
#   Smoke test runner for smfc service.
#
import atexit
import sys
import time
from configparser import ConfigParser
from pytest import fixture
from pyudev import Context
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, CpuFc, HdFc, NvmeFc, GpuFc, Service
from .test_00_data import TestData, MockedContextGood

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

        def exit_func() -> None:
            nonlocal my_td
            del my_td

        # pylint: disable=unused-argument, duplicate-code
        def mocked_cpufc_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal my_td
            self.hwmon_path = my_td.cpu_files
            count = len(my_td.cpu_files)
            # Initialize FanController class.
            FanController.__init__(
                self, log, ipmi,
                config[CpuFc.CS_CPU_FC].get(CpuFc.CV_CPU_FC_IPMI_ZONE, fallback=f"{Ipmi.CPU_ZONE}"),
                CpuFc.CS_CPU_FC, count,
                config[CpuFc.CS_CPU_FC].getint(CpuFc.CV_CPU_FC_TEMP_CALC, fallback=FanController.CALC_AVG),
                config[CpuFc.CS_CPU_FC].getint(CpuFc.CV_CPU_FC_STEPS, fallback=6),
                config[CpuFc.CS_CPU_FC].getfloat(CpuFc.CV_CPU_FC_SENSITIVITY, fallback=3.0),
                config[CpuFc.CS_CPU_FC].getfloat(CpuFc.CV_CPU_FC_POLLING, fallback=2),
                config[CpuFc.CS_CPU_FC].getfloat(CpuFc.CV_CPU_FC_MIN_TEMP, fallback=30.0),
                config[CpuFc.CS_CPU_FC].getfloat(CpuFc.CV_CPU_FC_MAX_TEMP, fallback=60.0),
                config[CpuFc.CS_CPU_FC].getint(CpuFc.CV_CPU_FC_MIN_LEVEL, fallback=35),
                config[CpuFc.CS_CPU_FC].getint(CpuFc.CV_CPU_FC_MAX_LEVEL, fallback=100)
            )

        def mocked_hdfc_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser, sudo: bool) -> None:
            nonlocal my_td
            nonlocal cmd_smart
            self.hd_device_names = my_td.hd_name_list
            self.hwmon_path = my_td.hd_files
            count = len(my_td.hd_files)
            self.sudo = sudo

            # Initialize FanController class.
            FanController.__init__(
                self, log, ipmi,
                config[HdFc.CS_HD_FC].get(HdFc.CV_HD_FC_IPMI_ZONE, fallback=f"{Ipmi.HD_ZONE}"),
                HdFc.CS_HD_FC, count,
                config[HdFc.CS_HD_FC].getint(HdFc.CV_HD_FC_TEMP_CALC, fallback=FanController.CALC_AVG),
                config[HdFc.CS_HD_FC].getint(HdFc.CV_HD_FC_STEPS, fallback=4),
                config[HdFc.CS_HD_FC].getfloat(HdFc.CV_HD_FC_SENSITIVITY, fallback=2),
                config[HdFc.CS_HD_FC].getfloat(HdFc.CV_HD_FC_POLLING, fallback=10),
                config[HdFc.CS_HD_FC].getfloat(HdFc.CV_HD_FC_MIN_TEMP, fallback=32),
                config[HdFc.CS_HD_FC].getfloat(HdFc.CV_HD_FC_MAX_TEMP, fallback=46),
                config[HdFc.CS_HD_FC].getint(HdFc.CV_HD_FC_MIN_LEVEL, fallback=35),
                config[HdFc.CS_HD_FC].getint(HdFc.CV_HD_FC_MAX_LEVEL, fallback=100)
            )

            # Save path for `smartctl` command.
            self.smartctl_path = cmd_smart

            # Read and validate the configuration of standby guard if enabled.
            self.standby_guard_enabled = config[HdFc.CS_HD_FC].getboolean(HdFc.CV_HD_FC_STANDBY_GUARD_ENABLED,
                                                                          fallback=False)
            if self.count == 1:
                self.log.msg(Log.LOG_INFO, "   WARNING: Standby guard is disabled ([HD] count=1")
            self.standby_guard_enabled = False
            if self.standby_guard_enabled:
                self.standby_array_states = [False] * self.count
                # Read and validate further parameters.
                self.standby_hd_limit = config[HdFc.CS_HD_FC].getint(HdFc.CV_HD_FC_STANDBY_HD_LIMIT, fallback=1)
                if self.standby_hd_limit < 0:
                    raise ValueError("standby_hd_limit < 0")
                if self.standby_hd_limit > self.count:
                    raise ValueError("standby_hd_limit > count")
                # Get the current power state of the HD array.
                n = self.check_standby_state()
                # Set calculated parameters.
                self.standby_change_timestamp = time.monotonic()
                self.standby_flag = n == self.count

            # Print configuration in CONFIG log level (or higher).
            if self.log.log_level >= Log.LOG_CONFIG:
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_HD_FC_HD_NAMES} = {self.hd_device_names}")
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_HD_FC_SMARTCTL_PATH} = {self.smartctl_path}")
                if self.standby_guard_enabled:
                    self.log.msg(Log.LOG_CONFIG, "   Standby guard is enabled:")
                    self.log.msg(Log.LOG_CONFIG, f"     {self.CV_HD_FC_STANDBY_HD_LIMIT} = {self.standby_hd_limit}")
                else:
                    self.log.msg(Log.LOG_CONFIG, "   Standby guard is disabled")

        def mocked_nvmefc_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal my_td
            self.nvme_device_names = my_td.nvme_name_list
            self.hwmon_path = my_td.nvme_files
            count = len(my_td.nvme_files)

            # Initialize FanController class.

            FanController.__init__(
                self, log, ipmi,
                config[NvmeFc.CS_NVME_FC].get(NvmeFc.CV_NVME_FC_IPMI_ZONE, fallback=f"{Ipmi.HD_ZONE}"),
                NvmeFc.CS_NVME_FC, count,
                config[NvmeFc.CS_NVME_FC].getint(NvmeFc.CV_NVME_FC_TEMP_CALC, fallback=FanController.CALC_AVG),
                config[NvmeFc.CS_NVME_FC].getint(NvmeFc.CV_NVME_FC_STEPS, fallback=4),
                config[NvmeFc.CS_NVME_FC].getfloat(NvmeFc.CV_NVME_FC_SENSITIVITY, fallback=2),
                config[NvmeFc.CS_NVME_FC].getfloat(NvmeFc.CV_NVME_FC_POLLING, fallback=10),
                config[NvmeFc.CS_NVME_FC].getfloat(NvmeFc.CV_NVME_FC_MIN_TEMP, fallback=30),
                config[NvmeFc.CS_NVME_FC].getfloat(NvmeFc.CV_NVME_FC_MAX_TEMP, fallback=50),
                config[NvmeFc.CS_NVME_FC].getint(NvmeFc.CV_NVME_FC_MIN_LEVEL, fallback=35),
                config[NvmeFc.CS_NVME_FC].getint(NvmeFc.CV_NVME_FC_MAX_LEVEL, fallback=100)
            )
            # Print configuration in CONFIG log level (or higher).
            if self.log.log_level >= Log.LOG_CONFIG:
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_NVME_FC_NVME_NAMES} = {self.nvme_device_names}")

        def mocked_gpufc_init(self, log: Log, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal cmd_nvidia, cmd_rocm
            self.gpu_device_ids = list(range(gpu_num))
            count = len(self.gpu_device_ids)
            self.gpu_type = config[GpuFc.CS_GPU_FC].get(GpuFc.CV_GPU_FC_GPU_TYPE, "nvidia").lower()
            self.nvidia_smi_path = cmd_nvidia
            self.rocm_smi_path = cmd_rocm

            self.amd_temp_sensor = config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_AMD_TEMP_SENSOR, fallback=0)
            self.smi_called = 0

            # Initialize FanController class.
            FanController.__init__(
                self, log, ipmi,
                config[GpuFc.CS_GPU_FC].get(GpuFc.CV_GPU_FC_IPMI_ZONE, fallback=f"{Ipmi.HD_ZONE}"),
                GpuFc.CS_GPU_FC, count,
                config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_TEMP_CALC, fallback=FanController.CALC_AVG),
                config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_STEPS, fallback=4),
                config[GpuFc.CS_GPU_FC].getfloat(GpuFc.CV_GPU_FC_SENSITIVITY, fallback=2),
                config[GpuFc.CS_GPU_FC].getfloat(GpuFc.CV_GPU_FC_POLLING, fallback=10),
                config[GpuFc.CS_GPU_FC].getfloat(GpuFc.CV_GPU_FC_MIN_TEMP, fallback=45),
                config[GpuFc.CS_GPU_FC].getfloat(GpuFc.CV_GPU_FC_MAX_TEMP, fallback=70),
                config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_MIN_LEVEL, fallback=35),
                config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_MAX_LEVEL, fallback=100)
            )

            # Print configuration in CONFIG log level (or higher).
            if self.log.log_level >= Log.LOG_CONFIG:
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_GPU_IDS} = {self.gpu_device_ids}")
            if self.gpu_type == "nvidia":
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_NVIDIA_SMI_PATH} = {self.nvidia_smi_path}")
            else:
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_ROCM_SMI_PATH} = {self.rocm_smi_path}")
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_AMD_TEMP_SENSOR} = {self.amd_temp_sensor}")
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
        if gpu_num:
            cmd_nvidia = my_td.create_nvidia_smi_command(gpu_num)
            cmd_rocm = my_td.create_rocm_smi_command(gpu_num)

        # Load the original configuration file
        my_config = ConfigParser()
        my_config.read(config_file)
        # Add generated parameters.
        my_config[Ipmi.CS_IPMI][Ipmi.CV_IPMI_COMMAND] = cmd_ipmi
        if hd_num:
            my_config[HdFc.CS_HD_FC][HdFc.CV_HD_FC_HD_NAMES] = my_td.hd_names
            my_config[HdFc.CS_HD_FC][HdFc.CV_HD_FC_SMARTCTL_PATH] = cmd_smart
        if nvme_num:
            my_config[NvmeFc.CS_NVME_FC][NvmeFc.CV_NVME_FC_NVME_NAMES] = my_td.nvme_names
        if gpu_num:
            gpu_type = my_config[GpuFc.CS_GPU_FC].get(GpuFc.CV_GPU_FC_GPU_TYPE, "nvidia").lower()
            if gpu_type == "nvidia":
                my_config[GpuFc.CS_GPU_FC][GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH] = cmd_nvidia
            else:
                my_config[GpuFc.CS_GPU_FC][GpuFc.CV_GPU_FC_ROCM_SMI_PATH] = cmd_rocm
        # Create a new config file
        new_config_file = my_td.create_config_file(my_config)
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        mocker.patch("smfc.CpuFc.__init__", mocked_cpufc_init)
        mocker.patch("smfc.HdFc.__init__", mocked_hdfc_init)
        mocker.patch("smfc.NvmeFc.__init__", mocked_nvmefc_init)
        mocker.patch("smfc.GpuFc.__init__", mocked_gpufc_init)
        sys.argv = ("smfc -o 0 -l 4 -ne -nd -c " + new_config_file).split()
        service = Service()
        service.run()

    # pylint: enable=redefined-outer-name


# pylint: enable=too-few-public-methods


# End.
