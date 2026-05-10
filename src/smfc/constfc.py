#
#   constfc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.ConstFc() class implementation.
#
import time
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import ConstConfig


class ConstFc:  # pylint: disable=too-few-public-methods
    """Class for CONST fan controller. This controller maintains a constant fan level."""

    config: ConstConfig

    # Core references
    log: Log                # Reference to a Log class instance
    ipmi: Ipmi              # Reference to an Ipmi class instance
    name: str               # Name of the controller

    # Runtime state
    last_time: float        # Last system time we polled (timestamp)
    last_temp: float        # Not used, but kept for interface compatibility
    last_level: int         # Last configured fan level (0..100%)
    deferred_apply: bool    # If True, skip IPMI calls (used for zone arbitration)

    def __init__(self, log: Log, ipmi: Ipmi, cfg: ConstConfig) -> None:
        """Initialize the CONST fan controller class and raise exception in case invalid configuration items.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            cfg (ConstConfig): CONST fan controller configuration
        """
        # Store config reference
        self.config = cfg

        # Initialize ConstFc class.
        self.log = log
        self.ipmi = ipmi
        self.name = cfg.section
        self.last_time = 0.0
        self.last_temp = 0.0
        self.last_level = cfg.level
        self.deferred_apply = False

        # Print configuration at CONFIG log level.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"{self.name} fan controller was initialized with:")
            self.log.msg(Log.LOG_CONFIG, f"   ipmi zone = {self.config.ipmi_zone}")
            self.log.msg(Log.LOG_CONFIG, f"   polling = {self.config.polling}")
            self.log.msg(Log.LOG_CONFIG, f"   level = {self.config.level}")

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
        if (current_time - self.last_time) >= self.config.polling:
            self.last_time = current_time

            # Step 2: in deferred mode, just store the desired level for arbitration.
            if self.deferred_apply:
                self.last_level = self.config.level
                return

            # Check in all IPMI zones if the current fan level is the expected one,
            # otherwise set the fan level again.
            for zone in self.config.ipmi_zone:
                level = self.ipmi.get_fan_level(zone)
                if self.log.log_level >= Log.LOG_DEBUG:
                    self.log.msg(Log.LOG_DEBUG, f"{self.name}: zone {zone} current={level}% "
                                 f"expected={self.config.level}%")
                if level != self.config.level:
                    self.ipmi.set_fan_level(zone, self.config.level)
                    self.log.msg(Log.LOG_INFO, f"{self.name}: set fan level > {self.config.level}% "
                                               f"@ IPMI {self.config.ipmi_zone} zone(s).")


# End.
