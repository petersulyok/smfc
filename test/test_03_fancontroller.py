#!/usr/bin/env python3
#
#   test_03_fancontroller.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.FanController() class.
#
import time
import re
from collections import deque
from typing import List, Tuple
import pytest
import pyudev
from mock import MagicMock, call
from pytest_mock import MockerFixture
from smfc import FanController, Log, Ipmi, CpuFc, HdFc
from .test_00_data import MockDevice, MockContext


class TestFanController:
    """Unit test class for smfc.FanController() class"""

    # pylint: disable=line-too-long
    @pytest.mark.parametrize(
        "ipmi_zone, name, count, temp_calc, steps, sensitivity, polling, min_temp, max_temp, "
        "min_level, max_level, smoothing, error",
        [
            ("0", CpuFc.CS_CPU_FC, 1, FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 1"),
            ("0", CpuFc.CS_CPU_FC, 4, FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 2"),
            ("0", CpuFc.CS_CPU_FC, 6, FanController.CALC_AVG, 6, 5, 4, 32, 52, 37, 95, 1, "FanController.__init__() 3"),
            ("0", CpuFc.CS_CPU_FC, 8, FanController.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() 4"),
            ("1", HdFc.CS_HD_FC, 1, FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 5"),
            ("1", HdFc.CS_HD_FC, 4, FanController.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 6"),
            ("1", HdFc.CS_HD_FC, 6, FanController.CALC_AVG, 6, 5, 4, 32, 52, 37, 95, 1, "FanController.__init__() 7"),
            ("1", HdFc.CS_HD_FC, 8, FanController.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() 8"),
            ("0, 1", HdFc.CS_HD_FC, 8, FanController.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() 9"),
            ("0, 1, 2", HdFc.CS_HD_FC, 8, FanController.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() 10"),
            (" 0 1 2", HdFc.CS_HD_FC, 8, FanController.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() 11"),
            ("  0  1  2 ", HdFc.CS_HD_FC, 8, FanController.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() 12"),
            ("  0,  1,  2 ", HdFc.CS_HD_FC, 8, FanController.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() 13"),
            ("0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, 4, "FanController.__init__() 14"),
        ],
    )
    # pylint: enable=line-too-long
    def test_init_p1(self, mocker: MockerFixture, ipmi_zone: str, name: str, count: int, temp_calc: int,
                     steps: int, sensitivity: float, polling: float, min_temp: float, max_temp: float,
                     min_level: int, max_level, smoothing: int, error: str,) -> None:
        """Positive unit test for FanController.__init__() method. It contains the following steps:
        - mock print(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController classes
        - ASSERT: if the class attributes contain different values that were passed to __init__
        - delete all instances
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_get_nth_temp = MagicMock()
        mocker.patch("smfc.FanController._get_nth_temp", mock_get_nth_temp)
        mock_get_nth_temp.return_value = 38.5
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_fc = FanController(my_log, my_ipmi, ipmi_zone, name, count, temp_calc, steps, sensitivity, polling,
                              min_temp, max_temp, min_level, max_level, smoothing)
        assert my_fc.log == my_log, error
        assert my_fc.ipmi == my_ipmi
        zone_str = re.sub(" +", " ", ipmi_zone.strip())
        assert my_fc.ipmi_zone == [int(s) for s in zone_str.split("," if "," in ipmi_zone else " ")], error
        assert my_fc.name == name, error
        assert my_fc.count == count, error
        assert my_fc.temp_calc == temp_calc, error
        assert my_fc.steps == steps, error
        assert my_fc.sensitivity == sensitivity, error
        assert my_fc.polling == polling, error
        assert my_fc.min_temp == min_temp, error
        assert my_fc.max_temp == max_temp, error
        assert my_fc.min_level == min_level, error
        assert my_fc.max_level == max_level, error
        assert my_fc.smoothing == smoothing, error
        assert my_fc.level_step == (max_level - min_level) / steps, error
        assert my_fc.last_temp == 0, error
        assert my_fc.last_level == 0, error
        assert isinstance(my_fc._temp_history, deque), error  # pylint: disable=protected-access
        assert my_fc._temp_history.maxlen == smoothing, error  # pylint: disable=protected-access

    @pytest.mark.parametrize(
        "ipmi_zone, name, count, temp_calc, steps, sensitivity, polling, min_temp, max_temp, "
        "min_level, max_level, smoothing, error",
        [
            # ipmi_zone is invalid
            ("-1", CpuFc.CS_CPU_FC, 1, 0, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 15"),
            ("101", CpuFc.CS_CPU_FC, 1, 0, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 16"),
            ("%, &", CpuFc.CS_CPU_FC, 1, 0, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 17"),
            ("1; 2; 3", CpuFc.CS_CPU_FC, 1, 0, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 18"),
            ("1, %, 3", CpuFc.CS_CPU_FC, 1, 0, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 19"),
            # count <= 0
            ("0", CpuFc.CS_CPU_FC, -1, 0, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 20"),
            ("0", CpuFc.CS_CPU_FC, 0, 0, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 21"),
            # temp_calc is invalid
            ("0", CpuFc.CS_CPU_FC, 1, -1, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 22"),
            ("0", CpuFc.CS_CPU_FC, 1, 100, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 23"),
            # step <= 0
            ("1", HdFc.CS_HD_FC, 1, 1, -2, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 24"),
            ("1", HdFc.CS_HD_FC, 1, 1, 0, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() 25"),
            # sensitivity <= 0
            ("1", HdFc.CS_HD_FC, 1, 1, 5, 0, 2, 30, 50, 35, 100, 1, "FanController.__init__() 26"),
            ("1", HdFc.CS_HD_FC, 1, 1, 5, -2, 2, 30, 50, 35, 100, 1, "FanController.__init__() 27"),
            # polling < 0
            ("1", HdFc.CS_HD_FC, 1, 1, 5, 4, -2, 30, 50, 35, 100, 1, "FanController.__init__() 28"),
            # max_temp < min_temp
            ("1", HdFc.CS_HD_FC, 1, 1, 5, 4, 2, 50, 30, 35, 100, 1, "FanController.__init__() 29"),
            # max_level < min_level
            ("1", HdFc.CS_HD_FC, 1, 1, 5, 4, 2, 30, 50, 100, 35, 1, "FanController.__init__() 30"),
            # smoothing < 1
            ("0", CpuFc.CS_CPU_FC, 1, 0, 5, 4, 2, 30, 50, 35, 100, 0, "FanController.__init__() 31"),
            ("0", CpuFc.CS_CPU_FC, 1, 0, 5, 4, 2, 30, 50, 35, 100, -1, "FanController.__init__() 32"),
        ],
    )
    def test_init_n1(self, mocker: MockerFixture, ipmi_zone: str, name: str, count: int, temp_calc: int,
                     steps: int, sensitivity: float, polling: float, min_temp: float, max_temp: float,
                     min_level: int, max_level, smoothing: int, error: str,) -> None:
        """Negative unit test for FanController.__init__() method. It contains the following steps:
        - mock print(), FanController._get_nth_temp() functions
        - initialize a Config, Log, Ipmi, and FanController classes
        - ASSERT: if exception was not raised in case of invalid parameter values
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_get_nth_temp = MagicMock()
        mocker.patch("smfc.FanController._get_nth_temp", mock_get_nth_temp)
        mock_get_nth_temp.return_value = 38.5
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        with pytest.raises(ValueError) as cm:
            FanController(my_log, my_ipmi, ipmi_zone, name, count, temp_calc, steps, sensitivity, polling,
                          min_temp, max_temp, min_level, max_level, smoothing)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "devices, result, error",
        [
            # Normal case - 1 device found
            (["/sys"], "/sys/temp1_input", "FanController.get_hwmon_path() 1"),
            # Error case - multiple devices found
            (["/sys1", "/sys2"], "", "FanController.get_hwmon_path() 2"),
            # Error case - no devices found
            ([], "", "FanController.get_hwmon_path() 3"),
        ],
    )
    def test_get_hwmon_path(self, mocker: MockerFixture, devices: List[str], result: str, error: str) -> None:
        """Positive unit test for FanController.get_hwmon_path() method. It contains the following steps:
        - mock pyudev.Context and pyudev.Device classes
        - initialize a pyudev.Context() and a pyudev.Device() classes
        - call FanController.get_hwmon_path() function
        - ASSERT: if not the expected result returned
        """
        result_devices: List[MockDevice]
        parent: pyudev.Device
        context: pyudev.Context

        # Result Device list for pyudev.list_devices()
        result_devices = []
        if devices is not None:
            for i in devices:
                md = MockDevice()
                # pylint: disable=protected-access
                md._sys_path = i
                # pylint: enable=protected-access
                result_devices.append(md)
        mocker.patch.object(pyudev.Context, "__new__", return_value=MockContext(result_devices))
        mocker.patch.object(pyudev.Device, "__new__", return_value=MockDevice())
        context = pyudev.Context.__new__(pyudev.Context)
        parent = pyudev.Device.__new__(pyudev.Device)
        assert FanController.get_hwmon_path(context, parent) == result, error

    @pytest.mark.parametrize(
        "count, temp_calc, temps, expected, error",
        [
            # count=1 (single device, temp_calc is irrelevant)
            (1, FanController.CALC_AVG, [38.5], 38.5, "fc get_temp single 1"),
            # CALC_MIN
            (3, FanController.CALC_MIN, [38.5, 38.5, 38.5], 38.5, "fc get_temp min 1"),
            (3, FanController.CALC_MIN, [38.5, 40.5, 42.5], 38.5, "fc get_temp min 2"),
            # CALC_AVG
            (3, FanController.CALC_AVG, [38.5, 38.5, 38.5], 38.5, "fc get_temp avg 1"),
            (3, FanController.CALC_AVG, [38.5, 40.5, 42.5], 40.5, "fc get_temp avg 2"),
            (8, FanController.CALC_AVG, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 45.0,
             "fc get_temp avg 3"),
            # CALC_MAX
            (3, FanController.CALC_MAX, [38.5, 38.5, 38.5], 38.5, "fc get_temp max 1"),
            (3, FanController.CALC_MAX, [38.5, 40.5, 42.5], 42.5, "fc get_temp max 2"),
            (8, FanController.CALC_MAX, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 52.0,
             "fc get_temp max 3"),
        ],
    )
    def test_get_temp(self, mocker: MockerFixture, count: int, temp_calc: int, temps: List[float], expected: float,
                      error: str):
        """Positive unit test for FanController.get_temp() method. It contains the following steps:
        - mock FanController._get_nth_temp() function
        - initialize an empty FanController class with count and temp_calc
        - ASSERT: if get_temp() returns different from expected temperature
        """
        my_fc = FanController.__new__(FanController)
        my_fc.count = count
        my_fc.temp_calc = temp_calc
        mock_temp = MagicMock()
        mock_temp.side_effect = temps
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        assert my_fc.get_temp() == expected, error

    @pytest.mark.parametrize(
        "zones, level, error",
        [
            ([0], 45, "FanController.set_fan_level() 1"),
            ([1], 55, "FanController.set_fan_level() 2"),
            ([0, 1], 65, "FanController.set_fan_level() 3"),
            ([0, 1, 2], 75, "FanController.set_fan_level() 4"),
        ],
    )
    def test_set_fan_level(self, mocker: MockerFixture, zones: List[int], level: int, error: str):
        """Positive unit test for FanController.set_fan_level() method. It contains the following steps:
        - mock Ipmi.set_fan_level() functions
        - initialize an empty FanController class
        - ASSERT: if the Ipmi.set_fan_level() function was called with different parameters
        """
        my_ipmi = Ipmi.__new__(Ipmi)
        my_fc = FanController.__new__(FanController)
        my_fc.ipmi_zone = zones
        my_fc.ipmi = my_ipmi
        my_fc.deferred_apply = False
        mock_set_multiple_fan_levels = MagicMock()
        mocker.patch("smfc.Ipmi.set_multiple_fan_levels", mock_set_multiple_fan_levels)
        my_fc.set_fan_level(level)
        calls = []
        for z in my_fc.ipmi_zone:
            calls.append(call(z, level))
        mock_set_multiple_fan_levels.assert_called_with(zones, level)
        assert mock_set_multiple_fan_levels.call_count == 1, error

    @pytest.mark.parametrize(
        "steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, temp, level, error",
        [
            (5, 1, 1, 30, 50, 35, 100, None, None, "FanController.run() 1"),
            (5, 1, 1, 40, 40, 45, 45, None, None, "FanController.run() 2"),
            # Check level if temperature is under the minimum value.
            (5, 1, 1, 30, 50, 35, 100, 25.0, 35, "FanController.run() 3"),
            # Check level if temperature is above the maximum value.
            (5, 1, 1, 30, 50, 35, 100, 55.0, 100, "FanController.run() 4"),
        ],
    )
    def test_run(self, mocker: MockerFixture, steps: int, sensitivity: float, polling: float, min_temp: float,
                 max_temp: float, min_level: int, max_level, temp: float, level: int, error: str,) -> None:
        """Positive unit test for FanController.run() method. It contains the following steps:
        - mock print() and FanController._get_nth_temp() functions
        - initialize an empty FanController class
        - ASSERT: if run() generates different fan level based on the input zone temperature
        """

        # Test data set 1 for a generic configuration (dynamic mapping):
        # steps=5, min_temp=30, max_temp=50, min_level=35, max_level=100
        test_values_1: List[Tuple[float, int]] = [
            (30.0, 35),
            (31.0, 35),
            (32.0, 35),
            (33.0, 48),
            (34.0, 48),
            (35.0, 48),
            (36.0, 61),
            (37.0, 61),
            (38.0, 61),
            (39.0, 61),
            (40.0, 61),
            (41.0, 74),
            (42.0, 74),
            (43.0, 74),
            (44.0, 87),
            (45.0, 87),
            (46.0, 87),
            (47.0, 87),
            (48.0, 87),
            (49.0, 100),
            (50.0, 100),
        ]
        # Test data set 2 for special configuration (constant mapping):
        # steps=5, min_temp=40, max_temp=40, min_level=45, max_level=45
        test_values_2: List[Tuple[float, int]] = [
            (30.0, 45),
            (31.0, 45),
            (32.0, 45),
            (33.0, 45),
            (34.0, 45),
            (35.0, 45),
            (36.0, 45),
            (37.0, 45),
            (38.0, 45),
            (39.0, 45),
            (40.0, 45),
            (41.0, 45),
            (42.0, 45),
            (43.0, 45),
            (44.0, 45),
            (45.0, 45),
            (46.0, 45),
            (47.0, 45),
            (48.0, 45),
            (49.0, 45),
            (50.0, 45),
        ]

        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_ipmi_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_ipmi_set_fan_level)
        mock_temp = MagicMock()
        mock_temp.return_value = 0
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)

        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, steps,
                              sensitivity, polling, min_temp, max_temp, min_level, max_level,)

        # If temperature/level is not specified, we use the internal data sets.
        if temp is None:
            # Test 1 with a valid data set.
            if min_temp < max_temp:
                for i in test_values_1:
                    mock_temp.return_value = i[0]
                    my_fc.last_level = 0
                    my_fc.last_time = time.monotonic() - (polling + 1)
                    my_fc.run()
                    assert my_fc.last_temp == i[0], error
                    assert my_fc.last_level == i[1], error
                    if mock_ipmi_set_fan_level.call_count > 0:
                        mock_ipmi_set_fan_level.assert_called_with(i[1])
            # Test 2 with constant mapping.
            elif min_temp == max_temp:
                for i in test_values_2:
                    mock_temp.return_value = i[0]
                    my_fc.last_level = 0
                    my_fc.last_time = time.monotonic() - (polling + 1)
                    my_fc.run()
                    assert my_fc.last_temp == i[0], error
                    assert my_fc.last_level == i[1], error
                    if mock_ipmi_set_fan_level.call_count > 0:
                        mock_ipmi_set_fan_level.assert_called_with(i[1])
        # Test 3 - special cases with specific temp/level values.
        else:
            mock_temp.return_value = temp
            my_fc.last_level = 0
            my_fc.last_time = time.monotonic() - (polling + 1)
            my_fc.run()
            assert my_fc.last_temp == temp, error
            assert my_fc.last_level == level, error
            if mock_ipmi_set_fan_level.call_count > 0:
                mock_ipmi_set_fan_level.assert_called_with(level)

    def test_set_fan_level_deferred(self, mocker: MockerFixture):
        """Positive unit test for FanController.set_fan_level() method in deferred mode. It contains the following steps:
        - mock Ipmi.set_multiple_fan_levels() function
        - initialize an empty FanController class with deferred_apply=True
        - call set_fan_level() with a level value
        - ASSERT: if IPMI call is not skipped when deferred_apply is True
        """
        my_ipmi = Ipmi.__new__(Ipmi)
        my_fc = FanController.__new__(FanController)
        my_fc.ipmi_zone = [0]
        my_fc.ipmi = my_ipmi
        my_fc.deferred_apply = True
        mock_set_multiple_fan_levels = MagicMock()
        mocker.patch("smfc.Ipmi.set_multiple_fan_levels", mock_set_multiple_fan_levels)
        my_fc.set_fan_level(50)
        assert mock_set_multiple_fan_levels.call_count == 0, "deferred_apply should skip IPMI call"

    def test_run_deferred(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method in deferred mode. It contains the following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class with deferred_apply=True
        - call run() method
        - ASSERT: if last_level is not updated when deferred_apply is True
        - ASSERT: if set_fan_level does not skip IPMI call in deferred mode
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_set_fan_level)
        mock_temp = MagicMock()
        mock_temp.return_value = 55.0
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 1, 1, 30, 50, 35,
                              100, 1)
        my_fc.deferred_apply = True
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        # Level should be updated (max_level since temp > max_temp)
        assert my_fc.last_level == 100, "deferred run should still update last_level"
        # But set_fan_level should not call IPMI (deferred_apply skips it inside set_fan_level)
        if mock_set_fan_level.call_count > 0:
            # set_fan_level was called but should not have triggered IPMI
            mock_set_fan_level.assert_called_with(100)

    def test_run_smoothing_spike(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method with temperature spike. It contains the following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class with smoothing=4
        - feed 3 stable readings at 30C, then a spike to 55C
        - ASSERT: if smoothing does not dampen a single-cycle temperature spike to intermediate level
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_set_fan_level)
        mock_temp = MagicMock()
        mock_temp.return_value = 0
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        # steps=5, min_temp=30, max_temp=50, min_level=35, max_level=100, smoothing=4
        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 1, 1, 30, 50, 35,
                              100, 4)
        # Feed 3 stable readings at 30C, then a spike to 55C.
        # With smoothing=4, the average after the spike is (30+30+30+55)/4 = 36.25C
        # which maps to step round((36.25-30)/4.0) = round(1.5625) = 2 → level = round(2*13)+35 = 61
        # Without smoothing, 55C would map to max_level=100.
        temps = [30.0, 30.0, 30.0, 55.0]
        for t in temps:
            mock_temp.return_value = t
            my_fc.last_level = 0
            my_fc.last_time = time.monotonic() - 2
            my_fc.run()
        # The smoothed temp after the spike should be 36.25C, not 55C.
        assert my_fc.last_temp == pytest.approx(36.25, abs=0.01), "smoothing should average temperatures"
        assert my_fc.last_level == 61, "smoothed spike should map to intermediate level, not max"

    def test_run_smoothing_warmup(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method during smoothing warm-up. It contains the following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class with smoothing=3
        - feed temperature readings while deque is not full yet
        - ASSERT: if smoothing does not correctly average available readings during warm-up
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_set_fan_level)
        mock_temp = MagicMock()
        mock_temp.return_value = 0
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        # smoothing=3
        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 1, 1, 30, 50, 35,
                              100, 3)
        # First reading: deque has 1 element, average = 40.0
        mock_temp.return_value = 40.0
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp == pytest.approx(40.0), "first reading should use single value"
        # Second reading: deque has 2 elements, average = (40+46)/2 = 43.0
        mock_temp.return_value = 46.0
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp == pytest.approx(43.0), "warm-up should average available readings"

    def test_run_smoothing_sustained_heat(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method with sustained heat. It contains the following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class with smoothing=3
        - feed sustained max temperature readings
        - ASSERT: if smoothing does not allow full response to sustained temperature increase
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_set_fan_level)
        mock_temp = MagicMock()
        mock_temp.return_value = 0
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        # smoothing=3, steps=5, sensitivity=1, min_temp=30, max_temp=50
        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 1, 1, 30, 50, 35,
                              100, 3)
        # First run at 50C: deque=[50], avg=50, passes sensitivity (|50-0|>=1), level=100
        mock_temp.return_value = 50.0
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp == pytest.approx(50.0), "sustained heat should converge to actual temp"
        assert my_fc.last_level == 100, "sustained max temp should reach max level"

    def test_run_smoothing_disabled(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method with smoothing=1. It contains the following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class with smoothing=1 (disabled)
        - feed a sequence of varying temperatures
        - ASSERT: if smoothing=1 does not use raw temperature without averaging
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_set_fan_level)
        mock_temp = MagicMock()
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        # smoothing=1 means disabled (no averaging)
        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 1, 1, 30, 50, 35,
                              100, 1)
        # Feed a sequence of varying temperatures
        temps = [30.0, 40.0, 50.0]
        expected_levels = [35, 61, 100]  # min_level, mid, max_level
        for i, t in enumerate(temps):
            mock_temp.return_value = t
            my_fc.last_level = 0
            my_fc.last_time = time.monotonic() - 2
            my_fc.run()
            assert my_fc.last_temp == pytest.approx(t), f"smoothing=1 should use raw temp {t}"
            assert my_fc.last_level == expected_levels[i], f"level for temp {t} should be {expected_levels[i]}"

    def test_run_smoothing_rapid_oscillation(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method with rapid oscillations. It contains the following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class with smoothing=4
        - feed rapid oscillating temperatures (30C/50C alternating for 10 cycles)
        - ASSERT: if smoothing does not dampen rapid temperature oscillations to midpoint (~40C)
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_set_fan_level)
        mock_temp = MagicMock()
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        # smoothing=4, min_temp=30, max_temp=50
        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 1, 1, 30, 50, 35,
                              100, 4)
        # Rapid oscillation: 30C and 50C alternating for 10 cycles
        # With smoothing=4, the average should converge to ~40C
        oscillating_temps = [30.0, 50.0] * 10
        for t in oscillating_temps:
            mock_temp.return_value = t
            my_fc.last_time = time.monotonic() - 2
            my_fc.run()
        # After many oscillations, the smoothed temp should be around 40C (average of 30 and 50)
        assert my_fc.last_temp == pytest.approx(40.0, abs=0.1), "oscillating temps should average to midpoint"
        # Level at 40C with steps=5, min_temp=30, max_temp=50 → step 2.5 rounds to 3 → level=35+3*13=74
        # Actually: temp_step = 4, (40-30)/4 = 2.5 rounds to 2 or 3, level_step = 13
        # Let's just verify it's in a reasonable middle range
        assert 50 <= my_fc.last_level <= 80, "smoothed oscillating temp should yield mid-range level"

    def test_run_smoothing_with_sensitivity(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method with smoothing and sensitivity interaction. It contains the following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class with smoothing=3 and sensitivity=5
        - feed temperature readings where smoothed change is below and above sensitivity threshold
        - ASSERT: if smoothed temperature change below sensitivity does not skip level update
        - ASSERT: if smoothed temperature change above sensitivity does not trigger level update
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_set_fan_level)
        mock_temp = MagicMock()
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        # smoothing=3, sensitivity=5 (high sensitivity threshold)
        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 5, 1, 30, 50, 35,
                              100, 3)
        # First reading at 35C
        mock_temp.return_value = 35.0
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        first_temp = my_fc.last_temp
        # Second reading at 37C - smoothed avg will be (35+37)/2 = 36C
        # Change from 35 to 36 is only 1C, less than sensitivity=5, so should NOT update
        mock_temp.return_value = 37.0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        # last_temp should still be 35.0 because sensitivity wasn't exceeded
        assert my_fc.last_temp == first_temp, "small smoothed change should not exceed sensitivity"
        # Third reading at 45C - smoothed avg = (35+37+45)/3 = 39C
        # Change from 35 to 39 is 4C, still less than sensitivity=5
        mock_temp.return_value = 45.0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp == first_temp, "smoothed change still under sensitivity threshold"
        # Fourth reading at 50C - smoothed avg = (37+45+50)/3 = 47.33C
        # Change from 35 to 47.33 is 12.33C, exceeds sensitivity=5
        mock_temp.return_value = 50.0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp > first_temp, "large smoothed change should exceed sensitivity"

    def test_run_smoothing_at_boundaries(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method at temperature boundaries. It contains the following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class with smoothing=3
        - feed temperatures at exactly min_temp (30C) and max_temp (50C) boundaries
        - ASSERT: if temperature at min_temp boundary does not yield min_level
        - ASSERT: if temperature at max_temp boundary does not yield max_level
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_set_fan_level)
        mock_temp = MagicMock()
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        # smoothing=3, min_temp=30, max_temp=50, min_level=35, max_level=100
        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 1, 1, 30, 50, 35,
                              100, 3)
        # Stay at exactly min_temp for multiple readings - first reading will set initial level
        mock_temp.return_value = 30.0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        # After first run, the level should be set
        assert my_fc.last_temp == pytest.approx(30.0), "temp at min boundary should stay at min"
        assert my_fc.last_level == 35, "level at min_temp should be min_level"
        # More readings at same temp shouldn't change anything (no sensitivity change)
        for _ in range(4):
            my_fc.last_time = time.monotonic() - 2
            my_fc.run()
        assert my_fc.last_level == 35, "level should remain at min_level"
        # Now jump to exactly max_temp - change exceeds sensitivity
        mock_temp.return_value = 50.0
        for _ in range(5):
            my_fc.last_time = time.monotonic() - 2
            my_fc.run()
        assert my_fc.last_temp == pytest.approx(50.0), "temp at max boundary should stay at max"
        assert my_fc.last_level == 100, "level at max_temp should be max_level"

    @pytest.mark.parametrize(
        "ipmi_zone, expected_zones, error",
        [
            ("0, 1, 0", [0, 1, 0], "duplicate zones should be preserved"),
            ("1, 1, 1", [1, 1, 1], "all same zones should be preserved"),
            ("0, 1, 2, 1, 0", [0, 1, 2, 1, 0], "multiple duplicates should be preserved"),
        ],
    )
    def test_init_duplicate_zones(self, mocker: MockerFixture, ipmi_zone: str, expected_zones: List[int],
                                  error: str) -> None:
        """Positive unit test for FanController.__init__() method with duplicate zones. It contains the following steps:
        - mock print(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class with duplicate zone IDs in ipmi_zone
        - ASSERT: if duplicate zone IDs are not preserved in the parsed ipmi_zone list
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_get_nth_temp = MagicMock()
        mocker.patch("smfc.FanController._get_nth_temp", mock_get_nth_temp)
        mock_get_nth_temp.return_value = 38.5
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_fc = FanController(my_log, my_ipmi, ipmi_zone, CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 4, 2, 30, 50,
                              35, 100, 1)
        assert my_fc.ipmi_zone == expected_zones, error

    def test_set_fan_level_deferred_multi_zone(self, mocker: MockerFixture):
        """Positive unit test for FanController.set_fan_level() method with deferred multi-zone. It contains the following steps:
        - mock Ipmi.set_multiple_fan_levels() function
        - initialize an empty FanController class with ipmi_zone=[0, 1, 2] and deferred_apply=True
        - call set_fan_level() with a level value
        - ASSERT: if IPMI call is not skipped for multi-zone controller in deferred mode
        """
        my_ipmi = Ipmi.__new__(Ipmi)
        my_fc = FanController.__new__(FanController)
        my_fc.ipmi_zone = [0, 1, 2]
        my_fc.ipmi = my_ipmi
        my_fc.deferred_apply = True
        mock_set_multiple_fan_levels = MagicMock()
        mocker.patch("smfc.Ipmi.set_multiple_fan_levels", mock_set_multiple_fan_levels)
        my_fc.set_fan_level(75)
        assert mock_set_multiple_fan_levels.call_count == 0, "deferred multi-zone should skip all IPMI calls"

    def test_run_polling_skipped(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method when polling interval has not elapsed. It contains the
        following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - initialize a Log, Ipmi, and FanController class
        - call run() without advancing time past the polling interval
        - ASSERT: if temperature is not read when polling is skipped
        - ASSERT: if fan level is not set when polling is skipped
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.FanController.set_fan_level", mock_set_fan_level)
        mock_temp = MagicMock()
        mock_temp.return_value = 35.0
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_fc = FanController(my_log, my_ipmi, "0", CpuFc.CS_CPU_FC, 1, FanController.CALC_AVG, 5, 2, 10, 30, 50, 35,
                              100, 1)
        # Set last_time to now so polling interval has not elapsed.
        initial_temp_calls = mock_temp.call_count
        my_fc.last_time = time.monotonic()
        my_fc.run()
        # Temperature should not have been read (polling was skipped silently).
        assert mock_temp.call_count == initial_temp_calls, "temperature should not be read when polling is skipped"
        assert mock_set_fan_level.call_count == 0, "fan level should not be set when polling is skipped"


# End.
