#!/usr/bin/python3
#
#   test_01_log.py (C) 2021-2022, Peter Sulyok
#   Unit test for smfc.py/Log() class.
#

import syslog
import unittest
from unittest.mock import patch, MagicMock
from smfc import Log


class LogTestCase(unittest.TestCase):
    """Unit test class for smfc.Log() class"""

    def primitive_test_1_pos(self, level: int, output: int, error: str) -> None:
        """This is a primitive positive test function. It contains the following steps:
            - mock syslog.openlog, syslog.syslog and print functions
            - initialize a Log class instance with a specified level and output values
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - ASSERT: if the mocked system functions were called wrong number of times
            - delete the instance
        """
        mock_syslog_openlog = MagicMock()
        mock_syslog_syslog = MagicMock()
        mock_print = MagicMock()
        with patch('builtins.print', mock_print), patch('syslog.openlog', mock_syslog_openlog), \
                patch('syslog.syslog', mock_syslog_syslog):
            myLog = Log(level, output)
            self.assertEqual(myLog.log_level, level, error)
            if myLog.log_output != Log.LOG_SYSLOG and myLog.log_level == Log.LOG_DEBUG:
                self.assertEqual(mock_print.call_count, 3)
            if myLog.log_output is Log.LOG_STDOUT:
                self.assertEqual(myLog.msg, myLog.msg_to_stdout, error)
            elif myLog.log_output is Log.LOG_STDERR:
                self.assertEqual(myLog.msg, myLog.msg_to_stderr, error)
            elif myLog.log_output == Log.LOG_SYSLOG:
                if myLog.log_level == Log.LOG_DEBUG:
                    self.assertEqual(mock_syslog_syslog.call_count, 3, error)
                if myLog.log_level != Log.LOG_NONE:
                    mock_syslog_openlog.assert_called()
            del myLog

    def primitive_test_2_neg(self, level: int, output: int, error: str) -> None:
        """This is a primitive negative test function. It contains the following steps:
            - initialize a Log class instance with specified level and output values
            - ASSERT: if __init__ does not raise an exception in case of invalid value
            - deletes the instance
        """
        with self.assertRaises(ValueError) as cm:
            Log(level, output)
        self.assertTrue(type(cm.exception) == ValueError, error)

    def test_init(self) -> None:
        """This is a unit test for function Log.__init__()"""

        # 1: Test valid values
        self.primitive_test_1_pos(Log.LOG_NONE, Log.LOG_STDOUT, "log init 01")
        self.primitive_test_1_pos(Log.LOG_ERROR, Log.LOG_STDOUT, "log init 02")
        self.primitive_test_1_pos(Log.LOG_INFO, Log.LOG_STDOUT, "log init 03")
        self.primitive_test_1_pos(Log.LOG_DEBUG, Log.LOG_STDOUT, "log init 04")

        self.primitive_test_1_pos(Log.LOG_NONE, Log.LOG_STDERR, "log init 05")
        self.primitive_test_1_pos(Log.LOG_ERROR, Log.LOG_STDERR, "log init 06")
        self.primitive_test_1_pos(Log.LOG_INFO, Log.LOG_STDERR, "log init 07")
        self.primitive_test_1_pos(Log.LOG_DEBUG, Log.LOG_STDERR, "log init 08")

        self.primitive_test_1_pos(Log.LOG_NONE, Log.LOG_SYSLOG, "log init 09")
        self.primitive_test_1_pos(Log.LOG_ERROR, Log.LOG_SYSLOG, "log init 10")
        self.primitive_test_1_pos(Log.LOG_INFO, Log.LOG_SYSLOG, "log init 11")
        self.primitive_test_1_pos(Log.LOG_DEBUG, Log.LOG_SYSLOG, "log init 12")

        # 2: Test invalid values.
        self.primitive_test_2_neg(100, Log.LOG_STDOUT, "log init 13")
        self.primitive_test_2_neg(Log.LOG_ERROR, 100, "log init 14")

    def primitive_test_3_pos(self, level: int, syslog_level: int, error: str) -> None:
        """This is a primitive positive test function. It contains the following steps:
            - initialize a Log class instance
            - call map_to_syslog with a specified level
            - ASSERT: if map_to_syslog function maps a specified log levels to a wrong syslog level value
            - delete the instance
        """
        myLog = Log(Log.LOG_INFO, Log.LOG_STDOUT)
        myLevel = myLog.map_to_syslog(level)
        self.assertEqual(syslog_level, myLevel, error)
        del myLog

    def test_map_to_syslog(self) -> None:
        """This is a unit test for function Log.map_to_syslog()."""
        self.primitive_test_3_pos(Log.LOG_ERROR, syslog.LOG_ERR, "log map_to_syslog 01")
        self.primitive_test_3_pos(Log.LOG_INFO, syslog.LOG_INFO, "log map_to_syslog 02")
        self.primitive_test_3_pos(Log.LOG_DEBUG, syslog.LOG_DEBUG, "log map_to_syslog 03")

    def primitive_test_4_pos(self, level: int, level_str: str, error: str) -> None:
        """This is a primitive positive test function. It contains the following steps:
            - initialize a Log class instance
            - call level_to_str() with a specified level
            - ASSERT: if level_to_str function maps a log level to an invalid string value
            - delete the Log instance
        """
        myLog = Log(Log.LOG_INFO, Log.LOG_STDOUT)
        myStr = myLog.level_to_str(level)
        self.assertEqual(myStr, level_str, error)
        del myLog

    def test_level_to_str(self) -> None:
        """This is a unit test for function Log.level_to_str()."""
        self.primitive_test_4_pos(Log.LOG_ERROR, 'ERROR', "log level_to_str 01")
        self.primitive_test_4_pos(Log.LOG_INFO, 'INFO', "log level_to_str 02")
        self.primitive_test_4_pos(Log.LOG_DEBUG, 'DEBUG', "log level_to_str 03")

    def primitive_test_5_pos(self, level: int, output: int, msg_level: int, count: int, error: str) -> None:
        """This is a primitive positive test function. It contains the following steps:
            - mock print and syslog.syslog functions
            - initialize a Log class instance with a specified level and output
            - calls Log.msg() with a specified level and log message
            - ASSERT: if msg() function calls print and/or syslog functions other times than expected
              (in case of DEBUG level there are 3 more calls)
            - delete the Log instance
        """
        mock_syslog_syslog = MagicMock()
        mock_print = MagicMock()
        with patch('builtins.print', mock_print), patch('syslog.syslog', mock_syslog_syslog):
            myLog = Log(level, output)
            myLog.msg(msg_level, "This is a test log message.")
            if myLog.log_level == Log.LOG_DEBUG:
                count += 3
            if output == Log.LOG_STDOUT:
                self.assertEqual(mock_print.call_count, count, error)
            elif output == Log.LOG_STDERR:
                self.assertEqual(mock_print.call_count, count, error)
            elif output == Log.LOG_SYSLOG:
                self.assertEqual(mock_syslog_syslog.call_count, count, error)
            del myLog

    def test_msg_to_xxx(self) -> None:
        """ This is a unit test for function Log.msg()."""

        # Test all combinations of class initialization values and same/different log level values.
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_NONE, 0, "log msg_to_??? 01")
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_ERROR, 0, "log msg_to_??? 02")
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_INFO, 0, "log msg_to_??? 03")
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_NONE, 0, "log msg_to_??? 05")
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_ERROR, 0, "log msg_to_??? 06")
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_INFO, 0, "log msg_to_??? 07")
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "log msg_to_??? 08")

        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "log msg_to_??? 09")
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_ERROR, 0, "log msg_to_??? 10")
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "log msg_to_??? 11")
        self.primitive_test_5_pos(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "log msg_to_??? 12")

        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_NONE, 0, "log msg_to_??? 13")
        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "log msg_to_??? 14")
        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_INFO, 0, "log msg_to_??? 15")
        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "log msg_to_??? 16")

        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_NONE, 0, "log msg_to_??? 17")
        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_ERROR, 1, "log msg_to_??? 18")
        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_INFO, 0, "log msg_to_??? 19")
        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "log msg_to_??? 20")

        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "log msg_to_??? 21")
        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "log msg_to_??? 22")
        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "log msg_to_??? 23")
        self.primitive_test_5_pos(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "log msg_to_??? 24")

        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_NONE, 0, "log msg_to_??? 25")
        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "log msg_to_??? 26")
        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_INFO, 1, "log msg_to_??? 27")
        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "log msg_to_??? 28")

        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_NONE, 0, "log msg_to_??? 29")
        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_ERROR, 1, "log msg_to_??? 30")
        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_INFO, 1, "log msg_to_??? 31")
        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "log msg_to_??? 32")

        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "log msg_to_??? 33")
        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "log msg_to_??? 34")
        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_INFO, 1, "log msg_to_??? 35")
        self.primitive_test_5_pos(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "log msg_to_??? 36")

        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_NONE, 0, "log msg_to_??? 37")
        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "log msg_to_??? 38")
        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_INFO, 1, "log msg_to_??? 39")
        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_DEBUG, 1, "log msg_to_??? 40")

        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_NONE, 0, "log msg_to_??? 41")
        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_ERROR, 1, "log msg_to_??? 42")
        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_INFO, 1, "log msg_to_??? 43")
        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_DEBUG, 1, "log msg_to_??? 44")

        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "log msg_to_??? 45")
        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "log msg_to_??? 46")
        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_INFO, 1, "log msg_to_??? 47")
        self.primitive_test_5_pos(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_DEBUG, 1, "log msg_to_??? 48")


if __name__ == "__main__":
    unittest.main()
