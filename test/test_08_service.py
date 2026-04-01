#!/usr/bin/env python3
#
#   test_08_service.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.Service() class.
#
from argparse import Namespace
import sys
import time
from configparser import ConfigParser
import pytest
from pyudev import Context
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, CpuFc, HdFc, NvmeFc, GpuFc, ConstFc, Service
from .test_00_data import TestData, MockedContextError, MockedContextGood
from .test_02_ipmi import BMC_INFO_OUTPUT


class TestService:
    """Unit test for smfc.Service() class"""

    sleep_counter: int

    @pytest.mark.parametrize(
        "ipmi, log, error",
        [
            (True, True, "Service.exit_func() 1"),
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
            ("something\ncoretemp\n",           True,  False, False, False, "Service.check_dependencies() 1"),
            ("something\nk10temp\n",            True,  False, True,  False, "Service.check_dependencies() 2"),
            ("coretemp\nsomething\nk10temp\n",  True,  False, False, False, "Service.check_dependencies() 3"),
            ("something\ndrivetemp\n",          False, True,  True,  False, "Service.check_dependencies() 4"),
            ("something\ndrivetemp\n",          False, True,  False, True,  "Service.check_dependencies() 5"),
            ("something\n",                     False, True,  False, False, "Service.check_dependencies() 6"),
            ("something\ndrivetemp\nx",         False, True,  True,  True,  "Service.check_dependencies() 7"),
            ("coretemp\ndrivetemp\n",           True,  True,  False, True,  "Service.check_dependencies() 8"),
        ],
    )
    def test_check_dependencies_p(self, mocker: MockerFixture, module_list: str, cpufc, hdfc, gpufc, standby: bool,
                                  error: str):
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

        service = Service()
        service.config = ConfigParser()
        service.config[Ipmi.CS_IPMI] = {}
        service.config[Ipmi.CS_IPMI][Ipmi.CV_IPMI_COMMAND] = ipmi_command

        service.cpu_fc_enabled = cpufc
        service.config[CpuFc.CS_CPU_FC] = {}
        service.config[CpuFc.CS_CPU_FC][CpuFc.CV_CPU_FC_ENABLED] = ("1" if cpufc else "0")

        service.hd_fc_enabled = hdfc
        service.config[HdFc.CS_HD_FC] = {}
        service.config[HdFc.CS_HD_FC][HdFc.CV_HD_FC_ENABLED] = ("1" if hdfc else "0")
        if hdfc:
            smartctl_cmd = my_td.create_command_file('echo "ACTIVE"')
            service.config[HdFc.CS_HD_FC][HdFc.CV_HD_FC_SMARTCTL_PATH] = smartctl_cmd
            service.config[HdFc.CS_HD_FC][HdFc.CV_HD_FC_STANDBY_GUARD_ENABLED] = "1" if standby else "0"

        service.nvme_fc_enabled = False
        service.config[NvmeFc.CS_NVME_FC] = {}
        service.config[NvmeFc.CS_NVME_FC][NvmeFc.CV_NVME_FC_ENABLED] = "0"

        service.gpu_fc_enabled = gpufc
        service.config[GpuFc.CS_GPU_FC] = {}
        service.config[GpuFc.CS_GPU_FC][GpuFc.CV_GPU_FC_ENABLED] = ("1" if gpufc else "0")
        if gpufc:
            nvidia_smi_cmd = my_td.create_command_file('echo "0"')
            service.config[GpuFc.CS_GPU_FC][GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH] = nvidia_smi_cmd

        assert service.check_dependencies() == "", error
        del my_td

    @pytest.mark.parametrize("error", ["Service.check_dependencies() 9"])
    def test_check_dependecies_n(self, mocker: MockerFixture, error: str):
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
        service = Service()
        service.config = ConfigParser()

        service.config[Ipmi.CS_IPMI] = {}
        service.config[Ipmi.CS_IPMI][Ipmi.CV_IPMI_COMMAND] = ipmi_command

        service.cpu_fc_enabled = True
        service.config[CpuFc.CS_CPU_FC] = {}
        service.config[CpuFc.CS_CPU_FC][CpuFc.CV_CPU_FC_ENABLED] = "1"

        service.hd_fc_enabled = True
        service.config[HdFc.CS_HD_FC] = {}
        service.config[HdFc.CS_HD_FC][HdFc.CV_HD_FC_ENABLED] = "1"
        smartctl_cmd = my_td.create_command_file('echo "ACTIVE"')
        service.config[HdFc.CS_HD_FC][HdFc.CV_HD_FC_SMARTCTL_PATH] = smartctl_cmd
        service.config[HdFc.CS_HD_FC][HdFc.CV_HD_FC_STANDBY_GUARD_ENABLED] = "1"

        service.nvme_fc_enabled = False
        service.config[NvmeFc.CS_NVME_FC] = {}
        service.config[NvmeFc.CS_NVME_FC][NvmeFc.CV_NVME_FC_ENABLED] = "0"

        nvidia_smi_cmd = my_td.create_command_file('echo "0"')
        service.gpu_fc_enabled = True
        service.config[GpuFc.CS_GPU_FC] = {}
        service.config[GpuFc.CS_GPU_FC][GpuFc.CV_GPU_FC_ENABLED] = "1"
        service.config[GpuFc.CS_GPU_FC][GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH] = nvidia_smi_cmd

        # Check if `nvidia-smi` command is not available.
        my_td.delete_file(nvidia_smi_cmd)
        error_str = service.check_dependencies()
        assert error_str.find("nvidia-smi") != -1, error

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
            ("-h",                                                      0, "Service.run() 1"),
            ("-v",                                                      0, "Service.run() 2"),
            ("-l 10",                                                   2, "Service.run() 3"),
            ("-o 9",                                                    2, "Service.run() 4"),
            ("-o 1 -l 10",                                              2, "Service.run() 5"),
            ("-o 9 -l 1",                                               2, "Service.run() 6"),
            ("-o 0 -l 3 -c &.txt",                                      6, "Service.run() 7"),
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
        [(10, 0, 5, "Service.run() 9"), (0, 9, 5, "Service.run() 10")],
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

    @pytest.mark.parametrize("exit_code, error", [(7, "Service.run() 11")])
    def test_run_7n(self, mocker: MockerFixture, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), argparse.ArgumentParser.parse_args(), smfc.Service.check_dependencies() functions
        - execute Service.run()
        - ASSERT: if sys.exit() did not return code 7 (check dependency error)
        """
        my_td = TestData()
        my_config = ConfigParser()
        my_config[CpuFc.CS_CPU_FC] = {CpuFc.CV_CPU_FC_ENABLED: "0"}
        my_config[HdFc.CS_HD_FC] = {HdFc.CV_HD_FC_ENABLED: "0"}
        my_config[NvmeFc.CS_NVME_FC] = {NvmeFc.CV_NVME_FC_ENABLED: "0"}
        my_config[GpuFc.CS_GPU_FC] = {GpuFc.CV_GPU_FC_ENABLED: "0"}
        my_config[ConstFc.CS_CONST_FC] = {ConstFc.CV_CONST_FC_ENABLED: "0"}
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
            ("NON_EXIST",  0,  0,  8, "Service.run() 12"),
            ("GOOD",      -1,  0,  8, "Service.run() 13"),
            ("GOOD",       0, -1,  8, "Service.run() 14"),
            ("BAD",        0,  0,  8, "Service.run() 15"),
            ("GOOD",       0,  0, 10, "Service.run() 16"),
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
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: ipmi_command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: str(mode_delay),
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: str(level_delay),
        }
        my_config[CpuFc.CS_CPU_FC] = {CpuFc.CV_CPU_FC_ENABLED: "0"}
        my_config[HdFc.CS_HD_FC] = {HdFc.CV_HD_FC_ENABLED: "0"}
        my_config[NvmeFc.CS_NVME_FC] = {NvmeFc.CV_NVME_FC_ENABLED: "0"}
        my_config[GpuFc.CS_GPU_FC] = {GpuFc.CV_GPU_FC_ENABLED: "0"}
        my_config[ConstFc.CS_CONST_FC] = {ConstFc.CV_CONST_FC_ENABLED: "0"}
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

    @pytest.mark.parametrize("exit_code, error", [(9, "Service.run() 17")])
    def test_run_9n(self, mocker: MockerFixture, exit_code: int, error: str):
        """Negative unit test for Service.run() method. It contains the following steps:
        - mock print(), pyudev.Context.__init__() functions
        - execute Service.run()
        - ASSERT: if sys.exit() did not return code 9 (pyudev.Context() init error)
        """
        my_td = TestData()
        my_config = ConfigParser()
        ipmi_command = my_td.create_ipmi_command()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: ipmi_command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: "0",
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: "0",
        }
        my_config[CpuFc.CS_CPU_FC] = {CpuFc.CV_CPU_FC_ENABLED: "0"}
        my_config[HdFc.CS_HD_FC] = {HdFc.CV_HD_FC_ENABLED: "0"}
        my_config[NvmeFc.CS_NVME_FC] = {NvmeFc.CV_NVME_FC_ENABLED: "0"}
        my_config[GpuFc.CS_GPU_FC] = {GpuFc.CV_GPU_FC_ENABLED: "0"}
        my_config[ConstFc.CS_CONST_FC] = {ConstFc.CV_CONST_FC_ENABLED: "0"}
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
            (True,  False, False, True,  False, 100, "Service.run() 18"),
            (False, True,  False, False, True,  100, "Service.run() 19"),
            (True,  False, False, True,  False, 100, "Service.run() 20"),
            (True,  False, True,  False, False, 100, "Service.run() 21"),
            (True,  True,  True,  True,  True,  100, "Service.run() 22"),
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

        def mocked_cpufc_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal my_td
            self.hwmon_path = my_td.cpu_files
            count = len(my_td.cpu_files)
            FanController.__init__(self, log, ipmi, f"{Ipmi.CPU_ZONE} {Ipmi.HD_ZONE}", CpuFc.CS_CPU_FC, count,
                                   1, 5, 5, 0, 30, 60, 35, 100,)

        def mocked_hdfc_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser, sudo: bool) -> None:
            nonlocal my_td
            nonlocal cmd_smart
            self.hd_device_names = my_td.hd_name_list
            self.hwmon_path = my_td.hd_files
            count = len(my_td.hd_files)
            self.sudo = sudo
            FanController.__init__(self, log, ipmi, f"{Ipmi.HD_ZONE}", HdFc.CS_HD_FC, count,
                                   1, 5, 2, 0, 32, 46, 35, 100)
            self.smartctl_path = cmd_smart
            self.standby_guard_enabled = True
            self.standby_hd_limit = 1
            self.standby_array_states = [False] * self.count
            self.standby_flag = False
            self.standby_change_timestamp = time.monotonic()

        def mocked_gpufc_init(self, log: Log, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal my_td
            nonlocal cmd_nvidia
            self.gpu_device_ids = [0]
            count = 1
            self.nvidia_smi_path = cmd_nvidia
            self.nvidia_smi_called = 0
            FanController.__init__(self, log, ipmi, f"{Ipmi.HD_ZONE}", GpuFc.CS_GPU_FC, count,
                                   1, 5, 2, 0, 45, 70, 35, 100)

        def mocked_nvmefc_init(self, log: Log, udevc: Context, ipmi: Ipmi, config: ConfigParser) -> None:
            nonlocal my_td
            self.nvme_device_names = my_td.nvme_name_list
            self.hwmon_path = my_td.nvme_files
            count = len(my_td.nvme_files)
            FanController.__init__(self, log, ipmi, f"{Ipmi.HD_ZONE}", NvmeFc.CS_NVME_FC, count,
                                   1, 5, 2, 0, 30, 50, 35, 100,)

        def mocked_constfc_init(self, log: Log, ipmi: Ipmi, config: ConfigParser) -> None:
            self.ipmi = ipmi
            self.log = log
            self.name = ConstFc.CS_CONST_FC
            self.ipmi_zone = [Ipmi.HD_ZONE]
            self.polling = 30
            self.level = 50
            self.last_level = self.level
            self.deferred_apply = False
            self.last_time = 0

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
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: cmd_ipmi,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: "0",
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: "0",
        }
        my_config[CpuFc.CS_CPU_FC] = {
            CpuFc.CV_CPU_FC_ENABLED: str(cpufc),
            CpuFc.CV_CPU_FC_TEMP_CALC: "1",
            CpuFc.CV_CPU_FC_STEPS: "5",
            CpuFc.CV_CPU_FC_SENSITIVITY: "5",
            CpuFc.CV_CPU_FC_POLLING: "0",
            CpuFc.CV_CPU_FC_MIN_TEMP: "30",
            CpuFc.CV_CPU_FC_MAX_TEMP: "60",
            CpuFc.CV_CPU_FC_MIN_LEVEL: "35",
            CpuFc.CV_CPU_FC_MAX_LEVEL: "100",
        }
        my_config[HdFc.CS_HD_FC] = {
            HdFc.CV_HD_FC_ENABLED: str(hdfc),
            HdFc.CV_HD_FC_TEMP_CALC: "1",
            HdFc.CV_HD_FC_STEPS: "4",
            HdFc.CV_HD_FC_SENSITIVITY: "2",
            HdFc.CV_HD_FC_POLLING: "0",
            HdFc.CV_HD_FC_MIN_TEMP: "30",
            HdFc.CV_HD_FC_MAX_TEMP: "45",
            HdFc.CV_HD_FC_MIN_LEVEL: "35",
            HdFc.CV_HD_FC_MAX_LEVEL: "100",
            HdFc.CV_HD_FC_HD_NAMES: my_td.hd_names,
            HdFc.CV_HD_FC_SMARTCTL_PATH: cmd_smart,
            HdFc.CV_HD_FC_STANDBY_GUARD_ENABLED: "1",
            HdFc.CV_HD_FC_STANDBY_HD_LIMIT: "2",
        }
        my_config[NvmeFc.CS_NVME_FC] = {
            NvmeFc.CV_NVME_FC_ENABLED: str(nvmefc),
            NvmeFc.CV_NVME_FC_TEMP_CALC: "1",
            NvmeFc.CV_NVME_FC_STEPS: "4",
            NvmeFc.CV_NVME_FC_SENSITIVITY: "2",
            NvmeFc.CV_NVME_FC_POLLING: "0",
            NvmeFc.CV_NVME_FC_MIN_TEMP: "30",
            NvmeFc.CV_NVME_FC_MAX_TEMP: "50",
            NvmeFc.CV_NVME_FC_MIN_LEVEL: "35",
            NvmeFc.CV_NVME_FC_MAX_LEVEL: "100",
            NvmeFc.CV_NVME_FC_NVME_NAMES: my_td.nvme_names,
        }
        my_config[GpuFc.CS_GPU_FC] = {
            GpuFc.CV_GPU_FC_ENABLED: str(gpufc),
            GpuFc.CV_GPU_FC_IPMI_ZONE: "2",
            GpuFc.CV_GPU_FC_TEMP_CALC: "1",
            GpuFc.CV_GPU_FC_STEPS: "4",
            GpuFc.CV_GPU_FC_SENSITIVITY: "2",
            GpuFc.CV_GPU_FC_POLLING: "0",
            GpuFc.CV_GPU_FC_MIN_TEMP: "45",
            GpuFc.CV_GPU_FC_MAX_TEMP: "70",
            GpuFc.CV_GPU_FC_MIN_LEVEL: "35",
            GpuFc.CV_GPU_FC_MAX_LEVEL: "100",
            GpuFc.CV_GPU_FC_GPU_IDS: "0",
            GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH: cmd_nvidia,
        }
        my_config[ConstFc.CS_CONST_FC] = {
            ConstFc.CV_CONST_FC_ENABLED: str(constfc),
            ConstFc.CV_CONST_FC_IPMI_ZONE: "2",
            ConstFc.CV_CONST_FC_POLLING: "0",
            ConstFc.CV_CONST_FC_LEVEL: "35",
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
        """Test that _collect_desired_levels() gathers levels from enabled controllers,
        skipping those with last_level == 0 (except ConstFc)."""
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}

        # Create two mock controllers on the same zone
        service.cpu_fc_enabled = True
        service.cpu_fc = FanController.__new__(FanController)
        service.cpu_fc.name = CpuFc.CS_CPU_FC
        service.cpu_fc.ipmi_zone = [0]
        service.cpu_fc.last_level = 60
        service.cpu_fc.last_temp = 45.0
        service.cpu_fc.deferred_apply = True

        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]
        service.hd_fc.last_level = 0  # Should be skipped (not yet computed)
        service.hd_fc.last_temp = 0.0
        service.hd_fc.deferred_apply = True

        service.nvme_fc_enabled = False
        service.gpu_fc_enabled = False

        # ConstFc with last_level=0 should NOT be skipped
        service.const_fc_enabled = True
        service.const_fc = ConstFc.__new__(ConstFc)
        service.const_fc.name = ConstFc.CS_CONST_FC
        service.const_fc.ipmi_zone = [1]
        service.const_fc.last_level = 0
        service.const_fc.deferred_apply = True

        levels = service._collect_desired_levels()  # pylint: disable=protected-access
        names = [name for name, _, _, _ in levels]
        assert CpuFc.CS_CPU_FC in names, "CPU controller should be collected"
        assert HdFc.CS_HD_FC not in names, "HD controller with level 0 should be skipped"
        assert ConstFc.CS_CONST_FC in names, "ConstFc with level 0 should still be collected"

    def test_apply_fan_levels_shared_zone(self, mocker: MockerFixture):
        """Test that _apply_fan_levels() applies the maximum level when two controllers share a zone
        and logs the winner and losers."""
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

        # Two controllers on zone 1: HD at 45%, NVME at 70%
        service.cpu_fc_enabled = False
        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]
        service.hd_fc.last_level = 45
        service.hd_fc.last_temp = 38.0
        service.hd_fc.deferred_apply = True

        service.nvme_fc_enabled = True
        service.nvme_fc = FanController.__new__(FanController)
        service.nvme_fc.name = NvmeFc.CS_NVME_FC
        service.nvme_fc.ipmi_zone = [1]
        service.nvme_fc.last_level = 70
        service.nvme_fc.last_temp = 42.5
        service.nvme_fc.deferred_apply = True

        service.gpu_fc_enabled = False
        service.const_fc_enabled = False

        service._apply_fan_levels()  # pylint: disable=protected-access
        # Zone 1 should be set to 70% (the higher level wins)
        mock_set_fan_level.assert_called_once_with(1, 70)
        assert service.applied_levels[1] == 70, "Zone 1 should cache level 70"
        # Log should mention the winner and losers for shared zones with temperatures
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: NVME=70%/42.5C" in log_output, "Shared zone log should mention winner with temp"
        assert "losers: HD=45%/38.0C" in log_output, "Shared zone log should mention losers with temp"

    def test_apply_fan_levels_single_zone(self, mocker: MockerFixture):
        """Test that _apply_fan_levels() logs the fan level for a single-controller zone."""
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

        # Single controller on zone 0
        service.cpu_fc_enabled = True
        service.cpu_fc = FanController.__new__(FanController)
        service.cpu_fc.name = CpuFc.CS_CPU_FC
        service.cpu_fc.ipmi_zone = [0]
        service.cpu_fc.last_level = 60
        service.cpu_fc.last_temp = 45.0
        service.cpu_fc.deferred_apply = True

        service.hd_fc_enabled = False
        service.nvme_fc_enabled = False
        service.gpu_fc_enabled = False
        service.const_fc_enabled = False

        service._apply_fan_levels()  # pylint: disable=protected-access
        mock_set_fan_level.assert_called_once_with(0, 60)
        assert service.applied_levels[0] == 60
        # Single-contributor zone should log the fan level with temperature
        log_output = str(mock_log_msg.call_args_list)
        assert "IPMI zone [0]: new level = 60% (CPU=45.0C)" in log_output

    def test_apply_fan_levels_single_zone_const(self, mocker: MockerFixture):
        """Test that _apply_fan_levels() logs without temperature for a single CONST controller zone."""
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

        # Single CONST controller on zone 0
        service.cpu_fc_enabled = False
        service.hd_fc_enabled = False
        service.nvme_fc_enabled = False
        service.gpu_fc_enabled = False
        service.const_fc_enabled = True
        service.const_fc = FanController.__new__(FanController)
        service.const_fc.name = ConstFc.CS_CONST_FC
        service.const_fc.ipmi_zone = [0]
        service.const_fc.last_level = 50
        service.const_fc.deferred_apply = True

        service._apply_fan_levels()  # pylint: disable=protected-access
        mock_set_fan_level.assert_called_once_with(0, 50)
        assert service.applied_levels[0] == 50
        # Single CONST zone should log without temperature
        log_output = str(mock_log_msg.call_args_list)
        assert "IPMI zone [0]: new level = 50% (CONST)" in log_output

    def test_apply_fan_levels_shared_zone_const_winner(self, mocker: MockerFixture):
        """Test that _apply_fan_levels() logs correctly when CONST wins arbitration."""
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

        # CONST at 80% wins over HD at 45% on zone 1
        service.cpu_fc_enabled = False
        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]
        service.hd_fc.last_level = 45
        service.hd_fc.last_temp = 38.0
        service.hd_fc.deferred_apply = True

        service.nvme_fc_enabled = False
        service.gpu_fc_enabled = False
        service.const_fc_enabled = True
        service.const_fc = FanController.__new__(FanController)
        service.const_fc.name = ConstFc.CS_CONST_FC
        service.const_fc.ipmi_zone = [1]
        service.const_fc.last_level = 80
        service.const_fc.deferred_apply = True

        service._apply_fan_levels()  # pylint: disable=protected-access
        mock_set_fan_level.assert_called_once_with(1, 80)
        assert service.applied_levels[1] == 80
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: CONST=80%" in log_output, "CONST winner should have no temperature"
        assert "losers: HD=45%/38.0C" in log_output

    def test_apply_fan_levels_shared_zone_const_loser(self, mocker: MockerFixture):
        """Test that _apply_fan_levels() logs correctly when CONST loses arbitration."""
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

        # HD at 70% wins over CONST at 40% on zone 1
        service.cpu_fc_enabled = False
        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]
        service.hd_fc.last_level = 70
        service.hd_fc.last_temp = 55.0
        service.hd_fc.deferred_apply = True

        service.nvme_fc_enabled = False
        service.gpu_fc_enabled = False
        service.const_fc_enabled = True
        service.const_fc = FanController.__new__(FanController)
        service.const_fc.name = ConstFc.CS_CONST_FC
        service.const_fc.ipmi_zone = [1]
        service.const_fc.last_level = 40
        service.const_fc.deferred_apply = True

        service._apply_fan_levels()  # pylint: disable=protected-access
        mock_set_fan_level.assert_called_once_with(1, 70)
        assert service.applied_levels[1] == 70
        log_output = str(mock_log_msg.call_args_list)
        assert "winner: HD=70%/55.0C" in log_output
        assert "losers: CONST=40%" in log_output, "CONST loser should have no temperature"

    def test_apply_fan_levels_skips_non_deferred(self, mocker: MockerFixture):
        """Test that _apply_fan_levels() skips non-deferred controllers."""
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {}

        # CPU deferred on shared zone 0, HD non-deferred on non-shared zone 1
        service.cpu_fc_enabled = True
        service.cpu_fc = FanController.__new__(FanController)
        service.cpu_fc.name = CpuFc.CS_CPU_FC
        service.cpu_fc.ipmi_zone = [0]
        service.cpu_fc.last_level = 60
        service.cpu_fc.last_temp = 45.0
        service.cpu_fc.deferred_apply = True

        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]
        service.hd_fc.last_level = 40
        service.hd_fc.last_temp = 23.0
        service.hd_fc.deferred_apply = False

        service.nvme_fc_enabled = False
        service.gpu_fc_enabled = False
        service.const_fc_enabled = False

        service._apply_fan_levels()  # pylint: disable=protected-access
        # Only zone 0 should get an IPMI call, zone 1 is handled by HD directly
        mock_set_fan_level.assert_called_once_with(0, 60)
        assert 0 in service.applied_levels
        assert 1 not in service.applied_levels

    def test_apply_fan_levels_cache(self, mocker: MockerFixture):
        """Test that _apply_fan_levels() skips IPMI call when level hasn't changed."""
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_set_fan_level = MagicMock()
        mocker.patch("smfc.Ipmi.set_fan_level", mock_set_fan_level)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        service.ipmi = Ipmi.__new__(Ipmi)
        service.applied_levels = {1: 70}  # Already applied 70% to zone 1

        service.cpu_fc_enabled = False
        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]
        service.hd_fc.last_level = 70
        service.hd_fc.last_temp = 40.0
        service.hd_fc.deferred_apply = True

        service.nvme_fc_enabled = False
        service.gpu_fc_enabled = False
        service.const_fc_enabled = False

        service._apply_fan_levels()  # pylint: disable=protected-access
        # No IPMI call since level hasn't changed
        assert mock_set_fan_level.call_count == 0, "Should skip IPMI call when level is cached"

    def test_check_shared_zones_detected(self, mocker: MockerFixture):
        """Test that _check_shared_zones() returns True when HD and NVME share zone 1."""
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)

        service.cpu_fc_enabled = False
        service.gpu_fc_enabled = False
        service.const_fc_enabled = False

        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]

        service.nvme_fc_enabled = True
        service.nvme_fc = FanController.__new__(FanController)
        service.nvme_fc.name = NvmeFc.CS_NVME_FC
        service.nvme_fc.ipmi_zone = [1]

        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == {1}, "Should detect shared zone 1"
        log_output = str(mock_log_msg.call_args_list)
        assert "Shared IPMI zone 1" in log_output, "Should log shared zone 1"

    def test_check_shared_zones_none(self, mocker: MockerFixture):
        """Test that _check_shared_zones() returns empty set when CPU on zone 0 and HD on zone 1."""
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)

        service.cpu_fc_enabled = True
        service.cpu_fc = FanController.__new__(FanController)
        service.cpu_fc.name = CpuFc.CS_CPU_FC
        service.cpu_fc.ipmi_zone = [0]

        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]

        service.nvme_fc_enabled = False
        service.gpu_fc_enabled = False
        service.const_fc_enabled = False

        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == set(), "Should not detect shared zones"

    def test_check_shared_zones_multi_zone(self, mocker: MockerFixture):
        """Test that _check_shared_zones() returns {1} when CPU on zones [0,1] and HD on zone [1]."""
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_log_msg = MagicMock()
        mocker.patch("smfc.Log.msg_to_stdout", mock_log_msg)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)

        service.cpu_fc_enabled = True
        service.cpu_fc = FanController.__new__(FanController)
        service.cpu_fc.name = CpuFc.CS_CPU_FC
        service.cpu_fc.ipmi_zone = [0, 1]

        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]

        service.nvme_fc_enabled = False
        service.gpu_fc_enabled = False
        service.const_fc_enabled = False

        result = service._check_shared_zones()  # pylint: disable=protected-access
        assert result == {1}, "Should detect shared zone 1"
        log_output = str(mock_log_msg.call_args_list)
        assert "Shared IPMI zone 1" in log_output, "Should log shared zone 1"

    def test_check_shared_zones_selective_deferred(self, mocker: MockerFixture):
        """Test that only controllers on shared zones get deferred_apply=True,
        while controllers on non-shared zones remain deferred_apply=False."""
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        service = Service()
        service.log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)

        # CPU on zone 0 (exclusive), HD on zone 1, NVME on zone 1 (shared)
        service.cpu_fc_enabled = True
        service.cpu_fc = FanController.__new__(FanController)
        service.cpu_fc.name = CpuFc.CS_CPU_FC
        service.cpu_fc.ipmi_zone = [0]
        service.cpu_fc.deferred_apply = False

        service.hd_fc_enabled = True
        service.hd_fc = FanController.__new__(FanController)
        service.hd_fc.name = HdFc.CS_HD_FC
        service.hd_fc.ipmi_zone = [1]
        service.hd_fc.deferred_apply = False

        service.nvme_fc_enabled = True
        service.nvme_fc = FanController.__new__(FanController)
        service.nvme_fc.name = NvmeFc.CS_NVME_FC
        service.nvme_fc.ipmi_zone = [1]
        service.nvme_fc.deferred_apply = False

        service.gpu_fc_enabled = False
        service.const_fc_enabled = False

        service.shared_zones = service._check_shared_zones()  # pylint: disable=protected-access
        assert service.shared_zones == {1}
        # Apply deferred only to controllers on shared zones
        if service.shared_zones:
            if service.hd_fc_enabled and set(service.hd_fc.ipmi_zone) & service.shared_zones:
                service.hd_fc.deferred_apply = True
            if service.nvme_fc_enabled and set(service.nvme_fc.ipmi_zone) & service.shared_zones:
                service.nvme_fc.deferred_apply = True
        assert service.cpu_fc.deferred_apply is False, "CPU on zone 0 should not be deferred"
        assert service.hd_fc.deferred_apply is True, "HD on shared zone 1 should be deferred"
        assert service.nvme_fc.deferred_apply is True, "NVME on shared zone 1 should be deferred"

    @pytest.mark.parametrize("exit_code, error", [(10, "Service.run() 23")])
    def test_run_old_section_names(self, mocker: MockerFixture, exit_code: int, error: str):
        """Test backward compatibility: old config section names (with 'zone' tag) are migrated to new names.
        - create config with old-style section names ([CPU zone], [HD zone], etc.)
        - execute Service.run()
        - ASSERT: exit code 10 (no enabled fancontroller), proving the migration code ran successfully
        """
        my_td = TestData()
        my_config = ConfigParser()
        ipmi_command = my_td.create_ipmi_command()
        my_config[Ipmi.CS_IPMI] = {
            Ipmi.CV_IPMI_COMMAND: ipmi_command,
            Ipmi.CV_IPMI_FAN_MODE_DELAY: "0",
            Ipmi.CV_IPMI_FAN_LEVEL_DELAY: "0",
        }
        # Use old-style section names with 'zone' tag.
        my_config["CPU zone"] = {CpuFc.CV_CPU_FC_ENABLED: "0"}
        my_config["HD zone"] = {HdFc.CV_HD_FC_ENABLED: "0"}
        my_config["NVME zone"] = {NvmeFc.CV_NVME_FC_ENABLED: "0"}
        my_config["GPU zone"] = {GpuFc.CV_GPU_FC_ENABLED: "0"}
        my_config["CONST zone"] = {ConstFc.CV_CONST_FC_ENABLED: "0"}
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


# End.
