#!/usr/bin/python3
#
#   test_02_ipmi.py (C) 2021, Peter Sulyok
#   Unittests for smfc/main() function.
#
import sys
import os
import configparser
import unittest
import smfc
from unittest.mock import patch, MagicMock


class MainTestCase(unittest.TestCase):
    """Unittests for main() function in smfc.py"""

    ipmi_command: str = '/tmp/test_06_main_ipmi_command.sh'
    config_file: str = '/tmp/test_06_main.conf'

    def primitive_test_1_neg(self, command_line: str, exit_code: int, error: str):
        """This is a primitive negative test function. It contains the following steps:
            - mock print, argparse.ArgumentParser._print_message functions
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

    def primitive_test_2_neg(self, ipmi_command: str, mode_delay: int, level_delay: int, exit_code: int, error: str):
        """This is a primitive negative test function. It contains the following steps:
            - mock print, argparse.ArgumentParser._print_message functions
            - execute smfc.main()
            - ASSERT: if not sys.exit will not happen with the specified exit code
        """
        my_config = configparser.ConfigParser()
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
        with open(self.config_file, 'w+') as cf:
            my_config.write(cf)
        mock_print = MagicMock()
        mock_parser_print_help = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('argparse.ArgumentParser._print_message', mock_parser_print_help):
            sys.argv = ('smfc.py -o 0 -c ' + self.config_file).split()
            with self.assertRaises(SystemExit) as cm:
                smfc.main()
            self.assertEqual(cm.exception.code, exit_code, error)
        os.remove(self.config_file)

    sleep_counter: int

    def mocked_sleep(self, t):
        """Mocked time.sleep() function. Exists at the 10th call."""
        self.sleep_counter += 1
        if self.sleep_counter >= 10:
            sys.exit(10)

    def primitive_test_3_pos(self, cpuzone: int, hdzone: int, exit_code: int, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, argparse.ArgumentParser._print_message functions
            - execute smfc.main()
            - The main loop will be executed 3 times then exit
        """
        my_config = configparser.ConfigParser()
        my_config['Ipmi'] = {
            'command': './test/hd_8/test1.sh',
            'fan_mode_delay': '0',
            'fan_level_delay': '0'
        }
        my_config['CPU zone'] = {
            'enabled': str(cpuzone),
            'steps': '5',
            'sensitivity': '5',
            'polling': '0',
            'min_temp': '30',
            'max_temp': '55',
            'min_level': '35',
            'max_level': '100',
            'hwmon_path': './test/hd_8/hwmon/cpu/*/temp1_input'
        }
        my_config['HD zone'] = {
            'enabled': str(hdzone),
            'steps': '4',
            'sensitivity': '2',
            'polling': '0',
            'min_temp': '32',
            'max_temp': '48',
            'min_level': '35',
            'max_level': '100',
            'hd_numbers': '8',
            'hd_names': '/dev/sda /dev/sdb /dev/sdc /dev/sdd /dev/sde /dev/sdf /dev/sdg /dev/sdh',
            'hwmon_path': ('./test/hd_8/hwmon/hd/0/*/temp1_input\n'
                           './test/hd_8/hwmon/hd/1/*/temp1_input\n'
                           './test/hd_8/hwmon/hd/2/*/temp1_input\n'
                           './test/hd_8/hwmon/hd/3/*/temp1_input\n'
                           './test/hd_8/hwmon/hd/4/?/temp1_input\n'
                           './test/hd_8/hwmon/hd/5/*/temp1_input\n'
                           './test/hd_8/hwmon/hd/6/*/temp1_input\n'
                           './test/hd_8/hwmon/hd/7/*/temp1_input'),
            'standby_guard_enabled': '1',
            'standby_hd_limit': '2',
            'smartctl_path': './test/hd_8/test2.sh'
        }
        with open(self.config_file, 'w+') as cf:
            my_config.write(cf)
        mock_print = MagicMock()
        mock_parser_print_help = MagicMock()
        mock_time_sleep = MagicMock()
        mock_time_sleep.side_effect = self.mocked_sleep
        self.sleep_counter = 0
        with patch('builtins.print', mock_print), \
             patch('argparse.ArgumentParser._print_message', mock_parser_print_help), \
             patch('time.sleep', mock_time_sleep):
            sys.argv = ('smfc.py -o 0 -c ' + self.config_file).split()
            with self.assertRaises(SystemExit) as cm:
                smfc.main()
            self.assertEqual(cm.exception.code, exit_code, error)
        os.remove(self.config_file)

    def test_main(self) -> None:
        """This is a unittest for function main()"""

        # Test standard exits (0, 2).
        self.primitive_test_1_neg('-h', 0, 'smfc main 1')
        self.primitive_test_1_neg('-v', 0, 'smfc main 2')
        # Test exits for invalid command line parameters.
        self.primitive_test_1_neg('-l 4', 2, 'smfc main 3')
        self.primitive_test_1_neg('-o 3', 2, 'smfc main 4')
        self.primitive_test_1_neg('-o 1 -l 5', 2, 'smfc main 5')
        self.primitive_test_1_neg('-o 5 -l 1', 2, 'smfc main 6')

        # Test exits (5) at Log() init skipped (cannot be reproduced because of the parsing of
        # the command-line arguments parsing).

        # Test exits(6) at configuration file loading.
        self.primitive_test_1_neg('-o 0 -l 3 -c &.txt', 6, 'smfc main 7')
        self.primitive_test_1_neg('-o 0 -l 3 -c ./nonexistent_folder/nonexistent_config_file.conf', 6, 'smfc main 8')

        # Test exits(7) at Ipmi() init.
        self.primitive_test_2_neg('./bin/nonexistent_command.sh', 0, 0, 7, 'smfc main 9')
        self.primitive_test_2_neg('./test/hd_2/test1.sh', -1, 0, 7, 'smfc main 10')
        self.primitive_test_2_neg('./test/hd_2/test1.sh', 0, -1, 7, 'smfc main 11')
        self.primitive_test_2_neg('./test/hd_2/test2.sh', 0, 0, 7, 'smfc main 12')

        # Test exits(8) in Ipmi() init.
        self.primitive_test_2_neg('./test/hd_2/test1.sh', 0, 0, 8, 'smfc main 13')

        # Test for main loop. Exits(10) at the 10th call of the mocked time.sleep().
        self.primitive_test_3_pos(1, 0, 10, 'smfc main 14')
        self.primitive_test_3_pos(0, 1, 10, 'smfc main 15')
        self.primitive_test_3_pos(1, 1, 10, 'smfc main 16')


if __name__ == "__main__":
    unittest.main()
