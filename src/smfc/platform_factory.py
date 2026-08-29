#
#   platform_factory.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   Factory function for creating platform-specific implementations.
#
import subprocess
from typing import Callable, List

from smfc.config import PlatformName
from smfc.generic import GenericPlatform
from smfc.genericx9 import GenericX9Platform
from smfc.genericx14 import X14AtenPlatform, X14OpenBmcCmd, X14OpenBmcPlatform
from smfc.platform import IpmiError, Platform
from smfc.x10qbi import X10QBi

# Part 1.1 of `doc/X14H14_MANUAL_FANCONTROL.md`: read the manual-mode flag of zone 1. This is the only
# command that is safe to send to an X14/H14 board whose firmware stack is unknown - it changes nothing.
# It is taken from the OpenBMC command table rather than spelled out again: the probe asks whether that
# command set exists, so the bytes it sends must be the bytes the platform would send.
X14_STACK_PROBE: List[str] = X14OpenBmcCmd.read_manual(0)
CC_INVALID_COMMAND: int = 0xC1      # The OEM manual-mode command does not exist -> ATEN firmware
STACK_PROBE_DOC: str = "doc/X14H14_MANUAL_FANCONTROL.md, Part 1"


def _create_x14_platform(platform_name: str,
                         exec_ipmitool: Callable[[List[str]], subprocess.CompletedProcess]) -> Platform:
    """Probe which of the two 14th generation BMC firmware stacks the board runs, and return its platform.

    Supermicro's 14th generation ships two unrelated BMC firmware stacks and the split does not follow the
    board generation: most X14 boards plus `H14SHM` run OpenBMC, while all other H14 boards plus the SoC
    boards `X14SDW`/`X14SDV` run ATEN. The BMC product name therefore cannot decide which command set
    applies, and a runtime probe must.

    There is deliberately no "try one, fall back to the other" branch. Part 1.3: the two stacks share the
    `0x30 0x70 0x66` layout - selector 0x00 reads a duty, 0x01 writes one - but selector 0x02 means per-zone
    manual mode on OpenBMC and a global bypass flag on ATEN. A fallback would therefore be accepted by the
    board and apply the wrong lever, taking over every zone where only one was meant, or none at all. Only
    completion code 0xC1 means ATEN; every other failure is fatal.
    Args:
        platform_name (str): the platform name (configuration value or BMC product name)
        exec_ipmitool (Callable): function that executes ipmitool commands
    Returns:
        Platform: X14OpenBmcPlatform or X14AtenPlatform
    Raises:
        FileNotFoundError: ipmitool cannot be found
        RuntimeError: the firmware stack could not be determined
    """
    try:
        r = exec_ipmitool(X14_STACK_PROBE)
    except IpmiError as e:
        if e.completion_code == CC_INVALID_COMMAND:
            return X14AtenPlatform(platform_name, exec_ipmitool)
        raise RuntimeError(f"Cannot determine the BMC fan control stack (see {STACK_PROBE_DOC}): {e}") from e
    # The reply echoes the IANA ID of the OEM command back before the payload (`cf c2 00 <flag>`), so the
    # flag is the last byte. A reply the probe cannot interpret is not evidence of either stack, so it must
    # not be guessed away.
    try:
        flag = int(r.stdout.split()[-1], 16)
    except (IndexError, ValueError) as e:
        raise RuntimeError(f"Cannot determine the BMC fan control stack (see {STACK_PROBE_DOC}): the manual "
                           f"fan mode flag could not be parsed from '{r.stdout.strip()}'.") from e
    if flag not in (0, 1):
        raise RuntimeError(f"Cannot determine the BMC fan control stack (see {STACK_PROBE_DOC}): the manual "
                           f"fan mode flag read back as 0x{flag:02x}, which is neither 0x00 nor 0x01.")
    return X14OpenBmcPlatform(platform_name, exec_ipmitool)


def create_platform(platform_name: str,
                    exec_ipmitool: Callable[[List[str]], subprocess.CompletedProcess]) -> Platform:
    """Factory method to create the appropriate Platform object for the given platform name.
    Args:
        platform_name (str): The platform name, one of:
            - 'generic': force the GenericPlatform (X10-X13/H10-H13)
            - 'generic_x9': force the GenericX9Platform (X9 motherboards)
            - 'generic_x14': force the X14/H14 platform *family* (the firmware stack is probed for)
            - 'X10QBi': force the X10QBi platform
            - any other string: auto-detected from the BMC product name prefix
              ('X14...'/'H14...' -> the X14/H14 family, 'X10QBi...' -> X10QBi, 'X9...' -> X9),
              falls back to GenericPlatform
        exec_ipmitool (Callable): Function that executes ipmitool commands
    Returns:
        Platform: The platform-specific implementation (defaults to GenericPlatform)
    Raises:
        FileNotFoundError: ipmitool cannot be found
        RuntimeError: an X14/H14 board whose firmware stack could not be determined
    """
    # The 14th generation is a platform *family*: `generic_x14` and both name prefixes resolve to it, and the
    # concrete class is chosen by the probe. No OEM command is ever sent to a board outside the family, so
    # X9-X13 auto-detection is untouched.
    if platform_name == PlatformName.GENERIC_X14 or platform_name.startswith(("X14", "H14")):
        return _create_x14_platform(platform_name, exec_ipmitool)
    platform_factory = {
        PlatformName.GENERIC: GenericPlatform,
        PlatformName.GENERIC_X9: GenericX9Platform,
        PlatformName.X10QBI: X10QBi,
    }
    platform_class = platform_factory.get(platform_name)
    if platform_class is None:
        if platform_name.startswith("X10QBi"):
            platform_class = X10QBi
        elif platform_name.startswith("X9"):
            platform_class = GenericX9Platform
        else:
            platform_class = GenericPlatform
    return platform_class(platform_name, exec_ipmitool)


# End.
