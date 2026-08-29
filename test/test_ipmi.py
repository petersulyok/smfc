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
from smfc.config import Config
from smfc.generic import GenericPlatform
from smfc.ipmi import parse_completion_code
from smfc.platform import IpmiError
from .test_config_builders import create_ipmi_config
from .test_fixtures import TestData


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

# `ipmitool sdr` output once the fan subsystem has settled: fan sensors report live RPM values.
SDR_READY_OUTPUT = (
    "CPU Temp         | 45 degrees C      | ok\n"
    "FAN1             | 500 RPM           | ok\n"
    "FANA             | 500 RPM           | ok\n"
)

# `ipmitool sdr` output during the post-cold-boot transitional window: every sensor still reads `ns`.
# Matches a real `mc reset cold` capture on the X11SCH-LN4F, where all sensors show `no reading | ns`
# for ~69 s after the command interface returns rc=0, before the fan subsystem settles.
SDR_NOTREADY_OUTPUT = (
    "CPU Temp         | no reading        | ns\n"
    "FAN1             | no reading        | ns\n"
    "FANA             | no reading        | ns\n"
)

# `ipmitool sdr` output of a board reboot that leaves the BMC powered: sensors read `disabled | ns`
# instead of `no reading | ns`. Both strings co-occur with state `ns`, which is why the gate keys on
# the state column. Captured on the X11SCH-LN4F.
SDR_NOTREADY_DISABLED_OUTPUT = (
    "CPU Temp         | disabled          | ns\n"
    "FAN1             | disabled          | ns\n"
    "FANA             | disabled          | ns\n"
)

# `ipmitool sdr` output of a board naming its fans with a prefix (e.g. X13SAE-F): the fan sensors are
# `CPU_FAN*`/`SYS_FAN*` instead of `FAN*`.
SDR_PREFIXED_READY_OUTPUT = (
    "CPU Temp         | 45 degrees C      | ok\n"
    "CPU_FAN1         | 840 RPM           | ok\n"
    "CPU_FAN2         | 840 RPM           | ok\n"
    "SYS_FAN1         | 980 RPM           | ok\n"
    "SYS_FAN2         | 840 RPM           | ok\n"
    "SYS_FAN3         | 980 RPM           | ok\n"
)

# A complete `sdr` list with no fan sensor at all: no sensor name of a real Supermicro board carries
# `FAN` outside of the fan sensors themselves, so none of these may satisfy the gate.
SDR_NO_FAN_OUTPUT = (
    "CPU Temp         | 45 degrees C      | ok\n"
    "Inlet Temp       | no reading        | ns\n"
    "PCH Temp         | 59 degrees C      | ok\n"
    "DIMMA1 Temp      | 32 degrees C      | ok\n"
    "12V              | 11.79 Volts       | ok\n"
    "VBAT             | 0x04              | ok\n"
    "1.8V_PCH_GPPA    | 1.82 Volts        | ok\n"
    "Chassis Intru    | 0x00              | ok\n"
)


def _make_bare_ipmi(mocker: MockerFixture, mock_ipmi_exec: MagicMock, **cfg_kwargs) -> Ipmi:
    """Build a bare Ipmi instance (no __init__) wired with the given exec mock and a default config.

    Removes the repeated `Ipmi.__new__(Ipmi) / .platform = / .config = / .sudo =` boilerplate that appears in
    nearly every non-init test below. `_exec_ipmitool` is patched at class level so any path through Ipmi
    routes to the supplied mock; `platform` is wired to a real GenericPlatform that uses the same mock for
    its own exec calls.
    """
    mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
    ipmi = Ipmi.__new__(Ipmi)
    ipmi.platform = GenericPlatform("test", mock_ipmi_exec)
    ipmi.config = create_ipmi_config(**cfg_kwargs)
    ipmi.sudo = False
    return ipmi


class TestIpmi:
    """Unit test class for smfc.Ipmi() class"""

    @pytest.mark.parametrize(
        "mode_delay, level_delay, remote_pars, sudo",
        [
            pytest.param(10, 2, "", False, id="local-no-sudo"),
            pytest.param(2, 10, "-I lanplus -U ADMIN -P ADMIN -H 127.0.0.1", True, id="remote-lanplus-sudo"),
        ],
    )
    def test_init_sets_attributes_and_bmc_info(self, mocker: MockerFixture, td: TestData, mode_delay: int,
                                               level_delay: int, remote_pars: str, sudo: bool) -> None:
        """Positive unit test for Ipmi.__init__() method. It contains the following steps:
        - mock builtins.print, Ipmi._exec_ipmitool (returns BMC info), and the td fixture's create_command_file
          (fake ipmitool binary)
        - build an ipmi Config via create_ipmi_config with the given delays and remote parameters
        - initialize a Log and call Ipmi(my_log, cfg, sudo)
        - ASSERT: config.command equals the created command path
        - ASSERT: config.fan_mode_delay equals mode_delay
        - ASSERT: config.fan_level_delay equals level_delay
        - ASSERT: config.remote_parameters equals remote_pars
        - ASSERT: print was called exactly 12 times (Ipmi-12 init messages)
        - ASSERT: sudo attribute equals the sudo argument
        - ASSERT: bmc_device_id, bmc_device_rev, bmc_firmware_rev, bmc_ipmi_version, bmc_manufacturer_id,
          bmc_manufacturer_name, bmc_product_id, bmc_product_name are parsed from BMC_INFO_OUTPUT
        """
        command = td.create_command_file()
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.side_effect = [
            subprocess.CompletedProcess([], returncode=0, stdout=SDR_READY_OUTPUT),
            subprocess.CompletedProcess([], returncode=0, stdout=BMC_INFO_OUTPUT),
        ]
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        cfg = create_ipmi_config(command=command, fan_mode_delay=mode_delay, fan_level_delay=level_delay,
                                 remote_parameters=remote_pars)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, cfg, sudo)
        assert my_ipmi.config.command == command
        assert my_ipmi.config.fan_mode_delay == mode_delay
        assert my_ipmi.config.fan_level_delay == level_delay
        assert my_ipmi.config.remote_parameters == remote_pars
        assert my_ipmi.config.ipmitool_timeout == Config.DV_IPMI_IPMITOOL_TIMEOUT
        assert mock_print.call_count == 14  # Ipmi-14 (incl. the ipmitool_timeout line)
        assert my_ipmi.sudo == sudo
        assert my_ipmi.bmc_device_id == 32
        assert my_ipmi.bmc_device_rev == 1
        assert my_ipmi.bmc_firmware_rev == "1.74"
        assert my_ipmi.bmc_ipmi_version == "2.0"
        assert my_ipmi.bmc_manufacturer_id == 10876
        assert my_ipmi.bmc_manufacturer_name == "Super Micro Computer Inc."
        assert my_ipmi.bmc_product_id == 6929
        assert my_ipmi.bmc_product_name == "X11SCH-LN4F"

    @pytest.mark.parametrize(
        "case, cmd_exists, mode_delay, level_delay, remote_pars, exception",
        [
            pytest.param(0, True, -1, 2, None, ValueError, id="invalid-mode-delay"),
            pytest.param(1, True, 10, -2, "-I lanplus", ValueError, id="invalid-level-delay"),
            pytest.param(2, False, 1, 1, "", FileNotFoundError, id="missing-command-file"),
            pytest.param(3, True, 1, 1, "-I lanplus", RuntimeError, id="sudo-error"),
            pytest.param(4, True, 1, 1, "", RuntimeError, id="ipmitool-error-recovered"),
            pytest.param(5, True, 1, 1, "", RuntimeError, id="ipmitool-error-exit"),
        ],
    )
    def test_init_raises_on_invalid_config_or_bmc_failure(self, mocker: MockerFixture, td: TestData, case: int,
                                                          cmd_exists: bool, mode_delay: int, level_delay: int,
                                                          remote_pars: str, exception: Any) -> None:
        """Negative unit test for Ipmi.__init__() method. It contains the following steps:
        - mock builtins.print, time.sleep (tracks wait_time), and Ipmi._exec_ipmitool to simulate different
          BMC/sudo/ipmitool failures; use the td fixture's create_command_file (fake ipmitool binary), optionally
          deleted via td.delete_file
        - build an ipmi Config via create_ipmi_config with the parameterized delays and remote parameters
        - call Ipmi(my_log, cfg, False) inside pytest.raises (except for the recovered-error case which must
          succeed after BMC_INIT_TIMEOUT/2)
        - ASSERT: for the recovered case, wait_time accumulates to at least BMC_INIT_TIMEOUT/2
        - ASSERT: for failure cases, the raised exception type matches `exception`
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
            return subprocess.CompletedProcess([], returncode=0, stdout=SDR_READY_OUTPUT)

        # pylint: enable=W0613

        def mocked_time_sleep(second: float) -> None:
            nonlocal wait_time
            wait_time += second

        command = td.create_command_file()
        if not cmd_exists:
            td.delete_file(command)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch("time.sleep", mocked_time_sleep)
        mocker.patch("smfc.Ipmi._exec_ipmitool", mocked_ipmi_exec)
        cfg = create_ipmi_config(command=command, fan_mode_delay=mode_delay, fan_level_delay=level_delay,
                                 remote_parameters=remote_pars if remote_pars is not None else "")
        my_log = Log(Log.LOG_ERROR, Log.LOG_STDOUT)
        if case == 4:
            Ipmi(my_log, cfg, False)
            assert wait_time >= Ipmi.BMC_INIT_TIMEOUT / 2
        else:
            with pytest.raises(Exception) as cm:
                Ipmi(my_log, cfg, False)
            assert cm.type is exception

    def test_init_rejects_negative_ipmitool_timeout(self, mocker: MockerFixture, td: TestData) -> None:
        """Negative unit test for Ipmi.__init__() method. It contains the following steps:
        - mock builtins.print and Ipmi._exec_ipmitool (never reached)
        - build an ipmi Config via create_ipmi_config with ipmitool_timeout=-1
        - call Ipmi(my_log, cfg, False) inside pytest.raises
        - ASSERT: ValueError is raised before any BMC access, and names the offending parameter. 0 is
          accepted and means "wait indefinitely"; only a negative value is meaningless
        """
        f = "TestIpmi.test_init_rejects_negative_ipmitool_timeout"
        mocker.patch("builtins.print", MagicMock())
        mocker.patch("smfc.Ipmi._exec_ipmitool", MagicMock())
        cfg = create_ipmi_config(command=td.create_command_file(), ipmitool_timeout=-1)
        with pytest.raises(ValueError) as cm:
            Ipmi(Log(Log.LOG_ERROR, Log.LOG_STDOUT), cfg, False)
        assert "ipmitool_timeout" in str(cm.value), f"{f}: message names the parameter: {cm.value}"

    # pylint: disable=duplicate-code, protected-access
    @pytest.mark.parametrize(
        "args, remote_args, sudo",
        [
            pytest.param(["1", "2", "3", "4", "5"], "", False, id="args-no-remote-no-sudo"),
            pytest.param(["1", "2", "3", "4", "5"], "", True, id="args-no-remote-sudo"),
            pytest.param(["1", "2", "3", "4", "5"], "-I lanplus", False, id="args-remote-no-sudo"),
            pytest.param(["1", "2", "3", "4", "5"], "-I lanplus", True, id="args-remote-sudo"),
            pytest.param([], "", False, id="no-args-no-remote-no-sudo"),
            pytest.param([], "", True, id="no-args-no-remote-sudo"),
            pytest.param([], "-I lanplus", False, id="no-args-remote-no-sudo"),
            pytest.param([], "-I lanplus", True, id="no-args-remote-sudo"),
        ],
    )
    def test_exec_ipmitool_invokes_subprocess_with_expected_args(self, mocker: MockerFixture, args: List[str],
                                                                  remote_args: str, sudo: bool) -> None:
        """Positive unit test for Ipmi.exec_ipmitool() method. It contains the following steps:
        - mock builtins.print and subprocess.run (returns CompletedProcess rc=0)
        - build a bare Ipmi via Ipmi.__new__ with create_ipmi_config(command, remote_parameters) and sudo flag
        - call Ipmi._exec_ipmitool(args)
        - ASSERT: subprocess.run was called with the expected argv (optional 'sudo', command, remote args, args)
          plus check=False, capture_output=True, text=True
        - ASSERT: subprocess.run was called exactly once
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
        mock_subprocess_run.assert_called_with(expected, check=False, capture_output=True, text=True,
                                              timeout=Config.DV_IPMI_IPMITOOL_TIMEOUT)
        assert mock_subprocess_run.call_count == 1

    @pytest.mark.parametrize(
        "ipmi_command, sudo, rc, exception",
        [
            pytest.param("/nonexistent/command", False, 0, FileNotFoundError, id="missing-command-path"),
            pytest.param("", True, 1, IpmiError, id="nonzero-rc-sudo"),
            pytest.param("", False, 1, IpmiError, id="nonzero-rc-no-sudo"),
        ],
    )
    def test_exec_ipmitool_raises_on_missing_command_or_nonzero_rc(self, mocker: MockerFixture, ipmi_command,
                                                                    sudo: bool, rc: int, exception: Any) -> None:
        """Negative unit test for Ipmi.exec_ipmitool() method. It contains the following steps:
        - mock subprocess.run (when rc != 0) to return a CompletedProcess with sudo/ipmitool stderr text
        - build a bare Ipmi via Ipmi.__new__ with create_ipmi_config(command=ipmi_command) and the sudo flag
        - call Ipmi._exec_ipmitool(["1", "2", "3"]) inside pytest.raises
        - ASSERT: the raised exception type matches the parameterized `exception`
        - ASSERT: an ipmitool failure is an IpmiError, which is a RuntimeError subclass, so every existing
          `except RuntimeError` in the code base keeps catching it unchanged (a missing ipmitool binary still
          raises FileNotFoundError, unchanged)
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
        assert cm.type == exception
        if exception is IpmiError:
            assert isinstance(cm.value, RuntimeError)

    # pylint: enable=duplicate-code, protected-access

    @pytest.mark.parametrize(
        "expected_mode",
        [
            pytest.param(Ipmi.STANDARD_MODE, id="standard"),
            pytest.param(Ipmi.FULL_MODE, id="full"),
            pytest.param(Ipmi.OPTIMAL_MODE, id="optimal"),
            pytest.param(Ipmi.HEAVY_IO_MODE, id="heavy-io"),
        ],
    )
    def test_get_fan_mode_returns_parsed_mode(self, mocker: MockerFixture, expected_mode: int) -> None:
        """Positive unit test for Ipmi.get_fan_mode() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool to return CompletedProcess with stdout=" {mode:02}"
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate)
        - call my_ipmi.get_fan_mode()
        - ASSERT: get_fan_mode() returns the expected parsed mode value
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {expected_mode:02}")
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec)
        assert my_ipmi.get_fan_mode() == expected_mode

    @pytest.mark.parametrize(
        "value, exception",
        [
            pytest.param("NA", ValueError, id="output-na"),
            pytest.param("", ValueError, id="output-empty"),
        ],
    )
    def test_get_fan_mode_raises_on_invalid_output(self, mocker: MockerFixture, value: str, exception: Any) -> None:
        """Negative unit test for Ipmi.get_fan_mode() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool to return CompletedProcess with invalid stdout (e.g. "NA" or "")
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate)
        - call my_ipmi.get_fan_mode() inside pytest.raises
        - ASSERT: the raised exception type equals ValueError
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {value}")
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec)
        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_mode()
        assert cm.type == exception

    @pytest.mark.parametrize(
        "fm, fms",
        [
            pytest.param(Ipmi.STANDARD_MODE, "STANDARD", id="standard"),
            pytest.param(Ipmi.FULL_MODE, "FULL", id="full"),
            pytest.param(Ipmi.OPTIMAL_MODE, "OPTIMAL", id="optimal"),
            pytest.param(Ipmi.PUE_MODE, "PUE", id="pue"),
            pytest.param(Ipmi.HEAVY_IO_MODE, "HEAVY IO", id="heavy-io"),
            pytest.param(100, "UNKNOWN", id="unknown"),
        ],
    )
    def test_get_fan_mode_name(self, fm: int, fms: str) -> None:
        """Positive unit test for Ipmi.get_fan_mode_name() method. It contains the following steps:
        - call the static Ipmi.get_fan_mode_name(fm) with each parameterized mode value (no mocks required)
        - ASSERT: get_fan_mode_name returns the expected string name (unknown modes fall back to "UNKNOWN")
        """
        assert Ipmi.get_fan_mode_name(fm) == fms

    @pytest.mark.parametrize(
        "fan_mode",
        [
            pytest.param(Ipmi.STANDARD_MODE, id="standard"),
            pytest.param(Ipmi.FULL_MODE, id="full"),
            pytest.param(Ipmi.OPTIMAL_MODE, id="optimal"),
            pytest.param(Ipmi.PUE_MODE, id="pue"),
            pytest.param(Ipmi.HEAVY_IO_MODE, id="heavy-io"),
        ],
    )
    def test_set_fan_mode_invokes_ipmitool_and_sleeps(self, mocker: MockerFixture, fan_mode: int) -> None:
        """Positive unit test for Ipmi.set_fan_mode() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool and time.sleep
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate) with
          fan_mode_delay=0
        - call my_ipmi.set_fan_mode(fan_mode)
        - ASSERT: _exec_ipmitool was called with ["raw", "0x30", "0x45", "0x01", f"0x{fan_mode:02x}"]
        - ASSERT: _exec_ipmitool was called exactly once
        - ASSERT: time.sleep was called with config.fan_mode_delay
        - ASSERT: time.sleep was called exactly once
        """
        mock_ipmi_exec = MagicMock()
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec, fan_mode_delay=0)
        mock_time_sleep = MagicMock()
        mocker.patch("time.sleep", mock_time_sleep)
        my_ipmi.set_fan_mode(fan_mode)
        mock_ipmi_exec.assert_called_with(["raw", "0x30", "0x45", "0x01", f"0x{fan_mode:02x}"])
        assert mock_ipmi_exec.call_count == 1
        mock_time_sleep.assert_called_with(my_ipmi.config.fan_mode_delay)
        assert mock_time_sleep.call_count == 1

    def test_set_fan_mode_logs_at_debug(self, mocker: MockerFixture) -> None:
        """Positive unit test for Ipmi.set_fan_mode() method (DEBUG logging). It contains the following steps:
        - mock Ipmi._exec_ipmitool, time.sleep and Log.msg
        - build a bare Ipmi via the _make_bare_ipmi helper with fan_mode_delay=0 and attach a DEBUG level Log
        - call my_ipmi.set_fan_mode(Ipmi.FULL_MODE)
        - ASSERT: Log.msg() is called once, i.e. the mode change is traced at DEBUG level
        - ASSERT: the logged message names the fan mode by name and by value
        """
        mock_ipmi_exec = MagicMock()
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec, fan_mode_delay=0)
        my_ipmi.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        mocker.patch("time.sleep", MagicMock())
        mock_msg = MagicMock()
        mocker.patch.object(my_ipmi.log, "msg", mock_msg)
        my_ipmi.set_fan_mode(Ipmi.FULL_MODE)
        assert mock_msg.call_count == 1
        assert "FULL (1)" in mock_msg.call_args.args[1]

    @pytest.mark.parametrize(
        "fan_mode, exception",
        [
            pytest.param(-1, ValueError, id="negative"),
            pytest.param(100, ValueError, id="out-of-range"),
        ],
    )
    def test_set_fan_mode_raises_on_invalid_mode(self, mocker: MockerFixture, fan_mode: int, exception: Any) -> None:
        """Negative unit test for Ipmi.set_fan_mode() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate) with
          fan_mode_delay=0
        - call my_ipmi.set_fan_mode(fan_mode) with an out-of-range value inside pytest.raises
        - ASSERT: the raised exception type equals ValueError
        """
        mock_ipmi_exec = MagicMock()
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec, fan_mode_delay=0)
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_fan_mode(fan_mode)
        assert cm.type == exception

    @pytest.mark.parametrize(
        "zone, level",
        [
            pytest.param(0, 0, id="zone0-min"),
            pytest.param(0, 50, id="zone0-mid"),
            pytest.param(0, 100, id="zone0-max"),
            pytest.param(1, 0, id="zone1-min"),
            pytest.param(1, 50, id="zone1-mid"),
            pytest.param(1, 100, id="zone1-max"),
        ],
    )
    def test_set_fan_level_invokes_ipmitool_and_sleeps(self, mocker: MockerFixture, zone: int, level: int) -> None:
        """Positive unit test for Ipmi.set_fan_level() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool and time.sleep
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate) with
          fan_level_delay=0
        - call my_ipmi.set_fan_level(zone, level)
        - ASSERT: _exec_ipmitool was called with ["raw", "0x30", "0x70", "0x66", "0x01",
          f"0x{zone:02x}", f"0x{level:02x}"]
        - ASSERT: _exec_ipmitool was called exactly once
        - ASSERT: time.sleep was called with config.fan_level_delay
        - ASSERT: time.sleep was called exactly once
        """
        mock_ipmi_exec = MagicMock()
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec, fan_level_delay=0)
        mock_time_sleep = MagicMock()
        mocker.patch("time.sleep", mock_time_sleep)
        my_ipmi.set_fan_level(zone, level)
        mock_ipmi_exec.assert_called_with(
            ["raw", "0x30", "0x70", "0x66", "0x01", f"0x{zone:02x}", f"0x{level:02x}"]
        )
        assert mock_ipmi_exec.call_count == 1
        mock_time_sleep.assert_called_with(my_ipmi.config.fan_level_delay)
        assert mock_time_sleep.call_count == 1

    @pytest.mark.parametrize(
        "zone, level",
        [
            pytest.param(Ipmi.CPU_ZONE, -1, id="level-negative"),
            pytest.param(Ipmi.CPU_ZONE, 101, id="level-over-100"),
            pytest.param(-1, 50, id="zone-negative"),
            pytest.param(101, 50, id="zone-over-100"),
        ],
    )
    def test_set_fan_level_raises_on_invalid_zone_or_level(self, mocker: MockerFixture, zone: int, level: int) -> None:
        """Negative unit test for Ipmi.set_fan_level() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate) with
          fan_level_delay=0
        - call my_ipmi.set_fan_level(zone, level) with an out-of-range zone or level inside pytest.raises
        - ASSERT: the raised exception type equals ValueError
        """
        mock_ipmi_exec = MagicMock()
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec, fan_level_delay=0)
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_fan_level(zone, level)
        assert cm.type is ValueError

    @pytest.mark.parametrize(
        "zones, level",
        [
            pytest.param([0], 0, id="1zone-level0"),
            pytest.param([0, 1], 50, id="2zones-level50"),
            pytest.param([0, 1, 2], 100, id="3zones-level100"),
        ],
    )
    def test_set_multiple_fan_levels_invokes_ipmitool_per_zone(self, mocker: MockerFixture, zones: List[int],
                                                                level: int) -> None:
        """Positive unit test for Ipmi.set_multiple_fan_levels() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool and time.sleep
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate) with
          fan_level_delay=0
        - call my_ipmi.set_multiple_fan_levels(zones, level)
        - ASSERT: _exec_ipmitool was called once per zone with the expected raw command list
        - ASSERT: _exec_ipmitool was called exactly len(zones) times
        - ASSERT: time.sleep was called with config.fan_level_delay
        - ASSERT: time.sleep was called exactly once (regardless of zone count)
        """
        mock_ipmi_exec = MagicMock()
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec, fan_level_delay=0)
        mock_time_sleep = MagicMock()
        mocker.patch("time.sleep", mock_time_sleep)
        my_ipmi.set_multiple_fan_levels(zones, level)
        # pylint: disable=duplicate-code
        calls = []
        for z in zones:
            calls.append(call(["raw", "0x30", "0x70", "0x66", "0x01", f"0x{z:02x}", f"0x{level:02x}"]))
        # pylint: enable=duplicate-code
        mock_ipmi_exec.assert_has_calls(calls)
        assert mock_ipmi_exec.call_count == len(zones)
        mock_time_sleep.assert_called_with(my_ipmi.config.fan_level_delay)
        assert mock_time_sleep.call_count == 1

    @pytest.mark.parametrize(
        "zones, level",
        [
            pytest.param([0], -1, id="level-negative"),
            pytest.param([0], 101, id="level-over-100"),
            pytest.param([-1], 50, id="zone-negative"),
            pytest.param([101], 50, id="zone-over-100"),
            pytest.param([0, -1], 50, id="zone-negative-in-list"),
            pytest.param([101, 0], 50, id="zone-over-100-in-list"),
        ],
    )
    def test_set_multiple_fan_levels_raises_on_invalid_zone_or_level(self, mocker: MockerFixture, zones: List[int],
                                                                      level: int) -> None:
        """Negative unit test for Ipmi.set_multiple_fan_levels() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate) with
          fan_level_delay=0
        - call my_ipmi.set_multiple_fan_levels(zones, level) with an out-of-range zone or level inside
          pytest.raises
        - ASSERT: the raised exception type equals ValueError
        """
        mock_ipmi_exec = MagicMock()
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec, fan_level_delay=0)
        with pytest.raises(ValueError) as cm:
            my_ipmi.set_multiple_fan_levels(zones, level)
        assert cm.type is ValueError

    @pytest.mark.parametrize(
        "zone, expected_level",
        [
            pytest.param(Ipmi.CPU_ZONE, 0, id="cpu-level0"),
            pytest.param(Ipmi.CPU_ZONE, 50, id="cpu-level50"),
            pytest.param(Ipmi.CPU_ZONE, 100, id="cpu-level100"),
            pytest.param(Ipmi.HD_ZONE, 0, id="hd-level0"),
            pytest.param(Ipmi.HD_ZONE, 50, id="hd-level50"),
            pytest.param(Ipmi.HD_ZONE, 100, id="hd-level100"),
        ],
    )
    def test_get_fan_level_returns_parsed_level(self, mocker: MockerFixture, zone: int, expected_level: int) -> None:
        """Positive unit test for Ipmi.get_fan_level() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool to return CompletedProcess with stdout=" {level:x}"
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate)
        - call my_ipmi.get_fan_level(zone)
        - ASSERT: get_fan_level() returns the expected parsed level value
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {expected_level:x}")
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec)
        assert my_ipmi.get_fan_level(zone) == expected_level

    @pytest.mark.parametrize(
        "zone, level",
        [
            pytest.param(Ipmi.CPU_ZONE, "NA", id="cpu-na"),
            pytest.param(Ipmi.CPU_ZONE, "", id="cpu-empty"),
            pytest.param(Ipmi.HD_ZONE, "NA", id="hd-na"),
            pytest.param(Ipmi.HD_ZONE, "", id="hd-empty"),
            pytest.param(-1, "NA", id="zone-negative"),
            pytest.param(200, "", id="zone-out-of-range"),
        ],
    )
    def test_get_fan_level_raises_on_invalid_output(self, mocker: MockerFixture, zone: int, level: str) -> None:
        """Negative unit test for Ipmi.get_fan_level() method. It contains the following steps:
        - mock Ipmi._exec_ipmitool to return CompletedProcess with invalid stdout (e.g. "NA" or "")
        - build a bare Ipmi via the _make_bare_ipmi helper (absorbs Ipmi.__new__/print boilerplate)
        - call my_ipmi.get_fan_level(zone) inside pytest.raises (covers invalid output and invalid zone)
        - ASSERT: the raised exception type equals ValueError
        """
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=f" {level}")
        my_ipmi = _make_bare_ipmi(mocker, mock_ipmi_exec)
        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_level(zone)
        assert cm.type is ValueError

    @pytest.mark.parametrize(
        "exception",
        [
            pytest.param(RuntimeError, id="runtime-error"),
            pytest.param(FileNotFoundError, id="file-not-found"),
        ],
    )
    def test_methods_propagate_underlying_ipmitool_exceptions(self, exception: Any) -> None:
        """Negative unit test for Ipmi.get_fan_mode(), Ipmi.set_fan_mode(), Ipmi.set_fan_level(),
        Ipmi.set_multiple_fan_levels(), Ipmi.get_fan_level() methods. It contains the following steps:
        - wire a raising_exec callable that raises the parameterized exception type for every ipmitool call
        - build a bare Ipmi via Ipmi.__new__ with a GenericPlatform("test", raising_exec) and
          create_ipmi_config(fan_mode_delay=0, fan_level_delay=0), sudo=False
        - call get_fan_mode(), set_fan_mode(FULL_MODE), set_fan_level(CPU_ZONE, 50), set_multiple_fan_levels([0], 50),
          and get_fan_level(CPU_ZONE), each inside pytest.raises
        - ASSERT: get_fan_mode raises the expected exception type
        - ASSERT: set_fan_mode raises the expected exception type
        - ASSERT: set_fan_level raises the expected exception type
        - ASSERT: set_multiple_fan_levels raises the expected exception type
        - ASSERT: get_fan_level raises the expected exception type
        """

        def raising_exec(args: List[str]) -> subprocess.CompletedProcess:
            raise exception

        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.platform = GenericPlatform("test", raising_exec)
        my_ipmi.config = create_ipmi_config(fan_mode_delay=0, fan_level_delay=0)
        my_ipmi.sudo = False

        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_mode()
        assert cm.type == exception

        with pytest.raises(Exception) as cm:
            my_ipmi.set_fan_mode(Ipmi.FULL_MODE)
        assert cm.type == exception

        with pytest.raises(Exception) as cm:
            my_ipmi.set_fan_level(Ipmi.CPU_ZONE, 50)
        assert cm.type == exception

        with pytest.raises(Exception) as cm:
            my_ipmi.set_multiple_fan_levels([0], 50)
        assert cm.type == exception

        with pytest.raises(Exception) as cm:
            my_ipmi.get_fan_level(Ipmi.CPU_ZONE)
        assert cm.type == exception

    def test_init_never_starts_platform(self, mocker: MockerFixture, td: TestData) -> None:
        """Positive unit test for Ipmi.__init__() method (fan control is not acquired here). It contains the
        following steps:
        - mock builtins.print, Ipmi._exec_ipmitool (returns BMC info on the info call),
          smfc.platform.Platform.start, and the td fixture's create_command_file (fake ipmitool binary)
        - build an ipmi Config via create_ipmi_config(command=...)
        - call Ipmi(my_log, cfg, False)
        - ASSERT: Platform.start() is not called at all - acquiring fan control belongs to Service.run(), which
          knows the controlled zone list and runs it after the DEBUG logging of the pre-change BMC state
        """
        command = td.create_command_file()
        mocker.patch("builtins.print", MagicMock())
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.side_effect = [
            subprocess.CompletedProcess([], returncode=0, stdout=SDR_READY_OUTPUT),
            subprocess.CompletedProcess([], returncode=0, stdout=BMC_INFO_OUTPUT),
        ]
        mocker.patch("smfc.Ipmi._exec_ipmitool", mock_ipmi_exec)
        mock_start = MagicMock()
        mocker.patch("smfc.platform.Platform.start", mock_start)
        cfg = create_ipmi_config(command=command)
        my_log = Log(Log.LOG_NONE, Log.LOG_STDOUT)
        Ipmi(my_log, cfg, False)
        assert mock_start.call_count == 0

    def test_init_bmc_init_timeout(self, mocker: MockerFixture, td: TestData) -> None:
        """Negative unit test for Ipmi.__init__() method (bmc_init_timeout override). It contains the following
        steps:
        - mock builtins.print, time.sleep (accumulates wait_time), Ipmi._exec_ipmitool (always raises
          RuntimeError("ipmitool error ...")), and the td fixture's create_command_file (fake ipmitool binary)
        - build an ipmi Config via create_ipmi_config(command=...)
        - call Ipmi(my_log, cfg, False, bmc_init_timeout=10.0) inside pytest.raises(RuntimeError)
        - ASSERT: wait_time stays below 20.0 (the override bounded the retry loop, well under the 180 s default)
        - ASSERT: wait_time is at least 10.0 (the loop did not exit before the override timeout)
        """
        wait_time: float = 0.0

        # pylint: disable=W0613
        def mocked_ipmi_exec(self, args: List[str]) -> subprocess.CompletedProcess:
            raise RuntimeError("ipmitool error (1): error.")
        # pylint: enable=W0613

        def mocked_time_sleep(second: float) -> None:
            nonlocal wait_time
            wait_time += second

        command = td.create_command_file()
        mocker.patch("builtins.print", MagicMock())
        mocker.patch("time.sleep", mocked_time_sleep)
        mocker.patch("smfc.Ipmi._exec_ipmitool", mocked_ipmi_exec)
        cfg = create_ipmi_config(command=command)
        my_log = Log(Log.LOG_NONE, Log.LOG_STDOUT)
        with pytest.raises(RuntimeError):
            Ipmi(my_log, cfg, False, bmc_init_timeout=10.0)
        # Loop sleeps in 5 s steps; with timeout=10 it should exit at 10..15 s, far below 180 s.
        assert wait_time < 20.0, "bmc_init_timeout did not bound the retry loop"
        assert wait_time >= 10.0, "bmc_init_timeout exited too early"

    @pytest.mark.parametrize(
        "sdr_output, expected",
        [
            # Realistic complete `sdr` captures.
            pytest.param(SDR_READY_OUTPUT, True, id="settled"),
            pytest.param(SDR_PREFIXED_READY_OUTPUT, True, id="settled-prefixed-names"),
            pytest.param(SDR_NOTREADY_OUTPUT, False, id="window-no-reading"),
            pytest.param(SDR_NOTREADY_DISABLED_OUTPUT, False, id="window-disabled"),
            pytest.param(SDR_NO_FAN_OUTPUT, False, id="no-fan-sensor-at-all"),
            # Fan naming conventions: `FAN` anywhere in the name marks a fan sensor.
            pytest.param("FAN1 | 500 RPM | ok\n", True, id="name-bare-digit"),
            pytest.param("FANA | 500 RPM | ok\n", True, id="name-bare-letter"),
            pytest.param("CPU_FAN1 | 840 RPM | ok\n", True, id="name-prefix-underscore-cpu"),
            pytest.param("SYS_FAN1 | 980 RPM | ok\n", True, id="name-prefix-underscore-sys"),
            pytest.param("REAR_FAN1 | 980 RPM | ok\n", True, id="name-prefix-underscore-rear"),
            pytest.param("SYSFAN1 | 980 RPM | ok\n", True, id="name-prefix-no-separator-sys"),
            pytest.param("CPUFAN1 | 840 RPM | ok\n", True, id="name-prefix-no-separator-cpu"),
            pytest.param("FAN_CPU1 | 840 RPM | ok\n", True, id="name-suffix-underscore"),
            pytest.param("Fan Speed | 1200 RPM | ok\n", True, id="name-space-separator"),
            pytest.param("fan1 | 500 RPM | ok\n", True, id="name-lower-case"),
            pytest.param("Fan1 | 500 RPM | ok\n", True, id="name-mixed-case"),
            # The same naming conventions in state `ns` stay not ready.
            pytest.param("FAN1 | no reading | ns\n", False, id="ns-bare"),
            pytest.param("CPU_FAN1 | no reading | ns\n", False, id="ns-prefix-underscore"),
            pytest.param("SYSFAN1 | disabled | ns\n", False, id="ns-prefix-no-separator"),
            pytest.param("FAN_CPU1 | disabled | ns\n", False, id="ns-suffix-underscore"),
            pytest.param("fan1 | Not Readable | ns\n", False, id="ns-lower-case"),
            # Any state other than `ns` counts: a fan booting into an alarm state must not hold the gate.
            pytest.param("FAN1 | 100 RPM | nc\n", True, id="state-non-critical"),
            pytest.param("FAN1 | 0 RPM | cr\n", True, id="state-critical"),
            pytest.param("FAN1 | 0 RPM | nr\n", True, id="state-non-recoverable"),
            pytest.param("FAN1 | 500 RPM | NS\n", False, id="state-ns-upper-case"),
            # A live fan among `ns` siblings is enough; an `ns` fan among live siblings is not decisive.
            pytest.param("FAN1 | no reading | ns\nFAN2 | 500 RPM | ok\n", True, id="mixed-one-live-fan"),
            pytest.param("CPU Temp | 45 degrees C | ok\nFAN1 | no reading | ns\n", False, id="mixed-live-non-fan"),
            # Malformed input.
            pytest.param("garbage line without pipes\nFAN1 | 500 RPM | ok\n", True, id="malformed-then-fan-ok"),
            pytest.param("FAN1 | 500 RPM\n", False, id="too-few-fields"),
            pytest.param("OTHER Temp | 40 degrees C | ok\n", False, id="no-fan-sensor"),
            pytest.param("", False, id="empty"),
        ],
    )
    def test_fan_sensors_ready(self, sdr_output: str, expected: bool) -> None:
        """Unit test for Ipmi._fan_sensors_ready(). It contains the following steps:
        - call Ipmi._fan_sensors_ready(sdr_output) on representative `ipmitool sdr` outputs
        - ASSERT: True when at least one sensor carrying `FAN` in its name reports a live reading,
          for every fan naming convention (`FAN1`, `FANA`, `CPU_FAN1`, `SYSFAN1`, `FAN_CPU1`, ...)
        - ASSERT: the match is case insensitive and independent of the reading column, so both
          `no reading | ns` and `disabled | ns` are not ready while `nc`/`cr`/`nr` are ready
        - ASSERT: False when no fan sensor is live, including a complete `sdr` list without fans
        - ASSERT: malformed lines (fewer than 3 fields) are skipped and an empty output returns False
        """
        assert Ipmi._fan_sensors_ready(sdr_output) is expected  # pylint: disable=protected-access

    @pytest.mark.parametrize(
        "settles, expected_waits, expected_sdr_calls",
        [
            pytest.param(True, 10.0, 3, id="fan-settles-after-two-waits"),
            pytest.param(False, 30.0, 7, id="fan-never-settles-hits-timeout"),
        ],
    )
    def test_init_waits_for_fan_sensors(self, mocker: MockerFixture, td: TestData, settles: bool,
                                        expected_waits: float, expected_sdr_calls: int) -> None:
        """Unit test for Ipmi.__init__() fan-subsystem readiness gate. It contains the following steps:
        - mock builtins.print, time.sleep (accumulates wait_time), and Ipmi._exec_ipmitool so that
          `sdr` reports `ns` (not ready) until it settles or the timeout hits
        - call Ipmi(my_log, cfg, False, bmc_init_timeout=30.0)
        - ASSERT: the loop waits in 5 s steps until a fan sensor reports live data (settles case) or the
          bmc_init_timeout is reached (never-settles case, which proceeds without raising)
        - ASSERT: the accumulated wait_time and number of `sdr` calls match the expected retry counts
        """
        wait_time: float = 0.0
        sdr_calls = 0

        # pylint: disable=W0613
        def mocked_ipmi_exec(self, args: List[str]) -> subprocess.CompletedProcess:
            nonlocal sdr_calls
            if args == ["sdr"]:
                sdr_calls += 1
                if settles and sdr_calls >= 3:
                    return subprocess.CompletedProcess([], returncode=0, stdout=SDR_READY_OUTPUT)
                return subprocess.CompletedProcess([], returncode=0, stdout=SDR_NOTREADY_OUTPUT)
            # The only other call in __init__ is `bmc info` (GenericPlatform.start() is a no-op).
            return subprocess.CompletedProcess([], returncode=0, stdout=BMC_INFO_OUTPUT)
        # pylint: enable=W0613

        def mocked_time_sleep(second: float) -> None:
            nonlocal wait_time
            wait_time += second

        command = td.create_command_file()
        mocker.patch("builtins.print", MagicMock())
        mocker.patch("time.sleep", mocked_time_sleep)
        mocker.patch("smfc.Ipmi._exec_ipmitool", mocked_ipmi_exec)
        cfg = create_ipmi_config(command=command)
        my_log = Log(Log.LOG_INFO, Log.LOG_STDOUT)
        my_ipmi = Ipmi(my_log, cfg, False, bmc_init_timeout=30.0)
        assert my_ipmi.bmc_product_name == "X11SCH-LN4F"
        assert wait_time == expected_waits
        assert sdr_calls == expected_sdr_calls

    @pytest.mark.parametrize("stderr, expected", [
        pytest.param("Unable to send RAW command (channel=0x0 netfn=0x2e lun=0x0 cmd=0x4 rsp=0xc1): "
                     "Invalid command", 0xC1, id="0xc1-invalid-command"),
        pytest.param("Unable to send RAW command (channel=0x0 netfn=0x30 lun=0x0 cmd=0x70 rsp=0xd4): "
                     "Insufficient privilege level", 0xD4, id="0xd4-lockdown"),
        pytest.param("Unable to send RAW command (rsp=0xCC): Invalid data field in request", 0xCC,
                     id="uppercase-hex"),
        pytest.param("Could not open device at /dev/ipmi0: No such file or directory", None, id="no-device"),
        pytest.param("Error: Unable to establish IPMI v2 / RMCP+ session", None, id="no-session"),
        pytest.param("", None, id="empty"),
    ])
    def test_parse_completion_code(self, stderr: str, expected: Any) -> None:
        """Positive unit test for the parse_completion_code() function. It contains the following steps:
        - call parse_completion_code() with ipmitool stderr texts that do and do not carry an IPMI
          completion code
        - ASSERT: the completion code is parsed out of the `rsp=0x..` field, in either letter case
        - ASSERT: None is returned when ipmitool failed for a reason that is not a BMC rejection, so an
          unreachable BMC can never be mistaken for a board that answered 0xC1. That distinction is what the
          X14/H14 stack probe rests on: guessing the stack executes a duty write instead of returning an error
        """
        f = "TestIpmi.test_parse_completion_code"
        assert parse_completion_code(stderr) == expected, f"{f}: {stderr!r}"

    # pylint: disable=protected-access
    def test_exec_ipmitool_carries_the_completion_code(self, mocker: MockerFixture) -> None:
        """Negative unit test for Ipmi._exec_ipmitool() method. It contains the following steps:
        - mock subprocess.run to fail with an ipmitool error line carrying `rsp=0xc1`
        - build a bare Ipmi and call Ipmi._exec_ipmitool(["raw", "0x2e"]) inside pytest.raises
        - ASSERT: the raised IpmiError carries the parsed completion code, so callers can distinguish a
          rejected command from an unreachable BMC without matching the error message text - matching text
          would leave a latent trap, since a change to the wording would silently turn a fatal condition into
          a wrong-stack guess
        """
        f = "TestIpmi.test_exec_ipmitool_carries_the_completion_code"
        stderr = "Unable to send RAW command (channel=0x0 netfn=0x2e lun=0x0 cmd=0x4 rsp=0xc1): Invalid command"
        mocker.patch("subprocess.run", MagicMock(return_value=subprocess.CompletedProcess([], 1, stderr=stderr)))
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.config = create_ipmi_config(command="")
        my_ipmi.sudo = False
        with pytest.raises(IpmiError) as cm:
            my_ipmi._exec_ipmitool(["raw", "0x2e"])
        assert cm.value.completion_code == 0xC1, f"{f}: completion code"

    @pytest.mark.parametrize("timeout", [10, 0], ids=["timeout-10s", "timeout-disabled"])
    def test_exec_ipmitool_timeout(self, mocker: MockerFixture, timeout: int) -> None:
        """Negative unit test for Ipmi._exec_ipmitool() method. It contains the following steps:
        - mock subprocess.run to raise subprocess.TimeoutExpired, i.e. ipmitool did not finish in time
        - build a bare Ipmi with the parameterized `ipmitool_timeout` and call _exec_ipmitool()
        - ASSERT: subprocess.run receives `timeout=10` when the parameter is 10, and `timeout=None` when it
          is 0 - the sentinel selecting the pre-existing "wait indefinitely" behaviour
        - ASSERT: an expired timeout surfaces as an IpmiError, not as a subprocess exception, so every
          existing `except RuntimeError` handles it: the watchdog reports it as an unconfirmed control loss
          and the control loop logs it and retries, instead of the daemon parking inside a wedged
          /dev/ipmi0 with nothing regulating the fans
        - ASSERT: no completion code is attached, because the BMC returned nothing to parse
        """
        f = "TestIpmi.test_exec_ipmitool_timeout"
        mock_run = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="ipmitool", timeout=timeout))
        mocker.patch("subprocess.run", mock_run)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_ipmi.config = create_ipmi_config(command="/usr/bin/ipmitool", ipmitool_timeout=timeout)
        my_ipmi.sudo = False
        with pytest.raises(IpmiError) as cm:
            my_ipmi._exec_ipmitool(["raw", "0x30", "0x45", "0x00"])
        assert mock_run.call_args.kwargs["timeout"] == (timeout or None), f"{f}: timeout= passed through"
        assert "timed out" in str(cm.value), f"{f}: message: {cm.value}"
        assert cm.value.completion_code is None, f"{f}: no completion code"
    # pylint: enable=protected-access


# End.
