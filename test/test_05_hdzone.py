#!/usr/bin/python3
#
#   test_05_hdzone.py (C) 2021, Peter Sulyok
#   Unittests for smfc/HdZone() class.
#
import configparser
import glob
import os
import subprocess
import unittest
from smfc import Log, Ipmi, HdZone
from unittest.mock import patch, MagicMock
from typing import List, Any


class HdZoneTestCase(unittest.TestCase):
    """Unittests for HdZone() class in smfc.py"""

    @staticmethod
    def normalize_path(path: str) -> str:
        file_names = glob.glob(path)
        return file_names[0]        

    # Path for the shell script substituting command ipmitool
    ipmi_command: str = '/tmp/test_05_ipmi_hz.sh'

    # Path for the shell script substituting command ipmitool
    smartctl_command: str = '/tmp/test_05_smartctl_hz.sh'

    # Path for hwmon_path files
    temp8_files: str = (
        './test/hd_8/hwmon/hd/0/*/temp1_input\n'
        './test/hd_8/hwmon/hd/1/*/temp1_input\n'
        './test/hd_8/hwmon/hd/2/*/temp1_input\n'
        './test/hd_8/hwmon/hd/3/*/temp1_input\n'
        './test/hd_8/hwmon/hd/4/?/temp1_input\n'
        './test/hd_8/hwmon/hd/5/*/temp1_input\n'
        './test/hd_8/hwmon/hd/6/*/temp1_input\n'
        './test/hd_8/hwmon/hd/7/*/temp1_input'
        )
    default8_files: str = (
        '/sys/class/scsi_device/0:0:0:0/device/hwmon/hwmon*/temp1_input\n'
        '/sys/class/scsi_device/1:0:0:0/device/hwmon/hwmon*/temp1_input\n'
        '/sys/class/scsi_device/2:0:0:0/device/hwmon/hwmon*/temp1_input\n'
        '/sys/class/scsi_device/3:0:0:0/device/hwmon/hwmon*/temp1_input\n'
        '/sys/class/scsi_device/4:0:0:0/device/hwmon/hwmon*/temp1_input\n'
        '/sys/class/scsi_device/5:0:0:0/device/hwmon/hwmon*/temp1_input\n'
        '/sys/class/scsi_device/6:0:0:0/device/hwmon/hwmon*/temp1_input\n'
        '/sys/class/scsi_device/7:0:0:0/device/hwmon/hwmon*/temp1_input'
        )
    temp8_wr_files: str = (
        '/tmp/cz_test_05_hd0_temp\n'
        '/tmp/cz_test_05_hd1_temp\n'
        '/tmp/cz_test_05_hd2_temp\n'
        '/tmp/cz_test_05_hd3_temp\n'
        '/tmp/cz_test_05_hd4_temp\n'
        '/tmp/cz_test_05_hd5_temp\n'
        '/tmp/cz_test_05_hd6_temp\n'
        '/tmp/cz_test_05_hd7_temp'
        )
    temp4_files: str = (
        './test/hd_4/hwmon/hd/0/*/temp1_input\n'
        './test/hd_4/hwmon/hd/1/*/temp1_input\n'
        './test/hd_4/hwmon/hd/2/?/temp1_input\n'
        './test/hd_4/hwmon/hd/3/*/temp1_input'
        )
    temp2_files: str = (
        './test/hd_2/hwmon/hd/0/*/temp1_input\n'
        './test/hd_2/hwmon/hd/1/?/temp1_input'
        )
    err2_files: str = (
        './test/hd_2/hwmon/hd/0/|/temp1_input\n'
        './test/hd_2/hwmon/hd/1/&/temp1_input'
        )

    # HD names
    names8: str = '/dev/sda /dev/sdb /dev/sdc /dev/sdd /dev/sde /dev/sdf /dev/sdg /dev/sdh'
    names4: str = '/dev/sda /dev/sdb /dev/sdc /dev/sdd'
    names2: str = '/dev/sda /dev/sdb'

    def primitive_test_1_pos(self, steps: int, sensitivity: float, polling: float, min_temp: float, max_temp: float,
                             min_level: int, max_level: int, hd_number: int, hd_names: str, hwmon_path: str,
                             sb_limit: int, error: str):
        """This is a primitive negative test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - delete the instances
        """
        with open(self.ipmi_command, "w+") as f:
            f.write('#!/bin/bash\necho " 01"\n')
        os.system('chmod +x '+self.ipmi_command)
        with open(self.smartctl_command, "w+") as f:
            f.write('#!/bin/bash\necho "ACTIVE"\n')
        os.system('chmod +x '+self.smartctl_command)
        mock_print = MagicMock()
        with patch('builtins.print', mock_print):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'steps': str(steps),
                'sensitivity': str(sensitivity),
                'polling': str(polling),
                'min_temp': str(min_temp),
                'max_temp': str(max_temp),
                'min_level': str(min_level),
                'max_level': str(max_level),
                'hd_numbers': str(hd_number),
                'hd_names': hd_names,
                'hwmon_path': hwmon_path,
                'standby_guard_enabled': '1',
                'standby_hd_limit': str(sb_limit),
                'smartctl_path': self.smartctl_command
            }
            my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_hdzone.steps, steps, error)
            self.assertEqual(my_hdzone.sensitivity, sensitivity, error)
            self.assertEqual(my_hdzone.polling, polling, error)
            self.assertEqual(my_hdzone.min_temp, min_temp, error)
            self.assertEqual(my_hdzone.max_temp, max_temp, error)
            self.assertEqual(my_hdzone.min_level, min_level, error)
            self.assertEqual(my_hdzone.max_level, max_level, error)
            self.assertEqual(my_hdzone.hd_numbers, hd_number, error)
            self.assertEqual(my_hdzone.hd_names, hd_names.split(), error)
            normalized_hwmon = hwmon_path.splitlines()
            for i in range(len(normalized_hwmon)):
                normalized_hwmon[i] = self.normalize_path(normalized_hwmon[i])
            self.assertEqual(my_hdzone.hwmon_path, normalized_hwmon, error)
            self.assertEqual(my_hdzone.standby_hd_limit, sb_limit, error)
            self.assertEqual(my_hdzone.smartctl_path, self.smartctl_command, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config
        os.remove(self.ipmi_command)
        os.remove(self.smartctl_command)

    def primitive_test_2_pos(self, steps: int, sensitivity: float, polling: float, min_temp: float, max_temp: float,
                             min_level: int, max_level: int, hd_number: int, hd_names: str, sb_limit: int,
                             smartctl_command: str, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if default values will not be saved properly in __init__
            - delete the instances
        """
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hwmon_path': self.temp8_files,
                'standby_guard_enabled': '1'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_hdzone.steps, steps, error)
            self.assertEqual(my_hdzone.sensitivity, sensitivity, error)
            self.assertEqual(my_hdzone.polling, polling, error)
            self.assertEqual(my_hdzone.min_temp, min_temp, error)
            self.assertEqual(my_hdzone.max_temp, max_temp, error)
            self.assertEqual(my_hdzone.min_level, min_level, error)
            self.assertEqual(my_hdzone.max_level, max_level, error)
            self.assertEqual(my_hdzone.hd_numbers, hd_number, error)
            self.assertEqual(my_hdzone.hd_names, hd_names.split(), error)
            normalized_hwmon = self.temp8_files.splitlines()
            for i in range(len(normalized_hwmon)):
                normalized_hwmon[i] = self.normalize_path(normalized_hwmon[i])
            self.assertEqual(my_hdzone.hwmon_path, normalized_hwmon, error)
            self.assertEqual(my_hdzone.standby_hd_limit, sb_limit, error)
            self.assertEqual(my_hdzone.smartctl_path, smartctl_command, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config

    def primitive_test_3_neg(self, hd_number: int, hd_names: str, hwmon_path: str, sb_hd_limit: int,
                             exception: Any, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - ASSERT: if the exceptions are raised in case of invalid parameters in __init__
            - delete the instances
        """
        with open(self.ipmi_command, "w+") as f:
            f.write('#!/bin/bash\necho " 01"\n')
        os.system('chmod +x '+self.ipmi_command)
        with open(self.smartctl_command, "w+") as f:
            f.write('#!/bin/bash\necho "ACTIVE"\n')
        os.system('chmod +x '+self.smartctl_command)
        mock_print = MagicMock()
        with patch('builtins.print', mock_print):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hd_numbers': str(hd_number),
                'hd_names': hd_names,
                'hwmon_path': hwmon_path,
                'standby_guard_enabled': '1',
                'standby_hd_limit': sb_hd_limit
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            with self.assertRaises(Exception) as cm:
                HdZone(my_log, my_ipmi, my_config)
            self.assertEqual(type(cm.exception), exception, error)
        del my_ipmi
        del my_log
        del my_config
        os.remove(self.ipmi_command)
        os.remove(self.smartctl_command)

    def test_init(self) -> None:
        """This is a unittest for function HdZone.__init__()"""
        # Test valid parameters.
        self.primitive_test_1_pos(4, 2, 2, 32, 48, 35, 100, 8, self.names8, self.temp8_files, 2, 'hz init 1')
        self.primitive_test_1_pos(4, 2, 2, 32, 48, 35, 100, 4, self.names4, self.temp4_files, 2, 'hz init 2')
        self.primitive_test_1_pos(4, 2, 2, 32, 48, 35, 100, 2, self.names2, self.temp2_files, 2, 'hz init 3')
        
        # Test loading default values (if they are not specified in INI files).
        self.primitive_test_2_pos(4, 2, 2400, 32, 48, 35, 100, 8, self.names8, 1, '/usr/sbin/smartctl', 'hz init 4')

        # Test error cases.
        # Negative hd number
        self.primitive_test_3_neg(-10, self.names8, self.temp8_files, 1, ValueError, 'hz init 5')
        # Inconsistent hd_numbers and size of hd_names
        self.primitive_test_3_neg(5, self.names8, self.temp8_files, 1, ValueError, 'hz init 5')
        # Inconsistent hd_numbers and size of hwmon_path 
        self.primitive_test_3_neg(8, self.names8, self.temp4_files, 1, ValueError, 'hz init 7')
        # Invalid hwmon
        self.primitive_test_3_neg(2, self.names2, self.err2_files, 1, ValueError, 'hz init 8')
        # Negative standby_hd_limit
        self.primitive_test_3_neg(2, self.names2, self.temp2_files, -1, ValueError, 'hz init 9')

    def primitive_test_4_pos(self, level: int):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.set_fan_level()
            - ASSERT: if the Ipmi.set_fan_level was called with different parameters
            - delete the instances
        """
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hd_number': '8',
                'hwmon_path': self.temp8_files,
                'standby_guard_enabled': '1'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_ipmi.set_fan_level = MagicMock(name='set_fan_level')
            my_ipmi.set_fan_level.return_value = Ipmi.SUCCESS
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            my_hdzone.set_fan_level(level)
            my_ipmi.set_fan_level.assert_any_call(Ipmi.HD_ZONE, level)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config

    def test_set_fan_level(self) -> None:
        """This is a unittest for function HdZone.set_fan_level()"""
        # Test valid parameters.
        self.primitive_test_4_pos(45)   # 'hz set_fan_level 1'

    def primitive_test_5_pos(self, states: List[bool], result: str, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.get_standby_state_str()
            - ASSERT: if the result is different than the internal state
            - delete the instances
        """
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hwmon_path': self.temp8_files,
                'standby_guard_enabled': '1'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            my_hdzone.standby_array_states = states
            self.assertEqual(my_hdzone.get_standby_state_str(), result, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config

    def test_get_standby_state_str(self) -> None:
        """This is a unittest for function HdZone.set_fan_level()"""
        # Test valid parameters.
        self.primitive_test_5_pos([True, True, True, True, True, True, True, True],         'SSSSSSSS',
                                  'hz get_standby_state_str 1')
        self.primitive_test_5_pos([False, False, False, False, False, False, False, False], 'AAAAAAAA',
                                  'hz get_standby_state_str 2')
        self.primitive_test_5_pos([True, False, False, False, False, False, False, False],  'SAAAAAAA',
                                  'hz get_standby_state_str 3')
        self.primitive_test_5_pos([False, True, False, False, False, False, False, False],  'ASAAAAAA',
                                  'hz get_standby_state_str 4')
        self.primitive_test_5_pos([False, False, True, False, False, False, False, False],  'AASAAAAA',
                                  'hz get_standby_state_str 5')
        self.primitive_test_5_pos([False, False, False, True, False, False, False, False],  'AAASAAAA',
                                  'hz get_standby_state_str 6')
        self.primitive_test_5_pos([False, False, False, False, True, False, False, False],  'AAAASAAA',
                                  'hz get_standby_state_str 7')
        self.primitive_test_5_pos([False, False, False, False, False, True, False, False],  'AAAAASAA',
                                  'hz get_standby_state_str 8')
        self.primitive_test_5_pos([False, False, False, False, False, False, True, False],  'AAAAAASA',
                                  'hz get_standby_state_str 9')
        self.primitive_test_5_pos([False, False, False, False, False, False, False, True],  'AAAAAAAS',
                                  'hz get_standby_state_str 10')

    def primitive_test_6_pos(self, states: List[bool], in_standby: int, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.check_standby_state()
            - ASSERT: if result is different that input parameters
            - delete the instances
        """
        results: List[subprocess.CompletedProcess]
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hwmon_path': self.temp8_files,
                'standby_guard_enabled': '1'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            results = [None, None, None, None, None, None, None, None]
            for i in range(my_hdzone.hd_numbers):
                if states[i]:
                    results[i] = subprocess.CompletedProcess([], 0, 'STANDBY')
                else:
                    results[i] = subprocess.CompletedProcess([], 0, 'ACTIVE')
            mock_subprocess_run.side_effect = results
            my_hdzone.standby_array_states = states
            self.assertEqual(my_hdzone.check_standby_state(), in_standby, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config

    def test_check_standby_state(self) -> None:
        """This is a unittest for function Hd.set_fan_level()"""
        # Test valid parameters.
        self.primitive_test_6_pos([True, True, True, True, True, True, True, True], 8,
                                  'hz check_standby_state 1')
        self.primitive_test_6_pos([False, True, True, True, True, True, True, True], 7,
                                  'hz check_standby_state 2')
        self.primitive_test_6_pos([True, False, True, True, True, True, True, True], 7,
                                  'hz check_standby_state 3')
        self.primitive_test_6_pos([True, True, False, True, True, True, True, True], 7,
                                  'hz check_standby_state 4')
        self.primitive_test_6_pos([True, True, True, False, True, True, True, True], 7,
                                  'hz check_standby_state 5')
        self.primitive_test_6_pos([True, True, True, True, False, True, True, True], 7,
                                  'hz check_standby_state 6')
        self.primitive_test_6_pos([True, True, True, True, True, False, True, True], 7,
                                  'hz check_standby_state 7')
        self.primitive_test_6_pos([True, True, True, True, True, True, False, True], 7,
                                  'hz check_standby_state 8')
        self.primitive_test_6_pos([True, True, True, True, True, True, True, False], 7,
                                  'hz check_standby_state 9')

        self.primitive_test_6_pos([True, False, True, True, True, True, True, False], 6,
                                  'hz check_standby_state 10')
        self.primitive_test_6_pos([True, False, True, True, False, True, True, False], 5,
                                  'hz check_standby_state 11')
        self.primitive_test_6_pos([False, False, True, True, False, True, True, False], 4,
                                  'hz check_standby_state 12')
        self.primitive_test_6_pos([False, False, True, False, False, True, True, False], 3,
                                  'hz check_standby_state 13')
        self.primitive_test_6_pos([False, False, True, False, False, True, False, False], 2,
                                  'hz check_standby_state 14')
        self.primitive_test_6_pos([False, False, False, False, False, True, False, False], 1,
                                  'hz check_standby_state 15')
        self.primitive_test_6_pos([False, False, False, False, False, False, False, False], 0,
                                  'hz check_standby_state 16')

    def primitive_test_7_pos(self, temperatures: List[float], avg_temp: float, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - deletes hwmon files
            - calls HdZone.get_temp()
            - ASSERT: if the return temperature is different than the value in the file
            - delete the instances
        """
        r = self.temp8_wr_files.splitlines()
        for i in range(len(r)):
            with open(r[i], "w+") as f:
                f.write(str(temperatures[i] * 1000))
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hd_number': 8,
                'hwmon_path': self.temp8_wr_files,
                'standby_guard_enabled': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            self.assertEqual(my_hdzone.get_temp(), avg_temp, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config
        for i in range(len(r)):
            os.remove(r[i])

    def primitive_test_8_neg(self, exception: Any, error: str):
        """This is a primitive negative test function. It contains the following steps:
            - mock print, subprocesses.run functions
            - initialize a Config, Log, Ipmi, and CpuZone classes
            - calls CpuZone.get_temp()
            - ASSERT: if no exception raised in case of file IO errors
            - delete the instances
        """
        r = self.temp8_wr_files.splitlines()
        for i in range(len(r)):
            with open(r[i], "w+") as f:
                f.write(str('38500'))
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hd_number': 8,
                'hwmon_path': self.temp8_wr_files,
                'standby_guard_enabled': '0'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            for i in range(len(r)):
                os.remove(r[i])
            with self.assertRaises(Exception) as cm:
                my_hdzone.get_temp()
            self.assertTrue(type(cm.exception) in exception, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config

    def test_get_temp(self) -> None:
        """This is a unittest for function HdZone.get_temp()"""
        # Test valid parameters.
        self.primitive_test_7_pos([38.5, 38.5, 38.5, 38.5, 38.5, 38.5, 38.5, 38.5], 38.5, 'hz get_temp 1')
        self.primitive_test_7_pos([31.1, 32.1, 33.1, 34.1, 35.1, 36.1, 37.1, 38.1], 34.6, 'hz get_temp 2')

        # Test exceptions.
        self.primitive_test_8_neg((IOError, FileNotFoundError), 'hz get_temp 3')

    def primitive_test_9_pos(self, states: List[bool], count: int, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.go_standby_state()
            - ASSERT: if the subprocess.run called with wrong parameters and array state is not in fully standby
            - delete the instances
        """
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hd_number': '8',
                'hwmon_path': self.temp8_files,
                'standby_guard_enabled': '1',
                'smartctl_path': self.smartctl_command
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            my_hdzone.standby_array_states = states
            mock_subprocess_run.reset_mock()
            my_hdzone.go_standby_state()
            self.assertEqual(mock_subprocess_run.call_count, count, error)
            self.assertEqual([True, True, True, True, True, True, True, True], my_hdzone.standby_array_states, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config

    def test_go_standby_state(self) -> None:
        """This is a unittest for function HdZone.go_standby_state()"""

        # Test valid parameters.
        self.primitive_test_9_pos([False, False, False, False, False, False, False, False], 8, 'hz go_standby_state 2')
        self.primitive_test_9_pos([True, False, False, False, False, False, False, False],  7, 'hz go_standby_state 3')
        self.primitive_test_9_pos([True, True, False, False, False, False, False, False],   6, 'hz go_standby_state 4')
        self.primitive_test_9_pos([True, True, True, False, False, False, False, False],    5, 'hz go_standby_state 5')
        self.primitive_test_9_pos([True, True, True, True, False, False, False, False],     4, 'hz go_standby_state 6')
        self.primitive_test_9_pos([True, True, True, True, True, False, False, False],      3, 'hz go_standby_state 7')
        self.primitive_test_9_pos([True, True, True, True, True, True, False, False],       2, 'hz go_standby_state 8')
        self.primitive_test_9_pos([True, True, True, True, True, True, True, False],        1, 'hz go_standby_state 9')
        self.primitive_test_9_pos([True, True, True, True, True, True, True, True],         0, 'hz go_standby_state 1')

    def primitive_test_10_pos(self, old_state: bool, states: List[bool], new_state: bool, error: str):
        """This is a primitive positive test function. It contains the following steps:
            - mock print, subprocesses.run, Ipmi.set_fan_level functions
            - initialize a Config, Log, Ipmi, and HdZone classes
            - calls HdZone.run_standby_guard()
            - ASSERT: if the expected standby_flag is different
            - delete the instances
        """
        mock_print = MagicMock()
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        with patch('builtins.print', mock_print), \
             patch('subprocess.run', mock_subprocess_run):
            my_config = configparser.ConfigParser()
            my_config['Ipmi'] = {
                'command': self.ipmi_command,
                'fan_mode_delay': '0',
                'fan_level_delay': '0'
            }
            my_config['HD zone'] = {
                'enabled': '1',
                'hd_number': '8',
                'hwmon_path': self.temp8_files,
                'standby_guard_enabled': '1'
            }
            my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
            my_ipmi = Ipmi(my_log, my_config)
            my_hdzone = HdZone(my_log, my_ipmi, my_config)
            my_hdzone.go_standby_state = MagicMock(name='go_standby_state')
            my_hdzone.check_standby_state = MagicMock(name='check_standby_state')
            my_hdzone.check_standby_state.return_value = states.count(True)
            my_hdzone.standby_array_states = states
            my_hdzone.standby_flag = old_state
            my_hdzone.run_standby_guard()
            self.assertEqual(my_hdzone.standby_flag, new_state, error)
        del my_hdzone
        del my_ipmi
        del my_log
        del my_config

    def test_run_standby_guard(self) -> None:
        """This is a unittest for function HdZone.run_standby_guard()"""
        # No state changes.
        self.primitive_test_10_pos(False, [False, False, False, False, False, False, False, False], False,
                                   'hz run_standby_guard 1')
        self.primitive_test_10_pos(True, [True, True, True, True, True, True, True, True], True,
                                   'hz run_standby_guard 2')

        # Step 2: from ACTIVE to STANDBY.
        self.primitive_test_10_pos(False, [False, True, False, False, False, False, False, False], True,
                                   'hz run_standby_guard 3')
        self.primitive_test_10_pos(False, [False, True, False, True, False, False, False, False], True,
                                   'hz run_standby_guard 4')
        self.primitive_test_10_pos(False, [True, True, True, True, True, True, True, True], True,
                                   'hz run_standby_guard 5')

        # Step 3: from STANDBY to ACTIVE.
        self.primitive_test_10_pos(True, [False, False, False, False, False, False, False, False], False,
                                   'hz run_standby_guard 6')
        self.primitive_test_10_pos(True, [True, False, False, True, True, True, True, True], False,
                                   'hz run_standby_guard 7')


if __name__ == "__main__":
    unittest.main()
