#!/usr/bin/env python3
#
#   test_08_smoke.py (C) 2021-2025, Peter Sulyok
#   Smoke test smfc.
#
from argparse import Namespace
import sys
import time
from configparser import ConfigParser
import pytest
from pytest import fixture
from pyudev import Context
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, CpuZone, HdZone, Service, FanController
from .test_00_data import TestData, MockedContextGood


@fixture()
def hd_num(request) -> int:
    return int(request.config.getoption("--hd"))

@fixture()
def cpu_num(request) -> int:
    return int(request.config.getoption("--cpu"))

@fixture()
def config_file(request) -> str:
    return request.config.getoption("--config")


class TestSmoke:

    def test_smoke(self, mocker: MockerFixture, cpu_num: int, hd_num: int, config_file: str):
        """This is a smoke test for smfc program. It contains the following steps:
            - mock print(), pyudev.Context.__init__(), CpuZone.__init__(), HdZone.__init__() functions
            - execute smfc.run()
            - The main loop will be executed till a user interrupt (CTRL-C)
        """

        # pylint: disable=unused-argument
        def mocked_cpuzone_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser) -> None:
            self.hwmon_path = my_td.cpu_files
            count = len(my_td.cpu_files)
            # Initialize FanController class.
            super(FanController).__init__(self, log, ipmi, Ipmi.CPU_ZONE, CpuZone.CS_CPU_ZONE, count,
                             config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_TEMP_CALC,
                                                                fallback=FanController.CALC_AVG),
                             config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_STEPS, fallback=6),
                             config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_SENSITIVITY, fallback=3.0),
                             config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_POLLING, fallback=2),
                             config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_MIN_TEMP, fallback=30.0),
                             config[CpuZone.CS_CPU_ZONE].getfloat(CpuZone.CV_CPU_ZONE_MAX_TEMP, fallback=60.0),
                             config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_MIN_LEVEL, fallback=35),
                             config[CpuZone.CS_CPU_ZONE].getint(CpuZone.CV_CPU_ZONE_MAX_LEVEL, fallback=100))

        def mocked_hdzone_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser, sudo: bool) -> None:
            self.hd_device_names = my_td.hd_name_list
            self.hwmon_path = my_td.hd_files
            count = len(my_td.hd_files)
            self.sudo=sudo

            # Initialize FanController class.
            super(FanController).__init__(self, log, ipmi, Ipmi.HD_ZONE, self.CS_HD_ZONE, count,
                             config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
                             config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_STEPS, fallback=4),
                             config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_SENSITIVITY, fallback=2),
                             config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_POLLING, fallback=10),
                             config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_MIN_TEMP, fallback=32),
                             config[self.CS_HD_ZONE].getfloat(self.CV_HD_ZONE_MAX_TEMP, fallback=46),
                             config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_MIN_LEVEL, fallback=35),
                             config[self.CS_HD_ZONE].getint(self.CV_HD_ZONE_MAX_LEVEL, fallback=100))

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
        # pragma pylint: enable=unused-argument

        my_td = TestData()
        # Force mode initial fan mode 0 for setting new FULL mode during the test.
        cmd_ipmi = my_td.create_command_file('echo "0"')
        cmd_smart = my_td.create_smart_command()
        #                     create_command_file('echo "ACTIVE"'))
        my_td.create_cpu_data(cpu_num)
        my_td.create_hd_data(hd_num)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mocker.patch('pyudev.Context.__init__', MockedContextGood.__init__)
        mocker.patch('smfc.CpuZone.__init__', mocked_cpuzone_init)
        mocker.patch('smfc.HdZone.__init__', mocked_hdzone_init)
        sys.argv = ('smfc.py -o 0 -ne -nd -c ' + config_file).split()
        service = Service()
        service.run()
        del my_td


# End.
