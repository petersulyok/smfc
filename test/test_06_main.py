#!/usr/bin/python3
#
#   test_06_main.py (C) 2021-2022, Peter Sulyok
#   Unit tests for smfc.main() function.
#
import configparser
import sys
import unittest
from unittest.mock import patch, MagicMock
from test_00_data import TestData
import smfc


class MainTestCase(unittest.TestCase):
    """Unit test for smfc.main() function"""

    sleep_counter: int

    def pt_main_n1(self, command_line: str, exit_code: int, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), argparse.ArgumentParser._print_message() functions
            - execute smfc.main()
            - ASSERT: if not sys.exit will not happen with the specified exit code
        """
        mock_print = MagicMock()
        mock_parser_print_help = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('argparse.ArgumentParser._print_message', mock_parser_print_help):
            sys.argv = ('smfc.py ' + command_line).split()
            with self.assertRaises(SystemExit) as cm:
                smfc.main()
        self.assertEqual(cm.exception.code, exit_code, error)

    def pt_main_n2(self, ipmi_command: str, mode_delay: int, level_delay: int, exit_code: int, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), argparse.ArgumentParser._print_message() functions
            - execute smfc.main()
            - ASSERT: if not sys.exit will not happen with the specified exit code
        """
        my_td = TestData()
        my_config = configparser.ConfigParser()
        if ipmi_command == 'NON_EXIST':
            ipmi_command = './non-existent-dir/non-existent-file'
        if ipmi_command == 'BAD':
            ipmi_command = my_td.create_command_file()
        if ipmi_command == 'GOOD':
            ipmi_command = my_td.create_ipmi_command()
        my_config['Ipmi'] = {
            'command': ipmi_command,
            'fan_mode_delay': str(mode_delay),
            'fan_level_delay': str(level_delay),
        }
        my_config['CPU zone'] = {
            'enabled': '0'
        }
        my_config['HD zone'] = {
            'enabled': '0'
        }
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mock_parser_print_help = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('argparse.ArgumentParser._print_message', mock_parser_print_help):
            sys.argv = ('smfc.py -o 0 -c ' + conf_file).split()
            with self.assertRaises(SystemExit) as cm:
                smfc.main()
        self.assertEqual(cm.exception.code, exit_code, error)
        del my_td

    def mocked_sleep(self, *args):
        """Mocked time.sleep() function. Exists at the 10th call."""
        self.sleep_counter += 1
        if self.sleep_counter >= 10:
            sys.exit(10)

    def pt_main_p1(self, cpuzone: int, hdzone: int, exit_code: int, error: str):
        """Primitive positive test function. It contains the following steps:
            - mock print(), argparse.ArgumentParser._print_message() functions
            - execute smfc.main()
            - The main loop will be executed 3 times then exit
        """
        my_td = TestData()
        cmd_ipmi = my_td.create_ipmi_command()
        cmd_smart = my_td.create_command_file('echo "ACTIVE"')
        cpu_hwmon_path = my_td.get_cpu_1()
        hd_hwmon_path = my_td.get_hd_8()
        hd_names = my_td.get_hd_names(8)
        my_config = configparser.ConfigParser()
        my_config['Ipmi'] = {
            'command': cmd_ipmi,
            'fan_mode_delay': '0',
            'fan_level_delay': '0'
        }
        my_config['CPU zone'] = {
            'enabled': str(cpuzone),
            'count': '1',
            'temp_calc': '1',
            'steps': '5',
            'sensitivity': '5',
            'polling': '0',
            'min_temp': '30',
            'max_temp': '60',
            'min_level': '35',
            'max_level': '100',
            'hwmon_path': cpu_hwmon_path
        }
        my_config['HD zone'] = {
            'enabled': str(hdzone),
            'count': '8',
            'temp_calc': '1',
            'steps': '4',
            'sensitivity': '2',
            'polling': '0',
            'min_temp': '30',
            'max_temp': '45',
            'min_level': '35',
            'max_level': '100',
            'hd_names': hd_names,
            'hwmon_path': hd_hwmon_path,
            'standby_guard_enabled': '1',
            'standby_hd_limit': '2',
            'smartctl_path': cmd_smart
        }
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mock_parser_print_help = MagicMock()
        mock_time_sleep = MagicMock()
        mock_time_sleep.side_effect = self.mocked_sleep
        self.sleep_counter = 0
        with patch('builtins.print', mock_print), \
             patch('argparse.ArgumentParser._print_message', mock_parser_print_help), \
             patch('time.sleep', mock_time_sleep):
            sys.argv = ('smfc.py -o 0 -c ' + conf_file).split()
            with self.assertRaises(SystemExit) as cm:
                smfc.main()
        self.assertEqual(cm.exception.code, exit_code, error)
        del my_td

    def test_main(self) -> None:
        """This is a unit test for function main()"""

        # Test standard exits (0, 2).
        self.pt_main_n1('-h', 0, 'smfc main 1')
        self.pt_main_n1('-v', 0, 'smfc main 2')
        # Test exits for invalid command line parameters.
        self.pt_main_n1('-l 4', 2, 'smfc main 3')
        self.pt_main_n1('-o 3', 2, 'smfc main 4')
        self.pt_main_n1('-o 1 -l 5', 2, 'smfc main 5')
        self.pt_main_n1('-o 5 -l 1', 2, 'smfc main 6')

        # Test exits (5) at Log() init skipped (cannot be reproduced because of the parsing of
        # the command-line arguments parsing).

        # Test exits(6) at configuration file loading.
        self.pt_main_n1('-o 0 -l 3 -c &.txt', 6, 'smfc main 7')
        self.pt_main_n1('-o 0 -l 3 -c ./nonexistent_folder/nonexistent_config_file.conf', 6, 'smfc main 8')

        # Test exits(7) at Ipmi() init.
        self.pt_main_n2('NON-EXIST', 0, 0, 7, 'smfc main 9')
        self.pt_main_n2('GOOD', -1, 0, 7, 'smfc main 10')
        self.pt_main_n2('GOOD', 0, -1, 7, 'smfc main 11')
        self.pt_main_n2('BAD', 0, 0, 7, 'smfc main 12')

        # Test exits(8) at controller init.
        self.pt_main_n2('GOOD', 0, 0, 8, 'smfc main 13')

        # Test for main loop. Exits(10) at the 10th call of the mocked time.sleep().
        self.pt_main_p1(1, 0, 10, 'smfc main 14')
        self.pt_main_p1(0, 1, 10, 'smfc main 15')
        self.pt_main_p1(1, 1, 10, 'smfc main 16')


if __name__ == "__main__":
    unittest.main()
