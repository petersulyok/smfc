#!/usr/bin/python3
#
#   test_01_log.py (C) 2021-2024, Peter Sulyok
#   Unit test for smfc.Log() class.
#

import syslog
import unittest
from unittest.mock import patch, MagicMock
from smfc import Log


class LogTestCase(unittest.TestCase):
    """Unit test class for smfc.Log() class"""

    def pt_init_p1(self, level: int, output: int, error: str) -> None:
        """Primitive positive test function. It contains the following steps:
            - mock syslog.openlog(), syslog.syslog() and print() functions
            - initialize a Log class instance with a specified level and output values
            - ASSERT: if the class attributes contain different values that were passed to __init__
            - ASSERT: if the mocked system functions were called wrong number of times
            - delete all instance
        """
        mock_syslog_openlog = MagicMock()
        mock_syslog_syslog = MagicMock()
        mock_print = MagicMock()
        with patch('builtins.print', mock_print), \
             patch('syslog.openlog', mock_syslog_openlog), \
             patch('syslog.syslog', mock_syslog_syslog):
            my_log = Log(level, output)
            self.assertEqual(my_log.log_level, level, error)
            if my_log.log_output != Log.LOG_SYSLOG and my_log.log_level == Log.LOG_DEBUG:
                self.assertEqual(mock_print.call_count, 3)
            if my_log.log_output is Log.LOG_STDOUT:
                self.assertEqual(my_log.msg, my_log.msg_to_stdout, error)
            elif my_log.log_output is Log.LOG_STDERR:
                self.assertEqual(my_log.msg, my_log.msg_to_stderr, error)
            elif my_log.log_output == Log.LOG_SYSLOG:
                if my_log.log_level == Log.LOG_DEBUG:
                    self.assertEqual(mock_syslog_syslog.call_count, 3, error)
                if my_log.log_level != Log.LOG_NONE:
                    mock_syslog_openlog.assert_called()
            del my_log

    def pt_init_n1(self, level: int, output: int, error: str) -> None:
        """This is a primitive negative test function. It contains the following steps:
            - initialize a Log class instance with specified level and output values
            - ASSERT: if __init__ does not raise an exception in case of invalid value
            - deletes the instance
        """
        with self.assertRaises(ValueError) as cm:
            Log(level, output)
        self.assertEqual(type(cm.exception), ValueError, error)

    def test_init(self) -> None:
        """This is a unit test for function Log.__init__()"""

        # 1: Test valid values
        self.pt_init_p1(Log.LOG_NONE, Log.LOG_STDOUT, "log init 01")
        self.pt_init_p1(Log.LOG_ERROR, Log.LOG_STDOUT, "log init 02")
        self.pt_init_p1(Log.LOG_CONFIG, Log.LOG_STDOUT, "log init 03")
        self.pt_init_p1(Log.LOG_INFO, Log.LOG_STDOUT, "log init 04")
        self.pt_init_p1(Log.LOG_DEBUG, Log.LOG_STDOUT, "log init 05")

        self.pt_init_p1(Log.LOG_NONE, Log.LOG_STDERR, "log init 06")
        self.pt_init_p1(Log.LOG_ERROR, Log.LOG_STDERR, "log init 07")
        self.pt_init_p1(Log.LOG_CONFIG, Log.LOG_STDERR, "log init 08")
        self.pt_init_p1(Log.LOG_INFO, Log.LOG_STDERR, "log init 09")
        self.pt_init_p1(Log.LOG_DEBUG, Log.LOG_STDERR, "log init 10")

        self.pt_init_p1(Log.LOG_NONE, Log.LOG_SYSLOG, "log init 11")
        self.pt_init_p1(Log.LOG_ERROR, Log.LOG_SYSLOG, "log init 12")
        self.pt_init_p1(Log.LOG_CONFIG, Log.LOG_SYSLOG, "log init 13")
        self.pt_init_p1(Log.LOG_INFO, Log.LOG_SYSLOG, "log init 14")
        self.pt_init_p1(Log.LOG_DEBUG, Log.LOG_SYSLOG, "log init 15")

        # 2: Test invalid values.
        self.pt_init_n1(100, Log.LOG_STDOUT, "log init 16")
        self.pt_init_n1(Log.LOG_ERROR, 100, "log init 17")

    def pt_mts_p1(self, level: int, syslog_level: int, error: str) -> None:
        """Primitive positive test function. It contains the following steps:
            - initialize a Log class instance
            - call map_to_syslog with a specified level
            - ASSERT: if map_to_syslog function maps a specified log levels to a wrong syslog level value
            - delete the instance
        """
        my_log = Log(Log.LOG_INFO, Log.LOG_STDOUT)
        my_level = my_log.map_to_syslog(level)
        self.assertEqual(syslog_level, my_level, error)
        del my_log

    def test_map_to_syslog(self) -> None:
        """This is a unit test for function Log.map_to_syslog()."""
        self.pt_mts_p1(Log.LOG_ERROR, syslog.LOG_ERR, "log map_to_syslog 01")
        self.pt_mts_p1(Log.LOG_CONFIG, syslog.LOG_INFO, "log map_to_syslog 02")
        self.pt_mts_p1(Log.LOG_INFO, syslog.LOG_INFO, "log map_to_syslog 03")
        self.pt_mts_p1(Log.LOG_DEBUG, syslog.LOG_DEBUG, "log map_to_syslog 04")

    def pt_lts_p1(self, level: int, level_str: str, error: str) -> None:
        """Primitive positive test function. It contains the following steps:
            - initialize a Log class instance
            - call level_to_str() with a specified level
            - ASSERT: if level_to_str function maps a log level to an invalid string value
            - delete the Log instance
        """
        my_log = Log(Log.LOG_INFO, Log.LOG_STDOUT)
        my_str = my_log.level_to_str(level)
        self.assertEqual(my_str, level_str, error)
        del my_log

    def test_level_to_str(self) -> None:
        """This is a unit test for function Log.level_to_str()."""
        self.pt_lts_p1(Log.LOG_NONE, 'NONE', "log level_to_str 01")
        self.pt_lts_p1(Log.LOG_ERROR, 'ERROR', "log level_to_str 02")
        self.pt_lts_p1(Log.LOG_CONFIG, 'CONFIG', "log level_to_str 03")
        self.pt_lts_p1(Log.LOG_INFO, 'INFO', "log level_to_str 04")
        self.pt_lts_p1(Log.LOG_DEBUG, 'DEBUG', "log level_to_str 05")

    def pt_mtx_p1(self, level: int, output: int, msg_level: int, count: int, error: str) -> None:
        """Positive test function. It contains the following steps:
            - mock print() and syslog.syslog() functions
            - initialize a Log class instance with a specified level and output
            - calls Log.msg() with a specified level and log message
            - ASSERT: if msg() function calls print and/or syslog functions other times than expected
              (in case of DEBUG level there are 3 more calls)
            - delete the Log instance
        """
        mock_syslog_syslog = MagicMock()
        mock_print = MagicMock()
        with patch('builtins.print', mock_print), patch('syslog.syslog', mock_syslog_syslog):
            my_log = Log(level, output)
            my_log.msg(msg_level, "This is a test log message.")
            if my_log.log_level >= Log.LOG_CONFIG:
                count += 3
            if output == Log.LOG_STDOUT:
                self.assertEqual(mock_print.call_count, count, error)
            elif output == Log.LOG_STDERR:
                self.assertEqual(mock_print.call_count, count, error)
            elif output == Log.LOG_SYSLOG:
                self.assertEqual(mock_syslog_syslog.call_count, count, error)
        del my_log

    def test_msg_to_xxx(self) -> None:
        """ This is a unit test for function Log.msg()."""

        # Test all combinations of class initialization values and same/different log level values.
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_NONE, 0, "log msg_to_??? 01")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_ERROR, 0, "log msg_to_??? 02")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_CONFIG, 0, "log msg_to_??? 03")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_INFO, 0, "log msg_to_??? 03")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "log msg_to_??? 04")

        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_NONE, 0, "log msg_to_??? 05")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_ERROR, 0, "log msg_to_??? 06")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_CONFIG, 0, "log msg_to_??? 07")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_INFO, 0, "log msg_to_??? 08")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "log msg_to_??? 09")

        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "log msg_to_??? 10")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_ERROR, 0, "log msg_to_??? 11")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_CONFIG, 0, "log msg_to_??? 12")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "log msg_to_??? 13")
        self.pt_mtx_p1(Log.LOG_NONE, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "log msg_to_??? 14")

        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_NONE, 0, "log msg_to_??? 15")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "log msg_to_??? 16")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_CONFIG, 0, "log msg_to_??? 17")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_INFO, 0, "log msg_to_??? 18")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "log msg_to_??? 19")

        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_NONE, 0, "log msg_to_??? 20")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_ERROR, 1, "log msg_to_??? 21")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_CONFIG, 0, "log msg_to_??? 22")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_INFO, 0, "log msg_to_??? 23")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "log msg_to_??? 24")

        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "log msg_to_??? 25")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "log msg_to_??? 26")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_CONFIG, 0, "log msg_to_??? 27")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "log msg_to_??? 28")
        self.pt_mtx_p1(Log.LOG_ERROR, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "log msg_to_??? 29")

        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_NONE, 0, "log msg_to_??? 30")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "log msg_to_??? 31")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, "log msg_to_??? 32")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_INFO, 0, "log msg_to_??? 33")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "log msg_to_??? 34")

        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_NONE, 0, "log msg_to_??? 35")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_ERROR, 1, "log msg_to_??? 36")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_CONFIG, 1, "log msg_to_??? 37")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_INFO, 0, "log msg_to_??? 38")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "log msg_to_??? 39")

        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "log msg_to_??? 40")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "log msg_to_??? 41")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, "log msg_to_??? 42")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_INFO, 0, "log msg_to_??? 43")
        self.pt_mtx_p1(Log.LOG_CONFIG, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "log msg_to_??? 44")

        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_NONE, 0, "log msg_to_??? 45")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "log msg_to_??? 46")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, "log msg_to_??? 47")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_INFO, 1, "log msg_to_??? 48")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDOUT, Log.LOG_DEBUG, 0, "log msg_to_??? 49")

        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_NONE, 0, "log msg_to_??? 50")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_ERROR, 1, "log msg_to_??? 51")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_CONFIG, 1, "log msg_to_??? 52")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_INFO, 1, "log msg_to_??? 53")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_STDERR, Log.LOG_DEBUG, 0, "log msg_to_??? 54")

        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "log msg_to_??? 55")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "log msg_to_??? 56")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, "log msg_to_??? 57")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_INFO, 1, "log msg_to_??? 58")
        self.pt_mtx_p1(Log.LOG_INFO, Log.LOG_SYSLOG, Log.LOG_DEBUG, 0, "log msg_to_??? 59")

        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_NONE, 0, "log msg_to_??? 60")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_ERROR, 1, "log msg_to_??? 61")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_CONFIG, 1, "log msg_to_??? 62")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_INFO, 1, "log msg_to_??? 63")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDOUT, Log.LOG_DEBUG, 1, "log msg_to_??? 64")

        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_NONE, 0, "log msg_to_??? 65")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_ERROR, 1, "log msg_to_??? 66")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_CONFIG, 1, "log msg_to_??? 67")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_INFO, 1, "log msg_to_??? 68")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_STDERR, Log.LOG_DEBUG, 1, "log msg_to_??? 69")

        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_NONE, 0, "log msg_to_??? 70")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_ERROR, 1, "log msg_to_??? 71")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_CONFIG, 1, "log msg_to_??? 72")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_INFO, 1, "log msg_to_??? 73")
        self.pt_mtx_p1(Log.LOG_DEBUG, Log.LOG_SYSLOG, Log.LOG_DEBUG, 1, "log msg_to_??? 74")


if __name__ == "__main__":
    unittest.main()
