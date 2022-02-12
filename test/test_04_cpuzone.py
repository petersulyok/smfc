#!/usr/bin/python3
#
#   test_04_cpuzone.py (C) 2021-2022, Peter Sulyok
#   Unit test for smfc.CpuZone() class.
#
import configparser
import unittest
import smfc
from smfc import Log, Ipmi, CpuZone
from test_00_data import TestData
from unittest.mock import patch, MagicMock


class CpuZoneTestCase(unittest.TestCase):
    """Unit test class for smfc.CpuZone() class"""

    def primitive_test_1_pos(self, count: int, temp_calc: int, steps: int, sensitivity: float, polling: float,
                             min_temp: float, max_temp: float, min_level: int, max_level: int, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete the instances
        """
        my_td = TestData()
        command = my_td.create_command_file()
        hwmon_path = my_td.get_cpu_1()
        if count == 2:
            hwmon_path = my_td.get_cpu_2()
        if count == 4:
            hwmon_path = my_td.get_cpu_4()
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
                'hwmon_path': '\n'.join(hwmon_path)+'\n'
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone=CpuZone(my_log, my_ipmi, my_config)
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
            self.assertEqual(my_cpuzone.hwmon_path, hwmon_path, error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def primitive_test_2_pos(self, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - ASSERT: if the class attributes contain different values than the default configuration parameters
            - delete the instances
        """
        my_td=TestData()
        command=my_td.create_command_file()
        hwmon_path=my_td.get_cpu_1()
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
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_cpuzone=CpuZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_cpuzone.count, 1, error)
            self.assertEqual(my_cpuzone.temp_calc, smfc.FanController.CALC_AVG, error)
            self.assertEqual(my_cpuzone.steps, 5, error)
            self.assertEqual(my_cpuzone.sensitivity, 4, error)
            self.assertEqual(my_cpuzone.polling, 2, error)
            self.assertEqual(my_cpuzone.min_temp, 30, error)
            self.assertEqual(my_cpuzone.max_temp, 55, error)
            self.assertEqual(my_cpuzone.min_level, 35, error)
            self.assertEqual(my_cpuzone.max_level, 100, error)
            # not tested, maybe the path is not valid where the test is executed.
            #self.assertEqual(my_cpuzone.hwmon_path, '/sys/devices/platform/coretemp.0/hwmon/hwmon*/temp1_input', error)
        del my_cpuzone
        del my_ipmi
        del my_log
        del my_config
        del my_td

    def test_init(self) -> None:
        """This is a unit test for function CpuZone.__init__()"""
        # Test valid parameters.
        self.primitive_test_1_pos(1, smfc.FanController.CALC_AVG, 5, 4, 2, 30, 55, 35, 100, 'cz init 1')
        self.primitive_test_1_pos(2, smfc.FanController.CALC_AVG, 5, 4, 2, 30, 55, 35, 100, 'cz init 1')
        self.primitive_test_1_pos(4, smfc.FanController.CALC_AVG, 5, 4, 2, 30, 55, 35, 100, 'cz init 1')
        self.primitive_test_2_pos('cz init 2')


if __name__ == "__main__":
    unittest.main()
