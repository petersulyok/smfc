#!/usr/bin/env python3
#
#   test_06_gpufc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.GpuFc() class.
#
import subprocess
from configparser import ConfigParser
from typing import List, Any
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, GpuFc
from .test_00_data import TestData


class TestGpuFc:
    """Unit test class for smfc.GpuFc() class"""

    @pytest.mark.parametrize(
        "count, ipmi_zone, gpu_device_ids, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, "
        "max_level, error",
        [
            (1, "0", "0",          FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, "GpuFc.__init__() 1"),
            (2, "1", "0, 1",       FanController.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, "GpuFc.__init__() 2"),
            (4, "2", "0, 1, 2, 3", FanController.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, "GpuFc.__init__() 3"),
        ],
    )
    def test_init_p1(self, mocker: MockerFixture, count: int, ipmi_zone: str, gpu_device_ids: str, temp_calc: int,
                     steps: int, sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                     max_level: int, error: str):
        """Positive unit test for GpuFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - initialize a Config, Log, Ipmi, and GpuFc classes
        - ASSERT: if the GpuFc class attributes are different from values passed to __init__
        """
        my_td = TestData()
        nvidia_smi_cmd = my_td.create_nvidia_smi_command(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        my_config = ConfigParser()
        my_config[GpuFc.CS_GPU_FC] = {
            GpuFc.CV_GPU_FC_ENABLED: "1",
            GpuFc.CV_GPU_FC_IPMI_ZONE: ipmi_zone,
            GpuFc.CV_GPU_FC_TEMP_CALC: str(temp_calc),
            GpuFc.CV_GPU_FC_STEPS: str(steps),
            GpuFc.CV_GPU_FC_SENSITIVITY: str(sensitivity),
            GpuFc.CV_GPU_FC_POLLING: str(polling),
            GpuFc.CV_GPU_FC_MIN_TEMP: str(min_temp),
            GpuFc.CV_GPU_FC_MAX_TEMP: str(max_temp),
            GpuFc.CV_GPU_FC_MIN_LEVEL: str(min_level),
            GpuFc.CV_GPU_FC_MAX_LEVEL: str(max_level),
            GpuFc.CV_GPU_FC_GPU_IDS: gpu_device_ids,
            GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH: nvidia_smi_cmd,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_gpufc = GpuFc(my_log, my_ipmi, my_config)
        assert my_gpufc.ipmi_zone == [int(s) for s in ipmi_zone.split("," if "," in ipmi_zone else " ")], error
        assert my_gpufc.name == GpuFc.CS_GPU_FC, error
        assert my_gpufc.count == count, error
        assert my_gpufc.temp_calc == temp_calc, error
        assert my_gpufc.steps == steps, error
        assert my_gpufc.sensitivity == sensitivity, error
        assert my_gpufc.polling == polling, error
        assert my_gpufc.min_temp == min_temp, error
        assert my_gpufc.max_temp == max_temp, error
        assert my_gpufc.min_level == min_level, error
        assert my_gpufc.max_level == max_level, error
        assert my_gpufc.smoothing == 1, error
        assert (my_gpufc.gpu_device_ids ==
                [int(s) for s in gpu_device_ids.split("," if "," in gpu_device_ids else " ")]), error
        assert my_gpufc.nvidia_smi_path == nvidia_smi_cmd, error
        del my_td

    @pytest.mark.parametrize("error", ["GpuFc.__init__() 4"])
    def test_init_p2(self, mocker: MockerFixture, error: str):
        """Positive unit test for GpuFc.__init__() method. It contains the following steps:
        - mock print(), smfc.GpuFc._exec_nvidia_smi()
        - initialize a Config, Log, Ipmi, and GpuFc classes
        - ASSERT: if the GpuFc class attributes are different from the default configuration values
        """
        count = 1
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_exec_nvidia_smi = MagicMock()
        mock_exec_nvidia_smi.return_value = subprocess.CompletedProcess([], 0, stdout="40\n")
        mocker.patch("smfc.GpuFc._exec_nvidia_smi", mock_exec_nvidia_smi)
        my_config = ConfigParser()
        my_config[GpuFc.CS_GPU_FC] = {GpuFc.CV_GPU_FC_ENABLED: "1"}
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_gpufc = GpuFc(my_log, my_ipmi, my_config)
        assert my_gpufc.log == my_log, error
        assert my_gpufc.ipmi == my_ipmi
        assert my_gpufc.ipmi_zone == [Ipmi.HD_ZONE], error
        assert my_gpufc.name == GpuFc.CS_GPU_FC, error
        assert my_gpufc.count == count, error
        assert my_gpufc.temp_calc == FanController.CALC_AVG, error
        assert my_gpufc.steps == 5, error
        assert my_gpufc.sensitivity == 2, error
        assert my_gpufc.polling == 2, error
        assert my_gpufc.min_temp == 40, error
        assert my_gpufc.max_temp == 70, error
        assert my_gpufc.min_level == 35, error
        assert my_gpufc.max_level == 100, error
        assert my_gpufc.smoothing == 1, error
        assert my_gpufc.gpu_device_ids == [0], error
        assert my_gpufc.nvidia_smi_path == "/usr/bin/nvidia-smi", error

    @pytest.mark.parametrize(
        "device_ids, error",
        [
            # gpu_device_ids= invalid value(s)
            ("#, 0, 1", "GpuFc.__init__() 5"),
            ("-1, 0, 1", "GpuFc.__init__() 6"),
            ("0, 101, 1", "GpuFc.__init__() 7"),
        ],
    )
    def test_init_n1(self, mocker: MockerFixture, device_ids: str, error: str):
        """Negative unit test for GpuFc.__init__() method. It contains the following steps:
        - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
        - initialize a Config, Log, Ipmi, and GpuFc classes
        - ASSERT: if no assertion is raised for invalid values at initialization
        """
        my_td = TestData()
        count = 3
        nvidia_smi_cmd = my_td.create_nvidia_smi_command(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        my_config = ConfigParser()
        my_config[GpuFc.CS_GPU_FC] = {
            GpuFc.CV_GPU_FC_ENABLED: "1",
            GpuFc.CV_GPU_FC_GPU_IDS: device_ids,
            GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH: nvidia_smi_cmd,
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        with pytest.raises(Exception) as cm:
            GpuFc(my_log, my_ipmi, my_config)
        assert cm.type is ValueError, error
        del my_td

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "args, error",
        [
            (["--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"], "GpuFc._exec_nvidia_smi() 1"),
            (["0", "1", "2", "3"], "GpuFc._exec_nvidia_smi() 2"),
        ],
    )
    def test_exec_nvidia_smi_p(self, mocker: MockerFixture, args: List[str], error: str):
        """Positive unit test for GpuFc._exec_nvidia_smi() method. It contains the following steps:
        - mock subprocess.run() function
        - initialize an empty GpuFc class
        - call GpuFc._exec_nvidia_smi() method
        - ASSERT: if subprocess.run() called with different parameters from specified argument list
        """
        expected_args: List[str]

        my_gpufc = GpuFc.__new__(GpuFc)
        my_gpufc.nvidia_smi_path = "nvidia-smi"
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0, stdout="40", stderr="")
        mocker.patch("subprocess.run", mock_subprocess_run)
        my_gpufc._exec_nvidia_smi(args)
        expected_args = [my_gpufc.nvidia_smi_path]
        # pylint: disable=R0801
        expected_args.extend(args)
        mock_subprocess_run.assert_called_with(expected_args, capture_output=True, check=False, text=True)
        assert mock_subprocess_run.call_count == 1, error

    @pytest.mark.parametrize(
        "nvidia_smi_path, exception, error",
        [
            # The real subprocess.run() executed (without sudo)
            ("/nonexistent/command", FileNotFoundError, "GpuFc._exec_nvidia_smi() 3")
        ],
    )
    def test_exec_nvidia_smi_n(self, nvidia_smi_path: str, exception: Any, error: str):
        """Negative unit test for GpuFc._exec_nvidia_smi() method. It contains the following steps:
        - mock subprocess.run() function if needed
        - initialize an empty GpuFc class
        - call GpuFc._exec_nvidia_smi() method
        - ASSERT: if no assertion was raised
        """
        my_gpufc = GpuFc.__new__(GpuFc)
        my_gpufc.nvidia_smi_path = nvidia_smi_path
        with pytest.raises(Exception) as cm:
            my_gpufc._exec_nvidia_smi(["0", "1"])
        assert cm.type == exception, error

    @pytest.mark.parametrize(
        "count, temperatures, error",
        [
            (1, [32], "GpuFc._get_nth_temp() 1"),
            (2, [33, 34], "GpuFc._get_nth_temp() 2"),
            (4, [33, 34, 35, 38], "GpuFc._get_nth_temp() 3"),
            (8, [33, 34, 35, 38, 36, 37, 31, 30], "GpuFc._get_nth_temp() 4"),
        ],
    )
    def test_get_nth_temp_p1(self, mocker: MockerFixture, count: int, temperatures: List[float], error: str):
        """Positive unit test for GpuFc._get_nth_temp() method. It contains the following steps:
        - mock print() function
        - initialize an empty GpuFc class
        - ASSERT: if the read temperature is different from the expected one
        """
        my_td = TestData()
        # pylint: enable=R0801
        nvidia_smi_cmd = my_td.create_nvidia_smi_command(count, temperatures)
        my_gpufc = GpuFc.__new__(GpuFc)
        my_gpufc.gpu_device_ids = list(range(count))
        my_gpufc.polling = 2
        my_gpufc.nvidia_smi_called = 0
        my_gpufc.nvidia_smi_path = nvidia_smi_cmd
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        for i in range(count):
            temp = my_gpufc._get_nth_temp(i)
            assert temp == temperatures[i], error
        del my_td


# End.
