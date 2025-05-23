#!/usr/bin/env python3
#
#   test_04_constzone.py (C) 2021-2025, Peter Sulyok
#   Unit tests for smfc.ConstZone() class.
#
from configparser import ConfigParser
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, ConstZone


class TestConstZone:
    """Unit test class for smfc.ConstZone() class"""

    @pytest.mark.parametrize(
        "ipmi_zone, polling, level, error", [
        ('0',       30, 45, 'ConstZone.__init__() 1'),
        ('0, 1',    35, 55, 'ConstZone.__init__() 2'),
        ('0, 1, 2', 40, 60, 'ConstZone.__init__() 3'),
        ('0 1 2',   45, 65, 'ConstZone.__init__() 4')
    ])
    def test_init_p1(self, mocker:MockerFixture, ipmi_zone: str, polling: float, level: int, error: str):
        """Positive unit test for ConstZone.__init__() method. It contains the following steps:
            - mock print() function
            - initialize a Config, Log, Ipmi, and ConstZone classes
            - ASSERT: if the ConstZone class attributes contain different from passed values to __init__
        """
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        my_config = ConfigParser()
        my_config[ConstZone.CS_CONST_ZONE] = {
            ConstZone.CV_CONST_ZONE_ENABLED: '1',
            ConstZone.CV_CONST_IPMI_ZONE: ipmi_zone,
            ConstZone.CV_CONST_ZONE_POLLING: str(polling),
            ConstZone.CV_CONST_ZONE_LEVEL: str(level)
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constzone = ConstZone(my_log, my_ipmi, my_config)
        assert my_constzone.log == my_log, error
        assert my_constzone.ipmi == my_ipmi, error
        assert my_constzone.ipmi_zone == [int(s) for s in ipmi_zone.split(',' if ',' in ipmi_zone else ' ')], error
        assert my_constzone.name == ConstZone.CS_CONST_ZONE, error
        assert my_constzone.polling == polling, error
        assert my_constzone.level == level, error

    @pytest.mark.parametrize("error", [
        ('ConstZone.__init__() 5')
    ])
    def test_init_p2(self, mocker:MockerFixture, error: str):
        """Positive unit test ConstZone.__init__() method. It contains the following steps:
            - mock print() function
            - initialize a Config, Log, Ipmi, and ConstZone classes
            - ASSERT: if the ConstZone class attributes contain different from default configuration values
        """
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        my_config = ConfigParser()
        my_config[ConstZone.CS_CONST_ZONE] = {
            ConstZone.CV_CONST_ZONE_ENABLED: '1'
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constzone = ConstZone(my_log, my_ipmi, my_config)
        assert my_constzone.log == my_log, error
        assert my_constzone.ipmi == my_ipmi
        assert my_constzone.ipmi_zone == [Ipmi.HD_ZONE], error
        assert my_constzone.name == ConstZone.CS_CONST_ZONE, error
        assert my_constzone.polling == 30, error
        assert my_constzone.level == 50, error

    @pytest.mark.parametrize("ipmi_zone, polling, level, error", [
        # invalid IPMI zone
        ('!',       30, 40,     'ConstZone.__init__() 6'),
        ('-1',      30, 40,     'ConstZone.__init__() 7'),
        ('1; 2',    30, 40,     'ConstZone.__init__() 8'),
        # invalid polling
        ('0',       -1, 40,     'ConstZone.__init__() 9'),
        # invalid level
        ('0',       30, -1,     'ConstZone.__init__() 10'),
        ('0',       30, 102,    'ConstZone.__init__() 11'),
    ])
    def test_init_n(self, mocker:MockerFixture, ipmi_zone: str, polling: float, level: int, error: str):
        """Negative unit test for ConstZone.__init__() method. It contains the following steps:
            - mock print() function
            - initialize a Config, Log, Ipmi, and ConstZone classes
            - ASSERT: if no ValueError assertion will be generated due to invalid configuration
        """
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        my_config = ConfigParser()
        my_config[ConstZone.CS_CONST_ZONE] = {
            ConstZone.CV_CONST_ZONE_ENABLED: '1',
            ConstZone.CV_CONST_IPMI_ZONE: ipmi_zone,
            ConstZone.CV_CONST_ZONE_POLLING: str(polling),
            ConstZone.CV_CONST_ZONE_LEVEL: str(level)
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        with pytest.raises(Exception) as cm:
            ConstZone(my_log, my_ipmi, my_config)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize(
        "ipmi_zone, read_level, level, error", [
        ('0',       30, 30, 'ConstZone.run() 1'),
        ('0, 1',    30, 30, 'ConstZone.run() 2'),
        ('0  1  2', 30, 30, 'ConstZone.run() 3'),
        ('0',       30, 40, 'ConstZone.run() 4'),
        ('0  1',    30, 40, 'ConstZone.run() 5'),
        ('0, 1, 2', 30, 40, 'ConstZone.run() 6')
    ])
    def test_run_p(self, mocker:MockerFixture, ipmi_zone: str, read_level: int, level: int, error: str):
        """Positive unit test for ConstZone.__init__() method. It contains the following steps:
            - mock print() function
            - initialize a Config, Log, Ipmi, and ConstZone classes
            - call ConstZone.run() function
            - ASSERT: if the number of Ipmi.get_fan_level() and Ipmi.set_fan_level() calls different from expected.
        """
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_getfanlevel = MagicMock()
        mock_getfanlevel.return_value = read_level
        mocker.patch('smfc.Ipmi.get_fan_level', mock_getfanlevel)
        mock_setfanlevel = MagicMock()
        mocker.patch('smfc.Ipmi.set_fan_level', mock_setfanlevel)
        my_config = ConfigParser()
        my_config[ConstZone.CS_CONST_ZONE] = {
            ConstZone.CV_CONST_ZONE_ENABLED: '1',
            ConstZone.CV_CONST_IPMI_ZONE: ipmi_zone,
            ConstZone.CV_CONST_ZONE_POLLING: str(30),
            ConstZone.CV_CONST_ZONE_LEVEL: str(level)
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_constzone = ConstZone(my_log, my_ipmi, my_config)
        my_constzone.level = level
        my_constzone.last_time = 0
        my_constzone.run()
        assert mock_getfanlevel.call_count == len(my_constzone.ipmi_zone), error
        if read_level != level:
            assert mock_setfanlevel.call_count == len(my_constzone.ipmi_zone), error


# End.
