#
#   discover.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.discover: find the devices of hd_names=, nvme_names=, gpu_device_ids= and npu_device_ids=, and
#   write the disks into the configuration.
#
import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

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

# Time one vendor tool may take to list its cards. npu-smi needs about 1.5 seconds on a healthy card,
# and some drivers are slow to answer the first call after a boot.
TOOL_TIMEOUT: float = 10.0

# A line of `nvidia-smi -L`: "GPU 0: NVIDIA GeForce RTX 4090 (UUID: GPU-...)". The MIG lines below a
# GPU are indented and start with "MIG", so the anchor skips them.
NVIDIA_LINE: str = r"^GPU (\d+): (.*?)(?: \(UUID: [^)]*\))?$"

# The chip of an Ascend card that is not an NPU. npu-smi lists it among the chips, and smfc never reads
# its temperature, so it does not name the card either.
NPU_MCU_NAME: str = "mcu"


@dataclass
class Card:
    """One GPU or NPU card a vendor tool reports."""
    index: int          # What the configuration file holds: the GPU index or the npu-smi card ID
    name: str           # What the tool calls the card, empty when it gives no name


class DiscoveryError(RuntimeError):
    """A vendor tool could not be run, or it answered with something that cannot be read."""


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


def _run_tool(command: Sequence[str], timeout: float) -> str:
    """Run a vendor tool and return what it printed.
    Args:
        command (Sequence[str]): the command and its arguments
        timeout (float): seconds the command may take
    Returns:
        str: the standard output
    Raises:
        DiscoveryError: the command cannot be found, did not answer in time, or failed
    """
    arguments = list(command)
    try:
        result = subprocess.run(arguments, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise DiscoveryError(f"{arguments[0]} cannot be found") from e
    except subprocess.TimeoutExpired as e:
        raise DiscoveryError(f"{arguments[0]} did not answer within {timeout:.0f} seconds") from e
    except OSError as e:
        raise DiscoveryError(f"{arguments[0]} cannot be run: {e}") from e
    if result.returncode != 0:
        reason = (result.stderr or result.stdout).strip().splitlines()
        raise DiscoveryError(f"{arguments[0]} failed: {reason[0] if reason else f'exit code {result.returncode}'}")
    return result.stdout


def parse_nvidia_cards(output: str) -> List[Card]:
    """Read the GPUs from the output of `nvidia-smi -L`.
    The index is the position in the temperature report the GPU fan controller reads, because both
    lists come from nvidia-smi in the same order.
    Args:
        output (str): stdout of `nvidia-smi -L`
    Returns:
        List[Card]: one card per GPU, in index order
    """
    pattern = re.compile(NVIDIA_LINE)
    cards = [Card(int(m.group(1)), m.group(2).strip()) for m in map(pattern.match, output.splitlines()) if m]
    return sorted(cards, key=lambda c: c.index)


def parse_rocm_cards(output: str) -> List[Card]:
    """Read the GPUs from the output of `rocm-smi --showproductname --json`.
    The index is the number of the `cardN` key, the same key the GPU fan controller reads its
    temperature from. rocm-smi also lists a card of another vendor, with a vendor warning instead of
    the `Card ...` keys, and that card is left out: the GPU fan controller cannot read it.
    Args:
        output (str): stdout of `rocm-smi --showproductname --json`
    Returns:
        List[Card]: one card per GPU, in index order
    Raises:
        DiscoveryError: the output is not JSON
    """
    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        raise DiscoveryError(f"rocm-smi printed no valid JSON: {e}") from e
    cards: List[Card] = []
    for key, values in data.items() if isinstance(data, dict) else []:
        match = re.fullmatch(r"card(\d+)", key)
        if not match:
            continue
        info = values if isinstance(values, dict) else {}
        if not any(k.startswith("Card ") for k in info):
            continue
        # ROCm 4.0 wrote "Card series", later releases write "Card Series". A missing SKU is "N/A".
        names = [str(info.get(k, "")).strip() for k in ("Card Series", "Card series", "Card SKU")]
        cards.append(Card(int(match.group(1)), next((n for n in names if n and n != "N/A"), "")))
    return sorted(cards, key=lambda c: c.index)


def parse_npu_cards(output: str) -> List[Card]:
    """Read the cards from the output of `npu-smi info -m`.
    The tool prints one line per chip: the card ID first, the chip name last, and the chip ID and the
    chip logic ID between them. A card with two NPU chips is one card, and its MCU is not counted as a
    chip.
    Args:
        output (str): stdout of `npu-smi info -m`
    Returns:
        List[Card]: one card per card ID, in ID order; the name says how many NPU chips it carries
    """
    chips: Dict[int, List[str]] = {}
    for line in output.splitlines():
        columns = re.split(r"\s{2,}", line.strip())
        if len(columns) < 2 or not columns[0].isdigit():
            continue
        names = chips.setdefault(int(columns[0]), [])
        if columns[-1].lower() != NPU_MCU_NAME:
            names.append(columns[-1])
    cards: List[Card] = []
    for index in sorted(chips):
        names = chips[index]
        if not names:
            cards.append(Card(index, ""))
        elif len(set(names)) == 1 and len(names) > 1:
            cards.append(Card(index, f"{names[0]} x{len(names)}"))
        else:
            cards.append(Card(index, ", ".join(names)))
    return cards


def discover_gpus(gpu_type: str, nvidia_smi_path: str, rocm_smi_path: str,
                  timeout: float = TOOL_TIMEOUT) -> List[Card]:
    """Ask the vendor tool which GPUs this system has.
    Args:
        gpu_type (str): "nvidia" or "amd", as in gpu_type=
        nvidia_smi_path (str): path of nvidia-smi
        rocm_smi_path (str): path of rocm-smi
        timeout (float): seconds the tool may take
    Returns:
        List[Card]: one card per GPU, in index order
    Raises:
        DiscoveryError: the tool cannot be run, or its output cannot be read
    """
    if gpu_type == "amd":
        return parse_rocm_cards(_run_tool([rocm_smi_path, "--showproductname", "--json"], timeout))
    return parse_nvidia_cards(_run_tool([nvidia_smi_path, "-L"], timeout))


def discover_npus(npu_smi_path: str, timeout: float = TOOL_TIMEOUT) -> List[Card]:
    """Ask npu-smi which Ascend cards this system has.
    Args:
        npu_smi_path (str): path or name of npu-smi
        timeout (float): seconds the tool may take
    Returns:
        List[Card]: one card per card ID, in ID order
    Raises:
        DiscoveryError: the tool cannot be run
    """
    return parse_npu_cards(_run_tool([npu_smi_path, "info", "-m"], timeout))


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
