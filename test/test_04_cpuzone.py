#!/usr/bin/python3
#
#   test_04_cpuzone.py (C) 2021, Peter Sulyok
#   Unittests for smfc/CpuZone() class.
#
import configparser
import os
import glob
import unittest
from smfc import Log, Ipmi, CpuZone
from unittest.mock import patch, MagicMock
from typing import Any


class CpuZoneTestCase(unittest.TestCase):
    """Unittests for CpuZone() class in smfc.py"""

    @staticmethod
    def normalize_path(path: str) -> str:
        file_names = glob.glob(path)
        return file_names[0]

    # Path for the shell script substituting command ipmitool
    command: str = '/tmp/test_04_cz.sh'
    # Path for hwmon_path file
    temp_file: str = '/tmp/test_04_cz_temp'

    def primitive_test_1_pos(self, steps: int, sensitivity: float, polling: float, min_temp: float,
                             max_temp: float, min_level: int, max_level: int, hwmon_path: str, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete the instances
        """
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
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
            self.assertEqual(my_cpuzone.steps, steps, error)
            self.assertEqual(my_cpuzone.sensitivity, sensitivity, error)
            self.assertEqual(my_cpuzone.polling, polling, error)
            self.assertEqual(my_cpuzone.min_temp, min_temp, error)
            self.assertEqual(my_cpuzone.max_temp, max_temp, error)
            self.assertEqual(my_cpuzone.min_level, min_level, error)
            self.assertEqual(my_cpuzone.max_level, max_level, error)
            self.assertEqual(my_cpuzone.hwmon_path, hwmon_path, error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config

    def primitive_test_2_pos(self, steps: int, sensitivity: float, polling: float, min_temp: float,
                             max_temp: float, min_level: int, max_level: int, hwmon_path: str, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - CpuZone config items are missing
            - ASSERT: if the class attributes cannot be initialized with the default configuration values
            - delete the instances
        """
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
                'hwmon_path': hwmon_path
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone = CpuZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_cpuzone.steps, steps, error)
            self.assertEqual(my_cpuzone.sensitivity, sensitivity, error)
            self.assertEqual(my_cpuzone.polling, polling, error)
            self.assertEqual(my_cpuzone.min_temp, min_temp, error)
            self.assertEqual(my_cpuzone.max_temp, max_temp, error)
            self.assertEqual(my_cpuzone.min_level, min_level, error)
            self.assertEqual(my_cpuzone.max_level, max_level, error)
            self.assertEqual(my_cpuzone.hwmon_path, self.normalize_path(hwmon_path), error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config

    def primitive_test_3_neg(self, steps: int, sensitivity: float, polling: float, min_temp: float,
                             max_temp: float, min_level: int, max_level: int, hwmon_path: str,
                             exception: Any, error: str):
        """This is a primitive negative test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if no exception raised in case of invalid parameters in the __init__
            - delete the instances
        """
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
                'steps': str(steps),
                'sensitivity': str(sensitivity),
                'polling': str(polling),
                'min_temp': str(min_temp),
                'max_temp': str(max_temp),
                'min_level': str(min_level),
                'max_level': str(max_level),
                'hwmon_path': hwmon_path
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            with self.assertRaises(Exception) as cm:
                CpuZone(my_log, my_ipmi, my_config)
            self.assertEqual(type(cm.exception), exception, error)
        del my_ipmi
        del my_log
        del my_config

    def test_init(self) -> None:
        """This is a unittest for function CpuZone.__init__()"""
        # Test valid parameters.
        self.primitive_test_1_pos(5, 4, 2, 30, 55, 35, 100,
                                  './test/hd_8/hwmon/cpu/1/temp1_input', 'cz init 1')
        self.primitive_test_2_pos(5, 4, 2, 30, 55, 35, 100,
                                  './test/hd_8/hwmon/cpu/1/temp1_input', 'cz init 2')
        
        # Test invalid parameters.
        self.primitive_test_3_neg(5, 4, 2, 30, 55, 35, 100,
                                  './test/hd_8/hwmon/cpu/x/temp1_input', ValueError, 'cz init 3')
        self.primitive_test_3_neg(5, 4, 2, 30, 55, 35, 100,
                                  './test/hd_8/hwmon/cpu/&?/temp1_input', IndexError, 'cz init 4')

    def primitive_test_4_pos(self, temperature: float, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - calls CpuZone.get_temp()
            - ASSERT: if the return temperature is different than the value in the file
            - delete the instances
        """
        with open(self.temp_file, "w+") as f:
            f.write(str(temperature * 1000))
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
                'steps': '5',
                'sensitivity': '4',
                'polling': '2',
                'min_temp': '30',
                'max_temp': '55',
                'min_level': '35',
                'max_level': '100',
                'hwmon_path': self.temp_file
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone = CpuZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_cpuzone.get_temp(), temperature, error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config
        os.remove(self.temp_file)

    def primitive_test_5_neg(self, exception: Any, error: str):
        """This is a primitive negative test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - calls CpuZone.get_temp()
            - ASSERT: if no exception raised in case of file IO errors
            - delete the instances
        """
        with open(self.temp_file, "w+") as f:
            f.write('38500')
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
                'steps': '5',
                'sensitivity': '4',
                'polling': '2',
                'min_temp': '30',
                'max_temp': '55',
                'min_level': '35',
                'max_level': '100',
                'hwmon_path': self.temp_file
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone = CpuZone(my_log, my_ipmi, my_config)
            os.remove(self.temp_file)
            with self.assertRaises(Exception) as cm:
                my_cpuzone.get_temp()
            self.assertTrue(type(cm.exception) in exception, error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config

    def test_get_temp(self) -> None:
        """This is a unittest for function CpuZone.get_temp()"""
        # Test valid parameters.
        self.primitive_test_4_pos(38.5, 'cz get_temp 1')
        self.primitive_test_4_pos(0, 'cz get_temp 2')
        self.primitive_test_4_pos(1000, 'cz get_temp 3')
        # Test exceptions.
        self.primitive_test_5_neg((IOError, FileNotFoundError), 'cz get_temp 4')

    def primitive_test_6_pos(self, level: int):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - calls CpuZone.set_fan_level()
            - ASSERT: if the Ipmi.set_fan_level was called with different parameters
            - delete the instances
        """
        with open(self.temp_file, "w+") as f:
            f.write('38500')
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['CPU zone'] = {
                'enabled': '1',
                'steps': '5',
                'sensitivity': '4',
                'polling': '2',
                'min_temp': '30',
                'max_temp': '55',
                'min_level': '35',
                'max_level': '100',
                'hwmon_path': self.temp_file
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_ipmi.set_fan_level = MagicMock(name='set_fan_level')
            my_ipmi.set_fan_level.return_value = Ipmi.SUCCESS
            my_cpuzone = CpuZone(my_log, my_ipmi, my_config)
            my_cpuzone.set_fan_level(level)
            my_ipmi.set_fan_level.assert_any_call(Ipmi.CPU_ZONE, level)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config
        os.remove(self.temp_file)

    def test_set_fan_level(self) -> None:
        """This is a unittest for function CpuZone.set_fan_level()"""
        # Test valid parameters.
        self.primitive_test_6_pos(45)   # 'cz set_fan_level 1'


if __name__ == "__main__":
    unittest.main()
