#!/usr/bin/env python3
#
#   test_discover.py (C) 2026, Peter Sulyok
#   Unit test for smfc.discover module.
#
import subprocess
from pathlib import Path
from typing import List
from unittest.mock import patch
import pytest
from smfc.config import Config
from smfc.discover import (BY_ID_DIR, Card, DiscoveryError, discover_gpus, discover_hds, discover_npus,
                           discover_nvmes, fill_empty_key, format_device_list, main, parse_npu_cards,
                           parse_nvidia_cards, parse_rocm_cards)


# Names of a system that holds two SATA disks, three NVMe drives, a USB stick and a ZFS volume.
# Every name here was taken from a real /dev/disk/by-id directory.
BY_ID_NAMES: List[str] = [
    "ata-WDC_WD120EFAX-68UNTN0_3A19R759",
    "ata-WDC_WD120EFAX-68UNTN0_3A19R759-part1",
    "ata-WDC_WD120EFAX-68UNTN0_YV4GL5UQ",
    "wwn-0x5000cca23b1c2d3e",
    "nvme-CT4000P3PSSD8_2336E8740474",
    "nvme-CT4000P3PSSD8_2336E8740474_1",
    "nvme-CT4000P3PSSD8_2336E8740474-part1",
    "nvme-eui.0025384161a097ed",
    "nvme-nvme.c0a9-323333364538373430343734-435434303030503350535344382d-00000001",
    "nvme-ADATA_LEGEND_800_2O4429AJ8DPT",
    "nvme-Samsung_SSD_990_PRO_2TB_AW76U6XB",
    "usb-SanDisk_Cruzer_Blade_0401234567-0:0",
    "dm-name-vg0-root",
    "md-uuid-2a1b3c4d:5e6f7a8b:9c0d1e2f:3a4b5c6d",
    "zd-0",
]


def _by_id(tmp_path: Path, names: List[str] = None) -> str:
    """Build a directory that stands in for /dev/disk/by-id.
    Args:
        tmp_path (Path): pytest temporary directory
        names (List[str]): names to create (default: BY_ID_NAMES)
    Returns:
        str: path of the created directory
    """
    directory = tmp_path / "by-id"
    directory.mkdir()
    for name in BY_ID_NAMES if names is None else names:
        (directory / name).write_text("", encoding="utf-8")
    return str(directory)


# Output of `nvidia-smi -L` on a machine with two GPUs, the second one split into MIG instances.
NVIDIA_L: str = (
    "GPU 0: NVIDIA GeForce RTX 4090 (UUID: GPU-5e8a1c2b-0d3f-4a6e-9b7c-1f2e3d4c5b6a)\n"
    "GPU 1: NVIDIA A100-SXM4-40GB (UUID: GPU-7a6b5c4d-3e2f-1a0b-9c8d-7e6f5a4b3c2d)\n"
    "  MIG 1g.5gb      Device  0: (UUID: MIG-1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d)\n"
)

# Output of `npu-smi info -m` on a machine with two Atlas 300I Duo cards, with narrower columns.
NPU_M: str = (
    "        NPU ID            Chip ID           Chip Logic ID     Chip Name\n"
    "        8                 0                 0                 Ascend 310P3\n"
    "        8                 1                 1                 Ascend 310P3\n"
    "        8                 2                 -                 Mcu\n"
    "        9                 0                 2                 Ascend 310P3\n"
    "        9                 1                 3                 Ascend 310P3\n"
    "        9                 2                 -                 Mcu\n"
)


# Output of `rocm-smi --showproductname --showmeminfo vram --showuniqueid --json` on a machine with a
# Radeon RX 6800/6900 card and the Raphael GPU of its AMD CPU, as it was posted in
# https://github.com/LostRuins/koboldcpp/issues/1104 (formatted there; the tool prints one line).
ROCM_JSON_IGPU: str = """{
  "card0": {
    "Unique ID": "0x9246____________",
    "VRAM Total Memory (B)": "17163091968",
    "VRAM Total Used Memory (B)": "708767744",
    "Card Series": "Navi 21 [Radeon RX 6800/6800 XT / 6900 XT]",
    "Card Model": "0x73bf",
    "Card Vendor": "Advanced Micro Devices, Inc. [AMD/ATI]",
    "Card SKU": "001",
    "Subsystem ID": "0x2406",
    "Device Rev": "0xc1",
    "Node ID": "1",
    "GUID": "45534",
    "GFX Version": "gfx1030"
  },
  "card1": {
    "Unique ID": "N/A",
    "VRAM Total Memory (B)": "67108864",
    "VRAM Total Used Memory (B)": "26079232",
    "Card Series": "Raphael",
    "Card Model": "0x164e",
    "Card Vendor": "Advanced Micro Devices, Inc. [AMD/ATI]",
    "Card SKU": "RAPHAEL",
    "Subsystem ID": "0x364e",
    "Device Rev": "0xc6",
    "Node ID": "2",
    "GUID": "52156",
    "GFX Version": "gfx1036"
  }
}
"""

# Output of `npu-smi info -m` on an Atlas 200I DK A2, the example of chapter 4.8 of the Huawei document
# "Ascend 310B 23.0.RC3 npu-smi command reference". The column widths are the ones of the PDF.
NPU_M_310B: str = (
    "     NPU ID            Chip ID       Chip Logic ID               Chip Name\n"
    "     0             0             0                       Ascend 310B1\n"
    "     0             1             -                       Mcu\n"
)

# Output of `rocm-smi --showproductname --json` on a machine with two Instinct MI300A cards and one card
# of another vendor. The values are the ones of the ROCm 6.1.1 changelog. The JSON form is built the way
# rocm_smi.py builds it: every "Key: value" line of a card goes under its cardN key, stripped.
ROCM_JSON: str = (
    '{"card0": {"Card Series": "Aqua Vanjaram [Instinct MI300A]", "Card Model": "0x74a0", '
    '"Card Vendor": "Advanced Micro Devices, Inc. [AMD/ATI]", "Card SKU": "N/A", "Subsystem ID": "0x74a0", '
    '"Device Rev": "0x00", "Node ID": "4", "GUID": "60294", "GFX Version": "gfx942"}, '
    '"card1": {"Card Series": "Aqua Vanjaram [Instinct MI300A]", "Card Model": "0x74a0", '
    '"Card Vendor": "Advanced Micro Devices, Inc. [AMD/ATI]", "Card SKU": "N/A", "Subsystem ID": "0x74a0", '
    '"Device Rev": "0x00", "Node ID": "5", "GUID": "35406", "GFX Version": "gfx942"}, '
    '"card2": {"GPU[2]\\t\\t": "Actual vendor name"}}'
)


# Output of `rocm-smi --showproductname --json` on a machine with one Radeon RX 7900 XT, as it was posted
# in https://github.com/marimo-team/marimo/issues/9237.
ROCM_JSON_RX7900: str = """{
  "card0": {
    "Card Series": "Radeon RX 7900 XT",
    "Card Model": "0x744c",
    "Card Vendor": "Advanced Micro Devices Inc. [AMD/ATI]",
    "Card SKU": "D70401XT",
    "Subsystem ID": "0x471e",
    "Device Rev": "0xcc",
    "Node ID": "1",
    "GUID": "26967",
    "GFX Version": "gfx1100"
  }
}
"""


def _tool(tmp_path: Path, output: str, code: int = 0) -> str:
    """Build a script that stands in for a vendor tool.
    Args:
        tmp_path (Path): pytest temporary directory
        output (str): what the script prints
        code (int): the exit code of the script
    Returns:
        str: path of the script
    """
    (tmp_path / "output.txt").write_text(output, encoding="utf-8")
    script = tmp_path / "tool"
    script.write_text(f"#!/bin/sh\ncat '{tmp_path / 'output.txt'}'\necho 'tool error' >&2\nexit {code}\n",
                      encoding="utf-8")
    script.chmod(0o755)
    return str(script)


class TestDiscover:
    """Unit test class for the smfc.discover module."""

    def test_hd_filter_keeps_only_whole_sata_disks(self, tmp_path: Path) -> None:
        """Positive unit test for discover_hds(). It contains the following steps:
        - build a by-id directory holding disks, partitions, aliases, a USB stick and volumes
        - call discover_hds()
        - ASSERT: both whole SATA disks are found, as full /dev/disk/by-id/ paths
        - ASSERT: a partition, a wwn- alias, an NVMe name, a USB stick and a volume are all dropped
        """
        directory = _by_id(tmp_path)
        assert discover_hds(directory) == [
            f"{directory}/ata-WDC_WD120EFAX-68UNTN0_3A19R759",
            f"{directory}/ata-WDC_WD120EFAX-68UNTN0_YV4GL5UQ",
        ]

    def test_nvme_filter_keeps_only_whole_drives(self, tmp_path: Path) -> None:
        """Positive unit test for discover_nvmes(). It contains the following steps:
        - build a by-id directory holding NVMe drives and each of their aliases
        - call discover_nvmes()
        - ASSERT: all three whole drives are found, once each
        - ASSERT: the partition, the EUI alias, the NQN alias and the duplicate are dropped
        """
        directory = _by_id(tmp_path)
        assert discover_nvmes(directory) == [
            f"{directory}/nvme-ADATA_LEGEND_800_2O4429AJ8DPT",
            f"{directory}/nvme-CT4000P3PSSD8_2336E8740474",
            f"{directory}/nvme-Samsung_SSD_990_PRO_2TB_AW76U6XB",
        ]

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("ata-Model_SERIAL01_1", id="duplicate-one"),
            pytest.param("ata-Model_SERIAL01_2", id="duplicate-two"),
            pytest.param("ata-Model_SERIAL01_3", id="duplicate-three"),
            pytest.param("ata-Model_SERIAL01_10", id="duplicate-ten"),
        ],
    )
    def test_every_numbered_duplicate_is_dropped(self, tmp_path: Path, name: str) -> None:
        """Negative unit test for discover_hds(). It contains the following steps:
        - build a by-id directory holding one disk and one numbered duplicate of it
        - call discover_hds()
        - ASSERT: only the undecorated name survives, whatever the number of the duplicate
        """
        directory = _by_id(tmp_path, ["ata-Model_SERIAL01", name])
        assert discover_hds(directory) == [f"{directory}/ata-Model_SERIAL01"]

    def test_a_usb_stick_never_reaches_the_nvme_filter(self, tmp_path: Path) -> None:
        """Positive unit test for discover_nvmes(). It contains the following steps:
        - build a by-id directory holding only a USB stick
        - call discover_nvmes()
        - ASSERT: the result is empty, because the NVMe filter is anchored on the nvme- prefix
        """
        directory = _by_id(tmp_path, ["usb-SanDisk_Cruzer_Blade_0401234567-0:0"])
        assert not discover_nvmes(directory)

    def test_a_missing_directory_is_not_an_error(self, tmp_path: Path) -> None:
        """Negative unit test for discover_hds() and discover_nvmes(). It contains the following steps:
        - name a directory that does not exist, which is the case on a system with no disk at all
        - call both discovery functions
        - ASSERT: both return an empty list instead of raising
        """
        missing = str(tmp_path / "nosuch")
        assert not discover_hds(missing)
        assert not discover_nvmes(missing)

    def test_the_default_directory_is_the_system_one(self) -> None:
        """Positive unit test for the module constants. It contains the following steps:
        - read the default directory of both discovery functions
        - ASSERT: it is /dev/disk/by-id, the only device names that survive a reboot
        """
        assert BY_ID_DIR == "/dev/disk/by-id"

    def test_format_puts_the_first_device_on_the_key_line(self) -> None:
        """Positive unit test for format_device_list(). It contains the following steps:
        - render a list of three devices
        - ASSERT: the first device starts the value, with no leading newline
        - ASSERT: every further device sits on its own tab-indented line
        - ASSERT: the value ends with a separator, as the installer has always written it
        """
        value = format_device_list(["/dev/a", "/dev/b", "/dev/c"])
        assert value == "/dev/a\n\t/dev/b\n\t/dev/c\n\t"
        assert not value.startswith("\n")

    def test_format_of_an_empty_list(self) -> None:
        """Negative unit test for format_device_list(). It contains the following steps:
        - render an empty device list
        - ASSERT: the value is empty, so the key stays empty rather than gaining a stray tab
        """
        assert format_device_list([]) == ""

    def test_written_value_parses_back_to_the_same_devices(self, tmp_path: Path) -> None:
        """Positive unit test for fill_empty_key(). It contains the following steps:
        - write three devices into a configuration file that has an empty hd_names= key
        - parse the file with the real Config class
        - ASSERT: the file was changed
        - ASSERT: the parser returns exactly the three devices
        - ASSERT: the first element is not empty, which is the trap of a leading newline
        """
        devices = ["/dev/disk/by-id/ata-A", "/dev/disk/by-id/ata-B", "/dev/disk/by-id/ata-C"]
        path = tmp_path / "smfc.conf"
        path.write_text("[Ipmi]\n[HD]\nenabled=1\nhd_names=\nsmartctl_path=/usr/sbin/smartctl\n",
                        encoding="utf-8")
        assert fill_empty_key(str(path), "hd_names", devices) is True
        assert Config(str(path)).hd[0].hd_names == devices

    def test_a_key_that_already_has_a_value_is_never_touched(self, tmp_path: Path) -> None:
        """Negative unit test for fill_empty_key(). It contains the following steps:
        - write a configuration file whose hd_names= key already lists a disk
        - call fill_empty_key() with a different disk
        - ASSERT: the function reports no change
        - ASSERT: the file still holds the user's own value
        """
        path = tmp_path / "smfc.conf"
        body = "[Ipmi]\n[HD]\nenabled=1\nhd_names=/dev/disk/by-id/ata-USER\n"
        path.write_text(body, encoding="utf-8")
        assert fill_empty_key(str(path), "hd_names", ["/dev/disk/by-id/ata-NEW"]) is False
        assert path.read_text(encoding="utf-8") == body

    def test_an_empty_device_list_changes_nothing(self, tmp_path: Path) -> None:
        """Negative unit test for fill_empty_key(). It contains the following steps:
        - call fill_empty_key() with no device at all, as on a machine that has none
        - ASSERT: the function reports no change
        - ASSERT: the file is left exactly as it was
        """
        path = tmp_path / "smfc.conf"
        body = "[Ipmi]\n[HD]\nhd_names=\n"
        path.write_text(body, encoding="utf-8")
        assert fill_empty_key(str(path), "hd_names", []) is False
        assert path.read_text(encoding="utf-8") == body

    def test_the_comment_above_the_key_survives(self, tmp_path: Path) -> None:
        """Positive unit test for fill_empty_key(). It contains the following steps:
        - write a configuration file that documents hd_names= with a comment, as the shipped file does
        - fill the key
        - ASSERT: the comment above the key is still there, because only the key line is rewritten
        """
        path = tmp_path / "smfc.conf"
        path.write_text("[Ipmi]\n[HD]\n# Names of the HDs (str multi-line list, default=)\nhd_names=\n",
                        encoding="utf-8")
        fill_empty_key(str(path), "hd_names", ["/dev/disk/by-id/ata-A"])
        assert "# Names of the HDs (str multi-line list, default=)" in path.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "kind, expected",
        [
            pytest.param("hd", "ata-WDC_WD120EFAX-68UNTN0_3A19R759", id="hd"),
            pytest.param("nvme", "nvme-ADATA_LEGEND_800_2O4429AJ8DPT", id="nvme"),
        ],
    )
    def test_command_line_prints_one_device_per_line(self, tmp_path: Path, capsys, kind: str,
                                                     expected: str) -> None:
        """Positive unit test for main(). It contains the following steps:
        - run the module with a kind and a directory, and without --fill
        - ASSERT: it returns 0
        - ASSERT: it prints one device path per line, which is what the shell scripts read
        """
        directory = _by_id(tmp_path)
        assert main([kind, "--dir", directory]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert f"{directory}/{expected}" in lines

    def test_command_line_fills_the_configuration_file(self, tmp_path: Path) -> None:
        """Positive unit test for main(). It contains the following steps:
        - run the module with --fill against a configuration file with an empty hd_names= key
        - ASSERT: it returns 0
        - ASSERT: the two whole SATA disks were written into the file
        """
        directory = _by_id(tmp_path)
        path = tmp_path / "smfc.conf"
        path.write_text("[Ipmi]\n[HD]\nenabled=1\nhd_names=\n", encoding="utf-8")
        assert main(["hd", "--dir", directory, "--fill", str(path)]) == 0
        assert len(Config(str(path)).hd[0].hd_names) == 2

    def test_command_line_reports_an_unwritable_file(self, tmp_path: Path, capsys) -> None:
        """Negative unit test for main(). It contains the following steps:
        - run the module with --fill against a configuration file that does not exist
        - ASSERT: it returns 1 instead of raising
        - ASSERT: it names the file in an error message on stderr
        """
        directory = _by_id(tmp_path)
        assert main(["hd", "--dir", directory, "--fill", str(tmp_path / "nosuch.conf")]) == 1
        assert "nosuch.conf" in capsys.readouterr().err


class TestDiscoverCards:
    """Unit test class for the GPU and NPU discovery of the smfc.discover module."""

    def test_nvidia_cards_are_read_from_the_list(self) -> None:
        """Positive unit test for parse_nvidia_cards(). It contains the following steps:
        - parse the output of nvidia-smi -L with two GPUs and one MIG instance
        - ASSERT: both GPUs are found with their index and name, and the UUID is dropped
        - ASSERT: the MIG line is not counted as a GPU
        """
        assert parse_nvidia_cards(NVIDIA_L) == [Card(0, "NVIDIA GeForce RTX 4090"),
                                                Card(1, "NVIDIA A100-SXM4-40GB")]

    @pytest.mark.parametrize(
        "output, expected",
        [
            pytest.param(ROCM_JSON_RX7900, [Card(0, "Radeon RX 7900 XT")], id="rx-7900-xt"),
            pytest.param(ROCM_JSON_IGPU, [Card(0, "Navi 21 [Radeon RX 6800/6800 XT / 6900 XT]"),
                                          Card(1, "Raphael")], id="discrete-and-integrated"),
            pytest.param(ROCM_JSON, [Card(0, "Aqua Vanjaram [Instinct MI300A]"),
                                     Card(1, "Aqua Vanjaram [Instinct MI300A]")], id="mi300a-and-other-vendor"),
            pytest.param('{"card1": {"Card Series": "Navi 31"}, "card0": {"Card Series": "Navi 21"}}',
                         [Card(0, "Navi 21"), Card(1, "Navi 31")], id="sorted-by-index"),
            pytest.param('{"card0": {"Card series": "Vega 20", "Card SKU": "D16304"}}', [Card(0, "Vega 20")],
                         id="rocm-4.0-key"),
            pytest.param('{"card0": {"Card Model": "0x744c", "Card SKU": "D70701"}}', [Card(0, "D70701")],
                         id="sku-without-series"),
            pytest.param('{"card0": {"Card Model": "0x74a0", "Card SKU": "N/A"}, "system": {"Driver version": "6.8"}}',
                         [Card(0, "")], id="no-name"),
        ],
    )
    def test_rocm_cards_are_read_from_the_json(self, output: str, expected: List[Card]) -> None:
        """Positive unit test for parse_rocm_cards(). It contains the following steps:
        - parse the JSON of rocm-smi --showproductname in the forms ROCm releases print
        - ASSERT: every AMD cardN key becomes one card with index N, sorted by index
        - ASSERT: a card of another vendor and a key that is not a card are left out
        - ASSERT: a SKU of N/A is not taken as a name, and a card with no name has an empty name
        """
        assert parse_rocm_cards(output) == expected

    def test_rocm_output_that_is_not_json_is_an_error(self) -> None:
        """Negative unit test for parse_rocm_cards(). It contains the following steps:
        - parse a line of text instead of JSON
        - ASSERT: DiscoveryError is raised, so the popup can say why the scan failed
        """
        with pytest.raises(DiscoveryError):
            parse_rocm_cards("WARNING: no AMD GPU found")

    def test_npu_cards_are_counted_without_the_mcu(self) -> None:
        """Positive unit test for parse_npu_cards(). It contains the following steps:
        - parse the output of npu-smi info -m with two dual-chip cards
        - ASSERT: one card per card ID, not one per chip, and the IDs need not start at 0
        - ASSERT: the MCU is not counted as a chip
        """
        assert parse_npu_cards(NPU_M) == [Card(8, "Ascend 310P3 x2"), Card(9, "Ascend 310P3 x2")]

    def test_the_npu_card_of_the_huawei_reference(self) -> None:
        """Positive unit test for parse_npu_cards(). It contains the following steps:
        - parse the npu-smi info -m example of the Huawei command reference: one chip and one MCU
        - ASSERT: one card with ID 0, named after its NPU chip, and the MCU is not counted
        """
        assert parse_npu_cards(NPU_M_310B) == [Card(0, "Ascend 310B1")]

    def test_gpus_are_listed_by_the_configured_tool(self, tmp_path: Path) -> None:
        """Positive unit test for discover_gpus(). It contains the following steps:
        - stand in for nvidia-smi and for rocm-smi with a script each
        - ASSERT: gpu_type=nvidia runs the nvidia-smi path and gpu_type=amd the rocm-smi path
        """
        (tmp_path / "nvidia").mkdir()
        (tmp_path / "amd").mkdir()
        nvidia = _tool(tmp_path / "nvidia", NVIDIA_L)
        amd = _tool(tmp_path / "amd", ROCM_JSON)
        assert len(discover_gpus("nvidia", nvidia, amd)) == 2
        assert [c.index for c in discover_gpus("amd", nvidia, amd)] == [0, 1]

    def test_npus_are_listed_by_npu_smi(self, tmp_path: Path) -> None:
        """Positive unit test for discover_npus(). It contains the following steps:
        - stand in for npu-smi with a script
        - ASSERT: the two cards of its output are found
        """
        assert [c.index for c in discover_npus(_tool(tmp_path, NPU_M))] == [8, 9]

    def test_a_missing_tool_is_an_error(self, tmp_path: Path) -> None:
        """Negative unit test for discover_gpus(). It contains the following steps:
        - name a tool that does not exist
        - ASSERT: DiscoveryError is raised and names the tool
        """
        path = str(tmp_path / "nvidia-smi")
        with pytest.raises(DiscoveryError, match="cannot be found"):
            discover_gpus("nvidia", path, "")

    def test_a_failing_tool_is_an_error(self, tmp_path: Path) -> None:
        """Negative unit test for discover_npus(). It contains the following steps:
        - stand in for npu-smi with a script that fails
        - ASSERT: DiscoveryError is raised and carries the first line the tool printed on stderr
        """
        with pytest.raises(DiscoveryError, match="tool error"):
            discover_npus(_tool(tmp_path, "", code=2))

    def test_a_tool_that_does_not_answer_is_an_error(self) -> None:
        """Negative unit test for discover_npus(). It contains the following steps:
        - let the tool run past its timeout
        - ASSERT: DiscoveryError is raised and names the timeout
        """
        with patch("smfc.discover.subprocess.run", side_effect=subprocess.TimeoutExpired("npu-smi", 2.0)):
            with pytest.raises(DiscoveryError, match="within 2 seconds"):
                discover_npus("npu-smi", 2.0)


# End.
