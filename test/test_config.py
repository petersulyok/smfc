#!/usr/bin/env python3
#
#   test_config.py (C) 2026, Peter Sulyok
#   Unit tests for smfc.Config class.
#
# pylint: disable=redefined-outer-name,unused-argument
from configparser import MissingSectionHeaderError, DuplicateSectionError
from typing import List, Callable
import pytest
from smfc.config import Config


@pytest.fixture
def create_config(tmp_path) -> Callable[[str], Config]:
    """Fixture that returns a helper function to create Config from string content."""
    def _create_config(content: str) -> Config:
        config_file = tmp_path / "test.conf"
        config_file.write_text(content)
        return Config(str(config_file))
    return _create_config


@pytest.fixture
def create_config_file(tmp_path) -> Callable[[str], str]:
    """Fixture that returns a helper function to create a config file and return its path."""
    def _create_config_file(content: str) -> str:
        config_file = tmp_path / "test.conf"
        config_file.write_text(content)
        return str(config_file)
    return _create_config_file


class TestConfigStaticMethods:
    """Unit tests for Config static helper methods."""

    @pytest.mark.parametrize(
        "input_str, expected",
        [
            pytest.param("0", [0], id="single-zone-0"),
            pytest.param("1", [1], id="single-zone-1"),
            pytest.param("0, 1", [0, 1], id="comma-with-space"),
            pytest.param("0,1,2", [0, 1, 2], id="comma-no-space"),
            pytest.param("0 1", [0, 1], id="space-separated"),
            pytest.param("0 1 2", [0, 1, 2], id="space-separated-multi"),
            pytest.param("  0  1  2  ", [0, 1, 2], id="extra-whitespace"),
            pytest.param("  0,  1,  2  ", [0, 1, 2], id="comma-extra-whitespace"),
            pytest.param("100", [100], id="max-valid-zone"),
            pytest.param("0, 1, 0", [0, 1, 0], id="duplicates-preserved"),
        ],
    )
    def test_parse_ipmi_zones_valid(self, input_str: str, expected: List[int]):
        """Positive unit test for Config.parse_ipmi_zones() method. It contains the following steps:
        - no external mocks
        - call Config.parse_ipmi_zones() with a valid zone string (single, comma, space, whitespace variants)
        - ASSERT: parse_ipmi_zones returns the expected list of zone integers
        """
        assert Config.parse_ipmi_zones(input_str) == expected

    @pytest.mark.parametrize(
        "input_str",
        [
            pytest.param("-1", id="negative"),
            pytest.param("101", id="over-100"),
            pytest.param("abc", id="non-numeric"),
            pytest.param("0, abc", id="mixed-valid-invalid"),
            pytest.param("", id="empty-string"),
        ],
    )
    def test_parse_ipmi_zones_invalid(self, input_str: str):
        """Negative unit test for Config.parse_ipmi_zones() method. It contains the following steps:
        - no external mocks
        - call Config.parse_ipmi_zones() with an out-of-range, non-numeric, mixed, or empty string
        - ASSERT: parse_ipmi_zones raises ValueError or IndexError for invalid input
        """
        with pytest.raises((ValueError, IndexError)):
            Config.parse_ipmi_zones(input_str)

    @pytest.mark.parametrize(
        "input_str, expected",
        [
            pytest.param("/dev/sda", ["/dev/sda"], id="single-device"),
            pytest.param("/dev/sda /dev/sdb", ["/dev/sda", "/dev/sdb"], id="space-separated"),
            pytest.param("/dev/sda\n/dev/sdb", ["/dev/sda", "/dev/sdb"], id="newline-separated"),
            pytest.param("/dev/sda\n/dev/sdb\n/dev/sdc", ["/dev/sda", "/dev/sdb", "/dev/sdc"],
                         id="newline-separated-multi"),
            pytest.param("/dev/disk/by-id/wwn-0x5000 /dev/disk/by-id/wwn-0x5001",
                         ["/dev/disk/by-id/wwn-0x5000", "/dev/disk/by-id/wwn-0x5001"], id="by-id-paths"),
        ],
    )
    def test_parse_device_names_valid(self, input_str: str, expected: List[str]):
        """Positive unit test for Config.parse_device_names() method. It contains the following steps:
        - no external mocks
        - call Config.parse_device_names() with a device-name string (single, space, newline, by-id paths)
        - ASSERT: parse_device_names returns the expected list of device-path strings
        """
        assert Config.parse_device_names(input_str) == expected

    @pytest.mark.parametrize(
        "input_str, expected",
        [
            pytest.param("0", [0], id="single-id"),
            pytest.param("0, 1", [0, 1], id="comma-with-space"),
            pytest.param("0,1,2,3", [0, 1, 2, 3], id="comma-no-space"),
            pytest.param("0 1 2", [0, 1, 2], id="space-separated"),
            pytest.param("  0  1  2  ", [0, 1, 2], id="extra-whitespace"),
        ],
    )
    def test_parse_gpu_ids_valid(self, input_str: str, expected: List[int]):
        """Positive unit test for Config.parse_gpu_ids() method. It contains the following steps:
        - no external mocks
        - call Config.parse_gpu_ids() with a valid id string (single, comma, space, whitespace variants)
        - ASSERT: parse_gpu_ids returns the expected list of GPU id integers
        """
        assert Config.parse_gpu_ids(input_str) == expected

    @pytest.mark.parametrize(
        "input_str",
        [
            pytest.param("-1", id="negative"),
            pytest.param("101", id="over-100"),
            pytest.param("abc", id="non-numeric"),
        ],
    )
    def test_parse_gpu_ids_invalid(self, input_str: str):
        """Negative unit test for Config.parse_gpu_ids() method. It contains the following steps:
        - no external mocks
        - call Config.parse_gpu_ids() with a negative, out-of-range, or non-numeric value
        - ASSERT: parse_gpu_ids raises ValueError for invalid input
        """
        with pytest.raises(ValueError):
            Config.parse_gpu_ids(input_str)

    @pytest.mark.parametrize(
        "input_str, expected",
        [
            pytest.param("30-35, 65-100", [(30, 35), (65, 100)], id="2-point-comma"),
            pytest.param("30-35, 50-40, 60-90, 65-100", [(30, 35), (50, 40), (60, 90), (65, 100)],
                         id="4-point-comma"),
            pytest.param("30-35 65-100", [(30, 35), (65, 100)], id="space-separator"),
            pytest.param("0-0, 100-100", [(0, 0), (100, 100)], id="endpoints-0-and-100"),
            pytest.param("  30-35 ,   65-100  ", [(30, 35), (65, 100)], id="extra-whitespace"),
        ],
    )
    def test_parse_control_function_valid(self, input_str: str, expected):
        """Positive unit test for Config.parse_control_function() method. It contains the following steps:
        - no external mocks
        - call Config.parse_control_function() with a valid temp-level pair list (2/4 points, varied separators)
        - ASSERT: parse_control_function returns the expected list of (temp, level) tuples
        """
        assert Config.parse_control_function(input_str) == expected

    @pytest.mark.parametrize(
        "input_str",
        [
            pytest.param("30-35", id="single-pair"),
            pytest.param("", id="empty-string"),
            pytest.param("30:35, 65:100", id="wrong-separator"),
            pytest.param("30-35-extra, 65-100", id="too-many-hyphens"),
            pytest.param("30.5-35, 65-100", id="non-integer-temp"),
            pytest.param("30-35, 65-abc", id="non-integer-level"),
            pytest.param("-1-35, 65-100", id="temp-negative"),
            pytest.param("30-35, 101-100", id="temp-over-100"),
            pytest.param("30-35, 65-150", id="level-over-100"),
            pytest.param("30--5, 65-100", id="level-negative"),
            pytest.param("60-35, 30-100", id="non-ascending-temps"),
            pytest.param("30-35, 30-100", id="duplicate-temps"),
        ],
    )
    def test_parse_control_function_invalid(self, input_str: str):
        """Negative unit test for Config.parse_control_function() method. It contains the following steps:
        - no external mocks
        - call Config.parse_control_function() with a malformed pair list (single pair, wrong separator,
          non-integer, out-of-range, non-ascending or duplicate temps)
        - ASSERT: parse_control_function raises ValueError for invalid input
        """
        with pytest.raises(ValueError):
            Config.parse_control_function(input_str)


class TestControlFunctionSectionWiring:
    """Section-level tests for control_function parsing (legacy-key precedence, cross-field, defaults)."""

    @pytest.mark.parametrize(
        "section",
        [
            pytest.param("CPU", id="cpu"),
            pytest.param("HD", id="hd"),
            pytest.param("NVME", id="nvme"),
            pytest.param("GPU", id="gpu"),
        ],
    )
    def test_section_without_control_function_defaults_to_empty(self, create_config, section: str):
        """Positive unit test for control_function wiring inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - build a minimal [Ipmi] + section body with no control_function key and instantiate Config
        - inspect the parsed section's control_function attribute
        - ASSERT: control_function is an empty list when the key is absent (legacy mode)
        """
        body = "[Ipmi]\n[" + section + "]\nenabled = 0\n"
        cfg = create_config(body)
        sec_list = {"CPU": cfg.cpu, "HD": cfg.hd, "NVME": cfg.nvme, "GPU": cfg.gpu}[section]
        assert sec_list[0].control_function == []

    @pytest.mark.parametrize(
        "section",
        [
            pytest.param("CPU", id="cpu"),
            pytest.param("HD", id="hd"),
            pytest.param("NVME", id="nvme"),
            pytest.param("GPU", id="gpu"),
        ],
    )
    def test_section_with_control_function_parsed(self, create_config, section: str):
        """Positive unit test for control_function wiring inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - build a section body with control_function = 30-35, 50-40, 60-90, 65-100 and instantiate Config
        - inspect the parsed section's control_function attribute
        - ASSERT: control_function holds the expected (temp, level) tuple list
        """
        body = ("[Ipmi]\n[" + section + "]\nenabled = 0\nsteps = 4\n"
                "control_function = 30-35, 50-40, 60-90, 65-100\n")
        cfg = create_config(body)
        sec_list = {"CPU": cfg.cpu, "HD": cfg.hd, "NVME": cfg.nvme, "GPU": cfg.gpu}[section]
        expected = [(30, 35), (50, 40), (60, 90), (65, 100)]
        assert sec_list[0].control_function == expected

    @pytest.mark.parametrize(
        "section, legacy_key, legacy_val",
        [
            pytest.param("CPU", "min_temp", "30", id="cpu-min-temp"),
            pytest.param("CPU", "max_temp", "60", id="cpu-max-temp"),
            pytest.param("CPU", "min_level", "35", id="cpu-min-level"),
            pytest.param("CPU", "max_level", "100", id="cpu-max-level"),
            pytest.param("HD", "min_temp", "32", id="hd-min-temp"),
            pytest.param("NVME", "max_level", "100", id="nvme-max-level"),
            pytest.param("GPU", "min_level", "35", id="gpu-min-level"),
        ],
    )
    def test_legacy_keys_ignored_when_control_function_defined(self, create_config, section: str, legacy_key: str,
                                                               legacy_val: str):
        """Positive unit test for control_function wiring inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - build a section body with both control_function and a legacy min/max key set, then instantiate Config
        - inspect the parsed section's control_function attribute
        - ASSERT: control_function reflects the parsed pairs (legacy key is ignored, not rejected)
        """
        body = ("[Ipmi]\n[" + section + "]\nenabled = 0\nsteps = 4\n"
                "control_function = 30-35, 65-100\n"
                f"{legacy_key} = {legacy_val}\n")
        cfg = create_config(body)
        sec_list = {"CPU": cfg.cpu, "HD": cfg.hd, "NVME": cfg.nvme, "GPU": cfg.gpu}[section]
        assert sec_list[0].control_function == [(30, 35), (65, 100)], \
            f"control_function parsed despite legacy {legacy_key} present"

    def test_cross_field_interior_too_small_for_steps(self, create_config_file):
        """Negative unit test for control_function wiring inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write a CPU section with steps=35 and control_function = 30-35, 65-100 (interior width 34 < steps)
        - call Config(path) and capture the ValueError
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "interior width"
        """
        # (65-30-1) = 34, steps=35 -> too few interior degrees
        body = ("[Ipmi]\n[CPU]\nenabled = 0\nsteps = 35\n"
                "control_function = 30-35, 65-100\n")
        path = create_config_file(body)
        with pytest.raises(ValueError) as exc_info:
            Config(path)
        assert "interior width" in str(exc_info.value), \
            f"expected interior-width error, got: {exc_info.value}"

    def test_cv_control_function_constant(self):
        """Positive unit test for the Config.CV_CONTROL_FUNCTION class constant. It contains the following steps:
        - no external mocks
        - read the class-level constant Config.CV_CONTROL_FUNCTION
        - ASSERT: Config.CV_CONTROL_FUNCTION == "control_function"
        """
        assert Config.CV_CONTROL_FUNCTION == "control_function"


class TestConfigFileLoading:
    """Unit tests for Config file loading."""

    def test_config_file_not_found(self):
        """Negative unit test for Config.__init__() file-loading path. It contains the following steps:
        - no external mocks
        - call Config("/nonexistent/path/to/config.conf") on a path that does not exist
        - ASSERT: Config(path) raises FileNotFoundError
        """
        with pytest.raises(FileNotFoundError):
            Config("/nonexistent/path/to/config.conf")

    def test_config_load_minimal(self, create_config):
        """Positive unit test for Config.__init__() file-loading path. It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write a minimal [Ipmi] body with a custom command key and instantiate Config
        - inspect the parsed ipmi attributes and the empty controller lists
        - ASSERT: ipmi.command equals the DV_IPMI_COMMAND default (the written command matches the default)
        - ASSERT: ipmi.fan_mode_delay equals DV_IPMI_FAN_MODE_DELAY
        - ASSERT: ipmi.fan_level_delay equals DV_IPMI_FAN_LEVEL_DELAY
        - ASSERT: cpu, hd, nvme, gpu, const lists are all empty
        """
        cfg = create_config("[Ipmi]\ncommand = /usr/bin/ipmitool\n")
        assert cfg.ipmi.command == Config.DV_IPMI_COMMAND
        assert cfg.ipmi.fan_mode_delay == Config.DV_IPMI_FAN_MODE_DELAY
        assert cfg.ipmi.fan_level_delay == Config.DV_IPMI_FAN_LEVEL_DELAY
        assert cfg.cpu == []
        assert cfg.hd == []
        assert cfg.nvme == []
        assert cfg.gpu == []
        assert cfg.const == []

    def test_config_missing_ipmi_section(self, create_config_file):
        """Negative unit test for Config.__init__() file-loading path. It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write a config body that lacks the mandatory [Ipmi] section and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "Missing mandatory [Ipmi] section"
        """
        config_path = create_config_file("[CPU]\nenabled = 1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "Missing mandatory [Ipmi] section" in str(exc_info.value)

    def test_config_invalid_ini_format(self, create_config_file):
        """Negative unit test for Config.__init__() file-loading path. It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write a malformed INI body without any section headers and call Config(path)
        - ASSERT: Config(path) raises MissingSectionHeaderError
        """
        config_path = create_config_file("This is not a valid INI file\nNo sections here\n")
        with pytest.raises(MissingSectionHeaderError):
            Config(config_path)

    def test_config_invalid_ini_duplicate_section(self, create_config_file):
        """Negative unit test for Config.__init__() file-loading path. It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write a config body with two [Ipmi] section headers and call Config(path)
        - ASSERT: Config(path) raises DuplicateSectionError (configparser strict mode)
        """
        cfg_path = create_config_file("[Ipmi]\ncommand = /first\n[Ipmi]\ncommand = /second\n")
        with pytest.raises(DuplicateSectionError):
            Config(cfg_path)

    def test_config_invalid_data_type_int(self, create_config_file):
        """Negative unit test for Config.__init__() file-loading path. It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [Ipmi] with fan_mode_delay = abc (non-integer) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        config_path = create_config_file("[Ipmi]\nfan_mode_delay = abc\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_config_invalid_data_type_float(self, create_config_file):
        """Negative unit test for Config.__init__() file-loading path. It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [CPU] with polling = not_a_float (non-float) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        config_path = create_config_file("[Ipmi]\n[CPU]\nenabled = 1\npolling = not_a_float\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_config_invalid_data_type_boolean(self, create_config_file):
        """Negative unit test for Config.__init__() file-loading path. It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [CPU] with enabled = maybe (invalid boolean) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        config_path = create_config_file("[Ipmi]\n[CPU]\nenabled = maybe\n")
        with pytest.raises(ValueError):
            Config(config_path)


class TestIpmiConfigParsing:
    """Unit tests for [Ipmi] section parsing."""

    def test_ipmi_defaults(self, create_config):
        """Positive unit test for the [Ipmi] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write a body with only "[Ipmi]" header and instantiate Config
        - inspect every IpmiConfig attribute
        - ASSERT: ipmi.command equals Config.DV_IPMI_COMMAND
        - ASSERT: ipmi.fan_mode_delay equals Config.DV_IPMI_FAN_MODE_DELAY
        - ASSERT: ipmi.fan_level_delay equals Config.DV_IPMI_FAN_LEVEL_DELAY
        - ASSERT: ipmi.remote_parameters equals Config.DV_IPMI_REMOTE_PARAMETERS
        - ASSERT: ipmi.platform_name equals Config.DV_IPMI_PLATFORM_NAME
        - ASSERT: ipmi.enforce_fan_mode equals Config.DV_IPMI_ENFORCE_FAN_MODE
        """
        cfg = create_config("[Ipmi]\n")
        assert cfg.ipmi.command == Config.DV_IPMI_COMMAND
        assert cfg.ipmi.fan_mode_delay == Config.DV_IPMI_FAN_MODE_DELAY
        assert cfg.ipmi.fan_level_delay == Config.DV_IPMI_FAN_LEVEL_DELAY
        assert cfg.ipmi.remote_parameters == Config.DV_IPMI_REMOTE_PARAMETERS
        assert cfg.ipmi.platform_name == Config.DV_IPMI_PLATFORM_NAME
        assert cfg.ipmi.enforce_fan_mode == Config.DV_IPMI_ENFORCE_FAN_MODE

    def test_ipmi_custom_values(self, create_config):
        """Positive unit test for the [Ipmi] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [Ipmi] with all six keys populated and instantiate Config
        - inspect every IpmiConfig attribute
        - ASSERT: ipmi.command equals "/opt/ipmitool"
        - ASSERT: ipmi.fan_mode_delay equals 5
        - ASSERT: ipmi.fan_level_delay equals 1
        - ASSERT: ipmi.remote_parameters equals the written string
        - ASSERT: ipmi.platform_name equals "X10QBi"
        - ASSERT: ipmi.enforce_fan_mode is False
        """
        cfg = create_config("""
[Ipmi]
command = /opt/ipmitool
fan_mode_delay = 5
fan_level_delay = 1
remote_parameters = -I lanplus -U admin -P secret -H 192.168.1.100
platform_name = X10QBi
enforce_fan_mode = false
""")
        assert cfg.ipmi.command == "/opt/ipmitool"
        assert cfg.ipmi.fan_mode_delay == 5
        assert cfg.ipmi.fan_level_delay == 1
        assert cfg.ipmi.remote_parameters == "-I lanplus -U admin -P secret -H 192.168.1.100"
        assert cfg.ipmi.platform_name == "X10QBi"
        assert cfg.ipmi.enforce_fan_mode is False

    @pytest.mark.parametrize(
        "value, expected",
        [
            # Legacy value is normalized to the canonical one
            pytest.param("genericx9", "generic_x9", id="legacy-genericx9-normalized"),
            # All documented values are accepted and passed through unchanged
            pytest.param("auto", "auto", id="auto"),
            pytest.param("generic", "generic", id="generic"),
            pytest.param("generic_x9", "generic_x9", id="generic-x9"),
            pytest.param("generic_x14", "generic_x14", id="generic-x14"),
            pytest.param("X10QBi", "X10QBi", id="x10qbi"),
        ],
    )
    def test_ipmi_platform_name_valid(self, create_config, value: str, expected: str):
        """Positive unit test for the [Ipmi] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [Ipmi] with platform_name set to a documented value and instantiate Config
        - inspect ipmi.platform_name
        - ASSERT: ipmi.platform_name equals the expected normalized value (legacy "genericx9" -> "generic_x9")
        """
        cfg = create_config(f"[Ipmi]\nplatform_name = {value}\n")
        assert cfg.ipmi.platform_name == expected

    @pytest.mark.parametrize(
        "value",
        [
            # A raw BMC product name is not a valid config value (auto-detection happens in 'auto' mode)
            pytest.param("X11DPH-T", id="bmc-product-name"),
            # A typo in a documented value
            pytest.param("genericx14", id="typo-genericx14"),
            # An empty value
            pytest.param("", id="empty"),
        ],
    )
    def test_ipmi_platform_name_invalid(self, create_config, value: str):
        """Negative unit test for the [Ipmi] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [Ipmi] with platform_name set to an unknown / typo / empty value and call create_config
        - ASSERT: Config raises ValueError
        - ASSERT: the captured exception type is exactly ValueError
        """
        with pytest.raises(ValueError) as cm:
            create_config(f"[Ipmi]\nplatform_name = {value}\n")
        assert cm.type is ValueError

    @pytest.mark.parametrize(
        "value, expected",
        [
            pytest.param("true", True, id="true-lower"),
            pytest.param("True", True, id="true-cap"),
            pytest.param("false", False, id="false-lower"),
            pytest.param("False", False, id="false-cap"),
            pytest.param("yes", True, id="yes"),
            pytest.param("no", False, id="no"),
        ],
    )
    def test_ipmi_enforce_fan_mode_parsing(self, create_config, value: str, expected: bool):
        """Positive unit test for the [Ipmi] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [Ipmi] with enforce_fan_mode = <boolean spelling> and instantiate Config
        - inspect ipmi.enforce_fan_mode
        - ASSERT: ipmi.enforce_fan_mode equals the expected bool for each spelling
        """
        cfg = create_config(f"[Ipmi]\nenforce_fan_mode = {value}\n")
        assert cfg.ipmi.enforce_fan_mode is expected

    @pytest.mark.parametrize(
        "param, value",
        [
            pytest.param("fan_mode_delay", "-1", id="negative-mode-delay"),
            pytest.param("fan_level_delay", "-5", id="negative-level-delay"),
        ],
    )
    def test_ipmi_invalid_values(self, create_config_file, param: str, value: str):
        """Negative unit test for the [Ipmi] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [Ipmi] with a negative fan_mode_delay or fan_level_delay and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        config_path = create_config_file(f"[Ipmi]\n{param} = {value}\n")
        with pytest.raises(ValueError):
            Config(config_path)


class TestExporterConfigParsing:
    """Unit tests for [Exporter] section parsing."""

    def test_exporter_section_absent_uses_defaults(self, create_config):
        """Positive unit test for the [Exporter] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write only "[Ipmi]" (no [Exporter] section) and instantiate Config
        - inspect every ExporterConfig attribute
        - ASSERT: exporter.enabled equals Config.DV_EXPORTER_ENABLED
        - ASSERT: exporter.bind_address equals Config.DV_EXPORTER_BIND_ADDRESS
        - ASSERT: exporter.port equals Config.DV_EXPORTER_PORT
        """
        cfg = create_config("[Ipmi]\n")
        assert cfg.exporter.enabled is Config.DV_EXPORTER_ENABLED
        assert cfg.exporter.bind_address == Config.DV_EXPORTER_BIND_ADDRESS
        assert cfg.exporter.port == Config.DV_EXPORTER_PORT

    def test_exporter_custom_values(self, create_config):
        """Positive unit test for the [Exporter] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [Exporter] with enabled=true, bind_address=0.0.0.0, port=8080 and instantiate Config
        - inspect every ExporterConfig attribute
        - ASSERT: exporter.enabled is True
        - ASSERT: exporter.bind_address equals "0.0.0.0"
        - ASSERT: exporter.port equals 8080
        """
        cfg = create_config("""
[Ipmi]
[Exporter]
enabled = true
bind_address = 0.0.0.0
port = 8080
""")
        assert cfg.exporter.enabled is True
        assert cfg.exporter.bind_address == "0.0.0.0"
        assert cfg.exporter.port == 8080

    def test_exporter_section_present_keys_absent(self, create_config):
        """Positive unit test for the [Exporter] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write "[Ipmi]\\n[Exporter]\\n" (empty Exporter section) and instantiate Config
        - inspect every ExporterConfig attribute
        - ASSERT: exporter.enabled equals Config.DV_EXPORTER_ENABLED
        - ASSERT: exporter.bind_address equals Config.DV_EXPORTER_BIND_ADDRESS
        - ASSERT: exporter.port equals Config.DV_EXPORTER_PORT
        """
        cfg = create_config("[Ipmi]\n[Exporter]\n")
        assert cfg.exporter.enabled is Config.DV_EXPORTER_ENABLED
        assert cfg.exporter.bind_address == Config.DV_EXPORTER_BIND_ADDRESS
        assert cfg.exporter.port == Config.DV_EXPORTER_PORT

    @pytest.mark.parametrize(
        "port",
        [
            pytest.param("0", id="zero"),
            pytest.param("-1", id="negative"),
            pytest.param("65536", id="just-over-max"),
            pytest.param("100000", id="far-over-max"),
        ],
    )
    def test_exporter_invalid_port_rejected(self, create_config_file, port: str):
        """Negative unit test for the [Exporter] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [Exporter] with an out-of-range port (0, -1, 65536, 100000) and call Config(path)
        - ASSERT: Config(path) raises ValueError whose message matches "port"
        """
        config_path = create_config_file(f"[Ipmi]\n[Exporter]\nport = {port}\n")
        with pytest.raises(ValueError, match="port"):
            Config(config_path)

    def test_exporter_empty_bind_address_rejected(self, create_config_file):
        """Negative unit test for the [Exporter] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [Exporter] with bind_address set to whitespace only and call Config(path)
        - ASSERT: Config(path) raises ValueError whose message matches "bind_address"
        """
        config_path = create_config_file("[Ipmi]\n[Exporter]\nbind_address =   \n")
        with pytest.raises(ValueError, match="bind_address"):
            Config(config_path)


class TestCpuConfigParsing:
    """Unit tests for [CPU] section parsing."""

    def test_cpu_defaults(self, create_config):
        """Positive unit test for the [CPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [Ipmi] + [CPU] with enabled = 1 only and instantiate Config
        - inspect the single CpuConfig in cfg.cpu
        - ASSERT: exactly one CPU entry is parsed
        - ASSERT: section name, enabled flag, ipmi_zone and every default-valued numeric field match DV_CPU_*
        """
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\n")
        assert len(cfg.cpu) == 1
        cpu = cfg.cpu[0]
        assert cpu.section == "CPU"
        assert cpu.enabled is True
        assert cpu.ipmi_zone == [Config.CPU_ZONE]
        assert cpu.temp_calc == Config.CALC_AVG
        assert cpu.steps == Config.DV_CPU_STEPS
        assert cpu.sensitivity == Config.DV_CPU_SENSITIVITY
        assert cpu.polling == Config.DV_CPU_POLLING
        assert cpu.min_temp == Config.DV_CPU_MIN_TEMP
        assert cpu.max_temp == Config.DV_CPU_MAX_TEMP
        assert cpu.min_level == Config.DV_CPU_MIN_LEVEL
        assert cpu.max_level == Config.DV_CPU_MAX_LEVEL
        assert cpu.smoothing == Config.DV_CPU_SMOOTHING

    def test_cpu_custom_values(self, create_config):
        """Positive unit test for the [CPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with every numeric/list field populated and instantiate Config
        - inspect the parsed CpuConfig
        - ASSERT: ipmi_zone equals [0, 1]
        - ASSERT: temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, max_level, smoothing each
          equal the written value
        """
        cfg = create_config("""
[Ipmi]
[CPU]
enabled = 1
ipmi_zone = 0, 1
temp_calc = 2
steps = 8
sensitivity = 2.5
polling = 5.0
min_temp = 25.0
max_temp = 70.0
min_level = 30
max_level = 95
smoothing = 4
""")
        cpu = cfg.cpu[0]
        assert cpu.ipmi_zone == [0, 1]
        assert cpu.temp_calc == 2
        assert cpu.steps == 8
        assert cpu.sensitivity == 2.5
        assert cpu.polling == 5.0
        assert cpu.min_temp == 25.0
        assert cpu.max_temp == 70.0
        assert cpu.min_level == 30
        assert cpu.max_level == 95
        assert cpu.smoothing == 4

    def test_cpu_multi_section(self, create_config):
        """Positive unit test for the [CPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write three CPU sections [CPU], [CPU:0], [CPU:1] each with distinct min_temp / enabled values
        - inspect cfg.cpu after instantiating Config
        - ASSERT: cfg.cpu has length 3
        - ASSERT: each entry has the expected .section name in order ("CPU", "CPU:0", "CPU:1")
        - ASSERT: each entry has the expected min_temp value
        - ASSERT: the last entry's enabled flag is False
        """
        cfg = create_config("""
[Ipmi]
[CPU]
enabled = 1
ipmi_zone = 0
min_temp = 30
[CPU:0]
enabled = 1
ipmi_zone = 1
min_temp = 32
[CPU:1]
enabled = 0
min_temp = 34
""")
        assert len(cfg.cpu) == 3
        assert cfg.cpu[0].section == "CPU"
        assert cfg.cpu[0].min_temp == 30.0
        assert cfg.cpu[1].section == "CPU:0"
        assert cfg.cpu[1].min_temp == 32.0
        assert cfg.cpu[2].section == "CPU:1"
        assert cfg.cpu[2].min_temp == 34.0
        assert cfg.cpu[2].enabled is False

    def test_cpu_disabled(self, create_config):
        """Positive unit test for the [CPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with enabled = 0 and instantiate Config
        - ASSERT: cfg.cpu has length 1 (disabled section is still recorded)
        - ASSERT: cfg.cpu[0].enabled is False
        """
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 0\n")
        assert len(cfg.cpu) == 1
        assert cfg.cpu[0].enabled is False


class TestHdConfigParsing:
    """Unit tests for [HD] section parsing."""

    @pytest.mark.parametrize(
        "param, value",
        [
            pytest.param("temp_calc", "5", id="invalid-temp-calc"),
            pytest.param("steps", "0", id="steps-zero"),
            pytest.param("steps", "-1", id="steps-negative"),
            # steps > max_level - min_level (default max_level=100, min_level=35 -> 65)
            pytest.param("steps", "66", id="steps-over-range"),
            pytest.param("sensitivity", "0", id="sensitivity-zero"),
            pytest.param("sensitivity", "-1", id="sensitivity-negative"),
            pytest.param("polling", "-1", id="polling-negative"),
            pytest.param("smoothing", "0", id="smoothing-zero"),
            pytest.param("smoothing", "-1", id="smoothing-negative"),
            pytest.param("min_temp", "-1", id="min-temp-negative"),
            pytest.param("max_temp", "201", id="max-temp-over-200"),
            pytest.param("min_level", "-1", id="min-level-negative"),
            pytest.param("max_level", "101", id="max-level-over-100"),
        ],
    )
    def test_hd_validation_errors(self, create_config_file, param: str, value: str):
        """Negative unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [HD] with one invalid numeric parameter (temp_calc, steps, sensitivity, polling, smoothing, min/max
          temp/level) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        config_path = create_config_file(f"[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\n{param} = {value}\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_hd_max_temp_less_than_min_error(self, create_config_file):
        """Negative unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [HD] with min_temp = 50 and max_temp = 30 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions both "max_temp" and "min_temp"
        """
        content = "[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\nmin_temp = 50\nmax_temp = 30\n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_temp" in str(exc_info.value) and "min_temp" in str(exc_info.value)

    def test_hd_max_level_less_than_min_error(self, create_config_file):
        """Negative unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [HD] with min_level = 100 and max_level = 35 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions both "max_level" and "min_level"
        """
        content = "[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\nmin_level = 100\nmax_level = 35\n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_level" in str(exc_info.value) and "min_level" in str(exc_info.value)

    @pytest.mark.parametrize(
        "temp_calc",
        [
            pytest.param(0, id="calc-min"),
            pytest.param(1, id="calc-avg"),
            pytest.param(2, id="calc-max"),
        ],
    )
    def test_hd_temp_calc_all_values(self, create_config, temp_calc: int):
        """Positive unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [HD] with temp_calc = {0,1,2} and instantiate Config
        - ASSERT: cfg.hd[0].temp_calc equals the written value
        """
        cfg = create_config(f"[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\ntemp_calc = {temp_calc}\n")
        assert cfg.hd[0].temp_calc == temp_calc

    def test_hd_defaults(self, create_config):
        """Positive unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [HD] with enabled = 1 and hd_names = /dev/sda only and instantiate Config
        - inspect the single HdConfig in cfg.hd
        - ASSERT: exactly one HD entry is parsed
        - ASSERT: section/enabled/ipmi_zone, every default-valued numeric field, hd_names, smartctl_path,
          standby_guard_enabled and standby_hd_limit each match DV_HD_*
        """
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\n")
        assert len(cfg.hd) == 1
        hd = cfg.hd[0]
        assert hd.section == "HD"
        assert hd.enabled is True
        assert hd.ipmi_zone == [Config.HD_ZONE]
        assert hd.temp_calc == Config.CALC_AVG
        assert hd.steps == Config.DV_HD_STEPS
        assert hd.sensitivity == Config.DV_HD_SENSITIVITY
        assert hd.polling == Config.DV_HD_POLLING
        assert hd.min_temp == Config.DV_HD_MIN_TEMP
        assert hd.max_temp == Config.DV_HD_MAX_TEMP
        assert hd.min_level == Config.DV_HD_MIN_LEVEL
        assert hd.max_level == Config.DV_HD_MAX_LEVEL
        assert hd.smoothing == Config.DV_HD_SMOOTHING
        assert hd.hd_names == ["/dev/sda"]
        assert hd.smartctl_path == Config.DV_HD_SMARTCTL_PATH
        assert hd.standby_guard_enabled is False
        assert hd.standby_hd_limit == Config.DV_HD_STANDBY_HD_LIMIT

    def test_hd_multi_names_newline(self, create_config):
        """Positive unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [HD] with hd_names spread over multiple indented lines and instantiate Config
        - ASSERT: cfg.hd[0].hd_names equals ["/dev/sda", "/dev/sdb", "/dev/sdc"]
        """
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\n    /dev/sdb\n    /dev/sdc\n")
        assert cfg.hd[0].hd_names == ["/dev/sda", "/dev/sdb", "/dev/sdc"]

    def test_hd_multi_names_space(self, create_config):
        """Positive unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [HD] with hd_names = /dev/sda /dev/sdb /dev/sdc (space-separated) and instantiate Config
        - ASSERT: cfg.hd[0].hd_names equals ["/dev/sda", "/dev/sdb", "/dev/sdc"]
        """
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda /dev/sdb /dev/sdc\n")
        assert cfg.hd[0].hd_names == ["/dev/sda", "/dev/sdb", "/dev/sdc"]

    def test_hd_standby_guard(self, create_config):
        """Positive unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [HD] with standby_guard_enabled = 1 and standby_hd_limit = 2 and instantiate Config
        - ASSERT: cfg.hd[0].standby_guard_enabled is True
        - ASSERT: cfg.hd[0].standby_hd_limit equals 2
        """
        cfg = create_config("""
[Ipmi]
[HD]
enabled = 1
hd_names = /dev/sda /dev/sdb
standby_guard_enabled = 1
standby_hd_limit = 2
""")
        assert cfg.hd[0].standby_guard_enabled is True
        assert cfg.hd[0].standby_hd_limit == 2

    def test_hd_enabled_without_names_error(self, create_config_file):
        """Negative unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [HD] with enabled = 1 but no hd_names key and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "hd_names"
        """
        config_path = create_config_file("[Ipmi]\n[HD]\nenabled = 1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "hd_names" in str(exc_info.value)

    def test_hd_nvme_in_names_error(self, create_config_file):
        """Negative unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [HD] with hd_names = /dev/nvme0n1 (NVMe path in HD list) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "NVMe"
        """
        config_path = create_config_file("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/nvme0n1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "NVMe" in str(exc_info.value)

    def test_hd_standby_limit_negative_error(self, create_config_file):
        """Negative unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [HD] with standby_guard_enabled = 1 and standby_hd_limit = -1 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        content = ("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\n"
                   "standby_guard_enabled = 1\nstandby_hd_limit = -1\n")
        config_path = create_config_file(content)
        with pytest.raises(ValueError):
            Config(config_path)

    def test_hd_empty_smartctl_path_error(self, create_config_file):
        """Negative unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [HD] with enabled = 1, hd_names = /dev/sda and smartctl_path = (empty) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "smartctl_path"
        """
        content = "[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\nsmartctl_path = \n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "smartctl_path" in str(exc_info.value)

    def test_hd_multi_section(self, create_config):
        """Positive unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write two HD sections [HD] and [HD:0] each with distinct ipmi_zone and instantiate Config
        - ASSERT: cfg.hd has length 2
        - ASSERT: cfg.hd[0].section equals "HD" and ipmi_zone equals [1]
        - ASSERT: cfg.hd[1].section equals "HD:0" and ipmi_zone equals [2]
        """
        cfg = create_config("""
[Ipmi]
[HD]
enabled = 1
hd_names = /dev/sda
ipmi_zone = 1
[HD:0]
enabled = 1
hd_names = /dev/sdb
ipmi_zone = 2
""")
        assert len(cfg.hd) == 2
        assert cfg.hd[0].section == "HD"
        assert cfg.hd[0].ipmi_zone == [1]
        assert cfg.hd[1].section == "HD:0"
        assert cfg.hd[1].ipmi_zone == [2]


class TestNvmeConfigParsing:
    """Unit tests for [NVME] section parsing."""

    @pytest.mark.parametrize(
        "param, value",
        [
            pytest.param("temp_calc", "5", id="invalid-temp-calc"),
            pytest.param("steps", "0", id="steps-zero"),
            pytest.param("steps", "-1", id="steps-negative"),
            # steps > max_level - min_level (default max_level=100, min_level=35 -> 65)
            pytest.param("steps", "66", id="steps-over-range"),
            pytest.param("sensitivity", "0", id="sensitivity-zero"),
            pytest.param("sensitivity", "-1", id="sensitivity-negative"),
            pytest.param("polling", "-1", id="polling-negative"),
            pytest.param("smoothing", "0", id="smoothing-zero"),
            pytest.param("smoothing", "-1", id="smoothing-negative"),
            pytest.param("min_temp", "-1", id="min-temp-negative"),
            pytest.param("max_temp", "201", id="max-temp-over-200"),
            pytest.param("min_level", "-1", id="min-level-negative"),
            pytest.param("max_level", "101", id="max-level-over-100"),
        ],
    )
    def test_nvme_validation_errors(self, create_config_file, param: str, value: str):
        """Negative unit test for the [NVME] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [NVME] with one invalid numeric parameter (temp_calc, steps, sensitivity, polling, smoothing,
          min/max temp/level) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        body = f"[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\n{param} = {value}\n"
        config_path = create_config_file(body)
        with pytest.raises(ValueError):
            Config(config_path)

    def test_nvme_max_temp_less_than_min_error(self, create_config_file):
        """Negative unit test for the [NVME] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [NVME] with min_temp = 80 and max_temp = 40 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions both "max_temp" and "min_temp"
        """
        body = "[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\nmin_temp = 80\nmax_temp = 40\n"
        config_path = create_config_file(body)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_temp" in str(exc_info.value) and "min_temp" in str(exc_info.value)

    def test_nvme_max_level_less_than_min_error(self, create_config_file):
        """Negative unit test for the [NVME] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [NVME] with min_level = 100 and max_level = 35 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions both "max_level" and "min_level"
        """
        body = "[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\nmin_level = 100\nmax_level = 35\n"
        config_path = create_config_file(body)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_level" in str(exc_info.value) and "min_level" in str(exc_info.value)

    @pytest.mark.parametrize(
        "temp_calc",
        [
            pytest.param(0, id="calc-min"),
            pytest.param(1, id="calc-avg"),
            pytest.param(2, id="calc-max"),
        ],
    )
    def test_nvme_temp_calc_all_values(self, create_config, temp_calc: int):
        """Positive unit test for the [NVME] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [NVME] with temp_calc = {0,1,2} and instantiate Config
        - ASSERT: cfg.nvme[0].temp_calc equals the written value
        """
        cfg = create_config(f"[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\ntemp_calc = {temp_calc}\n")
        assert cfg.nvme[0].temp_calc == temp_calc

    def test_nvme_defaults(self, create_config):
        """Positive unit test for the [NVME] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [NVME] with enabled = 1 and nvme_names = /dev/nvme0n1 and instantiate Config
        - inspect the single NvmeConfig in cfg.nvme
        - ASSERT: exactly one NVME entry is parsed
        - ASSERT: section name "NVME", enabled is True, ipmi_zone equals [HD_ZONE]
        - ASSERT: min_temp/max_temp equal DV_NVME_MIN_TEMP/DV_NVME_MAX_TEMP
        - ASSERT: nvme_names equals ["/dev/nvme0n1"]
        """
        cfg = create_config("[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\n")
        assert len(cfg.nvme) == 1
        nvme = cfg.nvme[0]
        assert nvme.section == "NVME"
        assert nvme.enabled is True
        assert nvme.ipmi_zone == [Config.HD_ZONE]
        assert nvme.min_temp == Config.DV_NVME_MIN_TEMP
        assert nvme.max_temp == Config.DV_NVME_MAX_TEMP
        assert nvme.nvme_names == ["/dev/nvme0n1"]

    def test_nvme_enabled_without_names_error(self, create_config_file):
        """Negative unit test for the [NVME] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [NVME] with enabled = 1 but no nvme_names key and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "nvme_names"
        """
        config_path = create_config_file("[Ipmi]\n[NVME]\nenabled = 1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "nvme_names" in str(exc_info.value)

    def test_nvme_multi_section(self, create_config):
        """Positive unit test for the [NVME] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write two NVME sections [NVME] and [NVME:0] each with distinct ipmi_zone and instantiate Config
        - ASSERT: cfg.nvme has length 2
        - ASSERT: cfg.nvme[0].section equals "NVME"
        - ASSERT: cfg.nvme[1].section equals "NVME:0"
        """
        cfg = create_config("""
[Ipmi]
[NVME]
enabled = 1
ipmi_zone = 0
nvme_names = /dev/nvme0n1
[NVME:0]
enabled = 1
ipmi_zone = 1
nvme_names = /dev/nvme1n1
""")
        assert len(cfg.nvme) == 2
        assert cfg.nvme[0].section == "NVME"
        assert cfg.nvme[1].section == "NVME:0"


class TestGpuConfigParsing:
    """Unit tests for [GPU] section parsing."""

    @pytest.mark.parametrize(
        "param, value",
        [
            pytest.param("temp_calc", "5", id="invalid-temp-calc"),
            pytest.param("steps", "0", id="steps-zero"),
            pytest.param("steps", "-1", id="steps-negative"),
            # steps > max_level - min_level (default max_level=100, min_level=35 -> 65)
            pytest.param("steps", "66", id="steps-over-range"),
            pytest.param("sensitivity", "0", id="sensitivity-zero"),
            pytest.param("sensitivity", "-1", id="sensitivity-negative"),
            pytest.param("polling", "-1", id="polling-negative"),
            pytest.param("smoothing", "0", id="smoothing-zero"),
            pytest.param("smoothing", "-1", id="smoothing-negative"),
            pytest.param("min_temp", "-1", id="min-temp-negative"),
            pytest.param("max_temp", "201", id="max-temp-over-200"),
            pytest.param("min_level", "-1", id="min-level-negative"),
            pytest.param("max_level", "101", id="max-level-over-100"),
        ],
    )
    def test_gpu_validation_errors(self, create_config_file, param: str, value: str):
        """Negative unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [GPU] with one invalid numeric parameter (temp_calc, steps, sensitivity, polling, smoothing,
          min/max temp/level) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        config_path = create_config_file(f"[Ipmi]\n[GPU]\nenabled = 1\n{param} = {value}\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_gpu_max_temp_less_than_min_error(self, create_config_file):
        """Negative unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [GPU] with min_temp = 80 and max_temp = 40 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions both "max_temp" and "min_temp"
        """
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\nmin_temp = 80\nmax_temp = 40\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_temp" in str(exc_info.value) and "min_temp" in str(exc_info.value)

    def test_gpu_max_level_less_than_min_error(self, create_config_file):
        """Negative unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [GPU] with min_level = 100 and max_level = 35 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions both "max_level" and "min_level"
        """
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\nmin_level = 100\nmax_level = 35\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_level" in str(exc_info.value) and "min_level" in str(exc_info.value)

    @pytest.mark.parametrize(
        "temp_calc",
        [
            pytest.param(0, id="calc-min"),
            pytest.param(1, id="calc-avg"),
            pytest.param(2, id="calc-max"),
        ],
    )
    def test_gpu_temp_calc_all_values(self, create_config, temp_calc: int):
        """Positive unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [GPU] with temp_calc = {0,1,2} and instantiate Config
        - ASSERT: cfg.gpu[0].temp_calc equals the written value
        """
        cfg = create_config(f"[Ipmi]\n[GPU]\nenabled = 1\ntemp_calc = {temp_calc}\n")
        assert cfg.gpu[0].temp_calc == temp_calc

    def test_gpu_defaults_nvidia(self, create_config):
        """Positive unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [GPU] with enabled = 1 only and instantiate Config
        - inspect the single GpuConfig in cfg.gpu
        - ASSERT: exactly one GPU entry is parsed
        - ASSERT: section "GPU", enabled is True, gpu_type/device_ids/paths/temp keys match DV_GPU_*
        """
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\n")
        assert len(cfg.gpu) == 1
        gpu = cfg.gpu[0]
        assert gpu.section == "GPU"
        assert gpu.enabled is True
        assert gpu.gpu_type == Config.DV_GPU_TYPE
        assert gpu.gpu_device_ids == Config.parse_gpu_ids(Config.DV_GPU_DEVICE_IDS)
        assert gpu.nvidia_smi_path == Config.DV_GPU_NVIDIA_SMI_PATH
        assert gpu.rocm_smi_path == Config.DV_GPU_ROCM_SMI_PATH
        assert gpu.amd_temp_sensor == Config.DV_GPU_AMD_TEMP_SENSOR
        assert gpu.min_temp == Config.DV_GPU_MIN_TEMP
        assert gpu.max_temp == Config.DV_GPU_MAX_TEMP

    def test_gpu_amd_type(self, create_config):
        """Positive unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [GPU] with gpu_type = amd and amd_temp_sensor = 1 and instantiate Config
        - ASSERT: cfg.gpu[0].gpu_type equals "amd"
        - ASSERT: cfg.gpu[0].amd_temp_sensor equals 1
        """
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = amd\namd_temp_sensor = 1\n")
        assert cfg.gpu[0].gpu_type == "amd"
        assert cfg.gpu[0].amd_temp_sensor == 1

    def test_gpu_multiple_ids(self, create_config):
        """Positive unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [GPU] with gpu_device_ids = 0, 1, 2 and instantiate Config
        - ASSERT: cfg.gpu[0].gpu_device_ids equals [0, 1, 2]
        """
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\ngpu_device_ids = 0, 1, 2\n")
        assert cfg.gpu[0].gpu_device_ids == [0, 1, 2]

    def test_gpu_invalid_type_error(self, create_config_file):
        """Negative unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [GPU] with gpu_type = intel (unknown vendor) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "gpu_type"
        """
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = intel\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "gpu_type" in str(exc_info.value)

    def test_gpu_invalid_amd_sensor_error(self, create_config_file):
        """Negative unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [GPU] with gpu_type = amd and amd_temp_sensor = 5 (out of range) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "amd_temp_sensor"
        """
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = amd\namd_temp_sensor = 5\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "amd_temp_sensor" in str(exc_info.value)

    def test_gpu_empty_nvidia_smi_path_error(self, create_config_file):
        """Negative unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [GPU] with gpu_type = nvidia and nvidia_smi_path = (empty) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "nvidia_smi_path"
        """
        content = "[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = nvidia\nnvidia_smi_path = \n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "nvidia_smi_path" in str(exc_info.value)

    def test_gpu_empty_rocm_smi_path_error(self, create_config_file):
        """Negative unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [GPU] with gpu_type = amd and rocm_smi_path = (empty) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "rocm_smi_path"
        """
        content = "[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = amd\nrocm_smi_path = \n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "rocm_smi_path" in str(exc_info.value)

    def test_gpu_multi_section(self, create_config):
        """Positive unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write two GPU sections [GPU] (nvidia) and [GPU:0] (amd) and instantiate Config
        - ASSERT: cfg.gpu has length 2
        - ASSERT: cfg.gpu[0].gpu_type equals "nvidia"
        - ASSERT: cfg.gpu[1].gpu_type equals "amd"
        """
        cfg = create_config("""
[Ipmi]
[GPU]
enabled = 1
ipmi_zone = 0
gpu_type = nvidia
gpu_device_ids = 0
[GPU:0]
enabled = 1
ipmi_zone = 1
gpu_type = amd
gpu_device_ids = 1
""")
        assert len(cfg.gpu) == 2
        assert cfg.gpu[0].gpu_type == "nvidia"
        assert cfg.gpu[1].gpu_type == "amd"


class TestConstConfigParsing:
    """Unit tests for [CONST] section parsing."""

    def test_const_defaults(self, create_config):
        """Positive unit test for the [CONST] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CONST] with enabled = 1 only and instantiate Config
        - inspect the single ConstConfig in cfg.const
        - ASSERT: exactly one CONST entry is parsed
        - ASSERT: section "CONST", enabled is True, ipmi_zone equals [HD_ZONE]
        - ASSERT: polling equals DV_CONST_POLLING and level equals DV_CONST_LEVEL
        """
        cfg = create_config("[Ipmi]\n[CONST]\nenabled = 1\n")
        assert len(cfg.const) == 1
        const = cfg.const[0]
        assert const.section == "CONST"
        assert const.enabled is True
        assert const.ipmi_zone == [Config.HD_ZONE]
        assert const.polling == Config.DV_CONST_POLLING
        assert const.level == Config.DV_CONST_LEVEL

    def test_const_custom_values(self, create_config):
        """Positive unit test for the [CONST] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CONST] with ipmi_zone = 0, 1; polling = 60; level = 75 and instantiate Config
        - ASSERT: const.ipmi_zone equals [0, 1]
        - ASSERT: const.polling equals 60.0
        - ASSERT: const.level equals 75
        """
        cfg = create_config("[Ipmi]\n[CONST]\nenabled = 1\nipmi_zone = 0, 1\npolling = 60\nlevel = 75\n")
        const = cfg.const[0]
        assert const.ipmi_zone == [0, 1]
        assert const.polling == 60.0
        assert const.level == 75

    def test_const_invalid_level_error(self, create_config_file):
        """Negative unit test for the [CONST] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [CONST] with level = 150 (over 100) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "level"
        """
        config_path = create_config_file("[Ipmi]\n[CONST]\nenabled = 1\nlevel = 150\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "level" in str(exc_info.value)

    def test_const_negative_polling_error(self, create_config_file):
        """Negative unit test for the [CONST] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [CONST] with polling = -1 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        config_path = create_config_file("[Ipmi]\n[CONST]\nenabled = 1\npolling = -1\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_const_multi_section(self, create_config):
        """Positive unit test for the [CONST] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write two CONST sections [CONST] and [CONST:0] with distinct levels and instantiate Config
        - ASSERT: cfg.const has length 2
        - ASSERT: cfg.const[0].level equals 40
        - ASSERT: cfg.const[1].level equals 60
        """
        cfg = create_config("""
[Ipmi]
[CONST]
enabled = 1
ipmi_zone = 0
level = 40
[CONST:0]
enabled = 1
ipmi_zone = 1
level = 60
""")
        assert len(cfg.const) == 2
        assert cfg.const[0].level == 40
        assert cfg.const[1].level == 60


class TestFanControllerValidation:
    """Unit tests for _validate_fan_controller_config() validation logic."""

    @pytest.mark.parametrize(
        "param, value",
        [
            pytest.param("temp_calc", "5", id="invalid-temp-calc"),
            pytest.param("steps", "0", id="steps-zero"),
            pytest.param("steps", "-1", id="steps-negative"),
            # steps > max_level - min_level (default max_level=100, min_level=35 -> 65)
            pytest.param("steps", "66", id="steps-over-range"),
            pytest.param("sensitivity", "0", id="sensitivity-zero"),
            pytest.param("sensitivity", "-1", id="sensitivity-negative"),
            pytest.param("polling", "-1", id="polling-negative"),
            pytest.param("smoothing", "0", id="smoothing-zero"),
            pytest.param("smoothing", "-1", id="smoothing-negative"),
            pytest.param("min_temp", "-1", id="min-temp-negative"),
            pytest.param("max_temp", "201", id="max-temp-over-200"),
            pytest.param("min_level", "-1", id="min-level-negative"),
            pytest.param("max_level", "101", id="max-level-over-100"),
        ],
    )
    def test_cpu_validation_errors(self, create_config_file, param: str, value: str):
        """Negative unit test for Config._validate_fan_controller_config() via [CPU] section. It contains the
        following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [CPU] with one invalid numeric parameter (temp_calc, steps, sensitivity, polling, smoothing,
          min/max temp/level) and call Config(path)
        - ASSERT: Config(path) raises ValueError from the shared fan-controller validator
        """
        config_path = create_config_file(f"[Ipmi]\n[CPU]\nenabled = 1\n{param} = {value}\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_cpu_max_temp_less_than_min_error(self, create_config_file):
        """Negative unit test for Config._validate_fan_controller_config() via [CPU] section. It contains the
        following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [CPU] with min_temp = 60 and max_temp = 30 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions both "max_temp" and "min_temp"
        """
        config_path = create_config_file("[Ipmi]\n[CPU]\nenabled = 1\nmin_temp = 60\nmax_temp = 30\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_temp" in str(exc_info.value) and "min_temp" in str(exc_info.value)

    def test_cpu_max_level_less_than_min_error(self, create_config_file):
        """Negative unit test for Config._validate_fan_controller_config() via [CPU] section. It contains the
        following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [CPU] with min_level = 100 and max_level = 35 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions both "max_level" and "min_level"
        """
        config_path = create_config_file("[Ipmi]\n[CPU]\nenabled = 1\nmin_level = 100\nmax_level = 35\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_level" in str(exc_info.value) and "min_level" in str(exc_info.value)


class TestConfigConstants:
    """Unit tests for Config class constants."""

    def test_section_name_constants(self):
        """Positive unit test for Config section-name class constants. It contains the following steps:
        - no external mocks
        - read each CS_* class constant
        - ASSERT: CS_IPMI/CS_CPU/CS_HD/CS_NVME/CS_GPU/CS_CONST equal the expected literal section names
        """
        assert Config.CS_IPMI == "Ipmi"
        assert Config.CS_CPU == "CPU"
        assert Config.CS_HD == "HD"
        assert Config.CS_NVME == "NVME"
        assert Config.CS_GPU == "GPU"
        assert Config.CS_CONST == "CONST"

    def test_calc_constants(self):
        """Positive unit test for Config calculation-method class constants. It contains the following steps:
        - no external mocks
        - read CALC_MIN, CALC_AVG, CALC_MAX class constants
        - ASSERT: CALC_MIN == 0, CALC_AVG == 1, CALC_MAX == 2
        """
        assert Config.CALC_MIN == 0
        assert Config.CALC_AVG == 1
        assert Config.CALC_MAX == 2

    def test_zone_constants(self):
        """Positive unit test for Config IPMI zone class constants. It contains the following steps:
        - no external mocks
        - read CPU_ZONE and HD_ZONE class constants
        - ASSERT: CPU_ZONE == 0 and HD_ZONE == 1
        """
        assert Config.CPU_ZONE == 0
        assert Config.HD_ZONE == 1

    def test_amd_temp_keys(self):
        """Positive unit test for the Config.CV_AMD_TEMP_KEYS class constant. It contains the following steps:
        - no external mocks
        - read the CV_AMD_TEMP_KEYS tuple
        - ASSERT: CV_AMD_TEMP_KEYS has length 3
        - ASSERT: entry [0] contains "junction"
        - ASSERT: entry [1] contains "edge"
        - ASSERT: entry [2] contains "memory"
        """
        assert len(Config.CV_AMD_TEMP_KEYS) == 3
        assert "junction" in Config.CV_AMD_TEMP_KEYS[0].lower()
        assert "edge" in Config.CV_AMD_TEMP_KEYS[1].lower()
        assert "memory" in Config.CV_AMD_TEMP_KEYS[2].lower()


class TestEdgeCases:
    """Unit tests for edge cases and additional coverage."""

    def test_hd_disabled_without_names(self, create_config):
        """Positive unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [HD] with enabled = 0 and no hd_names and instantiate Config
        - ASSERT: cfg.hd has length 1
        - ASSERT: cfg.hd[0].enabled is False
        - ASSERT: cfg.hd[0].hd_names is an empty list (disabled section does not require names)
        """
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 0\n")
        assert len(cfg.hd) == 1
        assert cfg.hd[0].enabled is False
        assert cfg.hd[0].hd_names == []

    def test_nvme_disabled_without_names(self, create_config):
        """Positive unit test for the [NVME] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [NVME] with enabled = 0 and no nvme_names and instantiate Config
        - ASSERT: cfg.nvme has length 1
        - ASSERT: cfg.nvme[0].enabled is False
        - ASSERT: cfg.nvme[0].nvme_names is an empty list
        """
        cfg = create_config("[Ipmi]\n[NVME]\nenabled = 0\n")
        assert len(cfg.nvme) == 1
        assert cfg.nvme[0].enabled is False
        assert cfg.nvme[0].nvme_names == []

    def test_hd_custom_smartctl_path(self, create_config):
        """Positive unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [HD] with smartctl_path = /opt/smartctl and instantiate Config
        - ASSERT: cfg.hd[0].smartctl_path equals "/opt/smartctl"
        """
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\nsmartctl_path = /opt/smartctl\n")
        assert cfg.hd[0].smartctl_path == "/opt/smartctl"

    def test_gpu_custom_nvidia_path(self, create_config):
        """Positive unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [GPU] with nvidia_smi_path = /opt/nvidia-smi and instantiate Config
        - ASSERT: cfg.gpu[0].nvidia_smi_path equals "/opt/nvidia-smi"
        """
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\nnvidia_smi_path = /opt/nvidia-smi\n")
        assert cfg.gpu[0].nvidia_smi_path == "/opt/nvidia-smi"

    def test_gpu_custom_rocm_path(self, create_config):
        """Positive unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [GPU] with gpu_type = amd and rocm_smi_path = /opt/rocm-smi and instantiate Config
        - ASSERT: cfg.gpu[0].rocm_smi_path equals "/opt/rocm-smi"
        """
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = amd\nrocm_smi_path = /opt/rocm-smi\n")
        assert cfg.gpu[0].rocm_smi_path == "/opt/rocm-smi"

    @pytest.mark.parametrize(
        "temp_calc",
        [
            pytest.param(0, id="calc-min"),
            pytest.param(1, id="calc-avg"),
            pytest.param(2, id="calc-max"),
        ],
    )
    def test_cpu_temp_calc_all_values(self, create_config, temp_calc: int):
        """Positive unit test for the [CPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with temp_calc = {0,1,2} and instantiate Config
        - ASSERT: cfg.cpu[0].temp_calc equals the written value
        """
        cfg = create_config(f"[Ipmi]\n[CPU]\nenabled = 1\ntemp_calc = {temp_calc}\n")
        assert cfg.cpu[0].temp_calc == temp_calc

    def test_cpu_polling_zero(self, create_config):
        """Positive unit test for the [CPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with polling = 0 (boundary, immediate polling) and instantiate Config
        - ASSERT: cfg.cpu[0].polling equals 0.0
        """
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\npolling = 0\n")
        assert cfg.cpu[0].polling == 0.0

    def test_const_level_boundary_zero(self, create_config_file):
        """Negative unit test for the [CONST] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [CONST] with level = 0 (fans off boundary) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        - ASSERT: the error message mentions "level"
        """
        config_path = create_config_file("[Ipmi]\n[CONST]\nenabled = 1\nlevel = 0\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "level" in str(exc_info.value)

    def test_const_level_boundary_one(self, create_config):
        """Positive unit test for the [CONST] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CONST] with level = 1 (minimum allowed) and instantiate Config
        - ASSERT: cfg.const[0].level equals 1
        """
        cfg = create_config("[Ipmi]\n[CONST]\nenabled = 1\nlevel = 1\n")
        assert cfg.const[0].level == 1

    def test_const_level_boundary_hundred(self, create_config):
        """Positive unit test for the [CONST] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CONST] with level = 100 (maximum allowed) and instantiate Config
        - ASSERT: cfg.const[0].level equals 100
        """
        cfg = create_config("[Ipmi]\n[CONST]\nenabled = 1\nlevel = 100\n")
        assert cfg.const[0].level == 100

    def test_ipmi_zone_boundary_zero(self, create_config):
        """Positive unit test for Config.parse_ipmi_zones() via [CPU] wiring. It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with ipmi_zone = 0 (lower boundary) and instantiate Config
        - ASSERT: cfg.cpu[0].ipmi_zone equals [0]
        """
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = 0\n")
        assert cfg.cpu[0].ipmi_zone == [0]

    def test_ipmi_zone_boundary_hundred(self, create_config):
        """Positive unit test for Config.parse_ipmi_zones() via [CPU] wiring. It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with ipmi_zone = 100 (upper boundary) and instantiate Config
        - ASSERT: cfg.cpu[0].ipmi_zone equals [100]
        """
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = 100\n")
        assert cfg.cpu[0].ipmi_zone == [100]

    def test_min_equals_max_temp(self, create_config):
        """Positive unit test for Config._validate_fan_controller_config() via [CPU] section. It contains the
        following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with min_temp = 40 and max_temp = 40 and instantiate Config
        - ASSERT: cfg.cpu[0].min_temp equals 40.0
        - ASSERT: cfg.cpu[0].max_temp equals 40.0
        """
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nmin_temp = 40\nmax_temp = 40\n")
        assert cfg.cpu[0].min_temp == 40.0
        assert cfg.cpu[0].max_temp == 40.0

    def test_min_equals_max_level(self, create_config):
        """Positive unit test for Config._validate_fan_controller_config() via [CPU] section. It contains the
        following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with min_level = 50 and max_level = 50 and instantiate Config
        - ASSERT: cfg.cpu[0].min_level equals 50
        - ASSERT: cfg.cpu[0].max_level equals 50
        """
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nmin_level = 50\nmax_level = 50\n")
        assert cfg.cpu[0].min_level == 50
        assert cfg.cpu[0].max_level == 50

    def test_hd_nvme_mixed_case_detection(self, create_config_file):
        """Negative unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [HD] with hd_names = /dev/NVME0N1 (uppercase NVMe) and call Config(path)
        - ASSERT: Config(path) raises ValueError (NVMe detection is case-insensitive)
        - ASSERT: the error message mentions "NVMe"
        """
        config_path = create_config_file("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/NVME0N1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "NVMe" in str(exc_info.value)

    def test_gpu_type_case_insensitive(self, create_config):
        """Positive unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [GPU] with gpu_type = NVIDIA (uppercase) and instantiate Config
        - ASSERT: cfg.gpu[0].gpu_type equals "nvidia" (normalized to lowercase)
        """
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = NVIDIA\n")
        assert cfg.gpu[0].gpu_type == "nvidia"

    def test_no_controller_sections(self, create_config):
        """Positive unit test for Config.__init__() file-loading path. It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write only [Ipmi] with a command key and instantiate Config
        - ASSERT: cfg.cpu, cfg.hd, cfg.nvme, cfg.gpu, cfg.const are all empty lists
        """
        cfg = create_config("[Ipmi]\ncommand = /usr/bin/ipmitool\n")
        assert cfg.cpu == []
        assert cfg.hd == []
        assert cfg.nvme == []
        assert cfg.gpu == []
        assert cfg.const == []

    def test_numbered_sections_only(self, create_config):
        """Positive unit test for the [CPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write only numbered sections [CPU:0] and [CPU:1] (no base [CPU]) and instantiate Config
        - ASSERT: cfg.cpu has length 2
        - ASSERT: cfg.cpu[0].section equals "CPU:0"
        - ASSERT: cfg.cpu[1].section equals "CPU:1"
        """
        cfg = create_config("[Ipmi]\n[CPU:0]\nenabled = 1\n[CPU:1]\nenabled = 0\n")
        assert len(cfg.cpu) == 2
        assert cfg.cpu[0].section == "CPU:0"
        assert cfg.cpu[1].section == "CPU:1"

    def test_unordered_numbered_sections_sorted(self, create_config):
        """Positive unit test for the [HD] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write numbered sections [HD:5], [HD:1], [HD:3] in out-of-order positions and instantiate Config
        - ASSERT: cfg.hd has length 3
        - ASSERT: cfg.hd[0].section equals "HD:1"
        - ASSERT: cfg.hd[1].section equals "HD:3"
        - ASSERT: cfg.hd[2].section equals "HD:5"
        """
        cfg = create_config("[Ipmi]\n[HD:5]\nenabled = 0\n[HD:1]\nenabled = 0\n[HD:3]\nenabled = 0\n")
        assert len(cfg.hd) == 3
        assert cfg.hd[0].section == "HD:1"
        assert cfg.hd[1].section == "HD:3"
        assert cfg.hd[2].section == "HD:5"

    def test_const_level_negative_error(self, create_config_file):
        """Negative unit test for the [CONST] section parser inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [CONST] with level = -1 and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        config_path = create_config_file("[Ipmi]\n[CONST]\nenabled = 1\nlevel = -1\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_gpu_device_ids_empty_string_error(self, create_config_file):
        """Negative unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config_file fixture (tmp_path-backed)
        - write [GPU] with gpu_device_ids = (empty) and call Config(path)
        - ASSERT: Config(path) raises ValueError
        """
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\ngpu_device_ids = \n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_gpu_device_ids_many(self, create_config):
        """Positive unit test for the [GPU] section parser inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [GPU] with gpu_device_ids = "0, 1, ..., 9" and instantiate Config
        - ASSERT: cfg.gpu[0].gpu_device_ids equals list(range(10))
        """
        ids = ", ".join(str(i) for i in range(10))
        cfg = create_config(f"[Ipmi]\n[GPU]\nenabled = 1\ngpu_device_ids = {ids}\n")
        assert cfg.gpu[0].gpu_device_ids == list(range(10))

    def test_multi_zone_duplicates(self, create_config):
        """Positive unit test for Config.parse_ipmi_zones() via [CPU] wiring. It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with ipmi_zone = 0, 0, 1, 1 (duplicates) and instantiate Config
        - ASSERT: cfg.cpu[0].ipmi_zone preserves duplicates as [0, 0, 1, 1]
        """
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = 0, 0, 1, 1\n")
        assert cfg.cpu[0].ipmi_zone == [0, 0, 1, 1]

    def test_multi_zone_many(self, create_config):
        """Positive unit test for Config.parse_ipmi_zones() via [CPU] wiring. It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] with ipmi_zone = "0, 1, ..., 9" and instantiate Config
        - ASSERT: cfg.cpu[0].ipmi_zone equals list(range(10))
        """
        zones = ", ".join(str(i) for i in range(10))
        cfg = create_config(f"[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = {zones}\n")
        assert cfg.cpu[0].ipmi_zone == list(range(10))


class TestConfigFullIntegration:
    """Integration tests for full configuration scenarios."""

    def test_full_config_all_controllers(self, create_config):
        """Positive unit test for full multi-section parsing inside Config.__init__(). It contains the following
        steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write a body with [Ipmi] + every controller section (CPU, HD, NVME, GPU, CONST) populated
          and instantiate Config
        - inspect each parsed controller list
        - ASSERT: ipmi.command equals "/usr/bin/ipmitool"
        - ASSERT: cfg.cpu has length 1 and cpu[0].enabled is True
        - ASSERT: cfg.hd has length 1 and hd[0].hd_names has length 2
        - ASSERT: cfg.nvme has length 1
        - ASSERT: cfg.gpu has length 1 and gpu[0].gpu_device_ids equals [0, 1]
        - ASSERT: cfg.const has length 1 and const[0].level equals 40
        """
        cfg = create_config("""
[Ipmi]
command = /usr/bin/ipmitool
fan_mode_delay = 5
fan_level_delay = 1

[CPU]
enabled = 1
ipmi_zone = 0
temp_calc = 1
steps = 6
sensitivity = 3
polling = 2
min_temp = 30
max_temp = 60
min_level = 35
max_level = 100

[HD]
enabled = 1
ipmi_zone = 1
hd_names = /dev/sda
    /dev/sdb
standby_guard_enabled = 1
standby_hd_limit = 1

[NVME]
enabled = 1
ipmi_zone = 1
nvme_names = /dev/nvme0n1

[GPU]
enabled = 1
ipmi_zone = 1
gpu_type = nvidia
gpu_device_ids = 0, 1

[CONST]
enabled = 1
ipmi_zone = 2
level = 40
""")
        assert cfg.ipmi.command == "/usr/bin/ipmitool"
        assert len(cfg.cpu) == 1
        assert cfg.cpu[0].enabled is True
        assert len(cfg.hd) == 1
        assert len(cfg.hd[0].hd_names) == 2
        assert len(cfg.nvme) == 1
        assert len(cfg.gpu) == 1
        assert cfg.gpu[0].gpu_device_ids == [0, 1]
        assert len(cfg.const) == 1
        assert cfg.const[0].level == 40

    def test_multi_section_ordering(self, create_config):
        """Positive unit test for multi-section ordering inside Config.__init__(). It contains the following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write CPU sections in scrambled order [CPU:2], [CPU], [CPU:0], [CPU:1] and instantiate Config
        - inspect cfg.cpu order
        - ASSERT: cfg.cpu has length 4
        - ASSERT: cfg.cpu[0].section equals "CPU"
        - ASSERT: cfg.cpu[1].section equals "CPU:0"
        - ASSERT: cfg.cpu[2].section equals "CPU:1"
        - ASSERT: cfg.cpu[3].section equals "CPU:2"
        """
        cfg = create_config("""
[Ipmi]
[CPU:2]
enabled = 1
ipmi_zone = 3
[CPU]
enabled = 1
ipmi_zone = 0
[CPU:0]
enabled = 1
ipmi_zone = 1
[CPU:1]
enabled = 1
ipmi_zone = 2
""")
        # Should be ordered: CPU, CPU:0, CPU:1, CPU:2
        assert len(cfg.cpu) == 4
        assert cfg.cpu[0].section == "CPU"
        assert cfg.cpu[1].section == "CPU:0"
        assert cfg.cpu[2].section == "CPU:1"
        assert cfg.cpu[3].section == "CPU:2"


class TestDuplicateZoneValidation:
    """Unit tests for _validate_no_duplicate_zones() validation logic."""

    def test_cpu_duplicate_zone_raises(self, create_config):
        """Negative unit test for Config._validate_no_duplicate_zones() (duplicate-zone detection). It contains the
        following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write two enabled CPU instances [CPU:0] and [CPU:1] both with ipmi_zone = 0
        - ASSERT: create_config raises ValueError whose message matches the [CPU:1] / [CPU:0] collision pattern
        """
        with pytest.raises(ValueError, match=r"\[CPU:1\] IPMI zone 0 is already used by \[CPU:0\]"):
            create_config("[Ipmi]\n[CPU:0]\nenabled = 1\nipmi_zone = 0\n[CPU:1]\nenabled = 1\nipmi_zone = 0\n")

    def test_hd_duplicate_zone_raises(self, create_config):
        """Negative unit test for Config._validate_no_duplicate_zones() (duplicate-zone detection). It contains the
        following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write two enabled HD instances [HD] and [HD:1] both with ipmi_zone = 1 and distinct hd_names
        - ASSERT: create_config raises ValueError whose message matches the [HD:1] / [HD] collision pattern
        """
        with pytest.raises(ValueError, match=r"\[HD:1\] IPMI zone 1 is already used by \[HD\]"):
            create_config("[Ipmi]\n[HD]\nenabled = 1\nipmi_zone = 1\nhd_names = /dev/sda\n"
                         "[HD:1]\nenabled = 1\nipmi_zone = 1\nhd_names = /dev/sdb\n")

    def test_disabled_instance_no_conflict(self, create_config):
        """Positive unit test for Config._validate_no_duplicate_zones() (duplicate-zone detection). It contains the
        following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU] enabled = 1 and [CPU:1] enabled = 0 both with ipmi_zone = 0 and instantiate Config
        - ASSERT: cfg.cpu has length 2 (disabled instance does not collide)
        """
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = 0\n[CPU:1]\nenabled = 0\nipmi_zone = 0\n")
        assert len(cfg.cpu) == 2

    def test_different_zones_no_conflict(self, create_config):
        """Positive unit test for Config._validate_no_duplicate_zones() (duplicate-zone detection). It contains the
        following steps:
        - mock the on-disk config via the create_config fixture (tmp_path-backed)
        - write [CPU:0] ipmi_zone = 0 and [CPU:1] ipmi_zone = 1 (both enabled) and instantiate Config
        - ASSERT: cfg.cpu has length 2 (distinct zones produce no conflict)
        """
        cfg = create_config("[Ipmi]\n[CPU:0]\nenabled = 1\nipmi_zone = 0\n[CPU:1]\nenabled = 1\nipmi_zone = 1\n")
        assert len(cfg.cpu) == 2


# End.
