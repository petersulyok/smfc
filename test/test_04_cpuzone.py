#!/usr/bin/python3
#
#   test_04_cpuzone.py (C) 2021-2022, Peter Sulyok
#   Unit tests for smfc.CpuZone() class.
#
import configparser
import glob
import unittest
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
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
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
                'hwmon_path': hwmon_path
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
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
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
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
                'count': str(count),
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
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
                'count': str(count)
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
        def mocked_glob(file: str, *args, **kwargs):
            # if file.startswith('/sys/devices/platform'):
                return None     # Invalid file name generated here !
            # return original_glob(file, *args, **kwargs)

        my_td = TestData()
        command = my_td.create_command_file()
        original_glob = glob.glob
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_glob = MagicMock(side_effect=mocked_glob)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run), \
             patch('glob.glob', mock_glob):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
                'count': str(count)
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


if __name__ == "__main__":
    unittest.main()
