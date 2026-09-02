#!/usr/bin/env python3
#
#   test_pcifc.py (C) 2026, Peter Sulyok
#   Unit tests for smfc.PciFc() class.
#
import os
from typing import List
import pyudev
import pytest
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import Ipmi, Log, PciFc
from smfc.config import Config
from .test_config_builders import create_pci_config
from .test_fixtures import TestData
from .test_fc_helpers import assert_fc_base_contract, build_pci_fc, make_bare_pci_fc
from .test_mocks import MockPciDevice

# Field order for the parametrized explicit-configuration init test.
CONFIG_FIELDS = ["count", "ipmi_zone", "temp_calc", "steps", "sensitivity", "polling", "min_temp", "max_temp",
                 "min_level", "max_level", "smoothing"]


class TestPciFc:
    """Unit test class for smfc.PciFc() class"""

    @pytest.mark.parametrize(
        CONFIG_FIELDS,
        [
            pytest.param(1, [0], Config.CALC_MIN, 6, 2, 2, 30, 60, 35, 100, 1, id="1pci-zone0-min"),
            pytest.param(2, [1], Config.CALC_AVG, 6, 2, 2, 30, 60, 35, 100, 3, id="2pci-zone1-avg-smooth3"),
            pytest.param(4, [2], Config.CALC_MAX, 4, 3, 5, 40, 80, 20, 90, 1, id="4pci-zone2-max"),
        ],
    )
    def test_init_sets_attributes_from_config(self, mocker: MockerFixture, td: TestData, count: int,
                                              ipmi_zone: List[int], temp_calc: int, steps: int, sensitivity: float,
                                              polling: float, min_temp: float, max_temp: float, min_level: int,
                                              max_level: int, smoothing: int):
        """Positive unit test for PciFc.__init__() method. It contains the following steps:
        - mock build_pci_fc helper (absorbs builtins.print, pyudev.Context.list_devices,
          smfc.pcifc.Devices.from_name, smfc.FanController.get_hwmon_paths, pyudev.Context.__new__,
          Ipmi.__new__ mocks)
        - parametrize explicit config field values (count, ipmi_zone, temp_calc, steps, sensitivity, polling,
          min_temp, max_temp, min_level, max_level, smoothing) and build a PciFc from that config
        - invoke assert_fc_base_contract to validate the shared FanController contract
        - call device_names() to verify it returns a defensive copy of device_labels
        - ASSERT: assert_fc_base_contract holds (log/ipmi refs, config, name, count, config fields)
        - ASSERT: fc.hwmon_path equals td.pci_files
        - ASSERT: fc.pci_devices equals td.pci_addresses (sorted by PCI slot address)
        - ASSERT: device_names() returns a list equal to td.pci_addresses
        - ASSERT: device_names() result is not the same object as fc.device_labels (defensive copy)
        """
        cfg_values = {"ipmi_zone": ipmi_zone, "temp_calc": temp_calc, "steps": steps, "sensitivity": sensitivity,
                      "polling": polling, "min_temp": min_temp, "max_temp": max_temp, "min_level": min_level,
                      "max_level": max_level, "smoothing": smoothing}
        h = build_pci_fc(mocker, td, count=count, **cfg_values)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=cfg_values, log=h.log, ipmi=h.ipmi)
        assert h.fc.hwmon_path == td.pci_files
        assert h.fc.pci_devices == td.pci_addresses
        names = h.fc.device_names()
        assert names == td.pci_addresses
        assert names is not h.fc.device_labels

    def test_init_applies_defaults(self, mocker: MockerFixture, td: TestData):
        """Positive unit test for PciFc.__init__() method using default configuration values. It contains the
        following steps:
        - mock build_pci_fc helper (absorbs builtins.print, pyudev.Context.list_devices,
          smfc.pcifc.Devices.from_name, smfc.FanController.get_hwmon_paths, pyudev.Context.__new__,
          Ipmi.__new__ mocks)
        - build a PciFc from a config with only enabled and pci_driver set, leaving every other field at its
          Config.DV_PCI_* default
        - invoke assert_fc_base_contract with the expected Config.DV_PCI_* default values
        - ASSERT: assert_fc_base_contract holds (log/ipmi refs, config, name, count, default config fields)
        - ASSERT: fc.hwmon_path equals td.pci_files
        - ASSERT: fc.config.temp_sensor equals Config.DV_PCI_TEMP_SENSOR
        """
        count = 2
        expected = {"ipmi_zone": [Config.HD_ZONE], "temp_calc": Config.CALC_MAX, "steps": Config.DV_PCI_STEPS,
                    "sensitivity": Config.DV_PCI_SENSITIVITY, "polling": Config.DV_PCI_POLLING,
                    "min_temp": Config.DV_PCI_MIN_TEMP, "max_temp": Config.DV_PCI_MAX_TEMP,
                    "min_level": Config.DV_PCI_MIN_LEVEL, "max_level": Config.DV_PCI_MAX_LEVEL,
                    "smoothing": Config.DV_PCI_SMOOTHING}
        h = build_pci_fc(mocker, td, count=count)
        assert_fc_base_contract(h.fc, h.cfg, count=count, expected=expected, log=h.log, ipmi=h.ipmi)
        assert h.fc.hwmon_path == td.pci_files
        assert h.fc.config.temp_sensor == Config.DV_PCI_TEMP_SENSOR

    @pytest.mark.parametrize(
        "addressing",
        [
            pytest.param("driver", id="pci_driver"),
            pytest.param("id", id="pci_id"),
            pytest.param("address", id="pci_address"),
        ],
    )
    def test_init_resolves_all_addressing_forms(self, mocker: MockerFixture, td: TestData, addressing: str):
        """Positive unit test for PciFc._resolve_devices() through all three addressing parameters. It contains
        the following steps:
        - mock build_pci_fc helper (absorbs builtins.print, pyudev.Context.list_devices,
          smfc.pcifc.Devices.from_name, smfc.FanController.get_hwmon_paths, pyudev.Context.__new__,
          Ipmi.__new__ mocks)
        - parametrize the three addressing forms: pci_driver=, pci_id= and pci_address=
        - build a PciFc with two identical cards resolved through the parametrized form
        - ASSERT: fc.count is 2 for every form (all three resolve the same two cards)
        - ASSERT: fc.pci_devices equals td.pci_addresses for every form
        """
        h = build_pci_fc(mocker, td, count=2, addressing=addressing)
        assert h.fc.count == 2
        assert h.fc.pci_devices == td.pci_addresses

    def test_init_counts_hwmon_devices_not_cards(self, mocker: MockerFixture, td: TestData):
        """Positive unit test for PciFc.__init__() when a card carries several hwmon devices. It contains the
        following steps:
        - mock build_pci_fc helper (absorbs builtins.print, pyudev.Context.list_devices,
          smfc.pcifc.Devices.from_name, smfc.FanController.get_hwmon_paths, pyudev.Context.__new__,
          Ipmi.__new__ mocks)
        - build a PciFc with one card owning three hwmon devices (the SATA controller shape)
        - read the per-device labels back with device_names()
        - ASSERT: fc.count is 3, i.e. the count is the number of hwmon devices, not the number of cards
        - ASSERT: fc.pci_devices holds the single card address
        - ASSERT: device_names() returns three unique labels, each prefixed with the card address
        """
        h = build_pci_fc(mocker, td, count=1, hwmon_per_card=3)
        assert h.fc.count == 3
        assert h.fc.pci_devices == td.pci_addresses
        names = h.fc.device_names()
        assert len(set(names)) == 3
        for name in names:
            assert name.startswith(td.pci_addresses[0] + "/")

    def test_init_rejects_different_models_in_pci_address(self, mocker: MockerFixture, td: TestData):
        """Negative unit test for PciFc._validate_same_model() method. It contains the following steps:
        - mock build_pci_fc helper (absorbs builtins.print, pyudev.Context.list_devices,
          smfc.pcifc.Devices.from_name, smfc.FanController.get_hwmon_paths, pyudev.Context.__new__,
          Ipmi.__new__ mocks)
        - build a PciFc with pci_address= listing two cards that report different PCI_ID values
        - ASSERT: PciFc.__init__() raises RuntimeError, because one section must cover one kind of device
        """
        with pytest.raises(RuntimeError):
            build_pci_fc(mocker, td, count=2, addressing="address", pci_ids=["1D6A:07B1", "144D:A80C"])

    def test_init_accepts_different_models_from_pci_driver(self, mocker: MockerFixture, td: TestData):
        """Positive unit test for PciFc.__init__() when a driver serves several models. It contains the
        following steps:
        - mock build_pci_fc helper (absorbs builtins.print, pyudev.Context.list_devices,
          smfc.pcifc.Devices.from_name, smfc.FanController.get_hwmon_paths, pyudev.Context.__new__,
          Ipmi.__new__ mocks)
        - build a PciFc with pci_driver= resolving two cards that report different PCI_ID values, the way the
          `nvme` driver serves NVMe drives of different brands
        - ASSERT: PciFc.__init__() succeeds and fc.count is 2 (the same-model check is pci_address= only)
        """
        h = build_pci_fc(mocker, td, count=2, addressing="driver", pci_ids=["144D:A80C", "15B7:5011"])
        assert h.fc.count == 2

    @pytest.mark.parametrize(
        "addressing, empty",
        [
            pytest.param("id", True, id="pci_id-no-match"),
            pytest.param("driver", True, id="pci_driver-no-match"),
            pytest.param("address", False, id="pci_address-not-present"),
        ],
    )
    def test_init_rejects_unresolvable_devices(self, mocker: MockerFixture, addressing: str, empty: bool):
        """Negative unit test for PciFc._resolve_devices() method when no device can be resolved. It contains
        the following steps:
        - mock builtins.print, pyudev.Context.__new__ and Ipmi.__new__
        - parametrize three scenarios: pci_id= matching nothing, pci_driver= matching nothing (both mocked
          with an empty pyudev.Context.list_devices result), and pci_address= naming a card that is not in
          the udev database (mocked with a DeviceNotFoundByNameError from pyudev.Devices.from_name)
        - construct a PciFc from the matching config and expect construction to fail
        - ASSERT: PciFc.__init__() raises RuntimeError for every scenario
        """
        mocker.patch("builtins.print", MagicMock())
        if empty:
            mocker.patch("pyudev.Context.list_devices", MagicMock(return_value=[]))
        else:
            mocker.patch("smfc.pcifc.Devices.from_name",
                         MagicMock(side_effect=pyudev.DeviceNotFoundByNameError("pci", "0000:99:00.0")))
        kwargs = {"id": {"pci_id": "dead:beef"}, "driver": {"pci_driver": "no_such_driver"},
                  "address": {"pci_address": ["0000:99:00.0"]}}[addressing]
        cfg = create_pci_config(enabled=True, **kwargs)
        with pytest.raises(RuntimeError):
            PciFc(Log(Log.LOG_DEBUG, Log.LOG_STDOUT), pyudev.Context.__new__(pyudev.Context),
                  Ipmi.__new__(Ipmi), cfg)

    def test_init_rejects_card_without_hwmon(self, mocker: MockerFixture):
        """Negative unit test for PciFc.__init__() method when a resolved card has no hwmon device. It contains
        the following steps:
        - mock builtins.print, pyudev.Context.list_devices (one card), pyudev.Context.__new__ and Ipmi.__new__
        - mock smfc.FanController.get_hwmon_paths to return an empty list (the card exposes no hwmon device)
        - construct a PciFc with pci_driver= and expect construction to fail
        - ASSERT: PciFc.__init__() raises RuntimeError, because a card with no hwmon device has no temperature
        """
        mocker.patch("builtins.print", MagicMock())
        mocker.patch("pyudev.Context.list_devices", MagicMock(return_value=[MockPciDevice("0000:05:00.0")]))
        mocker.patch("smfc.FanController.get_hwmon_paths", MagicMock(return_value=[]))
        cfg = create_pci_config(enabled=True, pci_driver="atlantic")
        with pytest.raises(RuntimeError):
            PciFc(Log(Log.LOG_DEBUG, Log.LOG_STDOUT), pyudev.Context.__new__(pyudev.Context),
                  Ipmi.__new__(Ipmi), cfg)

    # pylint: disable=protected-access
    @pytest.mark.parametrize(
        "count, temperatures",
        [
            pytest.param(1, [45], id="1pci"),
            pytest.param(2, [45, 58], id="2pci"),
            pytest.param(4, [45, 58, 60, 62], id="4pci"),
        ],
    )
    def test_get_nth_temp_reads_hwmon(self, td: TestData, count: int, temperatures: List[float]):
        """Positive unit test for PciFc._get_nth_temp() method. It contains the following steps:
        - call td.create_pci_data() to materialize PCI hwmon files with the parametrized per-device
          temperatures
        - mock build via make_bare_pci_fc helper (bypasses udev/super().__init__(), sets only hwmon_path,
          pci_devices and device_labels attributes)
        - iterate over each device index and read its temperature back through _get_nth_temp()
        - ASSERT: _get_nth_temp(i) returns the temperature written to device i's hwmon file for every i
        """
        td.create_pci_data(count, temperatures)
        fc = make_bare_pci_fc(td)
        for i in range(count):
            assert fc._get_nth_temp(i) == temperatures[i]

    @pytest.mark.parametrize(
        "operation, exception",
        [
            pytest.param(0, FileNotFoundError, id="missing-file"),
            pytest.param(1, ValueError, id="invalid-value"),
            pytest.param(2, IndexError, id="index-overflow"),
        ],
    )
    def test_get_nth_temp_raises_on_io_errors(self, td: TestData, operation: int, exception):
        """Negative unit test for PciFc._get_nth_temp() method error handling. It contains the following steps:
        - call td.create_pci_data() to materialize a single PCI hwmon file
        - mock build via make_bare_pci_fc helper (bypasses udev/super().__init__(), sets only hwmon_path,
          pci_devices and device_labels attributes)
        - parametrize three failure modes: redirect hwmon_path[0] to a non-existent file (missing file),
          overwrite the hwmon file with "invalid value" (unparsable numeric), or use index 1000 (out of range)
        - call _get_nth_temp() with the chosen index and expect it to fail
        - ASSERT: _get_nth_temp() raises the matching exception (FileNotFoundError, ValueError, or IndexError)
        """
        td.create_pci_data(1, [45])
        fc = make_bare_pci_fc(td)
        index = 0
        if operation == 0:
            fc.hwmon_path[0] = "/tmp/non_existent_dir/non_existent_file"
        elif operation == 1:
            with open(fc.hwmon_path[0], "w+t", encoding="UTF-8") as f:
                f.write("invalid value")
        else:
            index = 1000
        with pytest.raises(exception):
            fc._get_nth_temp(index)

    # pylint: enable=protected-access


class TestGetHwmonPaths:
    """Unit test class for the smfc.FanController.get_hwmon_paths() method added for PciFc."""

    @pytest.mark.parametrize(
        "node_count, sensor",
        [
            pytest.param(1, 1, id="1node-temp1"),
            pytest.param(1, 2, id="1node-temp2"),
            pytest.param(3, 1, id="3nodes-temp1"),
        ],
    )
    def test_collects_every_hwmon_device(self, mocker: MockerFixture, td: TestData, node_count: int, sensor: int):
        """Positive unit test for FanController.get_hwmon_paths() method. It contains the following steps:
        - call td.create_pci_data() to materialize one card with the parametrized number of hwmon devices and
          the parametrized sensor index
        - mock pyudev.Context.list_devices to return one mock hwmon device per materialized hwmon directory
        - call get_hwmon_paths() with the parametrized sensor index
        - ASSERT: the returned list holds one path per hwmon device, in hwmon device path order
        - ASSERT: every returned path ends with temp<sensor>_input
        """
        td.create_pci_data(1, hwmon_per_card=node_count, sensor=sensor)
        devices = [MagicMock(sys_path=os.path.dirname(p)) for p in td.pci_files]
        mocker.patch("pyudev.Context.list_devices", MagicMock(return_value=devices))
        udevc = pyudev.Context.__new__(pyudev.Context)
        paths = PciFc.get_hwmon_paths(udevc, MagicMock(), sensor)
        assert paths == sorted(td.pci_files)
        for path in paths:
            assert path.endswith(f"temp{sensor}_input")

    def test_returns_empty_list_without_hwmon_device(self, mocker: MockerFixture):
        """Positive unit test for FanController.get_hwmon_paths() method with no hwmon device. It contains the
        following steps:
        - mock pyudev.Context.list_devices to return an empty device list
        - call get_hwmon_paths() on that context
        - ASSERT: get_hwmon_paths() returns an empty list (the caller decides whether that is an error)
        """
        mocker.patch("pyudev.Context.list_devices", MagicMock(return_value=[]))
        udevc = pyudev.Context.__new__(pyudev.Context)
        assert not PciFc.get_hwmon_paths(udevc, MagicMock())

    def test_rejects_missing_sensor_file(self, mocker: MockerFixture, td: TestData):
        """Negative unit test for FanController.get_hwmon_paths() method when the sensor file is missing. It
        contains the following steps:
        - call td.create_pci_data() to materialize one card with a temp1_input file only
        - mock pyudev.Context.list_devices to return one mock hwmon device for it
        - call get_hwmon_paths() with sensor index 3, which the hwmon device does not expose
        - ASSERT: get_hwmon_paths() raises RuntimeError naming the missing temp3_input file
        """
        td.create_pci_data(1)
        devices = [MagicMock(sys_path=os.path.dirname(td.pci_files[0]))]
        mocker.patch("pyudev.Context.list_devices", MagicMock(return_value=devices))
        udevc = pyudev.Context.__new__(pyudev.Context)
        with pytest.raises(RuntimeError, match="temp3_input"):
            PciFc.get_hwmon_paths(udevc, MagicMock(), 3)


# End.
