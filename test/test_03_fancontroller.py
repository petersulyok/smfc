#!/usr/bin/python3
#
#   test_03_fancontroller.py (C) 2021, Peter Sulyok
#   Unittests for smfc/FanController() class.
#
import configparser
import time
import unittest
from smfc import FanController, Log, Ipmi
from unittest.mock import patch, MagicMock
from typing import List, Tuple


class FanControllerTestCase(unittest.TestCase):
    """Unittests for FanController() class in smfc.py"""

    # Default path for the shell script substituting command ipmitool
    command: str = '/tmp/test_03_fc.sh'

    def primitive_test_1_pos(self, name: str, steps: int, sensitivity: float, polling: float,
                             min_temp: float, max_temp: float, min_level: int, max_level, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
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
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, name, steps, sensitivity, polling, min_temp, max_temp,
                                  min_level, max_level)
        self.assertEqual(my_fc.log, my_log, error)
        self.assertEqual(my_fc.ipmi, my_ipmi, error)
        self.assertEqual(my_fc.name, name, error)
        self.assertEqual(my_fc.steps, steps, error)
        self.assertEqual(my_fc.sensitivity, sensitivity, error)
        self.assertEqual(my_fc.polling, polling, error)
        self.assertEqual(my_fc.min_temp, min_temp, error)
        self.assertEqual(my_fc.max_temp, max_temp, error)
        self.assertEqual(my_fc.min_level, min_level, error)
        self.assertEqual(my_fc.max_level, max_level, error)
        self.assertEqual(my_fc.level_step, (max_level - min_level) / steps, error)
        self.assertEqual(my_fc.last_temp, 0, error)
        self.assertEqual(my_fc.last_level, 0, error)
        del my_fc
        del my_ipmi
        del my_log
        del my_config

    def primitive_test_2_neg(self, steps: int, sensitivity: float, polling: float, min_temp: float,
                             max_temp: float, min_level: int, max_level, error: str):
        """This is a primitive negative test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if exception not raised in case of invalid parameter values
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
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            with self.assertRaises(ValueError) as cm: 
                FanController(my_log, my_ipmi, 'Test Zone', steps, sensitivity, polling, min_temp, max_temp,
                              min_level, max_level)
            self.assertTrue(type(cm.exception) is ValueError, error)
        del my_ipmi
        del my_log
        del my_config

    def test_init(self) -> None:
        """This is a unittest for function FanController.__init__()"""
        # Test valid parameters.
        self.primitive_test_1_pos('Test Zone', 5, 4, 2, 30, 50, 35, 100, 'fc init 1')
        # Test invalid parameters.
        self.primitive_test_2_neg(-5, 4, 2, 30, 50, 35, 100, 'fc init 2')
        self.primitive_test_2_neg(5, -4, 2, 30, 50, 35, 100, 'fc init 3')
        self.primitive_test_2_neg(5, 4, -2, 30, 50, 35, 100, 'fc init 4')
        self.primitive_test_2_neg(5, 4, 2, 50, 30, 35, 100, 'fc init 5')
        self.primitive_test_2_neg(5, 4, 2, 30, 50, 100, 35, 'fc init 6')

    def primitive_test_3_pos(self, name: str, steps: int, sensitivity: float, polling: float, min_temp: float,
                             max_temp: float, min_level: int, max_level, temp: float, level: int, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and FanController classes
            - ASSERT: if the controller generates different fan level based on the input zone temperature
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
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_fc = FanController(my_log, my_ipmi, name, steps, sensitivity, polling, min_temp, max_temp,
                                  min_level, max_level)
            my_fc.get_temp = MagicMock(name='get_temp')
            my_fc.get_temp.return_value = temp
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

    def test_run(self) -> None:
        """This is a unittest for function FanController.run()"""

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
            self.primitive_test_3_pos('Test Zone', 5, 0, 0, 30, 50, 35, 100, i[0], i[1], 'fc run {}'.format(counter))
            counter += 1

        # Test 2 with constant mapping.
        for i in test_values_2:
            self.primitive_test_3_pos('Test Zone', 5, 0, 0, 40, 40, 45, 45, i[0], i[1], 'fc run {}'.format(counter))
            counter += 1

        # Check level if temperature is under the minimum value.
        self.primitive_test_3_pos('Test Zone', 5, 0, 0, 30, 50, 35, 100, 25.0, 35, 'fc run {}'.format(counter))
        counter += 1

        # Check level if temperature is above the maximum value.
        self.primitive_test_3_pos('Test Zone', 5, 0, 0, 30, 50, 35, 100, 55.0, 100, 'fc run {}'.format(counter))
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
