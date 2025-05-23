#!/usr/bin/env python3
#
#   smoke_runner.py (C) 2021-2025, Peter Sulyok
#   Smoke test runner for smfc service.
#
import atexit
import sys
import time
from configparser import ConfigParser
from pytest import fixture
from pyudev import Context
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, CpuZone, HdZone, GpuZone, Service
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
def config_file(request) -> str:
    """Read the configuration file name from the command-line."""
    return request.config.getoption("--conf-file")


#pylint: disable=too-few-public-methods
class TestSmoke:
    """Smoke test class."""

    #pylint: disable=redefined-outer-name
    def test_smoke(self, mocker: MockerFixture, cpu_num, hd_num, gpu_num, config_file):
        """This is a smoke test for smfc program. It contains the following steps:
            - mock pyudev.Context.__init__(), CpuZone.__init__(), HdZone.__init__(), GpuZone.__init__() functions
            - execute smfc.run()
            - The main loop will be stopped if the user presses CTRL-C
        """
        my_td: TestData = None  # Test data

        def exit_func() -> None:
            nonlocal my_td
            del my_td

        # pylint: disable=unused-argument, duplicate-code
        def mocked_cpuzone_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal my_td
            self.hwmon_path = my_td.cpu_files
            count = len(my_td.cpu_files)
            # Initialize FanController class.
            FanController.__init__(
                self, log, ipmi,
                config[CpuZone.CS_CPU_ZONE].get(CpuZone.CV_CPU_IPMI_ZONE, fallback=f'{Ipmi.CPU_ZONE}'),
                CpuZone.CS_CPU_ZONE, count,
                config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
                config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_STEPS, fallback=6),
                config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_SENSITIVITY, fallback=3.0),
                config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_POLLING, fallback=2),
                config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_MIN_TEMP, fallback=30.0),
                config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_MAX_TEMP, fallback=60.0),
                config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_MIN_LEVEL, fallback=35),
                config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_MAX_LEVEL, fallback=100)
            )

        def mocked_hdzone_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser, sudo: bool) -> None:
            nonlocal my_td
            nonlocal cmd_smart
            self.hd_device_names = my_td.hd_name_list
            self.hwmon_path = my_td.hd_files
            count = len(my_td.hd_files)
            self.sudo=sudo

            # Initialize FanController class.
            FanController.__init__(
                self, log, ipmi,
                config[HdZone.CS_HD_ZONE].get(HdZone.CV_HD_IPMI_ZONE, fallback=f'{Ipmi.HD_ZONE}'),
                HdZone.CS_HD_ZONE, count,
                config[HdZone.CS_HD_ZONE].getint(HdZone.CV_HD_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
                config[HdZone.CS_HD_ZONE].getint(HdZone.CV_HD_ZONE_STEPS, fallback=4),
                config[HdZone.CS_HD_ZONE].getfloat(HdZone.CV_HD_ZONE_SENSITIVITY, fallback=2),
                config[HdZone.CS_HD_ZONE].getfloat(HdZone.CV_HD_ZONE_POLLING, fallback=10),
                config[HdZone.CS_HD_ZONE].getfloat(HdZone.CV_HD_ZONE_MIN_TEMP, fallback=32),
                config[HdZone.CS_HD_ZONE].getfloat(HdZone.CV_HD_ZONE_MAX_TEMP, fallback=46),
                config[HdZone.CS_HD_ZONE].getint(HdZone.CV_HD_ZONE_MIN_LEVEL, fallback=35),
                config[HdZone.CS_HD_ZONE].getint(HdZone.CV_HD_ZONE_MAX_LEVEL, fallback=100)
            )

            # Save path for `smartctl` command.
            self.smartctl_path = cmd_smart

            # Read and validate the configuration of standby guard if enabled.
            self.standby_guard_enabled = config[HdZone.CS_HD_ZONE].getboolean(HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED,
                                                                              fallback=False)
            if self.count == 1:
                self.log.msg(Log.LOG_INFO, '   WARNING: Standby guard is disabled ([HD zone] count=1')
            self.standby_guard_enabled = False
            if self.standby_guard_enabled:
                self.standby_array_states = [False] * self.count
                # Read and validate further parameters.
                self.standby_hd_limit = config[HdZone.CS_HD_ZONE].getint(HdZone.CV_HD_ZONE_STANDBY_HD_LIMIT, fallback=1)
                if self.standby_hd_limit < 0:
                    raise ValueError('standby_hd_limit < 0')
                if self.standby_hd_limit > self.count:
                    raise ValueError('standby_hd_limit > count')
                # Get the current power state of the HD array.
                n = self.check_standby_state()
                # Set calculated parameters.
                self.standby_change_timestamp = time.monotonic()
                self.standby_flag = n == self.count

            # Print configuration in CONFIG log level (or higher).
            if self.log.log_level >= Log.LOG_CONFIG:
                self.log.msg(Log.LOG_CONFIG, f'   {self.CV_HD_ZONE_HD_NAMES} = {self.hd_device_names}')
                self.log.msg(Log.LOG_CONFIG, f'   {self.CV_HD_ZONE_SMARTCTL_PATH} = {self.smartctl_path}')
                if self.standby_guard_enabled:
                    self.log.msg(Log.LOG_CONFIG, '   Standby guard is enabled:')
                    self.log.msg(Log.LOG_CONFIG, f'     {self.CV_HD_ZONE_STANDBY_HD_LIMIT} = {self.standby_hd_limit}')
                else:
                    self.log.msg(Log.LOG_CONFIG, '   Standby guard is disabled')

        def mocked_gpuzone_init(self, log: Log, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal  cmd_nvidia
            self.gpu_device_ids = list(range(gpu_num))
            count = len(self.gpu_device_ids)
            self.nvidia_smi_path = cmd_nvidia
            self.nvidia_smi_called = 0

            # Initialize FanController class.
            FanController.__init__(
                self, log, ipmi,
                config[GpuZone.CS_GPU_ZONE].get(GpuZone.CV_GPU_IPMI_ZONE, fallback=f'{Ipmi.HD_ZONE}'),
                GpuZone.CS_GPU_ZONE, count,
                config[GpuZone.CS_GPU_ZONE].getint(GpuZone.CV_GPU_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
                config[GpuZone.CS_GPU_ZONE].getint(GpuZone.CV_GPU_ZONE_STEPS, fallback=4),
                config[GpuZone.CS_GPU_ZONE].getfloat(GpuZone.CV_GPU_ZONE_SENSITIVITY, fallback=2),
                config[GpuZone.CS_GPU_ZONE].getfloat(GpuZone.CV_GPU_ZONE_POLLING, fallback=10),
                config[GpuZone.CS_GPU_ZONE].getfloat(GpuZone.CV_GPU_ZONE_MIN_TEMP, fallback=45),
                config[GpuZone.CS_GPU_ZONE].getfloat(GpuZone.CV_GPU_ZONE_MAX_TEMP, fallback=70),
                config[GpuZone.CS_GPU_ZONE].getint(GpuZone.CV_GPU_ZONE_MIN_LEVEL, fallback=35),
                config[GpuZone.CS_GPU_ZONE].getint(GpuZone.CV_GPU_ZONE_MAX_LEVEL, fallback=100)
            )

            # Print configuration in CONFIG log level (or higher).
            if self.log.log_level >= Log.LOG_CONFIG:
                self.log.msg(Log.LOG_CONFIG, f'   {self.CV_GPU_ZONE_GPU_IDS} = {self.gpu_device_ids}')
            self.log.msg(Log.LOG_CONFIG, f'   {self.CV_GPU_ZONE_NVIDIA_SMI_PATH} = {self.nvidia_smi_path}')
            # pragma pylint: enable=unused-argument, duplicate-code

        my_td = TestData()
        atexit.register(exit_func)
        # Force mode initial fan mode 0 for setting new FULL mode during the test.
        cmd_ipmi = my_td.create_command_file('echo "0"')
        cmd_smart = my_td.create_smart_command()
        if cpu_num:
            my_td.create_cpu_data(cpu_num)
        if hd_num:
            my_td.create_hd_data(hd_num)
        if gpu_num:
            cmd_nvidia = my_td.create_nvidia_smi_command(gpu_num)

        # Load the original configuration file
        my_config=ConfigParser()
        my_config.read(config_file)
        # Add generated parameters.
        my_config[Ipmi.CS_IPMI][Ipmi.CV_IPMI_COMMAND] = cmd_ipmi
        if hd_num:
            my_config[HdZone.CS_HD_ZONE][HdZone.CV_HD_ZONE_HD_NAMES] = my_td.hd_names
            my_config[HdZone.CS_HD_ZONE][HdZone.CV_HD_ZONE_SMARTCTL_PATH] = cmd_smart
        if gpu_num:
            my_config[GpuZone.CS_GPU_ZONE][GpuZone.CV_GPU_ZONE_NVIDIA_SMI_PATH] = cmd_nvidia
        # Create a new config file
        new_config_file = my_td.create_config_file(my_config)
        mocker.patch('pyudev.Context.__init__', MockedContextGood.__init__)
        mocker.patch('smfc.CpuZone.__init__', mocked_cpuzone_init)
        mocker.patch('smfc.HdZone.__init__', mocked_hdzone_init)
        mocker.patch('smfc.GpuZone.__init__', mocked_gpuzone_init)
        sys.argv = ('smfc -o 0 -l 4 -ne -nd -c ' + new_config_file).split()
        service = Service()
        service.run()
    #pylint: enable=redefined-outer-name
#pylint: enable=too-few-public-methods


# End.
