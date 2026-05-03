#
#   constfc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.ConstFc() class implementation.
#
import time
from configparser import ConfigParser
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class ConstFc(FanController):
    """Class for CONST fan controller."""

    # Constant values for the configuration parameters.
    CS_CONST_FC: str = "CONST"
    CV_CONST_FC_ENABLED: str = "enabled"
    CV_CONST_FC_IPMI_ZONE: str = "ipmi_zone"
    CV_CONST_FC_POLLING: str = "polling"
    CV_CONST_FC_LEVEL: str = "level"

    # Constant level for the zone.
    level: int

    # pylint: disable=super-init-not-called
    def __init__(self, log: Log, ipmi: Ipmi, config: ConfigParser, section: str = CS_CONST_FC) -> None:
        """Initialize the CONST fan controller class and raise exception in case invalid configuration items.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            config (ConfigParser): reference to the configuration
            section (str): configuration section name (default: CS_CONST_FC)
        Raises:
            ValueError: invalid configuration parameters
        """
        # Initialize ConstFc class.
        self.log = log
        self.ipmi = ipmi
        ipmi_zone_str = config[section].get(ConstFc.CV_CONST_FC_IPMI_ZONE, fallback=f"{Ipmi.HD_ZONE}")
        self.ipmi_zone = FanController.parse_ipmi_zones(ipmi_zone_str)

        self.name = section
        self.polling = config[section].getfloat(ConstFc.CV_CONST_FC_POLLING, fallback=30.0)
        if self.polling < 0.0:
            raise ValueError("polling < 0")
        self.level = config[section].getint(ConstFc.CV_CONST_FC_LEVEL, fallback=50)
        if self.level not in range(0, 101):
            raise ValueError("invalid level")
        self.last_time = 0.0
        self.last_temp = 0.0
        self.last_level = self.level
        self.deferred_apply = False

        # Print configuration at CONFIG log level.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"{self.name} fan controller was initialized with:")
            self.log.msg(Log.LOG_CONFIG, f"   ipmi zone = {self.ipmi_zone}")
            self.log.msg(Log.LOG_CONFIG, f"   polling = {self.polling}")
            self.log.msg(Log.LOG_CONFIG, f"   level = {self.level}")

    # pylint: enable=super-init-not-called

    def run(self) -> None:
        """Run IPMI zone controller function with the following steps:

        * Step 1: Read current time. If the elapsed time is bigger than the polling time period,
          then go to step 2, otherwise return.
        * Step 2: In deferred mode, just ensure last_level is set and return.
        * Step 3: Loop through IPMI zones: read current fan level in the zone, if the level is different from the
          expected one then we set fan level in the zone again, otherwise return.
        * Step 4: Log the fan level.
        """
        current_time: float  # Current system timestamp (measured)

        # Step 1: check the elapsed time.
        current_time = time.monotonic()
        if (current_time - self.last_time) >= self.polling:
            self.last_time = current_time

            # Step 2: in deferred mode, just store the desired level for arbitration.
            if self.deferred_apply:
                self.last_level = self.level
                return

            # Check in all IPMI zones if the current fan level is the expected one,
            # otherwise set the fan level again.
            for zone in self.ipmi_zone:
                level = self.ipmi.get_fan_level(zone)
                if self.log.log_level >= Log.LOG_DEBUG:
                    self.log.msg(Log.LOG_DEBUG, f"{self.name}: zone {zone} current={level}% expected={self.level}%")
                if level != self.level:
                    self.ipmi.set_fan_level(zone, self.level)
                    self.log.msg(Log.LOG_INFO, f"{self.name}: set fan level > {self.level}% "
                                               f"@ IPMI {self.ipmi_zone} zone(s).")


# End.
