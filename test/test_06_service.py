#!/usr/bin/python3
#
#   test_06_service.py (C) 2021-2023, Peter Sulyok
#   Unit tests for smfc.Service() class.
#
import configparser
from argparse import Namespace
import sys
import unittest
from unittest.mock import patch, MagicMock
from test_00_data import TestData
from smfc import Log, Ipmi, CpuZone, HdZone, Service


class ServiceTestCase(unittest.TestCase):
    """Unit test for smfc.Service() class"""

    sleep_counter: int

    def pt_ef_p1(self, ipmi: bool, log: bool) -> None:
        """Primitive positive test function. It contains the following steps:
            - mock print(), atexit.unregister(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
            - execute Service.exit_func()
            - ASSERT: if mocked functions not called
        """
        mock_print = MagicMock()
        mock_atexit_unregister = MagicMock()
        mock_ipmi_set_fan_level = MagicMock()
        mock_log_msg = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('atexit.unregister', mock_atexit_unregister), \
             patch('smfc.Ipmi.set_fan_level', mock_ipmi_set_fan_level), \
             patch('smfc.Log.msg_to_stdout', mock_log_msg):

            service = Service()
            if log:
                service.log = Log(1, 0)
            if ipmi:
                my_td = TestData()
                ipmi_command = my_td.create_ipmi_command()
                my_config = configparser.ConfigParser()
                my_config[Ipmi.CS_IPMI] = {
                    Ipmi.CV_IPMI_COMMAND: ipmi_command,
                    Ipmi.CV_IPMI_FAN_MODE_DELAY: '1',
                    Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '1',
                }
                service.ipmi = Ipmi(service.log, my_config)
            service.exit_func()
            mock_atexit_unregister.assert_called_once()
            if ipmi:
                mock_ipmi_set_fan_level.assert_called()
                if log:
                    mock_log_msg.assert_called_once()

    def test_exit_function(self) -> None:
        """This is a unit test for function Service.exit_function()"""
        self.pt_ef_p1(True, True)
        self.pt_ef_p1(False, False)

    def pt_run_n1(self, command_line: str, exit_code: int, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), argparse.ArgumentParser._print_message() functions
            - execute Service.run()
            - ASSERT: if sys.exit() not happened with the specified exit code
        """
        mock_print = MagicMock()
        mock_parser_print_help = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('argparse.ArgumentParser._print_message', mock_parser_print_help):
            sys.argv = ('smfc.py ' + command_line).split()
            service = Service()
            with self.assertRaises(SystemExit) as cm:
                service.run()
        self.assertEqual(cm.exception.code, exit_code, error)

    def pt_run_n2(self, ipmi_command: str, mode_delay: int, level_delay: int, exit_code: int, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), argparse.ArgumentParser._print_message(), smfc.Service.exit_func() functions
            - execute Service.run()
            - ASSERT: if sys.exit() not happened with the specified exit code
        """
        my_td = TestData()
        my_config = configparser.ConfigParser()
        if ipmi_command == 'NON_EXIST':
            ipmi_command = './non-existent-dir/non-existent-file'
        if ipmi_command == 'BAD':
            ipmi_command = my_td.create_command_file()
        if ipmi_command == 'GOOD':
            ipmi_command = my_td.create_ipmi_command()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: ipmi_command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(mode_delay),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(level_delay),
        }
        my_config[CpuZone.CS_CPU_ZONE] = {
            CpuZone.CV_CPU_ZONE_ENABLED: '0'
        }
        my_config[HdZone.CS_HD_ZONE] = {
            HdZone.CV_HD_ZONE_ENABLED: '0'
        }
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mock_parser_print_help = MagicMock()
        mock_exit_func = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('argparse.ArgumentParser._print_message', mock_parser_print_help), \
             patch('smfc.Service.exit_func', mock_exit_func):
            sys.argv = ('smfc.py -o 0 -c ' + conf_file).split()
            service = Service()
            with self.assertRaises(SystemExit) as cm:
                service.run()
            self.assertEqual(cm.exception.code, exit_code, error)
        del my_td

    def pt_run_n3(self, level: int, output: int, exit_code: int, error: str):
        """Primitive negative test function. It contains the following steps:
            - mock print(), argparse.ArgumentParser._print_message(), argparse.ArgumentParser.parse_args(),
              smfc.Service.exit_func() functions
            - execute Service.run()
            - ASSERT: if sys.exit() not happened with the specified exit code
        """

        def mocked_parser() -> Namespace:
            return Namespace(config_file="smfc.conf", l=level, o=output)

        mock_print = MagicMock()
        mock_parser_print_help = MagicMock()
        mock_parser_parse_args = MagicMock()
        mock_parser_parse_args.side_effect = mocked_parser
        mock_exit_func = MagicMock()

        with patch('builtins.print', mock_print), \
             patch('argparse.ArgumentParser._print_message', mock_parser_print_help), \
             patch('argparse.ArgumentParser.parse_args', mock_parser_parse_args), \
             patch('smfc.Service.exit_func', mock_exit_func):
            service = Service()
            with self.assertRaises(SystemExit) as cm:
                service.run()
            self.assertEqual(cm.exception.code, exit_code, error)

    # pragma pylint: disable=unused-argument
    def mocked_sleep(self, *args):
        """Mocked time.sleep() function. Exists at the 10th call."""
        self.sleep_counter += 1
        if self.sleep_counter >= 10:
            sys.exit(10)
    # pragma pylint: enable=unused-argument

    def pt_run_p1(self, cpuzone: int, hdzone: int, exit_code: int, error: str):
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
        hd_names = my_td.create_hd_names(8)
        my_config = configparser.ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: cmd_ipmi,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: '0',
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: '0'
        }
        my_config[CpuZone.CS_CPU_ZONE] = {
            CpuZone.CV_CPU_ZONE_ENABLED: str(cpuzone),
            CpuZone.CV_CPU_ZONE_COUNT: '1',
            CpuZone.CV_CPU_ZONE_TEMP_CALC: '1',
            CpuZone.CV_CPU_ZONE_STEPS: '5',
            CpuZone.CV_CPU_ZONE_SENSITIVITY: '5',
            CpuZone.CV_CPU_ZONE_POLLING: '0',
            CpuZone.CV_CPU_ZONE_MIN_TEMP: '30',
            CpuZone.CV_CPU_ZONE_MAX_TEMP: '60',
            CpuZone.CV_CPU_ZONE_MIN_LEVEL: '35',
            CpuZone.CV_CPU_ZONE_MAX_LEVEL: '100',
            CpuZone.CV_CPU_ZONE_HWMON_PATH: cpu_hwmon_path
        }
        my_config[HdZone.CS_HD_ZONE] = {
            HdZone.CV_HD_ZONE_ENABLED: str(hdzone),
            HdZone.CV_HD_ZONE_COUNT: '8',
            HdZone.CV_HD_ZONE_TEMP_CALC: '1',
            HdZone.CV_HD_ZONE_STEPS: '4',
            HdZone.CV_HD_ZONE_SENSITIVITY: '2',
            HdZone.CV_HD_ZONE_POLLING: '0',
            HdZone.CV_HD_ZONE_MIN_TEMP: '30',
            HdZone.CV_HD_ZONE_MAX_TEMP: '45',
            HdZone.CV_HD_ZONE_MIN_LEVEL: '35',
            HdZone.CV_HD_ZONE_MAX_LEVEL: '100',
            HdZone.CV_HD_ZONE_HD_NAMES: hd_names,
            HdZone.CV_HD_ZONE_HWMON_PATH: hd_hwmon_path,
            HdZone.CV_HD_ZONE_STANDBY_GUARD_ENABLED: '1',
            HdZone.CV_HD_ZONE_STANDBY_HD_LIMIT: '2',
            HdZone.CV_HD_ZONE_SMARTCTL_PATH: cmd_smart
        }
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mock_parser_print_help = MagicMock()
        mock_time_sleep = MagicMock()
        mock_time_sleep.side_effect = self.mocked_sleep
        mock_exit_func = MagicMock()
        self.sleep_counter = 0
        with patch('builtins.print', mock_print), \
             patch('argparse.ArgumentParser._print_message', mock_parser_print_help), \
             patch('time.sleep', mock_time_sleep), \
             patch('smfc.Service.exit_func', mock_exit_func):
            sys.argv = ('smfc.py -o 0 -c ' + conf_file).split()
            service = Service()
            with self.assertRaises(SystemExit) as cm:
                service.run()
            self.assertEqual(cm.exception.code, exit_code, error)
        del my_td

    def test_run(self) -> None:
        """This is a unit test for function Service.run()"""

        # Test standard exits (0, 2).
        self.pt_run_n1('-h', 0, 'service run 1')
        self.pt_run_n1('-v', 0, 'service run 2')
        # Test exits for invalid command line parameters.
        self.pt_run_n1('-l 10', 2, 'service run 3')
        self.pt_run_n1('-o 9', 2, 'service run 4')
        self.pt_run_n1('-o 1 -l 10', 2, 'service run 5')
        self.pt_run_n1('-o 9 -l 1', 2, 'service run 6')

        # Test exits (5) at Log() init.
        self.pt_run_n3(10, 0, 5, 'service run 7')
        self.pt_run_n3(0, 9, 5, 'service run 8')

        # Test exits(6) at configuration file loading.
        self.pt_run_n1('-o 0 -l 3 -c &.txt', 6, 'service run 9')
        self.pt_run_n1('-o 0 -l 3 -c ./nonexistent_folder/nonexistent_config_file.conf', 6, 'service run 10')

        # Test exits(7) at Ipmi() init.
        self.pt_run_n2('NON_EXIST', 0, 0, 7, 'service run 11')
        self.pt_run_n2('GOOD', -1, 0, 7, 'service run 12')
        self.pt_run_n2('GOOD', 0, -1, 7, 'service run 13')
        self.pt_run_n2('BAD', 0, 0, 7, 'service run 14')

        # Test exits(8) at controller init.
        self.pt_run_n2('GOOD', 0, 0, 8, 'service run 15')

        # Test for main loop. Exits(10) at the 10th call of the mocked time.sleep().
        self.pt_run_p1(1, 0, 10, 'service run 16')
        self.pt_run_p1(0, 1, 10, 'service run 17')
        self.pt_run_p1(1, 1, 10, 'service run 18')


if __name__ == "__main__":
    unittest.main()
