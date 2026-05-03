#!/usr/bin/env python3
#
#   test_gpufc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.GpuFc() class.
#
import json
import subprocess
from typing import List, Any
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, GpuFc
from smfc.config import Config
from .test_data import TestData, create_gpu_config


class TestGpuFc:
    """Unit test class for smfc.GpuFc() class"""

    @pytest.mark.parametrize(
        "gpu_type, count, ipmi_zone, gpu_device_ids, temp_calc, steps, sensitivity, polling, min_temp, max_temp, "
        "min_level, max_level, error",
        [
            # 1 NVIDIA GPU, zone 0, CALC_MIN
            ("nvidia", 1, [0], [0], FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, "GpuFc.__init__() 1"),
            # 2 NVIDIA GPUs, zone 1, CALC_AVG
            ("nvidia", 2, [1], [0, 1], FanController.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, "GpuFc.__init__() 2"),
            # 4 AMD GPUs, zone 2, CALC_AVG
            ("amd", 4, [2], [0, 1, 2, 3], FanController.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, "GpuFc.__init__() 3"),
        ],
    )
    def test_init_p1(self, mocker: MockerFixture, gpu_type: str, count: int, ipmi_zone: List[int],
                     gpu_device_ids: List[int], temp_calc: int, steps: int, sensitivity: float, polling: float,
                     min_temp: float, max_temp: float, min_level: int, max_level: int, error: str):
        """Positive unit test for GpuFc.__init__() method. It contains the following steps:
        - mock print(), smfc.GpuFc._exec_smi()
        - create GPU config using factory function
        - initialize a Log, Ipmi, and GpuFc classes
        - ASSERT: if the GpuFc class attributes are different from values passed to __init__
        """
        my_td = TestData()
        if gpu_type == "nvidia":
            smi_cmd = my_td.create_nvidia_smi_command(count)
        else:
            smi_cmd = my_td.create_rocm_smi_command(count)

        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        # Mock _exec_smi because FanController.__init__ calls get_temp() -> _get_nth_temp() -> _exec_smi()
        mock_exec_smi = MagicMock()
        if gpu_type == "nvidia":
            mock_exec_smi.return_value = subprocess.CompletedProcess([], 0, stdout="40\n"*count)
        else:
            amd_json_data = {f"card{i}": {"Temperature (Sensor junction) (C)": "40.0"} for i in range(count)}
            amd_stdout = json.dumps(amd_json_data)
            mock_exec_smi.return_value = subprocess.CompletedProcess([], 0, stdout=amd_stdout)
        mocker.patch("smfc.GpuFc._exec_smi", mock_exec_smi)

        cfg = create_gpu_config(enabled=True, gpu_type=gpu_type, ipmi_zone=ipmi_zone, temp_calc=temp_calc,
                                steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                                max_temp=max_temp, min_level=min_level, max_level=max_level,
                                gpu_device_ids=gpu_device_ids,
                                nvidia_smi_path=smi_cmd if gpu_type == "nvidia" else "/usr/bin/nvidia-smi",
                                rocm_smi_path=smi_cmd if gpu_type == "amd" else "/usr/bin/rocm-smi")

        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_gpufc = GpuFc(my_log, my_ipmi, cfg)
        assert my_gpufc.config.gpu_type == gpu_type, error
        assert my_gpufc.config.ipmi_zone == ipmi_zone, error
        assert my_gpufc.name == cfg.section, error
        assert my_gpufc.count == count, error
        assert my_gpufc.config.temp_calc == temp_calc, error
        assert my_gpufc.config.steps == steps, error
        assert my_gpufc.config.sensitivity == sensitivity, error
        assert my_gpufc.config.polling == polling, error
        assert my_gpufc.config.min_temp == min_temp, error
        assert my_gpufc.config.max_temp == max_temp, error
        assert my_gpufc.config.min_level == min_level, error
        assert my_gpufc.config.max_level == max_level, error
        assert my_gpufc.config.smoothing == 1, error
        assert my_gpufc.config.gpu_device_ids == gpu_device_ids, error
        if gpu_type == "nvidia":
            assert my_gpufc.config.nvidia_smi_path == smi_cmd, error
        else:
            assert my_gpufc.config.rocm_smi_path == smi_cmd, error
            assert my_gpufc.config.amd_temp_sensor == 0, error
        del my_td

    @pytest.mark.parametrize(
        "error",
        [
            # Default configuration values test
            ("GpuFc.__init__() 4"),
        ],
    )
    def test_init_p2(self, mocker: MockerFixture, error: str):
        """Positive unit test for GpuFc.__init__() method. It contains the following steps:
        - mock print(), smfc.GpuFc._exec_smi()
        - create GPU config using factory function with default values
        - initialize a Log, Ipmi, and GpuFc classes
        - ASSERT: if the GpuFc class attributes are different from the default configuration values
        """
        count = 1
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_exec_smi = MagicMock()
        mock_exec_smi.return_value = subprocess.CompletedProcess([], 0, stdout="40\n")
        mocker.patch("smfc.GpuFc._exec_smi", mock_exec_smi)
        cfg = create_gpu_config(enabled=True)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_gpufc = GpuFc(my_log, my_ipmi, cfg)
        assert my_gpufc.log == my_log, error
        assert my_gpufc.ipmi == my_ipmi
        assert my_gpufc.config.ipmi_zone == [Config.HD_ZONE], error
        assert my_gpufc.name == cfg.section, error
        assert my_gpufc.count == count, error
        assert my_gpufc.config.temp_calc == FanController.CALC_AVG, error
        assert my_gpufc.config.steps == 5, error
        assert my_gpufc.config.sensitivity == 2, error
        assert my_gpufc.config.polling == 2, error
        assert my_gpufc.config.min_temp == 40, error
        assert my_gpufc.config.max_temp == 70, error
        assert my_gpufc.config.min_level == 35, error
        assert my_gpufc.config.max_level == 100, error
        assert my_gpufc.config.smoothing == 1, error
        assert my_gpufc.config.gpu_device_ids == [0], error
        assert my_gpufc.config.nvidia_smi_path == "/usr/bin/nvidia-smi", error
        assert my_gpufc.config.gpu_type == "nvidia", error
        assert my_gpufc.config.amd_temp_sensor == 0, error

    @pytest.mark.parametrize(
        "device_ids, error",
        [
            # Invalid gpu_device_ids: special character
            ("#, 0, 1", "GpuFc.__init__() 5"),
            # Invalid gpu_device_ids: negative value
            ("-1, 0, 1", "GpuFc.__init__() 6"),
            # Invalid gpu_device_ids: value over 100
            ("0, 101, 1", "GpuFc.__init__() 7"),
        ],
    )
    def test_init_n1(self, mocker: MockerFixture, device_ids: str, error: str):
        """Negative unit test for GpuFc.__init__() method. It contains the following steps:
        - mock print(), smfc.GpuFc._exec_smi()
        - create GPU config using factory function with invalid gpu_device_ids
        - initialize a Log, Ipmi, and GpuFc classes
        - ASSERT: if no assertion is raised for invalid values at initialization
        """
        my_td = TestData()
        count = 3
        nvidia_smi_cmd = my_td.create_nvidia_smi_command(count)
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_exec_smi = MagicMock()
        mock_exec_smi.return_value = subprocess.CompletedProcess([], 0, stdout="40\n"*count)
        mocker.patch("smfc.GpuFc._exec_smi", mock_exec_smi)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        with pytest.raises(Exception) as cm:
            # This will raise during config parsing
            cfg = create_gpu_config(enabled=True, gpu_device_ids=Config.parse_gpu_ids(device_ids),
                                    nvidia_smi_path=nvidia_smi_cmd)
            GpuFc(my_log, my_ipmi, cfg)
        assert cm.type is ValueError, error
        del my_td

    @pytest.mark.parametrize(
        "gpu_type, amd_temp, error",
        [
            # Invalid gpu_type
            ("invalid", 0, "GpuFc.__init__() 8"),
            # Invalid amd_temp_sensor for nvidia type
            ("nvidia", 3, "GpuFc.__init__() 9"),
        ],
    )
    def test_init_n2(self, mocker: MockerFixture, gpu_type: str, amd_temp: int, error: str):
        """Negative unit test for GpuFc.__init__() method. It contains the following steps:
        - mock print(), smfc.GpuFc._exec_smi()
        - create GPU config using factory function with invalid gpu_type or amd_temp
        - initialize a Log, Ipmi, and GpuFc classes
        - ASSERT: if no ValueError is raised for invalid values at initialization
        """
        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        mock_exec_smi = MagicMock()
        mock_exec_smi.return_value = subprocess.CompletedProcess([], 0, stdout="40\n")
        mocker.patch("smfc.GpuFc._exec_smi", mock_exec_smi)
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        with pytest.raises(Exception) as cm:
            cfg = create_gpu_config(enabled=True, gpu_type=gpu_type, amd_temp_sensor=amd_temp)
            GpuFc(my_log, my_ipmi, cfg)
        assert cm.type is ValueError, error

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "args, error",
        [
            # nvidia-smi query arguments
            (["--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"], "GpuFc._exec_smi() 1"),
            # Device ID arguments
            (["0", "1", "2", "3"], "GpuFc._exec_smi() 2"),
        ],
    )
    def test_exec_smi_p(self, mocker: MockerFixture, args: List[str], error: str):
        """Positive unit test for GpuFc._exec_smi() method. It contains the following steps:
        - mock subprocess.run() function
        - initialize an empty GpuFc class
        - call GpuFc._exec_smi() method
        - ASSERT: if subprocess.run() called with different parameters from specified argument list
        """
        expected_args: List[str]

        my_gpufc = GpuFc.__new__(GpuFc)
        smi_path = "nvidia-smi"
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value = subprocess.CompletedProcess([], returncode=0, stdout="40", stderr="")
        mocker.patch("subprocess.run", mock_subprocess_run)
        my_gpufc._exec_smi(smi_path, args)
        expected_args = [smi_path]
        # pylint: disable=R0801
        expected_args.extend(args)
        mock_subprocess_run.assert_called_with(expected_args, capture_output=True, check=False, text=True)
        assert mock_subprocess_run.call_count == 1, error

    @pytest.mark.parametrize(
        "smi_path, exception, error",
        [
            # Non-existent command path
            ("/nonexistent/command", FileNotFoundError, "GpuFc._exec_smi() 3")
        ],
    )
    def test_exec_smi_n(self, smi_path: str, exception: Any, error: str):
        """Negative unit test for GpuFc._exec_smi() method. It contains the following steps:
        - mock subprocess.run() function if needed
        - initialize an empty GpuFc class
        - call GpuFc._exec_smi() method
        - ASSERT: if no assertion was raised
        """
        my_gpufc = GpuFc.__new__(GpuFc)
        with pytest.raises(Exception) as cm:
            my_gpufc._exec_smi(smi_path, ["0", "1"])
        assert cm.type == exception, error

    @pytest.mark.parametrize(
        "gpu_type, amd_temp, count, temperatures, error",
        [
            # 1 NVIDIA GPU
            ("nvidia", 0, 1, [32.0], "GpuFc._get_nth_temp() 1"),
            # 2 NVIDIA GPUs
            ("nvidia", 0, 2, [33.0, 34.0], "GpuFc._get_nth_temp() 2"),
            # 4 AMD GPUs, junction sensor
            ("amd", 0, 4, [33.0, 34.0, 35.0, 38.0], "GpuFc._get_nth_temp() 3"),
            # 2 AMD GPUs, junction sensor
            ("amd", 0, 2, [36.0, 37.0], "GpuFc._get_nth_temp() 4"),
            # 2 AMD GPUs, edge sensor
            ("amd", 1, 2, [36.0, 37.0], "GpuFc._get_nth_temp() 5"),
            # 2 AMD GPUs, memory sensor
            ("amd", 2, 2, [36.0, 37.0], "GpuFc._get_nth_temp() 6"),
        ],
    )
    def test_get_nth_temp_p1(self, mocker: MockerFixture, gpu_type: str, amd_temp: int, count: int,
                             temperatures: List[float], error: str):
        """Positive unit test for GpuFc._get_nth_temp() method. It contains the following steps:
        - mock print() function
        - initialize an empty GpuFc class with config
        - ASSERT: if the read temperature is different from the expected one
        """
        my_td = TestData()
        if gpu_type == "nvidia":
            smi_cmd = my_td.create_nvidia_smi_command(count, temperatures)
        else:
            smi_cmd = my_td.create_rocm_smi_command(count, temperatures)

        my_gpufc = GpuFc.__new__(GpuFc)
        cfg = create_gpu_config(gpu_type=gpu_type, gpu_device_ids=list(range(count)), polling=2,
                                amd_temp_sensor=amd_temp,
                                nvidia_smi_path=smi_cmd if gpu_type == "nvidia" else "/usr/bin/nvidia-smi",
                                rocm_smi_path=smi_cmd if gpu_type == "amd" else "/usr/bin/rocm-smi")
        my_gpufc.config = cfg
        my_gpufc.smi_called = 0

        mock_print = MagicMock()
        mocker.patch("builtins.print", mock_print)
        amd_offsets = [0.0, -2.0, -5.0]
        offset = amd_offsets[amd_temp] if gpu_type == "amd" else 0.0
        for i in range(count):
            temp = my_gpufc._get_nth_temp(i)
            assert temp == temperatures[i] + offset, error
        del my_td

    @pytest.mark.parametrize(
        "stdout, gpu_device_ids, amd_temp, error",
        [
            # Card key not found: gpu_device_ids=[1] but JSON only contains card0
            ('{"card0": {"Temperature (Sensor junction) (C)": "40.0"}}', [1], 0, "GpuFc._get_nth_temp() n1"),
            # Temp key not found: amd_temp=0 (junction) but card only has edge sensor
            ('{"card0": {"Temperature (Sensor edge) (C)": "38.0"}}', [0], 0, "GpuFc._get_nth_temp() n2"),
            # Malformed JSON output from rocm-smi
            ("not valid json", [0], 0, "GpuFc._get_nth_temp() n3"),
        ],
    )
    def test_get_nth_temp_n(self, mocker: MockerFixture, stdout: str, gpu_device_ids: List[int],
                            amd_temp: int, error: str):
        """Negative unit test for GpuFc._get_nth_temp() method. It contains the following steps:
        - mock smfc.GpuFc._exec_smi() to return controlled stdout
        - initialize an empty GpuFc class configured for AMD with config
        - ASSERT: if ValueError is not raised for missing card, missing temp key, or malformed JSON
        """
        my_gpufc = GpuFc.__new__(GpuFc)
        cfg = create_gpu_config(gpu_type="amd", gpu_device_ids=gpu_device_ids, amd_temp_sensor=amd_temp, polling=2,
                                rocm_smi_path="/usr/bin/rocm-smi")
        my_gpufc.config = cfg
        my_gpufc.smi_called = 0
        mock_exec_smi = MagicMock()
        mock_exec_smi.return_value = subprocess.CompletedProcess([], 0, stdout=stdout)
        mocker.patch("smfc.GpuFc._exec_smi", mock_exec_smi)
        with pytest.raises(Exception) as cm:
            my_gpufc._get_nth_temp(0)
        assert cm.type is ValueError, error


# End.
