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
        "input_str, expected, error_str",
        [
            # Single zone 0
            ("0", [0], "Config.parse_ipmi_zones() p1"),
            # Single zone 1
            ("1", [1], "Config.parse_ipmi_zones() p2"),
            # Comma-separated with spaces
            ("0, 1", [0, 1], "Config.parse_ipmi_zones() p3"),
            # Comma-separated without spaces
            ("0,1,2", [0, 1, 2], "Config.parse_ipmi_zones() p4"),
            # Space-separated
            ("0 1", [0, 1], "Config.parse_ipmi_zones() p5"),
            # Space-separated multiple
            ("0 1 2", [0, 1, 2], "Config.parse_ipmi_zones() p6"),
            # Extra whitespace
            ("  0  1  2  ", [0, 1, 2], "Config.parse_ipmi_zones() p7"),
            # Comma with extra whitespace
            ("  0,  1,  2  ", [0, 1, 2], "Config.parse_ipmi_zones() p8"),
            # Max valid zone
            ("100", [100], "Config.parse_ipmi_zones() p9"),
            # Duplicate zones preserved
            ("0, 1, 0", [0, 1, 0], "Config.parse_ipmi_zones() p10"),
        ],
    )
    def test_parse_ipmi_zones_valid(self, input_str: str, expected: List[int], error_str: str):
        """Positive unit test for Config.parse_ipmi_zones() method."""
        assert Config.parse_ipmi_zones(input_str) == expected, error_str

    @pytest.mark.parametrize(
        "input_str, error_str",
        [
            # Negative zone
            ("-1", "Config.parse_ipmi_zones() n1"),
            # Zone over 100
            ("101", "Config.parse_ipmi_zones() n2"),
            # Non-numeric string
            ("abc", "Config.parse_ipmi_zones() n3"),
            # Mixed valid and invalid
            ("0, abc", "Config.parse_ipmi_zones() n4"),
            # Empty string
            ("", "Config.parse_ipmi_zones() n5"),
        ],
    )
    def test_parse_ipmi_zones_invalid(self, input_str: str, error_str: str):
        """Negative unit test for Config.parse_ipmi_zones() method."""
        with pytest.raises((ValueError, IndexError)):
            Config.parse_ipmi_zones(input_str)

    @pytest.mark.parametrize(
        "input_str, expected, error_str",
        [
            # Single device
            ("/dev/sda", ["/dev/sda"], "Config.parse_device_names() p1"),
            # Space-separated
            ("/dev/sda /dev/sdb", ["/dev/sda", "/dev/sdb"], "Config.parse_device_names() p2"),
            # Newline-separated
            ("/dev/sda\n/dev/sdb", ["/dev/sda", "/dev/sdb"], "Config.parse_device_names() p3"),
            # Multiple newline-separated
            ("/dev/sda\n/dev/sdb\n/dev/sdc", ["/dev/sda", "/dev/sdb", "/dev/sdc"], "Config.parse_device_names() p4"),
            # By-id paths
            ("/dev/disk/by-id/wwn-0x5000 /dev/disk/by-id/wwn-0x5001",
             ["/dev/disk/by-id/wwn-0x5000", "/dev/disk/by-id/wwn-0x5001"], "Config.parse_device_names() p5"),
        ],
    )
    def test_parse_device_names_valid(self, input_str: str, expected: List[str], error_str: str):
        """Positive unit test for Config.parse_device_names() method."""
        assert Config.parse_device_names(input_str) == expected, error_str

    @pytest.mark.parametrize(
        "input_str, expected, error_str",
        [
            # Single GPU ID
            ("0", [0], "Config.parse_gpu_ids() p1"),
            # Comma-separated with space
            ("0, 1", [0, 1], "Config.parse_gpu_ids() p2"),
            # Comma-separated multiple
            ("0,1,2,3", [0, 1, 2, 3], "Config.parse_gpu_ids() p3"),
            # Space-separated
            ("0 1 2", [0, 1, 2], "Config.parse_gpu_ids() p4"),
            # Extra whitespace
            ("  0  1  2  ", [0, 1, 2], "Config.parse_gpu_ids() p5"),
        ],
    )
    def test_parse_gpu_ids_valid(self, input_str: str, expected: List[int], error_str: str):
        """Positive unit test for Config.parse_gpu_ids() method."""
        assert Config.parse_gpu_ids(input_str) == expected, error_str

    @pytest.mark.parametrize(
        "input_str, error_str",
        [
            # Negative ID
            ("-1", "Config.parse_gpu_ids() n1"),
            # ID over 100
            ("101", "Config.parse_gpu_ids() n2"),
            # Non-numeric string
            ("abc", "Config.parse_gpu_ids() n3"),
        ],
    )
    def test_parse_gpu_ids_invalid(self, input_str: str, error_str: str):
        """Negative unit test for Config.parse_gpu_ids() method."""
        with pytest.raises(ValueError):
            Config.parse_gpu_ids(input_str)


class TestConfigFileLoading:
    """Unit tests for Config file loading."""

    def test_config_file_not_found(self):
        """Negative test: Config raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            Config("/nonexistent/path/to/config.conf")

    def test_config_load_minimal(self, create_config):
        """Positive test: Config loads minimal valid configuration."""
        cfg = create_config("[Ipmi]\ncommand = /usr/bin/ipmitool\n")
        assert cfg.ipmi.command == Config.DV_IPMI_COMMAND, "TestConfigFileLoading.test_config_load_minimal: command default"
        assert cfg.ipmi.fan_mode_delay == Config.DV_IPMI_FAN_MODE_DELAY, "TestConfigFileLoading.test_config_load_minimal: fan_mode_delay default"
        assert cfg.ipmi.fan_level_delay == Config.DV_IPMI_FAN_LEVEL_DELAY, "TestConfigFileLoading.test_config_load_minimal: fan_level_delay default"
        assert cfg.cpu == [], "TestConfigFileLoading.test_config_load_minimal: no cpu sections"
        assert cfg.hd == [], "TestConfigFileLoading.test_config_load_minimal: no hd sections"
        assert cfg.nvme == [], "TestConfigFileLoading.test_config_load_minimal: no nvme sections"
        assert cfg.gpu == [], "TestConfigFileLoading.test_config_load_minimal: no gpu sections"
        assert cfg.const == [], "TestConfigFileLoading.test_config_load_minimal: no const sections"

    def test_config_missing_ipmi_section(self, create_config_file):
        """Negative test: Config raises ValueError when [Ipmi] section is missing."""
        config_path = create_config_file("[CPU]\nenabled = 1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "Missing mandatory [Ipmi] section" in str(exc_info.value)

    def test_config_invalid_ini_format(self, create_config_file):
        """Negative test: Config raises error for malformed INI file."""
        config_path = create_config_file("This is not a valid INI file\nNo sections here\n")
        with pytest.raises(MissingSectionHeaderError):
            Config(config_path)

    def test_config_invalid_ini_duplicate_section(self, create_config_file):
        """Negative test: ConfigParser raises DuplicateSectionError for strict mode (default)."""
        cfg_path = create_config_file("[Ipmi]\ncommand = /first\n[Ipmi]\ncommand = /second\n")
        with pytest.raises(DuplicateSectionError):
            Config(cfg_path)

    def test_config_invalid_data_type_int(self, create_config_file):
        """Negative test: Config raises error for non-integer where integer expected."""
        config_path = create_config_file("[Ipmi]\nfan_mode_delay = abc\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_config_invalid_data_type_float(self, create_config_file):
        """Negative test: Config raises error for non-float where float expected."""
        config_path = create_config_file("[Ipmi]\n[CPU]\nenabled = 1\npolling = not_a_float\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_config_invalid_data_type_boolean(self, create_config_file):
        """Negative test: Config raises error for invalid boolean value."""
        config_path = create_config_file("[Ipmi]\n[CPU]\nenabled = maybe\n")
        with pytest.raises(ValueError):
            Config(config_path)


class TestIpmiConfigParsing:
    """Unit tests for [Ipmi] section parsing."""

    def test_ipmi_defaults(self, create_config):
        """Positive test: IpmiConfig uses correct default values."""
        cfg = create_config("[Ipmi]\n")
        assert cfg.ipmi.command == Config.DV_IPMI_COMMAND, "TestIpmiConfigParsing.test_ipmi_defaults: command default"
        assert cfg.ipmi.fan_mode_delay == Config.DV_IPMI_FAN_MODE_DELAY, "TestIpmiConfigParsing.test_ipmi_defaults: fan_mode_delay default"
        assert cfg.ipmi.fan_level_delay == Config.DV_IPMI_FAN_LEVEL_DELAY, "TestIpmiConfigParsing.test_ipmi_defaults: fan_level_delay default"
        assert cfg.ipmi.remote_parameters == Config.DV_IPMI_REMOTE_PARAMETERS, "TestIpmiConfigParsing.test_ipmi_defaults: remote_parameters default"
        assert cfg.ipmi.platform_name == Config.DV_IPMI_PLATFORM_NAME, "TestIpmiConfigParsing.test_ipmi_defaults: platform_name default"

    def test_ipmi_custom_values(self, create_config):
        """Positive test: IpmiConfig parses custom values."""
        cfg = create_config("""
[Ipmi]
command = /opt/ipmitool
fan_mode_delay = 5
fan_level_delay = 1
remote_parameters = -I lanplus -U admin -P secret -H 192.168.1.100
platform_name = X11DPH-T
""")
        assert cfg.ipmi.command == "/opt/ipmitool", "TestIpmiConfigParsing.test_ipmi_custom_values: command"
        assert cfg.ipmi.fan_mode_delay == 5, "TestIpmiConfigParsing.test_ipmi_custom_values: fan_mode_delay"
        assert cfg.ipmi.fan_level_delay == 1, "TestIpmiConfigParsing.test_ipmi_custom_values: fan_level_delay"
        assert cfg.ipmi.remote_parameters == "-I lanplus -U admin -P secret -H 192.168.1.100", "TestIpmiConfigParsing.test_ipmi_custom_values: remote_parameters"
        assert cfg.ipmi.platform_name == "X11DPH-T", "TestIpmiConfigParsing.test_ipmi_custom_values: platform_name"

    @pytest.mark.parametrize(
        "param, value, error_str",
        [
            # Negative fan_mode_delay
            ("fan_mode_delay", "-1", "Config._parse_ipmi() n1"),
            # Negative fan_level_delay
            ("fan_level_delay", "-5", "Config._parse_ipmi() n2"),
        ],
    )
    def test_ipmi_invalid_values(self, create_config_file, param: str, value: str, error_str: str):
        """Negative test: IpmiConfig rejects invalid values."""
        config_path = create_config_file(f"[Ipmi]\n{param} = {value}\n")
        with pytest.raises(ValueError):
            Config(config_path)


class TestCpuConfigParsing:
    """Unit tests for [CPU] section parsing."""

    def test_cpu_defaults(self, create_config):
        """Positive test: CpuConfig uses correct default values."""
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\n")
        assert len(cfg.cpu) == 1, "TestCpuConfigParsing.test_cpu_defaults: one CPU section"
        cpu = cfg.cpu[0]
        assert cpu.section == "CPU", "TestCpuConfigParsing.test_cpu_defaults: section name"
        assert cpu.enabled is True, "TestCpuConfigParsing.test_cpu_defaults: enabled default"
        assert cpu.ipmi_zone == [Config.CPU_ZONE], "TestCpuConfigParsing.test_cpu_defaults: ipmi_zone default"
        assert cpu.temp_calc == Config.CALC_AVG, "TestCpuConfigParsing.test_cpu_defaults: temp_calc default"
        assert cpu.steps == Config.DV_CPU_STEPS, "TestCpuConfigParsing.test_cpu_defaults: steps default"
        assert cpu.sensitivity == Config.DV_CPU_SENSITIVITY, "TestCpuConfigParsing.test_cpu_defaults: sensitivity default"
        assert cpu.polling == Config.DV_CPU_POLLING, "TestCpuConfigParsing.test_cpu_defaults: polling default"
        assert cpu.min_temp == Config.DV_CPU_MIN_TEMP, "TestCpuConfigParsing.test_cpu_defaults: min_temp default"
        assert cpu.max_temp == Config.DV_CPU_MAX_TEMP, "TestCpuConfigParsing.test_cpu_defaults: max_temp default"
        assert cpu.min_level == Config.DV_CPU_MIN_LEVEL, "TestCpuConfigParsing.test_cpu_defaults: min_level default"
        assert cpu.max_level == Config.DV_CPU_MAX_LEVEL, "TestCpuConfigParsing.test_cpu_defaults: max_level default"
        assert cpu.smoothing == Config.DV_CPU_SMOOTHING, "TestCpuConfigParsing.test_cpu_defaults: smoothing default"

    def test_cpu_custom_values(self, create_config):
        """Positive test: CpuConfig parses custom values."""
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
        assert cpu.ipmi_zone == [0, 1], "TestCpuConfigParsing.test_cpu_custom_values: ipmi_zone"
        assert cpu.temp_calc == 2, "TestCpuConfigParsing.test_cpu_custom_values: temp_calc"
        assert cpu.steps == 8, "TestCpuConfigParsing.test_cpu_custom_values: steps"
        assert cpu.sensitivity == 2.5, "TestCpuConfigParsing.test_cpu_custom_values: sensitivity"
        assert cpu.polling == 5.0, "TestCpuConfigParsing.test_cpu_custom_values: polling"
        assert cpu.min_temp == 25.0, "TestCpuConfigParsing.test_cpu_custom_values: min_temp"
        assert cpu.max_temp == 70.0, "TestCpuConfigParsing.test_cpu_custom_values: max_temp"
        assert cpu.min_level == 30, "TestCpuConfigParsing.test_cpu_custom_values: min_level"
        assert cpu.max_level == 95, "TestCpuConfigParsing.test_cpu_custom_values: max_level"
        assert cpu.smoothing == 4, "TestCpuConfigParsing.test_cpu_custom_values: smoothing"

    def test_cpu_multi_section(self, create_config):
        """Positive test: Multiple CPU sections [CPU], [CPU:0], [CPU:1] parsed in order."""
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
        assert len(cfg.cpu) == 3, "TestCpuConfigParsing.test_cpu_multi_section: three sections parsed"
        assert cfg.cpu[0].section == "CPU", "TestCpuConfigParsing.test_cpu_multi_section: first section name"
        assert cfg.cpu[0].min_temp == 30.0, "TestCpuConfigParsing.test_cpu_multi_section: first min_temp"
        assert cfg.cpu[1].section == "CPU:0", "TestCpuConfigParsing.test_cpu_multi_section: second section name"
        assert cfg.cpu[1].min_temp == 32.0, "TestCpuConfigParsing.test_cpu_multi_section: second min_temp"
        assert cfg.cpu[2].section == "CPU:1", "TestCpuConfigParsing.test_cpu_multi_section: third section name"
        assert cfg.cpu[2].min_temp == 34.0, "TestCpuConfigParsing.test_cpu_multi_section: third min_temp"
        assert cfg.cpu[2].enabled is False, "TestCpuConfigParsing.test_cpu_multi_section: third enabled=False"

    def test_cpu_disabled(self, create_config):
        """Positive test: Disabled CPU section is still parsed."""
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 0\n")
        assert len(cfg.cpu) == 1, "TestCpuConfigParsing.test_cpu_disabled: one CPU section"
        assert cfg.cpu[0].enabled is False, "TestCpuConfigParsing.test_cpu_disabled: enabled=False"


class TestHdConfigParsing:
    """Unit tests for [HD] section parsing."""

    @pytest.mark.parametrize(
        "param, value, error_str",
        [
            # Invalid temp_calc value
            ("temp_calc", "5", "Config._validate_fan_controller_config() n1"),
            # steps = 0
            ("steps", "0", "Config._validate_fan_controller_config() n2"),
            # steps negative
            ("steps", "-1", "Config._validate_fan_controller_config() n3"),
            # steps > max_level - min_level (default max_level=100, min_level=35 -> 65)
            ("steps", "66", "Config._validate_fan_controller_config() n4"),
            # sensitivity = 0
            ("sensitivity", "0", "Config._validate_fan_controller_config() n5"),
            # sensitivity negative
            ("sensitivity", "-1", "Config._validate_fan_controller_config() n6"),
            # polling negative
            ("polling", "-1", "Config._validate_fan_controller_config() n7"),
            # smoothing = 0
            ("smoothing", "0", "Config._validate_fan_controller_config() n8"),
            # smoothing negative
            ("smoothing", "-1", "Config._validate_fan_controller_config() n9"),
            # min_temp negative
            ("min_temp", "-1", "Config._validate_fan_controller_config() n10"),
            # max_temp over 200
            ("max_temp", "201", "Config._validate_fan_controller_config() n11"),
            # min_level negative
            ("min_level", "-1", "Config._validate_fan_controller_config() n12"),
            # max_level over 100
            ("max_level", "101", "Config._validate_fan_controller_config() n13"),
        ],
    )
    def test_hd_validation_errors(self, create_config_file, param: str, value: str, error_str: str):  # noqa: ARG002
        """Negative test: HdConfig validation catches invalid parameters."""
        config_path = create_config_file(f"[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\n{param} = {value}\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_hd_max_temp_less_than_min_error(self, create_config_file):
        """Negative test: Validation catches max_temp < min_temp for HD."""
        content = "[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\nmin_temp = 50\nmax_temp = 30\n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_temp" in str(exc_info.value) and "min_temp" in str(exc_info.value)

    def test_hd_max_level_less_than_min_error(self, create_config_file):
        """Negative test: Validation catches max_level < min_level for HD."""
        content = "[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\nmin_level = 100\nmax_level = 35\n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_level" in str(exc_info.value) and "min_level" in str(exc_info.value)

    @pytest.mark.parametrize(
        "temp_calc, error_str",
        [
            # Use minimum temperature
            (0, "Config._parse_hd_sections() p1"),
            # Use average temperature
            (1, "Config._parse_hd_sections() p2"),
            # Use maximum temperature
            (2, "Config._parse_hd_sections() p3"),
        ],
    )
    def test_hd_temp_calc_all_values(self, create_config, temp_calc: int, error_str: str):
        """Positive test: All temp_calc values (0=MIN, 1=AVG, 2=MAX) are valid for HD."""
        cfg = create_config(f"[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\ntemp_calc = {temp_calc}\n")
        assert cfg.hd[0].temp_calc == temp_calc, error_str

    def test_hd_defaults(self, create_config):
        """Positive test: HdConfig uses correct default values when enabled with hd_names."""
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\n")
        assert len(cfg.hd) == 1, "TestHdConfigParsing.test_hd_defaults: one HD section"
        hd = cfg.hd[0]
        assert hd.section == "HD", "TestHdConfigParsing.test_hd_defaults: section name"
        assert hd.enabled is True, "TestHdConfigParsing.test_hd_defaults: enabled default"
        assert hd.ipmi_zone == [Config.HD_ZONE], "TestHdConfigParsing.test_hd_defaults: ipmi_zone default"
        assert hd.temp_calc == Config.CALC_AVG, "TestHdConfigParsing.test_hd_defaults: temp_calc default"
        assert hd.steps == Config.DV_HD_STEPS, "TestHdConfigParsing.test_hd_defaults: steps default"
        assert hd.sensitivity == Config.DV_HD_SENSITIVITY, "TestHdConfigParsing.test_hd_defaults: sensitivity default"
        assert hd.polling == Config.DV_HD_POLLING, "TestHdConfigParsing.test_hd_defaults: polling default"
        assert hd.min_temp == Config.DV_HD_MIN_TEMP, "TestHdConfigParsing.test_hd_defaults: min_temp default"
        assert hd.max_temp == Config.DV_HD_MAX_TEMP, "TestHdConfigParsing.test_hd_defaults: max_temp default"
        assert hd.min_level == Config.DV_HD_MIN_LEVEL, "TestHdConfigParsing.test_hd_defaults: min_level default"
        assert hd.max_level == Config.DV_HD_MAX_LEVEL, "TestHdConfigParsing.test_hd_defaults: max_level default"
        assert hd.smoothing == Config.DV_HD_SMOOTHING, "TestHdConfigParsing.test_hd_defaults: smoothing default"
        assert hd.hd_names == ["/dev/sda"], "TestHdConfigParsing.test_hd_defaults: hd_names"
        assert hd.smartctl_path == Config.DV_HD_SMARTCTL_PATH, "TestHdConfigParsing.test_hd_defaults: smartctl_path default"
        assert hd.standby_guard_enabled is False, "TestHdConfigParsing.test_hd_defaults: standby_guard_enabled default"
        assert hd.standby_hd_limit == Config.DV_HD_STANDBY_HD_LIMIT, "TestHdConfigParsing.test_hd_defaults: standby_hd_limit default"

    def test_hd_multi_names_newline(self, create_config):
        """Positive test: HdConfig parses multiple device names with newlines."""
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\n    /dev/sdb\n    /dev/sdc\n")
        assert cfg.hd[0].hd_names == ["/dev/sda", "/dev/sdb", "/dev/sdc"], "TestHdConfigParsing.test_hd_multi_names_newline: hd_names"

    def test_hd_multi_names_space(self, create_config):
        """Positive test: HdConfig parses multiple device names with spaces."""
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda /dev/sdb /dev/sdc\n")
        assert cfg.hd[0].hd_names == ["/dev/sda", "/dev/sdb", "/dev/sdc"], "TestHdConfigParsing.test_hd_multi_names_space: hd_names"

    def test_hd_standby_guard(self, create_config):
        """Positive test: HdConfig parses standby guard settings."""
        cfg = create_config("""
[Ipmi]
[HD]
enabled = 1
hd_names = /dev/sda /dev/sdb
standby_guard_enabled = 1
standby_hd_limit = 2
""")
        assert cfg.hd[0].standby_guard_enabled is True, "TestHdConfigParsing.test_hd_standby_guard: standby_guard_enabled"
        assert cfg.hd[0].standby_hd_limit == 2, "TestHdConfigParsing.test_hd_standby_guard: standby_hd_limit"

    def test_hd_enabled_without_names_error(self, create_config_file):
        """Negative test: HdConfig raises error when enabled but hd_names not specified."""
        config_path = create_config_file("[Ipmi]\n[HD]\nenabled = 1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "hd_names" in str(exc_info.value)

    def test_hd_nvme_in_names_error(self, create_config_file):
        """Negative test: HdConfig raises error when NVMe device in hd_names."""
        config_path = create_config_file("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/nvme0n1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "NVMe" in str(exc_info.value)

    def test_hd_standby_limit_negative_error(self, create_config_file):
        """Negative test: HdConfig raises error for negative standby_hd_limit."""
        content = ("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\n"
                   "standby_guard_enabled = 1\nstandby_hd_limit = -1\n")
        config_path = create_config_file(content)
        with pytest.raises(ValueError):
            Config(config_path)

    def test_hd_empty_smartctl_path_error(self, create_config_file):
        """Negative test: HdConfig raises error for empty smartctl_path when enabled."""
        content = "[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\nsmartctl_path = \n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "smartctl_path" in str(exc_info.value)

    def test_hd_multi_section(self, create_config):
        """Positive test: Multiple HD sections parsed correctly."""
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
        assert len(cfg.hd) == 2, "TestHdConfigParsing.test_hd_multi_section: two sections parsed"
        assert cfg.hd[0].section == "HD", "TestHdConfigParsing.test_hd_multi_section: first section name"
        assert cfg.hd[0].ipmi_zone == [1], "TestHdConfigParsing.test_hd_multi_section: first ipmi_zone"
        assert cfg.hd[1].section == "HD:0", "TestHdConfigParsing.test_hd_multi_section: second section name"
        assert cfg.hd[1].ipmi_zone == [2], "TestHdConfigParsing.test_hd_multi_section: second ipmi_zone"


class TestNvmeConfigParsing:
    """Unit tests for [NVME] section parsing."""

    @pytest.mark.parametrize(
        "param, value, error_str",
        [
            # Invalid temp_calc value
            ("temp_calc", "5", "Config._validate_fan_controller_config() n14"),
            # steps = 0
            ("steps", "0", "Config._validate_fan_controller_config() n15"),
            # steps negative
            ("steps", "-1", "Config._validate_fan_controller_config() n16"),
            # steps > max_level - min_level (default max_level=100, min_level=35 -> 65)
            ("steps", "66", "Config._validate_fan_controller_config() n17"),
            # sensitivity = 0
            ("sensitivity", "0", "Config._validate_fan_controller_config() n18"),
            # sensitivity negative
            ("sensitivity", "-1", "Config._validate_fan_controller_config() n19"),
            # polling negative
            ("polling", "-1", "Config._validate_fan_controller_config() n20"),
            # smoothing = 0
            ("smoothing", "0", "Config._validate_fan_controller_config() n21"),
            # smoothing negative
            ("smoothing", "-1", "Config._validate_fan_controller_config() n22"),
            # min_temp negative
            ("min_temp", "-1", "Config._validate_fan_controller_config() n23"),
            # max_temp over 200
            ("max_temp", "201", "Config._validate_fan_controller_config() n24"),
            # min_level negative
            ("min_level", "-1", "Config._validate_fan_controller_config() n25"),
            # max_level over 100
            ("max_level", "101", "Config._validate_fan_controller_config() n26"),
        ],
    )
    def test_nvme_validation_errors(self, create_config_file, param: str, value: str, error_str: str):  # noqa: ARG002
        """Negative test: NvmeConfig validation catches invalid parameters."""
        config_path = create_config_file(f"[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\n{param} = {value}\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_nvme_max_temp_less_than_min_error(self, create_config_file):
        """Negative test: Validation catches max_temp < min_temp for NVME."""
        config_path = create_config_file(
            "[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\nmin_temp = 80\nmax_temp = 40\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_temp" in str(exc_info.value) and "min_temp" in str(exc_info.value)

    def test_nvme_max_level_less_than_min_error(self, create_config_file):
        """Negative test: Validation catches max_level < min_level for NVME."""
        config_path = create_config_file(
            "[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\nmin_level = 100\nmax_level = 35\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_level" in str(exc_info.value) and "min_level" in str(exc_info.value)

    @pytest.mark.parametrize(
        "temp_calc, error_str",
        [
            # Use minimum temperature
            (0, "Config._parse_nvme_sections() p1"),
            # Use average temperature
            (1, "Config._parse_nvme_sections() p2"),
            # Use maximum temperature
            (2, "Config._parse_nvme_sections() p3"),
        ],
    )
    def test_nvme_temp_calc_all_values(self, create_config, temp_calc: int, error_str: str):
        """Positive test: All temp_calc values (0=MIN, 1=AVG, 2=MAX) are valid for NVME."""
        cfg = create_config(f"[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\ntemp_calc = {temp_calc}\n")
        assert cfg.nvme[0].temp_calc == temp_calc, error_str

    def test_nvme_defaults(self, create_config):
        """Positive test: NvmeConfig uses correct default values."""
        cfg = create_config("[Ipmi]\n[NVME]\nenabled = 1\nnvme_names = /dev/nvme0n1\n")
        assert len(cfg.nvme) == 1, "TestNvmeConfigParsing.test_nvme_defaults: one NVME section"
        nvme = cfg.nvme[0]
        assert nvme.section == "NVME", "TestNvmeConfigParsing.test_nvme_defaults: section name"
        assert nvme.enabled is True, "TestNvmeConfigParsing.test_nvme_defaults: enabled default"
        assert nvme.ipmi_zone == [Config.HD_ZONE], "TestNvmeConfigParsing.test_nvme_defaults: ipmi_zone default"
        assert nvme.min_temp == Config.DV_NVME_MIN_TEMP, "TestNvmeConfigParsing.test_nvme_defaults: min_temp default"
        assert nvme.max_temp == Config.DV_NVME_MAX_TEMP, "TestNvmeConfigParsing.test_nvme_defaults: max_temp default"
        assert nvme.nvme_names == ["/dev/nvme0n1"], "TestNvmeConfigParsing.test_nvme_defaults: nvme_names"

    def test_nvme_enabled_without_names_error(self, create_config_file):
        """Negative test: NvmeConfig raises error when enabled but nvme_names not specified."""
        config_path = create_config_file("[Ipmi]\n[NVME]\nenabled = 1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "nvme_names" in str(exc_info.value)

    def test_nvme_multi_section(self, create_config):
        """Positive test: Multiple NVME sections parsed correctly."""
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
        assert len(cfg.nvme) == 2, "TestNvmeConfigParsing.test_nvme_multi_section: two sections parsed"
        assert cfg.nvme[0].section == "NVME", "TestNvmeConfigParsing.test_nvme_multi_section: first section name"
        assert cfg.nvme[1].section == "NVME:0", "TestNvmeConfigParsing.test_nvme_multi_section: second section name"


class TestGpuConfigParsing:
    """Unit tests for [GPU] section parsing."""

    @pytest.mark.parametrize(
        "param, value, error_str",
        [
            # Invalid temp_calc value
            ("temp_calc", "5", "Config._validate_fan_controller_config() n27"),
            # steps = 0
            ("steps", "0", "Config._validate_fan_controller_config() n28"),
            # steps negative
            ("steps", "-1", "Config._validate_fan_controller_config() n29"),
            # steps > max_level - min_level (default max_level=100, min_level=35 -> 65)
            ("steps", "66", "Config._validate_fan_controller_config() n30"),
            # sensitivity = 0
            ("sensitivity", "0", "Config._validate_fan_controller_config() n31"),
            # sensitivity negative
            ("sensitivity", "-1", "Config._validate_fan_controller_config() n32"),
            # polling negative
            ("polling", "-1", "Config._validate_fan_controller_config() n33"),
            # smoothing = 0
            ("smoothing", "0", "Config._validate_fan_controller_config() n34"),
            # smoothing negative
            ("smoothing", "-1", "Config._validate_fan_controller_config() n35"),
            # min_temp negative
            ("min_temp", "-1", "Config._validate_fan_controller_config() n36"),
            # max_temp over 200
            ("max_temp", "201", "Config._validate_fan_controller_config() n37"),
            # min_level negative
            ("min_level", "-1", "Config._validate_fan_controller_config() n38"),
            # max_level over 100
            ("max_level", "101", "Config._validate_fan_controller_config() n39"),
        ],
    )
    def test_gpu_validation_errors(self, create_config_file, param: str, value: str, error_str: str):  # noqa: ARG002
        """Negative test: GpuConfig validation catches invalid parameters."""
        config_path = create_config_file(f"[Ipmi]\n[GPU]\nenabled = 1\n{param} = {value}\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_gpu_max_temp_less_than_min_error(self, create_config_file):
        """Negative test: Validation catches max_temp < min_temp for GPU."""
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\nmin_temp = 80\nmax_temp = 40\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_temp" in str(exc_info.value) and "min_temp" in str(exc_info.value)

    def test_gpu_max_level_less_than_min_error(self, create_config_file):
        """Negative test: Validation catches max_level < min_level for GPU."""
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\nmin_level = 100\nmax_level = 35\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_level" in str(exc_info.value) and "min_level" in str(exc_info.value)

    @pytest.mark.parametrize(
        "temp_calc, error_str",
        [
            # Use minimum temperature
            (0, "Config._parse_gpu_sections() p1"),
            # Use average temperature
            (1, "Config._parse_gpu_sections() p2"),
            # Use maximum temperature
            (2, "Config._parse_gpu_sections() p3"),
        ],
    )
    def test_gpu_temp_calc_all_values(self, create_config, temp_calc: int, error_str: str):
        """Positive test: All temp_calc values (0=MIN, 1=AVG, 2=MAX) are valid for GPU."""
        cfg = create_config(f"[Ipmi]\n[GPU]\nenabled = 1\ntemp_calc = {temp_calc}\n")
        assert cfg.gpu[0].temp_calc == temp_calc, error_str

    def test_gpu_defaults_nvidia(self, create_config):
        """Positive test: GpuConfig uses correct default values for NVIDIA."""
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\n")
        assert len(cfg.gpu) == 1, "TestGpuConfigParsing.test_gpu_defaults_nvidia: one GPU section"
        gpu = cfg.gpu[0]
        assert gpu.section == "GPU", "TestGpuConfigParsing.test_gpu_defaults_nvidia: section name"
        assert gpu.enabled is True, "TestGpuConfigParsing.test_gpu_defaults_nvidia: enabled default"
        assert gpu.gpu_type == Config.DV_GPU_TYPE, "TestGpuConfigParsing.test_gpu_defaults_nvidia: gpu_type default"
        assert gpu.gpu_device_ids == Config.parse_gpu_ids(Config.DV_GPU_DEVICE_IDS), "TestGpuConfigParsing.test_gpu_defaults_nvidia: gpu_device_ids default"
        assert gpu.nvidia_smi_path == Config.DV_GPU_NVIDIA_SMI_PATH, "TestGpuConfigParsing.test_gpu_defaults_nvidia: nvidia_smi_path default"
        assert gpu.rocm_smi_path == Config.DV_GPU_ROCM_SMI_PATH, "TestGpuConfigParsing.test_gpu_defaults_nvidia: rocm_smi_path default"
        assert gpu.amd_temp_sensor == Config.DV_GPU_AMD_TEMP_SENSOR, "TestGpuConfigParsing.test_gpu_defaults_nvidia: amd_temp_sensor default"
        assert gpu.min_temp == Config.DV_GPU_MIN_TEMP, "TestGpuConfigParsing.test_gpu_defaults_nvidia: min_temp default"
        assert gpu.max_temp == Config.DV_GPU_MAX_TEMP, "TestGpuConfigParsing.test_gpu_defaults_nvidia: max_temp default"

    def test_gpu_amd_type(self, create_config):
        """Positive test: GpuConfig parses AMD GPU type."""
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = amd\namd_temp_sensor = 1\n")
        assert cfg.gpu[0].gpu_type == "amd", "TestGpuConfigParsing.test_gpu_amd_type: gpu_type=amd"
        assert cfg.gpu[0].amd_temp_sensor == 1, "TestGpuConfigParsing.test_gpu_amd_type: amd_temp_sensor"

    def test_gpu_multiple_ids(self, create_config):
        """Positive test: GpuConfig parses multiple GPU device IDs."""
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\ngpu_device_ids = 0, 1, 2\n")
        assert cfg.gpu[0].gpu_device_ids == [0, 1, 2], "TestGpuConfigParsing.test_gpu_multiple_ids: gpu_device_ids"

    def test_gpu_invalid_type_error(self, create_config_file):
        """Negative test: GpuConfig raises error for invalid gpu_type."""
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = intel\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "gpu_type" in str(exc_info.value)

    def test_gpu_invalid_amd_sensor_error(self, create_config_file):
        """Negative test: GpuConfig raises error for invalid amd_temp_sensor."""
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = amd\namd_temp_sensor = 5\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "amd_temp_sensor" in str(exc_info.value)

    def test_gpu_empty_nvidia_smi_path_error(self, create_config_file):
        """Negative test: GpuConfig raises error for empty nvidia_smi_path when nvidia enabled."""
        content = "[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = nvidia\nnvidia_smi_path = \n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "nvidia_smi_path" in str(exc_info.value)

    def test_gpu_empty_rocm_smi_path_error(self, create_config_file):
        """Negative test: GpuConfig raises error for empty rocm_smi_path when amd enabled."""
        content = "[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = amd\nrocm_smi_path = \n"
        config_path = create_config_file(content)
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "rocm_smi_path" in str(exc_info.value)

    def test_gpu_multi_section(self, create_config):
        """Positive test: Multiple GPU sections parsed correctly."""
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
        assert len(cfg.gpu) == 2, "TestGpuConfigParsing.test_gpu_multi_section: two sections parsed"
        assert cfg.gpu[0].gpu_type == "nvidia", "TestGpuConfigParsing.test_gpu_multi_section: first gpu_type"
        assert cfg.gpu[1].gpu_type == "amd", "TestGpuConfigParsing.test_gpu_multi_section: second gpu_type"


class TestConstConfigParsing:
    """Unit tests for [CONST] section parsing."""

    def test_const_defaults(self, create_config):
        """Positive test: ConstConfig uses correct default values."""
        cfg = create_config("[Ipmi]\n[CONST]\nenabled = 1\n")
        assert len(cfg.const) == 1, "TestConstConfigParsing.test_const_defaults: one CONST section"
        const = cfg.const[0]
        assert const.section == "CONST", "TestConstConfigParsing.test_const_defaults: section name"
        assert const.enabled is True, "TestConstConfigParsing.test_const_defaults: enabled default"
        assert const.ipmi_zone == [Config.HD_ZONE], "TestConstConfigParsing.test_const_defaults: ipmi_zone default"
        assert const.polling == Config.DV_CONST_POLLING, "TestConstConfigParsing.test_const_defaults: polling default"
        assert const.level == Config.DV_CONST_LEVEL, "TestConstConfigParsing.test_const_defaults: level default"

    def test_const_custom_values(self, create_config):
        """Positive test: ConstConfig parses custom values."""
        cfg = create_config("[Ipmi]\n[CONST]\nenabled = 1\nipmi_zone = 0, 1\npolling = 60\nlevel = 75\n")
        const = cfg.const[0]
        assert const.ipmi_zone == [0, 1], "TestConstConfigParsing.test_const_custom_values: ipmi_zone"
        assert const.polling == 60.0, "TestConstConfigParsing.test_const_custom_values: polling"
        assert const.level == 75, "TestConstConfigParsing.test_const_custom_values: level"

    def test_const_invalid_level_error(self, create_config_file):
        """Negative test: ConstConfig raises error for invalid level."""
        config_path = create_config_file("[Ipmi]\n[CONST]\nenabled = 1\nlevel = 150\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "level" in str(exc_info.value)

    def test_const_negative_polling_error(self, create_config_file):
        """Negative test: ConstConfig raises error for negative polling."""
        config_path = create_config_file("[Ipmi]\n[CONST]\nenabled = 1\npolling = -1\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_const_multi_section(self, create_config):
        """Positive test: Multiple CONST sections parsed correctly."""
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
        assert len(cfg.const) == 2, "TestConstConfigParsing.test_const_multi_section: two sections parsed"
        assert cfg.const[0].level == 40, "TestConstConfigParsing.test_const_multi_section: first level"
        assert cfg.const[1].level == 60, "TestConstConfigParsing.test_const_multi_section: second level"


class TestFanControllerValidation:
    """Unit tests for _validate_fan_controller_config() validation logic."""

    @pytest.mark.parametrize(
        "param, value, error_str",
        [
            # Invalid temp_calc value
            ("temp_calc", "5", "Config._validate_fan_controller_config() n40"),
            # steps = 0
            ("steps", "0", "Config._validate_fan_controller_config() n41"),
            # steps negative
            ("steps", "-1", "Config._validate_fan_controller_config() n42"),
            # steps > max_level - min_level (default max_level=100, min_level=35 -> 65)
            ("steps", "66", "Config._validate_fan_controller_config() n43"),
            # sensitivity = 0
            ("sensitivity", "0", "Config._validate_fan_controller_config() n44"),
            # sensitivity negative
            ("sensitivity", "-1", "Config._validate_fan_controller_config() n45"),
            # polling negative
            ("polling", "-1", "Config._validate_fan_controller_config() n46"),
            # smoothing = 0
            ("smoothing", "0", "Config._validate_fan_controller_config() n47"),
            # smoothing negative
            ("smoothing", "-1", "Config._validate_fan_controller_config() n48"),
            # min_temp negative
            ("min_temp", "-1", "Config._validate_fan_controller_config() n49"),
            # max_temp over 200
            ("max_temp", "201", "Config._validate_fan_controller_config() n50"),
            # min_level negative
            ("min_level", "-1", "Config._validate_fan_controller_config() n51"),
            # max_level over 100
            ("max_level", "101", "Config._validate_fan_controller_config() n52"),
        ],
    )
    def test_cpu_validation_errors(self, create_config_file, param: str, value: str, error_str: str):  # noqa: ARG002
        """Negative test: CpuConfig validation catches invalid parameters."""
        config_path = create_config_file(f"[Ipmi]\n[CPU]\nenabled = 1\n{param} = {value}\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_cpu_max_temp_less_than_min_error(self, create_config_file):
        """Negative test: Validation catches max_temp < min_temp."""
        config_path = create_config_file("[Ipmi]\n[CPU]\nenabled = 1\nmin_temp = 60\nmax_temp = 30\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_temp" in str(exc_info.value) and "min_temp" in str(exc_info.value)

    def test_cpu_max_level_less_than_min_error(self, create_config_file):
        """Negative test: Validation catches max_level < min_level."""
        config_path = create_config_file("[Ipmi]\n[CPU]\nenabled = 1\nmin_level = 100\nmax_level = 35\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "max_level" in str(exc_info.value) and "min_level" in str(exc_info.value)


class TestConfigConstants:
    """Unit tests for Config class constants."""

    def test_section_name_constants(self):
        """Verify Config section name constants."""
        assert Config.CS_IPMI == "Ipmi", "TestConfigConstants.test_section_name_constants: CS_IPMI"
        assert Config.CS_CPU == "CPU", "TestConfigConstants.test_section_name_constants: CS_CPU"
        assert Config.CS_HD == "HD", "TestConfigConstants.test_section_name_constants: CS_HD"
        assert Config.CS_NVME == "NVME", "TestConfigConstants.test_section_name_constants: CS_NVME"
        assert Config.CS_GPU == "GPU", "TestConfigConstants.test_section_name_constants: CS_GPU"
        assert Config.CS_CONST == "CONST", "TestConfigConstants.test_section_name_constants: CS_CONST"

    def test_calc_constants(self):
        """Verify Config calculation method constants."""
        assert Config.CALC_MIN == 0, "TestConfigConstants.test_calc_constants: CALC_MIN"
        assert Config.CALC_AVG == 1, "TestConfigConstants.test_calc_constants: CALC_AVG"
        assert Config.CALC_MAX == 2, "TestConfigConstants.test_calc_constants: CALC_MAX"

    def test_zone_constants(self):
        """Verify Config zone constants."""
        assert Config.CPU_ZONE == 0, "TestConfigConstants.test_zone_constants: CPU_ZONE"
        assert Config.HD_ZONE == 1, "TestConfigConstants.test_zone_constants: HD_ZONE"

    def test_amd_temp_keys(self):
        """Verify Config AMD temperature sensor keys."""
        assert len(Config.CV_AMD_TEMP_KEYS) == 3, "TestConfigConstants.test_amd_temp_keys: three keys"
        assert "junction" in Config.CV_AMD_TEMP_KEYS[0].lower(), "TestConfigConstants.test_amd_temp_keys: key[0] is junction"
        assert "edge" in Config.CV_AMD_TEMP_KEYS[1].lower(), "TestConfigConstants.test_amd_temp_keys: key[1] is edge"
        assert "memory" in Config.CV_AMD_TEMP_KEYS[2].lower(), "TestConfigConstants.test_amd_temp_keys: key[2] is memory"


class TestEdgeCases:
    """Unit tests for edge cases and additional coverage."""

    def test_hd_disabled_without_names(self, create_config):
        """Positive test: HD disabled without hd_names should not raise error."""
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 0\n")
        assert len(cfg.hd) == 1, "TestEdgeCases.test_hd_disabled_without_names: one HD section"
        assert cfg.hd[0].enabled is False, "TestEdgeCases.test_hd_disabled_without_names: enabled=False"
        assert cfg.hd[0].hd_names == [], "TestEdgeCases.test_hd_disabled_without_names: hd_names empty"

    def test_nvme_disabled_without_names(self, create_config):
        """Positive test: NVME disabled without nvme_names should not raise error."""
        cfg = create_config("[Ipmi]\n[NVME]\nenabled = 0\n")
        assert len(cfg.nvme) == 1, "TestEdgeCases.test_nvme_disabled_without_names: one NVME section"
        assert cfg.nvme[0].enabled is False, "TestEdgeCases.test_nvme_disabled_without_names: enabled=False"
        assert cfg.nvme[0].nvme_names == [], "TestEdgeCases.test_nvme_disabled_without_names: nvme_names empty"

    def test_hd_custom_smartctl_path(self, create_config):
        """Positive test: HdConfig parses custom smartctl_path."""
        cfg = create_config("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/sda\nsmartctl_path = /opt/smartctl\n")
        assert cfg.hd[0].smartctl_path == "/opt/smartctl", "TestEdgeCases.test_hd_custom_smartctl_path: smartctl_path"

    def test_gpu_custom_nvidia_path(self, create_config):
        """Positive test: GpuConfig parses custom nvidia_smi_path."""
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\nnvidia_smi_path = /opt/nvidia-smi\n")
        assert cfg.gpu[0].nvidia_smi_path == "/opt/nvidia-smi", "TestEdgeCases.test_gpu_custom_nvidia_path: nvidia_smi_path"

    def test_gpu_custom_rocm_path(self, create_config):
        """Positive test: GpuConfig parses custom rocm_smi_path."""
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = amd\nrocm_smi_path = /opt/rocm-smi\n")
        assert cfg.gpu[0].rocm_smi_path == "/opt/rocm-smi", "TestEdgeCases.test_gpu_custom_rocm_path: rocm_smi_path"

    @pytest.mark.parametrize(
        "temp_calc, error_str",
        [
            # Use minimum temperature
            (0, "Config._parse_cpu_sections() p1"),
            # Use average temperature
            (1, "Config._parse_cpu_sections() p2"),
            # Use maximum temperature
            (2, "Config._parse_cpu_sections() p3"),
        ],
    )
    def test_cpu_temp_calc_all_values(self, create_config, temp_calc: int, error_str: str):
        """Positive test: All temp_calc values (0=MIN, 1=AVG, 2=MAX) are valid."""
        cfg = create_config(f"[Ipmi]\n[CPU]\nenabled = 1\ntemp_calc = {temp_calc}\n")
        assert cfg.cpu[0].temp_calc == temp_calc, error_str

    def test_cpu_polling_zero(self, create_config):
        """Positive test: polling = 0 is valid (immediate polling)."""
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\npolling = 0\n")
        assert cfg.cpu[0].polling == 0.0, "TestEdgeCases.test_cpu_polling_zero: polling=0.0"

    def test_const_level_boundary_zero(self, create_config_file):
        """Negative test: CONST level = 0 is invalid (fans off is not allowed)."""
        config_path = create_config_file("[Ipmi]\n[CONST]\nenabled = 1\nlevel = 0\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "level" in str(exc_info.value)

    def test_const_level_boundary_one(self, create_config):
        """Positive test: CONST level = 1 is valid (minimum allowed)."""
        cfg = create_config("[Ipmi]\n[CONST]\nenabled = 1\nlevel = 1\n")
        assert cfg.const[0].level == 1, "TestEdgeCases.test_const_level_boundary_one: level=1"

    def test_const_level_boundary_hundred(self, create_config):
        """Positive test: CONST level = 100 is valid."""
        cfg = create_config("[Ipmi]\n[CONST]\nenabled = 1\nlevel = 100\n")
        assert cfg.const[0].level == 100, "TestEdgeCases.test_const_level_boundary_hundred: level=100"

    def test_ipmi_zone_boundary_zero(self, create_config):
        """Positive test: ipmi_zone = 0 is valid."""
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = 0\n")
        assert cfg.cpu[0].ipmi_zone == [0], "TestEdgeCases.test_ipmi_zone_boundary_zero: ipmi_zone=[0]"

    def test_ipmi_zone_boundary_hundred(self, create_config):
        """Positive test: ipmi_zone = 100 is valid."""
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = 100\n")
        assert cfg.cpu[0].ipmi_zone == [100], "TestEdgeCases.test_ipmi_zone_boundary_hundred: ipmi_zone=[100]"

    def test_min_equals_max_temp(self, create_config):
        """Positive test: min_temp == max_temp is valid (constant temperature mapping)."""
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nmin_temp = 40\nmax_temp = 40\n")
        assert cfg.cpu[0].min_temp == 40.0, "TestEdgeCases.test_min_equals_max_temp: min_temp=40.0"
        assert cfg.cpu[0].max_temp == 40.0, "TestEdgeCases.test_min_equals_max_temp: max_temp=40.0"

    def test_min_equals_max_level(self, create_config):
        """Positive test: min_level == max_level is valid (constant fan level)."""
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nmin_level = 50\nmax_level = 50\n")
        assert cfg.cpu[0].min_level == 50, "TestEdgeCases.test_min_equals_max_level: min_level=50"
        assert cfg.cpu[0].max_level == 50, "TestEdgeCases.test_min_equals_max_level: max_level=50"

    def test_hd_nvme_mixed_case_detection(self, create_config_file):
        """Negative test: NVMe detection is case-insensitive."""
        config_path = create_config_file("[Ipmi]\n[HD]\nenabled = 1\nhd_names = /dev/NVME0N1\n")
        with pytest.raises(ValueError) as exc_info:
            Config(config_path)
        assert "NVMe" in str(exc_info.value)

    def test_gpu_type_case_insensitive(self, create_config):
        """Positive test: gpu_type is case-insensitive."""
        cfg = create_config("[Ipmi]\n[GPU]\nenabled = 1\ngpu_type = NVIDIA\n")
        assert cfg.gpu[0].gpu_type == "nvidia", "TestEdgeCases.test_gpu_type_case_insensitive: gpu_type normalized to lowercase"

    def test_no_controller_sections(self, create_config):
        """Positive test: Config with only [Ipmi] section is valid."""
        cfg = create_config("[Ipmi]\ncommand = /usr/bin/ipmitool\n")
        assert cfg.cpu == [], "TestEdgeCases.test_no_controller_sections: no cpu sections"
        assert cfg.hd == [], "TestEdgeCases.test_no_controller_sections: no hd sections"
        assert cfg.nvme == [], "TestEdgeCases.test_no_controller_sections: no nvme sections"
        assert cfg.gpu == [], "TestEdgeCases.test_no_controller_sections: no gpu sections"
        assert cfg.const == [], "TestEdgeCases.test_no_controller_sections: no const sections"

    def test_numbered_sections_only(self, create_config):
        """Positive test: Only numbered sections without base section."""
        cfg = create_config("[Ipmi]\n[CPU:0]\nenabled = 1\n[CPU:1]\nenabled = 0\n")
        assert len(cfg.cpu) == 2, "TestEdgeCases.test_numbered_sections_only: two CPU sections"
        assert cfg.cpu[0].section == "CPU:0", "TestEdgeCases.test_numbered_sections_only: first section name"
        assert cfg.cpu[1].section == "CPU:1", "TestEdgeCases.test_numbered_sections_only: second section name"

    def test_unordered_numbered_sections_sorted(self, create_config):
        """Positive test: Unordered numbered sections are sorted correctly."""
        cfg = create_config("[Ipmi]\n[HD:5]\nenabled = 0\n[HD:1]\nenabled = 0\n[HD:3]\nenabled = 0\n")
        assert len(cfg.hd) == 3, "TestEdgeCases.test_unordered_numbered_sections_sorted: three HD sections"
        assert cfg.hd[0].section == "HD:1", "TestEdgeCases.test_unordered_numbered_sections_sorted: first section HD:1"
        assert cfg.hd[1].section == "HD:3", "TestEdgeCases.test_unordered_numbered_sections_sorted: second section HD:3"
        assert cfg.hd[2].section == "HD:5", "TestEdgeCases.test_unordered_numbered_sections_sorted: third section HD:5"

    def test_const_level_negative_error(self, create_config_file):
        """Negative test: CONST level = -1 raises ValueError."""
        config_path = create_config_file("[Ipmi]\n[CONST]\nenabled = 1\nlevel = -1\n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_gpu_device_ids_empty_string_error(self, create_config_file):
        """Negative test: Empty gpu_device_ids string raises error."""
        config_path = create_config_file("[Ipmi]\n[GPU]\nenabled = 1\ngpu_device_ids = \n")
        with pytest.raises(ValueError):
            Config(config_path)

    def test_gpu_device_ids_many(self, create_config):
        """Positive test: Many GPU device IDs are valid."""
        ids = ", ".join(str(i) for i in range(10))
        cfg = create_config(f"[Ipmi]\n[GPU]\nenabled = 1\ngpu_device_ids = {ids}\n")
        assert cfg.gpu[0].gpu_device_ids == list(range(10)), "TestEdgeCases.test_gpu_device_ids_many: gpu_device_ids 0-9"

    def test_multi_zone_duplicates(self, create_config):
        """Positive test: Duplicate zones in ipmi_zone are preserved."""
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = 0, 0, 1, 1\n")
        assert cfg.cpu[0].ipmi_zone == [0, 0, 1, 1], "TestEdgeCases.test_multi_zone_duplicates: duplicate zones preserved"

    def test_multi_zone_many(self, create_config):
        """Positive test: Many zones in ipmi_zone are valid."""
        zones = ", ".join(str(i) for i in range(10))
        cfg = create_config(f"[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = {zones}\n")
        assert cfg.cpu[0].ipmi_zone == list(range(10)), "TestEdgeCases.test_multi_zone_many: zones 0-9"


class TestConfigFullIntegration:
    """Integration tests for full configuration scenarios."""

    def test_full_config_all_controllers(self, create_config):
        """Positive test: Full configuration with all controller types."""
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
        assert cfg.ipmi.command == "/usr/bin/ipmitool", "TestConfigFullIntegration.test_full_config_all_controllers: ipmi command"
        assert len(cfg.cpu) == 1, "TestConfigFullIntegration.test_full_config_all_controllers: one CPU section"
        assert cfg.cpu[0].enabled is True, "TestConfigFullIntegration.test_full_config_all_controllers: CPU enabled"
        assert len(cfg.hd) == 1, "TestConfigFullIntegration.test_full_config_all_controllers: one HD section"
        assert len(cfg.hd[0].hd_names) == 2, "TestConfigFullIntegration.test_full_config_all_controllers: two HD names"
        assert len(cfg.nvme) == 1, "TestConfigFullIntegration.test_full_config_all_controllers: one NVME section"
        assert len(cfg.gpu) == 1, "TestConfigFullIntegration.test_full_config_all_controllers: one GPU section"
        assert cfg.gpu[0].gpu_device_ids == [0, 1], "TestConfigFullIntegration.test_full_config_all_controllers: gpu_device_ids"
        assert len(cfg.const) == 1, "TestConfigFullIntegration.test_full_config_all_controllers: one CONST section"
        assert cfg.const[0].level == 40, "TestConfigFullIntegration.test_full_config_all_controllers: const level=40"

    def test_multi_section_ordering(self, create_config):
        """Positive test: Multi-section ordering is preserved correctly."""
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
        assert len(cfg.cpu) == 4, "TestConfigFullIntegration.test_multi_section_ordering: four CPU sections"
        assert cfg.cpu[0].section == "CPU", "TestConfigFullIntegration.test_multi_section_ordering: first section CPU"
        assert cfg.cpu[1].section == "CPU:0", "TestConfigFullIntegration.test_multi_section_ordering: second section CPU:0"
        assert cfg.cpu[2].section == "CPU:1", "TestConfigFullIntegration.test_multi_section_ordering: third section CPU:1"
        assert cfg.cpu[3].section == "CPU:2", "TestConfigFullIntegration.test_multi_section_ordering: fourth section CPU:2"


class TestDuplicateZoneValidation:
    """Unit tests for _validate_no_duplicate_zones() validation logic."""

    def test_cpu_duplicate_zone_raises(self, create_config):
        """Negative test: Two enabled CPU instances on the same IPMI zone raises ValueError."""
        with pytest.raises(ValueError, match=r"\[CPU:1\] IPMI zone 0 is already used by \[CPU:0\]"):
            create_config("[Ipmi]\n[CPU:0]\nenabled = 1\nipmi_zone = 0\n[CPU:1]\nenabled = 1\nipmi_zone = 0\n")

    def test_hd_duplicate_zone_raises(self, create_config):
        """Negative test: Two enabled HD instances on the same IPMI zone raises ValueError."""
        with pytest.raises(ValueError, match=r"\[HD:1\] IPMI zone 1 is already used by \[HD\]"):
            create_config("[Ipmi]\n[HD]\nenabled = 1\nipmi_zone = 1\nhd_names = /dev/sda\n"
                         "[HD:1]\nenabled = 1\nipmi_zone = 1\nhd_names = /dev/sdb\n")

    def test_disabled_instance_no_conflict(self, create_config):
        """Positive test: Disabled instance on the same zone does not raise."""
        cfg = create_config("[Ipmi]\n[CPU]\nenabled = 1\nipmi_zone = 0\n[CPU:1]\nenabled = 0\nipmi_zone = 0\n")
        assert len(cfg.cpu) == 2, "TestDuplicateZoneValidation.test_disabled_instance_no_conflict: two CPU sections"

    def test_different_zones_no_conflict(self, create_config):
        """Positive test: Enabled instances on different zones is valid."""
        cfg = create_config("[Ipmi]\n[CPU:0]\nenabled = 1\nipmi_zone = 0\n[CPU:1]\nenabled = 1\nipmi_zone = 1\n")
        assert len(cfg.cpu) == 2, "TestDuplicateZoneValidation.test_different_zones_no_conflict: two CPU sections"


# End.
