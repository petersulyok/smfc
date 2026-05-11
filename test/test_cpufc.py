#!/usr/bin/env python3
#
#   test_cpufc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.CpuFc() class.
#
import os
from typing import List
import pyudev
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, CpuFc
from smfc.config import Config
from .test_data import TestData, create_cpu_config


class TestCpuFc:
    """Unit test class for smfc.CpuFc() class"""

    @pytest.mark.parametrize(
        "count, ipmi_zone, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, "
        "smoothing, error",
        [
            # 1 CPU, zone 0, CALC_MIN
            (1, [0], Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "CpuFc.__init__() 1"),
            # 2 CPUs, zone 1, CALC_MIN
            (2, [1], Config.CALC_MIN, 6, 5, 3, 35, 55, 36, 99, 1, "CpuFc.__init__() 2"),
            # 4 CPUs, zone 2, CALC_MIN
            (4, [2], Config.CALC_MIN, 7, 6, 4, 40, 60, 37, 98, 1, "CpuFc.__init__() 3"),
            # 1 CPU, zone 3, CALC_AVG
            (1, [3], Config.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, 1, "CpuFc.__init__() 4"),
            # 2 CPUs, zone 4, CALC_AVG, smoothing=4
            (2, [4], Config.CALC_AVG, 6, 5, 3, 35, 55, 36, 99, 4, "CpuFc.__init__() 5"),
            # 4 CPUs, zone 5, CALC_AVG
            (4, [5], Config.CALC_AVG, 7, 6, 4, 40, 60, 37, 98, 1, "CpuFc.__init__() 6"),
            # 1 CPU, zone 6, CALC_MAX
            (1, [6], Config.CALC_MAX, 5, 4, 2, 30, 50, 35, 100, 1, "CpuFc.__init__() 7"),
            # 2 CPUs, zone 7, CALC_MAX
            (2, [7], Config.CALC_MAX, 6, 5, 3, 35, 55, 36, 99, 1, "CpuFc.__init__() 8"),
            # 4 CPUs, zone 8, CALC_MAX
            (4, [8], Config.CALC_MAX, 7, 6, 4, 40, 60, 37, 98, 1, "CpuFc.__init__() 9"),
        ]
    )
    def test_init_p1(self, mocker: MockerFixture, count: int, ipmi_zone: List[int], temp_calc: int, steps: int,
                     sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                     max_level: int, smoothing: int, error: str):
        """Positive unit test for CpuFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - create CPU config using factory function
        - initialize a Log, Ipmi, and CpuFc classes
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
        cfg = create_cpu_config(enabled=True, ipmi_zone=ipmi_zone, temp_calc=temp_calc, steps=steps,
                                sensitivity=sensitivity, polling=polling, min_temp=min_temp, max_temp=max_temp,
                                min_level=min_level, max_level=max_level, smoothing=smoothing)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_cpufc = CpuFc(my_log, my_udevc, my_ipmi, cfg)
        assert my_cpufc.log == my_log, error
        assert my_cpufc.ipmi == my_ipmi
        assert my_cpufc.config.ipmi_zone == ipmi_zone, error
        assert my_cpufc.name == cfg.section, error
        assert my_cpufc.count == count, error
        assert my_cpufc.config.temp_calc == temp_calc, error
        assert my_cpufc.config.steps == steps, error
        assert my_cpufc.config.sensitivity == sensitivity, error
        assert my_cpufc.config.polling == polling, error
        assert my_cpufc.config.min_temp == min_temp, error
        assert my_cpufc.config.max_temp == max_temp, error
        assert my_cpufc.config.min_level == min_level, error
        assert my_cpufc.config.max_level == max_level, error
        assert my_cpufc.config.smoothing == smoothing, error
        assert my_cpufc.hwmon_path == my_td.cpu_files, error
        del my_td

    @pytest.mark.parametrize("error", [("CpuFc.__init__() 10")])
    def test_init_p2(self, mocker: MockerFixture, error: str):
        """Positive unit test for CpuFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - create CPU config using factory function with default values
        - initialize a Log, Ipmi, and CpuFc classes
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
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        cfg = create_cpu_config(enabled=True)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_cpufc = CpuFc(my_log, my_udevc, my_ipmi, cfg)
        assert my_cpufc.log == my_log, error
        assert my_cpufc.ipmi == my_ipmi
        assert my_cpufc.config.ipmi_zone == [Config.CPU_ZONE], error
        assert my_cpufc.name == cfg.section, error
        assert my_cpufc.count == 1, error
        assert my_cpufc.config.temp_calc == Config.CALC_AVG, error
        assert my_cpufc.config.steps == Config.DV_CPU_STEPS, error
        assert my_cpufc.config.sensitivity == Config.DV_CPU_SENSITIVITY, error
        assert my_cpufc.config.polling == Config.DV_CPU_POLLING, error
        assert my_cpufc.config.min_temp == Config.DV_CPU_MIN_TEMP, error
        assert my_cpufc.config.max_temp == Config.DV_CPU_MAX_TEMP, error
        assert my_cpufc.config.min_level == Config.DV_CPU_MIN_LEVEL, error
        assert my_cpufc.config.max_level == Config.DV_CPU_MAX_LEVEL, error
        assert my_cpufc.config.smoothing == Config.DV_CPU_SMOOTHING, error
        assert my_cpufc.hwmon_path == my_td.cpu_files, error
        del my_td

    @pytest.mark.parametrize("error", [("CpuFc.__init__() 11")])
    def test_init_n(self, mocker: MockerFixture, error: str):
        """Negative unit test for CpuFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - create CPU config using factory function
        - initialize a Log, Ipmi, and CpuFc classes
        - ASSERT: if no RuntimeError assertion will be generated due to invalid configuration
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_context_list_devices = MagicMock()
        mock_context_list_devices.return_value = []
        mocker.patch("pyudev.Context.list_devices", mock_context_list_devices)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=None)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        cfg = create_cpu_config(enabled=True)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(Exception) as cm:
            CpuFc(my_log, my_udevc, my_ipmi, cfg)
        assert cm.type is RuntimeError, error

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "count, index, temperatures, error",
        [
            # 1 CPU, index 0
            (1, 0, [38.5], "CpuFc._get_nth_temp() 1"),
            # 2 CPUs, index 0
            (2, 0, [38.5, 40.5], "CpuFc._get_nth_temp() 2"),
            # 2 CPUs, index 1
            (2, 1, [38.5, 40.5], "CpuFc._get_nth_temp() 3"),
            # 4 CPUs, index 0
            (4, 0, [38.5, 40.5, 42.5, 44.5], "CpuFc._get_nth_temp() 4"),
            # 4 CPUs, index 1
            (4, 1, [38.5, 40.5, 42.5, 44.5], "CpuFc._get_nth_temp() 5"),
            # 4 CPUs, index 2
            (4, 2, [38.5, 40.5, 42.5, 44.5], "CpuFc._get_nth_temp() 6"),
            # 4 CPUs, index 3
            (4, 3, [38.5, 40.5, 42.5, 44.5], "CpuFc._get_nth_temp() 7"),
        ],
    )
    def test_get_nth_temp_p(self, mocker: MockerFixture, count: int, index: int, temperatures: List[float], error: str):
        """Positive unit test for CpuFc._get_nth_temp() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - create CPU config using factory function
        - initialize a Log, Ipmi, and CpuFc classes
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
        cfg = create_cpu_config(enabled=True)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_cpuzone = CpuFc(my_log, my_udevc, my_ipmi, cfg)
        assert my_cpuzone._get_nth_temp(index) == temperatures[index], error
        del my_td

    @pytest.mark.parametrize(
        "operation, error",
        [
            # FileNotFoundError - delete file
            (1, "CpuFc._get_nth_temp() 8"),
            # ValueError - invalid numeric value
            (2, "CpuFc._get_nth_temp() 9"),
            # IndexError - index overflow
            (3, "CpuFc._get_nth_temp() 10"),
        ],
    )
    def test_get_nth_temp_n(self, mocker: MockerFixture, operation: int, error: str):
        """Negative unit test for CpuFc._get_nth_temp() method. It contains the following steps:
        - mock print(), pyudev.Context.list_devices(), smfc.FanController.get_hwmon_path() functions
        - create CPU config using factory function
        - initialize a Log, Ipmi, and CpuFc classes
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
        cfg = create_cpu_config(enabled=True)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        my_cpuzone = CpuFc(my_log, my_udevc, my_ipmi, cfg)
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
