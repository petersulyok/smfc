#!/usr/bin/env python3
#
#   test_confwriter.py (C) 2026, Peter Sulyok
#   Unit test for smfc.config_editor.confwriter module.
#
import os
import shutil
from pathlib import Path
from typing import List
import pytest
from smfc.config import Config
from smfc.config_editor.confwriter import ConfWriter, is_writable


# Repository paths used by the tests.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
SHIPPED_CONF: Path = REPO_ROOT / "config" / "smfc.conf"
SAMPLES: List[Path] = sorted((REPO_ROOT / "config" / "samples").glob("*.conf"))

# A small file that carries a comment above every parameter, like the shipped one.
COMMENTED: str = (
    "# smfc configuration\n"
    "[Ipmi]\n"
    "# Path for ipmitool (str, default=/usr/bin/ipmitool)\n"
    "command=/usr/bin/ipmitool\n"
    "\n"
    "# CPU fan controller.\n"
    "[CPU]\n"
    "# Fan controller enabled (bool, default=0/false)\n"
    "enabled=1\n"
    "# Minimum CPU temperature (float, Celsius, default=30.0)\n"
    "min_temp=30.0\n"
)


def _copy(tmp_path: Path, source: Path) -> Path:
    """Copy a configuration file into the temporary directory of a test.
    Args:
        tmp_path (Path): pytest temporary directory
        source (Path): file to copy
    Returns:
        Path: path of the copy
    """
    target = tmp_path / source.name
    shutil.copy(source, target)
    return target


def _write(tmp_path: Path, body: str) -> Path:
    """Write a configuration file into the temporary directory of a test.
    Args:
        tmp_path (Path): pytest temporary directory
        body (str): content of the file
    Returns:
        Path: path of the written file
    """
    target = tmp_path / "smfc.conf"
    target.write_text(body, encoding="utf-8")
    return target


class TestConfWriter:
    """Unit test class for the smfc.config_editor.confwriter module."""

    @pytest.mark.parametrize("source", SAMPLES + [SHIPPED_CONF], ids=lambda p: p.name)
    def test_a_save_without_a_change_rewrites_the_file_byte_for_byte(self, tmp_path: Path,
                                                                     source: Path) -> None:
        """Positive unit test for ConfWriter.save(). It contains the following steps:
        - copy one of the eleven shipped samples, or the shipped smfc.conf, into a temporary directory
        - read it and save it again without changing anything
        - ASSERT: the file is identical to the original, byte for byte
        This is the acceptance test of the writer: a user who changes nothing must see no diff.
        """
        target = _copy(tmp_path, source)
        ConfWriter(str(target)).save()
        assert target.read_bytes() == source.read_bytes()

    def test_sections_are_listed_in_file_order(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.sections(). It contains the following steps:
        - read a file that holds numbered instances
        - ASSERT: every section is listed, with its instance number, in the order of the file
        """
        target = _write(tmp_path, "[Ipmi]\n[CPU:0]\n[CPU:1]\n[HD]\n")
        assert ConfWriter(str(target)).sections() == ["Ipmi", "CPU:0", "CPU:1", "HD"]

    def test_keys_of_a_section_are_listed_in_file_order(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.keys(). It contains the following steps:
        - read a file whose sections carry comments between the parameters
        - ASSERT: only the parameters of the named section are listed, in file order
        - ASSERT: a comment line is not mistaken for a parameter
        """
        target = _write(tmp_path, COMMENTED)
        writer = ConfWriter(str(target))
        assert writer.keys("CPU") == ["enabled", "min_temp"]
        assert writer.keys("Ipmi") == ["command"]

    def test_keys_of_an_absent_section(self, tmp_path: Path) -> None:
        """Negative unit test for ConfWriter.keys(). It contains the following steps:
        - ask for the parameters of a section the file does not hold
        - ASSERT: the result is empty instead of an exception
        """
        target = _write(tmp_path, COMMENTED)
        assert not ConfWriter(str(target)).keys("PCI")

    def test_changing_a_value_keeps_the_comment_above_it(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.set(). It contains the following steps:
        - read the shipped configuration file, which documents every parameter with a comment
        - change one value and save
        - ASSERT: the new value is in the file
        - ASSERT: the comment above that parameter is still there
        - ASSERT: the file lost no line, because only the value changed
        """
        target = _copy(tmp_path, SHIPPED_CONF)
        before = target.read_text(encoding="utf-8")
        writer = ConfWriter(str(target))
        writer.set("CPU", "min_temp", "40.0")
        writer.save()
        after = target.read_text(encoding="utf-8")
        assert "min_temp=40.0" in after
        assert "# Minimum CPU temperature (float, Celsius, default=30.0)" in after
        assert len(after.splitlines()) == len(before.splitlines())

    def test_a_changed_value_parses_back(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.set(). It contains the following steps:
        - change one value of the shipped configuration file and save
        - switch [HD] off, because the shipped file enables it with an empty hd_names= and the parser
          rejects that until the installer fills the disks in
        - parse the result with the real Config class
        - ASSERT: the parser reads the value that was written
        """
        target = _copy(tmp_path, SHIPPED_CONF)
        writer = ConfWriter(str(target))
        writer.set("CPU", "min_temp", "40.0")
        writer.set("HD", "enabled", "0")
        writer.save()
        assert Config(str(target)).cpu[0].min_temp == 40.0

    def test_a_parameter_that_is_absent_is_added_to_its_section(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.set(). It contains the following steps:
        - write a parameter the section does not hold yet
        - ASSERT: the parameter lands inside that section, not in the next one
        - ASSERT: the parser reads it back
        """
        target = _write(tmp_path, COMMENTED)
        writer = ConfWriter(str(target))
        writer.set("Ipmi", "fan_mode_delay", "5")
        writer.save()
        assert ConfWriter(str(target)).keys("Ipmi") == ["command", "fan_mode_delay"]
        assert Config(str(target)).ipmi.fan_mode_delay == 5

    def test_writing_to_an_absent_section_is_refused(self, tmp_path: Path) -> None:
        """Negative unit test for ConfWriter.set(). It contains the following steps:
        - write a parameter into a section the file does not hold
        - ASSERT: it raises KeyError instead of inventing a section
        """
        target = _write(tmp_path, COMMENTED)
        with pytest.raises(KeyError):
            ConfWriter(str(target)).set("PCI", "enabled", "1")

    def test_a_multi_line_value_is_read_and_replaced_as_a_whole(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.get() and set(). It contains the following steps:
        - read a file whose hd_names= value runs over three continuation lines
        - ASSERT: get() returns every line of the value
        - replace the value with a shorter one and save
        - ASSERT: no continuation line of the old value is left behind
        """
        body = ("[Ipmi]\n[HD]\nhd_names=/dev/a\n\t/dev/b\n\t/dev/c\n"
                "smartctl_path=/usr/sbin/smartctl\n")
        target = _write(tmp_path, body)
        writer = ConfWriter(str(target))
        assert writer.get("HD", "hd_names") == "/dev/a\n\t/dev/b\n\t/dev/c"
        writer.set_device_list("HD", "hd_names", ["/dev/x"])
        writer.save()
        after = target.read_text(encoding="utf-8")
        assert "/dev/b" not in after and "/dev/c" not in after
        assert "smartctl_path=/usr/sbin/smartctl" in after

    def test_a_device_list_is_written_in_the_form_the_parser_needs(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.set_device_list(). It contains the following steps:
        - write three devices into an empty hd_names= key
        - ASSERT: the first device sits on the key line, so the value has no empty first element
        - ASSERT: the parser returns exactly the three devices
        """
        target = _write(tmp_path, "[Ipmi]\n[HD]\nenabled=1\nhd_names=\n")
        writer = ConfWriter(str(target))
        devices = ["/dev/disk/by-id/ata-A", "/dev/disk/by-id/ata-B", "/dev/disk/by-id/ata-C"]
        writer.set_device_list("HD", "hd_names", devices)
        writer.save()
        assert target.read_text(encoding="utf-8").splitlines()[3].endswith("ata-A")
        assert Config(str(target)).hd[0].hd_names == devices

    def test_a_value_written_over_several_lines_can_be_read_back(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.set(). It contains the following steps:
        - write a device list, which carries continuation lines, into an empty key
        - read the parameter back from the same writer, without saving and loading again
        - ASSERT: the key is still found, and the value comes back
        - ASSERT: the section still lists the parameter
        A multi-line value has to enter the line list as one entry per line. Held as a single entry it
        still saves correctly, and every later lookup in the same session misses the key.
        """
        target = _write(tmp_path, "[Ipmi]\n[HD]\nenabled=1\nhd_names=\n")
        writer = ConfWriter(str(target))
        writer.set_device_list("HD", "hd_names", ["/dev/disk/by-id/ata-A", "/dev/disk/by-id/ata-B"])
        assert writer.keys("HD") == ["enabled", "hd_names"]
        assert writer.get("HD", "hd_names").startswith("/dev/disk/by-id/ata-A")
        writer.save()
        assert Config(str(target)).hd[0].hd_names == ["/dev/disk/by-id/ata-A",
                                                      "/dev/disk/by-id/ata-B"]

    def test_get_of_an_absent_parameter(self, tmp_path: Path) -> None:
        """Negative unit test for ConfWriter.get(). It contains the following steps:
        - ask for a parameter the section does not hold, and for one in an absent section
        - ASSERT: both return None instead of raising
        """
        target = _write(tmp_path, COMMENTED)
        writer = ConfWriter(str(target))
        assert writer.get("CPU", "max_temp") is None
        assert writer.get("PCI", "enabled") is None

    def test_adding_a_section_writes_only_the_parameters_given(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.add_section(). It contains the following steps:
        - add a [PCI] section with three parameters to a file that has no PCI section
        - ASSERT: the section holds exactly those three parameters
        - ASSERT: the parser fills every other parameter from its default
        """
        target = _copy(tmp_path, SHIPPED_CONF)
        writer = ConfWriter(str(target))
        writer.add_section("PCI:1", {"enabled": "1", "ipmi_zone": "3", "pci_id": "1d6a:07b1"})
        writer.set("HD", "enabled", "0")
        writer.save()
        assert ConfWriter(str(target)).keys("PCI:1") == ["enabled", "ipmi_zone", "pci_id"]
        instance = [c for c in Config(str(target)).pci if c.section == "PCI:1"][0]
        assert instance.enabled is True
        assert instance.steps == Config.DV_PCI_STEPS

    def test_adding_a_section_that_is_already_there_is_refused(self, tmp_path: Path) -> None:
        """Negative unit test for ConfWriter.add_section(). It contains the following steps:
        - add a section the file already holds
        - ASSERT: it raises KeyError instead of writing a second copy
        """
        target = _write(tmp_path, COMMENTED)
        with pytest.raises(KeyError):
            ConfWriter(str(target)).add_section("CPU")

    def test_removing_a_section_takes_its_comment_block_with_it(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.remove_section(). It contains the following steps:
        - remove the [CPU] section of a file that documents it with a comment above the header
        - ASSERT: the section and its parameters are gone
        - ASSERT: the comment that described it is gone too
        - ASSERT: the other section is untouched
        """
        target = _write(tmp_path, COMMENTED)
        writer = ConfWriter(str(target))
        writer.remove_section("CPU")
        writer.save()
        after = target.read_text(encoding="utf-8")
        assert "[CPU]" not in after
        assert "min_temp" not in after
        assert "# CPU fan controller." not in after
        assert "command=/usr/bin/ipmitool" in after

    def test_removing_an_absent_section_is_refused(self, tmp_path: Path) -> None:
        """Negative unit test for ConfWriter.remove_section(). It contains the following steps:
        - remove a section the file does not hold
        - ASSERT: it raises KeyError
        """
        target = _write(tmp_path, COMMENTED)
        with pytest.raises(KeyError):
            ConfWriter(str(target)).remove_section("PCI")

    def test_an_instance_is_added_and_removed_without_touching_the_base_section(self,
                                                                               tmp_path: Path) -> None:
        """Positive unit test for add_section() and remove_section(). It contains the following steps:
        - add a [CPU:1] instance beside [CPU], on a different IPMI zone
        - ASSERT: the parser reads two CPU instances
        - remove the instance again
        - ASSERT: only the base section is left, with its own value unchanged
        """
        target = _write(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\nipmi_zone=0\nmin_temp=30.0\n")
        writer = ConfWriter(str(target))
        writer.add_section("CPU:1", {"enabled": "1", "ipmi_zone": "1"})
        writer.save()
        assert [c.section for c in Config(str(target)).cpu] == ["CPU", "CPU:1"]
        writer = ConfWriter(str(target))
        writer.remove_section("CPU:1")
        writer.save()
        parsed = Config(str(target)).cpu
        assert [c.section for c in parsed] == ["CPU"]
        assert parsed[0].min_temp == 30.0

    def test_the_file_mode_is_kept(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.save(). It contains the following steps:
        - give a configuration file a mode of its own
        - save it through the writer
        - ASSERT: the mode is unchanged, because the file is replaced rather than created anew
        """
        target = _write(tmp_path, COMMENTED)
        os.chmod(target, 0o600)
        ConfWriter(str(target)).save()
        assert oct(os.stat(target).st_mode & 0o777) == "0o600"

    def test_no_temporary_file_is_left_behind(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.save(). It contains the following steps:
        - save a configuration file
        - ASSERT: the directory holds the configuration file and nothing else
        """
        target = _write(tmp_path, COMMENTED)
        ConfWriter(str(target)).save()
        assert [p.name for p in tmp_path.iterdir()] == [target.name]

    def test_saving_to_another_path_leaves_the_original(self, tmp_path: Path) -> None:
        """Positive unit test for ConfWriter.save(). It contains the following steps:
        - read one file, change a value, and save it under a different name
        - ASSERT: the new file carries the change
        - ASSERT: the file that was read is untouched
        """
        target = _write(tmp_path, COMMENTED)
        other = tmp_path / "other.conf"
        writer = ConfWriter(str(target))
        writer.set("CPU", "min_temp", "45.0")
        writer.save(str(other))
        assert "min_temp=45.0" in other.read_text(encoding="utf-8")
        assert "min_temp=30.0" in target.read_text(encoding="utf-8")

    def test_reading_a_file_that_does_not_exist(self, tmp_path: Path) -> None:
        """Negative unit test for ConfWriter. It contains the following steps:
        - open a configuration file that is not there
        - ASSERT: it raises FileNotFoundError, which the caller turns into the message of 12.2
        """
        with pytest.raises(FileNotFoundError):
            ConfWriter(str(tmp_path / "nosuch.conf"))

    def test_is_writable_reports_the_rights(self, tmp_path: Path) -> None:
        """Positive unit test for is_writable(). It contains the following steps:
        - test a writable file, a read-only file, and a file that does not exist yet
        - ASSERT: a writable file reports True
        - ASSERT: a file without write rights reports False, so the editor opens read-only
        - ASSERT: a missing file reports the rights of its directory, because it can be created
        """
        target = _write(tmp_path, COMMENTED)
        assert is_writable(str(target)) is True
        os.chmod(target, 0o400)
        assert is_writable(str(target)) is (os.geteuid() == 0)
        os.chmod(target, 0o644)
        assert is_writable(str(tmp_path / "new.conf")) is True


# End.
