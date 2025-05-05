#!/usr/bin/env python3
#
#   test_05_hdzone.py (C) 2021-2025, Peter Sulyok
#   Unit tests for smfc.HdZone() class.
#
import random
import subprocess
import os
import time
from configparser import ConfigParser
from typing import List, Any
import pytest
import pyudev
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, HdZone
from .test_00_data import TestData, MockDevices, factory_mockdevice

class TestHdZone:
    """Unit test class for smfc.HdZone() class"""

    @pytest.mark.parametrize(
        "count, ipmi_zone, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, sb_limit, "
        "sudo, error", [
        # Test valid parameters (hd=1 case is not tested because it turns off standby guard).
        (1, '0', FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, True,  'HdZone.__init__() 1'),
        (2, '1', FanController.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 2, False, 'HdZone.__init__() 2'),
        (4, '2', FanController.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 4, True,  'HdZone.__init__() 3'),
        (8, '3', FanController.CALC_MAX, 4, 2, 2, 32, 48, 35, 100, 6, False, 'HdZone.__init__() 4')
    ])
    def test_init_p1(self, mocker: MockerFixture, count: int, ipmi_zone: str, temp_calc: int, steps: int,
                     sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                     max_level: int, sb_limit: int, sudo: bool, error: str):
        """Positive unit test for HdZone.__init__() method. It contains the following steps:
            - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
            - initialize a Config, Log, Context, Ipmi, and HdZone classes
            - ASSERT: if the HdZone class attributes are different from values passed to __init__
        """
        my_td = TestData()
        cmd_smart = my_td.create_command_file('echo "ACTIVE"')
        my_td.create_hd_data(count)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mocker.patch.object(pyudev.Device, '__new__', new_callable=factory_mockdevice)
        mocker.patch('pyudev.Devices.from_device_file', MockDevices.from_device_file)
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        mocker.patch('smfc.HdZone._exec_smartctl', mock_ipmi_exec)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.hd_files)
        mocker.patch('smfc.FanController.get_hwmon_path', mock_fancontroller_gethwmonpath)
        my_config = ConfigParser()
        my_config[HdZone.CS_HD_ZONE] = {
            HdZone.CV_HD_ZONE_ENABLED: '1',
            HdZone.CV_HD_IPMI_ZONE: ipmi_zone,
            HdZone.CV_HD_ZONE_TEMP_CALC: str(temp_calc),
            HdZone.CV_HD_ZONE_STEPS: str(steps),
            HdZone.CV_HD_ZONE_SENSITIVITY: str(sensitivity),
            HdZone.CV_HD_ZONE_POLLING: str(polling),
            HdZone.CV_HD_ZONE_MIN_TEMP: str(min_temp),
            HdZone.CV_HD_ZONE_MAX_TEMP: str(max_temp),
            HdZone.CV_HD_ZONE_MIN_LEVEL: str(min_level),
            HdZone.CV_HD_ZONE_MAX_LEVEL: str(max_level),
            HdZone.CV_HD_ZONE_HD_NAMES: my_td.hd_names,
            HdZone.CV_HD_ZONE_SMARTCTL_PATH: cmd_smart,
            HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED: '1',
            HdZone.CV_HD_ZONE_STANDBY_HD_LIMIT: str(sb_limit)
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_hdzone = HdZone(my_log, my_udevc, my_ipmi, my_config, sudo)
        assert my_hdzone.ipmi_zone == [int(s) for s in ipmi_zone.split(',' if ',' in ipmi_zone else ' ')], error
        assert my_hdzone.name == HdZone.CS_HD_ZONE, error
        assert my_hdzone.count == count, error
        assert my_hdzone.sudo == sudo, error
        assert my_hdzone.temp_calc == temp_calc, error
        assert my_hdzone.steps == steps, error
        assert my_hdzone.sensitivity == sensitivity, error
        assert my_hdzone.polling == polling, error
        assert my_hdzone.min_temp == min_temp, error
        assert my_hdzone.max_temp == max_temp, error
        assert my_hdzone.min_level == min_level, error
        assert my_hdzone.max_level == max_level, error
        assert my_hdzone.hd_device_names == my_td.hd_name_list, error
        assert my_hdzone.smartctl_path == cmd_smart, error
        assert my_hdzone.hwmon_path == my_td.hd_files, error
        if count > 1:
            assert my_hdzone.standby_hd_limit == sb_limit, error
            assert my_hdzone.standby_guard_enabled is True, error
        del my_td

    @pytest.mark.parametrize("error", [
        'HdZone.__init__() 5'
    ])
    def test_init_p2(self, mocker: MockerFixture, error: str):
        """Positive unit test for HdZone.__init__() method. It contains the following steps:
            - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
            - initialize a Config, Log, Context, Ipmi, and HdZone classes
            - ASSERT: if the HdZone class attributes are different from the default configuration values
        """
        my_td = TestData()
        count = 4
        my_td.create_hd_data(count)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mocker.patch.object(pyudev.Device, '__new__', new_callable=factory_mockdevice)
        mocker.patch('pyudev.Devices.from_device_file', MockDevices.from_device_file)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.hd_files)
        mocker.patch('smfc.FanController.get_hwmon_path', mock_fancontroller_gethwmonpath)
        my_config = ConfigParser()
        my_config[HdZone.CS_HD_ZONE] = {
            HdZone.CV_HD_ZONE_ENABLED: '1',
            HdZone.CV_HD_ZONE_HD_NAMES: my_td.hd_names
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_hdzone = HdZone(my_log, my_udevc, my_ipmi, my_config, False)
        assert my_hdzone.log == my_log, error
        assert my_hdzone.ipmi == my_ipmi
        assert my_hdzone.ipmi_zone == [Ipmi.HD_ZONE], error
        assert my_hdzone.name == HdZone.CS_HD_ZONE, error
        assert my_hdzone.count == count, error
        assert my_hdzone.sudo is False
        assert my_hdzone.temp_calc == FanController.CALC_AVG, error
        assert my_hdzone.steps == 4, error
        assert my_hdzone.sensitivity == 2, error
        assert my_hdzone.polling == 10, error
        assert my_hdzone.min_temp == 32, error
        assert my_hdzone.max_temp == 46, error
        assert my_hdzone.min_level == 35, error
        assert my_hdzone.max_level == 100, error
        assert my_hdzone.hd_device_names == my_td.hd_name_list, error
        assert my_hdzone.smartctl_path == '/usr/sbin/smartctl', error
        assert my_hdzone.hwmon_path == my_td.hd_files, error
        del my_td

    @pytest.mark.parametrize(
        "count, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, sb_limit, error", [
        # hd_names= not specified (count = 0)
        (0,     FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2,  'HdZone.__init__() 6'),
        # standby_hd_limit < 0
        (2,     FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, -1, 'HdZone.__init__() 7'),
        # standby_hd_limit > count
        (2,     FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 4,  'HdZone.__init__() 8'),
        # Invalid device name (count == 100)
        (100,   FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 4,  'HdZone.__init__() 9')
    ])
    def test_init_n1(self, mocker: MockerFixture, count: int, temp_calc: int, steps: int, sensitivity: float,
                     polling: float, min_temp: float, max_temp: float, min_level: int, max_level: int, sb_limit: int,
                     error: str):
        """Negative unit test for HdZone.__init__() method. It contains the following steps:
            - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if no assertion is raised for invalid values at initialization
        """
        my_td = TestData()
        cmd_smart = my_td.create_command_file('echo "ACTIVE"')
        if count == 100:
            my_td.create_hd_data(1)
            my_td.hd_names='raise\n'
        else:
            my_td.create_hd_data(count)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mocker.patch.object(pyudev.Device, '__new__', new_callable=factory_mockdevice)
        mocker.patch('pyudev.Devices.from_device_file', MockDevices.from_device_file)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.hd_files)
        mocker.patch('smfc.FanController.get_hwmon_path', mock_fancontroller_gethwmonpath)
        my_config = ConfigParser()
        my_config[HdZone.CS_HD_ZONE] = {
            HdZone.CV_HD_ZONE_ENABLED: '1',
            HdZone.CV_HD_ZONE_TEMP_CALC: str(temp_calc),
            HdZone.CV_HD_ZONE_STEPS: str(steps),
            HdZone.CV_HD_ZONE_SENSITIVITY: str(sensitivity),
            HdZone.CV_HD_ZONE_POLLING: str(polling),
            HdZone.CV_HD_ZONE_MIN_TEMP: str(min_temp),
            HdZone.CV_HD_ZONE_MAX_TEMP: str(max_temp),
            HdZone.CV_HD_ZONE_MIN_LEVEL: str(min_level),
            HdZone.CV_HD_ZONE_MAX_LEVEL: str(max_level),
            HdZone.CV_HD_ZONE_HD_NAMES: my_td.hd_names,
            HdZone.CV_HD_ZONE_SMARTCTL_PATH: cmd_smart,
            HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED: '1',
            HdZone.CV_HD_ZONE_STANDBY_HD_LIMIT: str(sb_limit)
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(Exception) as cm:
            HdZone(my_log, my_udevc, my_ipmi, my_config, False)
        assert cm.type is ValueError, error
        del my_td

    #pylint: disable=protected-access
    @pytest.mark.parametrize("args, sudo, error", [
        (['-a', '/dev/sda'],                    True,  'HdZone._exec_smartctl() 1'),
        (['-a', '/dev/sda'],                    False, 'HdZone._exec_smartctl() 2'),
        (['-i', '-n', 'standby', '/dev/sda'],   True,  'HdZone._exec_smartctl() 3'),
        (['-i', '-n', 'standby', '/dev/sda'],   False, 'HdZone._exec_smartctl() 4'),
        (['-s', '/dev/sda'],                    True,  'HdZone._exec_smartctl() 5'),
        (['-s', '/dev/sda'],                    False, 'HdZone._exec_smartctl() 6')
    ])
    def test_exec_smartctl_p(self, mocker: MockerFixture, args:List[str], sudo: bool, error: str):
        """Positive unit test for HdZone._exec_smartctl() method. It contains the following steps:
            - mock subprocess.run() function
            - initialize an empty HdZone class
            - call HdZone._exec_smartctl() method
            - ASSERT: if subprocess.run() called different from specified argument list
        """
        expected_args: List[str]

        my_hdzone = HdZone.__new__(HdZone)
        my_hdzone.smartctl_path = 'smartctl'
        my_hdzone.sudo = sudo
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value=subprocess.CompletedProcess([], returncode=0, stdout='', stderr='')
        mocker.patch('subprocess.run', mock_subprocess_run)
        my_hdzone._exec_smartctl(args)
        expected_args = []
        if sudo:
            expected_args.append('sudo')
        expected_args.append(my_hdzone.smartctl_path)
        expected_args.extend(args)
        mock_subprocess_run.assert_called_with(expected_args, capture_output=True, check=False, text=True)
        assert mock_subprocess_run.call_count == 1, error

    #pylint: disable=R0801
    @pytest.mark.parametrize("smartctl_command, sudo, rc, exception, error", [
        # The real subprocess.run() executed (without sudo)
        ('/nonexistent/command', False, 0, FileNotFoundError, 'HdZone._exec_smartctl() 7'),
        # The mocked subprocess.run() executed and returns non-zero return code
        ('',                     True,  1, RuntimeError,      'HdZone._exec_smartctl() 8')
    ])
    def test_exec_smartctl_n(self, mocker: MockerFixture, smartctl_command, sudo: bool, rc: int, exception: Any,
                             error: str):
        """Negative unit test for HdZone._exec_smartctl() method. It contains the following steps:
            - mock subprocess.run() function if needed
            - initialize an empty HdZone class
            - call HdZone._exec_smartctl() method
            - ASSERT: if no assertion was raised
        """
        if rc:
            mock_subprocess_run = MagicMock()
            mocker.patch('subprocess.run', mock_subprocess_run)
            mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=rc,
                                                                           stderr='sudo: smartctl: command not found')
        my_hdzone = HdZone.__new__(HdZone)
        my_hdzone.smartctl_path = smartctl_command
        my_hdzone.sudo = sudo
        with pytest.raises(Exception) as cm:
            my_hdzone._exec_smartctl(['-a', '/dev/sda'])
        assert cm.type == exception, error
    # pylint: enable=R0801

    @pytest.mark.parametrize("count, temperatures, error", [
        (1, [32],                               'HdZone._get_nth_temp() 1'),
        (2, [33, 34],                           'HdZone._get_nth_temp() 2'),
        (4, [33, 34, 35, 38],                   'HdZone._get_nth_temp() 3'),
        (8, [33, 34, 35, 38, 36, 37, 31, 30],   'HdZone._get_nth_temp() 4')
    ])
    def test_get_ntf_temp_p1(self, mocker: MockerFixture, count: int, temperatures: List[float], error: str):
        """Positive unit test for HdZone._get_nth_temp() method. It contains the following steps:
            - mock print() function
            - initialize an empty HdZone class
            - ASSERT: if the read temperature (from HWMON) is different from the expected value
        """
        my_td = TestData()
        my_td.create_hd_data(count, temperatures)
        my_hdzone = HdZone.__new__(HdZone)
        my_hdzone.hwmon_path = my_td.hd_files
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        for i in range(count):
            temp = my_hdzone._get_nth_temp(i)
            assert temp == temperatures[i], error
        del my_td

    @pytest.mark.parametrize("count, temperatures, error", [
        (1, [32],                               'HdZone._get_nth_temp() 5'),
        (2, [33, 34],                           'HdZone._get_nth_temp() 6'),
        (4, [33, 34, 35, 38],                   'HdZone._get_nth_temp() 7'),
        (8, [33, 34, 35, 38, 36, 37, 31, 30],   'HdZone._get_nth_temp() 8')
    ])
    def test_get_nth_temp_p2(self, mocker: MockerFixture, count: int, temperatures: List[float], error: str):
        """Positive unit test for HdZone._get_nth_temp() method. It contains the following steps:
            - mock print(), subprocess.run() functions
            - initialize an empty HdZone class
            - ASSERT: if the read temperature (from smartctl) is different from the expected value
        """
        #pylint: disable=line-too-long
        smartctl_output = [
            # SCSI disks
            "smartctl 7.3 2022-02-28 r5338 [x86_64-linux-6.1.0-32-amd64] (local build)\n"
            "Copyright (C) 2002-22, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "Current Drive Temperature:     XX C\n",

            # SATA SMART attributes 1
            "smartctl 7.3 2022-02-28 r5338 [x86_64-linux-6.1.0-32-amd64] (local build)\n"
            "Copyright (C) 2002-22, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "190 Airflow_Temperature_Cel 0x0032   075   045   000    Old_age   Always       -       XX\n",

            # SATA SMART attributes 2
            "smartctl 7.3 2022-02-28 r5338 [x86_64-linux-6.1.0-32-amd64] (local build)\n"
            "Copyright (C) 2002-22, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "194 Temperature_Celsius     0x0002   232   232   000    Old_age   Always       -       XX (Min/Max 17/45)\n"
        ]
        # pylint: enable=line-too-long
        my_td = TestData()
        my_td.create_hd_data(count, temperatures)
        my_hdzone = HdZone.__new__(HdZone)
        my_hdzone.hwmon_path = my_td.hd_name_list
        my_hdzone.hd_device_names = my_td.hd_name_list
        my_hdzone.hwmon_path = [''] * count
        my_hdzone.sudo=False
        my_hdzone.smartctl_path = '/usr/sbin/smartctl'
        mock_exec_smartclt = MagicMock()
        mock_exec_smartclt.return_value = subprocess.CompletedProcess([], returncode=0, stdout=smartctl_output)
        mocker.patch('smfc.HdZone._exec_smartctl', mock_exec_smartclt)
        for i in range(count):
            s = smartctl_output[random.randint(0, 2)].replace('XX', str(temperatures[i]))
            mock_exec_smartclt.return_value = subprocess.CompletedProcess([], returncode=0, stdout=s)
            assert my_hdzone._get_nth_temp(i) == temperatures[i], error
        del my_hdzone
        del my_td

    @pytest.mark.parametrize("operation, exception, error", [
        # 0. hwmon - FileNotFoundError
        (0, FileNotFoundError,  'HdZone._get_nth_temp() 9'),
        # 1. hwmon - IndexError
        (1, IndexError,         'HdZone._get_nth_temp() 10'),
        # 2. hwmon - ValueError
        (2, ValueError,         'HdZone._get_nth_temp() 11'),
        # 3. smartctl - FileNotFoundError
        (3, FileNotFoundError,  'HdZone._get_nth_temp() 12'),
        # 4. smartctl - IndexError
        (4, IndexError,         'HdZone._get_nth_temp() 13'),
        # 5. smartctl - ValueError
        (5, ValueError,         'HdZone._get_nth_temp() 14')
    ])
    def test_get_nth_temp_n1(self, mocker: MockerFixture, operation: int, exception: Any, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), subprocess.run() functions
            - initialize an empty HdZone class
            - call HdZone._get_nth_temp()
            - ASSERT: if no assertion raised
        """
        index = 0
        my_td = TestData()
        my_td.create_hd_data(1, [32])
        my_hdzone = HdZone.__new__(HdZone)
        my_hdzone.hwmon_path = my_td.hd_files
        my_hdzone.hd_device_names = my_td.hd_name_list
        my_hdzone.count = 1
        my_hdzone.sudo = False
        # FileNotFoundError: invalid file name with hwmon
        if operation == 0:
            my_hdzone.hwmon_path[0] = '/tmp/non_existent_dir/non_existent_file'
        # IndexError: index error with hwmon
        elif operation == 1:
            index = 1000
        # ValueError: invalid temperature with hwmon
        elif operation == 2:
            os.system('echo "invalid value" >'+my_hdzone.hwmon_path[0])
        # FileNotFoundError: invalid file name with smartctl
        elif operation == 3:
            my_hdzone.hwmon_path[0] = ''
            my_hdzone.smartctl_path = '/tmp/non_existent_dir/non_existent_file'
        # IndexError: index error with smartctl
        elif operation == 4:
            my_hdzone.hwmon_path[0] = ''
            index = 1000
        # ValueError: temperature not found in smartctl's output
        elif operation == 5:
            my_hdzone.hwmon_path[0] = ''
            my_hdzone.smartctl_path = '/usr/sbin/smartctl'
            mock_subprocess_run = MagicMock()
            mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0,
                                                                           stdout='invalid\ninvalid\ninvalid\n')
            mocker.patch('subprocess.run', mock_subprocess_run)
        with pytest.raises(Exception) as cm:
            my_hdzone._get_nth_temp(index)
        assert cm.type == exception, error
        del my_td
    #pylint: enable=protected-access

    @pytest.mark.parametrize("states, result, error", [
        ([True, True, True, True, True, True, True, True],         'SSSSSSSS', 'hz get_standby_state_str 1'),
        ([False, False, False, False, False, False, False, False], 'AAAAAAAA', 'hz get_standby_state_str 2'),
        ([True, False, False, False, False, False, False, False],  'SAAAAAAA', 'hz get_standby_state_str 3'),
        ([False, True, False, False, False, False, False, False],  'ASAAAAAA', 'hz get_standby_state_str 4'),
        ([False, False, True, False, False, False, False, False],  'AASAAAAA', 'hz get_standby_state_str 5'),
        ([False, False, False, True, False, False, False, False],  'AAASAAAA', 'hz get_standby_state_str 6'),
        ([False, False, False, False, True, False, False, False],  'AAAASAAA', 'hz get_standby_state_str 7'),
        ([False, False, False, False, False, True, False, False],  'AAAAASAA', 'hz get_standby_state_str 8'),
        ([False, False, False, False, False, False, True, False],  'AAAAAASA', 'hz get_standby_state_str 9'),
        ([False, False, False, False, False, False, False, True],  'AAAAAAAS', 'hz get_standby_state_str 10')
    ])
    def test_get_standby_state_str(self, states: List[bool], result: str, error: str):
        """Positive unit test for HdZone.get_standby_state_str() method. It contains the following steps:
            - initialize an empty HdZone class
            - calls HdZone.get_standby_state_str()
            - ASSERT: if HdZone.get_standby_state_str() returns different from expected result
        """
        my_hdzone = HdZone.__new__(HdZone)
        my_hdzone.count = 8
        my_hdzone.standby_array_states = states
        assert my_hdzone.get_standby_state_str() == result, error
        del my_hdzone

    @pytest.mark.parametrize("states, in_standby, error", [
        ([True, True, True, True, True, True, True, True],          8, 'HdZone.check_standby_state() 1'),
        ([False, True, True, True, True, True, True, True],         7, 'HdZone.check_standby_state() 2'),
        ([True, False, True, True, True, True, True, True],         7, 'HdZone.check_standby_state() 3'),
        ([True, True, False, True, True, True, True, True],         7, 'HdZone.check_standby_state() 4'),
        ([True, True, True, False, True, True, True, True],         7, 'HdZone.check_standby_state() 5'),
        ([True, True, True, True, False, True, True, True],         7, 'HdZone.check_standby_state() 6'),
        ([True, True, True, True, True, False, True, True],         7, 'HdZone.check_standby_state() 7'),
        ([True, True, True, True, True, True, False, True],         7, 'HdZone.check_standby_state() 8'),
        ([True, True, True, True, True, True, True, False],         7, 'HdZone.check_standby_state() 9'),
        ([True, False, True, True, True, True, True, False],        6, 'HdZone.check_standby_state() 10'),
        ([True, False, True, True, False, True, True, False],       5, 'HdZone.check_standby_state() 11'),
        ([False, False, True, True, False, True, True, False],      4, 'HdZone.check_standby_state() 12'),
        ([False, False, True, False, False, True, True, False],     3, 'HdZone.check_standby_state() 13'),
        ([False, False, True, False, False, True, False, False],    2, 'HdZone.check_standby_state() 14'),
        ([False, False, False, False, False, True, False, False],   1, 'HdZone.check_standby_state() 15'),
        ([False, False, False, False, False, False, False, False],  0, 'HdZone.check_standby_state() 16')
    ])
    def test_check_standby_state(self, mocker:MockerFixture, states: List[bool], in_standby: int, error: str):
        """Positive unit test for HdZone.check_standby_state() method. It contains the following steps:
            - mock print(), HdZone._exec_smartctl() functions
            - initialize an empty HdZone classes
            - call HdZone.check_standby_state()
            - ASSERT: if result is different from the expected one
        """
        smartctl_output = [

            # Device in STANDBY mode.
            "smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.10.0-0.bpo.5-amd64] (local build)\n"
            "Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "Device is in STANDBY mode, exit(2)\n",

            # Device is ACTIVE.
            "smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.10.0-0.bpo.5-amd64] (local build)\n"
            "Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "=== START OF INFORMATION SECTION ===\n"
            "Model Family:     Samsung based SSDs\n"
            "Device Model:     Samsung SSD 870 QVO 8TB\n"
            "Serial Number:    S5SSNG0NB01828M\n"
            "LU WWN Device Id: 5 002538 f70b0ee2f\n"
            "Firmware Version: SVQ01B6Q\n"
            "User Capacity:    8,001,563,222,016 bytes [8.00 TB]\n"
            "Sector Size:      512 bytes logical/physical\n"
            "Rotation Rate:    Solid State Device\n"
            "Form Factor:      2.5 inches\n"
            "TRIM Command:     Available, deterministic, zeroed\n"
            "Device is:        In smartctl database [for details use: -P show]\n"
            "ATA Version is:   ACS-4 T13/BSR INCITS 529 revision 5\n"
            "SATA Version is:  SATA 3.3, 6.0 Gb/s (current: 6.0 Gb/s)\n"
            "Local Time is:    Sat May 15 14:26:26 2021 CEST\n"
            "SMART support is: Available - device has SMART capability.\n"
            "SMART support is: Enabled\n"
            "Power mode is:    ACTIVE or IDLE\n"
            "\n"
        ]
        results: List[subprocess.CompletedProcess] = []

        count = 8
        for i in range(count):
            results.append(subprocess.CompletedProcess([], returncode=0, stdout=smartctl_output[0 if states[i] else 1]))
        my_td = TestData()
        my_td.create_hd_data(count)
        my_hdzone = HdZone.__new__(HdZone)
        my_hdzone.count = count
        my_hdzone.sudo=False
        my_hdzone.hd_device_names = my_td.hd_name_list
        my_hdzone.hwmon_path = [''] * count
        my_hdzone.smartctl_path = '/usr/sbin/smartctl'
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_hdzone.log = my_log
        my_hdzone.standby_array_states = [True] * count
        mock_hdzone_exec_smartclt = MagicMock()
        mock_hdzone_exec_smartclt.side_effect = iter(results)
        mocker.patch('smfc.HdZone._exec_smartctl', mock_hdzone_exec_smartclt)
        assert my_hdzone.check_standby_state() == in_standby, error
        del my_td

    @pytest.mark.parametrize("states, count, error", [
        ([False, False, False, False, False, False, False, False],  8, 'HdZone.go_standby_state() 1'),
        ([True, False, False, False, False, False, False, False],   7, 'HdZone.go_standby_state() 2'),
        ([True, True, False, False, False, False, False, False],    6, 'HdZone.go_standby_state() 3'),
        ([True, True, True, False, False, False, False, False],     5, 'HdZone.go_standby_state() 4'),
        ([True, True, True, True, False, False, False, False],      4, 'HdZone.go_standby_state() 5'),
        ([True, True, True, True, True, False, False, False],       3, 'HdZone.go_standby_state() 6'),
        ([True, True, True, True, True, True, False, False],        2, 'HdZone.go_standby_state() 7'),
        ([True, True, True, True, True, True, True, False],         1, 'HdZone.go_standby_state() 8'),
        ([True, True, True, True, True, True, True, True],          0, 'HdZone.go_standby_state() 9')
    ])
    def test_go_standby_state(self, mocker: MockerFixture, states: List[bool], count: int, error: str):
        """Positive unit test for HdZone.go_standby_state() method. It contains the following steps:
            - mock HdZone._exec_smartctl() function
            - initialize an empty HdZone classes
            - calls HdZone.go_standby_state()
            - ASSERT: if the array state is not in fully standby
        """
        my_td = TestData()
        my_td.create_hd_data(8)
        my_hdzone = HdZone.__new__(HdZone)
        my_hdzone.count = 8
        my_hdzone.sudo = False
        my_hdzone.hd_device_names = my_td.hd_name_list
        my_hdzone.smartctl_path = '/usr/sbin/smartctl'
        my_hdzone.standby_array_states = states
        mock_exec_smartctl = MagicMock()
        mock_exec_smartctl.return_value = subprocess.CompletedProcess([], returncode=0)
        mocker.patch('smfc.HdZone._exec_smartctl', mock_exec_smartctl)
        my_hdzone.go_standby_state()
        assert mock_exec_smartctl.call_count == count, error
        assert my_hdzone.standby_array_states == [True, True, True, True, True, True, True, True], error
        del my_td

    @pytest.mark.parametrize("old_state, states, new_state, error", [
        # 1. No state changes.
        (False, [False, False, False, False, False, False, False, False],   False, 'HdZone.run_standby_guard() 1'),
        (True,  [True, True, True, True, True, True, True, True],           True,  'HdZone.run_standby_guard() 2'),
        # 2. change from ACTIVE to STANDBY.
        (False, [False, True, False, False, False, False, False, False],    True,  'HdZone.run_standby_guard() 3'),
        (False, [False, True, False, True, False, False, False, False],     True,  'HdZone.run_standby_guard() 4'),
        (False, [True, True, True, True, True, True, True, True],           True,  'HdZone.run_standby_guard() 5'),
        # 3. change from STANDBY to ACTIVE.
        (True,  [False, False, False, False, False, False, False, False],   False, 'HdZone.run_standby_guard() 6'),
        (True,  [True, False, False, True, True, True, True, True],         False, 'HdZone.run_standby_guard() 7')
    ])
    def test_run_standby_guard(self, mocker:MockerFixture, old_state: bool, states: List[bool], new_state: bool,
                               error: str):
        """Positive unit test for HdZone.run_standby_guard() method. It contains the following steps:
            - mock HdZone._exec_smartctl() function
            - initialize a Log and an empty HdZone classes
            - calls HdZone.run_standby_guard()
            - ASSERT: if the expected standby_flags are different
        """
        my_td = TestData()
        my_td.create_hd_data(8)
        my_hdzone = HdZone.__new__(HdZone)
        my_hdzone.count = 8
        my_hdzone.hd_device_names = my_td.hd_name_list
        my_hdzone.smartctl_path = '/usr/sbin/smartctl'
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_hdzone.log = my_log
        my_hdzone.go_standby_state = MagicMock(name='go_standby_state')
        my_hdzone.check_standby_state = MagicMock(name='check_standby_state')
        my_hdzone.check_standby_state.return_value = states.count(True)
        my_hdzone.standby_array_states = states
        my_hdzone.standby_flag = old_state
        my_hdzone.standby_hd_limit = 1
        my_hdzone.standby_change_timestamp = time.monotonic()
        mock_exec_smartctl = MagicMock()
        mock_exec_smartctl.return_value = subprocess.CompletedProcess([], returncode=0)
        mocker.patch('smfc.HdZone._exec_smartctl', mock_exec_smartctl)
        my_hdzone.run_standby_guard()
        assert my_hdzone.standby_flag == new_state, error
        del my_hdzone
        del my_td


# End.
