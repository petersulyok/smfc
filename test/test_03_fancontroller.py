#!/usr/bin/python3
#
#   test_03_fancontroller.py (C) 2021-2022, Peter Sulyok
#   Unit tests for smfc.FanController() class.
#
import configparser
import time
import unittest
from typing import List, Tuple, Any
from unittest.mock import patch, MagicMock
from smfc import FanController, Log, Ipmi
from test_00_data import TestData


class FanControllerTestCase(unittest.TestCase):
    """Unit test class for smfc.FanController() class"""

    def primitive_test_1_pos(self, ipmi_zone: int, name: str, count: int, temp_calc: int, steps: int,
                             sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                             max_level, hwmon_path: List[str], error: str) -> None:
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete the instances
        """
        my_td = TestData()
        cmd = my_td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)

            my_fc = FanController(my_log, my_ipmi, ipmi_zone, name, count, temp_calc, steps, sensitivity, polling,
                                  min_temp, max_temp, min_level, max_level, hwmon_path)
        self.assertEqual(my_fc.log, my_log, error)
        self.assertEqual(my_fc.ipmi, my_ipmi, error)
        self.assertEqual(my_fc.ipmi_zone, ipmi_zone, error)
        self.assertEqual(my_fc.name, name, error)
        self.assertEqual(my_fc.count, count, error)
        self.assertEqual(my_fc.temp_calc, temp_calc, error)
        self.assertEqual(my_fc.steps, steps, error)
        self.assertEqual(my_fc.sensitivity, sensitivity, error)
        self.assertEqual(my_fc.polling, polling, error)
        self.assertEqual(my_fc.min_temp, min_temp, error)
        self.assertEqual(my_fc.max_temp, max_temp, error)
        self.assertEqual(my_fc.min_level, min_level, error)
        self.assertEqual(my_fc.max_level, max_level, error)
        self.assertEqual(my_fc.hwmon_path, hwmon_path, error)
        self.assertEqual(my_fc.level_step, (max_level - min_level) / steps, error)
        self.assertEqual(my_fc.last_temp, 0, error)
        self.assertEqual(my_fc.last_level, 0, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def primitive_test_1a_pos(self, ipmi_zone: int, name: str, count: int, temp_calc: int, steps: int,
                             sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                             max_level, hwmon_path: List[str], error: str) -> None:
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete the instances
        """
        my_td = TestData()
        cmd = my_td.create_command_file()
        local_hwmon = my_td.normalize_path(hwmon_path)
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, ipmi_zone, name, count, temp_calc, steps, sensitivity, polling,
                                  min_temp, max_temp, min_level, max_level, local_hwmon)
        self.assertEqual(my_fc.log, my_log, error)
        self.assertEqual(my_fc.ipmi, my_ipmi, error)
        self.assertEqual(my_fc.ipmi_zone, ipmi_zone, error)
        self.assertEqual(my_fc.name, name, error)
        self.assertEqual(my_fc.count, count, error)
        self.assertEqual(my_fc.temp_calc, temp_calc, error)
        self.assertEqual(my_fc.steps, steps, error)
        self.assertEqual(my_fc.sensitivity, sensitivity, error)
        self.assertEqual(my_fc.polling, polling, error)
        self.assertEqual(my_fc.min_temp, min_temp, error)
        self.assertEqual(my_fc.max_temp, max_temp, error)
        self.assertEqual(my_fc.min_level, min_level, error)
        self.assertEqual(my_fc.max_level, max_level, error)
        self.assertEqual(my_fc.hwmon_path, local_hwmon, error)
        self.assertEqual(my_fc.level_step, (max_level - min_level) / steps, error)
        self.assertEqual(my_fc.last_temp, 0, error)
        self.assertEqual(my_fc.last_level, 0, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def primitive_test_2_neg(self, ipmi_zone: int, name: str, count: int, temp_calc: int, steps: int,
                             sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                             max_level, hwmon_path: List[str], exception: Any, error: str) -> None:
        """This is a primitive negative test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if exception not raised in case of invalid parameter values
            - delete the instances
        """
        my_td = TestData()
        cmd = my_td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            with self.assertRaises(Exception) as cm:
                FanController(my_log, my_ipmi, ipmi_zone, name, count, temp_calc, steps, sensitivity, polling,
                              min_temp, max_temp, min_level, max_level, hwmon_path)
            self.assertEqual(type(cm.exception), exception, error)
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_init(self) -> None:
        """This is a unit test for function FanController.__init__()"""
        td = TestData()
        # Test valid parameters.
        l = td.get_cpu_1()
        self.primitive_test_1_pos(Ipmi.CPU_ZONE, 'CPU zone', 1, FanController.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, l, 'fc init 1')
        self.primitive_test_1_pos(Ipmi.CPU_ZONE, 'CPU zone', 2, FanController.CALC_MAX, 5, 4, 2, 30, 50, 35, 100, td.get_cpu_2(), 'fc init 2')
        self.primitive_test_1_pos(Ipmi.CPU_ZONE, 'CPU zone', 4, FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, td.get_cpu_4(), 'fc init 3')
        self.primitive_test_1_pos(Ipmi.HD_ZONE,  'HD zone',  1, FanController.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, td.get_hd_1(),  'fc init 4')
        self.primitive_test_1_pos(Ipmi.HD_ZONE,  'HD zone',  2, FanController.CALC_MAX, 5, 4, 2, 30, 50, 35, 100, td.get_hd_2(),  'fc init 5')
        self.primitive_test_1_pos(Ipmi.HD_ZONE,  'HD zone',  4, FanController.CALC_MAX, 5, 4, 2, 30, 50, 35, 100, td.get_hd_4(),  'fc init 6')
        self.primitive_test_1_pos(Ipmi.HD_ZONE,  'HD zone',  8, FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, td.get_hd_8(),  'fc init 7')
        # Wild characters in path
        self.primitive_test_1a_pos(Ipmi.CPU_ZONE, 'CPU zone', 1, FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, td.get_cpu_1w(),  'fc init 8')
        self.primitive_test_1a_pos(Ipmi.CPU_ZONE, 'CPU zone', 2, FanController.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, td.get_cpu_2w(), 'fc init 9')
        self.primitive_test_1a_pos(Ipmi.CPU_ZONE, 'CPU zone', 4, FanController.CALC_MAX, 5, 4, 2, 30, 50, 35, 100, td.get_cpu_4w(), 'fc init 10')
        self.primitive_test_1a_pos(Ipmi.HD_ZONE,  'HD zone',  1, FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, td.get_hd_1w(),  'fc init 11')
        self.primitive_test_1a_pos(Ipmi.HD_ZONE,  'HD zone',  2, FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, td.get_hd_2w(), 'fc init 12')
        self.primitive_test_1a_pos(Ipmi.HD_ZONE,  'HD zone',  4, FanController.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, td.get_hd_4w(), 'fc init 13')
        self.primitive_test_1a_pos(Ipmi.HD_ZONE,  'HD zone',  8, FanController.CALC_MAX, 5, 4, 2, 30, 50, 35, 100, td.get_hd_8w(), 'fc init 14')

        # Test invalid parameters.
        # ipmi_zone
        self.primitive_test_2_neg(-1, 'CPU zone', 1, 0, 5, 4, 2, 30, 50, 35, 100, l, ValueError, 'fc init 15')
        self.primitive_test_2_neg(100, 'CPU zone', 1, 0, 5, 4, 2, 30, 50, 35, 100, l, ValueError, 'fc init 16')
        # count
        self.primitive_test_2_neg(Ipmi.CPU_ZONE, 'CPU zone', -1, 0, 5, 4, 2, 30, 50, 35, 100, l, ValueError, 'fc init 17')
        self.primitive_test_2_neg(Ipmi.CPU_ZONE, 'CPU zone', 0, 0, 5, 4, 2, 30, 50, 35, 100, l, ValueError, 'fc init 18')
        # temp_calc
        self.primitive_test_2_neg(Ipmi.CPU_ZONE, 'CPU zone', 1, -1, 5, 4, 2, 30, 50, 35, 100, l, ValueError, 'fc init 19')
        self.primitive_test_2_neg(Ipmi.CPU_ZONE, 'CPU zone', 1, 100, 5, 4, 2, 30, 50, 35, 100, l, ValueError, 'fc init 20')
        # step
        self.primitive_test_2_neg(Ipmi.HD_ZONE,  'HD zone',  1, 1, -2, 4, 2, 30, 50, 35, 100, l, ValueError, 'fc init 21')
        self.primitive_test_2_neg(Ipmi.HD_ZONE,  'HD zone',  1, 1, 0, 4, 2, 30, 50, 35, 100, l, ValueError, 'fc init 22')
        # sensitivity
        self.primitive_test_2_neg(Ipmi.HD_ZONE,  'HD zone',  1, 1, 5, 0, 2, 30, 50, 35, 100, l, ValueError, 'fc init 23')
        self.primitive_test_2_neg(Ipmi.HD_ZONE,  'HD zone',  1, 1, 5, -2, 2, 30, 50, 35, 100, l, ValueError, 'fc init 24')
        # polling
        self.primitive_test_2_neg(Ipmi.HD_ZONE,  'HD zone',  1, 1, 5, 4, -2, 30, 50, 35, 100, l, ValueError, 'fc init 25')
        # max_temp < min_temp
        self.primitive_test_2_neg(Ipmi.HD_ZONE,  'HD zone',  1, 1, 5, 4, 2, 50, 30, 35, 100, l, ValueError, 'fc init 26')
        # max_level < min_level
        self.primitive_test_2_neg(Ipmi.HD_ZONE,  'HD zone',  1, 1, 5, 4, 2, 30, 50, 100, 35, l, ValueError, 'fc init 27')
        # len(hwmon_path) != count
        self.primitive_test_2_neg(Ipmi.HD_ZONE,  'HD zone',  2, 1, 5, 4, 2, 30, 50, 100, 35, l, ValueError, 'fc init 28')
        # Invalid path
        self.primitive_test_2_neg(Ipmi.HD_ZONE,  'HD zone',  1, 1, 5, 4, 2, 30, 50, 100, 35, ['./xyz/temp/a'], ValueError, 'fc init 29')

    def primitive_test_3a_pos(self, count:int, temps: List[float], expected: float, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the get_1_temp() function returns different temperature
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_temp_files('cpu', count, temp_list=temps)
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, FanController.CALC_AVG, 5,
                                  4, 2, 30, 50, 35, 100, hwmon_path)
            self.assertEqual(my_fc.get_1_temp(), expected, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del td

    def primitive_test_3a_neg(self, count:int, temps: List[float], error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the get_1_temp() function will not generate IOError/FileNotFoundError exception
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_temp_files('cpu', count, temp_list=temps)
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, FanController.CALC_AVG, 5,
                          4, 2, 30, 50, 35, 100, hwmon_path)
            del td
            with self.assertRaises(IOError) as cm:
                my_fc.get_1_temp()
            self.assertEqual(type(cm.exception), FileNotFoundError, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config

    def test_get_1_temp(self) -> None:
        """This is a unit test for functions FanController.get_1_temp()"""
        # Valid cases
        self.primitive_test_3a_pos(1, [38.5], 38.5, 'fc get_1_temp 1')
        # File read error.
        self.primitive_test_3a_neg(1, [38.5], 'fc get_1_temp 2')

    def primitive_test_3b_pos(self, count:int, temps: List[float], expected: float, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the get_min_temp() function returns different temperature
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_temp_files('cpu', count, temp_list=temps)
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, FanController.CALC_AVG, 5,
                                  4, 2, 30, 50, 35, 100, hwmon_path)
            self.assertEqual(my_fc.get_min_temp(), expected, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del td

    def primitive_test_3b_neg(self, count:int, temps: List[float], error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the get_min_temp() function will not generate IOError/FileNotFoundError exception
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_temp_files('cpu', count, temp_list=temps)
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, FanController.CALC_AVG, 5,
                          4, 2, 30, 50, 35, 100, hwmon_path)
            del td
            with self.assertRaises(IOError) as cm:
                my_fc.get_min_temp()
            self.assertEqual(type(cm.exception), FileNotFoundError, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config

    def test_get_min_temp(self) -> None:
        """This is a unit test for functions FanController.get_min_temp()"""
        # Valid cases
        self.primitive_test_3b_pos(3, [38.5, 38.5, 38.5], 38.5, 'fc get_min_temp 1')
        self.primitive_test_3b_pos(3, [38.5, 40.5, 42.5], 38.5, 'fc get_min_temp 2')
        # File read error
        self.primitive_test_3b_neg(2, [38.5, 40.5], 'fc get_min_temp 3')

    def primitive_test_3c_pos(self, count:int, temps: List[float], expected: float, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the get_avg_temp() function returns different temperature
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_temp_files('cpu', count, temp_list=temps)
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, FanController.CALC_AVG, 5,
                                  4, 2, 30, 50, 35, 100, hwmon_path)
            self.assertEqual(my_fc.get_avg_temp(), expected, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del td

    def primitive_test_3c_neg(self, count:int, temps: List[float], error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the get_avg_temp() function will not generate IOError exception
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_temp_files('cpu', count, temp_list=temps)
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, FanController.CALC_AVG, 5,
                          4, 2, 30, 50, 35, 100, hwmon_path)
            del td
            with self.assertRaises(IOError) as cm:
                my_fc.get_avg_temp()
            self.assertEqual(type(cm.exception), FileNotFoundError, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config

    def test_get_avg_temp(self) -> None:
        """This is a unit test for functions FanController.get_avg_temp()"""
        # Valid cases
        self.primitive_test_3c_pos(3, [38.5, 38.5, 38.5], 38.5, 'fc get_avg_temp 1')
        self.primitive_test_3c_pos(3, [38.5, 40.5, 42.5], 40.5, 'fc get_avg_temp 2')
        self.primitive_test_3c_pos(8, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 45.0, 'fc get_avg_temp 3')
        # File read error
        self.primitive_test_3c_neg(2, [38.5, 40.5], 'fc get_avg_temp 4')

    def primitive_test_3d_pos(self, count:int, temps: List[float], expected: float, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the get_max_temp() function returns different temperature
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_temp_files('cpu', count, temp_list=temps)
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, FanController.CALC_AVG, 5,
                                  4, 2, 30, 50, 35, 100, hwmon_path)
            self.assertEqual(my_fc.get_max_temp(), expected, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del td

    def primitive_test_3d_neg(self, count:int, temps: List[float], error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the get_max_temp() function will not generate IOError exception
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_temp_files('cpu', count, temp_list=temps)
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, FanController.CALC_AVG, 5,
                          4, 2, 30, 50, 35, 100, hwmon_path)
            del td
            with self.assertRaises(IOError) as cm:
                my_fc.get_max_temp()
            self.assertEqual(type(cm.exception), FileNotFoundError, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config

    def test_get_max_temp(self) -> None:
        """This is a unit test for functions FanController.get_max_temp()"""
        # Valid cases
        self.primitive_test_3d_pos(3, [38.5, 38.5, 38.5], 38.5, 'fc get_max_temp 1')
        self.primitive_test_3d_pos(3, [38.5, 40.5, 42.5], 42.5, 'fc get_max_temp 2')
        self.primitive_test_3d_pos(8, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 52.0, 'fc get_max_temp 3')
        # File read error
        self.primitive_test_3d_neg(2, [38.5, 40.5], 'fc get_max_temp 4')

    def primitive_test_4_pos(self, ipmi_zone:int, level:int):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the Ipmi.set_fan_level() function was called with different parameters
            - delete the instances
        """
        td = TestData()
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_ipmi.set_fan_level = MagicMock(name='set_fan_level')
            my_ipmi.set_fan_level.return_value = Ipmi.SUCCESS
            my_fc = FanController(my_log, my_ipmi, ipmi_zone, 'CPU zone', 1, FanController.CALC_AVG, 5,
                                  4, 2, 30, 50, 35, 100, td.get_cpu_1())
            my_fc.set_fan_level(level)
            my_ipmi.set_fan_level.assert_any_call(my_fc.ipmi_zone, level)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del td

    def test_set_fan_level(self) -> None:
        """This is a unit test for functions FanController.set_fan_level()"""
        # Valid cases
        self.primitive_test_4_pos(Ipmi.CPU_ZONE, 45)
        self.primitive_test_4_pos(Ipmi.HD_ZONE, 65)

    def primitive_test_5_pos(self, steps: int, sensitivity: float, polling: float, min_temp: float, max_temp: float,
                             min_level: int, max_level, temp: float, level: int, error: str) -> None:
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the run() generates different fan level based on the input zone temperature
            - delete the instances
        """
        td = TestData()
        cmd = td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': cmd,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', 1, 1, steps, sensitivity, polling,
                                  min_temp, max_temp, min_level, max_level, td.get_cpu_1([temp]))
            #my_fc.get_temp = MagicMock(name='get_1_temp')
            #my_fc.get_temp.return_value = temp
            my_fc.set_fan_level = MagicMock(name='set_fan_level')
            my_fc.last_time = time.monotonic() - (polling + 1)
            my_fc.last_level = 0
            my_fc.run()
            self.assertEqual(my_fc.set_fan_level.call_args[0][0], level, error)
            self.assertEqual(my_fc.last_temp, temp, error)
            self.assertEqual(my_fc.last_level, level, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del td

    def test_run(self) -> None:
        """This is a unit test for function FanController.run()"""

        # Assert counter
        counter = 0

        # Test data set 1 for a generic configuration (dynamic mapping): steps=5, min_temp=30, max_temp=50, min_level=35, max_level=100
        test_values_1: List[Tuple[float, int]] = [
            (30.0, 35), (31.0, 35), (32.0, 35), (33.0, 48), (34.0, 48), (35.0, 48), (36.0, 61), (37.0, 61),
            (38.0, 61), (39.0, 61), (40.0, 61), (41.0, 74), (42.0, 74), (43.0, 74), (44.0, 87), (45.0, 87),
            (46.0, 87), (47.0, 87), (48.0, 87), (49.0, 100), (50.0, 100)
            ]

        # Test data set 2 for special configuration (constant mapping): steps=5, min_temp=40, max_temp=40, min_level=45, max_level=45
        test_values_2: List[Tuple[float, int]] = [
            (30.0, 45), (31.0, 45), (32.0, 45), (33.0, 45), (34.0, 45), (35.0, 45), (36.0, 45), (37.0, 45),
            (38.0, 45), (39.0, 45), (40.0, 45), (41.0, 45), (42.0, 45), (43.0, 45), (44.0, 45), (45.0, 45),
            (46.0, 45), (47.0, 45), (48.0, 45), (49.0, 45), (50.0, 45)
            ]
        
        # Test 1 with a valid data set.
        for i in test_values_1:
            self.primitive_test_5_pos(5, 1, 1, 30, 50, 35, 100, i[0], i[1], 'fc run {}'.format(counter))
            counter += 1

        # Test 2 with constant mapping.
        for i in test_values_2:
            self.primitive_test_5_pos(5, 1, 1, 40, 40, 45, 45, i[0], i[1], 'fc run {}'.format(counter))
            counter += 1

        # Check level if temperature is under the minimum value.
        self.primitive_test_5_pos(5, 1, 1, 30, 50, 35, 100, 25.0, 35, 'fc run {}'.format(counter))
        counter += 1

        # Check level if temperature is above the maximum value.
        self.primitive_test_5_pos(5, 1, 1, 30, 50, 35, 100, 55.0, 100, 'fc run {}'.format(counter))
        counter += 1

        ''' Default temperature and fan level value pairs
        [30C:35%], 
        [31C:35%], 
        [32C:35%], 
        [33C:48%], 
        [34C:48%], 
        [35C:48%], 
        [36C:61%], 
        [37C:61%], 
        [38C:61%], 
        [39C:61%], 
        [40C:61%], 
        [41C:74%], 
        [42C:74%], 
        [43C:74%], 
        [44C:87%], 
        [45C:87%], 
        [46C:87%], 
        [47C:87%], 
        [48C:87%], 
        [49C:100%], 
        [50C:100%],
        '''

if __name__ == "__main__":
    unittest.main()
