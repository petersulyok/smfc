#
#   log.py (C) 2020-2024, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.Log() class implementation.
#
import sys
import syslog
from typing import Callable


class Log:
    """Log class implementation. It can send log messages considering different log levels and different outputs."""

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
        """
        # Setup log configuration.
        if log_level not in {self.LOG_NONE, self.LOG_ERROR, self.LOG_CONFIG, self.LOG_INFO, self.LOG_DEBUG}:
            raise ValueError(f'Invalid log level value ({log_level})')
        self.log_level = log_level
        if log_output not in {self.LOG_STDOUT, self.LOG_STDERR, self.LOG_SYSLOG}:
            raise ValueError(f'Invalid log output value ({log_output})')
        self.log_output = log_output
        if self.log_output == self.LOG_STDOUT:
            self.msg = self.msg_to_stdout
        elif self.log_output == self.LOG_STDERR:
            self.msg = self.msg_to_stderr
        else:
            self.msg = self.msg_to_syslog
            syslog.openlog('smfc.service', facility=syslog.LOG_DAEMON)

        # Print the configuration out at DEBUG log level.
        if self.log_level >= self.LOG_CONFIG:
            self.msg(Log.LOG_CONFIG, 'Logging module was initialized with:')
            self.msg(Log.LOG_CONFIG, f'   log_level = {self.log_level}')
            self.msg(Log.LOG_CONFIG, f'   log_output = {self.log_output}')

    def map_to_syslog(self, level: int) -> int:
        """Map log level to syslog values.

            Args:
                level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            Returns:
                int: syslog log level
            """
        syslog_level = syslog.LOG_ERR
        if level in (self.LOG_CONFIG, self.LOG_INFO):
            syslog_level = syslog.LOG_INFO
        elif level == self.LOG_DEBUG:
            syslog_level = syslog.LOG_DEBUG
        return syslog_level

    def level_to_str(self, level: int) -> str:
        """Convert a log level to a string.

            Args:
                level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            Returns:
                str: log level string
            """
        string = 'NONE'
        if level == self.LOG_ERROR:
            string = 'ERROR'
        if level == self.LOG_CONFIG:
            string = 'CONFIG'
        if level == self.LOG_INFO:
            string = 'INFO'
        elif level == self.LOG_DEBUG:
            string = 'DEBUG'
        return string

    def msg_to_syslog(self, level: int, msg: str) -> None:
        """Print a log message to syslog.

        Args:
            level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            msg (str): log message
        """
        if level is not self.LOG_NONE:
            if level <= self.log_level:
                syslog.syslog(self.map_to_syslog(level), msg)

    def msg_to_stdout(self, level: int, msg: str) -> None:
        """Print a log message to stdout.

        Args:
            level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            msg (str):  log message
        """
        if level is not self.LOG_NONE:
            if level <= self.log_level:
                print(f'{self.level_to_str(level)}: {msg}', flush=True, file=sys.stdout)

    def msg_to_stderr(self, level: int, msg: str) -> None:
        """Print a log message to stderr.

        Args:
            level (int): log level (LOG_ERROR, LOG_CONFIG, LOG_INFO, LOG_DEBUG)
            msg (str):  log message
        """
        if level is not self.LOG_NONE:
            if level <= self.log_level:
                print(f'{self.level_to_str(level)}: {msg}', flush=True, file=sys.stderr)

# End.
