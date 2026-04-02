#!/usr/bin/env python3
#
#   test_04_cpufc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.CpuFc() class.
#
import os
from configparser import ConfigParser
from typing import List
import pyudev
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, CpuFc
from .test_00_data import TestData


class TestCpuFc:
    """Unit test class for smfc.CpuFc() class"""

    @pytest.mark.parametrize(
        "count, ipmi_zone, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, "
        "smoothing, error",
        [
            (1, "0", FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "CpuFc.__init__() 1"),
            (2, "1", FanController.CALC_MIN, 6, 5, 3, 35, 55, 36, 99, 1, "CpuFc.__init__() 2"),
            (4, "2", FanController.CALC_MIN, 7, 6, 4, 40, 60, 37, 98, 1, "CpuFc.__init__() 3"),
            (1, "3", FanController.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, 1, "CpuFc.__init__() 4"),
            (2, "4", FanController.CALC_AVG, 6, 5, 3, 35, 55, 36, 99, 4, "CpuFc.__init__() 5"),
            (4, "5", FanController.CALC_AVG, 7, 6, 4, 40, 60, 37, 98, 1, "CpuFc.__init__() 6"),
            (1, "6", FanController.CALC_MAX, 5, 4, 2, 30, 50, 35, 100, 1, "CpuFc.__init__() 7"),
            (2, "7", FanController.CALC_MAX, 6, 5, 3, 35, 55, 36, 99, 1, "CpuFc.__init__() 8"),
            (4, "8", FanController.CALC_MAX, 7, 6, 4, 40, 60, 37, 98, 1, "CpuFc.__init__() 9"),
        ]
    )
    def test_init_p1(self, mocker: MockerFixture, count: int, ipmi_zone: str, temp_calc: int, steps: int,
                     sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                     max_level: int, smoothing: int, error: str):
        """Positive unit test for CpuFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - initialize a Config, Log, Ipmi, and CpuFc classes
        - ASSERT: if the CpuFc class attributes contain different from passed values to __init__
        - delete all instances
        """
        dev_list: List[str]

        my_td = TestData()
        my_td.create_cpu_data(count)
        dev_list = [f"DEV{i}" for i in range(count)]
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_context_list_devices = MagicMock()
        mock_context_list_devices.return_value = dev_list
        mocker.patch("pyudev.Context.list_devices", mock_context_list_devices)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.cpu_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        my_config = ConfigParser()
        my_config[CpuFc.CS_CPU_FC] = {
            CpuFc.CV_CPU_FC_ENABLED: "1",
            CpuFc.CV_CPU_FC_IPMI_ZONE: str(ipmi_zone),
            CpuFc.CV_CPU_FC_TEMP_CALC: str(temp_calc),
            CpuFc.CV_CPU_FC_STEPS: str(steps),
            CpuFc.CV_CPU_FC_SENSITIVITY: str(sensitivity),
            CpuFc.CV_CPU_FC_POLLING: str(polling),
            CpuFc.CV_CPU_FC_MIN_TEMP: str(min_temp),
            CpuFc.CV_CPU_FC_MAX_TEMP: str(max_temp),
            CpuFc.CV_CPU_FC_MIN_LEVEL: str(min_level),
            CpuFc.CV_CPU_FC_MAX_LEVEL: str(max_level),
            CpuFc.CV_CPU_FC_SMOOTHING: str(smoothing),
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_cpufc = CpuFc(my_log, my_udevc, my_ipmi, my_config)
        assert my_cpufc.log == my_log, error
        assert my_cpufc.ipmi == my_ipmi
        assert my_cpufc.ipmi_zone == [int(s) for s in ipmi_zone.split("," if "," in ipmi_zone else " ")], error
        assert my_cpufc.name == CpuFc.CS_CPU_FC, error
        assert my_cpufc.count == count, error
        assert my_cpufc.temp_calc == temp_calc, error
        assert my_cpufc.steps == steps, error
        assert my_cpufc.sensitivity == sensitivity, error
        assert my_cpufc.polling == polling, error
        assert my_cpufc.min_temp == min_temp, error
        assert my_cpufc.max_temp == max_temp, error
        assert my_cpufc.min_level == min_level, error
        assert my_cpufc.max_level == max_level, error
        assert my_cpufc.smoothing == smoothing, error
        assert my_cpufc.hwmon_path == my_td.cpu_files, error
        del my_td

    @pytest.mark.parametrize("error", [("CpuFc.__init__() 10")])
    def test_init_p2(self, mocker: MockerFixture, error: str):
        """Positive unit test for CpuFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - initialize a Config, Log, Ipmi, and CpuFc classes
        - ASSERT: if the CpuFc class attributes contain different from default configuration values
        """
        dev_list: List[str]

        my_td = TestData()
        count = 1
        my_td.create_cpu_data(count)
        dev_list = [f"DEV{i}" for i in range(count)]
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_context_list_devices = MagicMock()
        mock_context_list_devices.return_value = dev_list
        mocker.patch("pyudev.Context.list_devices", mock_context_list_devices)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.cpu_files)
        mocker.patch(
            "smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath
        )
        my_config = ConfigParser()
        my_config[CpuFc.CS_CPU_FC] = {CpuFc.CV_CPU_FC_ENABLED: "1"}
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_cpufc = CpuFc(my_log, my_udevc, my_ipmi, my_config)
        assert my_cpufc.log == my_log, error
        assert my_cpufc.ipmi == my_ipmi
        assert my_cpufc.ipmi_zone == [Ipmi.CPU_ZONE], error
        assert my_cpufc.name == CpuFc.CS_CPU_FC, error
        assert my_cpufc.count == 1, error
        assert my_cpufc.temp_calc == FanController.CALC_AVG, error
        assert my_cpufc.steps == 6, error
        assert my_cpufc.sensitivity == 3.0, error
        assert my_cpufc.polling == 2, error
        assert my_cpufc.min_temp == 30, error
        assert my_cpufc.max_temp == 60, error
        assert my_cpufc.min_level == 35, error
        assert my_cpufc.max_level == 100, error
        assert my_cpufc.smoothing == 1, error
        assert my_cpufc.hwmon_path == my_td.cpu_files, error
        del my_td

    @pytest.mark.parametrize("error", [("CpuFc.__init__() 11")])
    def test_init_n(self, mocker: MockerFixture, error: str):
        """Negative unit test for CpuFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - initialize a Config, Log, Ipmi, and CpuFc classes
        - ASSERT: if no RuntimeError assertion will be generated due to invalid configuration
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_context_list_devices = MagicMock()
        mock_context_list_devices.return_value = []
        mocker.patch("pyudev.Context.list_devices", mock_context_list_devices)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=None)
        mocker.patch(
            "smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath
        )
        my_config = ConfigParser()
        my_config[CpuFc.CS_CPU_FC] = {CpuFc.CV_CPU_FC_ENABLED: "1"}
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(Exception) as cm:
            CpuFc(my_log, my_udevc, my_ipmi, my_config)
        assert cm.type is RuntimeError, error

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "count, index, temperatures, error",
        [
            (1, 0, [38.5], "CpuFc._get_nth_temp() 1"),
            (2, 0, [38.5, 40.5], "CpuFc._get_nth_temp() 2"),
            (2, 1, [38.5, 40.5], "CpuFc._get_nth_temp() 3"),
            (4, 0, [38.5, 40.5, 42.5, 44.5], "CpuFc._get_nth_temp() 4"),
            (4, 1, [38.5, 40.5, 42.5, 44.5], "CpuFc._get_nth_temp() 5"),
            (4, 2, [38.5, 40.5, 42.5, 44.5], "CpuFc._get_nth_temp() 6"),
            (4, 3, [38.5, 40.5, 42.5, 44.5], "CpuFc._get_nth_temp() 7"),
        ],
    )
    def test_get_nth_temp_p(self, mocker: MockerFixture, count: int, index: int, temperatures: List[float], error: str):
        """Positive unit test for CpuFc._get_nth_temp() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - initialize a Config, Log, Ipmi, and CpuFc classes
        - ASSERT: if _get_nth_temp() returns a different from the expected temperature
        """
        dev_list: List[str]

        my_td = TestData()
        my_td.create_cpu_data(count, temperatures)
        dev_list = [f"DEV{i}" for i in range(count)]
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_context_list_devices = MagicMock()
        mock_context_list_devices.return_value = dev_list
        mocker.patch("pyudev.Context.list_devices", mock_context_list_devices)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.cpu_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        my_config = ConfigParser()
        my_config[CpuFc.CS_CPU_FC] = {CpuFc.CV_CPU_FC_ENABLED: "1"}
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_cpuzone = CpuFc(my_log, my_udevc, my_ipmi, my_config)
        assert my_cpuzone._get_nth_temp(index) == temperatures[index], error
        del my_td

    @pytest.mark.parametrize(
        "operation, error",
        [
            (1, "CpuFc.__init__() 8"),
            (2, "CpuFc.__init__() 11"),
            (3, "CpuFc.__init__() 11"),
        ],
    )
    def test_get_nth_temp_n(self, mocker: MockerFixture, operation: int, error: str):
        """Negative unit test for CpuFc._get_nth_temp() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - initialize a Config, Log, Ipmi, and CpuFc classes
        - ASSERT: if _get_nth_temp() will not raise an exception in different error conditions
        """
        dev_list: List[str]
        index: int

        my_td = TestData()
        my_td.create_cpu_data(1)
        dev_list = ["DEV1"]
        index = 0
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_context_list_devices = MagicMock()
        mock_context_list_devices.return_value = dev_list
        mocker.patch("pyudev.Context.list_devices", mock_context_list_devices)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.cpu_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        my_config = ConfigParser()
        my_config[CpuFc.CS_CPU_FC] = {CpuFc.CV_CPU_FC_ENABLED: "1"}
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_cpuzone = CpuFc(my_log, my_udevc, my_ipmi, my_config)
        # Generate FileNotFoundError: delete file
        if operation == 1:
            my_td.delete_file(my_td.cpu_files[0])
        # Generate ValueError: write invalid numeric value to the file
        elif operation == 2:
            os.system('echo "invalid value" >' + my_td.cpu_files[0])
        # Generate IndexError: set index overflow
        else:
            # operation == 3
            index = 100
        with pytest.raises(Exception) as cm:
            my_cpuzone._get_nth_temp(index)
        assert cm.type in [IOError, FileNotFoundError, ValueError, IndexError], error
        del my_td

    # pylint: enable=protected-access


# End.
