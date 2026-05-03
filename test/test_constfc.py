#!/usr/bin/env python3
#
#   test_constfc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.ConstFc() class.
#
from typing import List
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, ConstFc
from smfc.config import Config
from .test_data import create_const_config


class TestConstFc:
    """Unit test class for smfc.ConstFc() class"""

    @pytest.mark.parametrize(
        "ipmi_zone, polling, level, error",
        [
            # Single zone
            ([0], 30, 45, "ConstFc.__init__() 1"),
            # Comma-separated zones
            ([0, 1], 35, 55, "ConstFc.__init__() 2"),
            # Three comma-separated zones
            ([0, 1, 2], 40, 60, "ConstFc.__init__() 3"),
            # Space-separated zones
            ([0, 1, 2], 45, 65, "ConstFc.__init__() 4"),
        ],
    )
    def test_init_p1(self, mocker: MockerFixture, ipmi_zone: List[int], polling: float, level: int, error: str):
        """Positive unit test for ConstFc.__init__() method. It contains the following steps:
        - mock print() function
        - initialize a Config, Log, Ipmi, and ConstFc classes
        - ASSERT: if the ConstFc class attributes contain different from passed values to __init__
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        cfg = create_const_config(enabled=True, ipmi_zone=ipmi_zone, polling=polling, level=level)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constfc = ConstFc(my_log, my_ipmi, cfg)
        assert my_constfc.log == my_log, error
        assert my_constfc.ipmi == my_ipmi, error
        assert my_constfc.config.ipmi_zone == ipmi_zone, error
        assert my_constfc.name == cfg.section, error
        assert my_constfc.config.polling == polling, error
        assert my_constfc.config.level == level, error

    @pytest.mark.parametrize("error", [("ConstFc.__init__() 5")])
    def test_init_p2(self, mocker: MockerFixture, error: str):
        """Positive unit test ConstFc.__init__() method. It contains the following steps:
        - mock print() function
        - initialize a Config, Log, Ipmi, and ConstFc classes
        - ASSERT: if the ConstFc class attributes contain different from default configuration values
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        cfg = create_const_config(enabled=True)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constfc = ConstFc(my_log, my_ipmi, cfg)
        assert my_constfc.log == my_log, error
        assert my_constfc.ipmi == my_ipmi
        assert my_constfc.config.ipmi_zone == [Config.HD_ZONE], error
        assert my_constfc.name == cfg.section, error
        assert my_constfc.config.polling == 30, error
        assert my_constfc.config.level == 50, error

    @pytest.mark.parametrize(
        "ipmi_zone, polling, level, error",
        [
            # Invalid IPMI zone - special character
            ("!", 30, 40, "ConstFc.__init__() 6"),
            # Invalid IPMI zone - negative
            ("-1", 30, 40, "ConstFc.__init__() 7"),
            # Invalid IPMI zone - wrong separator
            ("1; 2", 30, 40, "ConstFc.__init__() 8"),
            # NOTE: Invalid polling/level tests (9-11) moved to Config validation tests,
            # since validation now happens in Config class, not in ConstFc.__init__()
        ],
    )
    def test_init_n(self, mocker: MockerFixture, ipmi_zone, polling: float, level: int, error: str):
        """Negative unit test for ConstFc.__init__() method. It contains the following steps:
        - mock print() function
        - test that Config.parse_ipmi_zones() raises ValueError for invalid zone strings
        - ASSERT: if no ValueError assertion will be generated due to invalid configuration
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        with pytest.raises(Exception) as cm:
            # Invalid zone strings should fail at parse time
            Config.parse_ipmi_zones(ipmi_zone)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "ipmi_zone, read_level, level, error",
        [
            # Single zone, same level
            ([0], 30, 30, "ConstFc.run() 1"),
            # Two zones, same level
            ([0, 1], 30, 30, "ConstFc.run() 2"),
            # Three zones space-separated, same level
            ([0, 1, 2], 30, 30, "ConstFc.run() 3"),
            # Single zone, different level
            ([0], 30, 40, "ConstFc.run() 4"),
            # Two zones space-separated, different level
            ([0, 1], 30, 40, "ConstFc.run() 5"),
            # Three zones comma-separated, different level
            ([0, 1, 2], 30, 40, "ConstFc.run() 6"),
        ],
    )
    def test_run_p(self, mocker: MockerFixture, ipmi_zone: List[int], read_level: int, level: int, error: str):
        """Positive unit test for ConstFc.run() method. It contains the following steps:
        - mock print(), Ipmi.get_fan_level(), Ipmi.set_fan_level() functions
        - initialize a Config, Log, Ipmi, and ConstFc classes
        - call ConstFc.run()
        - ASSERT: if the number of Ipmi.get_fan_level() and Ipmi.set_fan_level() calls different from expected
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_getfanlevel = MagicMock()
        mock_getfanlevel.return_value = read_level
        mocker.patch("smfc.Ipmi.get_fan_level", mock_getfanlevel)
        mock_setfanlevel = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_setfanlevel)
        cfg = create_const_config(enabled=True, ipmi_zone=ipmi_zone, polling=3.0, level=level)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constfc = ConstFc(my_log, my_ipmi, cfg)
        my_constfc.config.level = level
        my_constfc.last_time = -100.0
        my_constfc.run()
        assert mock_getfanlevel.call_count == len(my_constfc.config.ipmi_zone), error
        if read_level != level:
            assert mock_setfanlevel.call_count == len(my_constfc.config.ipmi_zone), error

    @pytest.mark.parametrize(
        "ipmi_zone, level, error",
        [
            # Single zone deferred
            ([0], 45, "ConstFc.run() 7"),
            # Two zones deferred
            ([0, 1], 55, "ConstFc.run() 8"),
        ],
    )
    def test_run_deferred(self, mocker: MockerFixture, ipmi_zone: List[int], level: int, error: str):
        """Positive unit test for ConstFc.run() method in deferred mode. It contains the following steps:
        - mock print(), Ipmi.get_fan_level(), Ipmi.set_fan_level() functions
        - initialize a Config, Log, Ipmi, and ConstFc classes
        - call ConstFc.run() with deferred=True
        - ASSERT: if last_level is not set or IPMI calls were made
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_getfanlevel = MagicMock()
        mocker.patch("smfc.Ipmi.get_fan_level", mock_getfanlevel)
        mock_setfanlevel = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_setfanlevel)
        cfg = create_const_config(enabled=True, ipmi_zone=ipmi_zone, polling=3.0, level=level)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constfc = ConstFc(my_log, my_ipmi, cfg)
        my_constfc.deferred_apply = True
        my_constfc.last_time = -100.0
        my_constfc.run()
        assert my_constfc.last_level == level, error
        assert mock_getfanlevel.call_count == 0, error
        assert mock_setfanlevel.call_count == 0, error


# End.
