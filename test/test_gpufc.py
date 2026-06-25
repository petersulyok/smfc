#!/usr/bin/env python3
#
#   test_gpufc.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.GpuFc() class.
#
import subprocess
from typing import List
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc.config import Config
from .test_config_builders import create_gpu_config
from .test_fixtures import TestData
from .test_fc_helpers import assert_fc_base_contract, build_gpu_fc, make_bare_gpu_fc

# Field order for the parametrized explicit-configuration init test (GPU-specific gpu_type/ids + base fields).
INIT_FIELDS = ["gpu_type", "gpu_device_ids", "ipmi_zone", "temp_calc", "steps", "sensitivity", "polling",
               "min_temp", "max_temp", "min_level", "max_level", "smoothing"]


class TestGpuFc:
    """Unit test class for smfc.GpuFc() class"""

    @pytest.mark.parametrize(
        INIT_FIELDS,
        [
            pytest.param("nvidia", [0], [0], Config.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 1, id="1nvidia-zone0-min"),
            pytest.param("nvidia", [0, 1], [1], Config.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 3,
                         id="2nvidia-zone1-avg-smooth3"),
            pytest.param("amd", [0, 1, 2, 3], [2], Config.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 1, id="4amd-zone2-avg"),
        ],
    )
    def test_init_sets_attributes_from_config(self, mocker: MockerFixture, td: TestData, gpu_type: str,
                                              gpu_device_ids: List[int], ipmi_zone: List[int], temp_calc: int,
                                              steps: int, sensitivity: float, polling: float, min_temp: float,
                                              max_temp: float, min_level: int, max_level: int, smoothing: int):
        """Positive unit test for GpuFc.__init__() method. It contains the following steps:
        - mock builtins.print, smfc.GpuFc._exec_smi (via build_gpu_fc); Ipmi.__new__ stub
        - build a GpuFc via build_gpu_fc() for the parametrized (gpu_type, gpu_device_ids, base fields)
        - ASSERT: the base-class contract holds (log/ipmi refs, name, count, configured fields; no hwmon)
        - ASSERT: fc.config.gpu_type matches the parametrized gpu_type
        - ASSERT: fc.config.gpu_device_ids matches the parametrized gpu_device_ids
        - ASSERT: fc.config.nvidia_smi_path equals the generated nvidia-smi command (nvidia case)
        - ASSERT: fc.config.rocm_smi_path equals the generated rocm-smi command (amd case)
        - ASSERT: fc.config.amd_temp_sensor == 0 (amd case)
        - ASSERT: fc.device_names() returns the gpu<id> labels derived from gpu_device_ids
        """
        count = len(gpu_device_ids)
        cfg_values = {"ipmi_zone": ipmi_zone, "temp_calc": temp_calc, "steps": steps, "sensitivity": sensitivity,
                      "polling": polling, "min_temp": min_temp, "max_temp": max_temp, "min_level": min_level,
                      "max_level": max_level, "smoothing": smoothing}
        if gpu_type == "nvidia":
            smi_cmd = td.create_nvidia_smi_command(count)
            smi_kwargs = {"nvidia_smi_path": smi_cmd}
        else:
            smi_cmd = td.create_rocm_smi_command(count)
            smi_kwargs = {"rocm_smi_path": smi_cmd}
        h = build_gpu_fc(mocker, gpu_type=gpu_type, gpu_device_ids=gpu_device_ids, **cfg_values, **smi_kwargs)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=cfg_values, log=h.log, ipmi=h.ipmi,
                                has_hwmon=False)
        assert h.fc.config.gpu_type == gpu_type
        assert h.fc.config.gpu_device_ids == gpu_device_ids
        if gpu_type == "nvidia":
            assert h.fc.config.nvidia_smi_path == smi_cmd
        else:
            assert h.fc.config.rocm_smi_path == smi_cmd
            assert h.fc.config.amd_temp_sensor == 0
        # device_names() synthesizes gpu<id> labels from gpu_device_ids for the snapshot/exporter path.
        assert h.fc.device_names() == [f"gpu{gid}" for gid in gpu_device_ids]

    def test_init_applies_defaults(self, mocker: MockerFixture):
        """Positive unit test for GpuFc.__init__() method with default configuration. It contains the following steps:
        - mock builtins.print, smfc.GpuFc._exec_smi (via build_gpu_fc); Ipmi.__new__ stub
        - build a GpuFc from a default GPU config (only enabled is set)
        - ASSERT: the base-class contract holds with the Config.DV_GPU_* default values; no hwmon
        - ASSERT: fc.config.gpu_type == Config.DV_GPU_TYPE
        - ASSERT: fc.config.gpu_device_ids == Config.parse_gpu_ids(Config.DV_GPU_DEVICE_IDS)
        - ASSERT: fc.config.nvidia_smi_path == Config.DV_GPU_NVIDIA_SMI_PATH
        - ASSERT: fc.config.amd_temp_sensor == Config.DV_GPU_AMD_TEMP_SENSOR
        """
        count = len(Config.parse_gpu_ids(Config.DV_GPU_DEVICE_IDS))
        expected = {"ipmi_zone": [Config.HD_ZONE], "temp_calc": Config.CALC_AVG, "steps": Config.DV_GPU_STEPS,
                    "sensitivity": Config.DV_GPU_SENSITIVITY, "polling": Config.DV_GPU_POLLING,
                    "min_temp": Config.DV_GPU_MIN_TEMP, "max_temp": Config.DV_GPU_MAX_TEMP,
                    "min_level": Config.DV_GPU_MIN_LEVEL, "max_level": Config.DV_GPU_MAX_LEVEL,
                    "smoothing": Config.DV_GPU_SMOOTHING}
        h = build_gpu_fc(mocker)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=expected, log=h.log, ipmi=h.ipmi,
                                has_hwmon=False)
        assert h.fc.config.gpu_type == Config.DV_GPU_TYPE
        assert h.fc.config.gpu_device_ids == Config.parse_gpu_ids(Config.DV_GPU_DEVICE_IDS)
        assert h.fc.config.nvidia_smi_path == Config.DV_GPU_NVIDIA_SMI_PATH
        assert h.fc.config.amd_temp_sensor == Config.DV_GPU_AMD_TEMP_SENSOR

    @pytest.mark.parametrize(
        "device_ids",
        [
            pytest.param("#, 0, 1", id="special-char"),
            pytest.param("-1, 0, 1", id="negative-id"),
            pytest.param("0, 101, 1", id="id-over-100"),
        ],
    )
    def test_init_rejects_invalid_device_ids(self, device_ids: str):
        """Negative unit test for Config.parse_gpu_ids() / create_gpu_config(). It contains the following steps:
        - mock nothing (pure config-layer validation; GpuFc is never constructed)
        - call Config.parse_gpu_ids(device_ids) with an invalid id string (special char, negative, > 100)
        - feed the result into create_gpu_config(enabled=True, gpu_device_ids=...)
        - ASSERT: a ValueError is raised during parsing/validation
        """
        with pytest.raises(ValueError):
            create_gpu_config(enabled=True, gpu_device_ids=Config.parse_gpu_ids(device_ids))

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "args",
        [
            pytest.param(["--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"], id="nvidia-query"),
            pytest.param(["0", "1", "2", "3"], id="device-ids"),
        ],
    )
    def test_exec_smi_builds_command(self, mocker: MockerFixture, args: List[str]):
        """Positive unit test for GpuFc._exec_smi() method. It contains the following steps:
        - mock subprocess.run (MagicMock returning a CompletedProcess with stdout="40")
        - build a bare GpuFc via make_bare_gpu_fc() (no super().__init__())
        - call fc._exec_smi(smi_path, args) with the parametrized argument list
        - ASSERT: subprocess.run is called with ([smi_path] + args, capture_output=True, check=False, text=True)
        - ASSERT: subprocess.run is called exactly once
        """
        fc = make_bare_gpu_fc()
        smi_path = "nvidia-smi"
        mock_run = MagicMock(return_value=subprocess.CompletedProcess([], returncode=0, stdout="40", stderr=""))
        mocker.patch("subprocess.run", mock_run)
        fc._exec_smi(smi_path, args)
        mock_run.assert_called_with([smi_path] + args, capture_output=True, check=False, text=True)
        assert mock_run.call_count == 1

    def test_exec_smi_raises_on_missing_command(self):
        """Negative unit test for GpuFc._exec_smi() method. It contains the following steps:
        - mock nothing (the real subprocess.run is used so the missing binary triggers OS error)
        - build a bare GpuFc via make_bare_gpu_fc() (no super().__init__())
        - call fc._exec_smi("/nonexistent/command", ["0", "1"])
        - ASSERT: FileNotFoundError is raised
        """
        fc = make_bare_gpu_fc()
        with pytest.raises(FileNotFoundError):
            fc._exec_smi("/nonexistent/command", ["0", "1"])

    @pytest.mark.parametrize(
        "gpu_type, amd_temp, count, temperatures",
        [
            pytest.param("nvidia", 0, 1, [32.0], id="1nvidia"),
            pytest.param("nvidia", 0, 2, [33.0, 34.0], id="2nvidia"),
            pytest.param("amd", 0, 4, [33.0, 34.0, 35.0, 38.0], id="4amd-junction"),
            pytest.param("amd", 0, 2, [36.0, 37.0], id="2amd-junction"),
            pytest.param("amd", 1, 2, [36.0, 37.0], id="2amd-edge"),
            pytest.param("amd", 2, 2, [36.0, 37.0], id="2amd-memory"),
        ],
    )
    def test_get_nth_temp_reads_smi(self, td: TestData, gpu_type: str, amd_temp: int, count: int,
                                    temperatures: List[float]):
        """Positive unit test for GpuFc._get_nth_temp() method. It contains the following steps:
        - mock nothing in-process; uses a real on-disk nvidia-smi / rocm-smi fake command from TestData
        - create the fake smi command file emitting the parametrized per-device temperatures
        - build a bare GpuFc via make_bare_gpu_fc(config=...) configured for the gpu_type / amd_temp_sensor
        - for each device index i, call fc._get_nth_temp(i)
        - ASSERT: the returned temperature equals temperatures[i] plus the AMD sensor offset (0/-2/-5)
        """
        if gpu_type == "nvidia":
            smi_cmd = td.create_nvidia_smi_command(count, temperatures)
            cfg = create_gpu_config(gpu_type=gpu_type, gpu_device_ids=list(range(count)), polling=2,
                                    amd_temp_sensor=amd_temp, nvidia_smi_path=smi_cmd)
        else:
            smi_cmd = td.create_rocm_smi_command(count, temperatures)
            cfg = create_gpu_config(gpu_type=gpu_type, gpu_device_ids=list(range(count)), polling=2,
                                    amd_temp_sensor=amd_temp, rocm_smi_path=smi_cmd)
        fc = make_bare_gpu_fc(config=cfg)
        amd_offsets = [0.0, -2.0, -5.0]
        offset = amd_offsets[amd_temp] if gpu_type == "amd" else 0.0
        for i in range(count):
            assert fc._get_nth_temp(i) == temperatures[i] + offset

    @pytest.mark.parametrize(
        "stdout, gpu_device_ids, amd_temp",
        [
            # Card key not found: gpu_device_ids=[1] but JSON only contains card0
            pytest.param('{"card0": {"Temperature (Sensor junction) (C)": "40.0"}}', [1], 0, id="card-not-found"),
            # Temp key not found: amd_temp=0 (junction) but card only has edge sensor
            pytest.param('{"card0": {"Temperature (Sensor edge) (C)": "38.0"}}', [0], 0, id="temp-key-not-found"),
            # Malformed JSON output from rocm-smi
            pytest.param("not valid json", [0], 0, id="malformed-json"),
        ],
    )
    def test_get_nth_temp_raises_on_amd_errors(self, mocker: MockerFixture, stdout: str, gpu_device_ids: List[int],
                                               amd_temp: int):
        """Negative unit test for GpuFc._get_nth_temp() method on AMD. It contains the following steps:
        - mock smfc.GpuFc._exec_smi (MagicMock returning a CompletedProcess with the parametrized stdout)
        - build a bare AMD GpuFc via make_bare_gpu_fc(config=...) for the parametrized gpu_device_ids/amd_temp
        - call fc._get_nth_temp(0) against the controlled rocm-smi output
        - ASSERT: ValueError is raised (missing card key, missing temperature sensor key, or malformed JSON)
        """
        cfg = create_gpu_config(gpu_type="amd", gpu_device_ids=gpu_device_ids, amd_temp_sensor=amd_temp, polling=2,
                                rocm_smi_path="/usr/bin/rocm-smi")
        fc = make_bare_gpu_fc(config=cfg)
        smi_result = subprocess.CompletedProcess([], returncode=0, stdout=stdout)
        mocker.patch("smfc.GpuFc._exec_smi", MagicMock(return_value=smi_result))
        with pytest.raises(ValueError):
            fc._get_nth_temp(0)

    @pytest.mark.parametrize(
        "stdout, gpu_device_ids",
        [
            # nvidia-smi returns 2 temperature lines but gpu_device_ids requests index 2.
            pytest.param("40\n41\n", [0, 1, 2], id="3ids-2lines"),
            # nvidia-smi returns no lines at all (empty stdout).
            pytest.param("", [0], id="0ids-empty"),
            # nvidia-smi returns 1 line but config requests indices [0, 3] (driver dropped middle GPUs).
            pytest.param("42\n", [0, 3], id="2ids-1line-hotunplug"),
        ],
    )
    def test_get_nth_temp_raises_on_nvidia_partial_output(self, mocker: MockerFixture, stdout: str,
                                                         gpu_device_ids: List[int]):
        """Negative unit test for GpuFc._get_nth_temp() method on NVIDIA with partial nvidia-smi output. It contains the
        following steps:
        - mock smfc.GpuFc._exec_smi (MagicMock returning a CompletedProcess with truncated stdout — fewer temperature
          lines than max(gpu_device_ids) + 1, simulating a hot-unplugged GPU or driver fault)
        - build a bare NVIDIA GpuFc via make_bare_gpu_fc(config=...) for the parametrized gpu_device_ids
        - call fc._get_nth_temp(0) which triggers the per-device temperature collection loop
        - ASSERT: IndexError is raised when temp_list[gid] indexes past the end of the truncated output
        """
        cfg = create_gpu_config(gpu_type="nvidia", gpu_device_ids=gpu_device_ids, polling=2,
                                nvidia_smi_path="/usr/bin/nvidia-smi")
        fc = make_bare_gpu_fc(config=cfg)
        smi_result = subprocess.CompletedProcess([], returncode=0, stdout=stdout)
        mocker.patch("smfc.GpuFc._exec_smi", MagicMock(return_value=smi_result))
        with pytest.raises(IndexError):
            fc._get_nth_temp(0)

    # pylint: enable=protected-access


# End.
