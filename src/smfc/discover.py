#
#   discover.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.discover: find the disks of hd_names= and nvme_names=, and write them into the configuration.
#
import argparse
import os
import re
import sys
from typing import List, Optional, Sequence

# Directory holding the stable device names smfc writes into the configuration file.
BY_ID_DIR: str = "/dev/disk/by-id"

# Names excluded from hd_names=. A partition, an opaque alias (wwn-, -eui), an NVMe drive, a USB stick,
# a mapped or software volume, and the numbered duplicate udev creates for a name it has seen before.
HD_EXCLUDE: str = r"-part|^wwn-|-eui|nvme|^usb-|^dm-|^lvm-|^md-|^zd-|_[0-9]+$"

# Names accepted into nvme_names=: only the model-and-serial form of an NVMe drive.
NVME_INCLUDE: str = r"^nvme-"

# Names excluded from nvme_names=. A partition, the EUI and the NQN alias of the same drive, and the
# numbered duplicate. A usb- name can never reach this filter, because NVME_INCLUDE is anchored.
NVME_EXCLUDE: str = r"-part|-eui|-nvme|_[0-9]+$"

# Separator between two entries of a device list: a newline and a tab, which configparser reads as a
# continuation line. The first entry stays on the key line, or the value gains an empty first element.
LIST_SEPARATOR: str = "\n\t"


def _list_by_id(by_id_dir: str) -> List[str]:
    """List the stable device names of a system, sorted by name.
    Args:
        by_id_dir (str): directory to read (default: /dev/disk/by-id)
    Returns:
        List[str]: the names found there, empty if the directory does not exist
    """
    if not os.path.isdir(by_id_dir):
        return []
    return sorted(os.listdir(by_id_dir))


def discover_hds(by_id_dir: str = BY_ID_DIR) -> List[str]:
    """Find the SATA and SAS disks of this system.
    Args:
        by_id_dir (str): directory to read (default: /dev/disk/by-id)
    Returns:
        List[str]: one /dev/disk/by-id/... path per physical disk, sorted by name
    """
    exclude = re.compile(HD_EXCLUDE)
    return [f"{by_id_dir}/{name}" for name in _list_by_id(by_id_dir) if not exclude.search(name)]


def discover_nvmes(by_id_dir: str = BY_ID_DIR) -> List[str]:
    """Find the NVMe drives of this system.
    Args:
        by_id_dir (str): directory to read (default: /dev/disk/by-id)
    Returns:
        List[str]: one /dev/disk/by-id/... path per physical drive, sorted by name
    """
    include = re.compile(NVME_INCLUDE)
    exclude = re.compile(NVME_EXCLUDE)
    return [f"{by_id_dir}/{name}" for name in _list_by_id(by_id_dir)
            if include.search(name) and not exclude.search(name)]


def format_device_list(devices: Sequence[str]) -> str:
    """Render a device list the way the configuration file holds it.
    The first entry stays on the key line and every further entry gets its own tab-indented line. A
    value that starts with a newline parses into an empty first element, which is why the first entry
    may not be moved down. The trailing separator is what the installer has always written, and
    configparser strips it.
    Args:
        devices (Sequence[str]): device paths, in the order they should appear
    Returns:
        str: the value of hd_names= or nvme_names=, empty if there is no device
    """
    if not devices:
        return ""
    return LIST_SEPARATOR.join(devices) + LIST_SEPARATOR


def fill_empty_key(config_path: str, key: str, devices: Sequence[str]) -> bool:
    """Write a device list into a configuration file, but only where the key is still empty.
    A key that already carries a value belongs to the user, so it is never touched. That is the rule
    both package scripts follow, and it is the one the installer lacked.
    Args:
        config_path (str): path of the configuration file
        key (str): parameter name (e.g. "hd_names")
        devices (Sequence[str]): device paths to write
    Returns:
        bool: True if the file was changed
    """
    if not devices:
        return False
    with open(config_path, "rt", encoding="utf-8") as file:
        lines = file.readlines()
    empty_key = f"{key}="
    changed = False
    for index, line in enumerate(lines):
        if line.rstrip("\n") == empty_key:
            lines[index] = f"{empty_key}{format_device_list(devices)}\n"
            changed = True
            break
    if changed:
        with open(config_path, "wt", encoding="utf-8") as file:
            file.writelines(lines)
    return changed


def main(argv: Optional[List[str]] = None) -> int:
    """Command line entry point, used by the installer and by both package scripts.
    Without --fill it prints one device path per line. With --fill it writes the list into the named
    configuration file, and only where the matching key is still empty.
    Args:
        argv (Optional[List[str]]): command line arguments (default: sys.argv[1:])
    Returns:
        int: 0 on success, 1 if the configuration file cannot be read or written
    """
    parser = argparse.ArgumentParser(
        prog="smfc.discover",
        description="List the disks smfc can monitor, in /dev/disk/by-id/ form.")
    parser.add_argument("kind", choices=["hd", "nvme"], help="which devices to list")
    parser.add_argument("-f", "--fill", metavar="FILE", default="",
                        help="write the list into this configuration file, if its key is empty")
    parser.add_argument("-d", "--dir", metavar="DIR", default=BY_ID_DIR,
                        help=f"directory to read (default: {BY_ID_DIR})")
    args = parser.parse_args(argv)

    devices = discover_hds(args.dir) if args.kind == "hd" else discover_nvmes(args.dir)
    key = "hd_names" if args.kind == "hd" else "nvme_names"
    if not args.fill:
        for device in devices:
            print(device)
        return 0
    try:
        fill_empty_key(args.fill, key, devices)
    except OSError as error:
        print(f"ERROR: cannot update {args.fill}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

# End.
