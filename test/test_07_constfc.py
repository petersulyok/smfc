#!/usr/bin/env python3
#
#   test_04_constfc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.ConstFc() class.
#
from configparser import ConfigParser
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, ConstFc


class TestConstFc:
    """Unit test class for smfc.ConstFc() class"""

    @pytest.mark.parametrize(
        "ipmi_zone, polling, level, error",
        [
            ("0", 30, 45, "ConstFc.__init__() 1"),
            ("0, 1", 35, 55, "ConstFc.__init__() 2"),
            ("0, 1, 2", 40, 60, "ConstFc.__init__() 3"),
            ("0 1 2", 45, 65, "ConstFc.__init__() 4"),
        ],
    )
    def test_init_p1(self, mocker: MockerFixture, ipmi_zone: str, polling: float, level: int, error: str):
        """Positive unit test for ConstFc.__init__() method. It contains the following steps:
        - mock print() function
        - initialize a Config, Log, Ipmi, and ConstFc classes
        - ASSERT: if the ConstFc class attributes contain different from passed values to __init__
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        my_config = ConfigParser()
        my_config[ConstFc.CS_CONST_FC] = {
            ConstFc.CV_CONST_FC_ENABLED: "1",
            ConstFc.CV_CONST_FC_IPMI_ZONE: ipmi_zone,
            ConstFc.CV_CONST_FC_POLLING: str(polling),
            ConstFc.CV_CONST_FC_LEVEL: str(level),
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constfc = ConstFc(my_log, my_ipmi, my_config)
        assert my_constfc.log == my_log, error
        assert my_constfc.ipmi == my_ipmi, error
        assert my_constfc.ipmi_zone == [int(s) for s in ipmi_zone.split("," if "," in ipmi_zone else " ")], error
        assert my_constfc.name == ConstFc.CS_CONST_FC, error
        assert my_constfc.polling == polling, error
        assert my_constfc.level == level, error

    @pytest.mark.parametrize("error", [("ConstFc.__init__() 5")])
    def test_init_p2(self, mocker: MockerFixture, error: str):
        """Positive unit test ConstFc.__init__() method. It contains the following steps:
        - mock print() function
        - initialize a Config, Log, Ipmi, and ConstFc classes
        - ASSERT: if the ConstFc class attributes contain different from default configuration values
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        my_config = ConfigParser()
        my_config[ConstFc.CS_CONST_FC] = {ConstFc.CV_CONST_FC_ENABLED: "1"}
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constfc = ConstFc(my_log, my_ipmi, my_config)
        assert my_constfc.log == my_log, error
        assert my_constfc.ipmi == my_ipmi
        assert my_constfc.ipmi_zone == [Ipmi.HD_ZONE], error
        assert my_constfc.name == ConstFc.CS_CONST_FC, error
        assert my_constfc.polling == 30, error
        assert my_constfc.level == 50, error

    @pytest.mark.parametrize(
        "ipmi_zone, polling, level, error",
        [
            # invalid IPMI zone
            ("!", 30, 40, "ConstFc.__init__() 6"),
            ("-1", 30, 40, "ConstFc.__init__() 7"),
            ("1; 2", 30, 40, "ConstFc.__init__() 8"),
            # invalid polling
            ("0", -1, 40, "ConstFc.__init__() 9"),
            # invalid level
            ("0", 30, -1, "ConstFc.__init__() 10"),
            ("0", 30, 102, "ConstFc.__init__() 11"),
        ],
    )
    def test_init_n(self, mocker: MockerFixture, ipmi_zone: str, polling: float, level: int, error: str):
        """Negative unit test for ConstFc.__init__() method. It contains the following steps:
        - mock print() function
        - initialize a Config, Log, Ipmi, and ConstFc classes
        - ASSERT: if no ValueError assertion will be generated due to invalid configuration
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        my_config = ConfigParser()
        my_config[ConstFc.CS_CONST_FC] = {
            ConstFc.CV_CONST_FC_ENABLED: "1",
            ConstFc.CV_CONST_FC_IPMI_ZONE: ipmi_zone,
            ConstFc.CV_CONST_FC_POLLING: str(polling),
            ConstFc.CV_CONST_FC_LEVEL: str(level),
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        with pytest.raises(Exception) as cm:
            ConstFc(my_log, my_ipmi, my_config)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "ipmi_zone, read_level, level, error",
        [
            ("0", 30, 30, "ConstFc.run() 1"),
            ("0, 1", 30, 30, "ConstFc.run() 2"),
            ("0  1  2", 30, 30, "ConstFc.run() 3"),
            ("0", 30, 40, "ConstFc.run() 4"),
            ("0  1", 30, 40, "ConstFc.run() 5"),
            ("0, 1, 2", 30, 40, "ConstFc.run() 6"),
        ],
    )
    def test_run_p(self, mocker: MockerFixture, ipmi_zone: str, read_level: int, level: int, error: str):
        """Positive unit test for ConstFc.__init__() method. It contains the following steps:
        - mock print() function
        - initialize a Config, Log, Ipmi, and ConstFc classes
        - call ConstFc.run() function
        - ASSERT: if the number of Ipmi.get_fan_level() and Ipmi.set_fan_level() calls different from expected.
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_getfanlevel = MagicMock()
        mock_getfanlevel.return_value = read_level
        mocker.patch("smfc.Ipmi.get_fan_level", mock_getfanlevel)
        mock_setfanlevel = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_setfanlevel)
        my_config = ConfigParser()
        my_config[ConstFc.CS_CONST_FC] = {
            ConstFc.CV_CONST_FC_ENABLED: "1",
            ConstFc.CV_CONST_FC_IPMI_ZONE: ipmi_zone,
            ConstFc.CV_CONST_FC_POLLING: str(3.0),
            ConstFc.CV_CONST_FC_LEVEL: str(level),
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constfc = ConstFc(my_log, my_ipmi, my_config)
        my_constfc.level = level
        my_constfc.last_time = -100.0
        my_constfc.run()
        assert mock_getfanlevel.call_count == len(my_constfc.ipmi_zone), error
        if read_level != level:
            assert mock_setfanlevel.call_count == len(my_constfc.ipmi_zone), error

    @pytest.mark.parametrize(
        "ipmi_zone, level, error",
        [
            ("0", 45, "ConstFc.run() deferred 1"),
            ("0, 1", 55, "ConstFc.run() deferred 2"),
        ],
    )
    def test_run_deferred(self, mocker: MockerFixture, ipmi_zone: str, level: int, error: str):
        """Test that ConstFc.run() in deferred mode sets last_level but skips IPMI calls."""
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_getfanlevel = MagicMock()
        mocker.patch("smfc.Ipmi.get_fan_level", mock_getfanlevel)
        mock_setfanlevel = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_setfanlevel)
        my_config = ConfigParser()
        my_config[ConstFc.CS_CONST_FC] = {
            ConstFc.CV_CONST_FC_ENABLED: "1",
            ConstFc.CV_CONST_FC_IPMI_ZONE: ipmi_zone,
            ConstFc.CV_CONST_FC_POLLING: str(3.0),
            ConstFc.CV_CONST_FC_LEVEL: str(level),
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constfc = ConstFc(my_log, my_ipmi, my_config)
        my_constfc.deferred_apply = True
        my_constfc.last_time = -100.0
        my_constfc.run()
        assert my_constfc.last_level == level, error
        assert mock_getfanlevel.call_count == 0, error
        assert mock_setfanlevel.call_count == 0, error


# End.
