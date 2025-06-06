#!/usr/bin/env python3
#
#   test_08_service.py (C) 2021-2025, Peter Sulyok
#   Unit tests for smfc.Service() class.
#
from argparse import Namespace
import sys
import time
from configparser import ConfigParser
import pytest
from pyudev import Context
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, CpuZone, HdZone, GpuZone, ConstZone, Service
from .test_00_data import TestData, MockedContextError, MockedContextGood

class TestService:
    """Unit test for smfc.Service() class"""

    sleep_counter: int

    @pytest.mark.parametrize("ipmi, log, error", [
        (True, True,   'Service.exit_func() 1'),
        (False, False, 'Service.exit_func() 2')
    ])
    def test_exit_func(self, mocker:MockerFixture, ipmi: bool, log: bool, error: str) -> None:
        """Positive unit test for Service.exit_func() method. It contains the following steps:
            - mock atexit.unregister(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
            - execute Service.exit_func()
            - ASSERT: if mocked functions not called expected times
        """
        mock_atexit_unregister = MagicMock()
        mocker.patch('atexit.unregister', mock_atexit_unregister)
        mock_ipmi_set_fan_level = MagicMock()
        mocker.patch('smfc.Ipmi.set_fan_level', mock_ipmi_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch('smfc.Log.msg_to_stdout', mock_log_msg)
        service = Service()
        if log:
            service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        if ipmi:
            service.ipmi = Ipmi.__new__(Ipmi)
        service.exit_func()
        assert mock_atexit_unregister.call_count == 1, error
        if ipmi:
            assert mock_ipmi_set_fan_level.call_count == 2, error
            if log:
                assert mock_log_msg.call_count == 1, error

    @pytest.mark.parametrize("module_list, cpuzone, hdzone, gpuzone, standby, error", [
        ("something\ncoretemp\n",           True,  False, False, False, "Service.check_dependencies() 1"),
        ("something\nk10temp\n",            True,  False, True,  False, "Service.check_dependencies() 2"),
        ("coretemp\nsomething\nk10temp\n",  True,  False, False, False, "Service.check_dependencies() 3"),
        ("something\ndrivetemp\n",          False, True,  True,  False, "Service.check_dependencies() 4"),
        ("something\ndrivetemp\n",          False, True,  False, True,  "Service.check_dependencies() 5"),
        ("something\n",                     False, True,  False, False, "Service.check_dependencies() 6"),
        ("something\ndrivetemp\nx",         False, True,  True,  True,  "Service.check_dependencies() 7"),
        ("coretemp\ndrivetemp\n",           True,  True,  False, True,  "Service.check_dependencies() 8")
    ])
    def test_check_dependencies_p(self, mocker: MockerFixture, module_list: str, cpuzone: bool, hdzone: bool,
                                  gpuzone: bool, standby: bool, error: str):
        """Positive unit test for Service.check_dependencies() method. It contains the following steps:
            - mock print(), argparse.ArgumentParser._print_message() and builtins.open() functions
            - execute Service.check_dependencies()
            - ASSERT: if returns an error message
        """

        def mocked_open(path: str, *args, **kwargs):
            return original_open(modules, *args, **kwargs) if path == "/proc/modules" else \
                   original_open(path, *args, **kwargs)

        my_td = TestData()
        ipmi_command = my_td.create_ipmi_command()
        modules = my_td.create_text_file(module_list)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        original_open = open
        mock_open = MagicMock(side_effect=mocked_open)
        mocker.patch('builtins.open', mock_open)

        service = Service()
        service.config = ConfigParser()
        service.config[Ipmi.CS_IPMI] = {}
        service.config[Ipmi.CS_IPMI][Ipmi.CV_IPMI_COMMAND] = ipmi_command

        service.cpu_zone_enabled = cpuzone
        service.config[CpuZone.CS_CPU_ZONE] = {}
        service.config[CpuZone.CS_CPU_ZONE][CpuZone.CV_CPU_ZONE_ENABLED] = '1' if cpuzone else '0'

        service.hd_zone_enabled = hdzone
        service.config[HdZone.CS_HD_ZONE] = {}
        service.config[HdZone.CS_HD_ZONE][HdZone.CV_HD_ZONE_ENABLED] = '1' if hdzone else '0'
        if hdzone:
            smartctl_cmd = my_td.create_command_file('echo "ACTIVE"')
            service.config[HdZone.CS_HD_ZONE][HdZone.CV_HD_ZONE_SMARTCTL_PATH] = smartctl_cmd
            service.config[HdZone.CS_HD_ZONE][HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED] = '1' if standby else '0'

        service.gpu_zone_enabled = gpuzone
        service.config[GpuZone.CS_GPU_ZONE] = {}
        service.config[GpuZone.CS_GPU_ZONE][GpuZone.CV_GPU_ZONE_ENABLED] = '1' if gpuzone else '0'
        if gpuzone:
            nvidia_smi_cmd = my_td.create_command_file('echo "0"')
            service.config[GpuZone.CS_GPU_ZONE][GpuZone.CV_GPU_ZONE_NVIDIA_SMI_PATH] = nvidia_smi_cmd

        assert service.check_dependencies() == '', error
        del my_td

    @pytest.mark.parametrize("error", ["Service.check_dependencies() 9"])
    def test_check_dependecies_n(self, mocker:MockerFixture, error: str):
        """Negative unit test fot Service.check_dependencies() method. It contains the following steps:
            - mock print() and builtins.open() functions
            - execute Service.check_dependencies()
            - ASSERT: if it didn't return the specific error message
        """

        def mocked_open(path: str, *args, **kwargs):
            return original_open(modules, *args, **kwargs) if path == "/proc/modules" else \
                   original_open(path, *args, **kwargs)

        my_td = TestData()
        ipmi_command = my_td.create_ipmi_command()
        modules = my_td.create_text_file("coretemp\ndrivetemp\n")
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_open = MagicMock(side_effect=mocked_open)
        original_open = open
        mocker.patch('builtins.open', mock_open)
        service = Service()
        service.config = ConfigParser()

        service.config[Ipmi.CS_IPMI] = {}
        service.config[Ipmi.CS_IPMI][Ipmi.CV_IPMI_COMMAND] = ipmi_command

        service.cpu_zone_enabled = True
        service.config[CpuZone.CS_CPU_ZONE] = {}
        service.config[CpuZone.CS_CPU_ZONE][CpuZone.CV_CPU_ZONE_ENABLED] = '1'

        service.hd_zone_enabled = True
        service.config[HdZone.CS_HD_ZONE] = {}
        service.config[HdZone.CS_HD_ZONE][HdZone.CV_HD_ZONE_ENABLED] = '1'
        smartctl_cmd = my_td.create_command_file('echo "ACTIVE"')
        service.config[HdZone.CS_HD_ZONE][HdZone.CV_HD_ZONE_SMARTCTL_PATH] = smartctl_cmd
        service.config[HdZone.CS_HD_ZONE][HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED] = '1'

        nvidia_smi_cmd = my_td.create_command_file('echo "0"')
        service.gpu_zone_enabled = True
        service.config[GpuZone.CS_GPU_ZONE] = {}
        service.config[GpuZone.CS_GPU_ZONE][GpuZone.CV_GPU_ZONE_ENABLED] = '1'
        service.config[GpuZone.CS_GPU_ZONE][GpuZone.CV_GPU_ZONE_NVIDIA_SMI_PATH] = nvidia_smi_cmd

        # Check if `nvidia-smi` command is not available.
        my_td.delete_file(nvidia_smi_cmd)
        error_str = service.check_dependencies()
        assert error_str.find('nvidia-smi') != -1, error

        # Check if `smartctl` command is not available.
        my_td.delete_file(smartctl_cmd)
        error_str = service.check_dependencies()
        assert error_str.find('smartctl') != -1, error

        # Check if `drivetemp` is not on the module list.
        modules = my_td.create_text_file('coretemp something')
        error_str = service.check_dependencies()
        assert error_str.find('drivetemp') != -1, error

        # Check if `coretemp` is not on the module list.
        modules = my_td.create_text_file('drivetemp something')
        error_str = service.check_dependencies()
        assert error_str.find('coretemp') != -1, error

        # Check if `ipmitool` is not available.
        my_td.delete_file(ipmi_command)
        error_str = service.check_dependencies()
        assert error_str.find('ipmitool') != -1, error
        del my_td

    @pytest.mark.parametrize("command_line, exit_code, error", [
        ('-h',                                                      0, 'Service.run() 1'),
        ('-v',                                                      0, 'Service.run() 2'),
        ('-l 10',                                                   2, 'Service.run() 3'),
        ('-o 9',                                                    2, 'Service.run() 4'),
        ('-o 1 -l 10',                                              2, 'Service.run() 5'),
        ('-o 9 -l 1',                                               2, 'Service.run() 6'),
        ('-o 0 -l 3 -c &.txt',                                      6, 'Service.run() 7'),
        ('-o 0 -l 3 -c ./nonexistent_folder/nonexistent_file.conf', 6, 'Service.run() 8')
    ])
    def test_run_026n(self, mocker:MockerFixture, command_line: str, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
            - mock print(), argparse.ArgumentParser._print_message() functions
            - execute Service.run()
            - ASSERT: if sys.exit() did not return code 0 (-h -v), 2 (invalid arguments), 6 (invalid configuration file)
        """
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mocker_argumentparser_print = MagicMock()
        mocker.patch('argparse.ArgumentParser._print_message', mocker_argumentparser_print)
        sys.argv = ('smfc ' + command_line).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error

    @pytest.mark.parametrize("level, output, exit_code, error", [
        (10, 0, 5, 'Service.run() 9'),
        (0,  9, 5, 'Service.run() 10')
    ])
    def test_run_5n(self, mocker:MockerFixture, level: int, output: int, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
            - mock print(), argparse.ArgumentParser.parse_args() functions
            - execute Service.run()
            - ASSERT: if sys.exit() did not return code 5 (log initialization error)
        """
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_parser_parse_args = MagicMock()
        mocker.patch('argparse.ArgumentParser.parse_args', mock_parser_parse_args)
        mock_parser_parse_args.return_value = Namespace(config_file="smfc.conf", ne=False, s=False, l=level, o=output)
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error

    @pytest.mark.parametrize("exit_code, error", [
        (7, 'Service.run() 11')
    ])
    def test_run_7n(self, mocker:MockerFixture, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
            - mock print(), argparse.ArgumentParser.parse_args(), smfc.Service.check_dependencies() functions
            - execute Service.run()
            - ASSERT: if sys.exit() did not return code 7 (check dependency error)
        """
        my_td = TestData()
        my_config = ConfigParser()
        my_config[CpuZone.CS_CPU_ZONE] = {
            CpuZone.CV_CPU_ZONE_ENABLED: '0'
        }
        my_config[HdZone.CS_HD_ZONE] = {
            HdZone.CV_HD_ZONE_ENABLED: '0'
        }
        my_config[GpuZone.CS_GPU_ZONE] = {
            GpuZone.CV_GPU_ZONE_ENABLED: '0'
        }
        my_config[ConstZone.CS_CONST_ZONE] = {
            ConstZone.CV_CONST_ZONE_ENABLED: '0'
        }
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_parser_parse_args = MagicMock()
        mocker.patch('argparse.ArgumentParser.parse_args', mock_parser_parse_args)
        mock_parser_parse_args.return_value = Namespace(config_file=conf_file, ne=True, nd=False, s=False, l=0, o=0)
        mock_check_dependencies = MagicMock()
        mock_check_dependencies.return_value = "ERROR"
        mocker.patch('smfc.Service.check_dependencies', mock_check_dependencies)
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error
        del my_td

    @pytest.mark.parametrize("ipmi_command, mode_delay, level_delay, exit_code, error", [
        ('NON_EXIST', 0,  0,  8,  'Service.run() 12'),
        ('GOOD',      -1, 0,  8,  'Service.run() 13'),
        ('GOOD',      0,  -1, 8,  'Service.run() 14'),
        ('BAD',       0,  0,  8,  'Service.run() 15'),
        ('GOOD',      0,  0,  10, 'Service.run() 16')
    ])
    def test_run_810n(self, mocker:MockerFixture, ipmi_command: str, mode_delay: int, level_delay: int, exit_code: int,
                      error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
            - mock print(), pyudev.Context.__init__() functions
            - execute Service.run()
            - ASSERT: if sys.exit() did not return code 8 (Ipmi initialization error) or 10 (no enabled zone)
        """
        my_td = TestData()
        my_config = ConfigParser()
        if ipmi_command == 'NON_EXIST':
            ipmi_command = './non-existent-dir/non-existent-file'
        if ipmi_command == 'BAD':
            ipmi_command = my_td.create_command_file()
        if ipmi_command == 'GOOD':
            ipmi_command = my_td.create_ipmi_command()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: ipmi_command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(mode_delay),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(level_delay),
        }
        my_config[CpuZone.CS_CPU_ZONE] = {
            CpuZone.CV_CPU_ZONE_ENABLED: '0'
        }
        my_config[HdZone.CS_HD_ZONE] = {
            HdZone.CV_HD_ZONE_ENABLED: '0'
        }
        my_config[GpuZone.CS_GPU_ZONE] = {
            GpuZone.CV_GPU_ZONE_ENABLED: '0'
        }
        my_config[ConstZone.CS_CONST_ZONE] = {
            ConstZone.CV_CONST_ZONE_ENABLED: '0'
        }
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mocker.patch('pyudev.Context.__init__', MockedContextGood.__init__)
        sys.argv = ('smfc.py -o 0 -nd -ne -c ' + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error
        del my_td

    @pytest.mark.parametrize("exit_code, error", [
        (9, 'Service.run() 17')
    ])
    def test_run_9n(self, mocker:MockerFixture, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
            - mock print(), pyudev.Context.__init__() functions
            - execute Service.run()
            - ASSERT: if sys.exit() did not return code 9 (pyudev.Context() init error)
        """
        my_td = TestData()
        my_config = ConfigParser()
        ipmi_command = my_td.create_ipmi_command()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: ipmi_command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0',
        }
        my_config[CpuZone.CS_CPU_ZONE] = {
            CpuZone.CV_CPU_ZONE_ENABLED: '0'
        }
        my_config[HdZone.CS_HD_ZONE] = {
            HdZone.CV_HD_ZONE_ENABLED: '0'
        }
        my_config[GpuZone.CS_GPU_ZONE] = {
            GpuZone.CV_GPU_ZONE_ENABLED: '0'
        }
        my_config[ConstZone.CS_CONST_ZONE] = {
            ConstZone.CV_CONST_ZONE_ENABLED: '0'
        }
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mocker.patch('pyudev.Context.__init__', MockedContextError.__init__)
        sys.argv = ('smfc.py -o 0 -ne -nd -c ' + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error
        del my_td

    @pytest.mark.parametrize("cpuzone, hdzone, gpuzone, constzone, exit_code, error", [
        (True,  False, True,  False, 100, 'Service.run() 18'),
        (False, True,  False, True,  100, 'Service.run() 19'),
        (True,  False, True,  False, 100, 'Service.run() 20')
    ])
    def test_run_100p(self, mocker:MockerFixture, cpuzone: bool, hdzone: bool, gpuzone: bool, constzone: bool,
                      exit_code: int, error: str):
        """Positive unit test for Service.run() method. It contains the following steps:
            - mock print(), time.sleep() functions
            - execute smfc.run()
            - The main loop will be executed 10 times then exit with code 100
        """

        # pylint: disable=unused-argument
        def mocked_sleep(*args):
            """Mocked time.sleep() function. Exists at the 10th call."""
            self.sleep_counter += 1
            if self.sleep_counter >= 10:
                sys.exit(100)

        def mocked_cpuzone_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal my_td
            self.hwmon_path = my_td.cpu_files
            count = len(my_td.cpu_files)
            FanController.__init__(self, log, ipmi, f'{Ipmi.CPU_ZONE}', CpuZone.CS_CPU_ZONE, count, 1, 5,
                                  5, 0, 30, 60, 35, 100)

        def mocked_hdzone_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser, sudo: bool) -> None:
            nonlocal my_td
            nonlocal cmd_smart
            self.hd_device_names = my_td.hd_name_list
            self.hwmon_path = my_td.hd_files
            count = len(my_td.hd_files)
            self.sudo=sudo
            FanController.__init__(self, log, ipmi, f'{Ipmi.HD_ZONE}', HdZone.CS_HD_ZONE, count, 1, 5,
                                  2, 0, 32, 46, 35, 100)
            self.smartctl_path = cmd_smart
            self.standby_guard_enabled = True
            self.standby_hd_limit = 1
            self.standby_array_states = [False] * self.count
            self.standby_flag = False
            self.standby_change_timestamp = time.monotonic()

        def mocked_gpuzone_init(self, log: Log, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal my_td
            nonlocal cmd_nvidia
            self.gpu_device_ids = [0]
            count = 1
            self.nvidia_smi_path = cmd_nvidia
            self.nvidia_smi_called = 0
            FanController.__init__(self, log, ipmi, '2', GpuZone.CS_GPU_ZONE, count, 1, 5,
                                  2, 0, 45, 70, 35, 100)

        def mocked_constzone_init(self, log: Log, ipmi: Ipmi, config: ConfigParser) -> None:
            self.ipmi = ipmi
            self.log = log
            self.name = ConstZone.CS_CONST_ZONE
            self.ipmi_zone = [Ipmi.HD_ZONE]
            self.polling = 30
            self.level = 50
            self.last_time = 0
        # pragma pylint: enable=unused-argument

        my_td = TestData()
        # Force mode initial fan mode 0 for setting new FULL mode during the test.
        cmd_ipmi = my_td.create_command_file('echo "0"')
        cmd_smart = my_td.create_smart_command()
        #                     create_command_file('echo "ACTIVE"'))
        cmd_nvidia = my_td.create_nvidia_smi_command(1)
        my_td.create_cpu_data(1)
        my_td.create_hd_data(8)
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: cmd_ipmi,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0'
        }
        my_config[CpuZone.CS_CPU_ZONE] = {
            CpuZone.CV_CPU_ZONE_ENABLED: str(cpuzone),
            CpuZone.CV_CPU_ZONE_TEMP_CALC: '1',
            CpuZone.CV_CPU_ZONE_STEPS: '5',
            CpuZone.CV_CPU_ZONE_SENSITIVITY: '5',
            CpuZone.CV_CPU_ZONE_POLLING: '0',
            CpuZone.CV_CPU_ZONE_MIN_TEMP: '30',
            CpuZone.CV_CPU_ZONE_MAX_TEMP: '60',
            CpuZone.CV_CPU_ZONE_MIN_LEVEL: '35',
            CpuZone.CV_CPU_ZONE_MAX_LEVEL: '100',
        }
        my_config[HdZone.CS_HD_ZONE] = {
            HdZone.CV_HD_ZONE_ENABLED: str(hdzone),
            HdZone.CV_HD_ZONE_TEMP_CALC: '1',
            HdZone.CV_HD_ZONE_STEPS: '4',
            HdZone.CV_HD_ZONE_SENSITIVITY: '2',
            HdZone.CV_HD_ZONE_POLLING: '0',
            HdZone.CV_HD_ZONE_MIN_TEMP: '30',
            HdZone.CV_HD_ZONE_MAX_TEMP: '45',
            HdZone.CV_HD_ZONE_MIN_LEVEL: '35',
            HdZone.CV_HD_ZONE_MAX_LEVEL: '100',
            HdZone.CV_HD_ZONE_HD_NAMES: my_td.hd_names,
            HdZone.CV_HD_ZONE_SMARTCTL_PATH: cmd_smart,
            HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED: '1',
            HdZone.CV_HD_ZONE_STANDBY_HD_LIMIT: '2'
        }
        my_config[GpuZone.CS_GPU_ZONE] = {
            GpuZone.CV_GPU_ZONE_ENABLED: str(gpuzone),
            GpuZone.CV_GPU_IPMI_ZONE: '2',
            GpuZone.CV_GPU_ZONE_TEMP_CALC: '1',
            GpuZone.CV_GPU_ZONE_STEPS: '4',
            GpuZone.CV_GPU_ZONE_SENSITIVITY: '2',
            GpuZone.CV_GPU_ZONE_POLLING: '0',
            GpuZone.CV_GPU_ZONE_MIN_TEMP: '45',
            GpuZone.CV_GPU_ZONE_MAX_TEMP: '70',
            GpuZone.CV_GPU_ZONE_MIN_LEVEL: '35',
            GpuZone.CV_GPU_ZONE_MAX_LEVEL: '100',
            GpuZone.CV_GPU_ZONE_GPU_IDS: '0',
            GpuZone.CV_GPU_ZONE_NVIDIA_SMI_PATH: cmd_nvidia,
        }
        my_config[ConstZone.CS_CONST_ZONE] = {
            ConstZone.CV_CONST_ZONE_ENABLED: str(constzone),
            ConstZone.CV_CONST_IPMI_ZONE: '2',
            ConstZone.CV_CONST_ZONE_POLLING: '0',
            ConstZone.CV_CONST_ZONE_LEVEL: '35'
        }
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_time_sleep = MagicMock()
        mock_time_sleep.side_effect = mocked_sleep
        mocker.patch('time.sleep', mock_time_sleep)
        mocker.patch('pyudev.Context.__init__', MockedContextGood.__init__)
        mocker.patch('smfc.CpuZone.__init__', mocked_cpuzone_init)
        mocker.patch('smfc.HdZone.__init__', mocked_hdzone_init)
        mocker.patch('smfc.GpuZone.__init__', mocked_gpuzone_init)
        mocker.patch('smfc.ConstZone.__init__', mocked_constzone_init)
        self.sleep_counter = 0
        sys.argv = ('smfc.py -o 0 -l 4 -ne -nd -c ' + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error
        del my_td


# End.
