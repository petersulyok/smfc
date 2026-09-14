#!/usr/bin/env python3
#
#   test_schema.py (C) 2026, Peter Sulyok
#   Unit test for smfc.config_editor.schema module.
#
import re
from pathlib import Path
from typing import Dict, List
import pytest
from smfc.config import Config
from smfc.config_editor.schema import (SECTIONS, CURVE_OVERRIDES, Field, FieldKind, Widget, family_of,
                                       field_of, section_of)


# Repository paths used by the tests.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
SHIPPED_CONF: Path = REPO_ROOT / "config" / "smfc.conf"

# Config attribute holding the parsed result of each section.
PARSED_ATTR: Dict[str, str] = {"Ipmi": "ipmi", "CPU": "cpu", "HD": "hd", "NVME": "nvme", "GPU": "gpu",
                               "NPU": "npu", "PCI": "pci", "CONST": "const", "Exporter": "exporter"}


def _keys_of_shipped_conf() -> Dict[str, List[str]]:
    """Collect the parameter names of every section of the shipped configuration file, in file order.
    A commented-out example (e.g. '#control_function=') counts as a key: it documents a supported
    parameter that simply has no default value.
    Returns:
        Dict[str, List[str]]: parameter names per section name
    """
    result: Dict[str, List[str]] = {}
    section: str = ""
    for line in SHIPPED_CONF.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        m = re.match(r"^\[([^\]]+)\]$", line)
        if m:
            section = m.group(1)
            result[section] = []
            continue
        m = re.match(r"^#?([a-z_]+)=", line)
        if m and section:
            result[section].append(m.group(1))
    return result


def _bare_config(tmp_path: Path) -> Config:
    """Parse a configuration file that holds every section header and not a single key.
    Every parsed value is then the fallback the parser applies, which is what the schema must state.
    Args:
        tmp_path (Path): pytest temporary directory
    Returns:
        Config: the parsed configuration
    """
    path = tmp_path / "bare.conf"
    path.write_text("[Ipmi]\n" + "".join(f"[{n}]\n" for n in SECTIONS if n != "Ipmi"), encoding="utf-8")
    return Config(str(path))


class TestSchema:
    """Unit test class for the smfc.config_editor.schema module."""

    def test_sections_cover_the_shipped_configuration_file(self) -> None:
        """Positive unit test for SECTIONS. It contains the following steps:
        - read the section names of config/smfc.conf
        - ASSERT: the schema defines every section the shipped file contains
        - ASSERT: the schema defines no section the shipped file does not contain
        """
        file_sections = list(_keys_of_shipped_conf())
        assert not set(file_sections) - set(SECTIONS)
        assert not set(SECTIONS) - set(file_sections)

    @pytest.mark.parametrize("name", list(SECTIONS))
    def test_fields_match_the_shipped_configuration_file(self, name: str) -> None:
        """Positive unit test for the fields of one section. It contains the following steps:
        - read the parameter names of that section from config/smfc.conf, in file order
        - ASSERT: the schema defines every parameter the shipped file documents
        - ASSERT: the schema defines no parameter the shipped file does not document
        - ASSERT: the schema lists the parameters in the same order as the shipped file
        """
        file_keys = _keys_of_shipped_conf()[name]
        schema_keys = [f.key for f in SECTIONS[name].fields]
        assert not set(file_keys) - set(schema_keys)
        assert not set(schema_keys) - set(file_keys)
        assert schema_keys == file_keys

    @pytest.mark.parametrize("name", list(SECTIONS))
    def test_defaults_match_the_parser(self, name: str, tmp_path: Path) -> None:
        """Positive unit test for the default values of one section. It contains the following steps:
        - parse a configuration file that holds every section header and no key at all
        - read back the value the parser applied for each parameter of this section
        - ASSERT: every default of the schema equals the fallback the parser applies
        """
        parsed = getattr(_bare_config(tmp_path), PARSED_ATTR[name])
        parsed = parsed[0] if isinstance(parsed, list) else parsed
        for f in SECTIONS[name].fields:
            assert getattr(parsed, f.key) == f.default, f"[{name}] {f.key}"

    @pytest.mark.parametrize("name", list(SECTIONS))
    def test_every_field_carries_help_text(self, name: str) -> None:
        """Positive unit test for the help text of one section. It contains the following steps:
        - walk every field of the section
        - ASSERT: the section itself carries a summary and a detail
        - ASSERT: every field carries a summary and a detail
        - ASSERT: no summary ends with a full stop, because it is a label rather than a sentence
        """
        section = SECTIONS[name]
        assert section.summary and section.detail
        for f in section.fields:
            assert f.summary, f"[{name}] {f.key} has no summary"
            assert f.detail, f"[{name}] {f.key} has no detail"
            assert not f.summary.endswith("."), f"[{name}] {f.key}"

    def test_ipmi_section_is_mandatory_and_has_no_enabled_key(self) -> None:
        """Positive unit test for the [Ipmi] section. It contains the following steps:
        - look up the [Ipmi] section in the schema
        - ASSERT: it is marked mandatory, because the parser rejects a file without it
        - ASSERT: it is not toggleable and defines no enabled= key
        - ASSERT: it is not repeatable, because numbered instances make no sense for it
        """
        section = SECTIONS[Config.CS_IPMI]
        assert section.mandatory is True
        assert section.toggleable is False
        assert section.field(Config.CV_ENABLED) is None
        assert section.repeatable is False

    @pytest.mark.parametrize(
        "name, repeatable",
        [
            pytest.param("Ipmi", False, id="ipmi"),
            pytest.param("CPU", True, id="cpu"),
            pytest.param("HD", True, id="hd"),
            pytest.param("NVME", True, id="nvme"),
            pytest.param("GPU", True, id="gpu"),
            pytest.param("NPU", True, id="npu"),
            pytest.param("PCI", True, id="pci"),
            pytest.param("CONST", True, id="const"),
            pytest.param("Exporter", False, id="exporter"),
        ],
    )
    def test_repeatable_sections(self, name: str, repeatable: bool) -> None:
        """Positive unit test for the repeatable flag. It contains the following steps:
        - look up the section in the schema
        - ASSERT: only a fan controller family accepts numbered instances
        """
        assert SECTIONS[name].repeatable is repeatable

    @pytest.mark.parametrize(
        "section_name, key, widget",
        [
            pytest.param("CPU", "min_temp", Widget.INLINE, id="float-inline"),
            pytest.param("CPU", "steps", Widget.INLINE, id="int-inline"),
            pytest.param("CPU", "enabled", Widget.INLINE, id="bool-inline"),
            pytest.param("CPU", "temp_calc", Widget.SELECT, id="enum-select"),
            pytest.param("CPU", "control_function", Widget.POPUP, id="curve-popup"),
            pytest.param("Ipmi", "command", Widget.POPUP, id="path-popup"),
            pytest.param("Ipmi", "remote_parameters", Widget.POPUP, id="str-popup"),
            pytest.param("PCI", "pci_address", Widget.POPUP, id="str-list-popup"),
            pytest.param("HD", "hd_names", Widget.DEVICES, id="device-list-popup"),
            pytest.param("GPU", "gpu_device_ids", Widget.DEVICES, id="int-list-popup"),
            pytest.param("CPU", "ipmi_zone", Widget.INLINE, id="int-list-without-provider"),
        ],
    )
    def test_widget_follows_the_value_kind(self, section_name: str, key: str, widget: Widget) -> None:
        """Positive unit test for Field.widget. It contains the following steps:
        - look up one field of one section
        - ASSERT: a number, a flag and a zone list are typed in place
        - ASSERT: a path, free text, an address list and a curve open a popup
        - ASSERT: a list with a provider opens the device popup
        """
        f = field_of(section_name, key)
        assert f is not None
        assert f.widget is widget

    def test_curve_overrides_are_marked(self) -> None:
        """Positive unit test for Field.overridden_by_curve. It contains the following steps:
        - walk every field of every section
        - ASSERT: exactly the four keys a control_function= value overrides are marked
        - ASSERT: those four keys are min_temp, max_temp, min_level and max_level
        """
        assert CURVE_OVERRIDES == ("min_temp", "max_temp", "min_level", "max_level")
        for name, section in SECTIONS.items():
            for f in section.fields:
                assert f.overridden_by_curve is (f.key in CURVE_OVERRIDES), f"[{name}] {f.key}"

    @pytest.mark.parametrize(
        "section_name, expected",
        [
            pytest.param("CPU", "CPU", id="base"),
            pytest.param("CPU:0", "CPU", id="instance-zero"),
            pytest.param("CPU:1", "CPU", id="instance-one"),
            pytest.param("HD:12", "HD", id="instance-twelve"),
        ],
    )
    def test_family_of_strips_the_instance_number(self, section_name: str, expected: str) -> None:
        """Positive unit test for family_of(). It contains the following steps:
        - call family_of() with a base name and with numbered instance names
        - ASSERT: the instance number is removed and the family name is returned
        """
        assert family_of(section_name) == expected

    def test_lookup_of_an_instance_finds_the_family_metadata(self) -> None:
        """Positive unit test for section_of() and field_of(). It contains the following steps:
        - look up a numbered instance name
        - ASSERT: section_of() returns the metadata of its family
        - ASSERT: field_of() finds a field of that family through the instance name
        """
        assert section_of("CPU:1") is SECTIONS["CPU"]
        f = field_of("CPU:1", Config.CV_MIN_TEMP)
        assert f is not None and f.key == Config.CV_MIN_TEMP

    @pytest.mark.parametrize(
        "section_name, key",
        [
            pytest.param("NOSUCH", "min_temp", id="unknown-section"),
            pytest.param("CPU", "nosuchkey", id="unknown-key"),
            pytest.param("CPU", "hd_names", id="key-of-another-family"),
        ],
    )
    def test_lookup_of_an_unknown_name_returns_none(self, section_name: str, key: str) -> None:
        """Negative unit test for section_of() and field_of(). It contains the following steps:
        - look up a section name or a key the schema does not define
        - ASSERT: the lookup returns None instead of raising
        """
        assert field_of(section_name, key) is None

    def test_section_of_an_unknown_name_returns_none(self) -> None:
        """Negative unit test for section_of(). It contains the following steps:
        - look up a section name the schema does not define
        - ASSERT: the lookup returns None instead of raising
        """
        assert section_of("NOSUCH") is None

    @pytest.mark.parametrize(
        "section_name, key, expected",
        [
            pytest.param("CPU", "min_temp", "float, Celsius, default 30.0, 0.0 to 200.0",
                         id="range-both-ends"),
            pytest.param("CPU", "steps", "int, default 6, 1 or more", id="range-lower-end"),
            pytest.param("CPU", "temp_calc", "enum, default 1, one of 0, 1, 2", id="choices"),
            pytest.param("Ipmi", "remote_parameters", "str, default empty", id="empty-default"),
            pytest.param("Exporter", "port", "int, default 9099, 1 to 65535", id="port-range"),
        ],
    )
    def test_range_text_renders_the_help_line(self, section_name: str, key: str, expected: str) -> None:
        """Positive unit test for Field.range_text(). It contains the following steps:
        - render the type, unit, default and range of one field
        - ASSERT: a bounded value states both ends
        - ASSERT: a value bounded on one side states that side only
        - ASSERT: a field with choices lists them instead of a range
        - ASSERT: an empty default reads 'default empty' rather than 'default '
        """
        f = field_of(section_name, key)
        assert f is not None
        assert f.range_text() == expected

    def test_a_unit_is_written_in_full(self) -> None:
        """Positive unit test for the unit of every field. It contains the following steps:
        - walk every field of every section that names a unit
        - ASSERT: the unit is a word, not a symbol or an abbreviation
        A reader who is not a programmer should not have to know that C means Celsius or s seconds.
        """
        allowed = {"Celsius", "seconds", "percent"}
        for name, section in SECTIONS.items():
            for f in section.fields:
                if f.unit:
                    assert f.unit in allowed, f"[{name}] {f.key} uses {f.unit!r}"

    def test_enum_fields_label_every_choice(self) -> None:
        """Positive unit test for the choices of an enum field. It contains the following steps:
        - walk every field of every section
        - ASSERT: an enum field lists at least two choices
        - ASSERT: an enum field labels every one of its choices
        - ASSERT: the default of an enum field is one of its choices
        """
        for name, section in SECTIONS.items():
            for f in section.fields:
                if f.kind is not FieldKind.ENUM:
                    continue
                assert len(f.choices) >= 2, f"[{name}] {f.key}"
                assert len(f.labels) == len(f.choices), f"[{name}] {f.key}"
                assert f.default in f.choices, f"[{name}] {f.key}"

    def test_field_keys_are_unique_within_a_section(self) -> None:
        """Positive unit test for the field list of every section. It contains the following steps:
        - collect the parameter names of each section
        - ASSERT: no section defines the same parameter twice
        """
        for name, section in SECTIONS.items():
            keys = [f.key for f in section.fields]
            assert len(keys) == len(set(keys)), f"[{name}] has a duplicated key"

    def test_a_provider_is_named_only_for_a_list_field(self) -> None:
        """Positive unit test for Field.provider. It contains the following steps:
        - walk every field of every section
        - ASSERT: only a device list or an ID list names a provider function
        """
        for name, section in SECTIONS.items():
            for f in section.fields:
                if f.provider:
                    assert f.kind in (FieldKind.DEVICE_LIST, FieldKind.INT_LIST), f"[{name}] {f.key}"

    def test_field_is_immutable(self) -> None:
        """Negative unit test for Field. It contains the following steps:
        - look up one field of the schema
        - ASSERT: assigning to it raises, because the schema is shared constant metadata
        """
        f = field_of("CPU", Config.CV_MIN_TEMP)
        assert isinstance(f, Field)
        with pytest.raises(Exception):
            f.default = 1.0     # type: ignore[misc]


# End.
