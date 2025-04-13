#
#   log.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.Log() class implementation.
#
import sys
import syslog
from typing import Callable


class Log:
    """Log class. This class can send log messages considering different log levels and different log outputs."""

    # Configuration parameters.
    log_level: int                      # Log level
    log_output: int                     # Log output
    msg: Callable[[int, str], None]     # Function reference to the log function (based on log output)

    # Constants for log levels.
    LOG_NONE: int = 0
    LOG_ERROR: int = 1
    LOG_CONFIG: int = 2
    LOG_INFO: int = 3
    LOG_DEBUG: int = 4

    # Constants for log outputs.
    LOG_STDOUT: int = 0
    LOG_STDERR: int = 1
    LOG_SYSLOG: int = 2

    def __init__(self, log_level: int, log_output: int) -> None:
        """Initialize Log class with log output and log level.
        Args:
            log_level (int): user defined log level (LOG_NONE, LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            log_output (int): user defined log output (LOG_STDOUT, LOG_STDERR, LOG_SYSLOG)
        Raises:
            ValueError: invalid input parameters
        """
        # Setup log configuration.
        if log_level not in {Log.LOG_NONE, Log.LOG_ERROR, Log.LOG_CONFIG, Log.LOG_INFO, Log.LOG_DEBUG}:
            raise ValueError(f'Invalid log level value ({log_level})')
        self.log_level = log_level
        if log_output not in {Log.LOG_STDOUT, Log.LOG_STDERR, Log.LOG_SYSLOG}:
            raise ValueError(f'Invalid log output value ({log_output})')
        self.log_output = log_output
        if self.log_output == Log.LOG_STDOUT:
            self.msg = self.msg_to_stdout
        elif self.log_output == Log.LOG_STDERR:
            self.msg = self.msg_to_stderr
        else:
            self.msg = self.msg_to_syslog
            syslog.openlog('smfc.service', facility=syslog.LOG_DAEMON)

    @staticmethod
    def map_to_syslog(level: int) -> int:
        """Map log level to syslog values.
            Args:
                level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            Returns:
                int: syslog log level
            """
        syslog_level = syslog.LOG_ERR
        if level in (Log.LOG_CONFIG, Log.LOG_INFO):
            syslog_level = syslog.LOG_INFO
        elif level == Log.LOG_DEBUG:
            syslog_level = syslog.LOG_DEBUG
        return syslog_level

    @staticmethod
    def level_to_str(level: int) -> str:
        """Convert a log level to a string.
            Args:
                level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            Returns:
                str: log level string
            """
        string = 'NONE'
        if level == Log.LOG_ERROR:
            string = 'ERROR'
        if level == Log.LOG_CONFIG:
            string = 'CONFIG'
        if level == Log.LOG_INFO:
            string = 'INFO'
        elif level == Log.LOG_DEBUG:
            string = 'DEBUG'
        return string

    def msg_to_syslog(self, level: int, msg: str) -> None:
        """Print a log message to syslog.
        Args:
            level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            msg (str): log message
        """
        if level is not Log.LOG_NONE:
            if level <= self.log_level:
                syslog.syslog(self.map_to_syslog(level), msg)

    def msg_to_stdout(self, level: int, msg: str) -> None:
        """Print a log message to stdout.
        Args:
            level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            msg (str):  log message
        """
        if level is not Log.LOG_NONE:
            if level <= self.log_level:
                print(f'{self.level_to_str(level)}: {msg}', flush=True, file=sys.stdout)

    def msg_to_stderr(self, level: int, msg: str) -> None:
        """Print a log message to stderr.

        Args:
            level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            msg (str):  log message
        """
        if level is not Log.LOG_NONE:
            if level <= self.log_level:
                print(f'{self.level_to_str(level)}: {msg}', flush=True, file=sys.stderr)

# End.
