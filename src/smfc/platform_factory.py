#
#   platform_factory.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   Factory function for creating platform-specific implementations.
#
import subprocess
from typing import Callable, List

from smfc.generic import GenericPlatform
from smfc.genericx9 import GenericX9Platform
from smfc.platform import Platform
from smfc.x10qbi import X10QBi


def create_platform(platform_name: str, exec_ipmitool: Callable[[List[str]], subprocess.CompletedProcess]) -> Platform:
    """Factory method to create the appropriate Platform object for the given platform name.
    Args:
        platform_name (str): The platform name, one of:
            - 'generic': force the GenericPlatform (X10-X13/H10-H13)
            - 'genericx9': force the GenericX9Platform (X9 motherboards)
            - 'X10QBi': force the X10QBi platform
            - any other string: looked up in the platform registry, falls back to GenericPlatform
        exec_ipmitool (Callable): Function that executes ipmitool commands
    Returns:
        Platform: The platform-specific implementation (defaults to GenericPlatform)
    """
    platform_factory = {
        Platform.PLATFORM_GENERIC: GenericPlatform,
        Platform.PLATFORM_GENERIC_X9: GenericX9Platform,
        "X10QBi": X10QBi,
    }
    return platform_factory.get(platform_name, GenericPlatform)(platform_name, exec_ipmitool)


# End.
