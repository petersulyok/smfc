#!/usr/bin/env python3
#
#   test_npufc.py (C) 2026, Artur Kalagov, Peter Sulyok
#   Unit tests for smfc.NpuFc() class.
#
import subprocess
from typing import List
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import NpuFc
from smfc.config import Config
from .test_config_builders import create_npu_config
from .test_fc_helpers import (NPU_SMI_TEMP_OUTPUT, assert_fc_base_contract, build_npu_fc, make_bare_npu_fc)

# Field order for the parametrized explicit-configuration init test (NPU-specific npu_device_ids + base fields).
INIT_FIELDS = ["npu_device_ids", "ipmi_zone", "temp_calc", "steps", "sensitivity", "polling",
               "min_temp", "max_temp", "min_level", "max_level", "smoothing"]


class TestNpuFc:
    """Unit test class for smfc.NpuFc() class"""

    @pytest.mark.parametrize(
        INIT_FIELDS,
        [
            pytest.param([7], [0], Config.CALC_MIN, 4, 2, 2, 32, 48, 35, 100, 1, id="1card-zone0-min"),
            pytest.param([0, 7], [1], Config.CALC_MAX, 4, 2, 2, 32, 48, 35, 100, 3, id="2cards-zone1-max-smooth3"),
            pytest.param([7, 8, 9], [2], Config.CALC_AVG, 4, 2, 2, 32, 48, 35, 100, 1, id="3cards-zone2-avg"),
        ],
    )
    def test_init_sets_attributes_from_config(self, mocker: MockerFixture, npu_device_ids: List[int],
                                              ipmi_zone: List[int], temp_calc: int, steps: int, sensitivity: float,
                                              polling: float, min_temp: float, max_temp: float, min_level: int,
                                              max_level: int, smoothing: int):
        """Positive unit test for NpuFc.__init__() method. It contains the following steps:
        - mock builtins.print, smfc.NpuFc._exec_smi (via build_npu_fc); Ipmi.__new__ stub
        - build a NpuFc via build_npu_fc() for the parametrized (npu_device_ids, base fields)
        - ASSERT: the base-class contract holds (log/ipmi refs, name, count, configured fields; no hwmon)
        - ASSERT: fc.config.npu_device_ids matches the parametrized npu_device_ids
        - ASSERT: fc.config.npu_smi_path equals the default npu-smi command
        - ASSERT: fc.device_names() returns the npu<id> labels derived from npu_device_ids
        """
        count = len(npu_device_ids)
        cfg_values = {"ipmi_zone": ipmi_zone, "temp_calc": temp_calc, "steps": steps, "sensitivity": sensitivity,
                      "polling": polling, "min_temp": min_temp, "max_temp": max_temp, "min_level": min_level,
                      "max_level": max_level, "smoothing": smoothing}
        h = build_npu_fc(mocker, npu_device_ids=npu_device_ids, **cfg_values)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=cfg_values, log=h.log, ipmi=h.ipmi,
                                has_hwmon=False)
        assert h.fc.config.npu_device_ids == npu_device_ids
        assert h.fc.config.npu_smi_path == Config.DV_NPU_SMI_PATH
        # device_names() synthesizes npu<id> labels from npu_device_ids for the snapshot/exporter path.
        assert h.fc.device_names() == [f"npu{nid}" for nid in npu_device_ids]

    def test_init_applies_defaults(self, mocker: MockerFixture):
        """Positive unit test for NpuFc.__init__() method with default configuration. It contains the following steps:
        - mock builtins.print, smfc.NpuFc._exec_smi (via build_npu_fc); Ipmi.__new__ stub
        - build a NpuFc from a default NPU config (only enabled is set)
        - ASSERT: the base-class contract holds with the Config.DV_NPU_* default values; no hwmon
        - ASSERT: fc.config.npu_device_ids == Config.parse_npu_ids(Config.DV_NPU_DEVICE_IDS)
        - ASSERT: fc.config.npu_smi_path == Config.DV_NPU_SMI_PATH
        - ASSERT: fc.config.npu_smi_timeout == Config.DV_NPU_SMI_TIMEOUT
        """
        count = len(Config.parse_npu_ids(Config.DV_NPU_DEVICE_IDS))
        expected = {"ipmi_zone": [Config.HD_ZONE], "temp_calc": Config.CALC_AVG, "steps": Config.DV_NPU_STEPS,
                    "sensitivity": Config.DV_NPU_SENSITIVITY, "polling": Config.DV_NPU_POLLING,
                    "min_temp": Config.DV_NPU_MIN_TEMP, "max_temp": Config.DV_NPU_MAX_TEMP,
                    "min_level": Config.DV_NPU_MIN_LEVEL, "max_level": Config.DV_NPU_MAX_LEVEL,
                    "smoothing": Config.DV_NPU_SMOOTHING}
        h = build_npu_fc(mocker)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=expected, log=h.log, ipmi=h.ipmi,
                                has_hwmon=False)
        assert h.fc.config.npu_device_ids == Config.parse_npu_ids(Config.DV_NPU_DEVICE_IDS)
        assert h.fc.config.npu_smi_path == Config.DV_NPU_SMI_PATH
        assert h.fc.config.npu_smi_timeout == Config.DV_NPU_SMI_TIMEOUT

    @pytest.mark.parametrize(
        "device_ids",
        [
            pytest.param("#, 0, 1", id="special-char"),
            pytest.param("-1, 0, 1", id="negative-id"),
            pytest.param("0, 101, 1", id="id-over-100"),
        ],
    )
    def test_init_rejects_invalid_device_ids(self, device_ids: str):
        """Negative unit test for Config.parse_npu_ids() / create_npu_config(). It contains the following steps:
        - mock nothing (pure config-layer validation; NpuFc is never constructed)
        - call Config.parse_npu_ids(device_ids) with an invalid id string (special char, negative, > 100)
        - feed the result into create_npu_config(enabled=True, npu_device_ids=...)
        - ASSERT: a ValueError is raised during parsing/validation
        """
        with pytest.raises(ValueError):
            create_npu_config(enabled=True, npu_device_ids=Config.parse_npu_ids(device_ids))

    # pylint: disable=protected-access
    def test_exec_smi_builds_command(self, mocker: MockerFixture):
        """Positive unit test for NpuFc._exec_smi() method. It contains the following steps:
        - mock subprocess.run (MagicMock returning a CompletedProcess with parametrized stdout)
        - build a bare NpuFc via make_bare_npu_fc() (no super().__init__())
        - call fc._exec_smi(card_id)
        - ASSERT: subprocess.run is called with ([npu_smi_path, info, -t, temp, -i, <id>],
          capture_output=True, check=False, text=True, timeout=<configured>)
        - ASSERT: the stdout of the command is returned
        - ASSERT: subprocess.run is called exactly once
        """
        smi_path = "/opt/ascend/bin/npu-smi"
        fc = make_bare_npu_fc(config=create_npu_config(npu_smi_path=smi_path, npu_smi_timeout=20.0))
        mock_run = MagicMock(return_value=subprocess.CompletedProcess([], returncode=0,
                                                                      stdout=NPU_SMI_TEMP_OUTPUT, stderr=""))
        mocker.patch("subprocess.run", mock_run)
        out = fc._exec_smi(7)
        mock_run.assert_called_with([smi_path, "info", "-t", "temp", "-i", "7"], capture_output=True, check=False,
                                    text=True, timeout=20.0)
        assert mock_run.call_count == 1
        assert out == NPU_SMI_TEMP_OUTPUT

    def test_exec_smi_raises_on_missing_command(self):
        """Negative unit test for NpuFc._exec_smi() method. It contains the following steps:
        - mock nothing (the real subprocess.run is used so the missing binary triggers OS error)
        - build a bare NpuFc via make_bare_npu_fc() (no super().__init__())
        - call fc._exec_smi(0) with a nonexistent npu-smi path
        - ASSERT: FileNotFoundError is raised
        """
        fc = make_bare_npu_fc(config=create_npu_config(npu_smi_path="/nonexistent/npu-smi"))
        with pytest.raises(FileNotFoundError):
            fc._exec_smi(0)

    def test_exec_smi_raises_on_nonzero_exit(self, mocker: MockerFixture):
        """Negative unit test for NpuFc._exec_smi() method. It contains the following steps:
        - mock subprocess.run to return a non-zero exit code with an error message on stderr
        - build a bare NpuFc via make_bare_npu_fc() (no super().__init__())
        - call fc._exec_smi(0)
        - ASSERT: RuntimeError is raised and mentions the card id
        """
        fc = make_bare_npu_fc(config=create_npu_config())
        mock_run = MagicMock(return_value=subprocess.CompletedProcess([], returncode=1, stdout="",
                                                                      stderr="invalid card id"))
        mocker.patch("subprocess.run", mock_run)
        with pytest.raises(RuntimeError, match="card 0"):
            fc._exec_smi(0)

    def test_exec_smi_raises_on_timeout(self, mocker: MockerFixture):
        """Negative unit test for NpuFc._exec_smi() method. It contains the following steps:
        - mock subprocess.run to raise subprocess.TimeoutExpired (npu-smi can hang on busy NPU stacks)
        - build a bare NpuFc via make_bare_npu_fc() (no super().__init__())
        - call fc._exec_smi(3)
        - ASSERT: RuntimeError is raised and mentions the timeout
        """
        fc = make_bare_npu_fc(config=create_npu_config(npu_smi_timeout=1.5))
        mocker.patch("subprocess.run", MagicMock(side_effect=subprocess.TimeoutExpired(
            cmd="npu-smi", timeout=1.5)))
        with pytest.raises(RuntimeError, match="timed out"):
            fc._exec_smi(3)

    @pytest.mark.parametrize(
        "output, expected",
        [
            # Real two-chip card output (310P3); MCU block must be ignored.
            pytest.param(NPU_SMI_TEMP_OUTPUT, [39.0, 38.0], id="2chips-with-mcu-block"),
            # Single-chip card.
            pytest.param("        Temperature (C)                : 55\n        Chip ID                        : 0\n",
                         [55.0], id="1chip"),
            # Three-chip card.
            pytest.param("        Temperature (C)                : 30\n"
                         "        Temperature (C)                : 31\n"
                         "        Temperature (C)                : 32\n", [30.0, 31.0, 32.0], id="3chips"),
            # "Soc Max Temperature (C)" (npu-smi -t sensors) must not match the chip-temperature pattern.
            pytest.param("        Soc Max Temperature (C)        : 38\n", [], id="sensors-key-not-matched"),
            # Empty output.
            pytest.param("", [], id="empty"),
        ],
    )
    def test_parse_card_temps(self, output: str, expected: List[float]):
        """Positive/negative unit test for NpuFc.parse_card_temps() static method. It contains the following steps:
        - mock nothing (pure parsing)
        - call NpuFc.parse_card_temps(output) with the parametrized output
        - ASSERT: the returned per-chip temperature list equals the expected list
        """
        assert NpuFc.parse_card_temps(output) == expected

    @pytest.mark.parametrize(
        "card_outputs, npu_device_ids, expected",
        [
            # Single card, two chips: hottest chip wins.
            pytest.param([NPU_SMI_TEMP_OUTPUT], [7], [39.0], id="1card-2chips-max"),
            # Two cards: per-card hottest chip.
            pytest.param([NPU_SMI_TEMP_OUTPUT, NPU_SMI_TEMP_OUTPUT], [7, 8], [39.0, 39.0], id="2cards"),
        ],
    )
    def test_get_nth_temp_reads_smi(self, mocker: MockerFixture, card_outputs: List[str], npu_device_ids: List[int],
                                    expected: List[float]):
        """Positive unit test for NpuFc._get_nth_temp() method. It contains the following steps:
        - mock smfc.NpuFc._exec_smi to return the parametrized per-card outputs
        - build a bare NpuFc via make_bare_npu_fc(config=...) for the parametrized npu_device_ids
        - call fc._get_nth_temp(i) for each configured card
        - ASSERT: the returned temperature equals expected[i] (hottest chip of the card)
        - ASSERT: a second poll within the polling window reuses the cached values (one npu-smi call per card)
        """
        cfg = create_npu_config(npu_device_ids=npu_device_ids, polling=5)
        fc = make_bare_npu_fc(config=cfg)
        mock_smi = MagicMock(side_effect=list(card_outputs))
        mocker.patch("smfc.NpuFc._exec_smi", mock_smi)
        for i in range(len(npu_device_ids)):
            assert fc._get_nth_temp(i) == expected[i]
        assert fc.npu_temperature == expected
        # Second read within the polling window: no new npu-smi call.
        for i in range(len(npu_device_ids)):
            assert fc._get_nth_temp(i) == expected[i]
        assert mock_smi.call_count == len(npu_device_ids)

    @pytest.mark.parametrize(
        "output, npu_device_ids",
        [
            # MCU block only — no chip temperature lines at all.
            pytest.param("        T_LM75A  (C)                   : 29\n        Chip Name                      : MCU\n",
                         [0], id="mcu-only"),
            # Card disappeared (npu-smi printed nothing useful).
            pytest.param("", [0], id="empty-output"),
        ],
    )
    def test_get_nth_temp_raises_on_missing_temps(self, mocker: MockerFixture, output: str,
                                                  npu_device_ids: List[int]):
        """Negative unit test for NpuFc._get_nth_temp() method. It contains the following steps:
        - mock smfc.NpuFc._exec_smi (MagicMock returning a CompletedProcess-like stdout with no chip temps)
        - build a bare NpuFc via make_bare_npu_fc(config=...) for the parametrized npu_device_ids
        - call fc._get_nth_temp(0)
        - ASSERT: ValueError is raised (no chip temperature found in the npu-smi output)
        """
        cfg = create_npu_config(npu_device_ids=npu_device_ids, polling=2)
        fc = make_bare_npu_fc(config=cfg)
        mocker.patch("smfc.NpuFc._exec_smi", MagicMock(return_value=output))
        with pytest.raises(ValueError):
            fc._get_nth_temp(0)

    def test_get_temp_tolerates_failed_poll(self, mocker: MockerFixture):
        """Positive unit test for NpuFc.get_temp() method with a failed poll inside the error_tolerance budget.
        It contains the following steps:
        - build a 2-card NpuFc via build_npu_fc with error_tolerance=2, whose constructor read 39C for both cards
        - mock smfc.NpuFc._exec_smi via mocker.patch: the first poll fails for both cards (one npu-smi call
          per card, e.g. timeouts) and the second poll succeeds for both
        - call NpuFc.get_temp() twice, expiring the SMI rate limiter (smi_called) before each call
        - ASSERT: the failed poll does not raise and both cards reuse their last known good 39C
        - ASSERT: one bad poll advances the counter of both cards by exactly 1
        - ASSERT: the next, good poll returns the fresh reading and resets both counters
        """
        h = build_npu_fc(mocker, npu_device_ids=[7, 8], error_tolerance=2, temp_calc=Config.CALC_MIN)
        # _exec_smi() raises RuntimeError at its boundary when a call times out. A poll aborts on the
        # first failing card, so the failing poll consumes a single call; the next (good) poll reads
        # both cards.
        failed = RuntimeError("npu-smi timed out")
        mocker.patch("smfc.NpuFc._exec_smi",
                     MagicMock(side_effect=[failed, NPU_SMI_TEMP_OUTPUT, NPU_SMI_TEMP_OUTPUT]))
        h.fc.smi_called = 0
        assert h.fc.get_temp() == 39.0
        assert h.fc.last_per_device_temps == [39.0, 39.0]
        assert h.fc._temp_read_errors == [1, 1]
        h.fc.smi_called = 0
        assert h.fc.get_temp() == 39.0
        assert h.fc._temp_read_errors == [0, 0]

    def test_get_temp_exhausts_error_tolerance(self, mocker: MockerFixture):
        """Negative unit test for NpuFc.get_temp() method. It contains the following steps:
        - build a 1-card NpuFc via build_npu_fc with error_tolerance=0
        - mock smfc.NpuFc._exec_smi to keep failing with a RuntimeError
        - call NpuFc.get_temp() with the SMI rate limiter expired
        - ASSERT: the failure propagates (error budget exhausted immediately)
        """
        h = build_npu_fc(mocker, error_tolerance=0)
        mocker.patch("smfc.NpuFc._exec_smi", MagicMock(side_effect=RuntimeError("npu-smi timed out")))
        h.fc.smi_called = 0
        with pytest.raises(RuntimeError):
            h.fc.get_temp()

    # pylint: enable=protected-access


# End.
