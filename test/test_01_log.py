#!/usr/bin/env python3
#
#   test_01_log.py (C) 2021-2025, Peter Sulyok
#   Unit test for smfc.Log() class.
#
import syslog
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc.log import Log


class TestLog:
    """Unit test class for smfc.Log() class"""

    @pytest.mark.parametrize("level, output, error", [
        (Log.LOG_NONE, Log.LOG_STDOUT, "Log.__init__() 1"),
        (Log.LOG_ERROR, Log.LOG_STDOUT, "Log.__init__() 2"),
        (Log.LOG_CONFIG, Log.LOG_STDOUT, "Log.__init__() 3"),
        (Log.LOG_INFO, Log.LOG_STDOUT, "Log.__init__() 4"),
        (Log.LOG_DEBUG, Log.LOG_STDOUT, "Log.__init__() 5"),
        (Log.LOG_NONE, Log.LOG_STDERR, "Log.__init__() 6"),
        (Log.LOG_ERROR, Log.LOG_STDERR, "Log.__init__() 7"),
        (Log.LOG_CONFIG, Log.LOG_STDERR, "Log.__init__() 8"),
        (Log.LOG_INFO, Log.LOG_STDERR, "Log.__init__() 9"),
        (Log.LOG_DEBUG, Log.LOG_STDERR, "Log.__init__() 10"),
        (Log.LOG_NONE, Log.LOG_SYSLOG, "Log.__init__() 11"),
        (Log.LOG_ERROR, Log.LOG_SYSLOG, "Log.__init__() 12"),
        (Log.LOG_CONFIG, Log.LOG_SYSLOG, "Log.__init__() 13"),
        (Log.LOG_INFO, Log.LOG_SYSLOG, "Log.__init__() 14"),
        (Log.LOG_DEBUG, Log.LOG_SYSLOG, "Log.__init__() 15")
    ])
    def test_init_p1(self, mocker:MockerFixture, level: int, output: int, error: str) -> None:
        """Positive unit test for Log.__init__() method. It contains the following steps:
            - mock print(), syslog.openlog(), and syslog.syslog() functions
            - initialize a Log class instance with a specified level and output values
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - ASSERT: if the mocked system functions were called wrong number of times
        """
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_syslog_openlog = MagicMock()
        mocker.patch('syslog.openlog', mock_syslog_openlog)
        mock_syslog_syslog = MagicMock()
        mocker.patch('syslog.syslog', mock_syslog_syslog)
        my_log = Log(level, output)
        assert my_log.log_level == level, error
        assert my_log.log_output == output, error
        if my_log.log_output is Log.LOG_STDOUT:
            assert my_log.msg == my_log.msg_to_stdout, error
        elif my_log.log_output is Log.LOG_STDERR:
            assert my_log.msg == my_log.msg_to_stderr, error
        elif my_log.log_output == Log.LOG_SYSLOG:
            assert my_log.msg == my_log.msg_to_syslog, error

    @pytest.mark.parametrize("level, output, error", [
        (100, Log.LOG_STDOUT, "Log.__init__() 16"),
        (Log.LOG_ERROR, 100, "Log.__init__() 17")
    ])
    def test_init_n1(self, mocker: MockerFixture, level: int, output: int, error: str) -> None:
        """Negative unit test for Log.__init__() method. It contains the following steps:
            - initialize a Log class instance with specified level and output values
            - mock print() function
            - ASSERT: if __init__ does not raise an exception in case of invalid value
        """
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        with pytest.raises(ValueError) as cm:
            Log(level, output)
        assert cm.type is ValueError, error

    @pytest.mark.parametrize("level, syslog_level, error", [
        (Log.LOG_ERROR, syslog.LOG_ERR, "Log.map_to_syslog() 1"),
        (Log.LOG_CONFIG, syslog.LOG_INFO, "Log.map_to_syslog() 2"),
        (Log.LOG_INFO, syslog.LOG_INFO, "Log.map_to_syslog() 3"),
        (Log.LOG_DEBUG, syslog.LOG_DEBUG, "Log.map_to_syslog() 4"),
        (1000, syslog.LOG_ERR, "Log.map_to_syslog() 5"),
        (-1, syslog.LOG_ERR, "Log.map_to_syslog() 5")
    ])
    def test_mts(self, level: int, syslog_level: int, error: str) -> None:
        """Positive unit test for Log.map_to_syslog() method. It contains the following steps:
            - initialize a Log class instance
            - call map_to_syslog with a specified level
            - ASSERT: if map_to_syslog function maps a specified log levels to a wrong syslog level value
        """
        assert Log.map_to_syslog(level) == syslog_level, error

    @pytest.mark.parametrize("level, level_str, error", [
        (Log.LOG_NONE, 'NONE', "Log.level_to_str() 1"),
        (Log.LOG_ERROR, 'ERROR', "Log.level_to_str() 2"),
        (Log.LOG_CONFIG, 'CONFIG', "Log.level_to_str() 3"),
        (Log.LOG_INFO, 'INFO', "Log.level_to_str() 4"),
        (Log.LOG_DEBUG, 'DEBUG', "Log.level_to_str() 5"),
        (-1, 'NONE', "Log.level_to_str() 6"),
        (1000, 'NONE', "Log.level_to_str() 7")
    ])
    def test_lts(self, level: int, level_str: str, error: str) -> None:
        """Positive unit test for Log.level_to_str() method. It contains the following steps:
            - call level_to_str() with a specified level
            - ASSERT: if level_to_str function maps a log level to an invalid string value
        """
        assert Log.level_to_str(level) == level_str, error

    @pytest.mark.parametrize("level, output, msg_level, count, error", [
        (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() 1"),
        (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_ERROR, 0, "Log.msg_to_xxx() 2"),
        (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() 3"),
        (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_INFO, 0, "Log.msg_to_xxx() 3"),
        (Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 4"),

        (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() 5"),
        (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_ERROR, 0, "Log.msg_to_xxx() 6"),
        (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() 7"),
        (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_INFO, 0, "Log.msg_to_xxx() 8"),
        (Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 9"),

        (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() 10"),
        (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_ERROR, 0, "Log.msg_to_xxx() 11"),
        (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() 12"),
        (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "Log.msg_to_xxx() 13"),
        (Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 14"),

        (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() 15"),
        (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 16"),
        (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() 17"),
        (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_INFO, 0, "Log.msg_to_xxx() 18"),
        (Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 19"),

        (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() 20"),
        (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 21"),
        (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() 22"),
        (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_INFO, 0, "Log.msg_to_xxx() 23"),
        (Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 24"),

        (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() 25"),
        (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 26"),
        (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_CONFIG, 0, "Log.msg_to_xxx() 27"),
        (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "Log.msg_to_xxx() 28"),
        (Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 29"),

        (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() 30"),
        (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 31"),
        (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() 32"),
        (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_INFO, 0, "Log.msg_to_xxx() 33"),
        (Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 34"),

        (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() 35"),
        (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 36"),
        (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() 37"),
        (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_INFO, 0, "Log.msg_to_xxx() 38"),
        (Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 39"),

        (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() 40"),
        (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 41"),
        (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() 42"),
        (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "Log.msg_to_xxx() 43"),
        (Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 44"),

        (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() 45"),
        (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 46"),
        (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() 47"),
        (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_INFO, 1, "Log.msg_to_xxx() 48"),
        (Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 49"),

        (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() 50"),
        (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 51"),
        (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() 52"),
        (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_INFO, 1, "Log.msg_to_xxx() 53"),
        (Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 54"),

        (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() 55"),
        (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 56"),
        (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() 57"),
        (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_INFO, 1, "Log.msg_to_xxx() 58"),
        (Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "Log.msg_to_xxx() 59"),

        (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_NONE, 0, "Log.msg_to_xxx() 60"),
        (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 61"),
        (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() 62"),
        (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_INFO, 1, "Log.msg_to_xxx() 63"),
        (Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_DEBUG, 1, "Log.msg_to_xxx() 64"),

        (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_NONE, 0, "Log.msg_to_xxx() 65"),
        (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 66"),
        (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() 67"),
        (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_INFO, 1, "Log.msg_to_xxx() 68"),
        (Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_DEBUG, 1, "Log.msg_to_xxx() 69"),

        (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "Log.msg_to_xxx() 70"),
        (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "Log.msg_to_xxx() 71"),
        (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, "Log.msg_to_xxx() 72"),
        (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_INFO, 1, "Log.msg_to_xxx() 73"),
        (Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_DEBUG, 1, "Log.msg_to_xxx() 74")
    ])
    def test_msg_to_xxx(self, mocker:MockerFixture, level: int, output: int, msg_level: int, count: int,
                        error: str) -> None:
        """Positive unit test for Log.msg_to_xxx() method. It contains the following steps:
            - mock print() and syslog.syslog() functions
            - initialize a Log class instance with a specified level and output
            - calls Log.msg() with a specified level and log message
            - ASSERT: if msg() function calls print and/or syslog functions other times than expected
              (in case of DEBUG level there are additional 3 calls)
            - delete the Log instance
        """
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_syslog_openlog = MagicMock()
        mocker.patch('syslog.openlog', mock_syslog_openlog)
        mock_syslog_syslog = MagicMock()
        mocker.patch('syslog.syslog', mock_syslog_syslog)
        my_log = Log(level, output)
        my_log.msg(msg_level, "This is a test log message.")
        if output == Log.LOG_STDOUT:
            assert mock_print.call_count == count, error
        elif output == Log.LOG_STDERR:
            assert mock_print.call_count == count, error
        elif output == Log.LOG_SYSLOG:
            assert mock_syslog_syslog.call_count == count, error

# End.
