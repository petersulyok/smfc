#!/usr/bin/env python3
#
#   test_06_gpuzone.py (C) 2021-2025, Peter Sulyok
#   Unit tests for smfc.GpuZone() class.
#
import subprocess
from configparser import ConfigParser
from typing import List, Any
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Log, Ipmi, FanController, GpuZone
from .test_00_data import TestData

class TestGpuZone:
    """Unit test class for smfc.GpuZone() class"""

    @pytest.mark.parametrize(
        "count, ipmi_zone, gpu_device_ids, temp_calc, steps, sensitivity, polling, min_temp, max_temp, min_level, "
        "max_level, error", [
        (1, '0', '0',           FanController.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 'GpuZone.__init__() 1'),
        (2, '1', '0, 1',        FanController.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 'GpuZone.__init__() 2'),
        (4, '2', '0, 1, 2, 3',  FanController.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 'GpuZone.__init__() 3')
    ])
    def test_init_p1(self, mocker: MockerFixture, count: int, ipmi_zone: str, gpu_device_ids: str, temp_calc: int,
                     steps: int, sensitivity: float, polling: float, min_temp: float, max_temp: float, min_level: int,
                     max_level: int, error: str):
        """Positive unit test for GpuZone.__init__() method. It contains the following steps:
            - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
            - initialize a Config, Log, Ipmi, and GpuZone classes
            - ASSERT: if the GpuZone class attributes are different from values passed to __init__
        """
        my_td = TestData()
        nvidia_smi_cmd = my_td.create_nvidia_smi_command(count)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        my_config = ConfigParser()
        my_config[GpuZone.CS_GPU_ZONE] = {
            GpuZone.CV_GPU_ZONE_ENABLED: '1',
            GpuZone.CV_GPU_IPMI_ZONE: ipmi_zone,
            GpuZone.CV_GPU_ZONE_TEMP_CALC: str(temp_calc),
            GpuZone.CV_GPU_ZONE_STEPS: str(steps),
            GpuZone.CV_GPU_ZONE_SENSITIVITY: str(sensitivity),
            GpuZone.CV_GPU_ZONE_POLLING: str(polling),
            GpuZone.CV_GPU_ZONE_MIN_TEMP: str(min_temp),
            GpuZone.CV_GPU_ZONE_MAX_TEMP: str(max_temp),
            GpuZone.CV_GPU_ZONE_MIN_LEVEL: str(min_level),
            GpuZone.CV_GPU_ZONE_MAX_LEVEL: str(max_level),
            GpuZone.CV_GPU_ZONE_GPU_IDS: gpu_device_ids,
            GpuZone.CV_GPU_ZONE_NVIDIA_SMI_PATH: nvidia_smi_cmd
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_gpuzone = GpuZone(my_log, my_ipmi, my_config)
        assert my_gpuzone.ipmi_zone == [int(s) for s in ipmi_zone.split(',' if ',' in ipmi_zone else ' ')], error
        assert my_gpuzone.name == GpuZone.CS_GPU_ZONE, error
        assert my_gpuzone.count == count, error
        assert my_gpuzone.temp_calc == temp_calc, error
        assert my_gpuzone.steps == steps, error
        assert my_gpuzone.sensitivity == sensitivity, error
        assert my_gpuzone.polling == polling, error
        assert my_gpuzone.min_temp == min_temp, error
        assert my_gpuzone.max_temp == max_temp, error
        assert my_gpuzone.min_level == min_level, error
        assert my_gpuzone.max_level == max_level, error
        assert my_gpuzone.gpu_device_ids == [int(s) for s in gpu_device_ids.
                                             split(',' if ',' in gpu_device_ids else ' ')], error
        assert my_gpuzone.nvidia_smi_path == nvidia_smi_cmd, error
        del my_td

    @pytest.mark.parametrize("error", [
        'GpuZone.__init__() 4'
    ])
    def test_init_p2(self, mocker: MockerFixture, error: str):
        """Positive unit test for GpuZone.__init__() method. It contains the following steps:
            - mock print(), smfc.GpuZone._exec_nvidia_smi()
            - initialize a Config, Log, Ipmi, and GpuZone classes
            - ASSERT: if the GpuZone class attributes are different from the default configuration values
        """
        count = 1
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        mock_exec_nvidia_smi = MagicMock()
        mock_exec_nvidia_smi.return_value = subprocess.CompletedProcess([], 0, stdout='40\n')
        mocker.patch('smfc.GpuZone._exec_nvidia_smi', mock_exec_nvidia_smi)
        my_config = ConfigParser()
        my_config[GpuZone.CS_GPU_ZONE] = {
            GpuZone.CV_GPU_ZONE_ENABLED: '1',
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        my_gpuzone = GpuZone(my_log, my_ipmi, my_config)
        assert my_gpuzone.log == my_log, error
        assert my_gpuzone.ipmi == my_ipmi
        assert my_gpuzone.ipmi_zone == [Ipmi.HD_ZONE], error
        assert my_gpuzone.name == GpuZone.CS_GPU_ZONE, error
        assert my_gpuzone.count == count, error
        assert my_gpuzone.temp_calc == FanController.CALC_AVG, error
        assert my_gpuzone.steps == 5, error
        assert my_gpuzone.sensitivity == 2, error
        assert my_gpuzone.polling == 2, error
        assert my_gpuzone.min_temp == 40, error
        assert my_gpuzone.max_temp == 70, error
        assert my_gpuzone.min_level == 35, error
        assert my_gpuzone.max_level == 100, error
        assert my_gpuzone.gpu_device_ids == [0], error
        assert my_gpuzone.nvidia_smi_path == '/usr/bin/nvidia-smi', error

    @pytest.mark.parametrize("device_ids, error", [
        # gpu_device_ids= invalid value(s)
        ('#, 0, 1',     'GpuZone.__init__() 5'),
        ('-1, 0, 1',    'GpuZone.__init__() 6'),
        ('0, 101, 1',   'GpuZone.__init__() 7')
    ])
    def test_init_n1(self, mocker: MockerFixture, device_ids: str, error: str):
        """Negative unit test for GpuZone.__init__() method. It contains the following steps:
            - mock print(), pyudev.Devices.from_device_file(), pyudev.Device, smfc.FanController.get_hwmon_path()
            - initialize a Config, Log, Ipmi, and GpuZone classes
            - ASSERT: if no assertion is raised for invalid values at initialization
        """
        my_td = TestData()
        count=3
        nvidia_smi_cmd = my_td.create_nvidia_smi_command(count)
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        my_config = ConfigParser()
        my_config[GpuZone.CS_GPU_ZONE] = {
            GpuZone.CV_GPU_ZONE_ENABLED: '1',
            GpuZone.CV_GPU_ZONE_GPU_IDS: device_ids,
            GpuZone.CV_GPU_ZONE_NVIDIA_SMI_PATH: nvidia_smi_cmd
        }
        my_log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        my_ipmi = Ipmi.__new__(Ipmi)
        with pytest.raises(Exception) as cm:
            GpuZone(my_log, my_ipmi, my_config)
        assert cm.type is ValueError, error
        del my_td

    #pylint: disable=protected-access
    @pytest.mark.parametrize("args, error", [
        (['--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],  'GpuZone._exec_nvidia_smi() 1'),
        (['0', '1', '2', '3'],                                              'GpuZone._exec_nvidia_smi() 2')
    ])
    def test_exec_nvidia_smi_p(self, mocker: MockerFixture, args:List[str], error: str):
        """Positive unit test for GpuZone._exec_nvidia_smi() method. It contains the following steps:
            - mock subprocess.run() function
            - initialize an empty GpuZone class
            - call GpuZone._exec_nvidia_smi() method
            - ASSERT: if subprocess.run() called with different parameters from specified argument list
        """
        expected_args: List[str]

        my_gpuzone = GpuZone.__new__(GpuZone)
        my_gpuzone.nvidia_smi_path = 'nvidia-smi'
        mock_subprocess_run = MagicMock()
        mock_subprocess_run.return_value=subprocess.CompletedProcess([], returncode=0, stdout='40', stderr='')
        mocker.patch('subprocess.run', mock_subprocess_run)
        my_gpuzone._exec_nvidia_smi(args)
        expected_args = [my_gpuzone.nvidia_smi_path]
        expected_args.extend(args)
        mock_subprocess_run.assert_called_with(expected_args, capture_output=True, check=False, text=True)
        assert mock_subprocess_run.call_count == 1, error

    #pylint: disable=R0801
    @pytest.mark.parametrize("nvidia_smi_path, exception, error", [
        # The real subprocess.run() executed (without sudo)
        ('/nonexistent/command', FileNotFoundError, 'GpuZone._exec_nvidia_smi() 3')
    ])
    def test_exec_nvidia_smi_n(self, nvidia_smi_path: str, exception: Any, error: str):
        """Negative unit test for GpuZone._exec_nvidia_smi() method. It contains the following steps:
            - mock subprocess.run() function if needed
            - initialize an empty GpuZone class
            - call GpuZone._exec_nvidia_smi() method
            - ASSERT: if no assertion was raised
        """
        my_gpuzone = GpuZone.__new__(GpuZone)
        my_gpuzone.nvidia_smi_path = nvidia_smi_path
        with pytest.raises(Exception) as cm:
            my_gpuzone._exec_nvidia_smi(['0', '1'])
        assert cm.type == exception, error
    # pylint: enable=R0801

    @pytest.mark.parametrize("count, temperatures, error", [
        (1, [32],                               'GpuZone._get_nth_temp() 1'),
        (2, [33, 34],                           'GpuZone._get_nth_temp() 2'),
        (4, [33, 34, 35, 38],                   'GpuZone._get_nth_temp() 3'),
        (8, [33, 34, 35, 38, 36, 37, 31, 30],   'GpuZone._get_nth_temp() 4')
    ])
    def test_get_nth_temp_p1(self, mocker: MockerFixture, count: int, temperatures: List[float], error: str):
        """Positive unit test for GpuZone._get_nth_temp() method. It contains the following steps:
            - mock print() function
            - initialize an empty GpuZone class
            - ASSERT: if the read temperature is different from the expected one
        """
        my_td = TestData()
        nvidia_smi_cmd = my_td.create_nvidia_smi_command(count, temperatures)
        my_gpuzone = GpuZone.__new__(GpuZone)
        my_gpuzone.gpu_device_ids = list(range(count))
        my_gpuzone.polling=2
        my_gpuzone.nvidia_smi_called=0
        my_gpuzone.nvidia_smi_path=nvidia_smi_cmd
        mock_print = MagicMock()
        mocker.patch('builtins.print', mock_print)
        for i in range(count):
            temp = my_gpuzone._get_nth_temp(i)
            assert temp == temperatures[i], error
        del my_td


# End.
