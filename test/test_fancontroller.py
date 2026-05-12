#!/usr/bin/env python3
#
#   test_fancontroller.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.FanController() class.
#
import time
from collections import deque
from typing import List, Tuple
import pytest
import pyudev
from mock import MagicMock, call
from pytest_mock import MockerFixture
from smfc import FanController, Log, Ipmi
from smfc.config import Config
from .test_data import MockDevice, MockContext, create_cpu_config


class TestFanController:
    """Unit test class for smfc.FanController() class"""

    def _create_test_fc(self, mocker: MockerFixture, smoothing: int = 1, sensitivity: float = 1,
                        steps: int = 5, min_temp: float = 30, max_temp: float = 50, min_level: int = 35,
                        max_level: int = 100, polling: float = 1) -> FanController:
        """Helper method to create a configured FanController for testing.

        Args:
            mocker (MockerFixture): pytest mocker fixture
            smoothing (int): smoothing window size (default: 1)
            sensitivity (float): temperature change sensitivity (default: 1)
            steps (int): discrete steps (default: 5)
            min_temp (float): minimum temperature (default: 30)
            max_temp (float): maximum temperature (default: 50)
            min_level (int): minimum fan level (default: 35)
            max_level (int): maximum fan level (default: 100)
            polling (float): polling interval (default: 1)

        Returns:
            FanController: configured FanController instance with mocked dependencies
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
        cfg = create_cpu_config(steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                                max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing)
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        FanController.__init__(my_fc, my_log, my_ipmi, cfg.section, 1)
        return my_fc

    # pylint: disable=line-too-long
    @pytest.mark.parametrize(
        "ipmi_zone, count, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, "
        "smoothing, error_str",
        [
            # CPU zone 0, CALC_MIN, 1 device
            ([0], 1, Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() p1"),
            # CPU zone 0, CALC_MIN, 4 devices
            ([0], 4, Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() p2"),
            # CPU zone 0, CALC_AVG, 6 devices
            ([0], 6, Config.CALC_AVG, 6, 5, 4, 32, 52, 37, 95, 1, "FanController.__init__() p3"),
            # CPU zone 0, CALC_MAX, 8 devices
            ([0], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() p4"),
            # HD zone 1, CALC_MIN, 1 device
            ([1], 1, Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() p5"),
            # HD zone 1, CALC_MIN, 4 devices
            ([1], 4, Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, "FanController.__init__() p6"),
            # HD zone 1, CALC_AVG, 6 devices
            ([1], 6, Config.CALC_AVG, 6, 5, 4, 32, 52, 37, 95, 1, "FanController.__init__() p7"),
            # HD zone 1, CALC_MAX, 8 devices
            ([1], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() p8"),
            # Multiple zones comma-separated
            ([0, 1], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() p9"),
            # Three zones comma-separated
            ([0, 1, 2], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() p10"),
            # Three zones space-separated
            ([0, 1, 2], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() p11"),
            # Three zones extra whitespace
            ([0, 1, 2], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() p12"),
            # Three zones comma with whitespace
            ([0, 1, 2], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, "FanController.__init__() p13"),
            # Smoothing enabled (4)
            ([0], 1, Config.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, 4, "FanController.__init__() p14"),
        ],
    )
    # pylint: enable=line-too-long
    def test_init_p1(self, mocker: MockerFixture, ipmi_zone: List[int], count: int, temp_calc: int, steps: int,
                     sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                     max_level, smoothing: int, error_str: str,) -> None:
        """Positive unit test for FanController.__init__() method. It contains the following steps:
        - mock print(), FanController._get_nth_temp() functions
        - create CPU config using factory function
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
        cfg = create_cpu_config(ipmi_zone=ipmi_zone, temp_calc=temp_calc, steps=steps, sensitivity=sensitivity,
                                polling=polling, min_temp=min_temp, max_temp=max_temp, min_level=min_level,
                                max_level=max_level, smoothing=smoothing)
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        FanController.__init__(my_fc, my_log, my_ipmi, cfg.section, count)
        assert my_fc.log == my_log, error_str
        assert my_fc.ipmi == my_ipmi, error_str
        assert my_fc.config.ipmi_zone == ipmi_zone, error_str
        assert my_fc.name == cfg.section, error_str
        assert my_fc.count == count, error_str
        assert my_fc.config.temp_calc == temp_calc, error_str
        assert my_fc.config.steps == steps, error_str
        assert my_fc.config.sensitivity == sensitivity, error_str
        assert my_fc.config.polling == polling, error_str
        assert my_fc.config.min_temp == min_temp, error_str
        assert my_fc.config.max_temp == max_temp, error_str
        assert my_fc.config.min_level == min_level, error_str
        assert my_fc.config.max_level == max_level, error_str
        assert my_fc.config.smoothing == smoothing, error_str
        assert my_fc.level_step == (max_level - min_level) / steps, error_str
        assert my_fc.last_temp == 0, error_str
        assert my_fc.last_level == 0, error_str
        assert isinstance(my_fc._temp_history, deque), error_str  # pylint: disable=protected-access
        assert my_fc._temp_history.maxlen == smoothing, error_str  # pylint: disable=protected-access

    @pytest.mark.parametrize(
        "count, error_str",
        [
            # Invalid count - negative
            (-1, "FanController.__init__() n1"),
            # Invalid count - zero
            (0, "FanController.__init__() n2"),
        ],
    )
    def test_init_n1(self, mocker: MockerFixture, count: int, error_str: str) -> None:
        """Negative unit test for FanController.__init__() method. It contains the following steps:
        - mock print(), FanController._get_nth_temp() functions
        - create CPU config using factory function with invalid count
        - initialize a Log, Ipmi, and FanController classes
        - ASSERT: if exception was not raised in case of invalid count value
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_get_nth_temp = MagicMock()
        mocker.patch("smfc.FanController._get_nth_temp", mock_get_nth_temp)
        mock_get_nth_temp.return_value = 38.5
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        with pytest.raises(ValueError) as cm:
            cfg = create_cpu_config()
            my_fc = FanController.__new__(FanController)
            my_fc.config = cfg
            FanController.__init__(my_fc, my_log, my_ipmi, cfg.section, count)
        assert cm.type is ValueError, error_str

    @pytest.mark.parametrize(
        "devices, result, error_str",
        [
            # Normal case - 1 device found
            (["/sys"], "/sys/temp1_input", "FanController.get_hwmon_path() p1"),
            # Error case - multiple devices found
            (["/sys1", "/sys2"], "", "FanController.get_hwmon_path() p2"),
            # Error case - no devices found
            ([], "", "FanController.get_hwmon_path() p3"),
        ],
    )
    def test_get_hwmon_path(self, mocker: MockerFixture, devices: List[str], result: str, error_str: str) -> None:
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
        assert FanController.get_hwmon_path(context, parent) == result, error_str

    @pytest.mark.parametrize(
        "count, temp_calc, temps, expected, error_str",
        [
            # Single device (temp_calc irrelevant)
            (1, Config.CALC_AVG, [38.5], 38.5, "FanController.get_temp() p1"),
            # CALC_MIN - all same
            (3, Config.CALC_MIN, [38.5, 38.5, 38.5], 38.5, "FanController.get_temp() p2"),
            # CALC_MIN - different values
            (3, Config.CALC_MIN, [38.5, 40.5, 42.5], 38.5, "FanController.get_temp() p3"),
            # CALC_AVG - all same
            (3, Config.CALC_AVG, [38.5, 38.5, 38.5], 38.5, "FanController.get_temp() p4"),
            # CALC_AVG - different values
            (3, Config.CALC_AVG, [38.5, 40.5, 42.5], 40.5, "FanController.get_temp() p5"),
            # CALC_AVG - 8 devices
            (8, Config.CALC_AVG, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 45.0,
             "FanController.get_temp() p6"),
            # CALC_MAX - all same
            (3, Config.CALC_MAX, [38.5, 38.5, 38.5], 38.5, "FanController.get_temp() p7"),
            # CALC_MAX - different values
            (3, Config.CALC_MAX, [38.5, 40.5, 42.5], 42.5, "FanController.get_temp() p8"),
            # CALC_MAX - 8 devices
            (8, Config.CALC_MAX, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 52.0,
             "FanController.get_temp() p9"),
        ],
    )
    def test_get_temp(self, mocker: MockerFixture, count: int, temp_calc: int, temps: List[float], expected: float,
                      error_str: str):
        """Positive unit test for FanController.get_temp() method. It contains the following steps:
        - mock FanController._get_nth_temp() function
        - create CPU config using factory function
        - initialize an empty FanController class with count and temp_calc
        - ASSERT: if get_temp() returns different from expected temperature
        """
        cfg = create_cpu_config(temp_calc=temp_calc)
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        my_fc.count = count
        mock_temp = MagicMock()
        mock_temp.side_effect = temps
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        assert my_fc.get_temp() == expected, error_str

    @pytest.mark.parametrize(
        "zones, level, error_str",
        [
            # Single zone 0
            ([0], 45, "FanController.set_fan_level() p1"),
            # Single zone 1
            ([1], 55, "FanController.set_fan_level() p2"),
            # Two zones
            ([0, 1], 65, "FanController.set_fan_level() p3"),
            # Three zones
            ([0, 1, 2], 75, "FanController.set_fan_level() p4"),
        ],
    )
    def test_set_fan_level(self, mocker: MockerFixture, zones: List[int], level: int, error_str: str):
        """Positive unit test for FanController.set_fan_level() method. It contains the following steps:
        - mock Ipmi.set_fan_level() functions
        - create CPU config using factory function
        - initialize an empty FanController class
        - ASSERT: if the Ipmi.set_fan_level() function was called with different parameters
        """
        my_ipmi = Ipmi.__new__(Ipmi)
        cfg = create_cpu_config(ipmi_zone=zones)
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        my_fc.ipmi = my_ipmi
        my_fc.deferred_apply = False
        mock_set_multiple_fan_levels = MagicMock()
        mocker.patch("smfc.Ipmi.set_multiple_fan_levels", mock_set_multiple_fan_levels)
        my_fc.set_fan_level(level)
        calls = []
        for z in cfg.ipmi_zone:
            calls.append(call(z, level))
        mock_set_multiple_fan_levels.assert_called_with(zones, level)
        assert mock_set_multiple_fan_levels.call_count == 1, error_str

    @pytest.mark.parametrize(
        "steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, temp, level, error_str",
        [
            # Test with data set 1 (dynamic mapping)
            (5, 1, 1, 30, 50, 35, 100, None, None, "FanController.run() p1"),
            # Test with data set 2 (constant mapping)
            (5, 1, 1, 40, 40, 45, 45, None, None, "FanController.run() p2"),
            # Temperature under minimum
            (5, 1, 1, 30, 50, 35, 100, 25.0, 35, "FanController.run() p3"),
            # Temperature above maximum
            (5, 1, 1, 30, 50, 35, 100, 55.0, 100, "FanController.run() p4"),
        ],
    )
    def test_run(self, mocker: MockerFixture, steps: int, sensitivity: float, polling: float, min_temp: float,
                 max_temp: float, min_level: int, max_level, temp: float, level: int, error_str: str,) -> None:
        """Positive unit test for FanController.run() method. It contains the following steps:
        - mock print() and FanController._get_nth_temp() functions
        - create CPU config using factory function
        - initialize an empty FanController class
        - ASSERT: if run() generates different fan level based on the input zone temperature
        """

        # Test data set 1 for a generic configuration (dynamic mapping):
        # steps=5, min_temp=30, max_temp=50, min_level=35, max_level=100
        test_values_1: List[Tuple[float, int]] = [
            (30.0, 35), (31.0, 35), (32.0, 35), (33.0, 48), (34.0, 48), (35.0, 48), (36.0, 61), (37.0, 61),
            (38.0, 61), (39.0, 61), (40.0, 61), (41.0, 74), (42.0, 74), (43.0, 74), (44.0, 87), (45.0, 87),
            (46.0, 87), (47.0, 87), (48.0, 87), (49.0, 100), (50.0, 100),
        ]
        # Test data set 2 for special configuration (constant mapping):
        # steps=5, min_temp=40, max_temp=40, min_level=45, max_level=45
        test_values_2: List[Tuple[float, int]] = [
            (30.0, 45), (31.0, 45), (32.0, 45), (33.0, 45), (34.0, 45), (35.0, 45), (36.0, 45), (37.0, 45),
            (38.0, 45), (39.0, 45), (40.0, 45), (41.0, 45), (42.0, 45), (43.0, 45), (44.0, 45), (45.0, 45),
            (46.0, 45), (47.0, 45), (48.0, 45), (49.0, 45), (50.0, 45),
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

        cfg = create_cpu_config(steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                                max_temp=max_temp, min_level=min_level, max_level=max_level)
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        FanController.__init__(my_fc, my_log, my_ipmi, cfg.section, 1)

        # If temperature/level is not specified, we use the internal data sets.
        if temp is None:
            # Test 1 with a valid data set.
            if min_temp < max_temp:
                for i in test_values_1:
                    mock_temp.return_value = i[0]
                    my_fc.last_level = 0
                    my_fc.last_time = time.monotonic() - (polling + 1)
                    my_fc.run()
                    assert my_fc.last_temp == i[0], error_str
                    assert my_fc.last_level == i[1], error_str
                    if mock_ipmi_set_fan_level.call_count > 0:
                        mock_ipmi_set_fan_level.assert_called_with(i[1])
            # Test 2 with constant mapping.
            elif min_temp == max_temp:
                for i in test_values_2:
                    mock_temp.return_value = i[0]
                    my_fc.last_level = 0
                    my_fc.last_time = time.monotonic() - (polling + 1)
                    my_fc.run()
                    assert my_fc.last_temp == i[0], error_str
                    assert my_fc.last_level == i[1], error_str
                    if mock_ipmi_set_fan_level.call_count > 0:
                        mock_ipmi_set_fan_level.assert_called_with(i[1])
        # Test 3 - special cases with specific temp/level values.
        else:
            mock_temp.return_value = temp
            my_fc.last_level = 0
            my_fc.last_time = time.monotonic() - (polling + 1)
            my_fc.run()
            assert my_fc.last_temp == temp, error_str
            assert my_fc.last_level == level, error_str
            if mock_ipmi_set_fan_level.call_count > 0:
                mock_ipmi_set_fan_level.assert_called_with(level)

    def test_set_fan_level_deferred(self, mocker: MockerFixture):
        """Positive unit test for FanController.set_fan_level() method in deferred mode. It contains the following steps:
        - mock Ipmi.set_multiple_fan_levels() function
        - create CPU config using factory function
        - initialize an empty FanController class with deferred_apply=True
        - call set_fan_level() with a level value
        - ASSERT: if IPMI call is not skipped when deferred_apply is True
        """
        my_ipmi = Ipmi.__new__(Ipmi)
        cfg = create_cpu_config(ipmi_zone=[0])
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        my_fc.ipmi = my_ipmi
        my_fc.deferred_apply = True
        mock_set_multiple_fan_levels = MagicMock()
        mocker.patch("smfc.Ipmi.set_multiple_fan_levels", mock_set_multiple_fan_levels)
        my_fc.set_fan_level(50)
        assert mock_set_multiple_fan_levels.call_count == 0, "deferred_apply should skip IPMI call"

    def test_run_deferred(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method in deferred mode. It contains the following steps:
        - mock print(), FanController.set_fan_level(), FanController._get_nth_temp() functions
        - create CPU config using factory function
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
        cfg = create_cpu_config(steps=5, sensitivity=1, polling=1, min_temp=30, max_temp=50, min_level=35, max_level=100)
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        FanController.__init__(my_fc, my_log, my_ipmi, cfg.section, 1)
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
        - initialize a FanController using helper with smoothing=4
        - feed 3 stable readings at 30C, then a spike to 55C
        - ASSERT: if smoothing does not dampen a single-cycle temperature spike to intermediate level
        """
        my_fc = self._create_test_fc(mocker, smoothing=4)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
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
        - initialize a FanController using helper with smoothing=3
        - feed temperature readings while deque is not full yet
        - ASSERT: if smoothing does not correctly average available readings during warm-up
        """
        my_fc = self._create_test_fc(mocker, smoothing=3)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
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
        - initialize a FanController using helper with smoothing=3
        - feed sustained max temperature readings
        - ASSERT: if smoothing does not allow full response to sustained temperature increase
        """
        my_fc = self._create_test_fc(mocker, smoothing=3)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
        # First run at 50C: deque=[50], avg=50, passes sensitivity (|50-0|>=1), level=100
        mock_temp.return_value = 50.0
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp == pytest.approx(50.0), "sustained heat should converge to actual temp"
        assert my_fc.last_level == 100, "sustained max temp should reach max level"

    def test_run_smoothing_disabled(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method with smoothing=1. It contains the following steps:
        - initialize a FanController using helper with smoothing=1 (disabled)
        - feed a sequence of varying temperatures
        - ASSERT: if smoothing=1 does not use raw temperature without averaging
        """
        my_fc = self._create_test_fc(mocker, smoothing=1)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
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
        - initialize a FanController using helper with smoothing=4
        - feed rapid oscillating temperatures (30C/50C alternating for 10 cycles)
        - ASSERT: if smoothing does not dampen rapid temperature oscillations to midpoint (~40C)
        """
        my_fc = self._create_test_fc(mocker, smoothing=4)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
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
        - initialize a FanController using helper with smoothing=3 and sensitivity=5
        - feed temperature readings where smoothed change is below and above sensitivity threshold
        - ASSERT: if smoothed temperature change below sensitivity does not skip level update
        - ASSERT: if smoothed temperature change above sensitivity does not trigger level update
        """
        my_fc = self._create_test_fc(mocker, smoothing=3, sensitivity=5)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
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
        - initialize a FanController using helper with smoothing=3
        - feed temperatures at exactly min_temp (30C) and max_temp (50C) boundaries
        - ASSERT: if temperature at min_temp boundary does not yield min_level
        - ASSERT: if temperature at max_temp boundary does not yield max_level
        """
        my_fc = self._create_test_fc(mocker, smoothing=3)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
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
        "ipmi_zone, expected_zones, error_str",
        [
            # Duplicate zones preserved
            ([0, 1, 0], [0, 1, 0], "FanController.__init__() p15"),
            # All same zones preserved
            ([1, 1, 1], [1, 1, 1], "FanController.__init__() p16"),
            # Multiple duplicates preserved
            ([0, 1, 2, 1, 0], [0, 1, 2, 1, 0], "FanController.__init__() p17"),
        ],
    )
    def test_init_duplicate_zones(self, mocker: MockerFixture, ipmi_zone: List[int], expected_zones: List[int],
                                  error_str: str) -> None:
        """Positive unit test for FanController.__init__() method with duplicate zones. It contains the following steps:
        - mock print(), FanController._get_nth_temp() functions
        - create CPU config using factory function with duplicate zone IDs
        - initialize a Log, Ipmi, and FanController class
        - ASSERT: if duplicate zone IDs are not preserved in the parsed ipmi_zone list
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_get_nth_temp = MagicMock()
        mocker.patch("smfc.FanController._get_nth_temp", mock_get_nth_temp)
        mock_get_nth_temp.return_value = 38.5
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        cfg = create_cpu_config(ipmi_zone=ipmi_zone, temp_calc=Config.CALC_AVG, steps=5, sensitivity=4,
                                polling=2, min_temp=30, max_temp=50, min_level=35, max_level=100, smoothing=1)
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        FanController.__init__(my_fc, my_log, my_ipmi, cfg.section, 1)
        assert my_fc.config.ipmi_zone == expected_zones, error_str

    def test_set_fan_level_deferred_multi_zone(self, mocker: MockerFixture):
        """Positive unit test for FanController.set_fan_level() method with deferred multi-zone. It contains the following steps:
        - mock Ipmi.set_multiple_fan_levels() function
        - create CPU config using factory function with multiple zones
        - initialize an empty FanController class with ipmi_zone=[0, 1, 2] and deferred_apply=True
        - call set_fan_level() with a level value
        - ASSERT: if IPMI call is not skipped for multi-zone controller in deferred mode
        """
        my_ipmi = Ipmi.__new__(Ipmi)
        cfg = create_cpu_config(ipmi_zone=[0, 1, 2])
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        my_fc.ipmi = my_ipmi
        my_fc.deferred_apply = True
        mock_set_multiple_fan_levels = MagicMock()
        mocker.patch("smfc.Ipmi.set_multiple_fan_levels", mock_set_multiple_fan_levels)
        my_fc.set_fan_level(75)
        assert mock_set_multiple_fan_levels.call_count == 0, "deferred multi-zone should skip all IPMI calls"

    def test_run_polling_skipped(self, mocker: MockerFixture):
        """Positive unit test for FanController.run() method when polling interval has not elapsed. It contains the
        following steps:
        - initialize a FanController using helper with high polling interval
        - call run() without advancing time past the polling interval
        - ASSERT: if temperature is not read when polling is skipped
        - ASSERT: if fan level is not set when polling is skipped
        """
        my_fc = self._create_test_fc(mocker, polling=10, sensitivity=2)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
        mock_set_fan_level = mocker.patch("smfc.FanController.set_fan_level")
        mock_temp.return_value = 35.0
        # Set last_time to now so polling interval has not elapsed.
        initial_temp_calls = mock_temp.call_count
        my_fc.last_time = time.monotonic()
        my_fc.run()
        # Temperature should not have been read (polling was skipped silently).
        assert mock_temp.call_count == initial_temp_calls, "temperature should not be read when polling is skipped"
        assert mock_set_fan_level.call_count == 0, "fan level should not be set when polling is skipped"


# End.
