#!/usr/bin/python3
#
#   test_02_ipmi.py (C) 2021, Peter Sulyok
#   Unit tests for smfc.Ipmi() class.
#

import configparser
import subprocess
import unittest
from typing import Any
from unittest.mock import patch, MagicMock
from test_00_data import TestData
from smfc import Log, Ipmi


class IpmiTestCase(unittest.TestCase):
    """Unit test class for smfc.Ipmi() class"""

    def pt_init_p1(self, mode_delay: int, level_delay: int, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - create a shell script for IPMI command parameter
            - mock print() function
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - ASSERT: if the mocked print function was called wrong number of times
            - delete the instances
            - delete shell script
        """
        td = TestData()
        command = td.create_command_file()
        mock_print = MagicMock()
        with patch('builtins.print', mock_print):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': str(mode_delay),
                'fan_level_delay': str(level_delay)
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
        self.assertEqual(my_ipmi.command, command, error)
        self.assertEqual(my_ipmi.fan_mode_delay, mode_delay, error)
        self.assertEqual(my_ipmi.fan_level_delay, level_delay, error)
        self.assertEqual(mock_print.call_count, 3 + 4)  # Log-3, Ipmi-4
        del my_ipmi
        del my_log
        del my_config
        del td

    def pt_init_n1(self, cmd_exists: bool, mode_delay: int, level_delay: int,
                   exception: Any, error: str) -> None:
        """Primitive negative test function. It contains the following steps:
            - create a shell script depending on flag need_to_create
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the specified exception was not raised during __init__
            - delete all instances
            - delete shell script if needed
        """
        td = TestData()
        command = td.create_command_file()
        if not cmd_exists:
            td.delete_file(command)
        my_config = configparser.ConfigParser()
        my_config['Ipmi'] = {
            'command': command,
            'fan_mode_delay': str(mode_delay),
            'fan_level_delay': str(level_delay)
        }
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        with self.assertRaises(Exception) as cm:
            Ipmi(my_log, my_config)
        self.assertEqual(type(cm.exception), exception, error)
        del my_log
        del my_config
        del td

    def test_init(self) -> None:
        """This is a unit test for function Ipmi.__init__()"""

        # Test valid parameters.
        self.pt_init_p1(10, 2, 'ipmi init 1')

        # Test raising exception on invalid parameters.
        self.pt_init_n1(True, -1, 2, ValueError, 'ipmi init 2')
        self.pt_init_n1(True, 10, -2, ValueError, 'ipmi init 3')
        self.pt_init_n1(False, 10, 2, FileNotFoundError, 'ipmi init 4')

    def pt_gfm_p1(self, expected_mode: int, error: str) -> None:
        """Primitive positive test function. It contains the following steps:
            - create a shell script with an expected output
            - mock print() function
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the get_fan_mode() returns different value than the expected one
            - delete the instances
            - delete shell script
        """
        td = TestData()
        command = td.create_command_file(f'echo " {expected_mode:02}"')
        mock_print = MagicMock()
        with patch('builtins.print', mock_print):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '10',
                'fan_level_delay': '2'
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            fm = my_ipmi.get_fan_mode()
        self.assertEqual(fm, expected_mode, error)
        del my_ipmi
        del my_log
        del my_config
        del td

    def pt_gfm_n1(self, s: str, delete: bool, exception: Any, error: str) -> None:
        """Primitive negative test function. It contains the following steps:
            - create a shell script for IPMI command parameter
            - initialize a Config, Log, Ipmi classes
            - delete shell script
            - call get_fan_mode() function
            - ASSERT: if the no exception raised
            - delete the class instances
        """
        td = TestData()
        command = td.create_command_file('echo " ' + s + '"')
        my_config = configparser.ConfigParser()
        my_config['Ipmi'] = {
            'command': command,
            'fan_mode_delay': '10',
            'fan_level_delay': '2'
        }
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config)
        if delete:
            td.delete_file(command)
        with self.assertRaises(Exception) as cm:
            my_ipmi.get_fan_mode()
        self.assertEqual(type(cm.exception), exception, error)
        del my_ipmi
        del my_log
        del my_config
        del td

    def test_get_fan_mode(self) -> None:
        """This is a unit test for function Ipmi.get_fan_mode()"""

        # Test saving valid parameters.
        self.pt_gfm_p1(Ipmi.STANDARD_MODE, 'ipmi get_fan_mode 1')
        self.pt_gfm_p1(Ipmi.FULL_MODE, 'ipmi get_fan_mode 2')
        self.pt_gfm_p1(Ipmi.OPTIMAL_MODE, 'ipmi get_fan_mode 3')
        self.pt_gfm_p1(Ipmi.HEAVY_IO_MODE, 'ipmi get_fan_mode 4')

        # Test raising exception on missing command or invalid integer value.
        self.pt_gfm_n1('01', True, FileNotFoundError, 'ipmi get_fan_mode 5')
        self.pt_gfm_n1('NA', False, ValueError, 'ipmi get_fan_mode 6')

    def p1_gfmn_p1(self, fm: int, fms: str, error: str) -> None:
        """Primitive positive test function. It contains the following steps:
            - create a shell script for ipmitool substitution
            - mock print() function
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the get_fan_mode_name() returns with a different string than expected
            - delete the instances
            - delete shell script
        """
        td = TestData()
        command = td.create_command_file('echo " 01"')
        mock_print = MagicMock()
        with patch('builtins.print', mock_print):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': command,
                'fan_mode_delay': '1',
                'fan_level_delay': '2'
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            s = my_ipmi.get_fan_mode_name(fm)
        self.assertEqual(fms, s, error)
        del my_ipmi
        del my_log
        del my_config
        del td

    def test_get_fan_mode_name(self) -> None:
        """This is a unit test for function Ipmi.get_fan_mode_name()"""

        # Test valid parameters.
        self.p1_gfmn_p1(Ipmi.STANDARD_MODE, 'STANDARD_MODE', 'ipmi get_fan_mode_name 1')
        self.p1_gfmn_p1(Ipmi.FULL_MODE, 'FULL_MODE', 'ipmi get_fan_mode_name 2')
        self.p1_gfmn_p1(Ipmi.OPTIMAL_MODE, 'OPTIMAL_MODE', 'ipmi get_fan_mode_name 3')
        self.p1_gfmn_p1(Ipmi.HEAVY_IO_MODE, 'HEAVY IO MODE', 'ipmi get_fan_mode_name 4')
        self.p1_gfmn_p1(100, 'ERROR', 'ipmi get_fan_mode_name 5')

    def pt_sfm_p1(self, fan_mode: int) -> None:
        """Primitive positive test function. It contains the following steps:
            - create a shell script for IPMI command parameter
            - mock subprocess.run() function
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if set_fan_mode() calls subprocess.run() command with other parameters than expected
            - delete the instances
            - delete shell script
        """
        td = TestData()
        command = td.create_command_file()
        my_config = configparser.ConfigParser()
        my_config['Ipmi'] = {
            'command': command,
            'fan_mode_delay': '0',
            'fan_level_delay': '1'
        }
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config)
        mock_subprocess_run = MagicMock()
        with patch('subprocess.run', mock_subprocess_run):
            my_ipmi.set_fan_mode(fan_mode)
        mock_subprocess_run.assert_called_with([command, 'raw', '0x30', '0x45', '0x01', str(fan_mode)],
                                               check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        del my_ipmi
        del my_log
        del my_config
        del td

    def pt_sfm_n1(self, no_script: bool, fan_mode: int, exception: Any, error: str) -> None:
        """Primitive negative test function. It contains the following steps:
            - create a shell script for IPMI command parameter
            - mock print() function
            - initialize a Config, Log, Ipmi classes
            - the shell script maybe deleted (depending on 'no_script' parameter)
            - ASSERT: if exception not raised by set_fan_mode() in case of invalid parameters
            - delete all instances
            - delete shell script (depending on 'no_script' parameter)
        """
        td = TestData()
        command = td.create_command_file()
        my_config = configparser.ConfigParser()
        my_config['Ipmi'] = {
            'command': command,
            'fan_mode_delay': '0',
            'fan_level_delay': '1'
        }
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config)
        if no_script:
            td.delete_file(command)
        with self.assertRaises(Exception) as cm:
            my_ipmi.set_fan_mode(fan_mode)
        self.assertEqual(type(cm.exception), exception, error)
        del my_ipmi
        del my_log
        del my_config
        del td

    def test_set_fan_mode(self) -> None:
        """This is a unit test for function Ipmi.set_fan_mode()"""

        # Test valid parameters.
        self.pt_sfm_p1(Ipmi.STANDARD_MODE)   # 'ipmi set_fan_mode 1'
        self.pt_sfm_p1(Ipmi.FULL_MODE)       # 'ipmi set_fan_mode 2'
        self.pt_sfm_p1(Ipmi.OPTIMAL_MODE)    # 'ipmi set_fan_mode 3'
        self.pt_sfm_p1(Ipmi.HEAVY_IO_MODE)   # 'ipmi set_fan_mode 4'

        # Test raising exception on invalid parameters.
        self.pt_sfm_n1(False, 100, ValueError, 'ipmi get_fan_mode 5')
        self.pt_sfm_n1(True, Ipmi.FULL_MODE, FileNotFoundError, 'ipmi get_fan_mode 6')

    def pt_sfl_p1(self, zone: int, level: int) -> None:
        """Primitive positive test function. It contains the following steps:
            - mock print(), subprocess.run() functions
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if set_fan_level() calls subprocess.run() command with other parameters than expected
            - delete the instances
        """
        td = TestData()
        command = td.create_command_file()
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
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_ipmi.set_fan_level(zone, level)
            mock_subprocess_run.assert_called_with([command, 'raw', '0x30', '0x70', '0x66', '0x01',
                                                    str(zone), str(level)],
                                                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            del my_ipmi
            del my_log
            del my_config
            del td

    def pt_sfl_n1(self, zone: int, level: int, exception: Any, error: str) -> None:
        """Primitive negative test function. It contains the following steps:
            - mock print(), subprocess.run() function
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if set_fan_level() does not raise exception in case of invalid parameters
            - delete the instances
        """
        td = TestData()
        command = td.create_command_file()
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
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            with self.assertRaises(Exception) as cm:
                my_ipmi.set_fan_level(zone, level)
            self.assertTrue(isinstance(cm.exception, exception), error)
        del my_log
        del my_config
        del td

    def test_set_fan_level(self) -> None:
        """This is a unit test for function Ipmi.set_fan_level()"""

        # Test valid parameters.
        self.pt_sfl_p1(Ipmi.CPU_ZONE, 0)     # 'ipmi set_fan_level 1'
        self.pt_sfl_p1(Ipmi.CPU_ZONE, 50)    # 'ipmi set_fan_level 2'
        self.pt_sfl_p1(Ipmi.CPU_ZONE, 100)   # 'ipmi set_fan_level 3'

        self.pt_sfl_p1(Ipmi.HD_ZONE, 0)      # 'ipmi set_fan_level 4'
        self.pt_sfl_p1(Ipmi.HD_ZONE, 50)     # 'ipmi set_fan_level 5'
        self.pt_sfl_p1(Ipmi.HD_ZONE, 100)    # 'ipmi set_fan_level 6'

        # Test invalid parameters and exceptions.
        self.pt_sfl_n1(Ipmi.CPU_ZONE, -1, ValueError, 'ipmi set_fan_level 7')
        self.pt_sfl_n1(Ipmi.CPU_ZONE, 101, ValueError, 'ipmi set_fan_level 8')
        self.pt_sfl_n1(-1, 50, ValueError, 'ipmi set_fan_level 9')
        self.pt_sfl_n1(10, 50, ValueError, 'ipmi set_fan_level 10')


if __name__ == "__main__":
    unittest.main()
