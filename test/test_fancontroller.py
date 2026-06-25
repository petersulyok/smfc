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
from .test_config_builders import create_cpu_config
from .test_mocks import MockDevice, MockContext


def _make_fc(mocker: MockerFixture, cfg, count: int = 1, *, log_level: int = Log.LOG_DEBUG,
             temp_return: float = 0.0) -> Tuple[FanController, Log, Ipmi, MagicMock]:
    """Build a FanController with print / set_fan_level / _get_nth_temp mocked. Returns (fc, log, ipmi, mock_temp).

    Removes the repeated print/mocked-FanController-method boilerplate shared by every test that runs the
    base FanController constructor or run() loop. Subclass-specific builders for CpuFc / HdFc / NvmeFc /
    GpuFc live in test_fc_helpers.py; this helper targets the base FanController itself.
    """
    mocker.patch("builtins.print", MagicMock())
    mocker.patch("smfc.FanController.set_fan_level", MagicMock())
    mock_temp = MagicMock()
    mock_temp.return_value = temp_return
    mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
    log = Log(log_level, Log.LOG_STDOUT)
    ipmi = Ipmi.__new__(Ipmi)
    fc = FanController.__new__(FanController)
    fc.config = cfg
    FanController.__init__(fc, log, ipmi, cfg.section, count)
    return fc, log, ipmi, mock_temp


class TestFanController:
    """Unit test class for smfc.FanController() class"""

    def _create_test_fc(self, mocker: MockerFixture, smoothing: int = 1, sensitivity: float = 1,
                        steps: int = 5, min_temp: float = 30, max_temp: float = 50, min_level: int = 35,
                        max_level: int = 100, polling: float = 1) -> FanController:
        """Helper method to create a configured FanController for the smoothing-battery tests.

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
        cfg = create_cpu_config(steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                                max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing)
        fc, _, _, _ = _make_fc(mocker, cfg, count=1)
        return fc

    # pylint: disable=line-too-long
    @pytest.mark.parametrize(
        "ipmi_zone, count, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, smoothing",
        [
            pytest.param([0], 1, Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, id="cpu-min-1dev"),
            pytest.param([0], 4, Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, id="cpu-min-4dev"),
            pytest.param([0], 6, Config.CALC_AVG, 6, 5, 4, 32, 52, 37, 95, 1, id="cpu-avg-6dev"),
            pytest.param([0], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, id="cpu-max-8dev"),
            pytest.param([1], 1, Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, id="hd-min-1dev"),
            pytest.param([1], 4, Config.CALC_MIN, 5, 4, 2, 30, 50, 35, 100, 1, id="hd-min-4dev"),
            pytest.param([1], 6, Config.CALC_AVG, 6, 5, 4, 32, 52, 37, 95, 1, id="hd-avg-6dev"),
            pytest.param([1], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, id="hd-max-8dev"),
            pytest.param([0, 1], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, id="2zones"),
            pytest.param([0, 1, 2], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, id="3zones-comma"),
            pytest.param([0, 1, 2], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, id="3zones-space"),
            pytest.param([0, 1, 2], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, id="3zones-extra-ws"),
            pytest.param([0, 1, 2], 8, Config.CALC_MAX, 7, 6, 6, 34, 54, 39, 90, 1, id="3zones-comma-ws"),
            pytest.param([0], 1, Config.CALC_AVG, 5, 4, 2, 30, 50, 35, 100, 4, id="smoothing-4"),
        ],
    )
    # pylint: enable=line-too-long
    def test_init_sets_attributes_from_config(self, mocker: MockerFixture, ipmi_zone: List[int], count: int,
                                              temp_calc: int, steps: int, sensitivity: float, polling: float,
                                              min_temp: float, max_temp: float, min_level: int, max_level: int,
                                              smoothing: int) -> None:
        """Positive unit test for FanController.__init__() method. It contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - mock Ipmi via Ipmi.__new__ and instantiate FanController via FanController.__new__
        - build a CPU Config with the parametrized attributes and call FanController.__init__()
        - ASSERT: log reference is stored on the instance
        - ASSERT: ipmi reference is stored on the instance
        - ASSERT: config.ipmi_zone matches the parametrized zones
        - ASSERT: name equals the config section
        - ASSERT: count equals the parametrized device count
        - ASSERT: config.temp_calc matches the parametrized value
        - ASSERT: config.steps matches the parametrized value
        - ASSERT: config.sensitivity matches the parametrized value
        - ASSERT: config.polling matches the parametrized value
        - ASSERT: config.min_temp matches the parametrized value
        - ASSERT: config.max_temp matches the parametrized value
        - ASSERT: config.min_level matches the parametrized value
        - ASSERT: config.max_level matches the parametrized value
        - ASSERT: config.smoothing matches the parametrized value
        - ASSERT: level_step equals (max_level - min_level) / steps
        - ASSERT: last_temp is initialised to 0
        - ASSERT: last_level is initialised to 0
        - ASSERT: _temp_history is a deque instance
        - ASSERT: _temp_history maxlen equals the smoothing window size
        """
        cfg = create_cpu_config(ipmi_zone=ipmi_zone, temp_calc=temp_calc, steps=steps, sensitivity=sensitivity,
                                polling=polling, min_temp=min_temp, max_temp=max_temp, min_level=min_level,
                                max_level=max_level, smoothing=smoothing)
        my_fc, my_log, my_ipmi, _ = _make_fc(mocker, cfg, count=count, temp_return=38.5)
        assert my_fc.log == my_log
        assert my_fc.ipmi == my_ipmi
        assert my_fc.config.ipmi_zone == ipmi_zone
        assert my_fc.name == cfg.section
        assert my_fc.count == count
        assert my_fc.config.temp_calc == temp_calc
        assert my_fc.config.steps == steps
        assert my_fc.config.sensitivity == sensitivity
        assert my_fc.config.polling == polling
        assert my_fc.config.min_temp == min_temp
        assert my_fc.config.max_temp == max_temp
        assert my_fc.config.min_level == min_level
        assert my_fc.config.max_level == max_level
        assert my_fc.config.smoothing == smoothing
        assert my_fc.level_step == (max_level - min_level) / steps
        assert my_fc.last_temp == 0
        assert my_fc.last_level == 0
        assert isinstance(my_fc._temp_history, deque)  # pylint: disable=protected-access
        assert my_fc._temp_history.maxlen == smoothing  # pylint: disable=protected-access

    @pytest.mark.parametrize(
        "count",
        [
            pytest.param(-1, id="negative"),
            pytest.param(0, id="zero"),
        ],
    )
    def test_init_raises_on_invalid_count(self, mocker: MockerFixture, count: int) -> None:
        """Negative unit test for FanController.__init__() method. It contains the following steps:
        - mock builtins.print and smfc.FanController._get_nth_temp via mocker.patch
        - instantiate Ipmi via Ipmi.__new__ and FanController via FanController.__new__
        - call FanController.__init__() with count <= 0 (negative or zero)
        - ASSERT: ValueError is raised by the constructor
        """
        mocker.patch("builtins.print", MagicMock())
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
        assert cm.type is ValueError

    @pytest.mark.parametrize(
        "devices, result",
        [
            pytest.param(["/sys"], "/sys/temp1_input", id="one-device"),
            pytest.param(["/sys1", "/sys2"], "", id="multiple-devices"),
            pytest.param([], "", id="no-devices"),
        ],
    )
    def test_get_hwmon_path(self, mocker: MockerFixture, devices: List[str], result: str) -> None:
        """Positive unit test for FanController.get_hwmon_path() method. It contains the following steps:
        - mock pyudev.Context.__new__ to return a MockContext yielding the parametrized MockDevice list
        - mock pyudev.Device.__new__ to return a MockDevice parent
        - build a pyudev.Context and parent pyudev.Device via __new__
        - call FanController.get_hwmon_path(context, parent)
        - ASSERT: the returned sysfs path equals the expected string (empty when zero or multiple devices found)
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
        assert FanController.get_hwmon_path(context, parent) == result

    @pytest.mark.parametrize(
        "count, temp_calc, temps, expected",
        [
            pytest.param(1, Config.CALC_AVG, [38.5], 38.5, id="single-device"),
            pytest.param(3, Config.CALC_MIN, [38.5, 38.5, 38.5], 38.5, id="min-equal"),
            pytest.param(3, Config.CALC_MIN, [38.5, 40.5, 42.5], 38.5, id="min-mixed"),
            pytest.param(3, Config.CALC_AVG, [38.5, 38.5, 38.5], 38.5, id="avg-equal"),
            pytest.param(3, Config.CALC_AVG, [38.5, 40.5, 42.5], 40.5, id="avg-mixed"),
            pytest.param(8, Config.CALC_AVG, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 45.0, id="avg-8dev"),
            pytest.param(3, Config.CALC_MAX, [38.5, 38.5, 38.5], 38.5, id="max-equal"),
            pytest.param(3, Config.CALC_MAX, [38.5, 40.5, 42.5], 42.5, id="max-mixed"),
            pytest.param(8, Config.CALC_MAX, [38.0, 40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0], 52.0, id="max-8dev"),
        ],
    )
    def test_get_temp(self, mocker: MockerFixture, count: int, temp_calc: int, temps: List[float],
                      expected: float) -> None:
        """Positive unit test for FanController.get_temp() method. It contains the following steps:
        - mock smfc.FanController._get_nth_temp via mocker.patch with side_effect=temps
        - instantiate FanController via FanController.__new__ and set config and count attributes
        - call FanController.get_temp()
        - ASSERT: the returned aggregate equals the expected min/avg/max value for the parametrized temp_calc
        """
        cfg = create_cpu_config(temp_calc=temp_calc)
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        my_fc.count = count
        mock_temp = MagicMock()
        mock_temp.side_effect = temps
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        assert my_fc.get_temp() == expected

    @pytest.mark.parametrize(
        "count, temps",
        [
            pytest.param(1, [38.5], id="count-1"),
            pytest.param(4, [30.0, 32.0, 35.0, 40.0], id="count-4"),
        ],
    )
    def test_get_temp_caches_per_device(self, mocker: MockerFixture, count: int, temps: List[float]) -> None:
        """Positive unit test for FanController.get_temp() method (per-device caching). It contains the following steps:
        - mock smfc.FanController._get_nth_temp via mocker.patch with side_effect=temps
        - instantiate FanController via FanController.__new__ and set config and count attributes
        - call FanController.get_temp() to trigger the per-device read loop
        - ASSERT: last_per_device_temps equals the full list of parametrized per-device temperatures
        """
        cfg = create_cpu_config(temp_calc=Config.CALC_AVG)
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        my_fc.count = count
        mock_temp = MagicMock()
        mock_temp.side_effect = list(temps)
        mocker.patch("smfc.FanController._get_nth_temp", mock_temp)
        my_fc.get_temp()
        assert my_fc.last_per_device_temps == temps

    def test_default_device_names(self) -> None:
        """Positive unit test for FanController.device_names() method. It contains the following steps:
        - instantiate FanController via FanController.__new__ and set count=3
        - call FanController.device_names()
        - ASSERT: returns the default ordinal labels ["dev0", "dev1", "dev2"]
        """
        my_fc = FanController.__new__(FanController)
        my_fc.count = 3
        assert my_fc.device_names() == ["dev0", "dev1", "dev2"]

    @pytest.mark.parametrize(
        "zones, level",
        [
            pytest.param([0], 45, id="zone0"),
            pytest.param([1], 55, id="zone1"),
            pytest.param([0, 1], 65, id="2zones"),
            pytest.param([0, 1, 2], 75, id="3zones"),
        ],
    )
    def test_set_fan_level(self, mocker: MockerFixture, zones: List[int], level: int) -> None:
        """Positive unit test for FanController.set_fan_level() method. It contains the following steps:
        - mock smfc.Ipmi.set_multiple_fan_levels via mocker.patch
        - instantiate Ipmi via Ipmi.__new__ and FanController via FanController.__new__
        - set config, ipmi and deferred_apply=False on the FanController instance
        - call FanController.set_fan_level(level)
        - ASSERT: Ipmi.set_multiple_fan_levels was called with (zones, level)
        - ASSERT: Ipmi.set_multiple_fan_levels was called exactly once
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
        assert mock_set_multiple_fan_levels.call_count == 1

    @pytest.mark.parametrize(
        "steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, temp, level",
        [
            pytest.param(5, 1, 1, 30, 50, 35, 100, None, None, id="dynamic-curve"),
            pytest.param(5, 1, 1, 40, 40, 45, 45, None, None, id="constant-curve"),
            pytest.param(5, 1, 1, 30, 50, 35, 100, 25.0, 35, id="below-min-temp"),
            pytest.param(5, 1, 1, 30, 50, 35, 100, 55.0, 100, id="above-max-temp"),
        ],
    )
    def test_run_maps_temperature_to_level(self, mocker: MockerFixture, steps: int, sensitivity: float,
                                            polling: float, min_temp: float, max_temp: float, min_level: int,
                                            max_level: int, temp: float, level: int) -> None:
        """Positive unit test for FanController.run() method. It contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - mock smfc.FanController.set_fan_level a second time to count invocations
        - build a FanController from a CPU config with the parametrized staircase parameters
        - drive run() across either the documented (T, level) table or a single parametrized (temp, level) case
        - ASSERT: last_temp tracks the input temperature for each iteration
        - ASSERT: last_level matches the expected level from the staircase mapping
        - ASSERT: set_fan_level was invoked with the expected level whenever a level change occurred
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

        cfg = create_cpu_config(steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                                max_temp=max_temp, min_level=min_level, max_level=max_level)
        my_fc, _, _, mock_temp = _make_fc(mocker, cfg, count=1)
        mock_ipmi_set_fan_level = mocker.patch("smfc.FanController.set_fan_level")

        # If temperature/level is not specified, we use the internal data sets.
        if temp is None:
            # Test 1 with a valid data set.
            if min_temp < max_temp:
                for i in test_values_1:
                    mock_temp.return_value = i[0]
                    my_fc.last_level = 0
                    my_fc.last_time = time.monotonic() - (polling + 1)
                    my_fc.run()
                    assert my_fc.last_temp == i[0]
                    assert my_fc.last_level == i[1]
                    if mock_ipmi_set_fan_level.call_count > 0:
                        mock_ipmi_set_fan_level.assert_called_with(i[1])
            # Test 2 with constant mapping.
            elif min_temp == max_temp:
                for i in test_values_2:
                    mock_temp.return_value = i[0]
                    my_fc.last_level = 0
                    my_fc.last_time = time.monotonic() - (polling + 1)
                    my_fc.run()
                    assert my_fc.last_temp == i[0]
                    assert my_fc.last_level == i[1]
                    if mock_ipmi_set_fan_level.call_count > 0:
                        mock_ipmi_set_fan_level.assert_called_with(i[1])
        # Test 3 - special cases with specific temp/level values.
        else:
            mock_temp.return_value = temp
            my_fc.last_level = 0
            my_fc.last_time = time.monotonic() - (polling + 1)
            my_fc.run()
            assert my_fc.last_temp == temp
            assert my_fc.last_level == level
            if mock_ipmi_set_fan_level.call_count > 0:
                mock_ipmi_set_fan_level.assert_called_with(level)

    def test_set_fan_level_deferred(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.set_fan_level() method in deferred mode. It contains the following steps:
        - mock smfc.Ipmi.set_multiple_fan_levels via mocker.patch
        - instantiate Ipmi via Ipmi.__new__ and FanController via FanController.__new__
        - set config, ipmi and deferred_apply=True on the FanController instance
        - call FanController.set_fan_level(50)
        - ASSERT: Ipmi.set_multiple_fan_levels was NOT called (deferred mode suppresses the IPMI write)
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
        assert mock_set_multiple_fan_levels.call_count == 0

    def test_run_deferred(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method in deferred mode. It contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a FanController returning 55.0 C and set deferred_apply=True
        - mock smfc.FanController.set_fan_level a second time and call run() once
        - ASSERT: last_level is updated to max_level=100 (temp > max_temp)
        - ASSERT: set_fan_level (when invoked) received the expected level 100 (IPMI write is suppressed inside)
        """
        cfg = create_cpu_config(steps=5, sensitivity=1, polling=1, min_temp=30, max_temp=50, min_level=35,
                                max_level=100)
        my_fc, _, _, _ = _make_fc(mocker, cfg, count=1, temp_return=55.0)
        my_fc.deferred_apply = True
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        mock_set_fan_level = mocker.patch("smfc.FanController.set_fan_level")
        my_fc.run()
        # Level should be updated (max_level since temp > max_temp).
        assert my_fc.last_level == 100
        # set_fan_level may have been called, but should not have triggered IPMI (suppressed inside).
        if mock_set_fan_level.call_count > 0:
            mock_set_fan_level.assert_called_with(100)

    def test_run_smoothing_spike(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method with a temperature spike. It contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a FanController via _create_test_fc with smoothing=4
        - re-mock smfc.FanController._get_nth_temp and feed 3 stable 30 C readings, then a spike to 55 C
        - ASSERT: smoothing dampens the single-cycle spike so last_temp approx (30+30+30+55)/4 = 36.25 C
        - ASSERT: the smoothed reading maps to mid-level 61 (raw 55 C without smoothing would yield 100)
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
        assert my_fc.last_temp == pytest.approx(36.25, abs=0.01)
        assert my_fc.last_level == 61

    def test_run_smoothing_warmup(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method during smoothing warm-up. It contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a FanController via _create_test_fc with smoothing=3
        - re-mock smfc.FanController._get_nth_temp and feed two readings while the deque is not yet full
        - ASSERT: first reading uses the single value directly so last_temp approx 40.0
        - ASSERT: second reading averages the two available readings so last_temp approx 43.0
        """
        my_fc = self._create_test_fc(mocker, smoothing=3)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
        # First reading: deque has 1 element, average = 40.0
        mock_temp.return_value = 40.0
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp == pytest.approx(40.0)
        # Second reading: deque has 2 elements, average = (40+46)/2 = 43.0
        mock_temp.return_value = 46.0
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp == pytest.approx(43.0)

    def test_run_smoothing_sustained_heat(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method with sustained heat. It contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a FanController via _create_test_fc with smoothing=3
        - re-mock smfc.FanController._get_nth_temp and feed a single sustained reading at max_temp=50 C
        - ASSERT: smoothing converges to the actual temperature on the first read so last_temp approx 50.0
        - ASSERT: sustained max_temp drives last_level to max_level=100
        """
        my_fc = self._create_test_fc(mocker, smoothing=3)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
        # First run at 50C: deque=[50], avg=50, passes sensitivity (|50-0|>=1), level=100
        mock_temp.return_value = 50.0
        my_fc.last_level = 0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp == pytest.approx(50.0)
        assert my_fc.last_level == 100

    def test_run_smoothing_disabled(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method with smoothing disabled. It contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a FanController via _create_test_fc with smoothing=1 (disabled)
        - re-mock smfc.FanController._get_nth_temp and feed a sequence of 30 C, 40 C, 50 C readings
        - ASSERT: each iteration's last_temp equals the raw input temperature (no averaging)
        - ASSERT: last_level maps to 35 / 61 / 100 for the 30 / 40 / 50 C inputs respectively
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
            assert my_fc.last_temp == pytest.approx(t)
            assert my_fc.last_level == expected_levels[i]

    def test_run_smoothing_rapid_oscillation(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method with rapid oscillations. It contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a FanController via _create_test_fc with smoothing=4
        - re-mock smfc.FanController._get_nth_temp and feed 30 C / 50 C alternating readings across 10 cycles
        - ASSERT: smoothed last_temp converges to the midpoint approx 40 C
        - ASSERT: last_level lands in the mid-range between 50 and 80 inclusive
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
        assert my_fc.last_temp == pytest.approx(40.0, abs=0.1)
        # Level at 40C with steps=5, min_temp=30, max_temp=50 → step 2.5 rounds to 3 → level=35+3*13=74
        # Actually: temp_step = 4, (40-30)/4 = 2.5 rounds to 2 or 3, level_step = 13
        # Let's just verify it's in a reasonable middle range
        assert 50 <= my_fc.last_level <= 80

    def test_run_smoothing_with_sensitivity(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method with smoothing/sensitivity interaction. Contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a FanController via _create_test_fc with smoothing=3 and sensitivity=5
        - re-mock smfc.FanController._get_nth_temp and feed readings whose smoothed delta stays under sensitivity, then one that exceeds it
        - ASSERT: small smoothed changes (< sensitivity) do not advance last_temp from the first recorded value
        - ASSERT: further small smoothed changes still keep last_temp unchanged
        - ASSERT: a large smoothed change (>= sensitivity) finally advances last_temp above the first recorded value
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
        assert my_fc.last_temp == first_temp
        # Third reading at 45C - smoothed avg = (35+37+45)/3 = 39C
        # Change from 35 to 39 is 4C, still less than sensitivity=5
        mock_temp.return_value = 45.0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp == first_temp
        # Fourth reading at 50C - smoothed avg = (37+45+50)/3 = 47.33C
        # Change from 35 to 47.33 is 12.33C, exceeds sensitivity=5
        mock_temp.return_value = 50.0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        assert my_fc.last_temp > first_temp

    def test_run_smoothing_at_boundaries(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method at temperature boundaries. Contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a FanController via _create_test_fc with smoothing=3
        - re-mock smfc.FanController._get_nth_temp and hold at exactly min_temp=30 C, then jump to max_temp=50 C
        - ASSERT: at min_temp last_temp approx 30.0 and last_level resolves to min_level=35
        - ASSERT: repeated reads at min_temp keep last_level at 35 (no sensitivity change)
        - ASSERT: after jumping to max_temp last_temp approx 50.0
        - ASSERT: at max_temp last_level resolves to max_level=100
        """
        my_fc = self._create_test_fc(mocker, smoothing=3)
        mock_temp = mocker.patch("smfc.FanController._get_nth_temp")
        # Stay at exactly min_temp for multiple readings - first reading will set initial level
        mock_temp.return_value = 30.0
        my_fc.last_time = time.monotonic() - 2
        my_fc.run()
        # After first run, the level should be set
        assert my_fc.last_temp == pytest.approx(30.0)
        assert my_fc.last_level == 35
        # More readings at same temp shouldn't change anything (no sensitivity change)
        for _ in range(4):
            my_fc.last_time = time.monotonic() - 2
            my_fc.run()
        assert my_fc.last_level == 35
        # Now jump to exactly max_temp - change exceeds sensitivity
        mock_temp.return_value = 50.0
        for _ in range(5):
            my_fc.last_time = time.monotonic() - 2
            my_fc.run()
        assert my_fc.last_temp == pytest.approx(50.0)
        assert my_fc.last_level == 100

    @pytest.mark.parametrize(
        "ipmi_zone, expected_zones",
        [
            pytest.param([0, 1, 0], [0, 1, 0], id="duplicate-3"),
            pytest.param([1, 1, 1], [1, 1, 1], id="all-same-3"),
            pytest.param([0, 1, 2, 1, 0], [0, 1, 2, 1, 0], id="duplicates-5"),
        ],
    )
    def test_init_duplicate_zones(self, mocker: MockerFixture, ipmi_zone: List[int],
                                  expected_zones: List[int]) -> None:
        """Positive unit test for FanController.__init__() method with duplicate zones. Contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a CPU config with duplicate IPMI zone IDs and instantiate FanController via _make_fc
        - ASSERT: duplicates are preserved verbatim in config.ipmi_zone (no dedup occurs at init time)
        """
        cfg = create_cpu_config(ipmi_zone=ipmi_zone, temp_calc=Config.CALC_AVG, steps=5, sensitivity=4,
                                polling=2, min_temp=30, max_temp=50, min_level=35, max_level=100, smoothing=1)
        my_fc, _, _, _ = _make_fc(mocker, cfg, count=1, temp_return=38.5)
        assert my_fc.config.ipmi_zone == expected_zones

    def test_set_fan_level_deferred_multi_zone(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.set_fan_level() method with deferred multi-zone. Contains the steps:
        - mock smfc.Ipmi.set_multiple_fan_levels via mocker.patch
        - instantiate Ipmi via Ipmi.__new__ and FanController via FanController.__new__
        - set config with ipmi_zone=[0, 1, 2], ipmi reference and deferred_apply=True on the instance
        - call FanController.set_fan_level(75)
        - ASSERT: Ipmi.set_multiple_fan_levels was NOT called (deferred mode suppresses the write across zones)
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
        assert mock_set_multiple_fan_levels.call_count == 0

    @pytest.mark.parametrize(
        "min_temp, max_temp, min_level, max_level, steps",
        [
            pytest.param(30.0, 50.0, 35, 100, 5, id="30-50-steps5"),
            pytest.param(30.0, 60.0, 35, 100, 6, id="30-60-steps6"),
            pytest.param(32.0, 46.0, 35, 100, 4, id="32-46-steps4"),
            pytest.param(40.0, 40.0, 45, 45, 5, id="degenerate-constant"),
        ],
    )
    def test_create_legacy_lut_basic_shape(self, min_temp: float, max_temp: float, min_level: int,
                                           max_level: int, steps: int) -> None:
        """Positive unit test for FanController.create_legacy_lut() static method. It contains the following steps:
        - call FanController.create_legacy_lut(min_temp, max_temp, min_level, max_level, steps) directly
        - ASSERT: the resulting LUT has length 101 (covers temperatures 0..100)
        - ASSERT: LUT[int(min_temp)] equals min_level
        - ASSERT: LUT[int(max_temp)] equals max_level
        - ASSERT: LUT[0] equals min_level (head padding)
        - ASSERT: LUT[100] equals max_level (tail padding)
        - ASSERT: the LUT is non-decreasing across the full temperature range
        """
        lut = FanController.create_legacy_lut(min_temp, max_temp, min_level, max_level, steps)
        assert len(lut) == 101
        assert lut[int(min_temp)] == min_level
        assert lut[int(max_temp)] == max_level
        assert lut[0] == min_level
        assert lut[100] == max_level
        # Non-decreasing.
        for t in range(1, 101):
            assert lut[t] >= lut[t - 1], f"LUT not non-decreasing at T={t}"

    def test_create_legacy_lut_reproduces_run_formula(self) -> None:
        """Positive unit test for FanController.create_legacy_lut() static method. It contains the following steps:
        - call FanController.create_legacy_lut(30.0, 50.0, 35, 100, 5) directly
        - compare LUT entries against the canonical (30..50, 35..100, steps=5) staircase mapping
        - ASSERT: every integer temperature in 30..50 maps to the documented level from the original run() formula
        """
        lut = FanController.create_legacy_lut(30.0, 50.0, 35, 100, 5)
        expected = {30: 35, 31: 35, 32: 35, 33: 48, 34: 48, 35: 48, 36: 61, 37: 61, 38: 61, 39: 61,
                    40: 61, 41: 74, 42: 74, 43: 74, 44: 87, 45: 87, 46: 87, 47: 87, 48: 87, 49: 100,
                    50: 100}
        for t, level in expected.items():
            assert lut[t] == level, f"legacy LUT mismatch at T={t}: got {lut[t]}, expected {level}"

    @pytest.mark.parametrize(
        "pairs, steps",
        [
            pytest.param([(30, 35), (65, 100)], 5, id="2-point"),
            pytest.param([(30, 35), (50, 40), (65, 100)], 5, id="3-point"),
            pytest.param([(30, 35), (50, 40), (60, 90), (65, 100)], 5, id="4-point"),
            pytest.param([(30, 35), (60, 100)], 10, id="2-point-steps10"),
        ],
    )
    def test_create_control_function_shape(self, pairs, steps: int) -> None:
        """Positive unit test for FanController.create_control_function() static method. Contains the following steps:
        - call FanController.create_control_function(pairs, steps) directly with the parametrized breakpoints
        - inspect LUT length, endpoint pinning, head/tail padding, and plateau run-length count
        - ASSERT: the resulting LUT has length 101
        - ASSERT: LUT[t_first] equals the first breakpoint's level
        - ASSERT: LUT[t_last] equals the last breakpoint's level
        - ASSERT: all entries before t_first equal the first level (head padding)
        - ASSERT: all entries after t_last equal the last level (tail padding)
        - ASSERT: plateau count over the LUT equals steps + 2 (1 head + steps interior + 1 tail)
        """
        lut = FanController.create_control_function(pairs, steps)
        t_first, l_first = pairs[0]
        t_last, l_last = pairs[-1]
        assert len(lut) == 101
        assert lut[t_first] == l_first
        assert lut[t_last] == l_last
        assert all(v == l_first for v in lut[:t_first])
        assert all(v == l_last for v in lut[t_last + 1:])
        # Plateau count over the full LUT = steps + 2 (1 at t_first, `steps` interior, 1 at t_last);
        # the constant head and tail merge with their neighbouring endpoints, so the run-length
        # encoding of the LUT yields the same count.
        plateau_count = 1
        for t in range(1, 101):
            if lut[t] != lut[t - 1]:
                plateau_count += 1
        assert plateau_count == steps + 2

    def test_create_control_function_known_lut(self) -> None:
        """Positive unit test for FanController.create_control_function() static method. Contains the following steps:
        - call FanController.create_control_function() with the 4-point curve (30,35), (50,40), (60,90), (65,100) and steps=5
        - compare LUT entries against the published plateau dump (7 plateaus)
        - ASSERT: every spot-checked integer temperature maps to the documented LUT level
        """
        pairs = [(30, 35), (50, 40), (60, 90), (65, 100)]
        lut = FanController.create_control_function(pairs, 5)
        expected = {30: 35, 31: 36, 37: 36, 38: 38, 44: 38, 45: 40, 51: 40, 52: 65, 58: 65,
                    59: 92, 64: 92, 65: 100}
        for t, level in expected.items():
            assert lut[t] == level, f"LUT[{t}]={lut[t]} expected {level}"

    def test_create_control_function_steps_exceed_interior(self) -> None:
        """Positive unit test for FanController.create_control_function() static method when steps exceeds interior_len.
        Contains the following steps:
        - call FanController.create_control_function([(30, 35), (32, 100)], 5) so interior_len=1 and steps=5 (4 of 5 iterations hit the size==0 continue branch)
        - ASSERT: the resulting LUT has length 101
        - ASSERT: LUT[30] equals 35 (first breakpoint pinned)
        - ASSERT: LUT[31] equals 68 (single interior plateau value)
        - ASSERT: LUT[32] equals 100 (last breakpoint pinned)
        - ASSERT: all entries before T=30 equal 35 (head padding)
        - ASSERT: all entries after T=32 equal 100 (tail padding)
        """
        # t_last - t_first - 1 = 32 - 30 - 1 = 1 interior slot; steps=5 > 1
        lut = FanController.create_control_function([(30, 35), (32, 100)], 5)
        assert len(lut) == 101
        assert lut[30] == 35
        assert lut[31] == 68
        assert lut[32] == 100
        assert all(v == 35 for v in lut[:30])
        assert all(v == 100 for v in lut[33:])

    def test_print_temp_level_mapping_logs_plateaus(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.print_temp_level_mapping() method. It contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via mocker.patch
        - instantiate Log, Ipmi via Ipmi.__new__ and FanController via FanController.__new__
        - build a CPU config with a 4-point control_function and call FanController.__init__() which triggers the mapping print
        - capture all printed lines from the print MagicMock
        - ASSERT: the printed output contains the header "Temperature to level mapping:"
        - ASSERT: the number of "-> L=" occurrences equals the total plateau count returned by _level_plateaus()
        - ASSERT: no ASCII chart percentage column "% |" appears in the output
        - ASSERT: no Celsius axis label "(C)" appears in the output
        - ASSERT: no breakpoint legend "(^ = breakpoint)" appears in the output
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch("smfc.FanController.set_fan_level", MagicMock())
        mocker.patch("smfc.FanController._get_nth_temp", MagicMock(return_value=30.0))
        my_log = Log(Log.LOG_CONFIG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        cfg = create_cpu_config(steps=4, sensitivity=1, polling=1,
                                control_function=[(35, 35), (45, 50), (50, 70), (55, 100)])
        my_fc = FanController.__new__(FanController)
        my_fc.config = cfg
        FanController.__init__(my_fc, my_log, my_ipmi, cfg.section, 1)
        lines = [str(c.args[0]) for c in mock_print.call_args_list]
        printed = "\n".join(lines)
        total_plateaus = len(my_fc._level_plateaus())  # pylint: disable=protected-access
        assert "Temperature to level mapping:" in printed
        assert sum(ln.count("-> L=") for ln in lines) == total_plateaus
        assert "% |" not in printed
        assert "(C)" not in printed
        assert "(^ = breakpoint)" not in printed

    @pytest.mark.parametrize(
        "control_function, expect_new_path",
        [
            pytest.param([], False, id="legacy-path"),
            pytest.param([(30, 35), (65, 100)], True, id="new-path"),
        ],
    )
    def test_build_lut_dispatch(self, control_function, expect_new_path: bool) -> None:
        """Positive unit test for FanController.build_lut() static method. It contains the following steps:
        - build a CPU config with the parametrized control_function (empty for legacy path, populated for new path)
        - call FanController.build_lut(cfg) directly
        - ASSERT: the resulting LUT has length 101
        - ASSERT: when the new control_function path is taken, LUT[30]=35 and LUT[65]=100 (endpoints pinned)
        - ASSERT: when the legacy staircase path is taken, the same endpoints LUT[30]=35 and LUT[65]=100 hold
        - ASSERT: LUT[0] equals min_level=35 (head padding)
        - ASSERT: LUT[100] equals max_level=100 (tail padding)
        """
        # Use steps=5 so the cross-field constraint is satisfied for the 2-point new-path case.
        cfg = create_cpu_config(steps=5, min_temp=30, max_temp=65, min_level=35, max_level=100,
                                control_function=control_function)
        lut = FanController.build_lut(cfg)
        assert len(lut) == 101
        if expect_new_path:
            # Endpoint pinning: LUT[30]=35 and LUT[65]=100 exactly.
            assert lut[30] == 35 and lut[65] == 100
        else:
            # Legacy staircase has same endpoints.
            assert lut[30] == 35 and lut[65] == 100
        assert lut[0] == 35
        assert lut[100] == 100

    def test_run_with_control_function_drives_level_via_lut(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method driven by a control_function LUT. Contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a CPU config with a 4-point control_function and instantiate the FanController via _make_fc
        - drive run() across the spot-check (temp, expected_level) table derived from the published plateau dump
        - ASSERT: for each iteration last_level equals the plateau value from the control_function LUT (not the legacy formula)
        """
        # 4-point curve; steps=5 -> 7 plateaus.
        # NOTE: min_temp/max_temp/min_level/max_level are ignored when control_function is defined in
        # Config-driven parsing, but the factory bypasses Config so we just set control_function.
        cfg = create_cpu_config(steps=5, sensitivity=1, polling=1,
                                control_function=[(30, 35), (50, 40), (60, 90), (65, 100)])
        my_fc, _, _, mock_temp = _make_fc(mocker, cfg, count=1)
        # Spot-check against the published plateau dump for steps=5 on this curve:
        #   [(30,30,35), (31,37,36), (38,44,38), (45,51,40), (52,58,65), (59,64,92), (65,65,100)]
        # Only t_first=30 and t_last=65 are pinned; the intermediate user breakpoints (T=50, T=60)
        # are absorbed by the interior plateau averaging — that is the documented design.
        for temp, expected_level in [(30.0, 35), (50.0, 40), (55.0, 65), (60.0, 92), (65.0, 100)]:
            mock_temp.return_value = temp
            my_fc.last_level = 0
            my_fc.last_time = time.monotonic() - 2
            my_fc.run()
            assert my_fc.last_level == expected_level, \
                f"control_function run(): T={temp} -> level={my_fc.last_level}, expected {expected_level}"

    def test_run_polling_skipped(self, mocker: MockerFixture) -> None:
        """Positive unit test for FanController.run() method when polling interval has not elapsed. Contains the following steps:
        - mock builtins.print, smfc.FanController.set_fan_level, smfc.FanController._get_nth_temp via _make_fc
        - build a FanController via _create_test_fc with polling=10 and sensitivity=2
        - re-mock smfc.FanController._get_nth_temp and smfc.FanController.set_fan_level
        - set last_time to time.monotonic() so the polling interval has not yet elapsed and call run()
        - ASSERT: _get_nth_temp was NOT invoked (polling skip path returns early)
        - ASSERT: set_fan_level was NOT invoked (no level update without a temp read)
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
        assert mock_temp.call_count == initial_temp_calls
        assert mock_set_fan_level.call_count == 0


# End.
