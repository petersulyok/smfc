#!/usr/bin/env python3
#
#   test_02_ipmi.py (C) 2021-2025, Peter Sulyok
#   Unit tests for smfc.Ipmi() class.
#
import subprocess
import textwrap
from configparser import ConfigParser
from typing import Any, List

import pytest
from mock import MagicMock, call
from pytest_mock import MockerFixture

from smfc.platform import Platform, GenericPlatform, X10QBi, FanMode
from smfc import Ipmi, Log

from .test_00_data import TestData


def _ipmi_exec_effect(*args):
    if args == (["sdr"],):
        return subprocess.CompletedProcess(
            args=['/usr/bin/ipmitool', 'sdr'],
            returncode=0,
            stdout=textwrap.dedent("""\
                CPU1 Temp        | 33 degrees C      | ok
                CPU2 Temp        | 31 degrees C      | ok
                CPU3 Temp        | 29 degrees C      | ok
                CPU4 Temp        | 34 degrees C      | ok
                System Temp      | 32 degrees C      | ok
                Peripheral Temp  | 37 degrees C      | ok
                PCH Temp         | 52 degrees C      | ok
                MB_10G Temp      | 66 degrees C      | ok
                P1M1 DIMMAB Tmp  | no reading        | ns
                P1M1 DIMMCD Tmp  | no reading        | ns
                P1M2 DIMMAB Tmp  | 39 degrees C      | ok
                P1M2 DIMMCD Tmp  | no reading        | ns
                P2M1 DIMMAB Tmp  | 40 degrees C      | ok
                P2M1 DIMMCD Tmp  | no reading        | ns
                P2M2 DIMMAB Tmp  | no reading        | ns
                P2M2 DIMMCD Tmp  | no reading        | ns
                P3M1 DIMMAB Tmp  | 40 degrees C      | ok
                P3M1 DIMMCD Tmp  | no reading        | ns
                P3M2 DIMMAB Tmp  | no reading        | ns
                P3M2 DIMMCD Tmp  | no reading        | ns
                P4M1 DIMMAB Tmp  | 39 degrees C      | ok
                P4M1 DIMMCD Tmp  | no reading        | ns
                P4M2 DIMMAB Tmp  | no reading        | ns
                P4M2 DIMMCD Tmp  | no reading        | ns
                FAN1             | no reading        | ns
                FAN2             | 1000 RPM          | ok
                FAN3             | 1000 RPM          | ok
                FAN4             | 1000 RPM          | ok
                FAN5             | no reading        | ns
                FAN6             | no reading        | ns
                FAN7             | no reading        | ns
                FAN8             | no reading        | ns
                FAN9             | no reading        | ns
                FAN10            | no reading        | ns
                Vcpu1            | 1.78 Volts        | ok
                Vcpu2            | 1.78 Volts        | ok
                Vcpu3            | 1.79 Volts        | ok
                Vcpu4            | 1.79 Volts        | ok
                VMSE_CPU12       | 1.35 Volts        | ok
                VMSE_CPU34       | 1.35 Volts        | ok
                1.5VSSB          | 1.50 Volts        | ok
                VTT              | 0.95 Volts        | ok
                3.3V             | 3.35 Volts        | ok
                3.3VSB           | 3.30 Volts        | ok
                12V              | 12 Volts          | ok
                VBAT             | 3.11 Volts        | ok
                Chassis Intru    | 0x01              | ok
                PS1 Status       | 0x01              | ok
                PS2 Status       | 0x01              | ok
                PS3 Status       | invalid entry     | ok
                """
            ),
            stderr='',
        )
    if args == (["mc", "info"],):
        return subprocess.CompletedProcess(
            args=['/usr/bin/ipmitool', 'mc', 'info'],
            returncode=0,
            stdout=textwrap.dedent("""\
                Device ID                 : 32
                Device Revision           : 1
                Firmware Revision         : 3.19
                IPMI Version              : 2.0
                Manufacturer ID           : 10876
                Manufacturer Name         : Super Micro Computer Inc.
                Product ID                : 1579 (0x062b)
                Product Name              : X10SRi
                Device Available          : yes
                Provides Device SDRs      : no
                Additional Device Support :
                    Sensor Device
                    SDR Repository Device
                    SEL Device
                    FRU Inventory Device
                    IPMB Event Receiver
                    IPMB Event Generator
                    Chassis Device
               """),
            stderr='',
        )
    return subprocess.CompletedProcess([], returncode=0, stdout='') # pragma: no cover

class TestIpmi:
    """Unit test class for smfc.Ipmi() class"""

    @pytest.mark.parametrize("mode_delay, level_delay, remote_pars, sudo, platform_name, platform_instance, error", [
        (10, 2, '',False, 'X11SCH-F', GenericPlatform, 'Ipmi.__init__() 1'),
        (10, 2, '',False, 'X11SCL-iF', GenericPlatform, 'Ipmi.__init__() 2'),
        (10, 2, '',False, 'X10SRi', GenericPlatform, 'Ipmi.__init__() 3'),
        (10, 2, '',False, 'generic', GenericPlatform, 'Ipmi.__init__() 4'),
        (2, 10, '-I lanplus -U ADMIN -P ADMIN -H 127.0.0.1', True, 'X10QBi', X10QBi, 'Ipmi.__init__() 5')
    ])
    def test_init_p1(self, mocker: MockerFixture, mode_delay: int, level_delay: int,
                     remote_pars: str, sudo: bool, platform_name: str,
                     platform_instance: Platform, error: str) -> None:
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
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout='')

        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(mode_delay),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(level_delay),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: remote_pars,
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, sudo)
        assert my_ipmi.command == command, error
        assert my_ipmi.fan_mode_delay == mode_delay, error
        assert my_ipmi.fan_level_delay == level_delay, error
        assert my_ipmi.remote_parameters == remote_pars, error
        assert mock_print.call_count == 7, error  # Ipmi-7
        assert my_ipmi.sudo == sudo, error
        assert my_ipmi.platform.name() == platform_name

        assert isinstance(my_ipmi.platform, platform_instance)
        del my_td

    @pytest.mark.parametrize("case, cmd_exists, mode_delay, level_delay, remote_pars, exception, error", [
        (0, True, -1,  2,  None,            ValueError,         'Ipmi.__init__() 3'),
        (1, True, 10, -2,  '-I lanplus',    ValueError,         'Ipmi.__init__() 4'),
        (2, False, 1,  1,  '',              FileNotFoundError,  'Ipmi.__init__() 5'),
        (3, True,  1,  1,  '-I lanplus',    RuntimeError,       'Ipmi.__init__() 6'), # sudo error
        (4, True,  1,  1,  '',              RuntimeError,       'Ipmi.__init__() 7'), # ipmitool error, but recovered
        (5, True,  1,  1,  '',              RuntimeError,       'Ipmi.__init__() 8')  # ipmitool error with exit
    ])
    def test_init_n1(self, mocker: MockerFixture, case: int, cmd_exists: bool, mode_delay: int, level_delay: int,
                     remote_pars: str, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.__init__() method. It contains the following steps:
            - create a shell script depending on `cmd_exists` flag
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if the specified exception was not raised during __init__
            - delete all instances
        """
        wait_time: float = 0.0

        #pylint: disable=W0613
        def mocked_ipmi_exec(self, args: List[str]) -> subprocess.CompletedProcess:
            nonlocal case
            if case == 2:
                raise FileNotFoundError
            if case == 3:
                raise RuntimeError('sudo error (1): error.')
            if case == 4:
                if wait_time < Ipmi.BMC_INIT_TIMEOUT/2:
                    raise RuntimeError('ipmitool error (1): error.')
            if case == 5:
                raise RuntimeError('ipmitool error (1): error.')
            return subprocess.CompletedProcess([], returncode=0, stdout='')
        #pylint: enable=W0613

        def mocked_time_sleep(second: float) -> None:
            nonlocal  wait_time
            wait_time += second

        my_td = TestData()
        command = my_td.create_command_file()
        if not cmd_exists:
            my_td.delete_file(command)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mocker.patch('time.sleep', mocked_time_sleep)
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
        if case == 4:
            Ipmi(my_log, my_config, False)
            assert wait_time >= Ipmi.BMC_INIT_TIMEOUT/2, error
        else:
            with pytest.raises(Exception) as cm:
                Ipmi(my_log, my_config, False)
            assert cm.type is exception, error
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

    @pytest.mark.parametrize("platform_name, expected_mode, error", [
        ("X11SCH-F", FanMode.STANDARD,    'Ipmi.get_fan_mode() 1'),
        ("X11SCH-F", FanMode.FULL,        'Ipmi.get_fan_mode() 2'),
        ("X11SCH-F", FanMode.OPTIMAL,     'Ipmi.get_fan_mode() 3'),
        ("X11SCH-F", FanMode.HEAVY_IO,    'Ipmi.get_fan_mode() 4'),
        ("X10QBi",   FanMode.STANDARD,    'Ipmi.get_fan_mode() 5'),
        ("X10QBi",   FanMode.FULL,        'Ipmi.get_fan_mode() 6'),
        ("X10QBi",   FanMode.HEAVY_IO,    'Ipmi.get_fan_mode() 7')
    ])
    def test_get_fan_mode_p1(self, mocker:MockerFixture, platform_name: str, expected_mode: int, error: str) -> None:
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
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        assert my_ipmi.get_fan_mode() == expected_mode, error
        del my_td

    @pytest.mark.parametrize("platform_name, value, exception, error", [
        ('X11SCH-F', 'NA', ValueError, 'Ipmi.get_fan_mode() 5'),
        ('X11SCH-F', '',   ValueError, 'Ipmi.get_fan_mode() 6'),
        ('X10QBi',   'NA', ValueError, 'Ipmi.get_fan_mode() 7'),
        ('X10QBi',   '',   ValueError, 'Ipmi.get_fan_mode() 8')
    ])
    def test_get_fan_mode_n1(self, platform_name: str, value: str, exception: Any, error: str) -> None:
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
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_mode()
        assert cm.type == exception, error
        del my_td

    @pytest.mark.parametrize("fm, fms, error", [
        (FanMode.STANDARD, 'STANDARD', 'Ipmi.get_fan_mode_name() 1'),
        (FanMode.FULL,     'FULL',     'Ipmi.get_fan_mode_name() 2'),
        (FanMode.OPTIMAL,  'OPTIMAL',  'Ipmi.get_fan_mode_name() 3'),
        (FanMode.PUE,      'PUE',      'Ipmi.get_fan_mode_name() 4'),
        (FanMode.HEAVY_IO, 'HEAVY IO', 'Ipmi.get_fan_mode_name() 5'),
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

    @pytest.mark.parametrize("platform_name, fan_mode, error", [
        ('X11SCH-F', FanMode.STANDARD, 'Ipmi.set_fan_mode() 1'),
        ('X11SCH-F', FanMode.FULL,     'Ipmi.set_fan_mode() 2'),
        ('X11SCH-F', FanMode.OPTIMAL,  'Ipmi.set_fan_mode() 3'),
        ('X11SCH-F', FanMode.PUE,      'Ipmi.set_fan_mode() 4'),
        ('X11SCH-F', FanMode.HEAVY_IO, 'Ipmi.set_fan_mode() 5'),
        ('X10QBi', FanMode.STANDARD, 'Ipmi.set_fan_mode() 6'),
        ('X10QBi', FanMode.FULL,     'Ipmi.set_fan_mode() 7'),
        ('X10QBi', FanMode.HEAVY_IO, 'Ipmi.set_fan_mode() 8'),
    ])
    def test_set_fan_mode_p1(self, mocker:MockerFixture, platform_name: str, fan_mode: int, error: str) -> None:
        """Positive unit test for Ipmi.set_fan_mode() method. It contains the following steps:
            - mock Ipmi.exec() and time.sleep() functions
            - create an empty Ipmi class
            - ASSERT: if set_fan_mode() calls Ipmi.exec() and time.sleep() other parameters from expected
            - ASSERT: if set_fan_mode() calls Ipmi.exec() and time.sleep() more from expected times
        """
        my_td = TestData()
        command = my_td.create_command_file()
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(10),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(2),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: '',
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
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

    @pytest.mark.parametrize("platform_name, fan_mode, exception, error", [
        ('X11SCH-F', -1,  ValueError, 'Ipmi.set_fan_mode() 6'),
        ('X11SCH-F', 100, ValueError, 'Ipmi.set_fan_mode() 7'),
        ('X10QBi', -1,  ValueError, 'Ipmi.set_fan_mode() 6'),
        ('X10QBi', 100, ValueError, 'Ipmi.set_fan_mode() 7'),
    ])
    def test_set_fan_mode_n1(self, mocker: MockerFixture, platform_name: str,
                             fan_mode: int, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.set_fan_mode(). It contains the following steps:
            - mock Ipmi.exec() function
            - create an empty Ipmi class
            - ASSERT: if set_fan_mode() did not raise ValueError exception in case of invalid parameters
              (other potential exceptions are tested elsewhere)
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_td = TestData()
        command = my_td.create_command_file()
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(10),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(2),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: '',
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        my_ipmi.fan_mode_delay = 0
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_fan_mode(fan_mode)
        assert cm.type == exception, error

    @pytest.mark.parametrize("platform_name, zone, level, ipmitool_call_count, error", [
        ('X11SCH-F', 0, 0, 1,   'Ipmi.set_fan_level() 1'),
        ('X11SCH-F', 0, 50, 1,  'Ipmi.set_fan_level() 2'),
        ('X11SCH-F', 0, 100, 1, 'Ipmi.set_fan_level() 3'),
        ('X11SCH-F', 1, 0, 1,   'Ipmi.set_fan_level() 4'),
        ('X11SCH-F', 1, 50, 1,  'Ipmi.set_fan_level() 5'),
        ('X11SCH-F', 1, 100, 1, 'Ipmi.set_fan_level() 6'),
        ('X10QBi', 16, 0, 12,   'Ipmi.set_fan_level() 7'),
        ('X10QBi', 16, 50, 12,  'Ipmi.set_fan_level() 8'),
        ('X10QBi', 17, 100, 12, 'Ipmi.set_fan_level() 9'),
        ('X10QBi', 18, 0, 12,   'Ipmi.set_fan_level() 10'),
        ('X10QBi', 19, 50, 12,  'Ipmi.set_fan_level() 11'),
        ('X10QBi', 19, 100, 12, 'Ipmi.set_fan_level() 12'),
    ])
    def test_set_fan_level_p1(self, mocker:MockerFixture, platform_name: str,
                              zone: int, level: int, ipmitool_call_count: int, error: str) -> None:
        """Positive unit test function. It contains the following steps:
            - mock print(), subprocess.run() functions
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if set_fan_level() calls subprocess.run() command with other parameters than expected
            - delete the instances
        """
        my_td = TestData()
        command = my_td.create_command_file()
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(10),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(2),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: '',
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        my_ipmi.fan_level_delay = 0
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        mock_time_sleep = MagicMock()
        mocker.patch('time.sleep', mock_time_sleep)
        my_ipmi.set_fan_level(zone, level)
        if platform_name == "X10QBi":
            normalised_level = level * 255 // 100
            mock_ipmi_exec.assert_called_with(
                ['raw', '0x30', '0x91', '0x5c', '0x03', f'0x{zone:02x}', f'0x{normalised_level:02x}']
            )
        else:
            mock_ipmi_exec.assert_called_with(
                ['raw', '0x30', '0x70', '0x66', '0x01', f'0x{zone:02x}', f'0x{level:02x}']
            )
        assert mock_ipmi_exec.call_count == ipmitool_call_count, error
        mock_time_sleep.assert_called_with(my_ipmi.fan_level_delay)
        assert mock_time_sleep.call_count == 1, error

    @pytest.mark.parametrize("platform_name, zone, level, error", [
        ('X11SCH-F', Ipmi.CPU_ZONE, -1,  'Ipmi.set_fan_level() 7'),
        ('X11SCH-F', Ipmi.CPU_ZONE, 101, 'Ipmi.set_fan_level() 8'),
        ('X11SCH-F', -1,            50,  'Ipmi.set_fan_level() 9'),
        ('X11SCH-F', 101,           50,  'Ipmi.set_fan_level() 10'),
        ('X10QBi', int("0x10", 16), -1,  'Ipmi.set_fan_level() 11'),
        ('X10QBi', int("0x10", 16), 101, 'Ipmi.set_fan_level() 12'),
        ('X10QBi', 1,               50,  'Ipmi.set_fan_level() 13'),
        ('X10QBi', 2,               50,  'Ipmi.set_fan_level() 14'),
        ('X10QBi', 20,              50,  'Ipmi.set_fan_level() 15'),
    ])
    def test_set_fan_level_n1(self, mocker: MockerFixture, platform_name: str,
                              zone: int, level: int, error: str) -> None:
        """Negative unit test for Ipmi.set_fan_level() method. It contains the following steps:
            - mock Ipmi.exec() function
            - create an empty Ipmi class
            - ASSERT: if set_fan_level() does not raise ValueError exception in case of invalid parameter
              (other exceptions are tested elsewhere)
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_td = TestData()
        command = my_td.create_command_file()
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(10),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(2),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: '',
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        my_ipmi.fan_level_delay = 0
        my_ipmi.sudo = False
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_fan_level(zone, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize("platform_name, zones, level, ipmitool_call_count, error", [
        ('X11SCH-F', [0],              0, 0,      'Ipmi.set_multiple_fan_levels() 1'),
        ('X11SCH-F', [0, 1],           50, 0,    'Ipmi.set_multiple_fan_levels() 2'),
        ('X11SCH-F', [0, 1, 2],        100, 0,   'Ipmi.set_multiple_fan_levels() 3'),
        ('X10QBi',   [16],             0, 11,     'Ipmi.set_multiple_fan_levels() 4'),
        ('X10QBi',   [16, 17],         50, 11,    'Ipmi.set_multiple_fan_levels() 5'),
        ('X10QBi',   [16, 17, 18, 19], 100, 11,   'Ipmi.set_multiple_fan_levels() 6'),
    ])
    def test_set_multiple_fan_levels_p1(self, mocker:MockerFixture, platform_name: str,
                                        zones: List[int], level: int, ipmitool_call_count, error: str) -> None:
        """Positive unit test function. It contains the following steps:
            - mock print(), subprocess.run() functions
            - initialize a Config, Log, Ipmi classes
            - ASSERT: if set_multiple_fan_levels() calls subprocess.run() command with other parameters than expected
            - delete the instances
        """
        my_td = TestData()
        command = my_td.create_command_file()
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(10),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(2),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: '',
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        my_ipmi.fan_level_delay = 0
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        mock_time_sleep = MagicMock()
        mocker.patch('time.sleep', mock_time_sleep)
        my_ipmi.set_multiple_fan_levels(zones, level)
        calls=[]
        for z in zones:
            if platform_name == "X10QBi":
                normalised_level = level * 255 // 100
                calls.append(call(['raw', '0x30', '0x91', '0x5c', '0x03', f'0x{z:02x}', f'0x{normalised_level:02x}']))
            else:
                calls.append(call(['raw', '0x30', '0x70', '0x66', '0x01', f'0x{z:02x}', f'0x{level:02x}']))
        mock_ipmi_exec.assert_has_calls(calls)
        # In this case, ipmitool_call_count refers to the number of non-zone related ipmitool calls
        # i.e., required to set manual mode
        assert mock_ipmi_exec.call_count == len(zones) + ipmitool_call_count, error
        mock_time_sleep.assert_called_with(my_ipmi.fan_level_delay)
        assert mock_time_sleep.call_count == 1, error

    @pytest.mark.parametrize("platform_name, zones, level, error", [
        ('X11SCH-F', [0],       -1,     'Ipmi.set_multiple_fan_levels() 4'),
        ('X11SCH-F', [0],       101,    'Ipmi.set_multiple_fan_levels() 5'),
        ('X11SCH-F', [-1],      50,     'Ipmi.set_multiple_fan_levels() 6'),
        ('X11SCH-F', [101],     50,     'Ipmi.set_multiple_fan_levels() 7'),
        ('X11SCH-F', [0, -1],   50,     'Ipmi.set_multiple_fan_levels() 8'),
        ('X11SCH-F', [101, 0],  50,     'Ipmi.set_multiple_fan_levels() 9'),
        ('X10QBi',   [16],      -1,     'Ipmi.set_multiple_fan_levels() 10'),
        ('X10QBi',   [16],      101,    'Ipmi.set_multiple_fan_levels() 11'),
        ('X10QBi',   [-1],      50,     'Ipmi.set_multiple_fan_levels() 12'),
        ('X10QBi',   [1],       50,     'Ipmi.set_multiple_fan_levels() 13'),
        ('X10QBi',   [1, 16],   50,     'Ipmi.set_multiple_fan_levels() 14'),
        ('X10QBi',   [16, 0],   50,     'Ipmi.set_multiple_fan_levels() 15')
    ])
    def test_set_multiple_fan_levels_n1(self, mocker: MockerFixture, platform_name: str,
                                        zones: List[int], level: int, error: str) -> None:
        """Negative unit test for Ipmi.set_fan_level() method. It contains the following steps:
            - mock Ipmi.exec() function
            - create an empty Ipmi class
            - ASSERT: if set_multiple_fan_levels() does not raise ValueError exception in case of invalid parameters
              (other exceptions are tested elsewhere)
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_td = TestData()
        command = my_td.create_command_file()
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(10),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(2),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: '',
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        my_ipmi.fan_level_delay = 0
        my_ipmi.sudo = False
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize("platform_name, zone, expected_level, error", [
        ('X11SCH-F', Ipmi.CPU_ZONE, 0,   'Ipmi.get_fan_level() 1'),
        ('X11SCH-F', Ipmi.CPU_ZONE, 50,  'Ipmi.get_fan_level() 2'),
        ('X11SCH-F', Ipmi.CPU_ZONE, 100, 'Ipmi.get_fan_level() 3'),
        ('X11SCH-F', Ipmi.HD_ZONE,  0,   'Ipmi.get_fan_level() 4'),
        ('X11SCH-F', Ipmi.HD_ZONE,  50,  'Ipmi.get_fan_level() 5'),
        ('X11SCH-F', Ipmi.HD_ZONE,  100, 'Ipmi.get_fan_level() 6'),
        ('X10QBi', 16, 0,   'Ipmi.get_fan_level() 7'),
        ('X10QBi', 16, 50,  'Ipmi.get_fan_level() 8'),
        ('X10QBi', 16, 100, 'Ipmi.get_fan_level() 9'),
        ('X10QBi', 17,  0,   'Ipmi.get_fan_level() 10'),
        ('X10QBi', 17,  50,  'Ipmi.get_fan_level() 11'),
        ('X10QBi', 17,  100, 'Ipmi.get_fan_level() 12')
    ])
    def test_get_fan_level_p1(self, mocker: MockerFixture, platform_name: str,
                              zone: int, expected_level: int, error: str) -> None:
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
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        assert my_ipmi.get_fan_level(zone) == expected_level, error
        del my_td

    @pytest.mark.parametrize("platform_name, zone, level, error", [
        ('X11SCH-F', Ipmi.CPU_ZONE, 'NA', 'Ipmi.get_fan_level() 7'),
        ('X11SCH-F', Ipmi.CPU_ZONE, '',   'Ipmi.get_fan_level() 8'),
        ('X11SCH-F', Ipmi.HD_ZONE,  'NA', 'Ipmi.get_fan_level() 9'),
        ('X11SCH-F', Ipmi.HD_ZONE,  '',   'Ipmi.get_fan_level() 10'),
        ('X11SCH-F', -1,            'NA', 'Ipmi.get_fan_level() 11'),
        ('X11SCH-F', 200,           '',   'Ipmi.get_fan_level() 12'),
        ('X10QBi', 16, 'NA', 'Ipmi.get_fan_level() 7'),
        ('X10QBi', 16, '',   'Ipmi.get_fan_level() 8'),
        ('X10QBi', 17,  'NA', 'Ipmi.get_fan_level() 9'),
        ('X10QBi', 17,  '',   'Ipmi.get_fan_level() 10'),
        ('X10QBi', 18,  'NA', 'Ipmi.get_fan_level() 9'),
        ('X10QBi', 18,  '',   'Ipmi.get_fan_level() 10'),
        ('X10QBi', 19,  'NA', 'Ipmi.get_fan_level() 9'),
        ('X10QBi', 19,  '',   'Ipmi.get_fan_level() 10'),
        ('X10QBi', -1,            'NA', 'Ipmi.get_fan_level() 11'),
        ('X10QBi', 200,           '',   'Ipmi.get_fan_level() 12'),
    ])
    def test_get_fan_level_n1(self, platform_name: str, zone: int, level: str, error: str) -> None:
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
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_level(zone)
        assert cm.type is ValueError, error
        del my_td

    @pytest.mark.parametrize("platform_name, zone, exception, error", [
        ('X11SCH-F', Ipmi.CPU_ZONE, RuntimeError,      'Ipmi exceptions 1'),
        ('X11SCH-F', Ipmi.CPU_ZONE, FileNotFoundError, 'Ipmi exceptions 2'),
        ('X10QBi',   16,            RuntimeError,      'Ipmi exceptions 3'),
        ('X10QBi',   16,            FileNotFoundError, 'Ipmi exceptions 4'),
    ])
    def test_exceptions(self, mocker:MockerFixture, platform_name: str, zone: int, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.get_fan_mode(), Ipmi.set_fan_mode(), Ipmi.set_fan_level(),
           Ipmi.get_fan_level() methods. It contains the following steps:
            - create a shell script providing invalid value
            - initialize an empty Ipmi class
            - call all functions above
            - ASSERT: if the expected exception was not raised
        """

        def mocked_ipmi_exec(self, args: List[str]) -> subprocess.CompletedProcess:
            raise exception

        my_td = TestData()
        command = my_td.create_command_file()
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(10),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(2),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: '',
            Ipmi.CV_IPMI_PLATFORM_NAME: platform_name,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)
        my_ipmi.fan_mode_delay = 0
        my_ipmi.fan_level_delay = 0
        my_ipmi.sudo = False

        mocker.patch('smfc.Ipmi._exec_ipmitool', mocked_ipmi_exec)

        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_mode()
        assert cm.type == exception, error

        with pytest.raises(Exception) as cm:
            my_ipmi.set_fan_mode(FanMode.FULL)
        assert cm.type == exception, error

        with pytest.raises(Exception) as cm:
            my_ipmi.set_fan_level(zone, 50)
        assert cm.type == exception, error

        with pytest.raises(Exception) as cm:
            my_ipmi.set_multiple_fan_levels([zone], 50)
        assert cm.type == exception, error

        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_level(zone)
        assert cm.type == exception, error

    def test_get_sensor_data_repository(self, mocker: MockerFixture) -> None:
        """Test to confirm that given a realistic return value from `ipmitool sdr`,
        a well structured dictionary of parsed information is returned.
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.side_effect = _ipmi_exec_effect
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_td = TestData()
        command = my_td.create_command_file()
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(10),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(2),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: '',
            Ipmi.CV_IPMI_PLATFORM_NAME: str(""),
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)

        sdr = my_ipmi.get_sensor_data_repository()

        assert len(sdr) > 0
        assert sdr.get("CPU1 Temp").get("value") == 33
        assert sdr.get("CPU1 Temp").get("unit") == "degrees C"
        assert sdr.get("CPU1 Temp").get("status") == "ok"
        assert sdr.get("FAN4").get("value") == 1000
        assert sdr.get("FAN4").get("unit") == "RPM"
        assert sdr.get("FAN4").get("status") == "ok"
        assert sdr.get("FAN5").get("value") == 0
        assert sdr.get("FAN5").get("unit") == "no reading"
        assert sdr.get("FAN5").get("status") == "ns"
        assert sdr.get("Vcpu1").get("value") == 1.78
        assert sdr.get("Vcpu1").get("unit") == "Volts"
        assert sdr.get("Vcpu1").get("status") == "ok"
        assert sdr.get("Chassis Intru").get("value") == 1
        assert sdr.get("Chassis Intru").get("unit") == "bool"
        assert sdr.get("Chassis Intru").get("status") == "ok"


    def test_identify_platform_name(self, mocker: MockerFixture) -> None:
        """Test to confirm that given a realistic return value from `ipmitool mc info`,
        the platform name is successfully extracted and returned as a string.
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.side_effect = _ipmi_exec_effect
        mocker.patch('smfc.Ipmi._exec_ipmitool', mock_ipmi_exec)
        my_td = TestData()
        command = my_td.create_command_file()
        my_config = ConfigParser()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(10),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(2),
            Ipmi.CV_IPMI_REMOTE_PARAMETERS: '',
            Ipmi.CV_IPMI_PLATFORM_NAME: str(""),
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, my_config, False)

        expected_value = "X10SRi"
        platform_name = my_ipmi.identify_platform_name()

        assert platform_name == expected_value

# End.
