#
#   constzone.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.ConstZone() class implementation.
#
import re
import time
from configparser import ConfigParser
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class ConstZone(FanController):
    """Constant zone fan control."""

    # Constant values for the configuration parameters.
    CS_CONST_ZONE: str = 'CONST zone'
    CV_CONST_ZONE_ENABLED: str = 'enabled'
    CV_CONST_IPMI_ZONE: str = 'ipmi_zone'
    CV_CONST_ZONE_POLLING: str = 'polling'
    CV_CONST_ZONE_LEVEL: str = 'level'

    # Constant level for the zone.
    level: int

    #pylint: disable=super-init-not-called
    def __init__(self, log: Log, ipmi: Ipmi, config:ConfigParser) -> None:
        """Initialize the ConstZone class and raise exception in case invalid configuration items.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            config (ConfigParser): reference to the configuration (default=None)
        Raises:
            ValueError: invalid configuration parameters
        """
        # Initialize ConstZone class.
        self.log = log
        self.ipmi = ipmi

        # Read the list of IPMI zones from a string (trim and remove multiple spaces, convert strings to integers)
        ipmi_zone_str = config[ConstZone.CS_CONST_ZONE].get(ConstZone.CV_CONST_IPMI_ZONE, fallback=f'{Ipmi.HD_ZONE}')
        ipmi_zone_str = re.sub(' +', ' ', ipmi_zone_str.strip())
        try:
            self.ipmi_zone = [int(s) for s in ipmi_zone_str.split(',' if ',' in ipmi_zone_str else ' ')]
        except ValueError as e:
            raise e
        for zone in self.ipmi_zone:
            if zone not in range(0, 101):
                raise ValueError(f'invalid value: ipmi_zone={ipmi_zone_str}.')

        self.name = ConstZone.CS_CONST_ZONE
        self.polling = config[ConstZone.CS_CONST_ZONE].getfloat(ConstZone.CV_CONST_ZONE_POLLING, fallback=30.0)
        if self.polling < 0:
            raise ValueError('polling < 0')
        self.level = config[ConstZone.CS_CONST_ZONE].getint(ConstZone.CV_CONST_ZONE_LEVEL, fallback=50)
        if self.level not in range(0, 101):
            raise ValueError('invalid level')
        self.last_time = 0

        # Print configuration at DEBUG log level.
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f'{self.name} fan controller was initialized with:')
            self.log.msg(Log.LOG_CONFIG, f'   ipmi zone = {self.ipmi_zone}')
            self.log.msg(Log.LOG_CONFIG, f'   polling = {self.polling}')
            self.log.msg(Log.LOG_CONFIG, f'   level = {self.level}')
    # pylint: enable=super-init-not-called

    def run(self) -> None:
        """Run IPMI zone controller function with the following steps:

            * Step 1: Read current time. If the elapsed time is bigger than the polling time period,
              then go to step 2, otherwise return.
            * Step 2: Loop through IPMI zones: read current fan level in the zone, if the level is different from the
              expected one then we set fan level in the zone again, otherwise return.
            * Step 3: Log the fan level.
        """
        current_time: float     # Current system timestamp (measured)

        # Step 1: check the elapsed time.
        current_time = time.monotonic()
        if (time.monotonic() - self.last_time) >= self.polling:
            self.last_time = current_time

            # Check in all IPMI zones if the current fan level is the expected one,
            # otherwise set the fan level again.
            for zone in self.ipmi_zone:
                level = self.ipmi.get_fan_level(zone)
                if level != self.level:
                    self.ipmi.set_fan_level(zone, self.level)
                    self.log.msg(Log.LOG_INFO, f'{self.name}: set fan level > {self.level}% '
                                               f'@ IPMI {self.ipmi_zone} zone(s).')


# End.
