#!/usr/bin/env python3
#
#   test_discover.py (C) 2026, Peter Sulyok
#   Unit test for smfc.discover module.
#
from pathlib import Path
from typing import List
import pytest
from smfc.config import Config
from smfc.discover import (BY_ID_DIR, discover_hds, discover_nvmes, fill_empty_key, format_device_list,
                           main)


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


# End.
