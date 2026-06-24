#!/usr/bin/env python3
#
#   test_nvmefc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.NvmeFc() class.
#
import os
from typing import List
import pytest
from pytest_mock import MockerFixture
from smfc.config import Config
from .test_data import TestData
from .test_fc_helpers import assert_fc_base_contract, build_nvme_fc, make_bare_nvme_fc

# Field order for the parametrized explicit-configuration init test.
CONFIG_FIELDS = ["count", "ipmi_zone", "temp_calc", "steps", "sensitivity", "polling", "min_temp", "max_temp",
                 "min_level", "max_level", "smoothing"]


class TestNvmeFc:
    """Unit test class for smfc.NvmeFc() class"""

    @pytest.mark.parametrize(
        CONFIG_FIELDS,
        [
            pytest.param(1, [0], Config.CALC_MIN, 4, 2, 2, 35, 70, 35, 100, 1, id="1nvme-zone0-min"),
            pytest.param(2, [1], Config.CALC_AVG, 4, 2, 2, 35, 70, 35, 100, 3, id="2nvme-zone1-avg-smooth3"),
            pytest.param(4, [2], Config.CALC_AVG, 4, 2, 2, 35, 70, 35, 100, 1, id="4nvme-zone2-avg"),
            pytest.param(1, [3], Config.CALC_MAX, 5, 3, 5, 32, 48, 36, 99, 4, id="1nvme-zone3-max-smooth4"),
        ],
    )
    def test_init_sets_attributes_from_config(self, mocker: MockerFixture, td: TestData, count: int,
                                              ipmi_zone: List[int], temp_calc: int, steps: int, sensitivity: float,
                                              polling: float, min_temp: float, max_temp: float, min_level: int,
                                              max_level: int, smoothing: int):
        """Positive unit test for NvmeFc.__init__() with an explicit configuration. It contains the steps:
        - build an NvmeFc via the shared builder (udev/hwmon discovery mocked)
        - ASSERT: the base-class contract (log/ipmi refs, name, count, config fields)
        - ASSERT: the hwmon paths and device_names() copy semantics specific to NvmeFc
        """
        cfg_values = {"ipmi_zone": ipmi_zone, "temp_calc": temp_calc, "steps": steps, "sensitivity": sensitivity,
                      "polling": polling, "min_temp": min_temp, "max_temp": max_temp, "min_level": min_level,
                      "max_level": max_level, "smoothing": smoothing}
        h = build_nvme_fc(mocker, td, count=count, **cfg_values)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=cfg_values, log=h.log, ipmi=h.ipmi)
        assert h.fc.hwmon_path == td.nvme_files
        assert h.fc.nvme_device_names == td.nvme_name_list
        # device_names() exposes a defensive copy of nvme_device_names for the snapshot/exporter path.
        names = h.fc.device_names()
        assert names == td.nvme_name_list
        assert names is not h.fc.nvme_device_names

    def test_init_applies_defaults(self, mocker: MockerFixture, td: TestData):
        """Positive unit test for NvmeFc.__init__() with default configuration values. It contains the steps:
        - build an NvmeFc from a default config (only enabled + nvme_names set)
        - ASSERT: the base-class contract holds with the NVMe default config values (Config.DV_NVME_*)
        - ASSERT: the hwmon paths and configured nvme_device_names match the test data
        """
        count = 2
        expected = {"ipmi_zone": [Config.HD_ZONE], "temp_calc": Config.CALC_AVG, "steps": Config.DV_NVME_STEPS,
                    "sensitivity": Config.DV_NVME_SENSITIVITY, "polling": Config.DV_NVME_POLLING,
                    "min_temp": Config.DV_NVME_MIN_TEMP, "max_temp": Config.DV_NVME_MAX_TEMP,
                    "min_level": Config.DV_NVME_MIN_LEVEL, "max_level": Config.DV_NVME_MAX_LEVEL,
                    "smoothing": Config.DV_NVME_SMOOTHING}
        h = build_nvme_fc(mocker, td, count=count)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=expected, log=h.log, ipmi=h.ipmi)
        assert h.fc.hwmon_path == td.nvme_files
        assert h.fc.nvme_device_names == td.nvme_name_list

    @pytest.mark.parametrize(
        "data_count, names",
        [
            # nvme_names= not specified (no devices -> count <= 0)
            pytest.param(0, None, id="no-names"),
            # Device name cannot be reached in the udev database
            pytest.param(1, ["raise"], id="unreachable-name"),
        ],
    )
    def test_init_rejects_invalid_device_names(self, mocker: MockerFixture, td: TestData, data_count: int, names):
        """Negative unit test for NvmeFc.__init__() with invalid device names. It contains the steps:
        - build an NvmeFc via the shared builder with an empty or unreachable nvme_names list
        - ASSERT: construction raises ValueError (count <= 0, or device cannot be reached in udev)
        """
        with pytest.raises(ValueError):
            build_nvme_fc(mocker, td, count=data_count, names=names)

    def test_init_rejects_missing_hwmon(self, mocker: MockerFixture, td: TestData):
        """Negative unit test for NvmeFc.__init__() when a device has no hwmon path. It contains the steps:
        - build an NvmeFc via the shared builder with get_hwmon_path() returning an empty string
        - ASSERT: construction raises ValueError (device has no hwmon path)
        """
        with pytest.raises(ValueError):
            build_nvme_fc(mocker, td, count=1, hwmon="empty")

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "count, temperatures",
        [
            pytest.param(1, [35], id="1nvme"),
            pytest.param(2, [35, 38], id="2nvme"),
            pytest.param(4, [35, 38, 40, 42], id="4nvme"),
        ],
    )
    def test_get_nth_temp_reads_hwmon(self, td: TestData, count: int, temperatures: List[float]):
        """Positive unit test for NvmeFc._get_nth_temp(). It contains the steps:
        - create NVMe hwmon test data with fixed per-device temperatures
        - build a bare NvmeFc with only hwmon_path/nvme_device_names set
        - ASSERT: _get_nth_temp(i) returns the temperature written to each device's hwmon file
        """
        td.create_nvme_data(count, temperatures)
        fc = make_bare_nvme_fc(td)
        for i in range(count):
            assert fc._get_nth_temp(i) == temperatures[i]

    @pytest.mark.parametrize(
        "operation, exception",
        [
            pytest.param(0, FileNotFoundError, id="missing-file"),
            pytest.param(1, ValueError, id="invalid-value"),
            pytest.param(2, IndexError, id="index-overflow"),
        ],
    )
    def test_get_nth_temp_raises_on_io_errors(self, td: TestData, operation: int, exception):
        """Negative unit test for NvmeFc._get_nth_temp() error handling. It contains the steps:
        - build a bare NvmeFc over a single hwmon file
        - trigger one of: missing file, invalid numeric value, or index overflow
        - ASSERT: _get_nth_temp() raises the matching exception (FileNotFoundError/ValueError/IndexError)
        """
        td.create_nvme_data(1, [35])
        fc = make_bare_nvme_fc(td)
        index = 0
        if operation == 0:
            fc.hwmon_path[0] = "/tmp/non_existent_dir/non_existent_file"
        elif operation == 1:
            os.system('echo "invalid value" >' + fc.hwmon_path[0])
        else:
            index = 1000
        with pytest.raises(exception):
            fc._get_nth_temp(index)

    # pylint: enable=protected-access

# End.
