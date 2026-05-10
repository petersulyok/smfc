#!/usr/bin/env python3
#
#   test_service.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.Service() class.
#
from argparse import Namespace
from dataclasses import dataclass
from typing import List
import sys
import time
from configparser import ConfigParser
import pytest
from pyudev import Context
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, ConstFc, Service
from smfc.config import Config
from .test_data import TestData, MockedContextError, MockedContextGood
from .test_ipmi import BMC_INFO_OUTPUT


@dataclass
class MockControllerConfig:
    """Simple mock config for FanController tests."""
    ipmi_zone: List[int]
    polling: float = 2.0


class TestService:
    """Unit test for smfc.Service() class"""

    sleep_counter: int

    @pytest.mark.parametrize(
        "ipmi, log, error",
        [
            # Both IPMI and Log initialized
            (True, True, "Service.exit_func() 1"),
            # Neither IPMI nor Log initialized
            (False, False, "Service.exit_func() 2"),
        ],
    )
    def test_exit_func(self, mocker: MockerFixture, ipmi: bool, log: bool, error: str) -> None:
        """Positive unit test for Service.exit_func() method. It contains the following steps:
        - mock atexit.unregister(), Ipmi.set_fan_mode(), Log.msg_to_stdout() functions
        - execute Service.exit_func()
        - ASSERT: if mocked functions not called expected times
        """
        mock_atexit_unregister = MagicMock()
        mocker.patch("atexit.unregister", mock_atexit_unregister)
        mock_ipmi_set_fan_mode = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_mode", mock_ipmi_set_fan_mode)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        if log:
            service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        if ipmi:
            service.ipmi = Ipmi.__new__(Ipmi)
        service.exit_func()
        assert mock_atexit_unregister.call_count == 1, error
        if ipmi:
            assert mock_ipmi_set_fan_mode.call_count == 1, error
            if log:
                assert mock_log_msg.call_count == 1, error

    @pytest.mark.parametrize(
        "module_list, cpufc, hdfc, gpufc, standby, error",
        [
            # coretemp module loaded, CPU fan controller enabled
            ("something\ncoretemp\n", True, False, False, False, "Service.check_dependencies() 1"),
            # k10temp module loaded, CPU and GPU enabled
            ("something\nk10temp\n", True, False, True, False, "Service.check_dependencies() 2"),
            # Both coretemp and k10temp loaded
            ("coretemp\nsomething\nk10temp\n", True, False, False, False, "Service.check_dependencies() 3"),
            # drivetemp module loaded, HD and GPU enabled
            ("something\ndrivetemp\n", False, True, True, False, "Service.check_dependencies() 4"),
            # drivetemp module loaded, HD with standby guard
            ("something\ndrivetemp\n", False, True, False, True, "Service.check_dependencies() 5"),
            # No temperature module (HD only)
            ("something\n", False, True, False, False, "Service.check_dependencies() 6"),
            # drivetemp module loaded, HD, GPU, and standby
            ("something\ndrivetemp\nx", False, True, True, True, "Service.check_dependencies() 7"),
            # Both coretemp and drivetemp loaded
            ("coretemp\ndrivetemp\n", True, True, False, True, "Service.check_dependencies() 8"),
        ],
    )
    def test_check_dependencies_p(self, mocker: MockerFixture, module_list: str, cpufc, hdfc, gpufc, standby: bool,
                                  error: str, tmp_path):
        """Positive unit test for Service.check_dependencies() method. It contains the following steps:
        - mock print(), argparse.ArgumentParser._print_message() and builtins.open() functions
        - execute Service.check_dependencies()
        - ASSERT: if returns an error message
        """

        def mocked_open(path: str, *args, **kwargs):
            return (
                original_open(modules, *args, **kwargs)
                if path == "/proc/modules"
                else original_open(path, *args, **kwargs)
            )

        my_td = TestData()
        ipmi_command = my_td.create_ipmi_command()
        modules = my_td.create_text_file(module_list)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        original_open = open
        mock_open = MagicMock(side_effect=mocked_open)
        mocker.patch("builtins.open", mock_open)

        config_content = f"[Ipmi]\ncommand = {ipmi_command}\n"
        if cpufc:
            config_content += "[CPU]\nenabled = 1\n"
        if hdfc:
            smartctl_cmd = my_td.create_command_file('echo "ACTIVE"')
            config_content += f"[HD]\nenabled = 1\nhd_names = /dev/sda\nsmartctl_path = {smartctl_cmd}\n"
            if standby:
                config_content += "standby_guard_enabled = 1\n"
        if gpufc:
            nvidia_smi_cmd = my_td.create_command_file('echo "0"')
            config_content += f"[GPU]\nenabled = 1\ngpu_type = nvidia\nnvidia_smi_path = {nvidia_smi_cmd}\n"

        config_file = tmp_path / "test.conf"
        config_file.write_text(config_content)

        service = Service()
        service.config = Config(str(config_file))

        assert service.check_dependencies() == "", error
        del my_td

    def test_check_dependencies_disabled_gpu(self, mocker: MockerFixture, tmp_path):
        """Positive unit test: GPU section present with enabled=0 is skipped by check_dependencies()."""
        my_td = TestData()
        ipmi_command = my_td.create_ipmi_command()
        modules = my_td.create_text_file("something\ncoretemp\n")
        original_open = open
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        def fake_open(path, *a, **kw):
            target = modules if path == "/proc/modules" else path
            return original_open(target, *a, **kw)  # pylint: disable=consider-using-with
        mocker.patch("builtins.open", MagicMock(side_effect=fake_open))
        config_content = (f"[Ipmi]\ncommand = {ipmi_command}\n"
                          f"[CPU]\nenabled = 1\n"
                          f"[GPU]\nenabled = 0\n")
        config_file = tmp_path / "test.conf"
        config_file.write_text(config_content)
        service = Service()
        service.config = Config(str(config_file))
        assert service.check_dependencies() == ""
        del my_td

    @pytest.mark.parametrize(
        "error",
        [
            # Dependency check error conditions
            ("Service.check_dependencies() 9"),
        ],
    )
    def test_check_dependecies_n(self, mocker: MockerFixture, error: str, tmp_path):
        """Negative unit test for Service.check_dependencies() method. It contains the following steps:
        - mock print() and builtins.open() functions
        - execute Service.check_dependencies()
        - ASSERT: if it didn't return the specific error message
        """

        def mocked_open(path: str, *args, **kwargs):
            return (
                original_open(modules, *args, **kwargs)
                if path == "/proc/modules"
                else original_open(path, *args, **kwargs)
            )

        my_td = TestData()
        ipmi_command = my_td.create_ipmi_command()
        modules = my_td.create_text_file("coretemp\ndrivetemp\n")
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_open = MagicMock(side_effect=mocked_open)
        original_open = open
        mocker.patch("builtins.open", mock_open)

        smartctl_cmd = my_td.create_command_file('echo "ACTIVE"')
        nvidia_smi_cmd = my_td.create_command_file('echo "0"')

        hd_section = (f"[HD]\nenabled = 1\nhd_names = /dev/sda\n"
                      f"smartctl_path = {smartctl_cmd}\nstandby_guard_enabled = 1\n")
        config_content = (f"[Ipmi]\ncommand = {ipmi_command}\n"
                          f"[CPU]\nenabled = 1\n"
                          f"{hd_section}"
                          f"[GPU]\nenabled = 1\ngpu_type = nvidia\nnvidia_smi_path = {nvidia_smi_cmd}\n")
        config_file = tmp_path / "test.conf"
        config_file.write_text(config_content)

        service = Service()
        service.config = Config(str(config_file))

        # Check if `nvidia-smi` command is not available.
        my_td.delete_file(nvidia_smi_cmd)
        error_str = service.check_dependencies()
        assert error_str.find("command cannot be found!") != -1, error

        # Check if `smartctl` command is not available.
        my_td.delete_file(smartctl_cmd)
        error_str = service.check_dependencies()
        assert error_str.find("smartctl") != -1, error

        # Check if `drivetemp` is not on the module list.
        modules = my_td.create_text_file("coretemp something")
        error_str = service.check_dependencies()
        assert error_str.find("drivetemp") != -1, error

        # Check if `coretemp` is not on the module list.
        modules = my_td.create_text_file("drivetemp something")
        error_str = service.check_dependencies()
        assert error_str.find("coretemp") != -1, error

        # Check if `ipmitool` is not available.
        my_td.delete_file(ipmi_command)
        error_str = service.check_dependencies()
        assert error_str.find("ipmitool") != -1, error
        del my_td

    @pytest.mark.parametrize(
        "command_line, exit_code, error",
        [
            # Help flag (exit 0)
            ("-h", 0, "Service.run() 1"),
            # Version flag (exit 0)
            ("-v", 0, "Service.run() 2"),
            # Invalid log level (exit 2)
            ("-l 10", 2, "Service.run() 3"),
            # Invalid output (exit 2)
            ("-o 9", 2, "Service.run() 4"),
            # Invalid output with valid log level (exit 2)
            ("-o 1 -l 10", 2, "Service.run() 5"),
            # Valid output with invalid log level (exit 2)
            ("-o 9 -l 1", 2, "Service.run() 6"),
            # Invalid config file path: special char (exit 6)
            ("-o 0 -l 3 -c &.txt", 6, "Service.run() 7"),
            # Invalid config file path: non-existent (exit 6)
            ("-o 0 -l 3 -c ./nonexistent_folder/nonexistent_file.conf", 6, "Service.run() 8"),
        ],
    )
    def test_run_026n(self, mocker: MockerFixture, command_line: str, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), argparse.ArgumentParser._print_message() functions
        - execute Service.run()
        - ASSERT: if sys.exit() did not return code 0 (-h -v), 2 (invalid arguments), 6 (invalid configuration file)
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker_argumentparser_print = MagicMock()
        mocker.patch("argparse.ArgumentParser._print_message", mocker_argumentparser_print)
        sys.argv = ("smfc " + command_line).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error

    @pytest.mark.parametrize(
        "level, output, exit_code, error",
        [
            # Invalid log level via namespace (exit 5)
            (10, 0, 5, "Service.run() 9"),
            # Invalid output via namespace (exit 5)
            (0, 9, 5, "Service.run() 10"),
        ],
    )
    def test_run_5n(self, mocker: MockerFixture, level: int, output: int, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), argparse.ArgumentParser.parse_args() functions
        - execute Service.run()
        - ASSERT: if sys.exit() did not return code 5 (log initialization error)
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_parser_parse_args = MagicMock()
        mocker.patch("argparse.ArgumentParser.parse_args", mock_parser_parse_args)
        mock_parser_parse_args.return_value = Namespace(config_file="smfc.conf", ne=False, s=False, l=level, o=output)
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error

    @pytest.mark.parametrize(
        "exit_code, error",
        [
            # Check dependency error (exit 7)
            (7, "Service.run() 11"),
        ],
    )
    def test_run_7n(self, mocker: MockerFixture, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), argparse.ArgumentParser.parse_args(), smfc.Service.check_dependencies() functions
        - execute Service.run()
        - ASSERT: if sys.exit() did not return code 7 (check dependency error)
        """
        my_td = TestData()
        my_config = ConfigParser()
        my_config[Config.CS_IPMI] = {}
        my_config[Config.CS_CPU] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_HD] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_NVME] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_GPU] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_CONST] = {Config.CV_ENABLED: "0"}
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_parser_parse_args = MagicMock()
        mocker.patch("argparse.ArgumentParser.parse_args", mock_parser_parse_args)
        mock_parser_parse_args.return_value = Namespace(config_file=conf_file, ne=True, nd=False, s=False, l=0, o=0)
        mock_check_dependencies = MagicMock()
        mock_check_dependencies.return_value = "ERROR"
        mocker.patch("smfc.Service.check_dependencies", mock_check_dependencies)
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error
        del my_td

    @pytest.mark.parametrize(
        "ipmi_command, mode_delay, level_delay, exit_code, error",
        [
            # Non-existent IPMI command (exit 8)
            ("NON_EXIST", 0, 0, 8, "Service.run() 12"),
            # Invalid mode_delay (exit 6 - caught by Config validation)
            ("GOOD", -1, 0, 6, "Service.run() 13"),
            # Invalid level_delay (exit 6 - caught by Config validation)
            ("GOOD", 0, -1, 6, "Service.run() 14"),
            # Bad IPMI command (exit 8)
            ("BAD", 0, 0, 8, "Service.run() 15"),
            # No enabled zone (exit 10)
            ("GOOD", 0, 0, 10, "Service.run() 16"),
        ],
    )
    def test_run_810n(self, mocker: MockerFixture, ipmi_command: str, mode_delay: int, level_delay: int,
                      exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), pyudev.Context.__init__() functions
        - execute Service.run()
        - ASSERT: if sys.exit() did not return code 8 (Ipmi initialization error) or 10 (no enabled zone)
        """
        my_td = TestData()
        my_config = ConfigParser()
        if ipmi_command == "NON_EXIST":
            ipmi_command = "./non-existent-dir/non-existent-file"
        if ipmi_command == "BAD":
            ipmi_command = my_td.create_command_file()
        if ipmi_command == "GOOD":
            ipmi_command = my_td.create_ipmi_command()
        my_config[Config.CS_IPMI] = {
            Config.CV_IPMI_COMMAND: ipmi_command,
            Config.CV_IPMI_FAN_MODE_DELAY: str(mode_delay),
            Config.CV_IPMI_FAN_LEVEL_DELAY: str(level_delay),
        }
        my_config[Config.CS_CPU] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_HD] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_NVME] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_GPU] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_CONST] = {Config.CV_ENABLED: "0"}
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        sys.argv = ("smfc.py -o 0 -nd -ne -c " + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error
        del my_td

    def test_check_dependencies_amd_p(self, mocker: MockerFixture, tmp_path):
        """Positive unit test for Service.check_dependencies() with AMD GPU. It contains the following steps:
        - mock print() and builtins.open() functions
        - configure gpu_type=amd with a valid rocm_smi_path
        - execute Service.check_dependencies()
        - ASSERT: if it returns an error message (should return empty string)
        """

        def mocked_open(path: str, *args, **kwargs):
            return (
                original_open(modules, *args, **kwargs)
                if path == "/proc/modules"
                else original_open(path, *args, **kwargs)
            )

        my_td = TestData()
        ipmi_command = my_td.create_ipmi_command()
        modules = my_td.create_text_file("something\ncoretemp\n")
        rocm_smi_cmd = my_td.create_command_file('echo "0"')
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        original_open = open
        mock_open = MagicMock(side_effect=mocked_open)
        mocker.patch("builtins.open", mock_open)

        config_content = (f"[Ipmi]\ncommand = {ipmi_command}\n"
                          f"[GPU]\nenabled = 1\ngpu_type = amd\nrocm_smi_path = {rocm_smi_cmd}\n")
        config_file = tmp_path / "test.conf"
        config_file.write_text(config_content)

        service = Service()
        service.config = Config(str(config_file))
        assert service.check_dependencies() == "", "Service.check_dependencies() AMD p1"
        del my_td

    def test_check_dependencies_invalid_gpu_type_n(self, mocker: MockerFixture, tmp_path):
        """Negative unit test for Config parsing with invalid gpu_type. It contains the following steps:
        - configure gpu_type=invalid
        - attempt to create Config
        - ASSERT: if ValueError is not raised with "invalid" in the message
        """

        my_td = TestData()
        ipmi_command = my_td.create_ipmi_command()
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)

        config_content = (f"[Ipmi]\ncommand = {ipmi_command}\n"
                          f"[GPU]\nenabled = 1\ngpu_type = invalid\n")
        config_file = tmp_path / "test.conf"
        config_file.write_text(config_content)

        with pytest.raises(ValueError) as exc_info:
            Config(str(config_file))
        assert "invalid" in str(exc_info.value), "Config parsing should reject invalid gpu_type"
        del my_td

    @pytest.mark.parametrize(
        "exit_code, error",
        [
            # pyudev.Context init error (exit 9)
            (9, "Service.run() 17"),
        ],
    )
    def test_run_9n(self, mocker: MockerFixture, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), pyudev.Context.__init__() functions
        - execute Service.run()
        - ASSERT: if sys.exit() did not return code 9 (pyudev.Context() init error)
        """
        my_td = TestData()
        my_config = ConfigParser()
        ipmi_command = my_td.create_ipmi_command()
        my_config[Config.CS_IPMI] = {
            Config.CV_IPMI_COMMAND: ipmi_command,
            Config.CV_IPMI_FAN_MODE_DELAY: "0",
            Config.CV_IPMI_FAN_LEVEL_DELAY: "0",
        }
        my_config[Config.CS_CPU] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_HD] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_NVME] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_GPU] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_CONST] = {Config.CV_ENABLED: "0"}
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch("pyudev.Context.__init__", MockedContextError.__init__)
        sys.argv = ("smfc.py -o 0 -ne -nd -c " + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error
        del my_td

    @pytest.mark.parametrize(
        "cpufc, hdfc, nvmefc, gpufc, constfc, exit_code, error",
        [
            # CPU and GPU enabled
            (True, False, False, True, False, 100, "Service.run() 18"),
            # HD and CONST enabled
            (False, True, False, False, True, 100, "Service.run() 19"),
            # CPU and GPU enabled (duplicate)
            (True, False, False, True, False, 100, "Service.run() 20"),
            # CPU and NVME enabled
            (True, False, True, False, False, 100, "Service.run() 21"),
            # All controllers enabled
            (True, True, True, True, True, 100, "Service.run() 22"),
        ],
    )
    def test_run_100p(self, mocker: MockerFixture, cpufc: bool, hdfc: bool, nvmefc: bool, gpufc: bool,
                      constfc: bool, exit_code: int, error: str):
        """Positive unit test for Service.run() method. It contains the following steps:
        - mock print(), time.sleep() functions
        - execute smfc.run()
        - The main loop will be executed 10 times then exit with code 100
        """

        # pylint: disable=unused-argument
        def mocked_sleep(*args):
            """Mocked time.sleep() function. Exists at the 10th call."""
            self.sleep_counter += 1
            if self.sleep_counter >= 10:
                sys.exit(100)

        def mocked_cpufc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg) -> None:
            nonlocal my_td
            self.hwmon_path = my_td.cpu_files
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(my_td.cpu_files))

        def mocked_hdfc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg, sudo: bool) -> None:
            nonlocal my_td
            self.hd_device_names = my_td.hd_name_list
            self.hwmon_path = my_td.hd_files
            self.sudo = sudo
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(my_td.hd_files))
            self.standby_array_states = [False] * self.count
            self.standby_flag = False
            self.standby_change_timestamp = time.monotonic()

        def mocked_gpufc_init(self, log: Log, ipmi: Ipmi, cfg) -> None:
            nonlocal my_td
            self.smi_called = 0
            self.hwmon_path = []
            self.gpu_temperature = []
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(cfg.gpu_device_ids))

        def mocked_nvmefc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg) -> None:
            nonlocal my_td
            self.nvme_device_names = my_td.nvme_name_list
            self.hwmon_path = my_td.nvme_files
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(my_td.nvme_files))

        def mocked_constfc_init(self, log: Log, ipmi: Ipmi, cfg) -> None:
            self.ipmi = ipmi
            self.log = log
            self.name = cfg.section
            self.config = cfg
            self.last_time = 0
            self.last_temp = 0.0
            self.last_level = cfg.level
            self.deferred_apply = False

        # pragma pylint: enable=unused-argument

        my_td = TestData()
        # Force mode initial fan mode 0 for setting new FULL mode during the test.
        cmd_ipmi = my_td.create_command_file(
            'if [[ $1 = "bmc" && $2 = "info" ]] ; then\n'
            "cat << 'BMCEOF'\n" + BMC_INFO_OUTPUT +
            "BMCEOF\n"
            "exit 0\n"
            "fi\n"
            'echo "0"'
        )
        cmd_smart = my_td.create_smart_command()
        # create_command_file('echo "ACTIVE"'))
        cmd_nvidia = my_td.create_nvidia_smi_command(1)
        my_td.create_cpu_data(1)
        my_td.create_hd_data(8)
        my_td.create_nvme_data(2)
        my_config = ConfigParser()
        my_config[Config.CS_IPMI] = {
            Config.CV_IPMI_COMMAND: cmd_ipmi,
            Config.CV_IPMI_FAN_MODE_DELAY: "0",
            Config.CV_IPMI_FAN_LEVEL_DELAY: "0",
        }
        my_config[Config.CS_CPU] = {
            Config.CV_ENABLED: str(cpufc),
            Config.CV_TEMP_CALC: "1",
            Config.CV_STEPS: "5",
            Config.CV_SENSITIVITY: "5",
            Config.CV_POLLING: "0",
            Config.CV_MIN_TEMP: "30",
            Config.CV_MAX_TEMP: "60",
            Config.CV_MIN_LEVEL: "35",
            Config.CV_MAX_LEVEL: "100",
        }
        my_config[Config.CS_HD] = {
            Config.CV_ENABLED: str(hdfc),
            Config.CV_TEMP_CALC: "1",
            Config.CV_STEPS: "4",
            Config.CV_SENSITIVITY: "2",
            Config.CV_POLLING: "0",
            Config.CV_MIN_TEMP: "30",
            Config.CV_MAX_TEMP: "45",
            Config.CV_MIN_LEVEL: "35",
            Config.CV_MAX_LEVEL: "100",
            Config.CV_HD_NAMES: my_td.hd_names,
            Config.CV_HD_SMARTCTL_PATH: cmd_smart,
            Config.CV_HD_STANDBY_GUARD_ENABLED: "1",
            Config.CV_HD_STANDBY_HD_LIMIT: "2",
        }
        my_config[Config.CS_NVME] = {
            Config.CV_ENABLED: str(nvmefc),
            Config.CV_TEMP_CALC: "1",
            Config.CV_STEPS: "4",
            Config.CV_SENSITIVITY: "2",
            Config.CV_POLLING: "0",
            Config.CV_MIN_TEMP: "30",
            Config.CV_MAX_TEMP: "50",
            Config.CV_MIN_LEVEL: "35",
            Config.CV_MAX_LEVEL: "100",
            Config.CV_NVME_NAMES: my_td.nvme_names,
        }
        my_config[Config.CS_GPU] = {
            Config.CV_ENABLED: str(gpufc),
            Config.CV_IPMI_ZONE: "2",
            Config.CV_TEMP_CALC: "1",
            Config.CV_STEPS: "4",
            Config.CV_SENSITIVITY: "2",
            Config.CV_POLLING: "0",
            Config.CV_MIN_TEMP: "45",
            Config.CV_MAX_TEMP: "70",
            Config.CV_MIN_LEVEL: "35",
            Config.CV_MAX_LEVEL: "100",
            Config.CV_GPU_IDS: "0",
            Config.CV_GPU_NVIDIA_SMI_PATH: cmd_nvidia,
        }
        my_config[Config.CS_CONST] = {
            Config.CV_ENABLED: str(constfc),
            Config.CV_IPMI_ZONE: "2",
            Config.CV_POLLING: "0",
            Config.CV_CONST_LEVEL: "35",
        }
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_time_sleep = MagicMock()
        mock_time_sleep.side_effect = mocked_sleep
        mocker.patch("time.sleep", mock_time_sleep)
        # pylint: disable=R0801
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        mocker.patch("smfc.CpuFc.__init__", mocked_cpufc_init)
        mocker.patch("smfc.HdFc.__init__", mocked_hdfc_init)
        mocker.patch("smfc.NvmeFc.__init__", mocked_nvmefc_init)
        mocker.patch("smfc.GpuFc.__init__", mocked_gpufc_init)
        mocker.patch("smfc.ConstFc.__init__", mocked_constfc_init)
        # pylint: enable=R0801
        self.sleep_counter = 0
        sys.argv = ("smfc.py -o 0 -l 4 -ne -nd -c " + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error
        del my_td

    def test_collect_desired_levels(self, mocker: MockerFixture):
        """Positive unit test for Service._collect_desired_levels() method. It contains the following steps:
        - mock print() function
        - initialize a Service class with enabled controllers (CPU, HD, CONST)
        - set last_level values for controllers (CPU=60, HD=0, CONST=0)
        - call _collect_desired_levels()
        - ASSERT: if controllers with last_level=0 are not skipped (except ConstFc)
        - ASSERT: if ConstFc with last_level=0 is not still collected
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # Create mock controllers
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0])
        cpu_fc.last_level = 60
        cpu_fc.last_temp = 45.0
        cpu_fc.deferred_apply = True

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 0  # Should be skipped (not yet computed)
        hd_fc.last_temp = 0.0
        hd_fc.deferred_apply = True

        # ConstFc with last_level=0 should NOT be skipped
        const_fc = ConstFc.__new__(ConstFc)
        const_fc.name = Config.CS_CONST
        const_fc.config = MockControllerConfig(ipmi_zone=[1])
        const_fc.last_level = 0
        const_fc.last_temp = 0.0
        const_fc.deferred_apply = True

        service.controllers = [cpu_fc, hd_fc, const_fc]

        levels = service._collect_desired_levels()  # pylint: disable=protected-access
        names = [name for name, _, _, _ in levels]
        assert Config.CS_CPU in names, "CPU controller should be collected"
        assert Config.CS_HD not in names, "HD controller with level 0 should be skipped"
        assert Config.CS_CONST in names, "ConstFc with level 0 should still be collected"

    def test_apply_fan_levels_shared_zone(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with shared zone. It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
        - initialize a Service class with two controllers on zone 1 (HD at 45%, NVME at 70%)
        - call _apply_fan_levels()
        - ASSERT: if the maximum level (70%) is not applied when two controllers share a zone
        - ASSERT: if the log output does not contain the winner and losers
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # Two controllers on zone 1: HD at 45%, NVME at 70%
        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 45
        hd_fc.last_temp = 38.0
        hd_fc.deferred_apply = True

        nvme_fc = FanController.__new__(FanController)
        nvme_fc.name = Config.CS_NVME
        nvme_fc.config = MockControllerConfig(ipmi_zone=[1])
        nvme_fc.last_level = 70
        nvme_fc.last_temp = 42.5
        nvme_fc.deferred_apply = True

        service.controllers = [hd_fc, nvme_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # Zone 1 should be set to 70% (the higher level wins)
        mock_set_fan_level.assert_called_once_with(1, 70)
        assert service.applied_levels[1] == 70, "Zone 1 should cache level 70"
        # Log should mention the winner and losers for shared zones with temperatures
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: NVME=70%/42.5C" in log_output, "Shared zone log should mention winner with temp"
        assert "losers: HD=45%/38.0C" in log_output, "Shared zone log should mention losers with temp"

    def test_apply_fan_levels_single_zone(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with single-controller zone.
        It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
        - initialize a Service class with single CPU controller on zone 0
        - call _apply_fan_levels()
        - ASSERT: if the fan level is not logged for a single-controller zone
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # Single controller on zone 0
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0])
        cpu_fc.last_level = 60
        cpu_fc.last_temp = 45.0
        cpu_fc.deferred_apply = True

        service.controllers = [cpu_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        mock_set_fan_level.assert_called_once_with(0, 60)
        assert service.applied_levels[0] == 60
        # Single-contributor zone should log the fan level with temperature
        log_output = str(mock_log_msg.call_args_list)
        assert "IPMI zone [0]: new level = 60% (CPU=45.0C)" in log_output

    def test_apply_fan_levels_single_zone_const(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with single CONST controller.
        It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
        - initialize a Service class with single CONST controller on zone 0
        - call _apply_fan_levels()
        - ASSERT: if the log output does not exclude temperature for CONST controller
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # Single CONST controller on zone 0
        const_fc = ConstFc.__new__(ConstFc)
        const_fc.name = Config.CS_CONST
        const_fc.config = MockControllerConfig(ipmi_zone=[0])
        const_fc.last_level = 50
        const_fc.last_temp = 0.0
        const_fc.deferred_apply = True

        service.controllers = [const_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        mock_set_fan_level.assert_called_once_with(0, 50)
        assert service.applied_levels[0] == 50
        # Single CONST zone should log without temperature
        log_output = str(mock_log_msg.call_args_list)
        assert "IPMI zone [0]: new level = 50% (CONST)" in log_output

    def test_apply_fan_levels_shared_zone_const_winner(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method when CONST wins. It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
        - initialize a Service class with CONST at 80% and HD at 45% on zone 1
        - call _apply_fan_levels()
        - ASSERT: if CONST (80%) does not win over HD (45%)
        - ASSERT: if the log output does not show CONST winner without temperature
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # CONST at 80% wins over HD at 45% on zone 1
        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 45
        hd_fc.last_temp = 38.0
        hd_fc.deferred_apply = True

        const_fc = ConstFc.__new__(ConstFc)
        const_fc.name = Config.CS_CONST
        const_fc.config = MockControllerConfig(ipmi_zone=[1])
        const_fc.last_level = 80
        const_fc.last_temp = 0.0
        const_fc.deferred_apply = True

        service.controllers = [hd_fc, const_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        mock_set_fan_level.assert_called_once_with(1, 80)
        assert service.applied_levels[1] == 80
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: CONST=80%" in log_output, "CONST winner should have no temperature"
        assert "losers: HD=45%/38.0C" in log_output

    def test_apply_fan_levels_shared_zone_const_loser(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method when CONST loses. It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
        - initialize a Service class with HD at 70% and CONST at 40% on zone 1
        - call _apply_fan_levels()
        - ASSERT: if HD (70%) does not win over CONST (40%)
        - ASSERT: if the log output does not show CONST loser without temperature
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # HD at 70% wins over CONST at 40% on zone 1
        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 70
        hd_fc.last_temp = 55.0
        hd_fc.deferred_apply = True

        const_fc = ConstFc.__new__(ConstFc)
        const_fc.name = Config.CS_CONST
        const_fc.config = MockControllerConfig(ipmi_zone=[1])
        const_fc.last_level = 40
        const_fc.last_temp = 0.0
        const_fc.deferred_apply = True

        service.controllers = [hd_fc, const_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        mock_set_fan_level.assert_called_once_with(1, 70)
        assert service.applied_levels[1] == 70
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: HD=70%/55.0C" in log_output
        assert "losers: CONST=40%" in log_output, "CONST loser should have no temperature"

    def test_apply_fan_levels_skips_non_deferred(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with non-deferred controllers.
        It contains the following steps:
        - mock print(), Ipmi.set_fan_level() functions
        - initialize a Service class with CPU (deferred) on zone 0 and HD (non-deferred) on zone 1
        - call _apply_fan_levels()
        - ASSERT: if non-deferred controllers are not skipped in _apply_fan_levels()
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # CPU deferred on shared zone 0, HD non-deferred on non-shared zone 1
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0])
        cpu_fc.last_level = 60
        cpu_fc.last_temp = 45.0
        cpu_fc.deferred_apply = True

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 40
        hd_fc.last_temp = 23.0
        hd_fc.deferred_apply = False

        service.controllers = [cpu_fc, hd_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # Only zone 0 should get an IPMI call, zone 1 is handled by HD directly
        mock_set_fan_level.assert_called_once_with(0, 60)
        assert 0 in service.applied_levels
        assert 1 not in service.applied_levels

    def test_apply_fan_levels_cache(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with level caching.
        It contains the following steps:
        - mock print(), Ipmi.set_fan_level() functions
        - initialize a Service class with HD controller and pre-cached level 70% on zone 1
        - call _apply_fan_levels() with same level
        - ASSERT: if IPMI call is not skipped when level has not changed
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {1: 70}  # Already applied 70% to zone 1
        service.last_desired = []

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 70
        hd_fc.last_temp = 40.0
        hd_fc.deferred_apply = True

        service.controllers = [hd_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # No IPMI call since level hasn't changed
        assert mock_set_fan_level.call_count == 0, "Should skip IPMI call when level is cached"

    def test_apply_fan_levels_three_controllers(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method. It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), and Log.msg_to_stdout() functions
        - create 3 deferred controllers (CPU 40%, HD 60%, NVME 50%) on the same IPMI zone 1
        - execute _apply_fan_levels()
        - ASSERT: if the highest level (HD 60%) is not applied to zone 1
        - ASSERT: if the log output does not contain the correct winner and losers
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # Three controllers on zone 1: CPU 40%, HD 60%, NVME 50%
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[1])
        cpu_fc.last_level = 40
        cpu_fc.last_temp = 50.0
        cpu_fc.deferred_apply = True

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 60
        hd_fc.last_temp = 38.0
        hd_fc.deferred_apply = True

        nvme_fc = FanController.__new__(FanController)
        nvme_fc.name = Config.CS_NVME
        nvme_fc.config = MockControllerConfig(ipmi_zone=[1])
        nvme_fc.last_level = 50
        nvme_fc.last_temp = 42.0
        nvme_fc.deferred_apply = True

        service.controllers = [cpu_fc, hd_fc, nvme_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # HD at 60% should win (highest level among the three)
        mock_set_fan_level.assert_called_once_with(1, 60)
        assert service.applied_levels[1] == 60
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: HD=60%/38.0C" in log_output
        assert "CPU=40%/50.0C" in log_output
        assert "NVME=50%/42.0C" in log_output

    def test_apply_fan_levels_equal_levels(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method. It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), and Log.msg_to_stdout() functions
        - create 2 deferred controllers (CPU 70%, HD 70%) on the same IPMI zone 1 with equal levels
        - execute _apply_fan_levels()
        - ASSERT: if level 70% is not applied to zone 1
        - ASSERT: if the first collected controller (CPU) is not the winner (tie-breaking uses > not >=)
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # Two controllers on zone 1 with identical levels (70%)
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[1])
        cpu_fc.last_level = 70
        cpu_fc.last_temp = 55.0
        cpu_fc.deferred_apply = True

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 70
        hd_fc.last_temp = 40.0
        hd_fc.deferred_apply = True

        service.controllers = [cpu_fc, hd_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # Level 70% should be applied correctly
        mock_set_fan_level.assert_called_once_with(1, 70)
        assert service.applied_levels[1] == 70
        # First collected controller (CPU) should be the winner (uses > not >=)
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: CPU=70%/55.0C" in log_output
        assert "losers: HD=70%/40.0C" in log_output

    def test_apply_fan_levels_multi_zone_partial_shared(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method. It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), and Log.msg_to_stdout() functions
        - create CPU controller on zones [0, 1] at 55% and HD controller on zone [1] at 70%, both deferred
        - execute _apply_fan_levels()
        - ASSERT: if zone 0 is not set to CPU's 55% (single contributor)
        - ASSERT: if zone 1 is not set to HD's 70% (winner of shared zone arbitration)
        - ASSERT: if the log output does not contain correct single-zone and shared-zone messages
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # CPU on zones [0, 1] at 55%, HD on zone [1] at 70%
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0, 1])
        cpu_fc.last_level = 55
        cpu_fc.last_temp = 48.0
        cpu_fc.deferred_apply = True

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 70
        hd_fc.last_temp = 42.0
        hd_fc.deferred_apply = True

        service.controllers = [cpu_fc, hd_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # Zone 0: only CPU contributes → 55%
        # Zone 1: CPU 55% vs HD 70% → HD wins at 70%
        calls = mock_set_fan_level.call_args_list
        assert len(calls) == 2, "Both zone 0 and zone 1 should get IPMI calls"
        call_dict = {c.args[0]: c.args[1] for c in calls}
        assert call_dict[0] == 55, "Zone 0 should be set to CPU's 55%"
        assert call_dict[1] == 70, "Zone 1 should be set to HD's 70% (winner)"
        assert service.applied_levels[0] == 55
        assert service.applied_levels[1] == 70
        # Zone 0 should log as single-contributor, zone 1 as shared
        log_output = str(mock_log_msg.call_args_list)
        assert "IPMI zone [0]: new level = 55% (CPU=48.0C)" in log_output
        assert "winner: HD=70%/42.0C" in log_output

    def test_apply_fan_levels_cache_oscillation(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method. It contains the following steps:
        - mock print() and Ipmi.set_fan_level() functions
        - create HD controller on zone 1 with deferred apply
        - execute _apply_fan_levels() three times with levels 70%, 50%, 70% (oscillation)
        - ASSERT: if each level change does not trigger a new IPMI call (3 calls total)
        - ASSERT: if the cache does not correctly reflect the current level after each step
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_temp = 40.0
        hd_fc.deferred_apply = True

        service.controllers = [hd_fc]

        # Step 1: level = 70%
        hd_fc.last_level = 70
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 1
        assert service.applied_levels[1] == 70

        # Step 2: level drops to 50%
        hd_fc.last_level = 50
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 2
        assert service.applied_levels[1] == 50

        # Step 3: level returns to 70% — must trigger a new IPMI call
        hd_fc.last_level = 70
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 3, "Returning to previous level should trigger IPMI call"
        assert service.applied_levels[1] == 70

    def test_check_shared_zones_detected(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method with shared zone detection.
        It contains the following steps:
        - mock print(), Log.msg_to_stdout() functions
        - initialize a Service class with HD and NVME controllers both on zone 1
        - call _check_shared_zones()
        - ASSERT: if shared zone 1 is not detected when HD and NVME share it
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])

        nvme_fc = FanController.__new__(FanController)
        nvme_fc.name = Config.CS_NVME
        nvme_fc.config = MockControllerConfig(ipmi_zone=[1])

        service.controllers = [hd_fc, nvme_fc]

        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == {1}, "Should detect shared zone 1"
        log_output = str(mock_log_msg.call_args_list)
        assert "Shared IPMI zone 1" in log_output, "Should log shared zone 1"

    def test_check_shared_zones_none(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method with no shared zones.
        It contains the following steps:
        - mock print() function
        - initialize a Service class with CPU on zone 0 and HD on zone 1 (no overlap)
        - call _check_shared_zones()
        - ASSERT: if empty set is not returned when no zones are shared
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)

        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0])

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])

        service.controllers = [cpu_fc, hd_fc]

        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == set(), "Should not detect shared zones"

    def test_check_shared_zones_multi_zone(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method with multi-zone controller.
        It contains the following steps:
        - mock print(), Log.msg_to_stdout() functions
        - initialize a Service class with CPU on zones [0,1] and HD on zone [1]
        - call _check_shared_zones()
        - ASSERT: if {1} is not returned when CPU spans zones [0,1] and HD is on zone [1]
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)

        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0, 1])

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])

        service.controllers = [cpu_fc, hd_fc]

        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == {1}, "Should detect shared zone 1"
        log_output = str(mock_log_msg.call_args_list)
        assert "Shared IPMI zone 1" in log_output, "Should log shared zone 1"

    def test_check_shared_zones_selective_deferred(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method with selective deferred mode.
        It contains the following steps:
        - mock print() function
        - initialize a Service class with CPU on zone 0 (exclusive), HD and NVME on zone 1 (shared)
        - call _check_shared_zones() and set deferred_apply based on shared zones
        - ASSERT: if controllers on non-shared zones get deferred_apply=True
        - ASSERT: if controllers on shared zones do not get deferred_apply=True
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)

        # CPU on zone 0 (exclusive), HD on zone 1, NVME on zone 1 (shared)
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0])
        cpu_fc.deferred_apply = False

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.deferred_apply = False

        nvme_fc = FanController.__new__(FanController)
        nvme_fc.name = Config.CS_NVME
        nvme_fc.config = MockControllerConfig(ipmi_zone=[1])
        nvme_fc.deferred_apply = False

        service.controllers = [cpu_fc, hd_fc, nvme_fc]

        service.shared_zones = service._check_shared_zones()  # pylint: disable=protected-access
        assert service.shared_zones == {1}
        # Apply deferred only to controllers on shared zones
        if service.shared_zones:
            for fc in service.controllers:
                if set(fc.config.ipmi_zone) & service.shared_zones:
                    fc.deferred_apply = True
        assert cpu_fc.deferred_apply is False, "CPU on zone 0 should not be deferred"
        assert hd_fc.deferred_apply is True, "HD on shared zone 1 should be deferred"
        assert nvme_fc.deferred_apply is True, "NVME on shared zone 1 should be deferred"

    @pytest.mark.parametrize(
        "exit_code, error",
        [
            # Old-style section names migration (exit 10)
            (10, "Service.run() 23"),
        ],
    )
    def test_run_old_section_names(self, mocker: MockerFixture, exit_code: int, error: str):
        """Positive unit test for Service.run() method with old section names. It contains the following steps:
        - mock print(), pyudev.Context.__init__() functions
        - create config with old-style section names ([CPU zone], [HD zone], etc.)
        - execute Service.run()
        - ASSERT: if exit code 10 (no enabled fancontroller) is not returned,
          proving the migration code ran successfully
        """
        my_td = TestData()
        my_config = ConfigParser()
        ipmi_command = my_td.create_ipmi_command()
        my_config[Config.CS_IPMI] = {
            Config.CV_IPMI_COMMAND: ipmi_command,
            Config.CV_IPMI_FAN_MODE_DELAY: "0",
            Config.CV_IPMI_FAN_LEVEL_DELAY: "0",
        }
        # Use old-style section names with 'zone' tag.
        my_config["CPU zone"] = {Config.CV_ENABLED: "0"}
        my_config["HD zone"] = {Config.CV_ENABLED: "0"}
        my_config["NVME zone"] = {Config.CV_ENABLED: "0"}
        my_config["GPU zone"] = {Config.CV_ENABLED: "0"}
        my_config["CONST zone"] = {Config.CV_ENABLED: "0"}
        conf_file = my_td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        sys.argv = ("smfc.py -o 0 -nd -ne -c " + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code, error
        del my_td

    def test_apply_fan_levels_four_controllers_same_zone(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with four controllers.
        It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
        - create 4 deferred controllers (CPU 40%, HD 60%, NVME 50%, GPU 75%) on the same IPMI zone 1
        - execute _apply_fan_levels()
        - ASSERT: if the highest level (GPU 75%) is not applied to zone 1
        - ASSERT: if the log output does not contain the correct winner and losers
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # Four controllers on zone 1: CPU 40%, HD 60%, NVME 50%, GPU 75%
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[1])
        cpu_fc.last_level = 40
        cpu_fc.last_temp = 45.0
        cpu_fc.deferred_apply = True

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 60
        hd_fc.last_temp = 38.0
        hd_fc.deferred_apply = True

        nvme_fc = FanController.__new__(FanController)
        nvme_fc.name = Config.CS_NVME
        nvme_fc.config = MockControllerConfig(ipmi_zone=[1])
        nvme_fc.last_level = 50
        nvme_fc.last_temp = 42.0
        nvme_fc.deferred_apply = True

        gpu_fc = FanController.__new__(FanController)
        gpu_fc.name = Config.CS_GPU
        gpu_fc.config = MockControllerConfig(ipmi_zone=[1])
        gpu_fc.last_level = 75
        gpu_fc.last_temp = 65.0
        gpu_fc.deferred_apply = True

        service.controllers = [cpu_fc, hd_fc, nvme_fc, gpu_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # GPU at 75% should win (highest level among the four)
        mock_set_fan_level.assert_called_once_with(1, 75)
        assert service.applied_levels[1] == 75
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: GPU=75%/65.0C" in log_output
        assert "CPU=40%/45.0C" in log_output
        assert "HD=60%/38.0C" in log_output
        assert "NVME=50%/42.0C" in log_output

    def test_apply_fan_levels_five_controllers_with_const(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with all five controller types.
        It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
        - create 5 deferred controllers (CPU 40%, HD 60%, NVME 50%, GPU 55%, CONST 80%) on the same IPMI zone 1
        - execute _apply_fan_levels()
        - ASSERT: if the highest level (CONST 80%) is not applied to zone 1
        - ASSERT: if the log output does not contain the correct winner (without temperature) and losers
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # Five controllers on zone 1: CPU 40%, HD 60%, NVME 50%, GPU 55%, CONST 80%
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[1])
        cpu_fc.last_level = 40
        cpu_fc.last_temp = 45.0
        cpu_fc.deferred_apply = True

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 60
        hd_fc.last_temp = 38.0
        hd_fc.deferred_apply = True

        nvme_fc = FanController.__new__(FanController)
        nvme_fc.name = Config.CS_NVME
        nvme_fc.config = MockControllerConfig(ipmi_zone=[1])
        nvme_fc.last_level = 50
        nvme_fc.last_temp = 42.0
        nvme_fc.deferred_apply = True

        gpu_fc = FanController.__new__(FanController)
        gpu_fc.name = Config.CS_GPU
        gpu_fc.config = MockControllerConfig(ipmi_zone=[1])
        gpu_fc.last_level = 55
        gpu_fc.last_temp = 60.0
        gpu_fc.deferred_apply = True

        const_fc = ConstFc.__new__(ConstFc)
        const_fc.name = Config.CS_CONST
        const_fc.config = MockControllerConfig(ipmi_zone=[1])
        const_fc.last_level = 80
        const_fc.last_temp = 0.0
        const_fc.deferred_apply = True

        service.controllers = [cpu_fc, hd_fc, nvme_fc, gpu_fc, const_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # CONST at 80% should win (highest level among all five)
        mock_set_fan_level.assert_called_once_with(1, 80)
        assert service.applied_levels[1] == 80
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: CONST=80%" in log_output  # CONST has no temperature
        # All losers should be listed
        assert "CPU=40%/45.0C" in log_output
        assert "HD=60%/38.0C" in log_output
        assert "NVME=50%/42.0C" in log_output
        assert "GPU=55%/60.0C" in log_output

    def test_apply_fan_levels_complex_three_zone_overlap(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with complex zone overlap.
        It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout() functions
        - create CPU on zones [0, 1, 2] at 50%, HD on zones [1, 2] at 65%, NVME on zone [2] at 80%
        - execute _apply_fan_levels()
        - ASSERT: if zone 0 is not set to CPU's 50% (single contributor)
        - ASSERT: if zone 1 is not set to HD's 65% (HD wins over CPU)
        - ASSERT: if zone 2 is not set to NVME's 80% (NVME wins over CPU and HD)
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # CPU on zones [0, 1, 2] at 50%
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0, 1, 2])
        cpu_fc.last_level = 50
        cpu_fc.last_temp = 45.0
        cpu_fc.deferred_apply = True

        # HD on zones [1, 2] at 65%
        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1, 2])
        hd_fc.last_level = 65
        hd_fc.last_temp = 40.0
        hd_fc.deferred_apply = True

        # NVME on zone [2] at 80%
        nvme_fc = FanController.__new__(FanController)
        nvme_fc.name = Config.CS_NVME
        nvme_fc.config = MockControllerConfig(ipmi_zone=[2])
        nvme_fc.last_level = 80
        nvme_fc.last_temp = 55.0
        nvme_fc.deferred_apply = True

        service.controllers = [cpu_fc, hd_fc, nvme_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # Zone 0: only CPU → 50%
        # Zone 1: CPU 50% vs HD 65% → HD wins at 65%
        # Zone 2: CPU 50% vs HD 65% vs NVME 80% → NVME wins at 80%
        calls = mock_set_fan_level.call_args_list
        assert len(calls) == 3, "All three zones should get IPMI calls"
        call_dict = {c.args[0]: c.args[1] for c in calls}
        assert call_dict[0] == 50, "Zone 0 should be set to CPU's 50%"
        assert call_dict[1] == 65, "Zone 1 should be set to HD's 65%"
        assert call_dict[2] == 80, "Zone 2 should be set to NVME's 80%"
        assert service.applied_levels[0] == 50
        assert service.applied_levels[1] == 65
        assert service.applied_levels[2] == 80

    def test_apply_fan_levels_all_controllers_last_level_zero(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with last_level=0. It contains the following steps:
        - mock print(), Ipmi.set_fan_level() functions
        - create 2 deferred controllers on zone 1 with last_level=0 (not yet computed)
        - execute _apply_fan_levels()
        - ASSERT: if controllers with last_level=0 are not skipped in _collect_desired_levels()
        - ASSERT: if IPMI call is made when no controller has a valid level
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # Two controllers on zone 1, both with last_level=0 (not yet computed)
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[1])
        cpu_fc.last_level = 0
        cpu_fc.last_temp = 0.0
        cpu_fc.deferred_apply = True

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1])
        hd_fc.last_level = 0
        hd_fc.last_temp = 0.0
        hd_fc.deferred_apply = True

        service.controllers = [cpu_fc, hd_fc]

        service._apply_fan_levels()  # pylint: disable=protected-access
        # Both controllers have last_level=0, so they should be skipped in _collect_desired_levels
        # No IPMI call should be made
        assert mock_set_fan_level.call_count == 0, "Controllers with last_level=0 should be skipped"

    def test_check_shared_zones_three_plus_zones_partial_overlap(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method with complex overlap.
        It contains the following steps:
        - mock print(), Log.msg_to_stdout() functions
        - create CPU on zones [0, 1, 2], HD on zones [1, 2], NVME on zone [2]
        - execute _check_shared_zones()
        - ASSERT: if shared zones {1, 2} are not detected
        - ASSERT: if log output does not contain messages for both shared zones
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)

        # CPU on zones [0, 1, 2], HD on [1, 2], NVME on [2]
        # Shared zones: 1 (CPU+HD), 2 (CPU+HD+NVME)
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0, 1, 2])

        hd_fc = FanController.__new__(FanController)
        hd_fc.name = Config.CS_HD
        hd_fc.config = MockControllerConfig(ipmi_zone=[1, 2])

        nvme_fc = FanController.__new__(FanController)
        nvme_fc.name = Config.CS_NVME
        nvme_fc.config = MockControllerConfig(ipmi_zone=[2])

        service.controllers = [cpu_fc, hd_fc, nvme_fc]

        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == {1, 2}, "Should detect shared zones 1 and 2"
        log_output = str(mock_log_msg.call_args_list)
        assert "Shared IPMI zone 1" in log_output
        assert "Shared IPMI zone 2" in log_output

    def test_apply_fan_levels_multi_zone_deferred_caching(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with multi-zone caching.
        It contains the following steps:
        - mock print(), Ipmi.set_fan_level() functions
        - create CPU controller on zones [0, 1] with deferred apply
        - execute _apply_fan_levels() multiple times with same and different levels
        - ASSERT: if first call does not set both zones
        - ASSERT: if second call with same level does not skip IPMI calls (caching)
        - ASSERT: if third call with different level does not update both zones
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}
        service.last_desired = []

        # CPU on zones [0, 1] with deferred apply
        cpu_fc = FanController.__new__(FanController)
        cpu_fc.name = Config.CS_CPU
        cpu_fc.config = MockControllerConfig(ipmi_zone=[0, 1])
        cpu_fc.last_level = 60
        cpu_fc.last_temp = 45.0
        cpu_fc.deferred_apply = True

        service.controllers = [cpu_fc]

        # First call - should set both zones
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 2
        assert service.applied_levels[0] == 60
        assert service.applied_levels[1] == 60

        # Second call with same level - should NOT make IPMI calls (cached)
        mock_set_fan_level.reset_mock()
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 0, "Same level should be cached"

        # Third call with different level - should update both zones
        cpu_fc.last_level = 80
        mock_set_fan_level.reset_mock()
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 2
        assert service.applied_levels[0] == 80
        assert service.applied_levels[1] == 80


# End.
