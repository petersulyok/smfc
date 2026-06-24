#!/usr/bin/env python3
#
#   test_hdfc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.HdFc() class.
#
import os
import random
import subprocess
import time
from typing import List, Any
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log
from smfc.config import Config
from .test_data import TestData, create_hd_config
from .test_fc_helpers import assert_fc_base_contract, build_hd_fc, make_bare_hd_fc

# Field order for the parametrized explicit-configuration init test (base fields + HD-specific sb_limit/sudo).
INIT_FIELDS = ["count", "ipmi_zone", "temp_calc", "steps", "sensitivity", "polling", "min_temp", "max_temp",
               "min_level", "max_level", "smoothing", "sb_limit", "sudo"]


class TestHdFc:
    """Unit test class for smfc.HdFc() class"""

    @pytest.mark.parametrize(
        INIT_FIELDS,
        [
            pytest.param(1, [0], Config.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 1, 2, True, id="1hd-zone0-min-sudo"),
            pytest.param(2, [1], Config.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 3, 2, False, id="2hd-zone1-avg-smooth3"),
            pytest.param(4, [2], Config.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 1, 4, True, id="4hd-zone2-avg-sudo"),
            pytest.param(8, [3], Config.CALC_MAX, 4, 2, 2, 32, 48, 35, 100, 1, 6, False, id="8hd-zone3-max"),
        ],
    )
    def test_init_sets_attributes_from_config(self, mocker: MockerFixture, td: TestData, count: int,
                                              ipmi_zone: List[int], temp_calc: int, steps: int, sensitivity: float,
                                              polling: float, min_temp: float, max_temp: float, min_level: int,
                                              max_level: int, smoothing: int, sb_limit: int, sudo: bool):
        """Positive unit test for HdFc.__init__() with an explicit configuration. It contains the steps:
        - build an HdFc via the shared builder (udev/hwmon/smartctl mocked) with the standby guard enabled
        - ASSERT: the base-class contract (log/ipmi refs, name, count, config fields)
        - ASSERT: the HD-specific attributes (sudo, hd_names, smartctl_path, hwmon paths, device_names copy)
        - ASSERT: the standby-guard config is wired when count > 1
        """
        cfg_values = {"ipmi_zone": ipmi_zone, "temp_calc": temp_calc, "steps": steps, "sensitivity": sensitivity,
                      "polling": polling, "min_temp": min_temp, "max_temp": max_temp, "min_level": min_level,
                      "max_level": max_level, "smoothing": smoothing}
        cmd_smart = td.create_command_file('echo "ACTIVE"')
        h = build_hd_fc(mocker, td, count=count, sudo=sudo, smartctl_path=cmd_smart, standby_guard_enabled=True,
                        standby_hd_limit=sb_limit, **cfg_values)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=cfg_values, log=h.log, ipmi=h.ipmi)
        assert h.fc.sudo == sudo
        assert h.fc.hd_device_names == td.hd_name_list
        assert h.fc.config.smartctl_path == cmd_smart
        assert h.fc.hwmon_path == td.hd_files
        # device_names() exposes a defensive copy of hd_device_names for the snapshot/exporter path.
        names = h.fc.device_names()
        assert names == td.hd_name_list
        assert names is not h.fc.hd_device_names
        if count > 1:
            assert h.fc.config.standby_hd_limit == sb_limit
            assert h.fc.config.standby_guard_enabled is True

    def test_init_applies_defaults(self, mocker: MockerFixture, td: TestData):
        """Positive unit test for HdFc.__init__() with default configuration values. It contains the steps:
        - build an HdFc from a default config (only enabled + hd_names set)
        - ASSERT: the base-class contract holds with the HD default config values (Config.DV_HD_*)
        - ASSERT: the HD-specific defaults (sudo False, default smartctl_path, hd_names, hwmon paths)
        """
        count = 4
        expected = {"ipmi_zone": [Config.HD_ZONE], "temp_calc": Config.CALC_AVG, "steps": Config.DV_HD_STEPS,
                    "sensitivity": Config.DV_HD_SENSITIVITY, "polling": Config.DV_HD_POLLING,
                    "min_temp": Config.DV_HD_MIN_TEMP, "max_temp": Config.DV_HD_MAX_TEMP,
                    "min_level": Config.DV_HD_MIN_LEVEL, "max_level": Config.DV_HD_MAX_LEVEL,
                    "smoothing": Config.DV_HD_SMOOTHING}
        h = build_hd_fc(mocker, td, count=count, sudo=False)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=expected, log=h.log, ipmi=h.ipmi)
        assert h.fc.sudo is False
        assert h.fc.config.smartctl_path == Config.DV_HD_SMARTCTL_PATH
        assert h.fc.hd_device_names == td.hd_name_list
        assert h.fc.hwmon_path == td.hd_files

    @pytest.mark.parametrize(
        "data_count, names, standby_hd_limit",
        [
            # hd_names= not specified (no devices -> count <= 0)
            pytest.param(0, None, 2, id="no-names"),
            # standby_hd_limit < 0
            pytest.param(2, None, -1, id="limit-negative"),
            # standby_hd_limit > count
            pytest.param(2, None, 4, id="limit-exceeds-count"),
            # Device name cannot be reached in the udev database
            pytest.param(1, ["raise"], 4, id="unreachable-name"),
        ],
    )
    def test_init_rejects_invalid_config(self, mocker: MockerFixture, td: TestData, data_count: int, names,
                                         standby_hd_limit: int):
        """Negative unit test for HdFc.__init__() with invalid configuration. It contains the steps:
        - build an HdFc via the shared builder with an invalid device list or standby_hd_limit
        - ASSERT: construction raises ValueError (no devices, bad standby limit, or unreachable device)
        """
        with pytest.raises(ValueError):
            build_hd_fc(mocker, td, count=data_count, names=names, standby_guard_enabled=True,
                        standby_hd_limit=standby_hd_limit)

    @pytest.mark.parametrize(
        "hd_names",
        [
            pytest.param(["/dev/nvme0n1"], id="nvme-only"),
            pytest.param(["/dev/sda", "/dev/nvme1n1"], id="mixed-sata-nvme"),
        ],
    )
    def test_init_rejects_nvme_names(self, mocker: MockerFixture, td: TestData, hd_names: List[str]):
        """Negative unit test for HdFc.__init__() with NVMe device names. It contains the steps:
        - build an HdFc via the shared builder with NVMe names in hd_names
        - ASSERT: construction raises ValueError (NVMe drives are not allowed in the HD fan controller)
        """
        with pytest.raises(ValueError):
            build_hd_fc(mocker, td, count=1, names=hd_names)

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "args, sudo",
        [
            pytest.param(["-a", "/dev/sda"], True, id="read-all-sudo"),
            pytest.param(["-a", "/dev/sda"], False, id="read-all"),
            pytest.param(["-i", "-n", "standby", "/dev/sda"], True, id="standby-check-sudo"),
            pytest.param(["-i", "-n", "standby", "/dev/sda"], False, id="standby-check"),
            pytest.param(["-s", "/dev/sda"], True, id="set-standby-sudo"),
            pytest.param(["-s", "/dev/sda"], False, id="set-standby"),
        ],
    )
    def test_exec_smartctl_builds_command(self, mocker: MockerFixture, args: List[str], sudo: bool):
        """Positive unit test for HdFc._exec_smartctl(). It contains the steps:
        - build a bare HdFc with a fixed smartctl_path and sudo flag
        - mock subprocess.run() and call _exec_smartctl()
        - ASSERT: subprocess.run() is called exactly once with the expected (sudo + path + args) argument list
        """
        fc = make_bare_hd_fc(config=create_hd_config(smartctl_path="smartctl"), sudo=sudo)
        mock_run = MagicMock(return_value=subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""))
        mocker.patch("subprocess.run", mock_run)
        fc._exec_smartctl(args)
        expected_args = (["sudo"] if sudo else []) + [fc.config.smartctl_path] + args
        mock_run.assert_called_with(expected_args, capture_output=True, check=False, text=True)
        assert mock_run.call_count == 1

    @pytest.mark.parametrize(
        "smartctl_command, sudo, rc, exception",
        [
            pytest.param("/nonexistent/command", False, 0, FileNotFoundError, id="command-not-found"),
            pytest.param("", True, 1, RuntimeError, id="sudo-error"),
        ],
    )
    def test_exec_smartctl_raises_on_errors(self, mocker: MockerFixture, smartctl_command: str, sudo: bool, rc: int,
                                            exception: Any):
        """Negative unit test for HdFc._exec_smartctl() error handling. It contains the steps:
        - build a bare HdFc with the given smartctl_path and sudo flag
        - mock subprocess.run() to report a sudo error when a non-zero return code is requested
        - ASSERT: _exec_smartctl() raises the matching exception (FileNotFoundError missing command / RuntimeError sudo)
        """
        if rc:
            sudo_err = subprocess.CompletedProcess([], returncode=rc, stderr="sudo: smartctl: command not found")
            mocker.patch("subprocess.run", MagicMock(return_value=sudo_err))
        fc = make_bare_hd_fc(config=create_hd_config(smartctl_path=smartctl_command), sudo=sudo)
        with pytest.raises(exception):
            fc._exec_smartctl(["-a", "/dev/sda"])

    @pytest.mark.parametrize(
        "count, temperatures",
        [
            pytest.param(1, [32], id="1hd"),
            pytest.param(2, [33, 34], id="2hd"),
            pytest.param(4, [33, 34, 35, 38], id="4hd"),
            pytest.param(8, [33, 34, 35, 38, 36, 37, 31, 30], id="8hd"),
        ],
    )
    def test_get_nth_temp_reads_hwmon(self, td: TestData, count: int, temperatures: List[float]):
        """Positive unit test for HdFc._get_nth_temp() over HWMON. It contains the steps:
        - create HD hwmon test data with fixed per-device temperatures
        - build a bare HdFc with hwmon_path set to those files
        - ASSERT: _get_nth_temp(i) returns the temperature written to each device's hwmon file
        """
        td.create_hd_data(count, temperatures)
        fc = make_bare_hd_fc(hwmon_path=td.hd_files)
        for i in range(count):
            assert fc._get_nth_temp(i) == temperatures[i]

    @pytest.mark.parametrize(
        "count, temperatures",
        [
            pytest.param(1, [32], id="1hd"),
            pytest.param(2, [33, 34], id="2hd"),
            pytest.param(4, [33, 34, 35, 38], id="4hd"),
            pytest.param(8, [33, 34, 35, 38, 36, 37, 31, 30], id="8hd"),
        ],
    )
    def test_get_nth_temp_reads_smartctl(self, mocker: MockerFixture, td: TestData, count: int,
                                         temperatures: List[float]):
        """Positive unit test for HdFc._get_nth_temp() over the smartctl fallback (empty hwmon path). The steps:
        - build a bare HdFc with empty hwmon paths so the smartctl branch is used
        - mock _exec_smartctl() to return SCSI/SATA temperature output for each device
        - ASSERT: _get_nth_temp(i) parses the expected temperature from the smartctl output
        """
        # pylint: disable=line-too-long
        smartctl_output = [
            # SCSI disks
            "smartctl 7.3 2022-02-28 r5338 [x86_64-linux-6.1.0-32-amd64] (local build)\n"
            "Copyright (C) 2002-22, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "Current Drive Temperature:     XX C\n",
            # SATA SMART attributes 1
            "smartctl 7.3 2022-02-28 r5338 [x86_64-linux-6.1.0-32-amd64] (local build)\n"
            "Copyright (C) 2002-22, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "190 Airflow_Temperature_Cel 0x0032   075   045   000    Old_age   Always       -       XX\n",
            # SATA SMART attributes 2
            "smartctl 7.3 2022-02-28 r5338 [x86_64-linux-6.1.0-32-amd64] (local build)\n"
            "Copyright (C) 2002-22, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "194 Temperature_Celsius     0x0002   232   232   000    Old_age   Always       -       XX (Min/Max 17/45)\n",
        ]
        # pylint: enable=line-too-long
        td.create_hd_data(count, temperatures)
        fc = make_bare_hd_fc(count=count, hd_device_names=td.hd_name_list, hwmon_path=[""] * count)
        mock_exec = MagicMock()
        mocker.patch("smfc.HdFc._exec_smartctl", mock_exec)
        for i in range(count):
            s = smartctl_output[random.randint(0, 2)].replace("XX", str(temperatures[i]))
            mock_exec.return_value = subprocess.CompletedProcess([], returncode=0, stdout=s)
            assert fc._get_nth_temp(i) == temperatures[i]

    @pytest.mark.parametrize(
        "operation, exception",
        [
            pytest.param(0, FileNotFoundError, id="hwmon-missing-file"),
            pytest.param(1, IndexError, id="hwmon-index-overflow"),
            pytest.param(2, ValueError, id="hwmon-invalid-value"),
            pytest.param(3, FileNotFoundError, id="smartctl-missing-command"),
            pytest.param(4, IndexError, id="smartctl-index-overflow"),
            pytest.param(5, ValueError, id="smartctl-no-temperature"),
        ],
    )
    def test_get_nth_temp_raises_on_io_errors(self, mocker: MockerFixture, td: TestData, operation: int,
                                              exception: Any):
        """Negative unit test for HdFc._get_nth_temp() error handling (HWMON and smartctl). It contains the steps:
        - build a bare HdFc over a single device
        - trigger one HWMON or smartctl failure (missing file/command, index overflow, invalid/absent value)
        - ASSERT: _get_nth_temp() raises the matching exception
        """
        td.create_hd_data(1, [32])
        fc = make_bare_hd_fc(count=1, hd_device_names=td.hd_name_list, hwmon_path=td.hd_files)
        index = 0
        if operation == 0:
            fc.hwmon_path[0] = "/tmp/non_existent_dir/non_existent_file"
        elif operation == 1:
            index = 1000
        elif operation == 2:
            os.system('echo "invalid value" >' + fc.hwmon_path[0])
        elif operation == 3:
            fc.hwmon_path[0] = ""
            fc.config = create_hd_config(smartctl_path="/tmp/non_existent_dir/non_existent_file")
        elif operation == 4:
            fc.hwmon_path[0] = ""
            index = 1000
        else:
            fc.hwmon_path[0] = ""
            no_temp = subprocess.CompletedProcess([], returncode=0, stdout="invalid\ninvalid\ninvalid\n")
            mocker.patch("subprocess.run", MagicMock(return_value=no_temp))
        with pytest.raises(exception):
            fc._get_nth_temp(index)

    @pytest.mark.parametrize(
        "states, result",
        [
            pytest.param([True] * 8, "SSSSSSSS", id="all-standby"),
            pytest.param([False] * 8, "AAAAAAAA", id="all-active"),
            pytest.param([True, False, False, False, False, False, False, False], "SAAAAAAA", id="drive0-standby"),
            pytest.param([False, True, False, False, False, False, False, False], "ASAAAAAA", id="drive1-standby"),
            pytest.param([False, False, True, False, False, False, False, False], "AASAAAAA", id="drive2-standby"),
            pytest.param([False, False, False, True, False, False, False, False], "AAASAAAA", id="drive3-standby"),
            pytest.param([False, False, False, False, True, False, False, False], "AAAASAAA", id="drive4-standby"),
            pytest.param([False, False, False, False, False, True, False, False], "AAAAASAA", id="drive5-standby"),
            pytest.param([False, False, False, False, False, False, True, False], "AAAAAASA", id="drive6-standby"),
            pytest.param([False, False, False, False, False, False, False, True], "AAAAAAAS", id="drive7-standby"),
        ],
    )
    def test_get_standby_state_str(self, states: List[bool], result: str):
        """Positive unit test for HdFc.get_standby_state_str(). It contains the steps:
        - build a bare HdFc with the given standby_array_states
        - ASSERT: get_standby_state_str() renders S/A per drive matching the expected string
        """
        fc = make_bare_hd_fc(count=8, standby_array_states=states)
        assert fc.get_standby_state_str() == result

    @pytest.mark.parametrize(
        "states, in_standby",
        [
            pytest.param([True] * 8, 8, id="8-standby"),
            pytest.param([False, True, True, True, True, True, True, True], 7, id="7-standby-drive0-active"),
            pytest.param([True, False, True, True, True, True, True, True], 7, id="7-standby-drive1-active"),
            pytest.param([True, True, False, True, True, True, True, True], 7, id="7-standby-drive2-active"),
            pytest.param([True, True, True, False, True, True, True, True], 7, id="7-standby-drive3-active"),
            pytest.param([True, True, True, True, False, True, True, True], 7, id="7-standby-drive4-active"),
            pytest.param([True, True, True, True, True, False, True, True], 7, id="7-standby-drive5-active"),
            pytest.param([True, True, True, True, True, True, False, True], 7, id="7-standby-drive6-active"),
            pytest.param([True, True, True, True, True, True, True, False], 7, id="7-standby-drive7-active"),
            pytest.param([True, False, True, True, True, True, True, False], 6, id="6-standby"),
            pytest.param([True, False, True, True, False, True, True, False], 5, id="5-standby"),
            pytest.param([False, False, True, True, False, True, True, False], 4, id="4-standby"),
            pytest.param([False, False, True, False, False, True, True, False], 3, id="3-standby"),
            pytest.param([False, False, True, False, False, True, False, False], 2, id="2-standby"),
            pytest.param([False, False, False, False, False, True, False, False], 1, id="1-standby"),
            pytest.param([False] * 8, 0, id="0-standby"),
        ],
    )
    def test_check_standby_state_counts_standby(self, mocker: MockerFixture, td: TestData, states: List[bool],
                                                in_standby: int):
        """Positive unit test for HdFc.check_standby_state(). It contains the steps:
        - build a bare HdFc and mock _exec_smartctl() to report STANDBY/ACTIVE per drive
        - ASSERT: check_standby_state() returns the number of drives reported in STANDBY
        """
        standby_out = "Device is in STANDBY mode, exit(2)\n"
        active_out = "Power mode is:    ACTIVE or IDLE\n"
        results = [subprocess.CompletedProcess([], returncode=0, stdout=standby_out if s else active_out)
                   for s in states]
        td.create_hd_data(8)
        log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        fc = make_bare_hd_fc(count=8, hd_device_names=td.hd_name_list, hwmon_path=[""] * 8,
                             standby_array_states=[True] * 8, log=log)
        mocker.patch("smfc.HdFc._exec_smartctl", MagicMock(side_effect=iter(results)))
        assert fc.check_standby_state() == in_standby

    @pytest.mark.parametrize(
        "states, expected_calls",
        [
            pytest.param([False] * 8, 8, id="all-active-8-commands"),
            pytest.param([True, False, False, False, False, False, False, False], 7, id="1-standby-7-commands"),
            pytest.param([True, True, False, False, False, False, False, False], 6, id="2-standby-6-commands"),
            pytest.param([True, True, True, False, False, False, False, False], 5, id="3-standby-5-commands"),
            pytest.param([True, True, True, True, False, False, False, False], 4, id="4-standby-4-commands"),
            pytest.param([True, True, True, True, True, False, False, False], 3, id="5-standby-3-commands"),
            pytest.param([True, True, True, True, True, True, False, False], 2, id="6-standby-2-commands"),
            pytest.param([True, True, True, True, True, True, True, False], 1, id="7-standby-1-command"),
            pytest.param([True] * 8, 0, id="all-standby-0-commands"),
        ],
    )
    def test_go_standby_state_sends_commands(self, mocker: MockerFixture, td: TestData, states: List[bool],
                                             expected_calls: int):
        """Positive unit test for HdFc.go_standby_state(). It contains the steps:
        - build a bare HdFc with the given standby_array_states and mock _exec_smartctl()
        - ASSERT: a standby command is issued only for each ACTIVE drive (expected_calls total)
        - ASSERT: the whole array ends up in STANDBY
        """
        td.create_hd_data(8)
        fc = make_bare_hd_fc(count=8, hd_device_names=td.hd_name_list, standby_array_states=states)
        mock_exec = MagicMock(return_value=subprocess.CompletedProcess([], returncode=0))
        mocker.patch("smfc.HdFc._exec_smartctl", mock_exec)
        fc.go_standby_state()
        assert mock_exec.call_count == expected_calls
        assert fc.standby_array_states == [True] * 8

    @pytest.mark.parametrize(
        "old_state, states, new_state",
        [
            pytest.param(False, [False] * 8, False, id="active-no-change"),
            pytest.param(True, [True] * 8, True, id="standby-no-change"),
            pytest.param(False, [False, True, False, False, False, False, False, False], True, id="to-standby-1drive"),
            pytest.param(False, [False, True, False, True, False, False, False, False], True, id="to-standby-2drives"),
            pytest.param(False, [True] * 8, True, id="to-standby-all"),
            pytest.param(True, [False] * 8, False, id="to-active-all"),
            pytest.param(True, [True, False, False, True, True, True, True, True], False, id="to-active-some"),
        ],
    )
    def test_run_standby_guard_updates_flag(self, mocker: MockerFixture, td: TestData, old_state: bool,
                                            states: List[bool], new_state: bool):
        """Positive unit test for HdFc.run_standby_guard(). It contains the steps:
        - build a bare HdFc with standby_hd_limit=1 and stub check_standby_state()/go_standby_state()
        - run_standby_guard() against the given prior standby_flag and array states
        - ASSERT: standby_flag transitions to the expected new state
        """
        td.create_hd_data(8)
        log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        config = create_hd_config(smartctl_path="/usr/sbin/smartctl", standby_hd_limit=1)
        fc = make_bare_hd_fc(config=config, count=8, hd_device_names=td.hd_name_list,
                             standby_array_states=states, log=log)
        fc.standby_flag = old_state
        fc.standby_change_timestamp = time.monotonic()
        fc.go_standby_state = MagicMock(name="go_standby_state")
        fc.check_standby_state = MagicMock(name="check_standby_state", return_value=states.count(True))
        mocker.patch("smfc.HdFc._exec_smartctl", MagicMock(return_value=subprocess.CompletedProcess([], returncode=0)))
        fc.run_standby_guard()
        assert fc.standby_flag == new_state

    def test_get_nth_temp_smartctl_debug_logging(self, mocker: MockerFixture):
        """Positive unit test for HdFc._get_nth_temp() smartctl fallback with DEBUG logging. It contains the steps:
        - build a bare HdFc at DEBUG log level with an empty hwmon path (smartctl branch)
        - mock _exec_smartctl() to return an SCSI temperature line
        - ASSERT: _get_nth_temp(0) returns the parsed temperature (37.0 C)
        """
        log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        scsi_out = subprocess.CompletedProcess([], returncode=0, stdout="Current Drive Temperature:     37 C\n")
        mocker.patch("smfc.HdFc._exec_smartctl", MagicMock(return_value=scsi_out))
        fc = make_bare_hd_fc(hwmon_path=[""], hd_device_names=["/dev/sda"], log=log)
        assert fc._get_nth_temp(0) == 37.0

    # pylint: enable=protected-access


# End.
