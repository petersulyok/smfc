#!/usr/bin/env python3
#
#   test_02_ipmi.py (C) 2021-2025, Peter Sulyok
#   Unit tests for smfc.Ipmi() class.
#
import subprocess
from typing import Any, List
from configparser import ConfigParser
import pytest
from mock import MagicMock, call
from pytest_mock import MockerFixture
from smfc import Log, Ipmi
from .test_00_data import TestData

class TestIpmi:
    """Unit test class for smfc.Ipmi() class"""

    @pytest.mark.parametrize("mode_delay, level_delay, remote_pars, sudo, error", [
        (10, 2, '',                                          False, 'Ipmi.__init__() 1'),
        (2, 10, '-I lanplus -U ADMIN -P ADMIN -H 127.0.0.1', True,  'Ipmi.__init__() 2')
    ])
    def test_init_p1(self, mocker: MockerFixture, mode_delay: int, level_delay: int,
                     remote_pars: str, sudo: bool, error: str) -> None:
        """Positive unit test function for Ipmi.__init__() method. It contains the following steps:
            - create a shell script for IPMI command
            - mock print() function
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - ASSERT: if the mocked print function was called wrong number of times
        """
        my_td = TestData()
        command = my_td.create_command_file()
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(mode_delay),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(level_delay),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: remote_pars
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, sudo)
        assert my_ipmi.command == command, error
        assert my_ipmi.fan_mode_delay == mode_delay, error
        assert my_ipmi.fan_level_delay == level_delay, error
        assert my_ipmi.remote_parameters == remote_pars, error
        assert mock_print.call_count == 5, error  # Ipmi-5
        assert my_ipmi.sudo == sudo, error
        del my_td

    @pytest.mark.parametrize("cmd_exists, mode_delay, level_delay, remote_pars, exception, error", [
        (True, -1,  2,  None,            ValueError,         'Ipmi.__init__() 3'),
        (True, 10, -2,  '-I lanplus',    ValueError,         'Ipmi.__init__() 4'),
        (False, 1,  1,  '',              FileNotFoundError,  'Ipmi.__init__() 5'),
        (False, 1,  1,  '-I lanplus',    RuntimeError,       'Ipmi.__init__() 6')
    ])
    def test_init_n1(self, mocker: MockerFixture, cmd_exists: bool, mode_delay: int, level_delay: int,
                     remote_pars: str, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.__init__() method. It contains the following steps:
            - create a shell script depending on `cmd_exists` flag
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the specified exception was not raised during __init__
            - delete all instances
        """

        #pylint: disable=W0613
        def mocked_ipmi_exec(self, args: List[str]) -> subprocess.CompletedProcess:
            if exception is not ValueError:
                raise exception
            return subprocess.CompletedProcess([], returncode=0)
        #pylint: enable=W0613

        my_td = TestData()
        command = my_td.create_command_file()
        if not cmd_exists:
            my_td.delete_file(command)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mocker.patch('smfc.Ipmi._exec_ipmitool', mocked_ipmi_exec)
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(mode_delay),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(level_delay)
        }
        if remote_pars is not None:
            my_config.set(Ipmi.CS_IPMI, Ipmi.CV_IPMI_REMOTE_PARAMETERS, remote_pars)
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        with pytest.raises(Exception) as cm:
            Ipmi(my_log, my_config, False)
        assert cm.type == exception, error
        del my_td

    # pylint: disable=duplicate-code, protected-access
    @pytest.mark.parametrize("args, remote_args, sudo, error", [
        (['1', '2', '3', '4', '5'], '',             False, 'Ipmi.exec() 1'),
        (['1', '2', '3', '4', '5'], '',             True,  'Ipmi.exec() 2'),
        (['1', '2', '3', '4', '5'], '-I lanplus',   False, 'Ipmi.exec() 3'),
        (['1', '2', '3', '4', '5'], '-I lanplus',   True,  'Ipmi.exec() 4'),
        ([],                        '',             False, 'Ipmi.exec() 5'),
        ([],                        '',             True,  'Ipmi.exec() 6'),
        ([],                        '-I lanplus',   False, 'Ipmi.exec() 7'),
        ([],                        '-I lanplus',   True,  'Ipmi.exec() 8')
    ])
    def test_exec_ipmitool_p(self, mocker: MockerFixture, args: List[str], remote_args: str, sudo:bool,
                             error: str) -> None:
        """Positive unit test for Ipmi.exec() method. It contains the following steps:
            - mock print(), subprocess.run() functions
            - create an Ipmi classes
            - Call Ipmi._exec_ipmitool() method
            - ASSERT: if it was called with different parameters from expected argument list
            - ASSERT: if it was called with different times from expected value
        """
        expected: List[str]     # Expected argument list.

        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_subprocess_run = MagicMock()
        mocker.patch('subprocess.run', mock_subprocess_run)
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.command = 'usr/bin/ipmitool'
        my_ipmi.remote_parameters = remote_args
        my_ipmi.sudo = sudo
        my_ipmi._exec_ipmitool(args)
        expected = []
        if sudo:
            expected.append('sudo')
        expected.append(my_ipmi.command)
        if remote_args:
            expected.extend(remote_args.split())
        expected.extend(args)
        mock_subprocess_run.assert_called_with(expected, check=False, capture_output=True, text=True)
        assert mock_subprocess_run.call_count == 1, error

    @pytest.mark.parametrize("ipmi_command, sudo, rc, exception, error", [
        # The real subprocess.run() executed (without sudo)
        ('/nonexistent/command', False, 0, FileNotFoundError, 'Ipmi.exec() 9'),
        # The mocked subprocess.run() executed and returns non-zero return code
        ('',                     True,  1, RuntimeError,      'Ipmi.exec() 10'),
        ('',                     False, 1, RuntimeError,      'Ipmi.exec() 10')
    ])
    def test_exec_ipmitool_n(self, mocker: MockerFixture, ipmi_command, sudo:bool, rc: int, exception: Any,
                             error: str) -> None:
        """Negative unit test for Ipmi.exec() method. It contains the following steps:
            - create a shell script for IPMI command
            - mock print(), subprocess.run() functions
            - initialize a Config, Log, Ipmi classes
            - Call Ipmi._exec_ipmitool() method
            - ASSERT: if the expected assertion was not raised
        """
        err: List[str] = [
            'sudo: ipmi command not found',
            'ipmitool: error while loading shared libraries'
        ]
        # If we need to mock for the return code.
        if rc:
            mock_subprocess_run = MagicMock()
            mocker.patch('subprocess.run', mock_subprocess_run)
            mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=rc,
                                                                            stderr=err[0] if sudo else err[1])
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.command = ipmi_command
        my_ipmi.remote_parameters = ''
        my_ipmi.sudo = sudo
        with pytest.raises(Exception) as cm:
            my_ipmi._exec_ipmitool(['1', '2', '3'])
        assert cm.type == exception, error
    # pylint: enable=duplicate-code, protected-access

    @pytest.mark.parametrize("expected_mode, error", [
        (Ipmi.STANDARD_MODE,    'Ipmi.get_fan_mode() 1'),
        (Ipmi.FULL_MODE,        'Ipmi.get_fan_mode() 2'),
        (Ipmi.OPTIMAL_MODE,     'Ipmi.get_fan_mode() 3'),
        (Ipmi.HEAVY_IO_MODE,    'Ipmi.get_fan_mode() 4')
    ])
    def test_get_fan_mode_p1(self, mocker:MockerFixture, expected_mode: int, error: str) -> None:
        """Positive unit test for Ipmi.get_fan_mode() method. It contains the following steps:
            - create a shell script with an expected output
            - mock print() function
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the get_fan_mode() returns different value from the expected one
            - delete all instances
        """
        my_td = TestData()
        command = my_td.create_command_file(f'echo " {expected_mode:02}"')
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        assert my_ipmi.get_fan_mode() == expected_mode, error
        del my_td

    @pytest.mark.parametrize("value, exception, error", [
        ('NA', ValueError, 'Ipmi.get_fan_mode() 5'),
        ('',   ValueError, 'Ipmi.get_fan_mode() 6')
    ])
    def test_get_fan_mode_n1(self, value: str, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.get_fan_mode() method. It contains the following steps:
            - create a shell script providing invalid value
            - initialize a Config, Log, Ipmi classes
            - call get_fan_mode() function
            - ASSERT: if the no ValueError exception raised (other exceptions are tested in .exec() method)
            - delete all instances
        """
        my_td = TestData()
        command = my_td.create_command_file('echo " ' + value + '"')
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command
        }
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_mode()
        assert cm.type == exception, error
        del my_td

    @pytest.mark.parametrize("fm, fms, error", [
        (Ipmi.STANDARD_MODE, 'STANDARD', 'Ipmi.get_fan_mode_name() 1'),
        (Ipmi.FULL_MODE,     'FULL',     'Ipmi.get_fan_mode_name() 2'),
        (Ipmi.OPTIMAL_MODE,  'OPTIMAL',  'Ipmi.get_fan_mode_name() 3'),
        (Ipmi.PUE_MODE,      'PUE',      'Ipmi.get_fan_mode_name() 4'),
        (Ipmi.HEAVY_IO_MODE, 'HEAVY IO', 'Ipmi.get_fan_mode_name() 5'),
        (100,                'UNKNOWN',  'Ipmi.get_fan_mode_name() 6')
    ])
    def test_get_fan_mode_name(self, fm: int, fms: str, error: str) -> None:
        """Positive unit test for Ipmi.get_fan_mode_name() method. It contains the following steps:
            - create a shell script for ipmitool substitution
            - mock print() function
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the get_fan_mode_name() returns with a different string from the expected one
            - delete all instances
        """
        assert Ipmi.get_fan_mode_name(fm) == fms, error

    @pytest.mark.parametrize("fan_mode, error", [
        (Ipmi.STANDARD_MODE, 'Ipmi.set_fan_mode() 1'),
        (Ipmi.FULL_MODE,     'Ipmi.set_fan_mode() 2'),
        (Ipmi.OPTIMAL_MODE,  'Ipmi.set_fan_mode() 3'),
        (Ipmi.PUE_MODE,      'Ipmi.set_fan_mode() 4'),
        (Ipmi.HEAVY_IO_MODE, 'Ipmi.set_fan_mode() 5')
    ])
    def test_set_fan_mode_p1(self, mocker:MockerFixture, fan_mode: int, error: str) -> None:
        """Positive unit test for Ipmi.set_fan_mode() method. It contains the following steps:
            - mock Ipmi.exec() and time.sleep() functions
            - create an empty Ipmi class
            - ASSERT: if set_fan_mode() calls Ipmi.exec() and time.sleep() other parameters from expected
            - ASSERT: if set_fan_mode() calls Ipmi.exec() and time.sleep() more from expected times
        """
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.fan_mode_delay = 0
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        mock_time_sleep = MagicMock()
        mocker.patch('time.sleep', mock_time_sleep)
        my_ipmi.set_fan_mode(fan_mode)
        mock_ipmi_exec.assert_called_with(['raw', '0x30', '0x45', '0x01', f'0x{fan_mode:02x}'])
        assert mock_ipmi_exec.call_count == 1, error
        mock_time_sleep.assert_called_with(my_ipmi.fan_mode_delay)
        assert mock_time_sleep.call_count == 1, error

    @pytest.mark.parametrize("fan_mode, exception, error", [
        (-1,  ValueError, 'Ipmi.set_fan_mode() 6'),
        (100, ValueError, 'Ipmi.set_fan_mode() 7')
    ])
    def test_set_fan_mode_n1(self, mocker: MockerFixture, fan_mode: int, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.set_fan_mode(). It contains the following steps:
            - mock Ipmi.exec() function
            - create an empty Ipmi class
            - ASSERT: if set_fan_mode() did not raise ValueError exception in case of invalid parameters
              (other potential exceptions are tested elsewhere)
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.fan_mode_delay = 0
        my_ipmi.sudo = False
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_fan_mode(fan_mode)
        assert cm.type == exception, error

    @pytest.mark.parametrize("zone, level, error", [
        (0, 0,        'Ipmi.set_fan_level() 1'),
        (0, 50,       'Ipmi.set_fan_level() 2'),
        (0, 100,      'Ipmi.set_fan_level() 3'),
        (1, 0,        'Ipmi.set_fan_level() 4'),
        (1, 50,       'Ipmi.set_fan_level() 5'),
        (1, 100,      'Ipmi.set_fan_level() 6')
    ])
    def test_set_fan_level_p1(self, mocker:MockerFixture, zone: int, level: int, error: str) -> None:
        """Positive unit test function. It contains the following steps:
            - mock print(), subprocess.run() functions
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if set_fan_level() calls subprocess.run() command with other parameters than expected
            - delete the instances
        """
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.fan_level_delay = 0
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        mock_time_sleep = MagicMock()
        mocker.patch('time.sleep', mock_time_sleep)
        my_ipmi.set_fan_level(zone, level)
        mock_ipmi_exec.assert_called_with(['raw', '0x30', '0x70', '0x66', '0x01', f'0x{zone:02x}', f'0x{level:02x}'])
        assert mock_ipmi_exec.call_count == 1, error
        mock_time_sleep.assert_called_with(my_ipmi.fan_level_delay)
        assert mock_time_sleep.call_count == 1, error

    @pytest.mark.parametrize("zone, level, error", [
        (Ipmi.CPU_ZONE, -1,  'Ipmi.set_fan_level() 7'),
        (Ipmi.CPU_ZONE, 101, 'Ipmi.set_fan_level() 8'),
        (-1,            50,  'Ipmi.set_fan_level() 9'),
        (101,           50,  'Ipmi.set_fan_level() 10')
    ])
    def test_set_fan_level_n1(self, mocker: MockerFixture, zone: int, level: int, error: str) -> None:
        """Negative unit test for Ipmi.set_fan_level() method. It contains the following steps:
            - mock Ipmi.exec() function
            - create an empty Ipmi class
            - ASSERT: if set_fan_level() does not raise ValueError exception in case of invalid parameter
              (other exceptions are tested elsewhere)
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.fan_level_delay = 0
        my_ipmi.sudo = False
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_fan_level(zone, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize("zones, level, error", [
        ([0],       0,      'Ipmi.set_multiple_fan_levels() 1'),
        ([0, 1],    50,     'Ipmi.set_multiple_fan_levels() 2'),
        ([0, 1, 2], 100,    'Ipmi.set_multiple_fan_levels() 3')
    ])
    def test_set_multiple_fan_levels_p1(self, mocker:MockerFixture, zones: List[int], level: int, error: str) -> None:
        """Positive unit test function. It contains the following steps:
            - mock print(), subprocess.run() functions
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if set_multiple_fan_levels() calls subprocess.run() command with other parameters than expected
            - delete the instances
        """
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.fan_level_delay = 0
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        mock_time_sleep = MagicMock()
        mocker.patch('time.sleep', mock_time_sleep)
        my_ipmi.set_multiple_fan_levels(zones, level)
        calls=[]
        for z in zones:
            calls.append(call(['raw', '0x30', '0x70', '0x66', '0x01', f'0x{z:02x}', f'0x{level:02x}']))
        mock_ipmi_exec.assert_has_calls(calls)
        assert mock_ipmi_exec.call_count == len(zones), error
        mock_time_sleep.assert_called_with(my_ipmi.fan_level_delay)
        assert mock_time_sleep.call_count == 1, error

    @pytest.mark.parametrize("zones, level, error", [
        ([0],       -1,     'Ipmi.set_multiple_fan_levels() 4'),
        ([0],       101,    'Ipmi.set_multiple_fan_levels() 5'),
        ([-1],      50,     'Ipmi.set_multiple_fan_levels() 6'),
        ([101],     50,     'Ipmi.set_multiple_fan_levels() 7'),
        ([0, -1],   50,     'Ipmi.set_multiple_fan_levels() 8'),
        ([101, 0],  50,     'Ipmi.set_multiple_fan_levels() 9')
    ])
    def test_set_multiple_fan_levels_n1(self, mocker: MockerFixture, zones: List[int], level: int, error: str) -> None:
        """Negative unit test for Ipmi.set_fan_level() method. It contains the following steps:
            - mock Ipmi.exec() function
            - create an empty Ipmi class
            - ASSERT: if set_multiple_fan_levels() does not raise ValueError exception in case of invalid parameters
              (other exceptions are tested elsewhere)
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.fan_level_delay = 0
        my_ipmi.sudo = False
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize("zone, expected_level, error", [
        (Ipmi.CPU_ZONE, 0,   'Ipmi.get_fan_level() 1'),
        (Ipmi.CPU_ZONE, 50,  'Ipmi.get_fan_level() 2'),
        (Ipmi.CPU_ZONE, 100, 'Ipmi.get_fan_level() 3'),
        (Ipmi.HD_ZONE,  0,   'Ipmi.get_fan_level() 4'),
        (Ipmi.HD_ZONE,  50,  'Ipmi.get_fan_level() 5'),
        (Ipmi.HD_ZONE,  100, 'Ipmi.get_fan_level() 6')
    ])
    def test_get_fan_level_p1(self, mocker:MockerFixture, zone: int, expected_level: int, error: str) -> None:
        """Positive unit test for Ipmi.get_fan_level() method. It contains the following steps:
            - create a shell script with the expected output
            - mock print() function
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the get_fan_level() returns different from the expected value
            - delete all instances
        """
        my_td = TestData()
        command = my_td.create_command_file(f'echo " {expected_level:x}"')
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        assert my_ipmi.get_fan_level(zone) == expected_level, error
        del my_td

    @pytest.mark.parametrize("zone, level, error", [
        (Ipmi.CPU_ZONE, 'NA', 'Ipmi.get_fan_level() 7'),
        (Ipmi.CPU_ZONE, '',   'Ipmi.get_fan_level() 8'),
        (Ipmi.HD_ZONE,  'NA', 'Ipmi.get_fan_level() 9'),
        (Ipmi.HD_ZONE,  '',   'Ipmi.get_fan_level() 10'),
        (-1,            'NA', 'Ipmi.get_fan_level() 11'),
        (200,           '',   'Ipmi.get_fan_level() 12')
    ])
    def test_get_fan_level_n1(self, zone: int, level: str, error: str) -> None:
        """Negative unit test for Ipmi.get_fan_mode() method. It contains the following steps:
            - create a shell script providing invalid value
            - initialize a Config, Log, Ipmi classes
            - call get_fan_level() function
            - ASSERT: if no ValueError exception raised (other exceptions are tested in .exec() method)
            - delete all instances
        """
        my_td = TestData()
        command = my_td.create_command_file('echo " '+level+'"')
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command
        }
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_level(zone)
        assert cm.type is ValueError, error
        del my_td

    @pytest.mark.parametrize("exception, error", [
        (RuntimeError,      'Ipmi exceptions 1'),
        (FileNotFoundError, 'Ipmi exceptions 2')
    ])
    def test_exceptions(self, mocker:MockerFixture, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.get_fan_mode(), Ipmi.set_fan_mode(), Ipmi.set_fan_level(),
           Ipmi.get_fan_level() methods. It contains the following steps:
            - create a shell script providing invalid value
            - initialize an empty Ipmi class
            - call all functions above
            - ASSERT: if the expected exception was not raised
        """

        def mocked_ipmi_exec(self, args: List[str]) -> subprocess.CompletedProcess:
            raise exception

        mocker.patch('smfc.Ipmi._exec_ipmitool', mocked_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.fan_mode_delay = 0
        my_ipmi.fan_level_delay = 0
        my_ipmi.sudo = False

        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_mode()
        assert cm.type == exception, error

        with pytest.raises(Exception) as cm:
            my_ipmi.set_fan_mode(Ipmi.FULL_MODE)
        assert cm.type == exception, error

        with pytest.raises(Exception) as cm:
            my_ipmi.set_fan_level(Ipmi.CPU_ZONE, 50)
        assert cm.type == exception, error

        with pytest.raises(Exception) as cm:
            my_ipmi.set_multiple_fan_levels([0], 50)
        assert cm.type == exception, error

        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_level(Ipmi.CPU_ZONE)
        assert cm.type == exception, error


# End.
