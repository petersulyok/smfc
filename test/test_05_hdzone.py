#!/usr/bin/python3
#
#   test_05_hdzone.py (C) 2021-2022, Peter Sulyok
#   Unit tests for smfc.HdZone() class.
#
import configparser
import subprocess
import unittest
from typing import List
from unittest.mock import patch, MagicMock
import smfc
from smfc import Log, Ipmi, HdZone
from test_00_data import TestData


class HdZoneTestCase(unittest.TestCase):
    """Unit test class for smfc.HdZone() class"""

    def primitive_test_1_pos(self, count: int, temp_calc: int, steps: int, sensitivity: float, polling: float,
                             min_temp: float, max_temp: float, min_level: int, max_level: int, sb_limit: int,
                             error: str):
        """This is a primitive negative test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete the instances
        """
        my_td = TestData()
        cmd_ipmi = my_td.create_command_file('echo " 01"')
        cmd_smart = my_td.create_command_file('echo "ACTIVE"')
        hwmon_path = my_td.get_hd_2()
        if count == 4:
            hwmon_path = my_td.get_hd_4()
        if count == 8:
            hwmon_path = my_td.get_hd_8()
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
                'hwmon_path': '\n'.join(hwmon_path)+'\n',
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
        self.assertEqual(my_hdzone.hd_names, hd_names.split(), error)
        self.assertEqual(my_hdzone.hwmon_path, hwmon_path, error)
        self.assertEqual(my_hdzone.standby_hd_limit, sb_limit, error)
        self.assertEqual(my_hdzone.smartctl_path, cmd_smart, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def primitive_test_2_pos(self, error: str):
        """This is a primitive negative test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete the instances
        """
        my_td = TestData()
        cmd_ipmi = my_td.create_command_file('echo " 01"')
        hwmon_path = my_td.get_hd_8()
        hd_names = my_td.get_hd_names(8)
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
                'hwmon_path': '\n'.join(hwmon_path) + '\n',
                'standby_guard_enabled': '1',
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_hdzone.count, 8, error)
            self.assertEqual(my_hdzone.temp_calc, smfc.FanController.CALC_AVG, error)
            self.assertEqual(my_hdzone.steps, 4, error)
            self.assertEqual(my_hdzone.sensitivity, 2, error)
            self.assertEqual(my_hdzone.polling, 2400, error)
            self.assertEqual(my_hdzone.min_temp, 32, error)
            self.assertEqual(my_hdzone.max_temp, 48, error)
            self.assertEqual(my_hdzone.min_level, 35, error)
            self.assertEqual(my_hdzone.max_level, 100, error)
            self.assertEqual(my_hdzone.hd_names, hd_names.split(), error)
            # Default value is not checked, maybe the path does not exist where the unit test is executed.
            #self.assertEqual(my_hdzone.hwmon_path, (
            #                 '/sys/class/scsi_device/0:0:0:0/device/hwmon/hwmon*/temp1_input\n'
            #                 '/sys/class/scsi_device/1:0:0:0/device/hwmon/hwmon*/temp1_input\n'
            #                 '/sys/class/scsi_device/2:0:0:0/device/hwmon/hwmon*/temp1_input\n'
            #                 '/sys/class/scsi_device/3:0:0:0/device/hwmon/hwmon*/temp1_input\n'
            #                 '/sys/class/scsi_device/4:0:0:0/device/hwmon/hwmon*/temp1_input\n'
            #                 '/sys/class/scsi_device/5:0:0:0/device/hwmon/hwmon*/temp1_input\n'
            #                 '/sys/class/scsi_device/6:0:0:0/device/hwmon/hwmon*/temp1_input\n'
            #                 '/sys/class/scsi_device/7:0:0:0/device/hwmon/hwmon*/temp1_input'
            #                 ), error)
            self.assertEqual(my_hdzone.standby_hd_limit, 1, error)
            # Default value is not checked, maybe the path does not exist where the unit test is executed.
            #self.assertEqual(my_hdzone.smartctl_path, '/usr/sbin/smartctl', error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_init(self) -> None:
        """This is a unit test for function HdZone.__init__()"""
        # Test valid parameters.
        self.primitive_test_1_pos(2, smfc.FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, 'hz init 1')
        self.primitive_test_1_pos(4, smfc.FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, 'hz init 2')
        self.primitive_test_1_pos(8, smfc.FanController.CALC_MAX, 4, 2, 2, 32, 48, 35, 100, 2, 'hz init 3')

        # Test loading default values (if they are not specified in INI files).
        self.primitive_test_2_pos('hz init 4')

    def primitive_test_3_pos(self, states: List[bool], result: str, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.get_standby_state_str()
            - ASSERT: if the result is different than the internal state
            - delete the instances
        """
        my_td = TestData()
        hwmon_path = my_td.get_hd_8()
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
                'hwmon_path': '\n'.join(hwmon_path)+'\n',
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
        """This is a unit test for function HdZone.set_fan_level()"""
        # Test valid parameters.
        self.primitive_test_3_pos([True, True, True, True, True, True, True, True],         'SSSSSSSS',
                                  'hz get_standby_state_str 1')
        self.primitive_test_3_pos([False, False, False, False, False, False, False, False], 'AAAAAAAA',
                                  'hz get_standby_state_str 2')
        self.primitive_test_3_pos([True, False, False, False, False, False, False, False],  'SAAAAAAA',
                                  'hz get_standby_state_str 3')
        self.primitive_test_3_pos([False, True, False, False, False, False, False, False],  'ASAAAAAA',
                                  'hz get_standby_state_str 4')
        self.primitive_test_3_pos([False, False, True, False, False, False, False, False],  'AASAAAAA',
                                  'hz get_standby_state_str 5')
        self.primitive_test_3_pos([False, False, False, True, False, False, False, False],  'AAASAAAA',
                                  'hz get_standby_state_str 6')
        self.primitive_test_3_pos([False, False, False, False, True, False, False, False],  'AAAASAAA',
                                  'hz get_standby_state_str 7')
        self.primitive_test_3_pos([False, False, False, False, False, True, False, False],  'AAAAASAA',
                                  'hz get_standby_state_str 8')
        self.primitive_test_3_pos([False, False, False, False, False, False, True, False],  'AAAAAASA',
                                  'hz get_standby_state_str 9')
        self.primitive_test_3_pos([False, False, False, False, False, False, False, True],  'AAAAAAAS',
                                  'hz get_standby_state_str 10')

    def primitive_test_4_pos(self, states: List[bool], in_standby: int, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.check_standby_state()
            - ASSERT: if result is different that input parameters
            - delete the instances
        """
        results: List[subprocess.CompletedProcess]

        my_td = TestData()
        hwmon_path = my_td.get_hd_8()
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
                'hwmon_path': '\n'.join(hwmon_path)+'\n',
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
        """This is a unit test for function Hd.set_fan_level()"""
        # Test valid parameters.
        self.primitive_test_4_pos([True, True, True, True, True, True, True, True], 8,
                                  'hz check_standby_state 1')
        self.primitive_test_4_pos([False, True, True, True, True, True, True, True], 7,
                                  'hz check_standby_state 2')
        self.primitive_test_4_pos([True, False, True, True, True, True, True, True], 7,
                                  'hz check_standby_state 3')
        self.primitive_test_4_pos([True, True, False, True, True, True, True, True], 7,
                                  'hz check_standby_state 4')
        self.primitive_test_4_pos([True, True, True, False, True, True, True, True], 7,
                                  'hz check_standby_state 5')
        self.primitive_test_4_pos([True, True, True, True, False, True, True, True], 7,
                                  'hz check_standby_state 6')
        self.primitive_test_4_pos([True, True, True, True, True, False, True, True], 7,
                                  'hz check_standby_state 7')
        self.primitive_test_4_pos([True, True, True, True, True, True, False, True], 7,
                                  'hz check_standby_state 8')
        self.primitive_test_4_pos([True, True, True, True, True, True, True, False], 7,
                                  'hz check_standby_state 9')

        self.primitive_test_4_pos([True, False, True, True, True, True, True, False], 6,
                                  'hz check_standby_state 10')
        self.primitive_test_4_pos([True, False, True, True, False, True, True, False], 5,
                                  'hz check_standby_state 11')
        self.primitive_test_4_pos([False, False, True, True, False, True, True, False], 4,
                                  'hz check_standby_state 12')
        self.primitive_test_4_pos([False, False, True, False, False, True, True, False], 3,
                                  'hz check_standby_state 13')
        self.primitive_test_4_pos([False, False, True, False, False, True, False, False], 2,
                                  'hz check_standby_state 14')
        self.primitive_test_4_pos([False, False, False, False, False, True, False, False], 1,
                                  'hz check_standby_state 15')
        self.primitive_test_4_pos([False, False, False, False, False, False, False, False], 0,
                                  'hz check_standby_state 16')

    def primitive_test_5_pos(self, states: List[bool], count: int, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.go_standby_state()
            - ASSERT: if the subprocess.run called with wrong parameters and array state is not in fully standby
            - delete the instances
        """
        my_td = TestData()
        hwmon_path = my_td.get_hd_8()
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
                'hwmon_path': '\n'.join(hwmon_path)+'\n',
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

        # Test valid parameters.
        self.primitive_test_5_pos([False, False, False, False, False, False, False, False], 8, 'hz go_standby_state 1')
        self.primitive_test_5_pos([True, False, False, False, False, False, False, False], 7, 'hz go_standby_state 2')
        self.primitive_test_5_pos([True, True, False, False, False, False, False, False], 6, 'hz go_standby_state 3')
        self.primitive_test_5_pos([True, True, True, False, False, False, False, False], 5, 'hz go_standby_state 4')
        self.primitive_test_5_pos([True, True, True, True, False, False, False, False], 4, 'hz go_standby_state 5')
        self.primitive_test_5_pos([True, True, True, True, True, False, False, False], 3, 'hz go_standby_state 6')
        self.primitive_test_5_pos([True, True, True, True, True, True, False, False], 2, 'hz go_standby_state 7')
        self.primitive_test_5_pos([True, True, True, True, True, True, True, False], 1, 'hz go_standby_state 8')
        self.primitive_test_5_pos([True, True, True, True, True, True, True, True], 0, 'hz go_standby_state 9')

    def primitive_test_6_pos(self, old_state: bool, states: List[bool], new_state: bool, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.run_standby_guard()
            - ASSERT: if the expected standby_flag is different
            - delete the instances
        """
        my_td = TestData()
        hwmon_path = my_td.get_hd_8()
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
                'hwmon_path': '\n'.join(hwmon_path)+'\n',
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
        # No state changes.
        self.primitive_test_6_pos(False, [False, False, False, False, False, False, False, False], False,
                                   'hz run_standby_guard 1')
        self.primitive_test_6_pos(True, [True, True, True, True, True, True, True, True], True,
                                   'hz run_standby_guard 2')

        # Step 2: from ACTIVE to STANDBY.
        self.primitive_test_6_pos(False, [False, True, False, False, False, False, False, False], True,
                                   'hz run_standby_guard 3')
        self.primitive_test_6_pos(False, [False, True, False, True, False, False, False, False], True,
                                   'hz run_standby_guard 4')
        self.primitive_test_6_pos(False, [True, True, True, True, True, True, True, True], True,
                                   'hz run_standby_guard 5')

        # Step 3: from STANDBY to ACTIVE.
        self.primitive_test_6_pos(True, [False, False, False, False, False, False, False, False], False,
                                   'hz run_standby_guard 6')
        self.primitive_test_6_pos(True, [True, False, False, True, True, True, True, True], False,
                                   'hz run_standby_guard 7')


if __name__ == "__main__":
    unittest.main()
