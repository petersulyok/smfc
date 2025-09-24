#
#   ipmi.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.sharedzone.IpmiZoneUser() and smfc.sharedzone.SharedIpmiZone() class implementation.
#
from smfc.log import Log

class IpmiZoneUser:
    """IpmiZoneUser is used to represent a user (a FanController instance) of an IPMI zone"""
    def __init__(self, name: str):
        """Init IpmiZoneUser instance
        Args:
            name (str): Name of fan controller (i.e. HD Zone)
        """
        self.name = name
        self.last_temperature = None
        self.desired_level = None

    def set_desired_level(self, new_level, last_temperature):
        """Records the desired fan level being emitted by this controller, along with the temperature"""
        self.desired_level = new_level
        self.last_temperature = last_temperature


    def __repr__(self):
        return f"<IpmiZoneUser {self.name}, desires {self.desired_level}% for {self.last_temperature}C>"


class SharedIpmiZone:
    """SharedIpmiZone is used to manage a Shared IPMI zone.

    Each IpmiZoneUser sets their desired fan level, and the run() function takes the max
    """
    def __init__(self, zone: int, users: list[IpmiZoneUser], ipmi: "smfc.ipmi.Ipmi", log: Log):
        """Initialize the SharedIpmiZone class.
        Args:
            zone (int): The IPMI zone being shared
            users (List[IpmiZoneUser]): List of IPMI Zone users (as recorded by register_fan_controller)
            ipmi (Ipmi): The IPMI instance
            log (Log): a Log class instance
        Raises:
            ValueError: invalid input parameters
            FileNotFoundError: ipmitool not found
            RuntimeError: ipmitool execution error
        """
        self.zone = zone
        self.ipmi = ipmi
        self.log = log
        self.current_fan_level = None
        self.name = f"Shared IPMI Zone {zone}"
        self.zone_users = users
        if len(self.zone_users) <= 1:
            raise ValueError(f"IPMI zone {self.zone} does not appear to be shared"
                             f" - only has {len(self.zone_users)} controllers registered to it")

    def __repr__(self):
        return f"<SharedIpmiZone {self.zone} with {len(self.zone_users)} controllers>"


    def run(self):
        """
        Finds the maximum desired level from any controller in this zone, and changes fan level if required
        """
        # Find max desired level
        highest_desired_level_user = None
        for user in self.zone_users:
            if not highest_desired_level_user or user.desired_level > highest_desired_level_user.desired_level:
                highest_desired_level_user = user

        self.log.msg(Log.LOG_DEBUG, f"{self.name}: Most demanding zone user is {highest_desired_level_user}")
        # Check if desired level different to current
        if not highest_desired_level_user:
            return

        if not self.current_fan_level or highest_desired_level_user.desired_level != self.current_fan_level:
            current_level = highest_desired_level_user.desired_level
            current_temp = highest_desired_level_user.last_temperature
            if not current_temp:
                # temp is always set by FanController, but None is default to prevent breaking tests
                # However it must have a value here for f-string
                current_temp = 0
            self.log.msg(Log.LOG_INFO, f'{self.name}: new fan level > {current_level}%/{current_temp:.1f}C'
                         f', requested by {highest_desired_level_user.name}')
            self.current_fan_level = current_level
            self.ipmi.set_fan_level(self.zone, current_level)
