#!/usr/bin/env python3
#
#   test_ipmi.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.Ipmi() class.
#
import subprocess
from typing import Any, List
import pytest
from mock import MagicMock, call
from pytest_mock import MockerFixture
from smfc import Log, Ipmi
from smfc.generic import GenericPlatform
from .test_data import TestData, create_ipmi_config


BMC_INFO_OUTPUT = (
    "Device ID                 : 32\n"
    "Device Revision           : 1\n"
    "Firmware Revision         : 1.74\n"
    "IPMI Version              : 2.0\n"
    "Manufacturer ID           : 10876\n"
    "Manufacturer Name         : Super Micro Computer Inc.\n"
    "Product ID                : 6929 (0x1b11)\n"
    "Product Name              : X11SCH-LN4F\n"
    "Device Available          : yes\n"
    "Provides Device SDRs      : yes\n"
)


class TestIpmi:
    """Unit test class for smfc.Ipmi() class"""

    @pytest.mark.parametrize(
        "mode_delay, level_delay, remote_pars, sudo, error",
        [
            # Local mode, sudo=False
            (10, 2, "", False, "Ipmi.__init__() 1"),
            # Remote mode via lanplus, sudo=True
            (2, 10, "-I lanplus -U ADMIN -P ADMIN -H 127.0.0.1", True, "Ipmi.__init__() 2"),
        ],
    )
    def test_init_p1(self, mocker: MockerFixture, mode_delay: int, level_delay: int, remote_pars: str, sudo: bool,
                     error: str) -> None:
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
        mocker.patch("builtins.print", mock_print)
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.side_effect = [
            subprocess.CompletedProcess([], returncode=0),
            subprocess.CompletedProcess([], returncode=0, stdout=BMC_INFO_OUTPUT),
        ]
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        cfg = create_ipmi_config(command=command, fan_mode_delay=mode_delay, fan_level_delay=level_delay,
                                 remote_parameters=remote_pars)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, cfg, sudo)
        assert my_ipmi.config.command == command, error
        assert my_ipmi.config.fan_mode_delay == mode_delay, error
        assert my_ipmi.config.fan_level_delay == level_delay, error
        assert my_ipmi.config.remote_parameters == remote_pars, error
        assert mock_print.call_count == 11, error  # Ipmi-11
        assert my_ipmi.sudo == sudo, error
        assert my_ipmi.bmc_device_id == 32, error
        assert my_ipmi.bmc_device_rev == 1, error
        assert my_ipmi.bmc_firmware_rev == "1.74", error
        assert my_ipmi.bmc_ipmi_version == "2.0", error
        assert my_ipmi.bmc_manufacturer_id == 10876, error
        assert my_ipmi.bmc_manufacturer_name == "Super Micro Computer Inc.", error
        assert my_ipmi.bmc_product_id == 6929, error
        assert my_ipmi.bmc_product_name == "X11SCH-LN4F", error
        del my_td

    @pytest.mark.parametrize(
        "case, cmd_exists, mode_delay, level_delay, remote_pars, exception, error",
        [
            # Invalid mode_delay (negative)
            (0, True, -1, 2, None, ValueError, "Ipmi.__init__() 3"),
            # Invalid level_delay (negative)
            (1, True, 10, -2, "-I lanplus", ValueError, "Ipmi.__init__() 4"),
            # Command file does not exist
            (2, False, 1, 1, "", FileNotFoundError, "Ipmi.__init__() 5"),
            # sudo error
            (3, True, 1, 1, "-I lanplus", RuntimeError, "Ipmi.__init__() 6"),
            # ipmitool error, but recovered
            (4, True, 1, 1, "", RuntimeError, "Ipmi.__init__() 7"),
            # ipmitool error with exit
            (5, True, 1, 1, "", RuntimeError, "Ipmi.__init__() 8"),
        ],
    )
    def test_init_n1(self, mocker: MockerFixture, case: int, cmd_exists: bool, mode_delay: int, level_delay: int,
                     remote_pars: str, exception: Any, error: str,) -> None:
        """Negative unit test for Ipmi.__init__() method. It contains the following steps:
        - create a shell script depending on `cmd_exists` flag
        - initialize a Config, Log, Ipmi classes
        - ASSERT: if the specified exception was not raised during __init__
        - delete all instances
        """
        wait_time: float = 0.0

        # pylint: disable=W0613
        def mocked_ipmi_exec(self, args: List[str]) -> subprocess.CompletedProcess:
            nonlocal case
            if args == ["bmc", "info"]:
                return subprocess.CompletedProcess([], returncode=0, stdout=BMC_INFO_OUTPUT)
            if case == 2:
                raise FileNotFoundError
            if case == 3:
                raise RuntimeError("sudo error (1): error.")
            if case == 4:
                if wait_time < Ipmi.BMC_INIT_TIMEOUT / 2:
                    raise RuntimeError("ipmitool error (1): error.")
            if case == 5:
                raise RuntimeError("ipmitool error (1): error.")
            return subprocess.CompletedProcess([], returncode=0)

        # pylint: enable=W0613

        def mocked_time_sleep(second: float) -> None:
            nonlocal wait_time
            wait_time += second

        my_td = TestData()
        command = my_td.create_command_file()
        if not cmd_exists:
            my_td.delete_file(command)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch("time.sleep", mocked_time_sleep)
        mocker.patch("smfc.Ipmi._exec_ipmitool", mocked_ipmi_exec)
        cfg = create_ipmi_config(command=command, fan_mode_delay=mode_delay, fan_level_delay=level_delay,
                                 remote_parameters=remote_pars if remote_pars is not None else "")
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        if case == 4:
            Ipmi(my_log, cfg, False)
            assert wait_time >= Ipmi.BMC_INIT_TIMEOUT / 2, error
        else:
            with pytest.raises(Exception) as cm:
                Ipmi(my_log, cfg, False)
            assert cm.type is exception, error
        del my_td

    # pylint: disable=duplicate-code, protected-access
    @pytest.mark.parametrize(
        "args, remote_args, sudo, error",
        [
            # With args, no remote, no sudo
            (["1", "2", "3", "4", "5"], "", False, "Ipmi.exec() 1"),
            # With args, no remote, with sudo
            (["1", "2", "3", "4", "5"], "", True, "Ipmi.exec() 2"),
            # With args, with remote, no sudo
            (["1", "2", "3", "4", "5"], "-I lanplus", False, "Ipmi.exec() 3"),
            # With args, with remote, with sudo
            (["1", "2", "3", "4", "5"], "-I lanplus", True, "Ipmi.exec() 4"),
            # No args, no remote, no sudo
            ([], "", False, "Ipmi.exec() 5"),
            # No args, no remote, with sudo
            ([], "", True, "Ipmi.exec() 6"),
            # No args, with remote, no sudo
            ([], "-I lanplus", False, "Ipmi.exec() 7"),
            # No args, with remote, with sudo
            ([], "-I lanplus", True, "Ipmi.exec() 8"),
        ],
    )
    def test_exec_ipmitool_p(self, mocker: MockerFixture, args: List[str], remote_args: str, sudo: bool,
                             error: str) -> None:
        """Positive unit test for Ipmi.exec() method. It contains the following steps:
        - mock print(), subprocess.run() functions
        - create an Ipmi classes
        - Call Ipmi._exec_ipmitool() method
        - ASSERT: if it was called with different parameters from expected argument list
        - ASSERT: if it was called with different times from expected value
        """
        expected: List[str]  # Expected argument list.

        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_subprocess_run = MagicMock()
        mocker.patch("subprocess.run", mock_subprocess_run)
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.config = create_ipmi_config(command="usr/bin/ipmitool", remote_parameters=remote_args)
        my_ipmi.sudo = sudo
        my_ipmi._exec_ipmitool(args)
        expected = []
        if sudo:
            expected.append("sudo")
        expected.append(my_ipmi.config.command)
        if remote_args:
            expected.extend(remote_args.split())
        expected.extend(args)
        mock_subprocess_run.assert_called_with(
            expected, check=False, capture_output=True, text=True
        )
        assert mock_subprocess_run.call_count == 1, error

    @pytest.mark.parametrize(
        "ipmi_command, sudo, rc, exception, error",
        [
            # Non-existent command path
            ("/nonexistent/command", False, 0, FileNotFoundError, "Ipmi.exec() 9"),
            # Non-zero return code with sudo
            ("", True, 1, RuntimeError, "Ipmi.exec() 10"),
            # Non-zero return code without sudo
            ("", False, 1, RuntimeError, "Ipmi.exec() 10"),
        ],
    )
    def test_exec_ipmitool_n(self, mocker: MockerFixture, ipmi_command, sudo: bool, rc: int, exception: Any,
                             error: str) -> None:
        """Negative unit test for Ipmi.exec() method. It contains the following steps:
        - create a shell script for IPMI command
        - mock print(), subprocess.run() functions
        - initialize a Config, Log, Ipmi classes
        - Call Ipmi._exec_ipmitool() method
        - ASSERT: if the expected assertion was not raised
        """
        err: List[str] = [
            "sudo: ipmi command not found",
            "ipmitool: error while loading shared libraries",
        ]
        # If we need to mock for the return code.
        if rc:
            mock_subprocess_run = MagicMock()
            mocker.patch("subprocess.run", mock_subprocess_run)
            mock_subprocess_run.return_value = subprocess.CompletedProcess(
                [], returncode=rc, stderr=err[0] if sudo else err[1]
            )
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.config = create_ipmi_config(command=ipmi_command)
        my_ipmi.sudo = sudo
        with pytest.raises(Exception) as cm:
            my_ipmi._exec_ipmitool(["1", "2", "3"])
        assert cm.type == exception, error

    # pylint: enable=duplicate-code, protected-access

    @pytest.mark.parametrize(
        "expected_mode, error",
        [
            # STANDARD mode
            (Ipmi.STANDARD_MODE, "Ipmi.get_fan_mode() 1"),
            # FULL mode
            (Ipmi.FULL_MODE, "Ipmi.get_fan_mode() 2"),
            # OPTIMAL mode
            (Ipmi.OPTIMAL_MODE, "Ipmi.get_fan_mode() 3"),
            # HEAVY_IO mode
            (Ipmi.HEAVY_IO_MODE, "Ipmi.get_fan_mode() 4"),
        ],
    )
    def test_get_fan_mode_p1(self, mocker: MockerFixture, expected_mode: int, error: str) -> None:
        """Positive unit test for Ipmi.get_fan_mode() method. It contains the following steps:
        - mock _exec_ipmitool() function
        - create an empty Ipmi class
        - ASSERT: if the get_fan_mode() returns different value from the expected one
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {expected_mode:02}")
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        assert my_ipmi.get_fan_mode() == expected_mode, error

    @pytest.mark.parametrize(
        "value, exception, error",
        [
            # Invalid output: "NA"
            ("NA", ValueError, "Ipmi.get_fan_mode() 5"),
            # Invalid output: empty string
            ("", ValueError, "Ipmi.get_fan_mode() 6"),
        ],
    )
    def test_get_fan_mode_n1(self, mocker: MockerFixture, value: str, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.get_fan_mode() method. It contains the following steps:
        - mock _exec_ipmitool() function with invalid output
        - create an empty Ipmi class
        - call get_fan_mode() function
        - ASSERT: if no ValueError exception raised (other exceptions are tested in .exec() method)
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {value}")
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_mode()
        assert cm.type == exception, error

    @pytest.mark.parametrize(
        "fm, fms, error",
        [
            # STANDARD mode name
            (Ipmi.STANDARD_MODE, "STANDARD", "Ipmi.get_fan_mode_name() 1"),
            # FULL mode name
            (Ipmi.FULL_MODE, "FULL", "Ipmi.get_fan_mode_name() 2"),
            # OPTIMAL mode name
            (Ipmi.OPTIMAL_MODE, "OPTIMAL", "Ipmi.get_fan_mode_name() 3"),
            # PUE mode name
            (Ipmi.PUE_MODE, "PUE", "Ipmi.get_fan_mode_name() 4"),
            # HEAVY_IO mode name
            (Ipmi.HEAVY_IO_MODE, "HEAVY IO", "Ipmi.get_fan_mode_name() 5"),
            # Unknown mode name
            (100, "UNKNOWN", "Ipmi.get_fan_mode_name() 6"),
        ],
    )
    def test_get_fan_mode_name(self, fm: int, fms: str, error: str) -> None:
        """Positive unit test for Ipmi.get_fan_mode_name() method. It contains the following steps:
        - create a shell script for ipmitool substitution
        - mock print() function
        - initialize a Config, Log, Ipmi classes
        - ASSERT: if the get_fan_mode_name() returns with a different string from the expected one
        - delete all instances
        """
        assert Ipmi.get_fan_mode_name(fm) == fms, error

    @pytest.mark.parametrize(
        "fan_mode, error",
        [
            # STANDARD mode
            (Ipmi.STANDARD_MODE, "Ipmi.set_fan_mode() 1"),
            # FULL mode
            (Ipmi.FULL_MODE, "Ipmi.set_fan_mode() 2"),
            # OPTIMAL mode
            (Ipmi.OPTIMAL_MODE, "Ipmi.set_fan_mode() 3"),
            # PUE mode
            (Ipmi.PUE_MODE, "Ipmi.set_fan_mode() 4"),
            # HEAVY_IO mode
            (Ipmi.HEAVY_IO_MODE, "Ipmi.set_fan_mode() 5"),
        ],
    )
    def test_set_fan_mode_p1(self, mocker: MockerFixture, fan_mode: int, error: str) -> None:
        """Positive unit test for Ipmi.set_fan_mode() method. It contains the following steps:
        - mock Ipmi.exec() and time.sleep() functions
        - create an empty Ipmi class
        - ASSERT: if set_fan_mode() calls Ipmi.exec() and time.sleep() other parameters from expected
        - ASSERT: if set_fan_mode() calls Ipmi.exec() and time.sleep() more from expected times
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        my_ipmi.config = create_ipmi_config(fan_mode_delay=0)
        mock_time_sleep = MagicMock()
        mocker.patch("time.sleep", mock_time_sleep)
        my_ipmi.set_fan_mode(fan_mode)
        mock_ipmi_exec.assert_called_with(
            ["raw", "0x30", "0x45", "0x01", f"0x{fan_mode:02x}"]
        )
        assert mock_ipmi_exec.call_count == 1, error
        mock_time_sleep.assert_called_with(my_ipmi.config.fan_mode_delay)
        assert mock_time_sleep.call_count == 1, error

    @pytest.mark.parametrize(
        "fan_mode, exception, error",
        [
            # Invalid mode: negative
            (-1, ValueError, "Ipmi.set_fan_mode() 6"),
            # Invalid mode: over valid range
            (100, ValueError, "Ipmi.set_fan_mode() 7"),
        ],
    )
    def test_set_fan_mode_n1(self, mocker: MockerFixture, fan_mode: int, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.set_fan_mode(). It contains the following steps:
        - mock Ipmi.exec() function
        - create an empty Ipmi class
        - ASSERT: if set_fan_mode() did not raise ValueError exception in case of invalid parameters
          (other potential exceptions are tested elsewhere)
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        my_ipmi.config = create_ipmi_config(fan_mode_delay=0)
        my_ipmi.sudo = False
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_fan_mode(fan_mode)
        assert cm.type == exception, error

    @pytest.mark.parametrize(
        "zone, level, error",
        [
            # Zone 0, level 0 (min)
            (0, 0, "Ipmi.set_fan_level() 1"),
            # Zone 0, level 50 (mid)
            (0, 50, "Ipmi.set_fan_level() 2"),
            # Zone 0, level 100 (max)
            (0, 100, "Ipmi.set_fan_level() 3"),
            # Zone 1, level 0 (min)
            (1, 0, "Ipmi.set_fan_level() 4"),
            # Zone 1, level 50 (mid)
            (1, 50, "Ipmi.set_fan_level() 5"),
            # Zone 1, level 100 (max)
            (1, 100, "Ipmi.set_fan_level() 6"),
        ],
    )
    def test_set_fan_level_p1(self, mocker: MockerFixture, zone: int, level: int, error: str) -> None:
        """Positive unit test for Ipmi.set_fan_level() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool() and time.sleep() functions
        - create an empty Ipmi class
        - ASSERT: if set_fan_level() calls Ipmi._exec_ipmitool() with other parameters than expected
        - ASSERT: if set_fan_level() calls time.sleep() with other parameters than expected
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        my_ipmi.config = create_ipmi_config(fan_level_delay=0)
        mock_time_sleep = MagicMock()
        mocker.patch("time.sleep", mock_time_sleep)
        my_ipmi.set_fan_level(zone, level)
        mock_ipmi_exec.assert_called_with(
            ["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{level:02x}"]
        )
        assert mock_ipmi_exec.call_count == 1, error
        mock_time_sleep.assert_called_with(my_ipmi.config.fan_level_delay)
        assert mock_time_sleep.call_count == 1, error

    @pytest.mark.parametrize(
        "zone, level, error",
        [
            # Invalid level: negative
            (Ipmi.CPU_ZONE, -1, "Ipmi.set_fan_level() 7"),
            # Invalid level: over 100
            (Ipmi.CPU_ZONE, 101, "Ipmi.set_fan_level() 8"),
            # Invalid zone: negative
            (-1, 50, "Ipmi.set_fan_level() 9"),
            # Invalid zone: over 100
            (101, 50, "Ipmi.set_fan_level() 10"),
        ],
    )
    def test_set_fan_level_n1(self, mocker: MockerFixture, zone: int, level: int, error: str) -> None:
        """Negative unit test for Ipmi.set_fan_level() method. It contains the following steps:
        - mock Ipmi.exec() function
        - create an empty Ipmi class
        - ASSERT: if set_fan_level() does not raise ValueError exception in case of invalid parameter
          (other exceptions are tested elsewhere)
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        my_ipmi.config = create_ipmi_config(fan_level_delay=0)
        my_ipmi.sudo = False
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_fan_level(zone, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zones, level, error",
        [
            # Single zone, level 0
            ([0], 0, "Ipmi.set_multiple_fan_levels() 1"),
            # Two zones, level 50
            ([0, 1], 50, "Ipmi.set_multiple_fan_levels() 2"),
            # Three zones, level 100
            ([0, 1, 2], 100, "Ipmi.set_multiple_fan_levels() 3"),
        ],
    )
    def test_set_multiple_fan_levels_p1(self, mocker: MockerFixture, zones: List[int], level: int, error: str) -> None:
        """Positive unit test for Ipmi.set_multiple_fan_levels() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool() and time.sleep() functions
        - create an empty Ipmi class
        - ASSERT: if set_multiple_fan_levels() calls Ipmi._exec_ipmitool() with other parameters than expected
        - ASSERT: if set_multiple_fan_levels() calls time.sleep() with other parameters than expected
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        my_ipmi.config = create_ipmi_config(fan_level_delay=0)
        mock_time_sleep = MagicMock()
        mocker.patch("time.sleep", mock_time_sleep)
        my_ipmi.set_multiple_fan_levels(zones, level)
        # pylint: disable=duplicate-code
        calls = []
        for z in zones:
            calls.append(call(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{z:02x}", f"0x{level:02x}"]))
        # pylint: enable=duplicate-code
        mock_ipmi_exec.assert_has_calls(calls)
        assert mock_ipmi_exec.call_count == len(zones), error
        mock_time_sleep.assert_called_with(my_ipmi.config.fan_level_delay)
        assert mock_time_sleep.call_count == 1, error

    @pytest.mark.parametrize(
        "zones, level, error",
        [
            # Invalid level: negative
            ([0], -1, "Ipmi.set_multiple_fan_levels() 4"),
            # Invalid level: over 100
            ([0], 101, "Ipmi.set_multiple_fan_levels() 5"),
            # Invalid zone: negative
            ([-1], 50, "Ipmi.set_multiple_fan_levels() 6"),
            # Invalid zone: over 100
            ([101], 50, "Ipmi.set_multiple_fan_levels() 7"),
            # Invalid zone in list: negative
            ([0, -1], 50, "Ipmi.set_multiple_fan_levels() 8"),
            # Invalid zone in list: over 100
            ([101, 0], 50, "Ipmi.set_multiple_fan_levels() 9"),
        ],
    )
    def test_set_multiple_fan_levels_n1(self, mocker: MockerFixture, zones: List[int], level: int, error: str) -> None:
        """Negative unit test for Ipmi.set_fan_level() method. It contains the following steps:
        - mock Ipmi.exec() function
        - create an empty Ipmi class
        - ASSERT: if set_multiple_fan_levels() does not raise ValueError exception in case of invalid parameters
          (other exceptions are tested elsewhere)
        """
        mock_ipmi_exec = MagicMock()
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        my_ipmi.config = create_ipmi_config(fan_level_delay=0)
        my_ipmi.sudo = False
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "zone, expected_level, error",
        [
            # CPU zone, level 0
            (Ipmi.CPU_ZONE, 0, "Ipmi.get_fan_level() 1"),
            # CPU zone, level 50
            (Ipmi.CPU_ZONE, 50, "Ipmi.get_fan_level() 2"),
            # CPU zone, level 100
            (Ipmi.CPU_ZONE, 100, "Ipmi.get_fan_level() 3"),
            # HD zone, level 0
            (Ipmi.HD_ZONE, 0, "Ipmi.get_fan_level() 4"),
            # HD zone, level 50
            (Ipmi.HD_ZONE, 50, "Ipmi.get_fan_level() 5"),
            # HD zone, level 100
            (Ipmi.HD_ZONE, 100, "Ipmi.get_fan_level() 6"),
        ],
    )
    def test_get_fan_level_p1(self, mocker: MockerFixture, zone: int, expected_level: int, error: str) -> None:
        """Positive unit test for Ipmi.get_fan_level() method. It contains the following steps:
        - mock _exec_ipmitool() function
        - create an empty Ipmi class
        - ASSERT: if the get_fan_level() returns different from the expected value
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {expected_level:x}")
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        assert my_ipmi.get_fan_level(zone) == expected_level, error

    @pytest.mark.parametrize(
        "zone, level, error",
        [
            # CPU zone, invalid output "NA"
            (Ipmi.CPU_ZONE, "NA", "Ipmi.get_fan_level() 7"),
            # CPU zone, empty output
            (Ipmi.CPU_ZONE, "", "Ipmi.get_fan_level() 8"),
            # HD zone, invalid output "NA"
            (Ipmi.HD_ZONE, "NA", "Ipmi.get_fan_level() 9"),
            # HD zone, empty output
            (Ipmi.HD_ZONE, "", "Ipmi.get_fan_level() 10"),
            # Invalid zone: negative
            (-1, "NA", "Ipmi.get_fan_level() 11"),
            # Invalid zone: over 100
            (200, "", "Ipmi.get_fan_level() 12"),
        ],
    )
    def test_get_fan_level_n1(self, mocker: MockerFixture, zone: int, level: str, error: str) -> None:
        """Negative unit test for Ipmi.get_fan_level() method. It contains the following steps:
        - mock _exec_ipmitool() function with invalid output
        - create an empty Ipmi class
        - call get_fan_level() function
        - ASSERT: if no ValueError exception raised (other exceptions are tested in .exec() method)
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {level}")
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_level(zone)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "exception, error",
        [
            # RuntimeError exception
            (RuntimeError, "Ipmi exceptions 1"),
            # FileNotFoundError exception
            (FileNotFoundError, "Ipmi exceptions 2"),
        ],
    )
    def test_exceptions(self, exception: Any, error: str) -> None:
        """Negative unit test for Ipmi.get_fan_mode(), Ipmi.set_fan_mode(), Ipmi.set_fan_level(),
        Ipmi.set_multiple_fan_levels(), Ipmi.get_fan_level() methods. It contains the following steps:
        - create an empty Ipmi class with a raising exec function
        - call all functions above
        - ASSERT: if the expected exception was not raised
        """

        def raising_exec(args: List[str]) -> subprocess.CompletedProcess:
            raise exception

        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", raising_exec)
        my_ipmi.config = create_ipmi_config(fan_mode_delay=0, fan_level_delay=0)
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
