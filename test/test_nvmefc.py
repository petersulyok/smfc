#!/usr/bin/env python3
#
#   test_nvmefc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.NvmeFc() class.
#
import os
from typing import List
import pytest
import pyudev
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, NvmeFc
from smfc.config import Config
from .test_data import TestData, MockDevices, factory_mockdevice, create_nvme_config


class TestNvmeFc:
    """Unit test class for smfc.NvmeFc() class"""

    @pytest.mark.parametrize(
        "count, ipmi_zone, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, error_str",
        [
            # 1 NVMe, zone 0, CALC_MIN
            (1, [0], Config.CALC_MIN, 4, 2, 2, 35, 70, 35, 100, "NvmeFc.__init__() p1"),
            # 2 NVMes, zone 1, CALC_AVG
            (2, [1], Config.CALC_AVG, 4, 2, 2, 35, 70, 35, 100, "NvmeFc.__init__() p2"),
            # 4 NVMes, zone 2, CALC_AVG
            (4, [2], Config.CALC_AVG, 4, 2, 2, 35, 70, 35, 100, "NvmeFc.__init__() p3"),
            # 1 NVMe, zone 3, CALC_MAX
            (1, [3], Config.CALC_MAX, 5, 3, 5, 32, 48, 36, 99, "NvmeFc.__init__() p4"),
        ],
    )
    def test_init_p1(self, mocker: MockerFixture, count: int, ipmi_zone: List[int], temp_calc: int, steps: int,
                     sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                     max_level: int, error_str: str):
        """Positive unit test for NvmeFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - create NVME config using factory function
        - initialize a Log, Context, Ipmi, and NvmeFc classes
        - ASSERT: if the NvmeFc class attributes are different from values passed to __init__
        """
        my_td = TestData()
        my_td.create_nvme_data(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
        mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.nvme_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        cfg = create_nvme_config(enabled=True, ipmi_zone=ipmi_zone, temp_calc=temp_calc, steps=steps,
                                 sensitivity=sensitivity, polling=polling, min_temp=min_temp, max_temp=max_temp,
                                 min_level=min_level, max_level=max_level, nvme_names=my_td.nvme_name_list)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        mynvmefc = NvmeFc(my_log, my_udevc, my_ipmi, cfg)
        assert mynvmefc.config.ipmi_zone == ipmi_zone, error_str
        assert mynvmefc.name == cfg.section, error_str
        assert mynvmefc.count == count, error_str
        assert mynvmefc.config.temp_calc == temp_calc, error_str
        assert mynvmefc.config.steps == steps, error_str
        assert mynvmefc.config.sensitivity == sensitivity, error_str
        assert mynvmefc.config.polling == polling, error_str
        assert mynvmefc.config.min_temp == min_temp, error_str
        assert mynvmefc.config.max_temp == max_temp, error_str
        assert mynvmefc.config.min_level == min_level, error_str
        assert mynvmefc.config.max_level == max_level, error_str
        assert mynvmefc.config.smoothing == 1, error_str
        assert mynvmefc.nvme_device_names == my_td.nvme_name_list, error_str
        assert mynvmefc.hwmon_path == my_td.nvme_files, error_str
        del my_td

    @pytest.mark.parametrize(
        "error_str",
        [
            # Default configuration values test
            ("NvmeFc.__init__() p5"),
        ],
    )
    def test_init_p2(self, mocker: MockerFixture, error_str: str):
        """Positive unit test for NvmeFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - create NVME config using factory function with default values
        - initialize a Log, Context, Ipmi, and NvmeFc classes
        - ASSERT: if the NvmeFc class attributes are different from the default configuration values
        """
        my_td = TestData()
        count = 2
        my_td.create_nvme_data(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
        mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.nvme_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        cfg = create_nvme_config(enabled=True, nvme_names=my_td.nvme_name_list)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        mynvmefc = NvmeFc(my_log, my_udevc, my_ipmi, cfg)
        assert mynvmefc.log == my_log, error_str
        assert mynvmefc.ipmi == my_ipmi, error_str
        assert mynvmefc.config.ipmi_zone == [Config.HD_ZONE], error_str
        assert mynvmefc.name == cfg.section, error_str
        assert mynvmefc.count == count, error_str
        assert mynvmefc.config.temp_calc == Config.CALC_AVG, error_str
        assert mynvmefc.config.steps == Config.DV_NVME_STEPS, error_str
        assert mynvmefc.config.sensitivity == Config.DV_NVME_SENSITIVITY, error_str
        assert mynvmefc.config.polling == Config.DV_NVME_POLLING, error_str
        assert mynvmefc.config.min_temp == Config.DV_NVME_MIN_TEMP, error_str
        assert mynvmefc.config.max_temp == Config.DV_NVME_MAX_TEMP, error_str
        assert mynvmefc.config.min_level == Config.DV_NVME_MIN_LEVEL, error_str
        assert mynvmefc.config.max_level == Config.DV_NVME_MAX_LEVEL, error_str
        assert mynvmefc.config.smoothing == Config.DV_NVME_SMOOTHING, error_str
        assert mynvmefc.nvme_device_names == my_td.nvme_name_list, error_str
        assert mynvmefc.hwmon_path == my_td.nvme_files, error_str
        del my_td

    @pytest.mark.parametrize(
        "count, error_str",
        [
            # nvme_names= not specified (count = 0)
            (0, "NvmeFc.__init__() n1"),
            # Invalid device name (count == 100)
            (100, "NvmeFc.__init__() n2"),
        ],
    )
    def test_init_n1(self, mocker: MockerFixture, count: int, error_str: str):
        """Negative unit test for NvmeFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - create NVME config using factory function with invalid parameters
        - initialize a Log, Ipmi, and NvmeFc classes
        - ASSERT: if no assertion is raised for invalid values at initialization
        """
        my_td = TestData()
        if count == 100:
            my_td.create_nvme_data(1)
            my_td.nvme_name_list = ["raise"]
        else:
            my_td.create_nvme_data(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
        mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.nvme_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        cfg = create_nvme_config(enabled=True, nvme_names=my_td.nvme_name_list)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(Exception) as cm:
            NvmeFc(my_log, my_udevc, my_ipmi, cfg)
        assert cm.type is ValueError, error_str
        del my_td

    @pytest.mark.parametrize(
        "error_str",
        [
            # Empty hwmon path test
            ("NvmeFc.__init__() n3"),
        ],
    )
    def test_init_n2(self, mocker: MockerFixture, error_str: str):
        """Negative unit test for NvmeFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path() functions
        - create NVME config using factory function
        - initialize a Log, Ipmi, and NvmeFc classes with empty hwmon path
        - ASSERT: if no ValueError is raised when hwmon path is empty
        """
        my_td = TestData()
        my_td.create_nvme_data(1)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
        mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
        mock_fancontroller_gethwmonpath = MagicMock(return_value="")
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        cfg = create_nvme_config(enabled=True, nvme_names=my_td.nvme_name_list)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(Exception) as cm:
            NvmeFc(my_log, my_udevc, my_ipmi, cfg)
        assert cm.type is ValueError, error_str
        del my_td

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "count, temperatures, error_str",
        [
            # 1 NVMe
            (1, [35], "NvmeFc._get_nth_temp() p1"),
            # 2 NVMes
            (2, [35, 38], "NvmeFc._get_nth_temp() p2"),
            # 4 NVMes
            (4, [35, 38, 40, 42], "NvmeFc._get_nth_temp() p3"),
        ],
    )
    def test_get_nth_temp_p(self, mocker: MockerFixture, count: int, temperatures: List[float], error_str: str):
        """Positive unit test for NvmeFc._get_nth_temp() method. It contains the following steps:
        - mock print() function
        - initialize an empty NvmeFc class
        - ASSERT: if the read temperature (from HWMON) is different from the expected value
        """
        my_td = TestData()
        my_td.create_nvme_data(count, temperatures)
        mynvmefc = NvmeFc.__new__(NvmeFc)
        mynvmefc.hwmon_path = my_td.nvme_files
        mynvmefc.nvme_device_names = my_td.nvme_name_list
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        for i in range(count):
            temp = mynvmefc._get_nth_temp(i)
            assert temp == temperatures[i], error_str
        del my_td

    @pytest.mark.parametrize(
        "operation, exception, error_str",
        [
            # FileNotFoundError
            (0, FileNotFoundError, "NvmeFc._get_nth_temp() n1"),
            # ValueError - invalid temperature value
            (1, ValueError, "NvmeFc._get_nth_temp() n2"),
            # IndexError - index overflow
            (2, IndexError, "NvmeFc._get_nth_temp() n3"),
        ],
    )
    def test_get_nth_temp_n(self, operation: int, exception, error_str: str):
        """Negative unit test for NvmeFc._get_nth_temp() method. It contains the following steps:
        - initialize an empty NvmeFc class
        - call NvmeFc._get_nth_temp()
        - ASSERT: if no assertion raised
        """
        index = 0
        my_td = TestData()
        my_td.create_nvme_data(1, [35])
        mynvmefc = NvmeFc.__new__(NvmeFc)
        mynvmefc.hwmon_path = my_td.nvme_files
        mynvmefc.nvme_device_names = my_td.nvme_name_list
        # FileNotFoundError: invalid file name
        if operation == 0:
            mynvmefc.hwmon_path[0] = "/tmp/non_existent_dir/non_existent_file"
        # ValueError: invalid temperature value
        elif operation == 1:
            os.system('echo "invalid value" >' + mynvmefc.hwmon_path[0])
        # IndexError: index overflow
        else:
            # operation == 2
            index = 1000
        with pytest.raises(Exception) as cm:
            mynvmefc._get_nth_temp(index)
        assert cm.type == exception, error_str
        del my_td

    # pylint: enable=protected-access


# End.
