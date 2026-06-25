#!/usr/bin/env python3
#
#   test_log.py (C) 2021-2026, Peter Sulyok
#   Unit test for smfc.Log() class.
#
import syslog
from typing import Tuple
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc.log import Log


def _make_log(mocker: MockerFixture, level: int, output: int) -> Tuple[Log, MagicMock, MagicMock]:
    """Build a Log with print/syslog mocked. Returns (log, mock_print, mock_syslog_syslog).

    Removes the repeated print/syslog.openlog/syslog.syslog patching boilerplate that appears in every
    test that constructs a Log instance.
    """
    mock_print = MagicMock()
    mocker.patch("builtins.print", mock_print)
    mocker.patch("syslog.openlog", MagicMock())
    mock_syslog_syslog = MagicMock()
    mocker.patch("syslog.syslog", mock_syslog_syslog)
    return Log(level, output), mock_print, mock_syslog_syslog


class TestLog:
    """Unit test class for smfc.Log() class"""

    @pytest.mark.parametrize(
        "level, output",
        [
            pytest.param(Log.LOG_NONE, Log.LOG_STDOUT, id="none-stdout"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDOUT, id="error-stdout"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDOUT, id="config-stdout"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDOUT, id="info-stdout"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDOUT, id="debug-stdout"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDERR, id="none-stderr"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDERR, id="error-stderr"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDERR, id="config-stderr"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDERR, id="info-stderr"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDERR, id="debug-stderr"),
            pytest.param(Log.LOG_NONE, Log.LOG_SYSLOG, id="none-syslog"),
            pytest.param(Log.LOG_ERROR, Log.LOG_SYSLOG, id="error-syslog"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_SYSLOG, id="config-syslog"),
            pytest.param(Log.LOG_INFO, Log.LOG_SYSLOG, id="info-syslog"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_SYSLOG, id="debug-syslog"),
        ],
    )
    def test_init_sets_attributes_and_dispatcher(self, mocker: MockerFixture, level: int, output: int) -> None:
        """Positive unit test for Log.__init__() method. It contains the following steps:
        - mock print(), syslog.openlog(), and syslog.syslog() functions
        - initialize a Log class instance with a specified level and output values
        - ASSERT: log_level and log_output match the values passed to __init__
        - ASSERT: msg dispatcher is wired to the output-matching backend
          (msg_to_stdout / msg_to_stderr / msg_to_syslog)
        """
        my_log, _, _ = _make_log(mocker, level, output)
        assert my_log.log_level == level
        assert my_log.log_output == output
        if my_log.log_output is Log.LOG_STDOUT:
            # pylint: disable=comparison-with-callable
            assert my_log.msg == my_log.msg_to_stdout
        elif my_log.log_output is Log.LOG_STDERR:
            # pylint: disable=comparison-with-callable
            assert my_log.msg == my_log.msg_to_stderr
        elif my_log.log_output == Log.LOG_SYSLOG:
            # pylint: disable=comparison-with-callable
            assert my_log.msg == my_log.msg_to_syslog

    @pytest.mark.parametrize(
        "level, output",
        [
            pytest.param(100, Log.LOG_STDOUT, id="invalid-level"),
            pytest.param(Log.LOG_ERROR, 100, id="invalid-output"),
        ],
    )
    def test_init_raises_on_invalid_level_or_output(self, mocker: MockerFixture, level: int, output: int) -> None:
        """Negative unit test for Log.__init__() method. It contains the following steps:
        - mock print() function
        - initialize a Log class instance with specified level and output values
        - ASSERT: __init__ raises ValueError in case of invalid value
        """
        mocker.patch("builtins.print", MagicMock())
        with pytest.raises(ValueError) as cm:
            Log(level, output)
        assert cm.type is ValueError

    @pytest.mark.parametrize(
        "level, syslog_level",
        [
            pytest.param(Log.LOG_ERROR, syslog.LOG_ERR, id="error-to-err"),
            pytest.param(Log.LOG_CONFIG, syslog.LOG_INFO, id="config-to-info"),
            pytest.param(Log.LOG_INFO, syslog.LOG_INFO, id="info-to-info"),
            pytest.param(Log.LOG_DEBUG, syslog.LOG_DEBUG, id="debug-to-debug"),
            pytest.param(1000, syslog.LOG_ERR, id="invalid-high-to-err"),
            pytest.param(-1, syslog.LOG_ERR, id="invalid-negative-to-err"),
        ],
    )
    def test_map_to_syslog(self, level: int, syslog_level: int) -> None:
        """Positive unit test for Log.map_to_syslog() method. It contains the following steps:
        - call map_to_syslog() with a specified level
        - ASSERT: map_to_syslog returns the expected syslog level (invalid levels fall back to LOG_ERR)
        """
        assert Log.map_to_syslog(level) == syslog_level

    @pytest.mark.parametrize(
        "level, level_str",
        [
            pytest.param(Log.LOG_NONE, "NONE", id="none"),
            pytest.param(Log.LOG_ERROR, "ERROR", id="error"),
            pytest.param(Log.LOG_CONFIG, "CONFIG", id="config"),
            pytest.param(Log.LOG_INFO, "INFO", id="info"),
            pytest.param(Log.LOG_DEBUG, "DEBUG", id="debug"),
            pytest.param(-1, "NONE", id="invalid-negative"),
            pytest.param(1000, "NONE", id="invalid-high"),
        ],
    )
    def test_level_to_str(self, level: int, level_str: str) -> None:
        """Positive unit test for Log.level_to_str() method. It contains the following steps:
        - call level_to_str() with a specified level
        - ASSERT: level_to_str returns the expected name (invalid levels fall back to "NONE")
        """
        assert Log.level_to_str(level) == level_str

    @pytest.mark.parametrize(
        "output, output_str",
        [
            pytest.param(Log.LOG_STDOUT, "STDOUT", id="stdout"),
            pytest.param(Log.LOG_STDERR, "STDERR", id="stderr"),
            pytest.param(Log.LOG_SYSLOG, "SYSLOG", id="syslog"),
            pytest.param(-1, "STDOUT", id="invalid-negative"),
            pytest.param(1000, "STDOUT", id="invalid-high"),
        ],
    )
    def test_output_to_str(self, output: int, output_str: str) -> None:
        """Positive unit test for Log.output_to_str() method. It contains the following steps:
        - call output_to_str() with a specified output
        - ASSERT: output_to_str returns the expected name (invalid outputs fall back to "STDOUT")
        """
        assert Log.output_to_str(output) == output_str

    @pytest.mark.parametrize(
        "level, output, msg_level, count",
        [
            # LOG_NONE: nothing emitted regardless of msg_level / output
            pytest.param(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_NONE, 0, id="none-stdout-msg-none"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_ERROR, 0, id="none-stdout-msg-error"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_CONFIG, 0, id="none-stdout-msg-config"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_INFO, 0, id="none-stdout-msg-info"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, id="none-stdout-msg-debug"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_NONE, 0, id="none-stderr-msg-none"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_ERROR, 0, id="none-stderr-msg-error"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_CONFIG, 0, id="none-stderr-msg-config"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_INFO, 0, id="none-stderr-msg-info"),
            pytest.param(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_DEBUG, 0, id="none-stderr-msg-debug"),
            pytest.param(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_NONE, 0, id="none-syslog-msg-none"),
            pytest.param(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_ERROR, 0, id="none-syslog-msg-error"),
            pytest.param(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_CONFIG, 0, id="none-syslog-msg-config"),
            pytest.param(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_INFO, 0, id="none-syslog-msg-info"),
            pytest.param(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, id="none-syslog-msg-debug"),
            # LOG_ERROR: only ERROR messages emitted
            pytest.param(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_NONE, 0, id="error-stdout-msg-none"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_ERROR, 1, id="error-stdout-msg-error"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_CONFIG, 0, id="error-stdout-msg-config"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_INFO, 0, id="error-stdout-msg-info"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, id="error-stdout-msg-debug"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_NONE, 0, id="error-stderr-msg-none"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_ERROR, 1, id="error-stderr-msg-error"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_CONFIG, 0, id="error-stderr-msg-config"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_INFO, 0, id="error-stderr-msg-info"),
            pytest.param(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_DEBUG, 0, id="error-stderr-msg-debug"),
            pytest.param(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_NONE, 0, id="error-syslog-msg-none"),
            pytest.param(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, id="error-syslog-msg-error"),
            pytest.param(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_CONFIG, 0, id="error-syslog-msg-config"),
            pytest.param(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_INFO, 0, id="error-syslog-msg-info"),
            pytest.param(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, id="error-syslog-msg-debug"),
            # LOG_CONFIG: ERROR + CONFIG messages emitted
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_NONE, 0, id="config-stdout-msg-none"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_ERROR, 1, id="config-stdout-msg-error"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, id="config-stdout-msg-config"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_INFO, 0, id="config-stdout-msg-info"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, id="config-stdout-msg-debug"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_NONE, 0, id="config-stderr-msg-none"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_ERROR, 1, id="config-stderr-msg-error"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_CONFIG, 1, id="config-stderr-msg-config"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_INFO, 0, id="config-stderr-msg-info"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_DEBUG, 0, id="config-stderr-msg-debug"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_NONE, 0, id="config-syslog-msg-none"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, id="config-syslog-msg-error"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, id="config-syslog-msg-config"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_INFO, 0, id="config-syslog-msg-info"),
            pytest.param(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, id="config-syslog-msg-debug"),
            # LOG_INFO: ERROR + CONFIG + INFO messages emitted
            pytest.param(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_NONE, 0, id="info-stdout-msg-none"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_ERROR, 1, id="info-stdout-msg-error"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, id="info-stdout-msg-config"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_INFO, 1, id="info-stdout-msg-info"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, id="info-stdout-msg-debug"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_NONE, 0, id="info-stderr-msg-none"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_ERROR, 1, id="info-stderr-msg-error"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_CONFIG, 1, id="info-stderr-msg-config"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_INFO, 1, id="info-stderr-msg-info"),
            pytest.param(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_DEBUG, 0, id="info-stderr-msg-debug"),
            pytest.param(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_NONE, 0, id="info-syslog-msg-none"),
            pytest.param(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, id="info-syslog-msg-error"),
            pytest.param(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, id="info-syslog-msg-config"),
            pytest.param(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_INFO, 1, id="info-syslog-msg-info"),
            pytest.param(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, id="info-syslog-msg-debug"),
            # LOG_DEBUG: all messages emitted
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_NONE, 0, id="debug-stdout-msg-none"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_ERROR, 1, id="debug-stdout-msg-error"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, id="debug-stdout-msg-config"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_INFO, 1, id="debug-stdout-msg-info"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_DEBUG, 1, id="debug-stdout-msg-debug"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_NONE, 0, id="debug-stderr-msg-none"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_ERROR, 1, id="debug-stderr-msg-error"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_CONFIG, 1, id="debug-stderr-msg-config"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_INFO, 1, id="debug-stderr-msg-info"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_DEBUG, 1, id="debug-stderr-msg-debug"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_NONE, 0, id="debug-syslog-msg-none"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, id="debug-syslog-msg-error"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, id="debug-syslog-msg-config"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_INFO, 1, id="debug-syslog-msg-info"),
            pytest.param(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_DEBUG, 1, id="debug-syslog-msg-debug"),
        ],
    )
    def test_msg_routes_by_level_and_output(self, mocker: MockerFixture, level: int, output: int, msg_level: int,
                                            count: int) -> None:
        """Positive unit test for Log.msg() routing. It contains the following steps:
        - mock print() and syslog.syslog() functions
        - initialize a Log class instance with a specified level and output
        - call Log.msg() with a specified msg_level and a log message
        - ASSERT: print is called `count` times for STDOUT/STDERR outputs (suppressed when msg_level
          exceeds the configured level)
        - ASSERT: syslog.syslog is called `count` times for SYSLOG output
        """
        my_log, mock_print, mock_syslog_syslog = _make_log(mocker, level, output)
        my_log.msg(msg_level, "This is a test log message.")
        if output in (Log.LOG_STDOUT, Log.LOG_STDERR):
            assert mock_print.call_count == count
        elif output == Log.LOG_SYSLOG:
            assert mock_syslog_syslog.call_count == count


# End.
