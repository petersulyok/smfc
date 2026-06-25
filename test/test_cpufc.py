#!/usr/bin/env python3
#
#   test_cpufc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.CpuFc() class.
#
import os
from typing import List
import pytest
from pytest_mock import MockerFixture
from smfc.config import Config
from .test_fixtures import TestData
from .test_fc_helpers import assert_fc_base_contract, build_cpu_fc

# Field order for the parametrized explicit-configuration init test.
CONFIG_FIELDS = ["count", "ipmi_zone", "temp_calc", "steps", "sensitivity", "polling", "min_temp", "max_temp",
                 "min_level", "max_level", "smoothing"]


class TestCpuFc:
    """Unit test class for smfc.CpuFc() class"""

    @pytest.mark.parametrize(
        CONFIG_FIELDS,
        [
            pytest.param(1, [0], Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, id="1cpu-zone0-min"),
            pytest.param(2, [1], Config.CALC_MIN, 6, 5, 3, 35, 55, 36, 99, 1, id="2cpu-zone1-min"),
            pytest.param(4, [2], Config.CALC_MIN, 7, 6, 4, 40, 60, 37, 98, 1, id="4cpu-zone2-min"),
            pytest.param(1, [3], Config.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, 1, id="1cpu-zone3-avg"),
            pytest.param(2, [4], Config.CALC_AVG, 6, 5, 3, 35, 55, 36, 99, 4, id="2cpu-zone4-avg-smooth4"),
            pytest.param(4, [5], Config.CALC_AVG, 7, 6, 4, 40, 60, 37, 98, 1, id="4cpu-zone5-avg"),
            pytest.param(1, [6], Config.CALC_MAX, 5, 4, 2, 30, 50, 35, 100, 1, id="1cpu-zone6-max"),
            pytest.param(2, [7], Config.CALC_MAX, 6, 5, 3, 35, 55, 36, 99, 1, id="2cpu-zone7-max"),
            pytest.param(4, [8], Config.CALC_MAX, 7, 6, 4, 40, 60, 37, 98, 1, id="4cpu-zone8-max"),
        ],
    )
    def test_init_sets_attributes_from_config(self, mocker: MockerFixture, td: TestData, count: int,
                                              ipmi_zone: List[int], temp_calc: int, steps: int, sensitivity: float,
                                              polling: float, min_temp: float, max_temp: float, min_level: int,
                                              max_level: int, smoothing: int):
        """Positive unit test for CpuFc.__init__() method. It contains the following steps:
        - mock pyudev.Context.list_devices, smfc.FanController.get_hwmon_path, and print via the
          build_cpu_fc helper (which also absorbs pyudev.Context.__new__, Ipmi.__new__, and print mocks)
        - build a Config with the parametrized explicit values for the CPU section
        - instantiate a CpuFc through build_cpu_fc with the requested count and config overrides
        - call assert_fc_base_contract() to validate base-class wiring against the expected values
        - ASSERT: the base-class contract (log/ipmi refs, name, count, config fields) holds
        - ASSERT: fc.hwmon_path equals td.cpu_files (the discovered hwmon paths)
        - ASSERT: fc.device_names() returns the synthesized ["cpu0", ..., f"cpu{count-1}"] labels
        """
        cfg_values = {"ipmi_zone": ipmi_zone, "temp_calc": temp_calc, "steps": steps, "sensitivity": sensitivity,
                      "polling": polling, "min_temp": min_temp, "max_temp": max_temp, "min_level": min_level,
                      "max_level": max_level, "smoothing": smoothing}
        h = build_cpu_fc(mocker, td, count=count, **cfg_values)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=cfg_values, log=h.log, ipmi=h.ipmi)
        assert h.fc.hwmon_path == td.cpu_files
        # device_names() synthesizes ordinal cpu0/cpu1/... labels for the snapshot/exporter path.
        assert h.fc.device_names() == [f"cpu{i}" for i in range(count)]

    def test_init_applies_defaults(self, mocker: MockerFixture, td: TestData):
        """Positive unit test for CpuFc.__init__() method with default configuration values. It contains the
        following steps:
        - mock pyudev.Context.list_devices, smfc.FanController.get_hwmon_path, and print via the
          build_cpu_fc helper (which also absorbs pyudev.Context.__new__, Ipmi.__new__, and print mocks)
        - build the expected-defaults dict from Config.DV_CPU_* constants
        - instantiate a CpuFc through build_cpu_fc with count=1 and no config overrides
        - call assert_fc_base_contract() to validate base-class wiring against the default values
        - ASSERT: the base-class contract holds with the CPU default config values (Config.DV_CPU_*)
        - ASSERT: fc.hwmon_path equals td.cpu_files (the discovered hwmon paths)
        """
        count = 1
        expected = {"ipmi_zone": [Config.CPU_ZONE], "temp_calc": Config.CALC_AVG, "steps": Config.DV_CPU_STEPS,
                    "sensitivity": Config.DV_CPU_SENSITIVITY, "polling": Config.DV_CPU_POLLING,
                    "min_temp": Config.DV_CPU_MIN_TEMP, "max_temp": Config.DV_CPU_MAX_TEMP,
                    "min_level": Config.DV_CPU_MIN_LEVEL, "max_level": Config.DV_CPU_MAX_LEVEL,
                    "smoothing": Config.DV_CPU_SMOOTHING}
        h = build_cpu_fc(mocker, td, count=count)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=expected, log=h.log, ipmi=h.ipmi)
        assert h.fc.hwmon_path == td.cpu_files

    def test_init_raises_without_hwmon_devices(self, mocker: MockerFixture, td: TestData):
        """Negative unit test for CpuFc.__init__() method when no CPU hwmon device is found. It contains the
        following steps:
        - mock pyudev.Context.list_devices, smfc.FanController.get_hwmon_path, and print via the
          build_cpu_fc helper (which also absorbs pyudev.Context.__new__, Ipmi.__new__, and print mocks)
        - call build_cpu_fc with count=0 so the mocked udev discovery yields an empty device list
        - enter a pytest.raises(RuntimeError) block around the construction
        - ASSERT: CpuFc.__init__ raises RuntimeError because no HWMON device is found for the CPU
        """
        with pytest.raises(RuntimeError):
            build_cpu_fc(mocker, td, count=0)

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "count, index, temperatures",
        [
            pytest.param(1, 0, [38.5], id="1cpu-idx0"),
            pytest.param(2, 0, [38.5, 40.5], id="2cpu-idx0"),
            pytest.param(2, 1, [38.5, 40.5], id="2cpu-idx1"),
            pytest.param(4, 0, [38.5, 40.5, 42.5, 44.5], id="4cpu-idx0"),
            pytest.param(4, 1, [38.5, 40.5, 42.5, 44.5], id="4cpu-idx1"),
            pytest.param(4, 2, [38.5, 40.5, 42.5, 44.5], id="4cpu-idx2"),
            pytest.param(4, 3, [38.5, 40.5, 42.5, 44.5], id="4cpu-idx3"),
        ],
    )
    def test_get_nth_temp_reads_hwmon(self, mocker: MockerFixture, td: TestData, count: int, index: int,
                                      temperatures: List[float]):
        """Positive unit test for CpuFc._get_nth_temp() method. It contains the following steps:
        - mock pyudev.Context.list_devices, smfc.FanController.get_hwmon_path, and print via the
          build_cpu_fc helper (which also absorbs pyudev.Context.__new__, Ipmi.__new__, and print mocks)
        - prepare a list of per-device temperatures and write them into the hwmon test files
        - instantiate a CpuFc through build_cpu_fc with the parametrized count and temps
        - call fc._get_nth_temp(index) for the parametrized index
        - ASSERT: _get_nth_temp(index) returns the temperature written to that device's hwmon file
        """
        h = build_cpu_fc(mocker, td, count=count, temps=temperatures)
        assert h.fc._get_nth_temp(index) == temperatures[index]

    @pytest.mark.parametrize(
        "operation, exception",
        [
            pytest.param(1, FileNotFoundError, id="missing-file"),
            pytest.param(2, ValueError, id="invalid-value"),
            pytest.param(3, IndexError, id="index-overflow"),
        ],
    )
    def test_get_nth_temp_raises_on_io_errors(self, mocker: MockerFixture, td: TestData, operation: int, exception):
        """Negative unit test for CpuFc._get_nth_temp() method error handling. It contains the following steps:
        - mock pyudev.Context.list_devices, smfc.FanController.get_hwmon_path, and print via the
          build_cpu_fc helper (which also absorbs pyudev.Context.__new__, Ipmi.__new__, and print mocks)
        - instantiate a CpuFc through build_cpu_fc with count=1 (one hwmon test file)
        - apply the parametrized fault: delete the hwmon file, write an invalid numeric value, or set
          an out-of-range index
        - enter a pytest.raises(exception) block and call fc._get_nth_temp(index)
        - ASSERT: _get_nth_temp() raises the matching exception (FileNotFoundError/ValueError/IndexError)
        """
        h = build_cpu_fc(mocker, td, count=1)
        index = 0
        if operation == 1:
            td.delete_file(td.cpu_files[0])
        elif operation == 2:
            os.system('echo "invalid value" >' + td.cpu_files[0])
        else:
            index = 100
        with pytest.raises(exception):
            h.fc._get_nth_temp(index)

    # pylint: enable=protected-access


# End.
