#!/usr/bin/env python3
#
#   test_10_nvmefc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.NvmeFc() class.
#
import os
from configparser import ConfigParser
from typing import List
import pytest
import pyudev
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, NvmeFc
from .test_00_data import TestData, MockDevices, factory_mockdevice


class TestNvmeFc:
    """Unit test class for smfc.NvmeFc() class"""

    @pytest.mark.parametrize(
        "count, ipmi_zone, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, error",
        [
            (1, "0", FanController.CALC_MIN, 4, 2, 2, 35, 70, 35, 100, "NvmeFc.__init__() 1"),
            (2, "1", FanController.CALC_AVG, 4, 2, 2, 35, 70, 35, 100, "NvmeFc.__init__() 2"),
            (4, "2", FanController.CALC_AVG, 4, 2, 2, 35, 70, 35, 100, "NvmeFc.__init__() 3"),
            (1, "3", FanController.CALC_MAX, 5, 3, 5, 32, 48, 36, 99,  "NvmeFc.__init__() 4"),
        ],
    )
    def test_init_p1(self, mocker: MockerFixture, count: int, ipmi_zone: str, temp_calc: int, steps: int,
                     sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                     max_level: int, error: str):
        """Positive unit test for NvmeFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - initialize a Config, Log, Context, Ipmi, and NvmeFc classes
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
        my_config = ConfigParser()
        my_config[NvmeFc.CS_NVME_FC] = {
            NvmeFc.CV_NVME_FC_ENABLED: "1",
            NvmeFc.CV_NVME_FC_IPMI_ZONE: ipmi_zone,
            NvmeFc.CV_NVME_FC_TEMP_CALC: str(temp_calc),
            NvmeFc.CV_NVME_FC_STEPS: str(steps),
            NvmeFc.CV_NVME_FC_SENSITIVITY: str(sensitivity),
            NvmeFc.CV_NVME_FC_POLLING: str(polling),
            NvmeFc.CV_NVME_FC_MIN_TEMP: str(min_temp),
            NvmeFc.CV_NVME_FC_MAX_TEMP: str(max_temp),
            NvmeFc.CV_NVME_FC_MIN_LEVEL: str(min_level),
            NvmeFc.CV_NVME_FC_MAX_LEVEL: str(max_level),
            NvmeFc.CV_NVME_FC_NVME_NAMES: my_td.nvme_names,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        mynvmefc = NvmeFc(my_log, my_udevc, my_ipmi, my_config)
        assert mynvmefc.ipmi_zone == [int(s) for s in ipmi_zone.split("," if "," in ipmi_zone else " ")], error
        assert mynvmefc.name == NvmeFc.CS_NVME_FC, error
        assert mynvmefc.count == count, error
        assert mynvmefc.temp_calc == temp_calc, error
        assert mynvmefc.steps == steps, error
        assert mynvmefc.sensitivity == sensitivity, error
        assert mynvmefc.polling == polling, error
        assert mynvmefc.min_temp == min_temp, error
        assert mynvmefc.max_temp == max_temp, error
        assert mynvmefc.min_level == min_level, error
        assert mynvmefc.max_level == max_level, error
        assert mynvmefc.nvme_device_names == my_td.nvme_name_list, error
        assert mynvmefc.hwmon_path == my_td.nvme_files, error
        del my_td

    @pytest.mark.parametrize("error", ["NvmeFc.__init__() 5"])
    def test_init_p2(self, mocker: MockerFixture, error: str):
        """Positive unit test for NvmeFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - initialize a Config, Log, Context, Ipmi, and NvmeFc classes
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
        my_config = ConfigParser()
        my_config[NvmeFc.CS_NVME_FC] = {
            NvmeFc.CV_NVME_FC_ENABLED: "1",
            NvmeFc.CV_NVME_FC_NVME_NAMES: my_td.nvme_names,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        mynvmefc = NvmeFc(my_log, my_udevc, my_ipmi, my_config)
        assert mynvmefc.log == my_log, error
        assert mynvmefc.ipmi == my_ipmi
        assert mynvmefc.ipmi_zone == [Ipmi.HD_ZONE], error
        assert mynvmefc.name == NvmeFc.CS_NVME_FC, error
        assert mynvmefc.count == count, error
        assert mynvmefc.temp_calc == FanController.CALC_AVG, error
        assert mynvmefc.steps == 4, error
        assert mynvmefc.sensitivity == 2, error
        assert mynvmefc.polling == 10, error
        assert mynvmefc.min_temp == 35, error
        assert mynvmefc.max_temp == 70, error
        assert mynvmefc.min_level == 35, error
        assert mynvmefc.max_level == 100, error
        assert mynvmefc.nvme_device_names == my_td.nvme_name_list, error
        assert mynvmefc.hwmon_path == my_td.nvme_files, error
        del my_td

    @pytest.mark.parametrize(
        "count, error",
        [
            # nvme_names= not specified (count = 0)
            (0, "NvmeFc.__init__() 6"),
            # Invalid device name (count == 100)
            (100, "NvmeFc.__init__() 7"),
        ],
    )
    def test_init_n1(self, mocker: MockerFixture, count: int, error: str):
        """Negative unit test for NvmeFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - initialize a Config, Log, Ipmi, and NvmeFc classes
        - ASSERT: if no assertion is raised for invalid values at initialization
        """
        my_td = TestData()
        if count == 100:
            my_td.create_nvme_data(1)
            my_td.nvme_names = "raise\n"
        else:
            my_td.create_nvme_data(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch.object(pyudev.Device, "__new__", new_callable=factory_mockdevice)
        mocker.patch("pyudev.Devices.from_device_file", MockDevices.from_device_file)
        mock_fancontroller_gethwmonpath = MagicMock(side_effect=my_td.nvme_files)
        mocker.patch("smfc.FanController.get_hwmon_path", mock_fancontroller_gethwmonpath)
        my_config = ConfigParser()
        my_config[NvmeFc.CS_NVME_FC] = {
            NvmeFc.CV_NVME_FC_ENABLED: "1",
            NvmeFc.CV_NVME_FC_NVME_NAMES: my_td.nvme_names,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(Exception) as cm:
            NvmeFc(my_log, my_udevc, my_ipmi, my_config)
        assert cm.type is ValueError, error
        del my_td

    @pytest.mark.parametrize("error", ["NvmeFc.__init__() 8"])
    def test_init_n2(self, mocker: MockerFixture, error: str):
        """Negative unit test for NvmeFc.__init__() method: empty hwmon path.
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
        my_config = ConfigParser()
        my_config[NvmeFc.CS_NVME_FC] = {
            NvmeFc.CV_NVME_FC_ENABLED: "1",
            NvmeFc.CV_NVME_FC_NVME_NAMES: my_td.nvme_names,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(Exception) as cm:
            NvmeFc(my_log, my_udevc, my_ipmi, my_config)
        assert cm.type is ValueError, error
        del my_td

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "count, temperatures, error",
        [
            (1, [35], "NvmeFc._get_nth_temp() 1"),
            (2, [35, 38], "NvmeFc._get_nth_temp() 2"),
            (4, [35, 38, 40, 42], "NvmeFc._get_nth_temp() 3"),
        ],
    )
    def test_get_nth_temp_p(self, mocker: MockerFixture, count: int, temperatures: List[float], error: str):
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
            assert temp == temperatures[i], error
        del my_td

    @pytest.mark.parametrize(
        "operation, exception, error",
        [
            # 0. FileNotFoundError
            (0, FileNotFoundError, "NvmeFc._get_nth_temp() 4"),
            # 1. ValueError
            (1, ValueError, "NvmeFc._get_nth_temp() 5"),
            # 2. IndexError
            (2, IndexError, "NvmeFc._get_nth_temp() 6"),
        ],
    )
    def test_get_nth_temp_n(self, operation: int, exception, error: str):
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
        assert cm.type == exception, error
        del my_td

    # pylint: enable=protected-access


# End.
