#!/usr/bin/python3
#
#   test_04_cpuzone.py (C) 2021-2023, Peter Sulyok
#   Unit tests for smfc.CpuZone() class.
#
import configparser
import glob
import os
import unittest
from typing import List
from unittest.mock import patch, MagicMock
from test_00_data import TestData
from smfc import Log, Ipmi, FanController, CpuZone


class CpuZoneTestCase(unittest.TestCase):
    """Unit test class for smfc.CpuZone() class"""

    def pt_init_p1(self, count: int, temp_calc: int, steps: int, sensitivity: float, polling: float, min_temp: float,
                   max_temp: float, min_level: int, max_level: int, hwmon_path: str, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete all instances
        """
        my_td = TestData()
        command = my_td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config[Ipmi.CS_IPMI] = {
                Ipmi.CV_IPMI_COMMAND: command,
                Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
                Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0'
            }
            my_config[CpuZone.CS_CPU_ZONE] = {
                CpuZone.CV_CPU_ZONE_ENABLED: '1',
                CpuZone.CV_CPU_ZONE_COUNT: str(count),
                CpuZone.CV_CPU_ZONE_TEMP_CALC: str(temp_calc),
                CpuZone.CV_CPU_ZONE_STEPS: str(steps),
                CpuZone.CV_CPU_ZONE_SENSITIVITY: str(sensitivity),
                CpuZone.CV_CPU_ZONE_POLLING: str(polling),
                CpuZone.CV_CPU_ZONE_MIN_TEMP: str(min_temp),
                CpuZone.CV_CPU_ZONE_MAX_TEMP: str(max_temp),
                CpuZone.CV_CPU_ZONE_MIN_LEVEL: str(min_level),
                CpuZone.CV_CPU_ZONE_MAX_LEVEL: str(max_level),
                CpuZone.CV_CPU_ZONE_HWMON_PATH: hwmon_path
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone = CpuZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_cpuzone.log, my_log, error)
            self.assertEqual(my_cpuzone.ipmi, my_ipmi, error)
            self.assertEqual(my_cpuzone.ipmi_zone, Ipmi.CPU_ZONE, error)
            self.assertEqual(my_cpuzone.name, "CPU zone", error)
            self.assertEqual(my_cpuzone.count, count, error)
            self.assertEqual(my_cpuzone.temp_calc, temp_calc, error)
            self.assertEqual(my_cpuzone.steps, steps, error)
            self.assertEqual(my_cpuzone.sensitivity, sensitivity, error)
            self.assertEqual(my_cpuzone.polling, polling, error)
            self.assertEqual(my_cpuzone.min_temp, min_temp, error)
            self.assertEqual(my_cpuzone.max_temp, max_temp, error)
            self.assertEqual(my_cpuzone.min_level, min_level, error)
            self.assertEqual(my_cpuzone.max_level, max_level, error)
            self.assertEqual(my_cpuzone.hwmon_path, my_td.create_normalized_path_list(hwmon_path), error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def pt_init_p2(self, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run(), glob.glob() functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if the class attributes contain different values than the default configuration values
            - delete all instances
        """
        # Mock function for glob.glob().
        def mocked_glob(file: str, *args, **kwargs):
            if file.startswith('/sys/devices/platform'):
                file = my_td.td_dir + file
            return original_glob(file, *args, **kwargs)

        my_td = TestData()
        command = my_td.create_command_file()
        hwmon_path = my_td.get_cpu_1()
        original_glob = glob.glob
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_glob = MagicMock(side_effect=mocked_glob)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run), \
             patch('glob.glob', mock_glob):
            my_config = configparser.ConfigParser()
            my_config[Ipmi.CS_IPMI] = {
                Ipmi.CV_IPMI_COMMAND: command,
                Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
                Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0'
            }
            my_config[CpuZone.CS_CPU_ZONE] = {
                CpuZone.CV_CPU_ZONE_ENABLED: '1',
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone = CpuZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_cpuzone.count, 1, error)
            self.assertEqual(my_cpuzone.temp_calc, FanController.CALC_AVG, error)
            self.assertEqual(my_cpuzone.steps, 6, error)
            self.assertEqual(my_cpuzone.sensitivity, 3.0, error)
            self.assertEqual(my_cpuzone.polling, 2, error)
            self.assertEqual(my_cpuzone.min_temp, 30, error)
            self.assertEqual(my_cpuzone.max_temp, 60, error)
            self.assertEqual(my_cpuzone.min_level, 35, error)
            self.assertEqual(my_cpuzone.max_level, 100, error)
            self.assertEqual(my_cpuzone.hwmon_path, my_td.create_normalized_path_list(hwmon_path), error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def pt_init_n1(self, count: int, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), subprocesses.run() functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if invalid counter value does not generate ValueError exception
            - delete all instances
        """
        my_td = TestData()
        command = my_td.create_command_file()
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config[Ipmi.CS_IPMI] = {
                Ipmi.CV_IPMI_COMMAND: command,
                Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
                Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0'
            }
            my_config[CpuZone.CS_CPU_ZONE] = {
                CpuZone.CV_CPU_ZONE_ENABLED: '1',
                CpuZone.CV_CPU_ZONE_COUNT: str(count),
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            with self.assertRaises(Exception) as cm:
                CpuZone(my_log, my_ipmi, my_config)
            self.assertEqual(type(cm.exception), ValueError, error)
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_init(self) -> None:
        """This is a unit test for function CpuZone.__init__()"""
        my_td = TestData()
        # Test valid parameters.
        self.pt_init_p1(1, FanController.CALC_AVG, 5, 4, 2, 30, 55, 35, 100, my_td.get_cpu_1(), 'cz init 1')
        self.pt_init_p1(2, FanController.CALC_AVG, 5, 4, 2, 30, 55, 35, 100, my_td.get_cpu_2(), 'cz init 2')
        self.pt_init_p1(4, FanController.CALC_AVG, 5, 4, 2, 30, 55, 35, 100, my_td.get_cpu_4(), 'cz init 3')

        # Test default configuration values.
        self.pt_init_p2('cz init 4')

        # Test invalid count values.
        self.pt_init_n1(0, 'cz init 5')
        self.pt_init_n1(-10, 'cz init 6')
        del my_td

    def pt_bhp_p1(self, count: int, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run(), glob.glob() functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if build_hwmon_path() will not create the expected list
            - delete all instances
        """
        # Mock function for glob.glob().
        def mocked_glob(file: str, *args, **kwargs):
            if file.startswith('/sys/devices/platform'):
                file = my_td.td_dir + file
            return original_glob(file, *args, **kwargs)

        my_td = TestData()
        command = my_td.create_command_file()
        if count == 1:
            hwmon_path = my_td.get_cpu_1()
        elif count == 2:
            hwmon_path = my_td.get_cpu_2()
        else:
            hwmon_path = my_td.get_cpu_4()
        original_glob = glob.glob
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_glob = MagicMock(side_effect=mocked_glob)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run), \
             patch('glob.glob', mock_glob):
            my_config = configparser.ConfigParser()
            my_config[Ipmi.CS_IPMI] = {
                Ipmi.CV_IPMI_COMMAND: command,
                Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
                Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0'
            }
            my_config[CpuZone.CS_CPU_ZONE] = {
                CpuZone.CV_CPU_ZONE_ENABLED: '1',
                CpuZone.CV_CPU_ZONE_COUNT: str(count)
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone = CpuZone(my_log, my_ipmi, my_config)
            # build_hwmon_path() will be called from __init__(), no need to call it directly
            # my_cpuzone.build_hwmon_path(hwmon_path)
            self.assertEqual(my_cpuzone.hwmon_path, my_td.create_path_list(hwmon_path), error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def pt_bhp_n1(self, count: int, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), subprocesses.run(), glob.glob() functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if build_hwmon_path() will not raise assert
            - delete all instances
        """
        # Mock function for glob.glob(). This function will generate invalid file name!
        # pragma pylint: disable=unused-argument
        def mocked_glob(file: str, *args, **kwargs):
            # if file.startswith('/sys/devices/platform'):
            return None     # Invalid file name generated here !
            # return original_glob(file, *args, **kwargs)
        # pragma pylint: enable=unused-argument

        my_td = TestData()
        command = my_td.create_command_file()
        # original_glob = glob.glob
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_glob = MagicMock(side_effect=mocked_glob)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run), \
             patch('glob.glob', mock_glob):
            my_config = configparser.ConfigParser()
            my_config[Ipmi.CS_IPMI] = {
                Ipmi.CV_IPMI_COMMAND: command,
                Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
                Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0'
            }
            my_config[CpuZone.CS_CPU_ZONE] = {
                CpuZone.CV_CPU_ZONE_ENABLED: '1',
                CpuZone.CV_CPU_ZONE_COUNT: str(count)
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            with self.assertRaises(Exception) as cm:
                # build_hwmon_path() will be called from __init__(), no need to call it directly
                CpuZone(my_log, my_ipmi, my_config)
            self.assertEqual(type(cm.exception), ValueError, error)
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_build_hwmon_path(self) -> None:
        """This is a unit test for function CpuZone.build_hwmon_path()"""

        # Test expected values.
        self.pt_bhp_p1(1, 'cz build_hwmon_path 1')
        self.pt_bhp_p1(2, 'cz build_hwmon_path 2')
        self.pt_bhp_p1(4, 'cz build_hwmon_path 3')

        # Test invalid / non-existing hwmon_path.
        self.pt_bhp_n1(1, 'cz build_hwmon_path 4')

    def pt_gnt_p1(self, count: int, index: int, temps: List[float], error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocesses.run(), glob.glob(), CpuZone._get_nth_temp() functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if _get_nth_temp() returns a different temperature than the expected one
            - delete all instances
        """
        # Mock function for glob.glob().
        def mocked_glob(file: str, *args, **kwargs):
            if file.startswith('/sys/devices/platform'):
                file = my_td.td_dir + file
            return original_glob(file, *args, **kwargs)

        my_td = TestData()
        command = my_td.create_command_file()
        if count == 1:
            my_td.get_cpu_1(temps)
        elif count == 2:
            my_td.get_cpu_2(temps)
        else:
            my_td.get_cpu_4(temps)
        original_glob = glob.glob
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_glob = MagicMock(side_effect=mocked_glob)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run), \
             patch('glob.glob', mock_glob):
            my_config = configparser.ConfigParser()
            my_config[Ipmi.CS_IPMI] = {
                Ipmi.CV_IPMI_COMMAND: command,
                Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
                Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0'
            }
            my_config[CpuZone.CS_CPU_ZONE] = {
                CpuZone.CV_CPU_ZONE_ENABLED: '1',
                CpuZone.CV_CPU_ZONE_COUNT: str(count)
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone = CpuZone(my_log, my_ipmi, my_config)

            self.assertEqual(my_cpuzone._get_nth_temp(index), temps[index], error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def pt_gnt_n1(self, index: int, operation: int, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), subprocesses.run(), glob.glob(), CpuZone._get_nth_temp() functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if _get_nth_temp() will not raise an exception for different error conditions
            - delete all instances
        """
        hwmon: str

        # Mock function for glob.glob().
        def mocked_glob(file: str, *args, **kwargs):
            if file.startswith('/sys/devices/platform'):
                file = my_td.td_dir + file
            return original_glob(file, *args, **kwargs)

        my_td = TestData()
        command = my_td.create_command_file()
        hwmon = my_td.get_cpu_1()
        original_glob = glob.glob
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_glob = MagicMock(side_effect=mocked_glob)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run), \
             patch('glob.glob', mock_glob):
            my_config = configparser.ConfigParser()
            my_config[Ipmi.CS_IPMI] = {
                Ipmi.CV_IPMI_COMMAND: command,
                Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
                Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0'
            }
            my_config[CpuZone.CS_CPU_ZONE] = {
                CpuZone.CV_CPU_ZONE_ENABLED: '1',
                CpuZone.CV_CPU_ZONE_COUNT: '1'
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone = CpuZone(my_log, my_ipmi, my_config)
            # Delete file
            if operation == 1:
                hwmon = hwmon.strip()
                my_td.delete_file(hwmon)
            # Create invalid numeric input
            elif operation == 2:
                os.system('echo "invalid value" >' + hwmon)
            # Index overflow, do nothing.
            else:
                # operation == 3
                pass
            with self.assertRaises(Exception) as cm:
                my_cpuzone._get_nth_temp(index)
            self.assertTrue(type(cm.exception) in [IOError, FileNotFoundError, ValueError, IndexError], error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_get_nth_temp(self) -> None:
        """This is a unit test for function CpuZone._get_nth_temp()"""

        # Test valid/expected values.
        self.pt_gnt_p1(1, 0, [38.5], 'cz _get_nth_temp 1')
        self.pt_gnt_p1(2, 0, [38.5, 40.5], 'cz _get_nth_temp 2')
        self.pt_gnt_p1(2, 1, [38.5, 40.5], 'cz _get_nth_temp 3')
        self.pt_gnt_p1(4, 0, [38.5, 40.5, 42.5, 44.5], 'cz _get_nth_temp 4')
        self.pt_gnt_p1(4, 1, [38.5, 40.5, 42.5, 44.5], 'cz _get_nth_temp 5')
        self.pt_gnt_p1(4, 2, [38.5, 40.5, 42.5, 44.5], 'cz _get_nth_temp 6')
        self.pt_gnt_p1(4, 3, [38.5, 40.5, 42.5, 44.5], 'cz _get_nth_temp 7')

        # Test exceptions
        # 1. invalid hwmon file name
        self.pt_gnt_n1(0, 1, 'cz _get_nth_temp 8')
        # 2. invalid numeric value
        self.pt_gnt_n1(0, 2, 'cz _get_nth_temp 9')
        # 3. invalid index value
        self.pt_gnt_n1(3, 3, 'cz _get_nth_temp 10')


if __name__ == "__main__":
    unittest.main()
