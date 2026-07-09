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
from .test_fixtures import TestData
from .test_mocks import MockedContextError, MockedContextGood
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
        "ipmi, log",
        [
            pytest.param(True, True, id="ipmi-and-log"),
            pytest.param(False, False, id="neither"),
        ],
    )
    def test_exit_func(self, mocker: MockerFixture, ipmi: bool, log: bool) -> None:
        """Positive unit test for Service.exit_func() method. It contains the following steps:
        - mock atexit.unregister(), Ipmi.set_fan_mode(), Log.msg_to_stdout(), platform end()
        - instantiate Service and conditionally attach Log and Ipmi (with mocked platform)
        - call Service.exit_func()
        - ASSERT: atexit.unregister() is called exactly once
        - ASSERT: Ipmi.set_fan_mode() is called once when ipmi is attached
        - ASSERT: platform.end() is called once to release manual mode when ipmi is attached
        - ASSERT: Log.msg_to_stdout() is called once when both ipmi and log are attached
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
        mock_platform = MagicMock()
        if ipmi:
            service.ipmi = Ipmi.__new__(Ipmi)
            service.ipmi.platform = mock_platform
        service.exit_func()
        assert mock_atexit_unregister.call_count == 1
        if ipmi:
            assert mock_ipmi_set_fan_mode.call_count == 1
            assert mock_platform.end.call_count == 1
            if log:
                assert mock_log_msg.call_count == 1

    @pytest.mark.parametrize(
        "module_list, cpufc, hdfc, gpufc, standby",
        [
            # coretemp module loaded, CPU fan controller enabled
            pytest.param("something\ncoretemp\n", True, False, False, False, id="coretemp-cpu"),
            # k10temp module loaded, CPU and GPU enabled
            pytest.param("something\nk10temp\n", True, False, True, False, id="k10temp-cpu-gpu"),
            # Both coretemp and k10temp loaded
            pytest.param("coretemp\nsomething\nk10temp\n", True, False, False, False, id="coretemp-k10temp-cpu"),
            # drivetemp module loaded, HD and GPU enabled
            pytest.param("something\ndrivetemp\n", False, True, True, False, id="drivetemp-hd-gpu"),
            # drivetemp module loaded, HD with standby guard
            pytest.param("something\ndrivetemp\n", False, True, False, True, id="drivetemp-hd-standby"),
            # No temperature module (HD only)
            pytest.param("something\n", False, True, False, False, id="no-module-hd"),
            # drivetemp module loaded, HD, GPU, and standby
            pytest.param("something\ndrivetemp\nx", False, True, True, True, id="drivetemp-hd-gpu-standby"),
            # Both coretemp and drivetemp loaded
            pytest.param("coretemp\ndrivetemp\n", True, True, False, True, id="coretemp-drivetemp-cpu-hd"),
        ],
    )
    def test_check_dependencies_p(self, mocker: MockerFixture, td: TestData, module_list: str,
                                  cpufc, hdfc, gpufc, standby: bool, tmp_path):
        """Positive unit test for Service.check_dependencies() method. It contains the following steps:
        - mock print(), builtins.open() (redirects /proc/modules to a fake module list)
        - build a temporary config file via `td` with selected controllers enabled and fake command files
        - instantiate Service and assign a Config loaded from the temp config file
        - call Service.check_dependencies()
        - ASSERT: check_dependencies() returns an empty string (no missing dependency)
        """

        def mocked_open(path: str, *args, **kwargs):
            return (
                original_open(modules, *args, **kwargs)
                if path == "/proc/modules"
                else original_open(path, *args, **kwargs)
            )

        ipmi_command = td.create_ipmi_command()
        modules = td.create_text_file(module_list)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        original_open = open
        mock_open = MagicMock(side_effect=mocked_open)
        mocker.patch("builtins.open", mock_open)

        config_content = f"[Ipmi]\ncommand = {ipmi_command}\n"
        if cpufc:
            config_content += "[CPU]\nenabled = 1\n"
        if hdfc:
            smartctl_cmd = td.create_command_file('echo "ACTIVE"')
            config_content += f"[HD]\nenabled = 1\nhd_names = /dev/sda\nsmartctl_path = {smartctl_cmd}\n"
            if standby:
                config_content += "standby_guard_enabled = 1\n"
        if gpufc:
            nvidia_smi_cmd = td.create_command_file('echo "0"')
            config_content += f"[GPU]\nenabled = 1\ngpu_type = nvidia\nnvidia_smi_path = {nvidia_smi_cmd}\n"

        config_file = tmp_path / "test.conf"
        config_file.write_text(config_content)

        service = Service()
        service.config = Config(str(config_file))

        assert service.check_dependencies() == ""

    def test_check_dependencies_disabled_gpu(self, mocker: MockerFixture, td: TestData, tmp_path):
        """Positive unit test for Service.check_dependencies() method. It contains the following steps:
        - mock print(), builtins.open() (redirects /proc/modules to a fake module list with coretemp)
        - build a temporary config file via `td` with [GPU] enabled=0 (section present but disabled)
        - instantiate Service and assign a Config loaded from the temp config file
        - call Service.check_dependencies()
        - ASSERT: check_dependencies() returns an empty string (disabled GPU section is skipped)
        """
        ipmi_command = td.create_ipmi_command()
        modules = td.create_text_file("something\ncoretemp\n")
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

    @pytest.mark.parametrize(
        "_dummy",
        [
            # Missing commands/modules conditions
            pytest.param(None, id="missing-commands-modules"),
        ],
    )
    def test_check_dependencies_returns_error_for_missing_commands(self, mocker: MockerFixture, td: TestData,
                                                                    _dummy, tmp_path):
        """Negative unit test for Service.check_dependencies() method. It contains the following steps:
        - mock print(), builtins.open() (redirects /proc/modules to a fake module list)
        - build a config with CPU/HD/GPU enabled and fake nvidia-smi / smartctl / ipmitool commands
        - delete each prerequisite in turn (nvidia-smi, smartctl, drivetemp, coretemp, ipmitool)
        - call Service.check_dependencies() after each deletion
        - ASSERT: returned error message mentions "command cannot be found!" when nvidia-smi is missing
        - ASSERT: returned error message mentions "smartctl" when smartctl is missing
        - ASSERT: returned error message mentions "drivetemp" when drivetemp module is missing
        - ASSERT: returned error message mentions "coretemp" when coretemp module is missing
        - ASSERT: returned error message mentions "ipmitool" when ipmitool is missing
        """

        def mocked_open(path: str, *args, **kwargs):
            return (
                original_open(modules, *args, **kwargs)
                if path == "/proc/modules"
                else original_open(path, *args, **kwargs)
            )

        ipmi_command = td.create_ipmi_command()
        modules = td.create_text_file("coretemp\ndrivetemp\n")
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_open = MagicMock(side_effect=mocked_open)
        original_open = open
        mocker.patch("builtins.open", mock_open)

        smartctl_cmd = td.create_command_file('echo "ACTIVE"')
        nvidia_smi_cmd = td.create_command_file('echo "0"')

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
        td.delete_file(nvidia_smi_cmd)
        check_result = service.check_dependencies()
        assert check_result.find("command cannot be found!") != -1

        # Check if `smartctl` command is not available.
        td.delete_file(smartctl_cmd)
        check_result = service.check_dependencies()
        assert check_result.find("smartctl") != -1

        # Check if `drivetemp` is not on the module list.
        modules = td.create_text_file("coretemp something")
        check_result = service.check_dependencies()
        assert check_result.find("drivetemp") != -1

        # Check if `coretemp` is not on the module list.
        modules = td.create_text_file("drivetemp something")
        check_result = service.check_dependencies()
        assert check_result.find("coretemp") != -1

        # Check if `ipmitool` is not available.
        td.delete_file(ipmi_command)
        check_result = service.check_dependencies()
        assert check_result.find("ipmitool") != -1

    @pytest.mark.parametrize(
        "command_line, exit_code",
        [
            # Help flag (exit 0)
            pytest.param("-h", 0, id="help-exit0"),
            # Version flag (exit 0)
            pytest.param("-v", 0, id="version-exit0"),
            # Invalid log level (exit 2)
            pytest.param("-l 10", 2, id="invalid-log-level-exit2"),
            # Invalid output (exit 2)
            pytest.param("-o 9", 2, id="invalid-output-exit2"),
            # Invalid output with valid log level (exit 2)
            pytest.param("-o 1 -l 10", 2, id="invalid-output-valid-log-exit2"),
            # Valid output with invalid log level (exit 2)
            pytest.param("-o 9 -l 1", 2, id="valid-output-invalid-log-exit2"),
            # Invalid config file path: special char (exit 6)
            pytest.param("-o 0 -l 3 -c &.txt", 6, id="invalid-config-path-exit6"),
            # Invalid config file path: non-existent (exit 6)
            pytest.param("-o 0 -l 3 -c ./nonexistent_folder/nonexistent_file.conf", 6, id="nonexistent-config-exit6"),
        ],
    )
    def test_run_exits_on_bad_args_or_config(self, mocker: MockerFixture, command_line: str, exit_code: int):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), argparse.ArgumentParser._print_message()
        - set sys.argv to the parametrized command line (help/version/invalid log level/invalid output/bad config path)
        - instantiate Service and call Service.run() inside pytest.raises(SystemExit)
        - ASSERT: sys.exit() code equals 0 (-h/-v), 2 (invalid args), or 6 (invalid configuration file)
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker_argumentparser_print = MagicMock()
        mocker.patch("argparse.ArgumentParser._print_message", mocker_argumentparser_print)
        sys.argv = ("smfc " + command_line).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code

    @pytest.mark.parametrize(
        "level, output, exit_code",
        [
            # Invalid log level via namespace (exit 5)
            pytest.param(10, 0, 5, id="invalid-level-via-namespace"),
            # Invalid output via namespace (exit 5)
            pytest.param(0, 9, 5, id="invalid-output-via-namespace"),
        ],
    )
    def test_run_exits_on_log_init_failure(self, mocker: MockerFixture, level: int, output: int, exit_code: int):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), argparse.ArgumentParser.parse_args() to return a Namespace with bad level/output
        - instantiate Service and call Service.run() inside pytest.raises(SystemExit)
        - ASSERT: sys.exit() code equals 5 (log initialization error)
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_parser_parse_args = MagicMock()
        mocker.patch("argparse.ArgumentParser.parse_args", mock_parser_parse_args)
        mock_parser_parse_args.return_value = Namespace(config_file="smfc.conf", ne=False, s=False, l=level, o=output)
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code

    @pytest.mark.parametrize(
        "exit_code",
        [
            # Check dependency error (exit 7)
            pytest.param(7, id="dependency-check-error-exit7"),
        ],
    )
    def test_run_exits_on_dependency_check_failure(self, mocker: MockerFixture, td: TestData, exit_code: int):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), argparse.ArgumentParser.parse_args(), smfc.Service.check_dependencies() to return "ERROR"
        - build a minimal config file via `td` with all controllers disabled
        - instantiate Service and call Service.run() inside pytest.raises(SystemExit)
        - ASSERT: sys.exit() code equals 7 (dependency check error)
        """
        my_config = ConfigParser()
        my_config[Config.CS_IPMI] = {}
        my_config[Config.CS_CPU] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_HD] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_NVME] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_GPU] = {Config.CV_ENABLED: "0"}
        my_config[Config.CS_CONST] = {Config.CV_ENABLED: "0"}
        conf_file = td.create_config_file(my_config)
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
        assert cm.value.code == exit_code

    @pytest.mark.parametrize(
        "ipmi_command, mode_delay, level_delay, exit_code",
        [
            # Non-existent IPMI command (exit 8)
            pytest.param("NON_EXIST", 0, 0, 8, id="nonexistent-ipmitool-exit8"),
            # Invalid mode_delay (exit 6 - caught by Config validation)
            pytest.param("GOOD", -1, 0, 6, id="invalid-mode-delay-exit6"),
            # Invalid level_delay (exit 6 - caught by Config validation)
            pytest.param("GOOD", 0, -1, 6, id="invalid-level-delay-exit6"),
            # Bad IPMI command (exit 8)
            pytest.param("BAD", 0, 0, 8, id="bad-ipmitool-exit8"),
            # No enabled zone (exit 10)
            pytest.param("GOOD", 0, 0, 10, id="no-enabled-zone-exit10"),
        ],
    )
    def test_run_exits_on_ipmi_init_failure_or_no_zone(self, mocker: MockerFixture, td: TestData,
                                                        ipmi_command: str, mode_delay: int, level_delay: int,
                                                        exit_code: int):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), pyudev.Context.__init__ via MockedContextGood
        - build a config with bad/missing ipmitool path or invalid mode_delay/level_delay
        - instantiate Service and call Service.run() inside pytest.raises(SystemExit)
        - ASSERT: sys.exit() code equals 8 (Ipmi initialization error), 6 (Config validation), or 10 (no enabled zone)
        """
        my_config = ConfigParser()
        if ipmi_command == "NON_EXIST":
            ipmi_command = "./non-existent-dir/non-existent-file"
        if ipmi_command == "BAD":
            ipmi_command = td.create_command_file()
        if ipmi_command == "GOOD":
            ipmi_command = td.create_ipmi_command()
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
        conf_file = td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        # A bad/empty ipmitool answers `sdr` with rc=0 but no fan sensors, so the BMC fan-readiness gate
        # would spin its full retry budget in real 5 s sleeps before failing at `bmc info`; mock it out.
        mocker.patch("time.sleep", MagicMock())
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        sys.argv = ("smfc.py -o 0 -nd -ne -c " + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code

    def test_check_dependencies_amd_p(self, mocker: MockerFixture, td: TestData, tmp_path):
        """Positive unit test for Service.check_dependencies() method with AMD GPU. It contains the following steps:
        - mock print(), builtins.open() (redirects /proc/modules to a fake module list with coretemp)
        - build a config with [GPU] enabled=1 / gpu_type=amd and a fake rocm-smi command via `td`
        - instantiate Service and assign a Config loaded from the temp config file
        - call Service.check_dependencies()
        - ASSERT: check_dependencies() returns an empty string (no missing dependency for AMD GPU)
        """

        def mocked_open(path: str, *args, **kwargs):
            return (
                original_open(modules, *args, **kwargs)
                if path == "/proc/modules"
                else original_open(path, *args, **kwargs)
            )

        ipmi_command = td.create_ipmi_command()
        modules = td.create_text_file("something\ncoretemp\n")
        rocm_smi_cmd = td.create_command_file('echo "0"')
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
        assert service.check_dependencies() == ""

    def test_check_dependencies_invalid_gpu_type_n(self, mocker: MockerFixture, td: TestData, tmp_path):
        """Negative unit test for Config parsing exercised through Service setup with invalid gpu_type. It contains the
        following steps:
        - mock print()
        - build a config with [GPU] enabled=1 / gpu_type=invalid
        - instantiate Config(str(config_file)) inside pytest.raises(ValueError)
        - ASSERT: ValueError is raised and its message contains the substring "invalid"
        """

        ipmi_command = td.create_ipmi_command()
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)

        config_content = (f"[Ipmi]\ncommand = {ipmi_command}\n"
                          f"[GPU]\nenabled = 1\ngpu_type = invalid\n")
        config_file = tmp_path / "test.conf"
        config_file.write_text(config_content)

        with pytest.raises(ValueError) as exc_info:
            Config(str(config_file))
        assert "invalid" in str(exc_info.value)

    @pytest.mark.parametrize(
        "exit_code",
        [
            # pyudev.Context init error (exit 9)
            pytest.param(9, id="pyudev-init-error-exit9"),
        ],
    )
    def test_run_exits_on_pyudev_init_failure(self, mocker: MockerFixture, td: TestData, exit_code: int):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), pyudev.Context.__init__ via MockedContextError (forces pyudev init to fail)
        - build a minimal config file via `td` with all controllers disabled and a fake ipmitool command
        - instantiate Service and call Service.run() inside pytest.raises(SystemExit)
        - ASSERT: sys.exit() code equals 9 (pyudev.Context() init error)
        """
        my_config = ConfigParser()
        ipmi_command = td.create_ipmi_command()
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
        conf_file = td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch("pyudev.Context.__init__", MockedContextError.__init__)
        sys.argv = ("smfc.py -o 0 -ne -nd -c " + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code

    @pytest.mark.parametrize(
        "cpufc, hdfc, nvmefc, gpufc, constfc, exit_code",
        [
            # CPU and GPU enabled
            pytest.param(True, False, False, True, False, 100, id="cpu-gpu"),
            # HD and CONST enabled
            pytest.param(False, True, False, False, True, 100, id="hd-const"),
            # CPU and GPU enabled (duplicate)
            pytest.param(True, False, False, True, False, 100, id="cpu-gpu-alt"),
            # CPU and NVME enabled
            pytest.param(True, False, True, False, False, 100, id="cpu-nvme"),
            # All controllers enabled
            pytest.param(True, True, True, True, True, 100, id="all-controllers"),
        ],
    )
    def test_run_happy_path(self, mocker: MockerFixture, td: TestData, cpufc: bool, hdfc: bool, nvmefc: bool,
                            gpufc: bool, constfc: bool, exit_code: int):
        """Positive unit test for Service.run() method. It contains the following steps:
        - mock print(), time.sleep() (exits with code 100 after 10 iterations), smfc.service.Exporter
        - mock pyudev.Context.__init__ via MockedContextGood and CpuFc/HdFc/NvmeFc/GpuFc/ConstFc.__init__
        - build a full config via `td` (fake ipmitool, smartctl, nvidia-smi, cpu/hd/nvme hwmon data)
          enabling the parametrized combination of controllers
        - instantiate Service and call Service.run() inside pytest.raises(SystemExit)
        - ASSERT: sys.exit() code equals 100 (the main loop ran 10 iterations and exited via mocked sleep)
        """

        # pylint: disable=unused-argument
        def mocked_sleep(*args):
            """Mocked time.sleep() function. Exists at the 10th call."""
            self.sleep_counter += 1
            if self.sleep_counter >= 10:
                sys.exit(100)

        def mocked_cpufc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg) -> None:
            nonlocal td
            self.hwmon_path = td.cpu_files
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(td.cpu_files))

        def mocked_hdfc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg, sudo: bool) -> None:
            nonlocal td
            self.hd_device_names = td.hd_name_list
            self.hwmon_path = td.hd_files
            self.sudo = sudo
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(td.hd_files))
            self.standby_array_states = [False] * self.count
            self.standby_flag = False
            self.standby_change_timestamp = time.monotonic()

        def mocked_gpufc_init(self, log: Log, ipmi: Ipmi, cfg) -> None:
            nonlocal td
            self.smi_called = 0
            self.hwmon_path = []
            self.gpu_temperature = []
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(cfg.gpu_device_ids))

        def mocked_nvmefc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg) -> None:
            nonlocal td
            self.nvme_device_names = td.nvme_name_list
            self.hwmon_path = td.nvme_files
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(td.nvme_files))

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

        # Force mode initial fan mode 0 for setting new FULL mode during the test.
        cmd_ipmi = td.create_command_file(
            'if [[ $1 = "bmc" && $2 = "info" ]] ; then\n'
            "cat << 'BMCEOF'\n" + BMC_INFO_OUTPUT +
            "BMCEOF\n"
            "exit 0\n"
            "fi\n"
            # `sdr` must report a live fan sensor so the BMC fan-readiness gate passes without sleeping
            # (otherwise its retry sleeps would be counted by mocked_sleep and exit before the main loop).
            'if [[ $1 = "sdr" ]] ; then\n'
            'echo "FAN1             | 500 RPM           | ok"\n'
            "exit 0\n"
            "fi\n"
            'echo "0"'
        )
        cmd_smart = td.create_smart_command()
        # create_command_file('echo "ACTIVE"'))
        cmd_nvidia = td.create_nvidia_smi_command(1)
        td.create_cpu_data(1)
        td.create_hd_data(8)
        td.create_nvme_data(2)
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
            Config.CV_HD_NAMES: td.hd_names,
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
            Config.CV_NVME_NAMES: td.nvme_names,
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
        my_config[Config.CS_EXPORTER] = {
            Config.CV_EXPORTER_ENABLED: "1",
            Config.CV_EXPORTER_BIND_ADDRESS: "127.0.0.1",
            Config.CV_EXPORTER_PORT: "9099",
        }
        conf_file = td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_time_sleep = MagicMock()
        mock_time_sleep.side_effect = mocked_sleep
        mocker.patch("time.sleep", mock_time_sleep)
        mocker.patch("smfc.service.Exporter", MagicMock())
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
        assert cm.value.code == exit_code

    def test_run_propagates_controller_exception(self, mocker: MockerFixture, td: TestData):
        """Negative unit test for Service.run() method when a controller's fc.run() raises mid-loop. It contains the
        following steps:
        - mock print(), time.sleep() (counted but not exited), smfc.service.Exporter, pyudev.Context.__init__ via
          MockedContextGood, and CpuFc.__init__ to skip real hwmon discovery
        - mock smfc.CpuFc.run via mocker.patch with a MagicMock whose side_effect raises RuntimeError("sensor gone")
          on the very first call from the main loop
        - build a minimal CPU-only config via `td` (fake ipmitool + one CPU hwmon file) and write it to disk
        - instantiate Service and invoke Service.run()
        - ASSERT: RuntimeError("sensor gone") propagates out of Service.run() unhandled (the main loop has no
          exception handler around fc.run(), so a single controller fault terminates the daemon)
        - ASSERT: smfc.CpuFc.run was called exactly once before the exception escaped
        """

        # pylint: disable=unused-argument
        def mocked_cpufc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg) -> None:
            nonlocal td
            self.hwmon_path = td.cpu_files
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(td.cpu_files))
        # pylint: enable=unused-argument

        # Force initial fan mode 0 so Service sets FULL mode once, then bmc-info supplies a stub product name.
        cmd_ipmi = td.create_command_file(
            'if [[ $1 = "bmc" && $2 = "info" ]] ; then\n'
            "cat << 'BMCEOF'\n" + BMC_INFO_OUTPUT +
            "BMCEOF\n"
            "exit 0\n"
            "fi\n"
            # `sdr` must report a live fan sensor so the BMC fan-readiness gate passes without sleeping
            # (otherwise its retry sleeps would be counted by mocked_sleep and exit before the main loop).
            'if [[ $1 = "sdr" ]] ; then\n'
            'echo "FAN1             | 500 RPM           | ok"\n'
            "exit 0\n"
            "fi\n"
            'echo "0"'
        )
        td.create_cpu_data(1)
        my_config = ConfigParser()
        my_config[Config.CS_IPMI] = {
            Config.CV_IPMI_COMMAND: cmd_ipmi,
            Config.CV_IPMI_FAN_MODE_DELAY: "0",
            Config.CV_IPMI_FAN_LEVEL_DELAY: "0",
        }
        my_config[Config.CS_CPU] = {
            Config.CV_ENABLED: "True",
            Config.CV_TEMP_CALC: "1",
            Config.CV_STEPS: "5",
            Config.CV_SENSITIVITY: "5",
            Config.CV_POLLING: "0",
            Config.CV_MIN_TEMP: "30",
            Config.CV_MAX_TEMP: "60",
            Config.CV_MIN_LEVEL: "35",
            Config.CV_MAX_LEVEL: "100",
        }
        conf_file = td.create_config_file(my_config)
        mocker.patch("builtins.print", MagicMock())
        mocker.patch("time.sleep", MagicMock())
        mocker.patch("smfc.service.Exporter", MagicMock())
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        mocker.patch("smfc.CpuFc.__init__", mocked_cpufc_init)
        mock_run = MagicMock(side_effect=RuntimeError("sensor gone"))
        mocker.patch("smfc.CpuFc.run", mock_run)
        sys.argv = ("smfc.py -o 0 -l 4 -ne -nd -c " + conf_file).split()
        service = Service()
        with pytest.raises(RuntimeError, match="sensor gone"):
            service.run()
        assert mock_run.call_count == 1

    @pytest.mark.parametrize(
        "startup_mode, expect_startup_set",
        [
            # BMC already settled in FULL (warm restart): the startup set is skipped.
            pytest.param(Ipmi.FULL_MODE, False, id="already-full-skips"),
            # BMC reports a non-FULL default (cold boot): the startup set fires once.
            pytest.param(Ipmi.STANDARD_MODE, True, id="not-full-sets"),
        ],
    )
    def test_run_startup_fan_mode_conditional(self, mocker: MockerFixture, td: TestData,
                                              startup_mode: int, expect_startup_set: bool):
        """Positive unit test for the conditional FULL-mode set at Service.run() startup. It contains the following
        steps:
        - mock print(), time.sleep() (exits with code 100 after 3 iterations), smfc.service.Exporter,
          pyudev.Context.__init__ via MockedContextGood, and CpuFc.__init__ to skip real hwmon discovery
        - patch smfc.Ipmi.get_fan_mode with a staged function returning `startup_mode` on the first (startup) read
          and Ipmi.FULL_MODE afterwards, so the main loop's _check_fan_mode() sees no drift and stays quiet
        - patch smfc.Ipmi.set_fan_mode with a MagicMock spy
        - build a minimal CPU-only config via `td` (fake ipmitool whose `sdr` reports a live fan so the BMC gate
          passes without sleeping) and write it to disk
        - instantiate Service and invoke Service.run() inside pytest.raises(SystemExit)
        - ASSERT: sys.exit() code equals 100 (the main loop ran and exited via mocked sleep)
        - ASSERT: when startup_mode is FULL, set_fan_mode() is never called (redundant startup write skipped)
        - ASSERT: when startup_mode is not FULL, set_fan_mode() is called exactly once with Ipmi.FULL_MODE
        - ASSERT: service.last_fan_mode holds Ipmi.FULL_MODE after startup in both cases
        """

        # pylint: disable=unused-argument
        def mocked_cpufc_init(self, log: Log, udevc: Context, ipmi: Ipmi, cfg) -> None:
            nonlocal td
            self.hwmon_path = td.cpu_files
            self.config = cfg
            FanController.__init__(self, log, ipmi, cfg.section, len(td.cpu_files))

        def mocked_sleep(*args):
            """Mocked time.sleep() function. Exits at the 3rd call."""
            self.sleep_counter += 1
            if self.sleep_counter >= 3:
                sys.exit(100)

        def staged_get_fan_mode(_self) -> int:
            """Return the startup mode on the first read, then a steady FULL so the loop sees no drift."""
            if seen["first"]:
                seen["first"] = False
                return startup_mode
            return Ipmi.FULL_MODE
        # pylint: enable=unused-argument

        seen = {"first": True}
        cmd_ipmi = td.create_command_file(
            'if [[ $1 = "bmc" && $2 = "info" ]] ; then\n'
            "cat << 'BMCEOF'\n" + BMC_INFO_OUTPUT +
            "BMCEOF\n"
            "exit 0\n"
            "fi\n"
            # `sdr` must report a live fan sensor so the BMC fan-readiness gate passes without sleeping.
            'if [[ $1 = "sdr" ]] ; then\n'
            'echo "FAN1             | 500 RPM           | ok"\n'
            "exit 0\n"
            "fi\n"
            'echo "0"'
        )
        td.create_cpu_data(1)
        my_config = ConfigParser()
        my_config[Config.CS_IPMI] = {
            Config.CV_IPMI_COMMAND: cmd_ipmi,
            Config.CV_IPMI_FAN_MODE_DELAY: "0",
            Config.CV_IPMI_FAN_LEVEL_DELAY: "0",
        }
        my_config[Config.CS_CPU] = {
            Config.CV_ENABLED: "True",
            Config.CV_TEMP_CALC: "1",
            Config.CV_STEPS: "5",
            Config.CV_SENSITIVITY: "5",
            Config.CV_POLLING: "0",
            Config.CV_MIN_TEMP: "30",
            Config.CV_MAX_TEMP: "60",
            Config.CV_MIN_LEVEL: "35",
            Config.CV_MAX_LEVEL: "100",
        }
        conf_file = td.create_config_file(my_config)
        mocker.patch("builtins.print", MagicMock())
        mocker.patch("time.sleep", MagicMock(side_effect=mocked_sleep))
        mocker.patch("smfc.service.Exporter", MagicMock())
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        mocker.patch("smfc.CpuFc.__init__", mocked_cpufc_init)
        mocker.patch("smfc.Ipmi.get_fan_mode", staged_get_fan_mode)
        mock_set = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_mode", mock_set)
        self.sleep_counter = 0
        sys.argv = ("smfc.py -o 0 -l 4 -ne -nd -c " + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == 100
        if expect_startup_set:
            assert mock_set.call_count == 1, "non-FULL startup mode must set FULL exactly once"
            assert mock_set.call_args.args[0] == Ipmi.FULL_MODE, "startup set must target FULL"
        else:
            mock_set.assert_not_called()
        assert service.last_fan_mode == Ipmi.FULL_MODE, "last_fan_mode must hold FULL after startup"

    def _make_service_for_fan_mode_check(self, mocker: MockerFixture, enforce: bool) -> Service:
        """Build a minimally-initialized Service for unit-testing _check_fan_mode()."""
        mocker.patch("builtins.print", MagicMock())
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        # Real Ipmi instance with attributes we need for the helper, no actual ipmitool.
        service.ipmi = Ipmi.__new__(Ipmi)
        # Stub a minimal config object — only ipmi.enforce_fan_mode is read by _check_fan_mode().
        service.config = MagicMock()
        service.config.ipmi.enforce_fan_mode = enforce
        service.applied_levels = {0: 45, 1: 55}
        service.last_fan_mode = Ipmi.FULL_MODE
        service.last_fan_mode_at = time.monotonic()
        service.fan_mode_enforced_count = 0
        return service

    def test_check_fan_mode_no_drift(self, mocker: MockerFixture):
        """Positive unit test for Service._check_fan_mode() method. It contains the following steps:
        - mock print(), Ipmi.get_fan_mode() returning FULL_MODE, Ipmi.set_fan_mode(), Ipmi.set_fan_level()
        - build a Service via _make_service_for_fan_mode_check() with enforce=True
        - call Service._check_fan_mode()
        - ASSERT: service.last_fan_mode still equals Ipmi.FULL_MODE (cache holds FULL)
        - ASSERT: Ipmi.set_fan_mode() is not called (no recovery needed)
        - ASSERT: Ipmi.set_fan_level() is not called (no zone re-apply needed)
        """
        f = "TestService.test_check_fan_mode_no_drift"
        service = self._make_service_for_fan_mode_check(mocker, enforce=True)
        mocker.patch("smfc.Ipmi.get_fan_mode", MagicMock(return_value=Ipmi.FULL_MODE))
        mock_set_mode = MagicMock()
        mock_set_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_mode", mock_set_mode)
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_level)
        service._check_fan_mode()  # pylint: disable=protected-access
        assert service.last_fan_mode == Ipmi.FULL_MODE, f"{f}: cache must hold FULL"
        assert mock_set_mode.call_count == 0, f"{f}: no recovery expected"
        assert mock_set_level.call_count == 0, f"{f}: no zone re-apply expected"

    def test_check_fan_mode_drift_recovers(self, mocker: MockerFixture):
        """Positive unit test for Service._check_fan_mode() method. It contains the following steps:
        - mock print(), Ipmi.get_fan_mode() returning STANDARD_MODE (drift), Ipmi.set_fan_mode(), Ipmi.set_fan_level()
        - build a Service via _make_service_for_fan_mode_check() with enforce=True and applied_levels={0:45,1:55}
        - call Service._check_fan_mode()
        - ASSERT: Ipmi.set_fan_mode() is called exactly once
        - ASSERT: Ipmi.set_fan_mode() is called with Ipmi.FULL_MODE (mode restored)
        - ASSERT: Ipmi.set_fan_level() is called once per cached zone in applied_levels
        - ASSERT: set of zones passed to set_fan_level() equals service.applied_levels.keys()
        - ASSERT: service.last_fan_mode is updated back to Ipmi.FULL_MODE
        - ASSERT: service.fan_mode_enforced_count is incremented by one per excursion
        """
        f = "TestService.test_check_fan_mode_drift_recovers"
        service = self._make_service_for_fan_mode_check(mocker, enforce=True)
        mocker.patch("smfc.Ipmi.get_fan_mode", MagicMock(return_value=Ipmi.STANDARD_MODE))
        mock_set_mode = MagicMock()
        mock_set_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_mode", mock_set_mode)
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_level)
        service._check_fan_mode()  # pylint: disable=protected-access
        assert mock_set_mode.call_count == 1, f"{f}: set_fan_mode should be called once"
        assert mock_set_mode.call_args.args[0] == Ipmi.FULL_MODE, f"{f}: must restore FULL"
        # set_fan_level called once per applied_levels entry.
        assert mock_set_level.call_count == len(service.applied_levels), \
            f"{f}: every cached zone should be re-applied"
        called_zones = {c.args[0] for c in mock_set_level.call_args_list}
        assert called_zones == set(service.applied_levels.keys()), f"{f}: re-apply set must match cache"
        assert service.last_fan_mode == Ipmi.FULL_MODE, f"{f}: cache should reflect restored mode"
        assert service.fan_mode_enforced_count == 1, f"{f}: enforcement counter should increment once per excursion"

    def test_check_fan_mode_drift_exits_when_disabled(self, mocker: MockerFixture):
        """Negative unit test for Service._check_fan_mode() method. It contains the following steps:
        - mock print(), Ipmi.get_fan_mode() returning OPTIMAL_MODE (drift), Ipmi.set_fan_mode()
        - build a Service via _make_service_for_fan_mode_check() with enforce=False
        - call Service._check_fan_mode() inside pytest.raises(SystemExit)
        - ASSERT: sys.exit() code equals 11 (drift detected with enforcement disabled)
        - ASSERT: Ipmi.set_fan_mode() is not called (no recovery attempt when disabled)
        """
        f = "TestService.test_check_fan_mode_drift_exits_when_disabled"
        service = self._make_service_for_fan_mode_check(mocker, enforce=False)
        mocker.patch("smfc.Ipmi.get_fan_mode", MagicMock(return_value=Ipmi.OPTIMAL_MODE))
        mock_set_mode = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_mode", mock_set_mode)
        with pytest.raises(SystemExit) as cm:
            service._check_fan_mode()  # pylint: disable=protected-access
        assert cm.value.code == 11, f"{f}: must exit with code 11"
        assert mock_set_mode.call_count == 0, f"{f}: must not attempt recovery when disabled"

    def test_check_fan_mode_get_mode_transient_error(self, mocker: MockerFixture):
        """Negative unit test for Service._check_fan_mode() method. It contains the following steps:
        - mock print(), Ipmi.get_fan_mode() raising RuntimeError("ipmitool error..."), Ipmi.set_fan_mode()
        - build a Service via _make_service_for_fan_mode_check() with enforce=True and capture pre-call cache
        - call Service._check_fan_mode() (no SystemExit expected)
        - ASSERT: service.last_fan_mode is unchanged after the transient error
        - ASSERT: service.last_fan_mode_at timestamp is unchanged after the transient error
        - ASSERT: Ipmi.set_fan_mode() is not called (no recovery attempt on read failure)
        """
        f = "TestService.test_check_fan_mode_get_mode_transient_error"
        service = self._make_service_for_fan_mode_check(mocker, enforce=True)
        before_mode = service.last_fan_mode
        before_at = service.last_fan_mode_at
        mocker.patch("smfc.Ipmi.get_fan_mode",
                     MagicMock(side_effect=RuntimeError("ipmitool error (1): permission denied.")))
        mock_set_mode = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_mode", mock_set_mode)
        service._check_fan_mode()  # pylint: disable=protected-access
        assert service.last_fan_mode == before_mode, f"{f}: cache must not change on transient error"
        assert service.last_fan_mode_at == before_at, f"{f}: timestamp must not advance on transient error"
        assert mock_set_mode.call_count == 0, f"{f}: must not attempt recovery on read failure"

    def test_check_fan_mode_recovery_transient_error(self, mocker: MockerFixture):
        """Negative unit test for Service._check_fan_mode() method. It contains the following steps:
        - mock print(), Ipmi.get_fan_mode() returning STANDARD_MODE (drift),
          Ipmi.set_fan_mode() raising RuntimeError, Ipmi.set_fan_level()
        - build a Service via _make_service_for_fan_mode_check() with enforce=True
        - call Service._check_fan_mode() (no SystemExit expected — loop is the recovery mechanism)
        - ASSERT: service.last_fan_mode holds Ipmi.STANDARD_MODE (drifted mode) so the next iteration retries
        - ASSERT: Ipmi.set_fan_level() is not called (no zone re-apply when set_fan_mode() failed)
        """
        f = "TestService.test_check_fan_mode_recovery_transient_error"
        service = self._make_service_for_fan_mode_check(mocker, enforce=True)
        mocker.patch("smfc.Ipmi.get_fan_mode", MagicMock(return_value=Ipmi.STANDARD_MODE))
        mock_set_mode = MagicMock(side_effect=RuntimeError("ipmitool error (1): try again."))
        mock_set_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_mode", mock_set_mode)
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_level)
        # No SystemExit; the loop is the recovery mechanism.
        service._check_fan_mode()  # pylint: disable=protected-access
        # last_fan_mode should reflect the failed reading (drifted), so the next iteration retries.
        assert service.last_fan_mode == Ipmi.STANDARD_MODE, \
            f"{f}: cache must hold the drifted mode so the next iteration retries"
        assert mock_set_level.call_count == 0, f"{f}: must not re-apply levels when set_fan_mode failed"

    def test_exporter_disabled_does_not_start(self, mocker: MockerFixture):
        """Positive unit test for Service._start_exporter() guard. It contains the following steps:
        - mock Service._start_exporter() via mocker.patch.object
        - instantiate Service, attach a MagicMock config with exporter.enabled = False, set exporter = None
        - execute the call-site guard (if service.config.exporter.enabled: service._start_exporter())
        - ASSERT: service.exporter remains None when exporter is disabled
        - ASSERT: Service._start_exporter() is not called when exporter is disabled
        """
        f = "TestService.test_exporter_disabled_does_not_start"
        mock_start = MagicMock()
        service = Service()
        service.config = MagicMock()
        service.config.exporter.enabled = False
        service.exporter = None
        mocker.patch.object(service, "_start_exporter", mock_start)
        if service.config.exporter.enabled:
            service._start_exporter()  # pylint: disable=protected-access  # pragma: no cover
        assert service.exporter is None, f"{f}: exporter must be None when disabled"
        assert mock_start.called is False, f"{f}: _start_exporter() must not be called when disabled"

    def test_exporter_enabled_started(self, mocker: MockerFixture):
        """Positive unit test for Service._start_exporter() method. It contains the following steps:
        - mock smfc.service.Exporter class to return a MagicMock instance
        - instantiate Service with a Log and a MagicMock config (exporter.enabled=True, bind_address, port)
        - call Service._start_exporter()
        - ASSERT: Exporter class is constructed exactly once
        - ASSERT: Exporter.start() is called exactly once on the constructed instance
        - ASSERT: Exporter is constructed with kwargs bind_address="127.0.0.1"
        - ASSERT: Exporter is constructed with kwargs port=9099
        - ASSERT: service.exporter is the Exporter instance returned by the mocked class
        """
        f = "TestService.test_exporter_enabled_started"
        mock_exporter = MagicMock()
        mock_exporter_cls = MagicMock(return_value=mock_exporter)
        mocker.patch("smfc.service.Exporter", mock_exporter_cls)
        service = Service()
        service.log = Log(Log.LOG_CONFIG, Log.LOG_STDOUT)
        service.config = MagicMock()
        service.config.exporter.enabled = True
        service.config.exporter.bind_address = "127.0.0.1"
        service.config.exporter.port = 9099
        service._start_exporter()  # pylint: disable=protected-access
        assert mock_exporter_cls.call_count == 1, f"{f}: Exporter() must be constructed once"
        assert mock_exporter.start.call_count == 1, f"{f}: start() must be called once"
        kwargs = mock_exporter_cls.call_args.kwargs
        assert kwargs["bind_address"] == "127.0.0.1"
        assert kwargs["port"] == 9099
        assert service.exporter is mock_exporter

    def test_exporter_bind_failure_does_not_kill_service(self, mocker: MockerFixture):
        """Negative unit test for Service._start_exporter() method. It contains the following steps:
        - mock smfc.service.Exporter to return an instance whose start() raises OSError("port already in use")
        - instantiate Service with a Log and a MagicMock config (exporter.enabled=True)
        - call Service._start_exporter() (no exception should propagate)
        - ASSERT: service.exporter is None after the bind failure (error swallowed, daemon continues)
        """
        f = "TestService.test_exporter_bind_failure_does_not_kill_service"
        mock_exporter = MagicMock()
        mock_exporter.start.side_effect = OSError("port already in use")
        mock_exporter_cls = MagicMock(return_value=mock_exporter)
        mocker.patch("smfc.service.Exporter", mock_exporter_cls)
        service = Service()
        service.log = Log(Log.LOG_NONE, Log.LOG_STDOUT)
        service.config = MagicMock()
        service.config.exporter.enabled = True
        service.config.exporter.bind_address = "0.0.0.0"
        service.config.exporter.port = 9099
        service._start_exporter()  # pylint: disable=protected-access
        assert service.exporter is None, f"{f}: exporter must be None after a bind failure"

    def test_exit_func_stops_running_exporter(self, mocker: MockerFixture):
        """Positive unit test for Service.exit_func() method. It contains the following steps:
        - mock print()
        - instantiate Service with a Log, a MagicMock ipmi and a MagicMock exporter
        - call Service.exit_func()
        - ASSERT: exporter.stop() is called exactly once
        - ASSERT: ipmi.set_fan_mode() is called with Ipmi.FULL_MODE (BMC reset to FULL)
        """
        mocker.patch("builtins.print", MagicMock())
        service = Service()
        service.log = Log(Log.LOG_INFO, Log.LOG_STDOUT)
        service.ipmi = MagicMock()
        service.exporter = MagicMock()
        service.exit_func()
        # Exporter was stopped, then BMC reset to FULL.
        assert service.exporter.stop.call_count == 1
        service.ipmi.set_fan_mode.assert_called_with(Ipmi.FULL_MODE)

    def test_exit_func_tolerates_exporter_stop_failure(self, mocker: MockerFixture):
        """Negative unit test for Service.exit_func() method. It contains the following steps:
        - mock print()
        - instantiate Service with a Log, a MagicMock ipmi and a MagicMock exporter whose stop() raises RuntimeError
        - call Service.exit_func() (no exception should propagate)
        - ASSERT: ipmi.set_fan_mode() is still called with Ipmi.FULL_MODE despite exporter.stop() failing
        """
        mocker.patch("builtins.print", MagicMock())
        service = Service()
        service.log = Log(Log.LOG_INFO, Log.LOG_STDOUT)
        service.ipmi = MagicMock()
        service.exporter = MagicMock()
        service.exporter.stop.side_effect = RuntimeError("stop failed")
        service.exit_func()
        # set_fan_mode still called even though stop() raised.
        service.ipmi.set_fan_mode.assert_called_with(Ipmi.FULL_MODE)

    def test_collect_desired_levels(self, mocker: MockerFixture):
        """Positive unit test for Service._collect_desired_levels() method. It contains the following steps:
        - mock print()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi), set applied_levels={} and last_desired=[]
        - attach three controllers: CPU (last_level=60), HD (last_level=0), CONST (last_level=50)
        - call Service._collect_desired_levels()
        - ASSERT: CPU controller is present in the collected names (level > 0)
        - ASSERT: HD controller is absent from the collected names (last_level=0 is skipped)
        - ASSERT: CONST controller is present in the collected names (ConstFc with level > 0)
        """
        f = "TestService.test_collect_desired_levels"
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

        const_fc = ConstFc.__new__(ConstFc)
        const_fc.name = Config.CS_CONST
        const_fc.config = MockControllerConfig(ipmi_zone=[1])
        const_fc.last_level = 50
        const_fc.last_temp = 0.0
        const_fc.deferred_apply = True

        service.controllers = [cpu_fc, hd_fc, const_fc]

        levels = service._collect_desired_levels()  # pylint: disable=protected-access
        names = [name for name, _, _, _ in levels]
        assert Config.CS_CPU in names, f"{f}: CPU controller should be collected"
        assert Config.CS_HD not in names, f"{f}: HD controller with level 0 should be skipped"
        assert Config.CS_CONST in names, f"{f}: ConstFc with level > 0 should be collected"

    def test_apply_fan_levels_shared_zone(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with shared zone arbitration. It contains the
        following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach two deferred controllers on zone 1: HD at 45%/38.0C and NVME at 70%/42.5C
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (1, 70) — the higher level wins
        - ASSERT: service.applied_levels[1] is cached as 70
        - ASSERT: log output contains "winner: NVME=70%/42.5C"
        - ASSERT: log output contains "losers: HD=45%/38.0C"
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
        f = "TestService.test_apply_fan_levels_shared_zone"
        assert service.applied_levels[1] == 70, f"{f}: zone 1 should cache level 70"
        # Log should mention the winner and losers for shared zones with temperatures
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: NVME=70%/42.5C" in log_output, f"{f}: shared zone log should mention winner with temp"
        assert "losers: HD=45%/38.0C" in log_output, f"{f}: shared zone log should mention losers with temp"

    def test_apply_fan_levels_single_zone(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with single-controller zone. It contains the
        following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach a single deferred CPU controller on zone 0 at 60%/45.0C
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (0, 60)
        - ASSERT: service.applied_levels[0] is cached as 60
        - ASSERT: log output contains "IPMI zone [0]: new level = 60% (CPU=45.0C)" (single-contributor log)
        """
        f = "TestService.test_apply_fan_levels_single_zone"
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
        assert service.applied_levels[0] == 60, f"{f}: zone 0 should cache level 60"
        # Single-contributor zone should log the fan level with temperature
        log_output = str(mock_log_msg.call_args_list)
        assert "IPMI zone [0]: new level = 60% (CPU=45.0C)" in log_output, f"{f}: log should contain level and temp"

    def test_apply_fan_levels_single_zone_const(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with single CONST controller. It contains the
        following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach a single deferred CONST controller on zone 0 at level=50
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (0, 50)
        - ASSERT: service.applied_levels[0] is cached as 50
        - ASSERT: log output contains "IPMI zone [0]: new level = 50% (CONST)" (no temperature for CONST)
        """
        f = "TestService.test_apply_fan_levels_single_zone_const"
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
        assert service.applied_levels[0] == 50, f"{f}: zone 0 should cache level 50"
        # Single CONST zone should log without temperature
        log_output = str(mock_log_msg.call_args_list)
        assert "IPMI zone [0]: new level = 50% (CONST)" in log_output, f"{f}: log should not include temperature"

    def test_apply_fan_levels_shared_zone_const_winner(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with CONST winning a shared zone. It contains the
        following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach two deferred controllers on zone 1: HD at 45%/38.0C and CONST at 80%
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (1, 80) — CONST wins
        - ASSERT: service.applied_levels[1] is cached as 80
        - ASSERT: log output contains "winner: CONST=80%" (no temperature for CONST winner)
        - ASSERT: log output contains "losers: HD=45%/38.0C"
        """
        f = "TestService.test_apply_fan_levels_shared_zone_const_winner"
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
        assert service.applied_levels[1] == 80, f"{f}: zone 1 should cache level 80"
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: CONST=80%" in log_output, f"{f}: CONST winner should have no temperature"
        assert "losers: HD=45%/38.0C" in log_output, f"{f}: loser should show HD with temp"

    def test_apply_fan_levels_shared_zone_const_loser(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with CONST losing a shared zone. It contains the
        following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach two deferred controllers on zone 1: HD at 70%/55.0C and CONST at 40%
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (1, 70) — HD wins
        - ASSERT: service.applied_levels[1] is cached as 70
        - ASSERT: log output contains "winner: HD=70%/55.0C"
        - ASSERT: log output contains "losers: CONST=40%" (no temperature for CONST loser)
        """
        f = "TestService.test_apply_fan_levels_shared_zone_const_loser"
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
        assert service.applied_levels[1] == 70, f"{f}: zone 1 should cache level 70"
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: HD=70%/55.0C" in log_output, f"{f}: HD should win at 70%"
        assert "losers: CONST=40%" in log_output, f"{f}: CONST loser should have no temperature"

    def test_apply_fan_levels_skips_non_deferred(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with mixed deferred/non-deferred controllers. It
        contains the following steps:
        - mock print(), Ipmi.set_fan_level()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach CPU (deferred=True) on zone 0 at 60% and HD (deferred=False) on zone 1 at 40%
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (0, 60) — only deferred CPU triggers IPMI
        - ASSERT: zone 0 is present in service.applied_levels (cached)
        - ASSERT: zone 1 is absent from service.applied_levels (non-deferred HD applies its own level)
        """
        f = "TestService.test_apply_fan_levels_skips_non_deferred"
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
        assert 0 in service.applied_levels, f"{f}: zone 0 should be cached"
        assert 1 not in service.applied_levels, f"{f}: zone 1 should not be cached"

    def test_apply_fan_levels_cache(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with level caching. It contains the following
        steps:
        - mock print(), Ipmi.set_fan_level()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); pre-seed applied_levels={1: 70} and last_desired=[]
        - attach a single deferred HD controller on zone 1 at 70% (same as cached level)
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is not called (level unchanged, IPMI call skipped by cache)
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
        f = "TestService.test_apply_fan_levels_cache"
        assert mock_set_fan_level.call_count == 0, f"{f}: should skip IPMI call when level is cached"

    def test_apply_fan_levels_three_controllers(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with three controllers on a shared zone. It
        contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach three deferred controllers on zone 1: CPU 40%/50.0C, HD 60%/38.0C, NVME 50%/42.0C
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (1, 60) — HD wins as highest
        - ASSERT: service.applied_levels[1] is cached as 60
        - ASSERT: log output contains "winner: HD=60%/38.0C"
        - ASSERT: log output contains "CPU=40%/50.0C" as a loser
        - ASSERT: log output contains "NVME=50%/42.0C" as a loser
        """
        f = "TestService.test_apply_fan_levels_three_controllers"
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
        assert service.applied_levels[1] == 60, f"{f}: zone 1 should cache level 60"
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: HD=60%/38.0C" in log_output, f"{f}: HD should be winner"
        assert "CPU=40%/50.0C" in log_output, f"{f}: CPU should be a loser"
        assert "NVME=50%/42.0C" in log_output, f"{f}: NVME should be a loser"

    def test_apply_fan_levels_equal_levels(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with tied levels. It contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach two deferred controllers on zone 1 with identical 70%: CPU at 55.0C and HD at 40.0C
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (1, 70)
        - ASSERT: service.applied_levels[1] is cached as 70
        - ASSERT: log output contains "winner: CPU=70%/55.0C" (first-collected wins because tie-break uses >)
        - ASSERT: log output contains "losers: HD=70%/40.0C"
        """
        f = "TestService.test_apply_fan_levels_equal_levels"
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
        assert service.applied_levels[1] == 70, f"{f}: zone 1 should cache level 70"
        # First collected controller (CPU) should be the winner (uses > not >=)
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: CPU=70%/55.0C" in log_output, f"{f}: CPU should win the tie"
        assert "losers: HD=70%/40.0C" in log_output, f"{f}: HD should be the loser in tie"

    def test_apply_fan_levels_multi_zone_partial_shared(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with partial multi-zone overlap. It contains the
        following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach CPU on zones [0, 1] at 55%/48.0C and HD on zone [1] at 70%/42.0C, both deferred
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly twice (zone 0 and zone 1)
        - ASSERT: zone 0 is set to 55 (CPU is the single contributor)
        - ASSERT: zone 1 is set to 70 (HD wins shared-zone arbitration)
        - ASSERT: service.applied_levels[0] is cached as 55
        - ASSERT: service.applied_levels[1] is cached as 70
        - ASSERT: log output contains "IPMI zone [0]: new level = 55% (CPU=48.0C)" (single-contributor)
        - ASSERT: log output contains "winner: HD=70%/42.0C" (shared zone)
        """
        f = "TestService.test_apply_fan_levels_multi_zone_partial_shared"
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
        assert len(calls) == 2, f"{f}: both zone 0 and zone 1 should get IPMI calls"
        call_dict = {c.args[0]: c.args[1] for c in calls}
        assert call_dict[0] == 55, f"{f}: zone 0 should be set to CPU's 55%"
        assert call_dict[1] == 70, f"{f}: zone 1 should be set to HD's 70% (winner)"
        assert service.applied_levels[0] == 55, f"{f}: zone 0 should cache 55"
        assert service.applied_levels[1] == 70, f"{f}: zone 1 should cache 70"
        # Zone 0 should log as single-contributor, zone 1 as shared
        log_output = str(mock_log_msg.call_args_list)
        assert "IPMI zone [0]: new level = 55% (CPU=48.0C)" in log_output, f"{f}: zone 0 single log"
        assert "winner: HD=70%/42.0C" in log_output, f"{f}: HD wins zone 1"

    def test_apply_fan_levels_cache_oscillation(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method exercising oscillation across calls. It contains
        the following steps:
        - mock print(), Ipmi.set_fan_level()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach a single deferred HD controller on zone 1 and run three calls with last_level 70 -> 50 -> 70
        - ASSERT: first call (level 70) triggers exactly 1 IPMI call
        - ASSERT: after step 1, service.applied_levels[1] is cached as 70
        - ASSERT: second call (level 50) brings the IPMI call count to 2 (level change triggers IPMI)
        - ASSERT: after step 2, service.applied_levels[1] is cached as 50
        - ASSERT: third call (level 70 again) brings the IPMI call count to 3 (returning level still re-applied)
        - ASSERT: after step 3, service.applied_levels[1] is cached as 70
        """
        f = "TestService.test_apply_fan_levels_cache_oscillation"
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
        assert mock_set_fan_level.call_count == 1, f"{f}: first call should trigger IPMI"
        assert service.applied_levels[1] == 70, f"{f}: zone 1 should cache 70 after step 1"

        # Step 2: level drops to 50%
        hd_fc.last_level = 50
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 2, f"{f}: level change should trigger IPMI"
        assert service.applied_levels[1] == 50, f"{f}: zone 1 should cache 50 after step 2"

        # Step 3: level returns to 70% — must trigger a new IPMI call
        hd_fc.last_level = 70
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 3, f"{f}: returning to previous level should trigger IPMI call"
        assert service.applied_levels[1] == 70, f"{f}: zone 1 should cache 70 after step 3"

    def test_check_shared_zones_detected(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method. It contains the following steps:
        - mock print(), Log.msg_to_stdout()
        - instantiate Service with a Log; attach HD and NVME controllers both on zone 1
        - call Service._check_shared_zones()
        - ASSERT: the returned set equals {1} (zone 1 is shared by HD and NVME)
        - ASSERT: log output contains "Shared IPMI zone 1"
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

        f = "TestService.test_check_shared_zones_detected"
        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == {1}, f"{f}: should detect shared zone 1"
        log_output = str(mock_log_msg.call_args_list)
        assert "Shared IPMI zone 1" in log_output, f"{f}: should log shared zone 1"

    def test_check_shared_zones_none(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method with no shared zones. It contains the following
        steps:
        - mock print()
        - instantiate Service with a Log; attach CPU on zone 0 and HD on zone 1 (no overlap)
        - call Service._check_shared_zones()
        - ASSERT: the returned set is empty (no zones are shared)
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
        assert result == set(), "TestService.test_check_shared_zones_none: should not detect shared zones"

    def test_check_shared_zones_multi_zone(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method with a multi-zone controller. It contains the
        following steps:
        - mock print(), Log.msg_to_stdout()
        - instantiate Service with a Log; attach CPU on zones [0, 1] and HD on zone [1]
        - call Service._check_shared_zones()
        - ASSERT: the returned set equals {1} (CPU and HD overlap on zone 1)
        - ASSERT: log output contains "Shared IPMI zone 1"
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

        f = "TestService.test_check_shared_zones_multi_zone"
        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == {1}, f"{f}: should detect shared zone 1"
        log_output = str(mock_log_msg.call_args_list)
        assert "Shared IPMI zone 1" in log_output, f"{f}: should log shared zone 1"

    def test_check_shared_zones_selective_deferred(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method with selective deferred-apply assignment. It
        contains the following steps:
        - mock print()
        - instantiate Service with a Log; attach CPU on zone 0 (exclusive), HD and NVME on zone 1 (shared)
        - call Service._check_shared_zones() and set deferred_apply=True only for controllers on shared zones
        - ASSERT: service.shared_zones equals {1}
        - ASSERT: CPU.deferred_apply remains False (zone 0 not shared)
        - ASSERT: HD.deferred_apply is True (zone 1 shared)
        - ASSERT: NVME.deferred_apply is True (zone 1 shared)
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

        f = "TestService.test_check_shared_zones_selective_deferred"
        service.shared_zones = service._check_shared_zones()  # pylint: disable=protected-access
        assert service.shared_zones == {1}, f"{f}: zone 1 should be shared"
        # Apply deferred only to controllers on shared zones
        if service.shared_zones:
            for fc in service.controllers:
                if set(fc.config.ipmi_zone) & service.shared_zones:
                    fc.deferred_apply = True
        assert cpu_fc.deferred_apply is False, f"{f}: CPU on zone 0 should not be deferred"
        assert hd_fc.deferred_apply is True, f"{f}: HD on shared zone 1 should be deferred"
        assert nvme_fc.deferred_apply is True, f"{f}: NVME on shared zone 1 should be deferred"

    @pytest.mark.parametrize(
        "exit_code",
        [
            # Old-style section names migration (exit 10)
            pytest.param(10, id="old-section-names-exit10"),
        ],
    )
    def test_run_old_section_names(self, mocker: MockerFixture, td: TestData, exit_code: int):
        """Positive unit test for Service.run() method exercising old-section-name migration. It contains the
        following steps:
        - mock print(), pyudev.Context.__init__ via MockedContextGood
        - build a config file via `td` with old-style section names ("CPU zone", "HD zone", "NVME zone", etc.)
        - instantiate Service and call Service.run() inside pytest.raises(SystemExit)
        - ASSERT: sys.exit() code equals 10 (no enabled fancontroller) — proves migration code ran successfully
        """
        my_config = ConfigParser()
        ipmi_command = td.create_ipmi_command()
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
        conf_file = td.create_config_file(my_config)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mocker.patch("pyudev.Context.__init__", MockedContextGood.__init__)
        sys.argv = ("smfc.py -o 0 -nd -ne -c " + conf_file).split()
        service = Service()
        with pytest.raises(SystemExit) as cm:
            service.run()
        assert cm.value.code == exit_code

    def test_apply_fan_levels_four_controllers_same_zone(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with four controllers on a shared zone. It
        contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach four deferred controllers on zone 1: CPU 40%/45.0C, HD 60%/38.0C, NVME 50%/42.0C, GPU 75%/65.0C
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (1, 75) — GPU wins
        - ASSERT: service.applied_levels[1] is cached as 75
        - ASSERT: log output contains "winner: GPU=75%/65.0C"
        - ASSERT: log output contains "CPU=40%/45.0C" as a loser
        - ASSERT: log output contains "HD=60%/38.0C" as a loser
        - ASSERT: log output contains "NVME=50%/42.0C" as a loser
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

        f = "TestService.test_apply_fan_levels_four_controllers_same_zone"
        service._apply_fan_levels()  # pylint: disable=protected-access
        # GPU at 75% should win (highest level among the four)
        mock_set_fan_level.assert_called_once_with(1, 75)
        assert service.applied_levels[1] == 75, f"{f}: zone 1 should cache 75"
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: GPU=75%/65.0C" in log_output, f"{f}: GPU should win"
        assert "CPU=40%/45.0C" in log_output, f"{f}: CPU should be a loser"
        assert "HD=60%/38.0C" in log_output, f"{f}: HD should be a loser"
        assert "NVME=50%/42.0C" in log_output, f"{f}: NVME should be a loser"

    def test_apply_fan_levels_five_controllers_with_const(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with five controllers including CONST winner. It
        contains the following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach five deferred controllers on zone 1: CPU 40%, HD 60%, NVME 50%, GPU 55%, CONST 80%
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly once with (1, 80) — CONST wins
        - ASSERT: service.applied_levels[1] is cached as 80
        - ASSERT: log output contains "winner: CONST=80%" (CONST has no temperature)
        - ASSERT: log output contains "CPU=40%/45.0C" as a loser
        - ASSERT: log output contains "HD=60%/38.0C" as a loser
        - ASSERT: log output contains "NVME=50%/42.0C" as a loser
        - ASSERT: log output contains "GPU=55%/60.0C" as a loser
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

        f = "TestService.test_apply_fan_levels_five_controllers_with_const"
        service._apply_fan_levels()  # pylint: disable=protected-access
        # CONST at 80% should win (highest level among all five)
        mock_set_fan_level.assert_called_once_with(1, 80)
        assert service.applied_levels[1] == 80, f"{f}: zone 1 should cache 80"
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: CONST=80%" in log_output  # CONST has no temperature
        # All losers should be listed
        assert "CPU=40%/45.0C" in log_output, f"{f}: CPU should be a loser"
        assert "HD=60%/38.0C" in log_output, f"{f}: HD should be a loser"
        assert "NVME=50%/42.0C" in log_output, f"{f}: NVME should be a loser"
        assert "GPU=55%/60.0C" in log_output, f"{f}: GPU should be a loser"

    def test_apply_fan_levels_complex_three_zone_overlap(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with three-zone overlap. It contains the
        following steps:
        - mock print(), Ipmi.set_fan_level(), Log.msg_to_stdout()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach CPU on zones [0,1,2] at 50%, HD on zones [1,2] at 65%, NVME on zone [2] at 80%, all deferred
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is called exactly three times (one per zone)
        - ASSERT: zone 0 is set to 50 (CPU is the single contributor)
        - ASSERT: zone 1 is set to 65 (HD wins over CPU)
        - ASSERT: zone 2 is set to 80 (NVME wins over CPU and HD)
        - ASSERT: service.applied_levels[0] is cached as 50
        - ASSERT: service.applied_levels[1] is cached as 65
        - ASSERT: service.applied_levels[2] is cached as 80
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

        f = "TestService.test_apply_fan_levels_complex_three_zone_overlap"
        service._apply_fan_levels()  # pylint: disable=protected-access
        # Zone 0: only CPU → 50%
        # Zone 1: CPU 50% vs HD 65% → HD wins at 65%
        # Zone 2: CPU 50% vs HD 65% vs NVME 80% → NVME wins at 80%
        calls = mock_set_fan_level.call_args_list
        assert len(calls) == 3, f"{f}: all three zones should get IPMI calls"
        call_dict = {c.args[0]: c.args[1] for c in calls}
        assert call_dict[0] == 50, f"{f}: zone 0 should be set to CPU's 50%"
        assert call_dict[1] == 65, f"{f}: zone 1 should be set to HD's 65%"
        assert call_dict[2] == 80, f"{f}: zone 2 should be set to NVME's 80%"
        assert service.applied_levels[0] == 50, f"{f}: zone 0 should cache 50"
        assert service.applied_levels[1] == 65, f"{f}: zone 1 should cache 65"
        assert service.applied_levels[2] == 80, f"{f}: zone 2 should cache 80"

    def test_apply_fan_levels_all_controllers_last_level_zero(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with all controllers at last_level=0. It contains
        the following steps:
        - mock print(), Ipmi.set_fan_level()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach two deferred controllers on zone 1 (CPU and HD), both with last_level=0 (not yet computed)
        - call Service._apply_fan_levels()
        - ASSERT: Ipmi.set_fan_level() is not called (all level-zero controllers skipped by _collect_desired_levels())
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
        f = "TestService.test_apply_fan_levels_all_controllers_last_level_zero"
        assert mock_set_fan_level.call_count == 0, f"{f}: controllers with last_level=0 should be skipped"

    def test_check_shared_zones_three_plus_zones_partial_overlap(self, mocker: MockerFixture):
        """Positive unit test for Service._check_shared_zones() method with three-controller partial overlap. It
        contains the following steps:
        - mock print(), Log.msg_to_stdout()
        - instantiate Service with a Log; attach CPU on zones [0,1,2], HD on [1,2], NVME on [2]
        - call Service._check_shared_zones()
        - ASSERT: the returned set equals {1, 2} (zone 1 shared by CPU+HD, zone 2 shared by all three)
        - ASSERT: log output contains "Shared IPMI zone 1"
        - ASSERT: log output contains "Shared IPMI zone 2"
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

        f = "TestService.test_check_shared_zones_three_plus_zones_partial_overlap"
        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == {1, 2}, f"{f}: should detect shared zones 1 and 2"
        log_output = str(mock_log_msg.call_args_list)
        assert "Shared IPMI zone 1" in log_output, f"{f}: zone 1 should be logged"
        assert "Shared IPMI zone 2" in log_output, f"{f}: zone 2 should be logged"

    def test_apply_fan_levels_multi_zone_deferred_caching(self, mocker: MockerFixture):
        """Positive unit test for Service._apply_fan_levels() method with multi-zone deferred caching across calls. It
        contains the following steps:
        - mock print(), Ipmi.set_fan_level()
        - instantiate Service with a Log and Ipmi.__new__(Ipmi); set applied_levels={} and last_desired=[]
        - attach a single deferred CPU controller on zones [0, 1] at 60% and run three successive calls
        - ASSERT: first call sets both zones (Ipmi.set_fan_level() called twice)
        - ASSERT: after the first call, service.applied_levels[0] equals 60
        - ASSERT: after the first call, service.applied_levels[1] equals 60
        - ASSERT: second call with same level makes no IPMI calls (both zones cached)
        - ASSERT: third call with new level=80 sets both zones again (2 IPMI calls)
        - ASSERT: after the third call, service.applied_levels[0] equals 80
        - ASSERT: after the third call, service.applied_levels[1] equals 80
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

        f = "TestService.test_apply_fan_levels_multi_zone_deferred_caching"
        # First call - should set both zones
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 2, f"{f}: first call should set both zones"
        assert service.applied_levels[0] == 60, f"{f}: zone 0 should cache 60"
        assert service.applied_levels[1] == 60, f"{f}: zone 1 should cache 60"

        # Second call with same level - should NOT make IPMI calls (cached)
        mock_set_fan_level.reset_mock()
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 0, f"{f}: same level should be cached"

        # Third call with different level - should update both zones
        cpu_fc.last_level = 80
        mock_set_fan_level.reset_mock()
        service._apply_fan_levels()  # pylint: disable=protected-access
        assert mock_set_fan_level.call_count == 2, f"{f}: third call should update both zones"
        assert service.applied_levels[0] == 80, f"{f}: zone 0 should cache 80"
        assert service.applied_levels[1] == 80, f"{f}: zone 1 should cache 80"


# End.
