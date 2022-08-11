#!/usr/bin/python3
#
#   test_03_fancontroller.py (C) 2021-2022, Peter Sulyok
#   Unit tests for smfc.FanController() class.
#
import configparser
import time
import unittest
from typing import List, Tuple
from unittest.mock import patch, MagicMock
from test_00_data import TestData
from smfc import FanController, Log, Ipmi


class FanControllerTestCase(unittest.TestCase):
    """Unit test class for smfc.FanController() class"""

    def pt_init_p1(self, ipmi_zone: int, name: str, count: int, temp_calc: int, steps: int,
                   sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                   max_level, hwmon_path: str, error: str) -> None:
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete all instances
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
        if hwmon_path:
            self.assertEqual(my_fc.hwmon_path, my_td.create_normalized_path_list(hwmon_path), error)
        self.assertEqual(my_fc.level_step, (max_level - min_level) / steps, error)
        self.assertEqual(my_fc.last_temp, 0, error)
        self.assertEqual(my_fc.last_level, 0, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def pt_init_n1(self, ipmi_zone: int, name: str, count: int, temp_calc: int, steps: int,
                   sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                   max_level, hwmon_path: str, error: str) -> None:
        """Primitive negative test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
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
            self.assertEqual(type(cm.exception), ValueError, error)
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_init(self) -> None:
        """This is a unit test for function FanController.__init__()"""
        my_td = TestData()
        m_min = FanController.CALC_MIN
        m_avg = FanController.CALC_AVG
        m_max = FanController.CALC_MAX

        # Test valid parameters:
        # a. no hwmon_path specified.
        self.pt_init_p1(Ipmi.CPU_ZONE, 'CPU zone', 1, m_avg, 5, 4, 2, 30, 50, 35, 100, None, 'fc init 1')
        list_1 = my_td.get_cpu_1()
        # b. no wild characters in hwmon_path
        self.pt_init_p1(Ipmi.CPU_ZONE, 'CPU zone', 1, m_avg, 5, 4, 2, 30, 50, 35, 100, list_1, 'fc init 2')
        self.pt_init_p1(Ipmi.CPU_ZONE, 'CPU zone', 2, m_max, 5, 4, 2, 30, 50, 35, 100, my_td.get_cpu_2(), 'fc init 3')
        self.pt_init_p1(Ipmi.CPU_ZONE, 'CPU zone', 4, m_min, 5, 4, 2, 30, 50, 35, 100, my_td.get_cpu_4(), 'fc init 4')
        self.pt_init_p1(Ipmi.HD_ZONE, 'HD zone', 1, m_avg, 5, 4, 2, 30, 50, 35, 100, my_td.get_hd_1(), 'fc init 5')
        self.pt_init_p1(Ipmi.HD_ZONE, 'HD zone', 2, m_max, 5, 4, 2, 30, 50, 35, 100, my_td.get_hd_2(), 'fc init 6')
        self.pt_init_p1(Ipmi.HD_ZONE, 'HD zone', 4, m_max, 5, 4, 2, 30, 50, 35, 100, my_td.get_hd_4(), 'fc init 7')
        self.pt_init_p1(Ipmi.HD_ZONE, 'HD zone', 8, m_min, 5, 4, 2, 30, 50, 35, 100, my_td.get_hd_8(), 'fc init 8')
        # c. there are wild characters in hwmon_path
        self.pt_init_p1(Ipmi.CPU_ZONE, 'CPU zone', 1, m_min, 5, 4, 2, 30, 50, 35, 100, my_td.get_cpu_1w(), 'fc init 9')
        self.pt_init_p1(Ipmi.CPU_ZONE, 'CPU zone', 2, m_avg, 5, 4, 2, 30, 50, 35, 100, my_td.get_cpu_2w(), 'fc init 10')
        self.pt_init_p1(Ipmi.CPU_ZONE, 'CPU zone', 4, m_max, 5, 4, 2, 30, 50, 35, 100, my_td.get_cpu_4w(), 'fc init 11')
        self.pt_init_p1(Ipmi.HD_ZONE, 'HD zone', 1, m_min, 5, 4, 2, 30, 50, 35, 100, my_td.get_hd_1w(), 'fc init 12')
        self.pt_init_p1(Ipmi.HD_ZONE, 'HD zone', 2, m_min, 5, 4, 2, 30, 50, 35, 100, my_td.get_hd_2w(), 'fc init 13')
        self.pt_init_p1(Ipmi.HD_ZONE, 'HD zone', 4, m_avg, 5, 4, 2, 30, 50, 35, 100, my_td.get_hd_4w(), 'fc init 14')
        self.pt_init_p1(Ipmi.HD_ZONE, 'HD zone', 8, m_max, 5, 4, 2, 30, 50, 35, 100, my_td.get_hd_8w(), 'fc init 15')

        # Test invalid parameters:
        # ipmi_zone is invalid
        self.pt_init_n1(-1, 'CPU zone', 1, 0, 5, 4, 2, 30, 50, 35, 100, list_1, 'fc init 16')
        self.pt_init_n1(100, 'CPU zone', 1, 0, 5, 4, 2, 30, 50, 35, 100, list_1, 'fc init 17')
        # count <= 0
        self.pt_init_n1(Ipmi.CPU_ZONE, 'CPU zone', -1, 0, 5, 4, 2, 30, 50, 35, 100, list_1, 'fc init 18')
        self.pt_init_n1(Ipmi.CPU_ZONE, 'CPU zone', 0, 0, 5, 4, 2, 30, 50, 35, 100, list_1, 'fc init 19')
        # temp_calc is invalid
        self.pt_init_n1(Ipmi.CPU_ZONE, 'CPU zone', 1, -1, 5, 4, 2, 30, 50, 35, 100, list_1, 'fc init 20')
        self.pt_init_n1(Ipmi.CPU_ZONE, 'CPU zone', 1, 100, 5, 4, 2, 30, 50, 35, 100, list_1, 'fc init 21')
        # step <= 0
        self.pt_init_n1(Ipmi.HD_ZONE, 'HD zone', 1, 1, -2, 4, 2, 30, 50, 35, 100, list_1, 'fc init 22')
        self.pt_init_n1(Ipmi.HD_ZONE, 'HD zone', 1, 1, 0, 4, 2, 30, 50, 35, 100, list_1, 'fc init 23')
        # sensitivity <= 0
        self.pt_init_n1(Ipmi.HD_ZONE, 'HD zone', 1, 1, 5, 0, 2, 30, 50, 35, 100, list_1, 'fc init 24')
        self.pt_init_n1(Ipmi.HD_ZONE, 'HD zone', 1, 1, 5, -2, 2, 30, 50, 35, 100, list_1, 'fc init 25')
        # polling < 0
        self.pt_init_n1(Ipmi.HD_ZONE, 'HD zone', 1, 1, 5, 4, -2, 30, 50, 35, 100, list_1, 'fc init 26')
        # max_temp < min_temp
        self.pt_init_n1(Ipmi.HD_ZONE, 'HD zone', 1, 1, 5, 4, 2, 50, 30, 35, 100, list_1, 'fc init 27')
        # max_level < min_level
        self.pt_init_n1(Ipmi.HD_ZONE, 'HD zone', 1, 1, 5, 4, 2, 30, 50, 100, 35, list_1, 'fc init 28')
        # len(hwmon_path) != count
        self.pt_init_n1(Ipmi.HD_ZONE, 'HD zone', 2, 1, 5, 4, 2, 30, 50, 100, 35, list_1, 'fc init 29')
        # Invalid hwmon_path
        self.pt_init_n1(Ipmi.HD_ZONE, 'HD zone', 1, 1, 5, 4, 2, 30, 50, 35, 100, './xyz/temp/a', 'fc init 30')

        del my_td

    def pt_bhp_p1(self, counter: int, hwmon_str: str, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if build_hwmon_path() creates unexpected hwmon list based on the specified values
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
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', counter, FanController.CALC_AVG, 5,
                                  4, 2, 30, 50, 35, 100, None)
            my_fc.build_hwmon_path(hwmon_str)
            self.assertEqual(my_fc.hwmon_path, my_td.create_normalized_path_list(hwmon_str), error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def pt_bhp_n1(self, counter: int, hwmon_str: str, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if build_hwmon_path() will not raise exception for invalid values
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
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', counter, FanController.CALC_AVG, 5,
                                  4, 2, 30, 50, 35, 100, None)
            with self.assertRaises(ValueError) as cm:
                my_fc.build_hwmon_path(hwmon_str)
            self.assertEqual(type(cm.exception), ValueError, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_build_hwmon_path(self) -> None:
        """This is a unit test for function FanController.build_hwmon_path()"""
        my_td = TestData()

        # Test with valid data:
        self.pt_bhp_p1(1, my_td.get_cpu_1(), 'build_hwmon_path 1')
        self.pt_bhp_p1(2, my_td.get_cpu_2(), 'build_hwmon_path 2')
        self.pt_bhp_p1(4, my_td.get_cpu_4(), 'build_hwmon_path 3')

        # Test ValueError exceptions:
        # 1. count != len(hwmon_path)
        self.pt_bhp_n1(4, my_td.get_cpu_1(), 'build_hwmon_path 4')
        # 2. glob.glob() returns with empty list (invalid hwmon_path)
        self.pt_bhp_n1(1, '/tmp/nonexistentpath/*/a_file.txt', 'build_hwmon_path 5')
        # 3. os.path.isfile() returns with False (invalid hwmon_path)
        self.pt_bhp_n1(1, '/tmp/nonexistentpath/a_file.txt', 'build_hwmon_path 6')

        del my_td

    def pt_gxt_p1(self, count: int, code: int, temps: List[float], expected: float, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if get_???_temp() function returns different temperature
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_cpu_temp_files(count, temp_list=temps)
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
            # get_1_temp() / get_avg_temp()
            if code in (1, 3):
                cm = FanController.CALC_AVG
            # get_min_temp()
            elif code == 2:
                cm = FanController.CALC_MIN
            # get_max_temp()
            else:  # code == 4:
                cm = FanController.CALC_MAX
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, cm, 5,
                                  4, 2, 30, 50, 35, 100, hwmon_path)
            if code == 1:
                f = my_fc.get_1_temp()
            elif code == 2:
                f = my_fc.get_min_temp()
            elif code == 3:
                f = my_fc.get_avg_temp()
            else:  # code == 4:
                f = my_fc.get_max_temp()
            self.assertEqual(f, expected, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del td

    def pt_gxt_n1(self, count: int, code: int, temps: List[float], error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if get_???_temp() function will not generate IOError/FileNotFoundError exception
            - delete the instances
        """
        td = TestData()
        hwmon_path = td.create_cpu_temp_files(count, temp_list=temps)
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
            if code in (1, 3):
                cm = FanController.CALC_AVG
            # get_min_temp()
            elif code == 2:
                cm = FanController.CALC_MIN
            # get_max_temp()
            else:  # code == 4:
                cm = FanController.CALC_MAX
            my_fc = FanController(my_log, my_ipmi, Ipmi.CPU_ZONE, 'CPU zone', count, cm, 5,
                                  4, 2, 30, 50, 35, 100, hwmon_path)
            del td
            with self.assertRaises(IOError) as cm:
                if code == 1:
                    my_fc.get_1_temp()
                elif code == 2:
                    my_fc.get_min_temp()
                elif code == 3:
                    my_fc.get_avg_temp()
                else:  # code == 4:
                    my_fc.get_max_temp()
            self.assertEqual(type(cm.exception), FileNotFoundError, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config

    def test_get_xxx_temp(self) -> None:
        """This is a unit test for the next functions:
           - FanController.get_1_temp()
           - FanController.get_min_temp()
           - FanController.get_max_temp()
        """
        # get_1_temp()
        # Test expected temperature.
        self.pt_gxt_p1(1, 1, [38.5], 38.5, 'fc get_1_temp 1')
        # Test file read error.
        self.pt_gxt_n1(1, 1, [38.5], 'fc get_1_temp 2')

        # get_min_temp()
        # Test expected temperature
        self.pt_gxt_p1(3, 2, [38.5, 38.5, 38.5], 38.5, 'fc get_min_temp 1')
        self.pt_gxt_p1(3, 2, [38.5, 40.5, 42.5], 38.5, 'fc get_min_temp 2')
        # Test file read error.
        self.pt_gxt_n1(2, 2, [38.5, 40.5], 'fc get_min_temp 3')

        # get_avg_temp()
        # Test expected temperature
        self.pt_gxt_p1(3, 3, [38.5, 38.5, 38.5], 38.5, 'fc get_avg_temp 1')
        self.pt_gxt_p1(3, 3, [38.5, 40.5, 42.5], 40.5, 'fc get_avg_temp 2')
        self.pt_gxt_p1(8, 3, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 45.0, 'fc get_avg_temp 3')
        # Test file read error.
        self.pt_gxt_n1(2, 3, [38.5, 40.5], 'fc get_avg_temp 4')

        # get_max_temp()
        # Test expected temperature
        self.pt_gxt_p1(3, 4, [38.5, 38.5, 38.5], 38.5, 'fc get_max_temp 1')
        self.pt_gxt_p1(3, 4, [38.5, 40.5, 42.5], 42.5, 'fc get_max_temp 2')
        self.pt_gxt_p1(8, 4, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 52.0, 'fc get_max_temp 3')
        # File read error
        self.pt_gxt_n1(2, 4, [38.5, 40.5], 'fc get_max_temp 4')

    def pt_sfl_p1(self, ipmi_zone: int, level: int):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run(), Ipmi.set_fan_level() functions
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
                                  4, 2, 30, 50, 35, 100, None)
            my_fc.set_fan_level(level)
            my_ipmi.set_fan_level.assert_any_call(my_fc.ipmi_zone, level)
        del my_fc
        del my_ipmi
        del my_log
        del my_config
        del td

    def test_set_fan_level(self) -> None:
        """This is a unit test for functions FanController.set_fan_level()"""
        self.pt_sfl_p1(Ipmi.CPU_ZONE, 45)
        self.pt_sfl_p1(Ipmi.HD_ZONE, 65)

    def pt_run_p1(self, steps: int, sensitivity: float, polling: float, min_temp: float, max_temp: float,
                  min_level: int, max_level, temp: float, level: int, error: str) -> None:
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
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

        # Test data set 1 for a generic configuration (dynamic mapping):
        # steps=5, min_temp=30, max_temp=50, min_level=35, max_level=100
        test_values_1: List[Tuple[float, int]] = [
            (30.0, 35), (31.0, 35), (32.0, 35), (33.0, 48), (34.0, 48), (35.0, 48), (36.0, 61), (37.0, 61),
            (38.0, 61), (39.0, 61), (40.0, 61), (41.0, 74), (42.0, 74), (43.0, 74), (44.0, 87), (45.0, 87),
            (46.0, 87), (47.0, 87), (48.0, 87), (49.0, 100), (50.0, 100)
            ]

        # Test data set 2 for special configuration (constant mapping):
        # steps=5, min_temp=40, max_temp=40, min_level=45, max_level=45
        test_values_2: List[Tuple[float, int]] = [
            (30.0, 45), (31.0, 45), (32.0, 45), (33.0, 45), (34.0, 45), (35.0, 45), (36.0, 45), (37.0, 45),
            (38.0, 45), (39.0, 45), (40.0, 45), (41.0, 45), (42.0, 45), (43.0, 45), (44.0, 45), (45.0, 45),
            (46.0, 45), (47.0, 45), (48.0, 45), (49.0, 45), (50.0, 45)
            ]

        # Primitive test counter
        counter = 0

        # Test 1 with a valid data set.
        for i in test_values_1:
            self.pt_run_p1(5, 1, 1, 30, 50, 35, 100, i[0], i[1], f'fc run {counter}')
            counter += 1

        # Test 2 with constant mapping.
        for i in test_values_2:
            self.pt_run_p1(5, 1, 1, 40, 40, 45, 45, i[0], i[1], f'fc run {counter}')
            counter += 1

        # Check level if temperature is under the minimum value.
        self.pt_run_p1(5, 1, 1, 30, 50, 35, 100, 25.0, 35, f'fc run {counter}')
        counter += 1

        # Check level if temperature is above the maximum value.
        self.pt_run_p1(5, 1, 1, 30, 50, 35, 100, 55.0, 100, f'fc run {counter}')
        counter += 1

        """ Default temperature and fan level value pairs
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
        """


if __name__ == "__main__":
    unittest.main()
