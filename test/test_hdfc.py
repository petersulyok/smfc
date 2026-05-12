#!/usr/bin/env python3
#
#   test_hdfc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.HdFc() class.
#
import random
import subprocess
import os
import time
from typing import List, Any
import pytest
import pyudev
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, HdFc
from smfc.config import Config
from .test_data import TestData, MockDevices, factory_mockdevice, create_hd_config


class TestHdFc:
    """Unit test class for smfc.HdFc() class"""

    @pytest.mark.parametrize(
        "count, ipmi_zone, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, sb_limit, "
        "sudo, error_str",
        [
            # 1 HD, zone 0, CALC_MIN, sudo=True
            (1, [0], Config.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, True, "HdFc.__init__() p1"),
            # 2 HDs, zone 1, CALC_AVG, sudo=False
            (2, [1], Config.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 2, False, "HdFc.__init__() p2"),
            # 4 HDs, zone 2, CALC_AVG, sudo=True
            (4, [2], Config.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 4, True, "HdFc.__init__() p3"),
            # 8 HDs, zone 3, CALC_MAX, sudo=False
            (8, [3], Config.CALC_MAX, 4, 2, 2, 32, 48, 35, 100, 6, False, "HdFc.__init__() p4"),
        ],
    )
    def test_init_p1(self, mocker: MockerFixture, count: int, ipmi_zone: List[int], temp_calc: int, steps: int,
                     sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                     max_level: int, sb_limit: int, sudo: bool, error_str: str):
        """Positive unit test for HdFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - initialize a Config, Log, Context, Ipmi, and HdFc classes
        - ASSERT: if the HdFc class attributes are different from values passed to __init__
        """
        my_td = TestData()
        cmd_smart = my_td.create_command_file('echo "ACTIVE"')
        my_td.create_hd_data(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
        mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
        mock_ipmi_exec = MagicMock()
        mock_ipmi_exec.return_value = subprocess.CompletedProcess([], returncode=0)
        mocker.patch("smfc.HdFc._exec_smartctl", mock_ipmi_exec)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.hd_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        cfg = create_hd_config(enabled=True, ipmi_zone=ipmi_zone, temp_calc=temp_calc, steps=steps,
                               sensitivity=sensitivity, polling=polling, min_temp=min_temp, max_temp=max_temp,
                               min_level=min_level, max_level=max_level, hd_names=my_td.hd_name_list,
                               smartctl_path=cmd_smart, standby_guard_enabled=True, standby_hd_limit=sb_limit)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_hdfc = HdFc(my_log, my_udevc, my_ipmi, cfg, sudo)
        assert my_hdfc.config.ipmi_zone == ipmi_zone, error_str
        assert my_hdfc.name == cfg.section, error_str
        assert my_hdfc.count == count, error_str
        assert my_hdfc.sudo == sudo, error_str
        assert my_hdfc.config.temp_calc == temp_calc, error_str
        assert my_hdfc.config.steps == steps, error_str
        assert my_hdfc.config.sensitivity == sensitivity, error_str
        assert my_hdfc.config.polling == polling, error_str
        assert my_hdfc.config.min_temp == min_temp, error_str
        assert my_hdfc.config.max_temp == max_temp, error_str
        assert my_hdfc.config.min_level == min_level, error_str
        assert my_hdfc.config.max_level == max_level, error_str
        assert my_hdfc.config.smoothing == 1, error_str
        assert my_hdfc.hd_device_names == my_td.hd_name_list, error_str
        assert my_hdfc.config.smartctl_path == cmd_smart, error_str
        assert my_hdfc.hwmon_path == my_td.hd_files, error_str
        if count > 1:
            assert my_hdfc.config.standby_hd_limit == sb_limit, error_str
            assert my_hdfc.config.standby_guard_enabled is True, error_str
        del my_td

    @pytest.mark.parametrize(
        "error_str",
        [
            # Default configuration values test
            ("HdFc.__init__() p5"),
        ],
    )
    def test_init_p2(self, mocker: MockerFixture, error_str: str):
        """Positive unit test for HdFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - initialize a Config, Log, Context, Ipmi, and HdFc classes
        - ASSERT: if the HdFc class attributes are different from the default configuration values
        """
        my_td = TestData()
        count = 4
        my_td.create_hd_data(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
        mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.hd_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        cfg = create_hd_config(enabled=True, hd_names=my_td.hd_name_list)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_hdfc = HdFc(my_log, my_udevc, my_ipmi, cfg, False)
        assert my_hdfc.log == my_log, error_str
        assert my_hdfc.ipmi == my_ipmi, error_str
        assert my_hdfc.config.ipmi_zone == [Config.HD_ZONE], error_str
        assert my_hdfc.name == cfg.section, error_str
        assert my_hdfc.count == count, error_str
        assert my_hdfc.sudo is False, error_str
        assert my_hdfc.config.temp_calc == Config.CALC_AVG, error_str
        assert my_hdfc.config.steps == Config.DV_HD_STEPS, error_str
        assert my_hdfc.config.sensitivity == Config.DV_HD_SENSITIVITY, error_str
        assert my_hdfc.config.polling == Config.DV_HD_POLLING, error_str
        assert my_hdfc.config.min_temp == Config.DV_HD_MIN_TEMP, error_str
        assert my_hdfc.config.max_temp == Config.DV_HD_MAX_TEMP, error_str
        assert my_hdfc.config.min_level == Config.DV_HD_MIN_LEVEL, error_str
        assert my_hdfc.config.max_level == Config.DV_HD_MAX_LEVEL, error_str
        assert my_hdfc.config.smoothing == Config.DV_HD_SMOOTHING, error_str
        assert my_hdfc.hd_device_names == my_td.hd_name_list, error_str
        assert my_hdfc.config.smartctl_path == Config.DV_HD_SMARTCTL_PATH, error_str
        assert my_hdfc.hwmon_path == my_td.hd_files, error_str
        del my_td

    @pytest.mark.parametrize(
        "count, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, sb_limit, error_str",
        [
            # hd_names not specified (count=0)
            (0, Config.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 2, "HdFc.__init__() n1"),
            # standby_hd_limit < 0
            (2, Config.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, -1, "HdFc.__init__() n2"),
            # standby_hd_limit > count
            (2, Config.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 4, "HdFc.__init__() n3"),
            # Invalid device name (count=100 triggers error)
            (100, Config.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 4, "HdFc.__init__() n4"),
        ],
    )
    def test_init_n1(self, mocker: MockerFixture, count: int, temp_calc: int, steps: int, sensitivity: float,
                     polling: float, min_temp: float, max_temp: float, min_level: int, max_level: int,
                     sb_limit: int, error_str: str):
        """Negative unit test for HdFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - initialize a Config, Log, Ipmi, and HdFc classes
        - ASSERT: if no assertion is raised for invalid values at initialization
        """
        my_td = TestData()
        cmd_smart = my_td.create_command_file('echo "ACTIVE"')
        if count == 100:
            my_td.create_hd_data(1)
            my_td.hd_name_list = ["raise"]
        else:
            my_td.create_hd_data(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
        mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.hd_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        cfg = create_hd_config(enabled=True, temp_calc=temp_calc, steps=steps, sensitivity=sensitivity,
                               polling=polling, min_temp=min_temp, max_temp=max_temp, min_level=min_level,
                               max_level=max_level, hd_names=my_td.hd_name_list, smartctl_path=cmd_smart,
                               standby_guard_enabled=True, standby_hd_limit=sb_limit)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(Exception) as cm:
            HdFc(my_log, my_udevc, my_ipmi, cfg, False)
        assert cm.type is ValueError, error_str
        del my_td

    @pytest.mark.parametrize(
        "hd_names, error_str",
        [
            # NVMe device only
            ("/dev/nvme0n1", "HdFc.__init__() n5"),
            # Mixed SATA and NVMe devices
            ("/dev/sda /dev/nvme1n1", "HdFc.__init__() n6"),
        ],
    )
    def test_init_n2(self, mocker: MockerFixture, hd_names: str, error_str: str):
        """Negative unit test for HdFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device functions
        - initialize a Config, Log, Ipmi, and HdFc classes with NVMe device names
        - ASSERT: if no ValueError is raised for NVMe device names (NVMe drives are not allowed in HD fan controller)
        """
        my_td = TestData()
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
        mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
        cfg = create_hd_config(enabled=True, hd_names=hd_names.split())
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(Exception) as cm:
            HdFc(my_log, my_udevc, my_ipmi, cfg, False)
        assert cm.type is ValueError, error_str
        del my_td

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "args, sudo, error_str",
        [
            # -a flag with sudo
            (["-a", "/dev/sda"], True, "HdFc._exec_smartctl() p1"),
            # -a flag without sudo
            (["-a", "/dev/sda"], False, "HdFc._exec_smartctl() p2"),
            # standby check with sudo
            (["-i", "-n", "standby", "/dev/sda"], True, "HdFc._exec_smartctl() p3"),
            # standby check without sudo
            (["-i", "-n", "standby", "/dev/sda"], False, "HdFc._exec_smartctl() p4"),
            # -s flag with sudo
            (["-s", "/dev/sda"], True, "HdFc._exec_smartctl() p5"),
            # -s flag without sudo
            (["-s", "/dev/sda"], False, "HdFc._exec_smartctl() p6"),
        ],
    )
    def test_exec_smartctl_p(self, mocker: MockerFixture, args: List[str], sudo: bool, error_str: str):
        """Positive unit test for HdFc._exec_smartctl() method. It contains the following steps:
        - mock subprocess.run() function
        - initialize an empty HdFc class
        - call HdFc._exec_smartctl() method
        - ASSERT: if subprocess.run() called different from specified argument list
        """
        expected_args: List[str]

        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.config = create_hd_config(smartctl_path="smartctl")
        my_hdfc.sudo = sudo
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
        mocker.patch("subprocess.run", mock_subprocess_run)
        my_hdfc._exec_smartctl(args)
        expected_args = []
        if sudo:
            expected_args.append("sudo")
        expected_args.append(my_hdfc.config.smartctl_path)
        expected_args.extend(args)
        mock_subprocess_run.assert_called_with(expected_args, capture_output=True, check=False, text=True)
        assert mock_subprocess_run.call_count == 1, error_str

    # pylint: disable=R0801

    # pylint: disable=R0801
    @pytest.mark.parametrize(
        "smartctl_command, sudo, rc, exception, error_str",
        [
            # Non-existent command path
            ("/nonexistent/command", False, 0, FileNotFoundError, "HdFc._exec_smartctl() n1"),
            # Non-zero return code with sudo
            ("", True, 1, RuntimeError, "HdFc._exec_smartctl() n2"),
        ],
    )
    def test_exec_smartctl_n(self, mocker: MockerFixture, smartctl_command, sudo: bool, rc: int, exception: Any,
                             error_str: str):
        """Negative unit test for HdFc._exec_smartctl() method. It contains the following steps:
        - mock subprocess.run() function if needed
        - initialize an empty HdFc class
        - call HdFc._exec_smartctl() method
        - ASSERT: if no assertion was raised
        """
        if rc:
            mock_subprocess_run = MagicMock()
            mocker.patch("subprocess.run", mock_subprocess_run)
            mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=rc,
                                                                           stderr="sudo: smartctl: command not found")
        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.config = create_hd_config(smartctl_path=smartctl_command)
        my_hdfc.sudo = sudo
        with pytest.raises(Exception) as cm:
            my_hdfc._exec_smartctl(["-a", "/dev/sda"])
        assert cm.type == exception, error_str

    # pylint: enable=R0801

    # pylint: enable=R0801

    @pytest.mark.parametrize(
        "count, temperatures, error_str",
        [
            # 1 HD via hwmon
            (1, [32], "HdFc._get_nth_temp() p1"),
            # 2 HDs via hwmon
            (2, [33, 34], "HdFc._get_nth_temp() p2"),
            # 4 HDs via hwmon
            (4, [33, 34, 35, 38], "HdFc._get_nth_temp() p3"),
            # 8 HDs via hwmon
            (8, [33, 34, 35, 38, 36, 37, 31, 30], "HdFc._get_nth_temp() p4"),
        ],
    )
    def test_get_ntf_temp_p1(self, mocker: MockerFixture, count: int, temperatures: List[float], error_str: str):
        """Positive unit test for HdFc._get_nth_temp() method. It contains the following steps:
        - mock print() function
        - initialize an empty HdFc class
        - ASSERT: if the read temperature (from HWMON) is different from the expected value
        """
        my_td = TestData()
        my_td.create_hd_data(count, temperatures)
        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.hwmon_path = my_td.hd_files
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        for i in range(count):
            temp = my_hdfc._get_nth_temp(i)
            assert temp == temperatures[i], error_str
        del my_td

    @pytest.mark.parametrize(
        "count, temperatures, error_str",
        [
            # 1 HD via smartctl
            (1, [32], "HdFc._get_nth_temp() p5"),
            # 2 HDs via smartctl
            (2, [33, 34], "HdFc._get_nth_temp() p6"),
            # 4 HDs via smartctl
            (4, [33, 34, 35, 38], "HdFc._get_nth_temp() p7"),
            # 8 HDs via smartctl
            (8, [33, 34, 35, 38, 36, 37, 31, 30], "HdFc._get_nth_temp() p8"),
        ],
    )
    def test_get_nth_temp_p2(self, mocker: MockerFixture, count: int, temperatures: List[float], error_str: str):
        """Positive unit test for HdFc._get_nth_temp() method. It contains the following steps:
        - mock print(), subprocess.run() functions
        - initialize an empty HdFc class
        - ASSERT: if the read temperature (from smartctl) is different from the expected value
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
        my_td = TestData()
        my_td.create_hd_data(count, temperatures)
        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.hwmon_path = my_td.hd_name_list
        my_hdfc.hd_device_names = my_td.hd_name_list
        my_hdfc.hwmon_path = [""] * count
        my_hdfc.sudo = False
        my_hdfc.config = create_hd_config(smartctl_path="/usr/sbin/smartctl")
        mock_exec_smartclt = MagicMock()
        mock_exec_smartclt.return_value = subprocess.CompletedProcess([], returncode=0, stdout=smartctl_output)
        mocker.patch("smfc.HdFc._exec_smartctl", mock_exec_smartclt)
        for i in range(count):
            s = smartctl_output[random.randint(0, 2)].replace("XX", str(temperatures[i]))
            mock_exec_smartclt.return_value = subprocess.CompletedProcess([], returncode=0, stdout=s)
            assert my_hdfc._get_nth_temp(i) == temperatures[i], error_str
        del my_hdfc
        del my_td

    @pytest.mark.parametrize(
        "operation, exception, error_str",
        [
            # hwmon - FileNotFoundError
            (0, FileNotFoundError, "HdFc._get_nth_temp() n1"),
            # hwmon - IndexError
            (1, IndexError, "HdFc._get_nth_temp() n2"),
            # hwmon - ValueError
            (2, ValueError, "HdFc._get_nth_temp() n3"),
            # smartctl - FileNotFoundError
            (3, FileNotFoundError, "HdFc._get_nth_temp() n4"),
            # smartctl - IndexError
            (4, IndexError, "HdFc._get_nth_temp() n5"),
            # smartctl - ValueError
            (5, ValueError, "HdFc._get_nth_temp() n6"),
        ],
    )
    def test_get_nth_temp_n1(
        self, mocker: MockerFixture, operation: int, exception: Any, error_str: str
    ):
        """Negative unit test for HdFc._get_nth_temp() method. It contains the following steps:
        - mock print(), subprocess.run() functions
        - initialize an empty HdFc class
        - call HdFc._get_nth_temp()
        - ASSERT: if no exception raised
        """
        index = 0
        my_td = TestData()
        my_td.create_hd_data(1, [32])
        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.hwmon_path = my_td.hd_files
        my_hdfc.hd_device_names = my_td.hd_name_list
        my_hdfc.count = 1
        my_hdfc.sudo = False
        my_hdfc.config = create_hd_config(smartctl_path="/usr/sbin/smartctl")
        # FileNotFoundError: invalid file name with hwmon
        if operation == 0:
            my_hdfc.hwmon_path[0] = "/tmp/non_existent_dir/non_existent_file"
        # IndexError: index error with hwmon
        elif operation == 1:
            index = 1000
        # ValueError: invalid temperature with hwmon
        elif operation == 2:
            os.system('echo "invalid value" >' + my_hdfc.hwmon_path[0])
        # FileNotFoundError: invalid file name with smartctl
        elif operation == 3:
            my_hdfc.hwmon_path[0] = ""
            my_hdfc.config = create_hd_config(smartctl_path="/tmp/non_existent_dir/non_existent_file")
        # IndexError: index error with smartctl
        elif operation == 4:
            my_hdfc.hwmon_path[0] = ""
            index = 1000
        # ValueError: temperature not found in smartctl's output
        elif operation == 5:
            my_hdfc.hwmon_path[0] = ""
            mock_subprocess_run = MagicMock()
            mock_subprocess_run.return_value = subprocess.CompletedProcess(
                [], returncode=0, stdout="invalid\ninvalid\ninvalid\n"
            )
            mocker.patch("subprocess.run", mock_subprocess_run)
        with pytest.raises(Exception) as cm:
            my_hdfc._get_nth_temp(index)
        assert cm.type == exception, error_str
        del my_td

    # pylint: enable=protected-access

    @pytest.mark.parametrize(
        "states, result, error_str",
        [
            # All drives in STANDBY
            ([True, True, True, True, True, True, True, True], "SSSSSSSS", "HdFc.get_standby_state_str() p1"),
            # All drives ACTIVE
            ([False, False, False, False, False, False, False, False], "AAAAAAAA", "HdFc.get_standby_state_str() p2"),
            # Drive 0 in STANDBY
            ([True, False, False, False, False, False, False, False], "SAAAAAAA", "HdFc.get_standby_state_str() p3"),
            # Drive 1 in STANDBY
            ([False, True, False, False, False, False, False, False], "ASAAAAAA", "HdFc.get_standby_state_str() p4"),
            # Drive 2 in STANDBY
            ([False, False, True, False, False, False, False, False], "AASAAAAA", "HdFc.get_standby_state_str() p5"),
            # Drive 3 in STANDBY
            ([False, False, False, True, False, False, False, False], "AAASAAAA", "HdFc.get_standby_state_str() p6"),
            # Drive 4 in STANDBY
            ([False, False, False, False, True, False, False, False], "AAAASAAA", "HdFc.get_standby_state_str() p7"),
            # Drive 5 in STANDBY
            ([False, False, False, False, False, True, False, False], "AAAAASAA", "HdFc.get_standby_state_str() p8"),
            # Drive 6 in STANDBY
            ([False, False, False, False, False, False, True, False], "AAAAAASA", "HdFc.get_standby_state_str() p9"),
            # Drive 7 in STANDBY
            ([False, False, False, False, False, False, False, True], "AAAAAAAS", "HdFc.get_standby_state_str() p10"),
        ],
    )
    def test_get_standby_state_str(self, states: List[bool], result: str, error_str: str):
        """Positive unit test for HdFc.get_standby_state_str() method. It contains the following steps:
        - initialize an empty HdFc class
        - calls HdFc.get_standby_state_str()
        - ASSERT: if HdFc.get_standby_state_str() returns different from expected result
        """
        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.count = 8
        my_hdfc.standby_array_states = states
        assert my_hdfc.get_standby_state_str() == result, error_str
        del my_hdfc

    @pytest.mark.parametrize(
        "states, in_standby, error_str",
        [
            # 8 drives in STANDBY
            ([True, True, True, True, True, True, True, True], 8, "HdFc.check_standby_state() p1"),
            # 7 drives in STANDBY (drive 0 ACTIVE)
            ([False, True, True, True, True, True, True, True], 7, "HdFc.check_standby_state() p2"),
            # 7 drives in STANDBY (drive 1 ACTIVE)
            ([True, False, True, True, True, True, True, True], 7, "HdFc.check_standby_state() p3"),
            # 7 drives in STANDBY (drive 2 ACTIVE)
            ([True, True, False, True, True, True, True, True], 7, "HdFc.check_standby_state() p4"),
            # 7 drives in STANDBY (drive 3 ACTIVE)
            ([True, True, True, False, True, True, True, True], 7, "HdFc.check_standby_state() p5"),
            # 7 drives in STANDBY (drive 4 ACTIVE)
            ([True, True, True, True, False, True, True, True], 7, "HdFc.check_standby_state() p6"),
            # 7 drives in STANDBY (drive 5 ACTIVE)
            ([True, True, True, True, True, False, True, True], 7, "HdFc.check_standby_state() p7"),
            # 7 drives in STANDBY (drive 6 ACTIVE)
            ([True, True, True, True, True, True, False, True], 7, "HdFc.check_standby_state() p8"),
            # 7 drives in STANDBY (drive 7 ACTIVE)
            ([True, True, True, True, True, True, True, False], 7, "HdFc.check_standby_state() p9"),
            # 6 drives in STANDBY
            ([True, False, True, True, True, True, True, False], 6, "HdFc.check_standby_state() p10"),
            # 5 drives in STANDBY
            ([True, False, True, True, False, True, True, False], 5, "HdFc.check_standby_state() p11"),
            # 4 drives in STANDBY
            ([False, False, True, True, False, True, True, False], 4, "HdFc.check_standby_state() p12"),
            # 3 drives in STANDBY
            ([False, False, True, False, False, True, True, False], 3, "HdFc.check_standby_state() p13"),
            # 2 drives in STANDBY
            ([False, False, True, False, False, True, False, False], 2, "HdFc.check_standby_state() p14"),
            # 1 drive in STANDBY
            ([False, False, False, False, False, True, False, False], 1, "HdFc.check_standby_state() p15"),
            # 0 drives in STANDBY (all ACTIVE)
            ([False, False, False, False, False, False, False, False], 0, "HdFc.check_standby_state() p16"),
        ],
    )
    def test_check_standby_state(self, mocker: MockerFixture, states: List[bool], in_standby: int, error_str: str):
        """Positive unit test for HdFc.check_standby_state() method. It contains the following steps:
        - mock print(), HdFc._exec_smartctl() functions
        - initialize an empty HdFc classes
        - call HdFc.check_standby_state()
        - ASSERT: if result is different from the expected one
        """
        smartctl_output = [
            # Device in STANDBY mode.
            "smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.10.0-0.bpo.5-amd64] (local build)\n"
            "Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "Device is in STANDBY mode, exit(2)\n",
            # Device is ACTIVE.
            "smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.10.0-0.bpo.5-amd64] (local build)\n"
            "Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org\n"
            "\n"
            "=== START OF INFORMATION SECTION ===\n"
            "Model Family:     Samsung based SSDs\n"
            "Device Model:     Samsung SSD 870 QVO 8TB\n"
            "Serial Number:    S5SSNG0NB01828M\n"
            "LU WWN Device Id: 5 002538 f70b0ee2f\n"
            "Firmware Version: SVQ01B6Q\n"
            "User Capacity:    8,001,563,222,016 bytes [8.00 TB]\n"
            "Sector Size:      512 bytes logical/physical\n"
            "Rotation Rate:    Solid State Device\n"
            "Form Factor:      2.5 inches\n"
            "TRIM Command:     Available, deterministic, zeroed\n"
            "Device is:        In smartctl database [for details use: -P show]\n"
            "ATA Version is:   ACS-4 T13/BSR INCITS 529 revision 5\n"
            "SATA Version is:  SATA 3.3, 6.0 Gb/s (current: 6.0 Gb/s)\n"
            "Local Time is:    Sat May 15 14:26:26 2021 CEST\n"
            "SMART support is: Available - device has SMART capability.\n"
            "SMART support is: Enabled\n"
            "Power mode is:    ACTIVE or IDLE\n"
            "\n",
        ]
        results: List[subprocess.CompletedProcess] = []

        count = 8
        for i in range(count):
            results.append(subprocess.CompletedProcess([], returncode=0,
                                                       stdout=smartctl_output[0 if states[i] else 1]))
        my_td = TestData()
        my_td.create_hd_data(count)
        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.count = count
        my_hdfc.sudo = False
        my_hdfc.hd_device_names = my_td.hd_name_list
        my_hdfc.hwmon_path = [""] * count
        my_hdfc.config = create_hd_config(smartctl_path="/usr/sbin/smartctl")
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_hdfc.log = my_log
        my_hdfc.standby_array_states = [True] * count
        mock_hdzone_exec_smartclt = MagicMock()
        mock_hdzone_exec_smartclt.side_effect = iter(results)
        mocker.patch("smfc.HdFc._exec_smartctl", mock_hdzone_exec_smartclt)
        assert my_hdfc.check_standby_state() == in_standby, error_str
        del my_td

    @pytest.mark.parametrize(
        "states, count, error_str",
        [
            # All ACTIVE, send 8 standby commands
            ([False, False, False, False, False, False, False, False], 8, "HdFc.go_standby_state() p1"),
            # 1 in STANDBY, send 7 standby commands
            ([True, False, False, False, False, False, False, False], 7, "HdFc.go_standby_state() p2"),
            # 2 in STANDBY, send 6 standby commands
            ([True, True, False, False, False, False, False, False], 6, "HdFc.go_standby_state() p3"),
            # 3 in STANDBY, send 5 standby commands
            ([True, True, True, False, False, False, False, False], 5, "HdFc.go_standby_state() p4"),
            # 4 in STANDBY, send 4 standby commands
            ([True, True, True, True, False, False, False, False], 4, "HdFc.go_standby_state() p5"),
            # 5 in STANDBY, send 3 standby commands
            ([True, True, True, True, True, False, False, False], 3, "HdFc.go_standby_state() p6"),
            # 6 in STANDBY, send 2 standby commands
            ([True, True, True, True, True, True, False, False], 2, "HdFc.go_standby_state() p7"),
            # 7 in STANDBY, send 1 standby command
            ([True, True, True, True, True, True, True, False], 1, "HdFc.go_standby_state() p8"),
            # All in STANDBY, send 0 standby commands
            ([True, True, True, True, True, True, True, True], 0, "HdFc.go_standby_state() p9"),
        ],
    )
    def test_go_standby_state(self, mocker: MockerFixture, states: List[bool], count: int, error_str: str):
        """Positive unit test for HdFc.go_standby_state() method. It contains the following steps:
        - mock HdFc._exec_smartctl() function
        - initialize an empty HdFc classes
        - calls HdFc.go_standby_state()
        - ASSERT: if the array state is not in fully standby
        """
        my_td = TestData()
        my_td.create_hd_data(8)
        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.count = 8
        my_hdfc.sudo = False
        my_hdfc.hd_device_names = my_td.hd_name_list
        my_hdfc.config = create_hd_config(smartctl_path="/usr/sbin/smartctl")
        my_hdfc.standby_array_states = states
        mock_exec_smartctl = MagicMock()
        mock_exec_smartctl.return_value = subprocess.CompletedProcess([], returncode=0)
        mocker.patch("smfc.HdFc._exec_smartctl", mock_exec_smartctl)
        my_hdfc.go_standby_state()
        assert mock_exec_smartctl.call_count == count, error_str
        assert my_hdfc.standby_array_states == [True, True, True, True, True, True, True, True, ], error_str
        del my_td

    @pytest.mark.parametrize(
        "old_state, states, new_state, error_str",
        [
            # No state changes: all ACTIVE
            (False, [False, False, False, False, False, False, False, False], False, "HdFc.run_standby_guard() p1"),
            # No state changes: all STANDBY
            (True, [True, True, True, True, True, True, True, True], True, "HdFc.run_standby_guard() p2"),
            # Change from ACTIVE to STANDBY: 1 drive enters STANDBY
            (False, [False, True, False, False, False, False, False, False], True, "HdFc.run_standby_guard() p3"),
            # Change from ACTIVE to STANDBY: 2 drives enter STANDBY
            (False, [False, True, False, True, False, False, False, False], True, "HdFc.run_standby_guard() p4"),
            # Change from ACTIVE to STANDBY: all enter STANDBY
            (False, [True, True, True, True, True, True, True, True], True, "HdFc.run_standby_guard() p5"),
            # Change from STANDBY to ACTIVE: all become ACTIVE
            (True, [False, False, False, False, False, False, False, False], False, "HdFc.run_standby_guard() p6"),
            # Change from STANDBY to ACTIVE: some become ACTIVE
            (True, [True, False, False, True, True, True, True, True], False, "HdFc.run_standby_guard() p7"),
        ],
    )
    def test_run_standby_guard(self, mocker: MockerFixture, old_state: bool, states: List[bool], new_state: bool,
                               error_str: str):
        """Positive unit test for HdFc.run_standby_guard() method. It contains the following steps:
        - mock HdFc._exec_smartctl() function
        - initialize a Log and an empty HdFc classes
        - calls HdFc.run_standby_guard()
        - ASSERT: if the expected standby_flags are different
        """
        my_td = TestData()
        my_td.create_hd_data(8)
        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.count = 8
        my_hdfc.hd_device_names = my_td.hd_name_list
        my_hdfc.config = create_hd_config(smartctl_path="/usr/sbin/smartctl", standby_hd_limit=1)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_hdfc.log = my_log
        my_hdfc.go_standby_state = MagicMock(name="go_standby_state")
        my_hdfc.check_standby_state = MagicMock(name="check_standby_state")
        my_hdfc.check_standby_state.return_value = states.count(True)
        my_hdfc.standby_array_states = states
        my_hdfc.standby_flag = old_state
        my_hdfc.standby_change_timestamp = time.monotonic()
        mock_exec_smartctl = MagicMock()
        mock_exec_smartctl.return_value = subprocess.CompletedProcess([], returncode=0)
        mocker.patch("smfc.HdFc._exec_smartctl", mock_exec_smartctl)
        my_hdfc.run_standby_guard()
        assert my_hdfc.standby_flag == new_state, error_str
        del my_hdfc
        del my_td

    def test_get_nth_temp_smartctl_debug(self, mocker: MockerFixture):
        """Positive unit test for HdFc._get_nth_temp() method with DEBUG logging on smartctl fallback. It contains the
        following steps:
        - mock print(), HdFc._exec_smartctl() functions
        - initialize an empty HdFc class with log at DEBUG level
        - ASSERT: if temperature read via smartctl returns the expected value
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        smartctl_output = "Current Drive Temperature:     37 C\n"
        mock_exec_smartctl = MagicMock()
        mock_exec_smartctl.return_value = subprocess.CompletedProcess([], returncode=0, stdout=smartctl_output)
        mocker.patch("smfc.HdFc._exec_smartctl", mock_exec_smartctl)
        my_hdfc = HdFc.__new__(HdFc)
        my_hdfc.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_hdfc.hwmon_path = [""]
        my_hdfc.hd_device_names = ["/dev/sda"]
        my_hdfc.sudo = False
        my_hdfc.config = create_hd_config(smartctl_path="/usr/sbin/smartctl")
        assert my_hdfc._get_nth_temp(0) == 37.0, "smartctl temperature should be 37.0C"  # pylint: disable=protected-access
        del my_hdfc


# End.
