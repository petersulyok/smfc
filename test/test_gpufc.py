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
from .test_data import TestData, create_gpu_config
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
        """Positive unit test for GpuFc.__init__() with an explicit configuration. It contains the steps:
        - build a GpuFc via the shared builder (_exec_smi mocked; GPU has no udev/hwmon)
        - ASSERT: the base-class contract (log/ipmi refs, name, count, config fields; no hwmon)
        - ASSERT: the GPU-specific attributes (gpu_type, gpu_device_ids, smi path, amd sensor, gpu<id> names)
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
        """Positive unit test for GpuFc.__init__() with default configuration values. It contains the steps:
        - build a GpuFc from a default config (only enabled set)
        - ASSERT: the base-class contract holds with the GPU default config values (Config.DV_GPU_*)
        - ASSERT: the GPU-specific defaults (gpu_type, gpu_device_ids, nvidia_smi_path, amd_temp_sensor)
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
        """Negative unit test for GPU device-id parsing. It contains the steps:
        - parse invalid gpu_device_ids while building the GPU config
        - ASSERT: a ValueError is raised during config parsing (before GpuFc is constructed)
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
        """Positive unit test for GpuFc._exec_smi(). It contains the steps:
        - build a bare GpuFc and mock subprocess.run()
        - call _exec_smi() with a command path and arguments
        - ASSERT: subprocess.run() is called exactly once with the [path] + args argument list
        """
        fc = make_bare_gpu_fc()
        smi_path = "nvidia-smi"
        mock_run = MagicMock(return_value=subprocess.CompletedProcess([], returncode=0, stdout="40", stderr=""))
        mocker.patch("subprocess.run", mock_run)
        fc._exec_smi(smi_path, args)
        mock_run.assert_called_with([smi_path] + args, capture_output=True, check=False, text=True)
        assert mock_run.call_count == 1

    def test_exec_smi_raises_on_missing_command(self):
        """Negative unit test for GpuFc._exec_smi() with a non-existent command. It contains the steps:
        - build a bare GpuFc and call _exec_smi() with a non-existent command path
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
        """Positive unit test for GpuFc._get_nth_temp() over the SMI command. It contains the steps:
        - create a real nvidia-smi/rocm-smi command file emitting the given per-device temperatures
        - build a bare GpuFc configured for that GPU type/sensor
        - ASSERT: _get_nth_temp(i) returns the device temperature (with the AMD sensor offset applied)
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
        """Negative unit test for GpuFc._get_nth_temp() AMD parsing errors. It contains the steps:
        - build a bare AMD GpuFc and mock _exec_smi() to return controlled rocm-smi output
        - ASSERT: ValueError is raised for a missing card, a missing temperature key, or malformed JSON
        """
        cfg = create_gpu_config(gpu_type="amd", gpu_device_ids=gpu_device_ids, amd_temp_sensor=amd_temp, polling=2,
                                rocm_smi_path="/usr/bin/rocm-smi")
        fc = make_bare_gpu_fc(config=cfg)
        smi_result = subprocess.CompletedProcess([], returncode=0, stdout=stdout)
        mocker.patch("smfc.GpuFc._exec_smi", MagicMock(return_value=smi_result))
        with pytest.raises(ValueError):
            fc._get_nth_temp(0)

    # pylint: enable=protected-access


# End.
