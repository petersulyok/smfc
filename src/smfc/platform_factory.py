#
#   platform_factory.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   Factory function for creating platform-specific implementations.
#
import subprocess
from typing import Callable, List

from smfc.generic import GenericPlatform
from smfc.genericx9 import GenericX9Platform
from smfc.genericx14 import GenericX14Platform
from smfc.platform import Platform, PlatformName
from smfc.x10qbi import X10QBi


def create_platform(platform_name: str, exec_ipmitool: Callable[[List[str]], subprocess.CompletedProcess]) -> Platform:
    """Factory method to create the appropriate Platform object for the given platform name.
    Args:
        platform_name (str): The platform name, one of:
            - 'generic': force the GenericPlatform (X10-X13/H10-H13)
            - 'genericx9': force the GenericX9Platform (X9 motherboards)
            - 'genericx14': force the GenericX14Platform (X14 motherboards)
            - 'X10QBi': force the X10QBi platform
            - any other string: looked up in the platform registry, falls back to GenericPlatform
        exec_ipmitool (Callable): Function that executes ipmitool commands
    Returns:
        Platform: The platform-specific implementation (defaults to GenericPlatform)
    """
    platform_factory = {
        PlatformName.GENERIC: GenericPlatform,
        PlatformName.GENERIC_X9: GenericX9Platform,
        PlatformName.GENERIC_X14: GenericX14Platform,
        PlatformName.X10QBI: X10QBi,
    }
    return platform_factory.get(platform_name, GenericPlatform)(platform_name, exec_ipmitool)


# End.
