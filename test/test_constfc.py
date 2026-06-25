#!/usr/bin/env python3
#
#   test_constfc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.ConstFc() class.
#
from typing import List, Tuple
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, ConstFc
from smfc.config import Config
from .test_config_builders import create_const_config


def _make_const_fc(mocker: MockerFixture, **cfg_kwargs) -> Tuple[ConstFc, Log, Ipmi]:
    """Build a ConstFc from a const config (print mocked). Returns (fc, log, ipmi).

    ConstFc is not a FanController subclass (no device discovery / hwmon), so it does not use the shared
    test_fc_helpers builders; this small local helper just removes the repeated construction boilerplate.
    """
    mocker.patch("builtins.print", MagicMock())
    cfg = create_const_config(enabled=True, **cfg_kwargs)
    log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
    ipmi = Ipmi.__new__(Ipmi)
    return ConstFc(log, ipmi, cfg), log, ipmi


class TestConstFc:
    """Unit test class for smfc.ConstFc() class"""

    @pytest.mark.parametrize(
        "ipmi_zone, polling, level",
        [
            pytest.param([0], 30, 45, id="1zone"),
            pytest.param([0, 1], 35, 55, id="2zones"),
            pytest.param([0, 1, 2], 40, 60, id="3zones"),
            pytest.param([0, 1, 2], 45, 65, id="3zones-alt"),
        ],
    )
    def test_init_sets_attributes_from_config(self, mocker: MockerFixture, ipmi_zone: List[int], polling: float,
                                              level: int):
        """Positive unit test for ConstFc.__init__() method. It contains the following steps:
        - mock print() function
        - instantiate ConstFc via _make_const_fc() helper with the given ipmi_zone/polling/level
        - ASSERT: fc.log keeps the Log reference passed to __init__
        - ASSERT: fc.ipmi keeps the Ipmi reference passed to __init__
        - ASSERT: fc.name equals fc.config.section
        - ASSERT: fc.config.ipmi_zone matches the configured value
        - ASSERT: fc.config.polling matches the configured value
        - ASSERT: fc.config.level matches the configured value
        """
        fc, log, ipmi = _make_const_fc(mocker, ipmi_zone=ipmi_zone, polling=polling, level=level)
        assert fc.log is log
        assert fc.ipmi is ipmi
        assert fc.name == fc.config.section
        assert fc.config.ipmi_zone == ipmi_zone
        assert fc.config.polling == polling
        assert fc.config.level == level

    def test_init_applies_defaults(self, mocker: MockerFixture):
        """Positive unit test for ConstFc.__init__() method with default configuration. It contains the following steps:
        - mock print() function
        - instantiate ConstFc via _make_const_fc() helper using a default const config (only enabled set)
        - ASSERT: fc.log keeps the Log reference passed to __init__
        - ASSERT: fc.ipmi keeps the Ipmi reference passed to __init__
        - ASSERT: fc.name equals fc.config.section
        - ASSERT: fc.config.ipmi_zone falls back to [Config.HD_ZONE]
        - ASSERT: fc.config.polling falls back to Config.DV_CONST_POLLING
        - ASSERT: fc.config.level falls back to Config.DV_CONST_LEVEL
        """
        fc, log, ipmi = _make_const_fc(mocker)
        assert fc.log is log
        assert fc.ipmi is ipmi
        assert fc.name == fc.config.section
        assert fc.config.ipmi_zone == [Config.HD_ZONE]
        assert fc.config.polling == Config.DV_CONST_POLLING
        assert fc.config.level == Config.DV_CONST_LEVEL

    @pytest.mark.parametrize(
        "ipmi_zone",
        [
            pytest.param("!", id="special-char"),
            pytest.param("-1", id="negative"),
            pytest.param("1; 2", id="wrong-separator"),
        ],
    )
    def test_init_rejects_invalid_zones(self, ipmi_zone: str):
        """Negative unit test for Config.parse_ipmi_zones() method (CONST zone parsing). It contains the
        following steps:
        - call Config.parse_ipmi_zones() with an invalid ipmi_zone string
        - ASSERT: Config.parse_ipmi_zones() raises ValueError (zone validation happens at parse time)
        """
        with pytest.raises(ValueError):
            Config.parse_ipmi_zones(ipmi_zone)

    @pytest.mark.parametrize(
        "ipmi_zone, read_level, level",
        [
            pytest.param([0], 30, 30, id="1zone-no-drift"),
            pytest.param([0, 1], 30, 30, id="2zones-no-drift"),
            pytest.param([0, 1, 2], 30, 30, id="3zones-no-drift"),
            pytest.param([0], 30, 40, id="1zone-drift"),
            pytest.param([0, 1], 30, 40, id="2zones-drift"),
            pytest.param([0, 1, 2], 30, 40, id="3zones-drift"),
        ],
    )
    def test_run_applies_level_on_drift(self, mocker: MockerFixture, ipmi_zone: List[int], read_level: int,
                                        level: int):
        """Positive unit test for ConstFc.run() method. It contains the following steps:
        - mock print(), Ipmi.get_fan_level() and Ipmi.set_fan_level()
        - instantiate ConstFc via _make_const_fc() helper with the given ipmi_zone/polling/level
        - force fc.last_time into the past so the polling interval has elapsed
        - call ConstFc.run()
        - ASSERT: Ipmi.get_fan_level() is invoked once per configured zone
        - ASSERT: Ipmi.set_fan_level() is invoked once per zone only when the read level differs from the target
        """
        mock_get = MagicMock(return_value=read_level)
        mocker.patch("smfc.Ipmi.get_fan_level", mock_get)
        mock_set = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set)
        fc, _, _ = _make_const_fc(mocker, ipmi_zone=ipmi_zone, polling=3.0, level=level)
        fc.last_time = -100.0
        fc.run()
        assert mock_get.call_count == len(ipmi_zone)
        if read_level != level:
            assert mock_set.call_count == len(ipmi_zone)

    @pytest.mark.parametrize(
        "ipmi_zone, level",
        [
            pytest.param([0], 45, id="1zone"),
            pytest.param([0, 1], 55, id="2zones"),
        ],
    )
    def test_run_deferred_skips_ipmi(self, mocker: MockerFixture, ipmi_zone: List[int], level: int):
        """Positive unit test for ConstFc.run() method in deferred-apply mode. It contains the following steps:
        - mock print(), Ipmi.get_fan_level() and Ipmi.set_fan_level()
        - instantiate ConstFc via _make_const_fc() helper with the given ipmi_zone/level
        - set fc.deferred_apply = True and force fc.last_time into the past
        - call ConstFc.run()
        - ASSERT: fc.last_level is updated to the configured target level
        - ASSERT: Ipmi.get_fan_level() is not called (level is only stored for zone arbitration)
        - ASSERT: Ipmi.set_fan_level() is not called (level is only stored for zone arbitration)
        """
        mock_get = MagicMock()
        mocker.patch("smfc.Ipmi.get_fan_level", mock_get)
        mock_set = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set)
        fc, _, _ = _make_const_fc(mocker, ipmi_zone=ipmi_zone, polling=3.0, level=level)
        fc.deferred_apply = True
        fc.last_time = -100.0
        fc.run()
        assert fc.last_level == level
        assert mock_get.call_count == 0
        assert mock_set.call_count == 0


# End.
