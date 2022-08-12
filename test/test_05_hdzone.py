#!/usr/bin/python3
#
#   test_05_hdzone.py (C) 2021-2022, Peter Sulyok
#   Unit tests for smfc.HdZone() class.
#
import configparser
import os
import subprocess
import unittest
import glob
from typing import List
from unittest.mock import patch, MagicMock
from test_00_data import TestData
from smfc import Log, Ipmi, FanController, HdZone


class HdZoneTestCase(unittest.TestCase):
    """Unit test class for smfc.HdZone() class"""

    def pt_init_p1(self, count: int, temp_calc: int, steps: int, sensitivity: float, polling: float,
                   min_temp: float, max_temp: float, min_level: int, max_level: int, sb_limit: int,
                   hwmon_path: str, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print() functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete the instances
        """
        my_td = TestData()
        cmd_ipmi = my_td.create_command_file('echo " 01"')
        cmd_smart = my_td.create_command_file('echo "ACTIVE"')
        hd_names = my_td.get_hd_names(count)
        mock_print = MagicMock()
        with patch('builtins.print', mock_print):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd_ipmi,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'count': str(count),
                'temp_calc': str(temp_calc),
                'steps': str(steps),
                'sensitivity': str(sensitivity),
                'polling': str(polling),
                'min_temp': str(min_temp),
                'max_temp': str(max_temp),
                'min_level': str(min_level),
                'max_level': str(max_level),
                'hd_names': hd_names,
                'hwmon_path': hwmon_path,
                'standby_guard_enabled': '1',
                'standby_hd_limit': str(sb_limit),
                'smartctl_path': cmd_smart
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
        self.assertEqual(my_hdzone.ipmi_zone, Ipmi.HD_ZONE, error)
        self.assertEqual(my_hdzone.name, "HD zone", error)
        self.assertEqual(my_hdzone.count, count, error)
        self.assertEqual(my_hdzone.temp_calc, temp_calc, error)
        self.assertEqual(my_hdzone.steps, steps, error)
        self.assertEqual(my_hdzone.sensitivity, sensitivity, error)
        self.assertEqual(my_hdzone.polling, polling, error)
        self.assertEqual(my_hdzone.min_temp, min_temp, error)
        self.assertEqual(my_hdzone.max_temp, max_temp, error)
        self.assertEqual(my_hdzone.min_level, min_level, error)
        self.assertEqual(my_hdzone.max_level, max_level, error)
        self.assertEqual(my_hdzone.hd_device_names, my_td.create_normalized_path_list(hd_names), error)
        self.assertEqual(my_hdzone.hwmon_path, my_td.create_normalized_path_list(hwmon_path), error)
        self.assertEqual(my_hdzone.standby_hd_limit, sb_limit, error)
        self.assertEqual(my_hdzone.smartctl_path, cmd_smart, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def pt_init_p2(self, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run(), glob.glob(), os.listdir() functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if the class attributes contain different values than default configuration values
            - delete all instances
        """

        # Mock function for glob.glob().
        def mocked_glob(file: str, *args, **kwargs):
            if file.startswith('/sys/class/scsi_disk'):
                file = my_td.td_dir + file
            return original_glob(file, *args, **kwargs)

        # Mock function for os.listdir().
        def mocked_listdir(dir_str: str):
            if dir_str.startswith('/sys/class/scsi_disk'):
                dir_str = my_td.td_dir + dir_str
            return original_listdir(dir_str)

        my_td = TestData()
        command = my_td.create_command_file()
        hwmon_path = my_td.get_hd_1()
        hd_names = my_td.get_hd_names(1)
        original_glob = glob.glob
        original_listdir = os.listdir
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_glob = MagicMock(side_effect=mocked_glob)
        mock_listdir = MagicMock(side_effect=mocked_listdir)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run), \
             patch('glob.glob', mock_glob), \
             patch('os.listdir', mock_listdir):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hd_names': hd_names
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_hdzone.count, 1, error)
            self.assertEqual(my_hdzone.temp_calc, FanController.CALC_AVG, error)
            self.assertEqual(my_hdzone.steps, 4, error)
            self.assertEqual(my_hdzone.sensitivity, 2, error)
            self.assertEqual(my_hdzone.polling, 10, error)
            self.assertEqual(my_hdzone.min_temp, 32, error)
            self.assertEqual(my_hdzone.max_temp, 46, error)
            self.assertEqual(my_hdzone.min_level, 35, error)
            self.assertEqual(my_hdzone.max_level, 100, error)
            self.assertEqual(my_hdzone.hd_device_names, my_td.create_normalized_path_list(hd_names), error)
            self.assertEqual(my_hdzone.hwmon_path, my_td.create_normalized_path_list(hwmon_path), error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def pt_init_n1(self, count: int, temp_calc: int, steps: int, sensitivity: float, polling: float,
                   min_temp: float, max_temp: float, min_level: int, max_level: int, sb_limit: int,
                   hd_names: str, hwmon_path: str, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print() function
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete the instances
        """
        my_td = TestData()
        cmd_ipmi = my_td.create_command_file('echo " 01"')
        cmd_smart = my_td.create_command_file('echo "ACTIVE"')
        mock_print = MagicMock()
        with patch('builtins.print', mock_print):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd_ipmi,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'count': str(count),
                'temp_calc': str(temp_calc),
                'steps': str(steps),
                'sensitivity': str(sensitivity),
                'polling': str(polling),
                'min_temp': str(min_temp),
                'max_temp': str(max_temp),
                'min_level': str(min_level),
                'max_level': str(max_level),
                'hd_names': hd_names,
                'hwmon_path': hwmon_path,
                'standby_guard_enabled': '1',
                'standby_hd_limit': str(sb_limit),
                'smartctl_path': cmd_smart
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            with self.assertRaises(Exception) as cm:
                HdZone(my_log, my_ipmi, my_config)
            self.assertEqual(type(cm.exception), ValueError, error)
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_init(self) -> None:
        """This is a unit test for function HdZone.__init__()"""
        my_td = TestData()

        # Test valid parameters (hd=1 case is not tested because it turns off standby guard).
        self.pt_init_p1(2, FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, my_td.get_hd_2(), 'hz init 1')
        self.pt_init_p1(4, FanController.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 4, my_td.get_hd_4(), 'hz init 2')
        self.pt_init_p1(8, FanController.CALC_MAX, 4, 2, 2, 32, 48, 35, 100, 6, my_td.get_hd_8(), 'hz init 3')

        # Test default configuration values.
        self.pt_init_p2('hz init 4')

        # Test invalid values:
        # count <= 0
        self.pt_init_n1(0, FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, my_td.get_hd_names(1),
                        my_td.get_hd_1(), 'hz init 5')
        self.pt_init_n1(-10, FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, my_td.get_hd_names(1),
                        my_td.get_hd_1(), 'hz init 6')
        # hd_names= not specified
        self.pt_init_n1(1, FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, '',
                        my_td.get_hd_1(), 'hz init 7')
        # len(hd_names) != count
        self.pt_init_n1(2, FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, my_td.get_hd_names(1),
                        my_td.get_hd_2(), 'hz init 8')
        # standby_limit < 0
        self.pt_init_n1(2, FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, -1, my_td.get_hd_names(2),
                        my_td.get_hd_2(), 'hz init 9')
        # standby_limit > count
        self.pt_init_n1(2, FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 4, my_td.get_hd_names(2),
                        my_td.get_hd_2(), 'hz init 10')

    def pt_bhp_p1(self, count: int, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run(), glob.glob() os.listdir() functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if build_hwmon_path() will not create the expected list
            - delete all instances
        """

        # Mock function for glob.glob().
        def mocked_glob(file: str, *args, **kwargs):
            if file.startswith('/sys/class/scsi_disk'):
                file = my_td.td_dir + file
            return original_glob(file, *args, **kwargs)

        # Mock function for os.listdir().
        def mocked_listdir(dir_str: str):
            if dir_str.startswith('/sys/class/scsi_disk'):
                dir_str = my_td.td_dir + dir_str
            return original_listdir(dir_str)

        my_td = TestData()
        command = my_td.create_command_file()
        if count == 1:
            hwmon_path = my_td.get_hd_1()
        elif count == 2:
            hwmon_path = my_td.get_hd_2()
        elif count == 4:
            hwmon_path = my_td.get_hd_4()
        else:
            hwmon_path = my_td.get_hd_8()
        hd_names = my_td.get_hd_names(count)
        original_glob = glob.glob
        original_listdir = os.listdir
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_glob = MagicMock(side_effect=mocked_glob)
        mock_listdir = MagicMock(side_effect=mocked_listdir)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run), \
             patch('glob.glob', mock_glob), \
             patch('os.listdir', mock_listdir):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'count': str(count),
                'hd_names': hd_names
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_hdzone.hwmon_path, my_td.create_normalized_path_list(hwmon_path), error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def pt_bhp_n1(self, count: int, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), subprocesses.run(), glob.glob() os.listdir() functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if build_hwmon_path() will not raise ValueError exception for invalid values
            - delete all instances
        """

        # Mock function for glob.glob().
        def mocked_glob(file: str, *args, **kwargs):
            if file.startswith('/sys/class/scsi_disk'):
                if 'block' in file:
                    file = my_td.td_dir + file
                else:
                    return None     # Invalid filename generated here!
            return original_glob(file, *args, **kwargs)

        # Mock function for os.listdir().
        def mocked_listdir(dir_str: str):
            if dir_str.startswith('/sys/class/scsi_disk'):
                dir_str = my_td.td_dir + dir_str
            return original_listdir(dir_str)

        my_td = TestData()
        command = my_td.create_command_file()
        hd_names = my_td.get_hd_names(count)
        my_td.get_hd_1()
        original_glob = glob.glob
        original_listdir = os.listdir
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_glob = MagicMock(side_effect=mocked_glob)
        mock_listdir = MagicMock(side_effect=mocked_listdir)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run), \
             patch('glob.glob', mock_glob), \
             patch('os.listdir', mock_listdir):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'count': str(count),
                'hd_names': hd_names
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            with self.assertRaises(ValueError) as cm:
                # build_hwmon_path() will be called from __init__(), no need to call it directly
                HdZone(my_log, my_ipmi, my_config)
            self.assertEqual(type(cm.exception), ValueError, error)
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_build_hwmon_path(self) -> None:
        """This is a unit test for function HdZone.build_hwmon_path()"""

        # Test expected values.
        self.pt_bhp_p1(1, 'hz build_hwmon_path 1')
        self.pt_bhp_p1(2, 'hz build_hwmon_path 2')
        self.pt_bhp_p1(4, 'hz build_hwmon_path 3')
        self.pt_bhp_p1(8, 'hz build_hwmon_path 4')

        # Test invalid hwmon_path values.
        self.pt_bhp_n1(1, 'hz build_hwmon_path 5')

    def pt_gsss_p1(self, states: List[bool], result: str, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.get_standby_state_str()
            - ASSERT: if the result is different from the internal power state
            - delete all instances
        """
        my_td = TestData()
        hwmon_path = my_td.get_hd_8()
        hd_names = my_td.get_hd_names(8)
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'count': '8',
                'hd_names': hd_names,
                'hwmon_path': hwmon_path,
                'standby_guard_enabled': '1'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            my_hdzone.standby_array_states = states
        self.assertEqual(my_hdzone.get_standby_state_str(), result, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_get_standby_state_str(self) -> None:
        """This is a unit test for function HdZone.get_standby_state_str()"""
        self.pt_gsss_p1([True, True, True, True, True, True, True, True],
                        'SSSSSSSS', 'hz get_standby_state_str 1')
        self.pt_gsss_p1([False, False, False, False, False, False, False, False],
                        'AAAAAAAA', 'hz get_standby_state_str 2')
        self.pt_gsss_p1([True, False, False, False, False, False, False, False],
                        'SAAAAAAA', 'hz get_standby_state_str 3')
        self.pt_gsss_p1([False, True, False, False, False, False, False, False],
                        'ASAAAAAA', 'hz get_standby_state_str 4')
        self.pt_gsss_p1([False, False, True, False, False, False, False, False],
                        'AASAAAAA', 'hz get_standby_state_str 5')
        self.pt_gsss_p1([False, False, False, True, False, False, False, False],
                        'AAASAAAA', 'hz get_standby_state_str 6')
        self.pt_gsss_p1([False, False, False, False, True, False, False, False],
                        'AAAASAAA', 'hz get_standby_state_str 7')
        self.pt_gsss_p1([False, False, False, False, False, True, False, False],
                        'AAAAASAA', 'hz get_standby_state_str 8')
        self.pt_gsss_p1([False, False, False, False, False, False, True, False],
                        'AAAAAASA', 'hz get_standby_state_str 9')
        self.pt_gsss_p1([False, False, False, False, False, False, False, True],
                        'AAAAAAAS', 'hz get_standby_state_str 10')

    def pt_css_p1(self, states: List[bool], in_standby: int, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.check_standby_state()
            - ASSERT: if result is different from input parameters
            - delete all instances
        """
        results: List[subprocess.CompletedProcess]

        my_td = TestData()
        hwmon_path = my_td.get_hd_8()
        hd_names = my_td.get_hd_names(8)
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'count': '8',
                'hd_names': hd_names,
                'hwmon_path': hwmon_path,
                'standby_guard_enabled': '1'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            results = [None, None, None, None, None, None, None, None]
            for i in range(my_hdzone.count):
                if states[i]:
                    results[i] = subprocess.CompletedProcess([], 0, 'STANDBY')
                else:
                    results[i] = subprocess.CompletedProcess([], 0, 'ACTIVE')
            mock_subprocess_run.side_effect = results
            my_hdzone.standby_array_states = states
            self.assertEqual(my_hdzone.check_standby_state(), in_standby, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config

    def test_check_standby_state(self) -> None:
        """This is a unit test for function Hd.check_standby_state()"""
        self.pt_css_p1([True, True, True, True, True, True, True, True], 8, 'hz check_standby_state 1')
        self.pt_css_p1([False, True, True, True, True, True, True, True], 7, 'hz check_standby_state 2')
        self.pt_css_p1([True, False, True, True, True, True, True, True], 7, 'hz check_standby_state 3')
        self.pt_css_p1([True, True, False, True, True, True, True, True], 7, 'hz check_standby_state 4')
        self.pt_css_p1([True, True, True, False, True, True, True, True], 7, 'hz check_standby_state 5')
        self.pt_css_p1([True, True, True, True, False, True, True, True], 7, 'hz check_standby_state 6')
        self.pt_css_p1([True, True, True, True, True, False, True, True], 7, 'hz check_standby_state 7')
        self.pt_css_p1([True, True, True, True, True, True, False, True], 7, 'hz check_standby_state 8')
        self.pt_css_p1([True, True, True, True, True, True, True, False], 7, 'hz check_standby_state 9')
        self.pt_css_p1([True, False, True, True, True, True, True, False], 6, 'hz check_standby_state 10')
        self.pt_css_p1([True, False, True, True, False, True, True, False], 5, 'hz check_standby_state 11')
        self.pt_css_p1([False, False, True, True, False, True, True, False], 4, 'hz check_standby_state 12')
        self.pt_css_p1([False, False, True, False, False, True, True, False], 3, 'hz check_standby_state 13')
        self.pt_css_p1([False, False, True, False, False, True, False, False], 2, 'hz check_standby_state 14')
        self.pt_css_p1([False, False, False, False, False, True, False, False], 1, 'hz check_standby_state 15')
        self.pt_css_p1([False, False, False, False, False, False, False, False], 0, 'hz check_standby_state 16')

    def pt_gss_p1(self, states: List[bool], count: int, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.go_standby_state()
            - ASSERT: if the subprocess.run() called with wrong parameters and array state is not in fully standby
            - delete the instances
        """
        my_td = TestData()
        hwmon_path = my_td.get_hd_8()
        hd_names = my_td.get_hd_names(8)
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'count': '8',
                'hd_names': hd_names,
                'hwmon_path': hwmon_path,
                'standby_guard_enabled': '1',
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            my_hdzone.standby_array_states = states
            mock_subprocess_run.reset_mock()
            my_hdzone.go_standby_state()
            self.assertEqual(mock_subprocess_run.call_count, count, error)
            self.assertEqual([True, True, True, True, True, True, True, True], my_hdzone.standby_array_states, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_go_standby_state(self) -> None:
        """This is a unit test for function HdZone.go_standby_state()"""
        self.pt_gss_p1([False, False, False, False, False, False, False, False], 8, 'hz go_standby_state 1')
        self.pt_gss_p1([True, False, False, False, False, False, False, False], 7, 'hz go_standby_state 2')
        self.pt_gss_p1([True, True, False, False, False, False, False, False], 6, 'hz go_standby_state 3')
        self.pt_gss_p1([True, True, True, False, False, False, False, False], 5, 'hz go_standby_state 4')
        self.pt_gss_p1([True, True, True, True, False, False, False, False], 4, 'hz go_standby_state 5')
        self.pt_gss_p1([True, True, True, True, True, False, False, False], 3, 'hz go_standby_state 6')
        self.pt_gss_p1([True, True, True, True, True, True, False, False], 2, 'hz go_standby_state 7')
        self.pt_gss_p1([True, True, True, True, True, True, True, False], 1, 'hz go_standby_state 8')
        self.pt_gss_p1([True, True, True, True, True, True, True, True], 0, 'hz go_standby_state 9')

    def pt_rsg_p1(self, old_state: bool, states: List[bool], new_state: bool, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.run_standby_guard()
            - ASSERT: if the expected standby_flag is different
            - delete all instances
        """
        my_td = TestData()
        hwmon_path = my_td.get_hd_8()
        hd_names = my_td.get_hd_names(8)
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'count': '8',
                'hd_names': hd_names,
                'hwmon_path': hwmon_path,
                'standby_guard_enabled': '1'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            my_hdzone.go_standby_state = MagicMock(name='go_standby_state')
            my_hdzone.check_standby_state = MagicMock(name='check_standby_state')
            my_hdzone.check_standby_state.return_value = states.count(True)
            my_hdzone.standby_array_states = states
            my_hdzone.standby_flag = old_state
            my_hdzone.run_standby_guard()
            self.assertEqual(my_hdzone.standby_flag, new_state, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config

    def test_run_standby_guard(self) -> None:
        """This is a unit test for function HdZone.run_standby_guard()"""
        # 1. No state changes.
        self.pt_rsg_p1(False, [False, False, False, False, False, False, False, False], False, 'hz run_standby_guard 1')
        self.pt_rsg_p1(True, [True, True, True, True, True, True, True, True], True, 'hz run_standby_guard 2')
        # 2. change from ACTIVE to STANDBY.
        self.pt_rsg_p1(False, [False, True, False, False, False, False, False, False], True, 'hz run_standby_guard 3')
        self.pt_rsg_p1(False, [False, True, False, True, False, False, False, False], True, 'hz run_standby_guard 4')
        self.pt_rsg_p1(False, [True, True, True, True, True, True, True, True], True, 'hz run_standby_guard 5')
        # 3. change from STANDBY to ACTIVE.
        self.pt_rsg_p1(True, [False, False, False, False, False, False, False, False], False, 'hz run_standby_guard 6')
        self.pt_rsg_p1(True, [True, False, False, True, True, True, True, True], False, 'hz run_standby_guard 7')


if __name__ == "__main__":
    unittest.main()
