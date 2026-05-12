#!/usr/bin/env python3
#
#   test_log.py (C) 2021-2026, Peter Sulyok
#   Unit test for smfc.Log() class.
#
import syslog
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc.log import Log


class TestLog:
    """Unit test class for smfc.Log() class"""

    @pytest.mark.parametrize(
        "level, output, error_str",
        [
            # LOG_NONE to STDOUT
            (Log.LOG_NONE, Log.LOG_STDOUT, "Log.__init__() p1"),
            # LOG_ERROR to STDOUT
            (Log.LOG_ERROR, Log.LOG_STDOUT, "Log.__init__() p2"),
            # LOG_CONFIG to STDOUT
            (Log.LOG_CONFIG, Log.LOG_STDOUT, "Log.__init__() p3"),
            # LOG_INFO to STDOUT
            (Log.LOG_INFO, Log.LOG_STDOUT, "Log.__init__() p4"),
            # LOG_DEBUG to STDOUT
            (Log.LOG_DEBUG, Log.LOG_STDOUT, "Log.__init__() p5"),
            # LOG_NONE to STDERR
            (Log.LOG_NONE, Log.LOG_STDERR, "Log.__init__() p6"),
            # LOG_ERROR to STDERR
            (Log.LOG_ERROR, Log.LOG_STDERR, "Log.__init__() p7"),
            # LOG_CONFIG to STDERR
            (Log.LOG_CONFIG, Log.LOG_STDERR, "Log.__init__() p8"),
            # LOG_INFO to STDERR
            (Log.LOG_INFO, Log.LOG_STDERR, "Log.__init__() p9"),
            # LOG_DEBUG to STDERR
            (Log.LOG_DEBUG, Log.LOG_STDERR, "Log.__init__() p10"),
            # LOG_NONE to SYSLOG
            (Log.LOG_NONE, Log.LOG_SYSLOG, "Log.__init__() p11"),
            # LOG_ERROR to SYSLOG
            (Log.LOG_ERROR, Log.LOG_SYSLOG, "Log.__init__() p12"),
            # LOG_CONFIG to SYSLOG
            (Log.LOG_CONFIG, Log.LOG_SYSLOG, "Log.__init__() p13"),
            # LOG_INFO to SYSLOG
            (Log.LOG_INFO, Log.LOG_SYSLOG, "Log.__init__() p14"),
            # LOG_DEBUG to SYSLOG
            (Log.LOG_DEBUG, Log.LOG_SYSLOG, "Log.__init__() p15"),
        ],
    )
    def test_init_p1(self, mocker: MockerFixture, level: int, output: int, error_str: str) -> None:
        """Positive unit test for Log.__init__() method. It contains the following steps:
        - mock print(), syslog.openlog(), and syslog.syslog() functions
        - initialize a Log class instance with a specified level and output values
        - ASSERT: if the class attributes contain different values that were passed to __init__
        - ASSERT: if the mocked system functions were called wrong number of times
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_syslog_openlog = MagicMock()
        mocker.patch("syslog.openlog", mock_syslog_openlog)
        mock_syslog_syslog = MagicMock()
        mocker.patch("syslog.syslog", mock_syslog_syslog)
        my_log = Log(level, output)
        assert my_log.log_level == level, error_str
        assert my_log.log_output == output, error_str
        if my_log.log_output is Log.LOG_STDOUT:
            assert my_log.msg == my_log.msg_to_stdout, error_str
        elif my_log.log_output is Log.LOG_STDERR:
            assert my_log.msg == my_log.msg_to_stderr, error_str
        elif my_log.log_output == Log.LOG_SYSLOG:
            assert my_log.msg == my_log.msg_to_syslog, error_str

    @pytest.mark.parametrize(
        "level, output, error_str",
        [
            # Invalid level: 100
            (100, Log.LOG_STDOUT, "Log.__init__() n1"),
            # Invalid output: 100
            (Log.LOG_ERROR, 100, "Log.__init__() n2"),
        ],
    )
    def test_init_n1(self, mocker: MockerFixture, level: int, output: int, error_str: str) -> None:
        """Negative unit test for Log.__init__() method. It contains the following steps:
        - initialize a Log class instance with specified level and output values
        - mock print() function
        - ASSERT: if __init__ does not raise an exception in case of invalid value
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        with pytest.raises(ValueError) as cm:
            Log(level, output)
        assert cm.type is ValueError, error_str

    @pytest.mark.parametrize(
        "level, syslog_level, error_str",
        [
            # LOG_ERROR maps to LOG_ERR
            (Log.LOG_ERROR, syslog.LOG_ERR, "Log.map_to_syslog() p1"),
            # LOG_CONFIG maps to LOG_INFO
            (Log.LOG_CONFIG, syslog.LOG_INFO, "Log.map_to_syslog() p2"),
            # LOG_INFO maps to LOG_INFO
            (Log.LOG_INFO, syslog.LOG_INFO, "Log.map_to_syslog() p3"),
            # LOG_DEBUG maps to LOG_DEBUG
            (Log.LOG_DEBUG, syslog.LOG_DEBUG, "Log.map_to_syslog() p4"),
            # Invalid level: 1000 maps to LOG_ERR
            (1000, syslog.LOG_ERR, "Log.map_to_syslog() p5"),
            # Invalid level: -1 maps to LOG_ERR
            (-1, syslog.LOG_ERR, "Log.map_to_syslog() p6"),
        ],
    )
    def test_mts(self, level: int, syslog_level: int, error_str: str) -> None:
        """Positive unit test for Log.map_to_syslog() method. It contains the following steps:
        - initialize a Log class instance
        - call map_to_syslog with a specified level
        - ASSERT: if map_to_syslog function maps a specified log levels to a wrong syslog level value
        """
        assert Log.map_to_syslog(level) == syslog_level, error_str

    @pytest.mark.parametrize(
        "level, level_str, error_str",
        [
            # LOG_NONE to "NONE"
            (Log.LOG_NONE, "NONE", "Log.level_to_str() p1"),
            # LOG_ERROR to "ERROR"
            (Log.LOG_ERROR, "ERROR", "Log.level_to_str() p2"),
            # LOG_CONFIG to "CONFIG"
            (Log.LOG_CONFIG, "CONFIG", "Log.level_to_str() p3"),
            # LOG_INFO to "INFO"
            (Log.LOG_INFO, "INFO", "Log.level_to_str() p4"),
            # LOG_DEBUG to "DEBUG"
            (Log.LOG_DEBUG, "DEBUG", "Log.level_to_str() p5"),
            # Invalid level: -1 to "NONE"
            (-1, "NONE", "Log.level_to_str() p6"),
            # Invalid level: 1000 to "NONE"
            (1000, "NONE", "Log.level_to_str() p7"),
        ],
    )
    def test_lts(self, level: int, level_str: str, error_str: str) -> None:
        """Positive unit test for Log.level_to_str() method. It contains the following steps:
        - call level_to_str() with a specified level
        - ASSERT: if level_to_str function maps a log level to an invalid string value
        """
        assert Log.level_to_str(level) == level_str, error_str

    @pytest.mark.parametrize(
        "level, output, msg_level, count, error_str",
        [
            (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() p1"),
            (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_ERROR, 0, "Log.msg_to_xxx() p2"),
            (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() p3"),
            (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_INFO, 0, "Log.msg_to_xxx() p4"),
            (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p5"),
            (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() p6"),
            (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_ERROR, 0, "Log.msg_to_xxx() p7"),
            (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() p8"),
            (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_INFO, 0, "Log.msg_to_xxx() p9"),
            (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p10"),
            (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() p11"),
            (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_ERROR, 0, "Log.msg_to_xxx() p12"),
            (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() p13"),
            (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "Log.msg_to_xxx() p14"),
            (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p15"),
            (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() p16"),
            (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p17"),
            (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() p18"),
            (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_INFO, 0, "Log.msg_to_xxx() p19"),
            (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p20"),
            (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() p21"),
            (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p22"),
            (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() p23"),
            (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_INFO, 0, "Log.msg_to_xxx() p24"),
            (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p25"),
            (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() p26"),
            (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p27"),
            (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() p28"),
            (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "Log.msg_to_xxx() p29"),
            (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p30"),
            (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() p31"),
            (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p32"),
            (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() p33"),
            (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_INFO, 0, "Log.msg_to_xxx() p34"),
            (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p35"),
            (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() p36"),
            (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p37"),
            (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() p38"),
            (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_INFO, 0, "Log.msg_to_xxx() p39"),
            (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p40"),
            (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() p41"),
            (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p42"),
            (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() p43"),
            (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "Log.msg_to_xxx() p44"),
            (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p45"),
            (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() p46"),
            (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p47"),
            (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() p48"),
            (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_INFO, 1, "Log.msg_to_xxx() p49"),
            (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p50"),
            (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() p51"),
            (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p52"),
            (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() p53"),
            (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_INFO, 1, "Log.msg_to_xxx() p54"),
            (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p55"),
            (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() p56"),
            (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p57"),
            (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() p58"),
            (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_INFO, 1, "Log.msg_to_xxx() p59"),
            (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() p60"),
            (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() p61"),
            (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p62"),
            (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() p63"),
            (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_INFO, 1, "Log.msg_to_xxx() p64"),
            (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_DEBUG, 1, "Log.msg_to_xxx() p65"),
            (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() p66"),
            (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p67"),
            (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() p68"),
            (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_INFO, 1, "Log.msg_to_xxx() p69"),
            (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_DEBUG, 1, "Log.msg_to_xxx() p70"),
            (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() p71"),
            (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "Log.msg_to_xxx() p72"),
            (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() p73"),
            (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_INFO, 1, "Log.msg_to_xxx() p74"),
            (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_DEBUG, 1, "Log.msg_to_xxx() p75"),
        ],
    )
    def test_msg_to_xxx(self, mocker: MockerFixture, level: int, output: int, msg_level: int, count: int,
                        error_str: str) -> None:
        """Positive unit test for Log.msg_to_xxx() method. It contains the following steps:
        - mock print() and syslog.syslog() functions
        - initialize a Log class instance with a specified level and output
        - calls Log.msg() with a specified level and log message
        - ASSERT: if msg() function calls print and/or syslog functions other times than expected
          (in case of DEBUG level there are additional 3 calls)
        - delete the Log instance
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_syslog_openlog = MagicMock()
        mocker.patch("syslog.openlog", mock_syslog_openlog)
        mock_syslog_syslog = MagicMock()
        mocker.patch("syslog.syslog", mock_syslog_syslog)
        my_log = Log(level, output)
        my_log.msg(msg_level, "This is a test log message.")
        if output == Log.LOG_STDOUT:
            assert mock_print.call_count == count, error_str
        elif output == Log.LOG_STDERR:
            assert mock_print.call_count == count, error_str
        elif output == Log.LOG_SYSLOG:
            assert mock_syslog_syslog.call_count == count, error_str


# End.
