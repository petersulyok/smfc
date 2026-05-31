#!/usr/bin/env python3
#
#   test_client.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.client module (smfc-client console script).
#
# pylint: disable=protected-access
import io
from typing import Any, List, Optional, Tuple
from unittest.mock import MagicMock
import pytest
from pytest_mock import MockerFixture
from smfc import client
from smfc.client import (
    EXIT_OK,
    EXIT_CONFIG_ERROR,
    EXIT_IPMI_ERROR,
    EXIT_UDEV_ERROR,
)


def _make_offline_cfg() -> MagicMock:
    """Build a Config-like mock with [Exporter] disabled (forces standalone path in main())."""
    cfg = MagicMock()
    cfg.ipmi = MagicMock()
    cfg.exporter.enabled = False
    return cfg


def _make_fake_ipmi(fan_mode_value: int = 1, fan_level_value: int = 50) -> MagicMock:
    """Create a fully-mocked Ipmi instance suitable for _format_report()."""
    fake = MagicMock()
    fake.bmc_manufacturer_name = "Super Micro Computer Inc."
    fake.bmc_manufacturer_id = 10876
    fake.bmc_product_name = "X11SCH-LN4F"
    fake.bmc_product_id = 6929
    fake.bmc_firmware_rev = "1.74"
    fake.bmc_ipmi_version = "2.0"
    fake.platform.name = "X11SCH-LN4F"
    type(fake.platform).__name__ = "GenericPlatform"
    fake.get_fan_mode.return_value = fan_mode_value
    fake.get_fan_level.return_value = fan_level_value
    return fake


def _make_fake_cpu_controller(zones: Optional[List[int]] = None, count: int = 1, temp: float = 42.3) -> MagicMock:
    """Build a fake CpuFc-like controller used in _format_report tests."""
    zones = zones if zones is not None else [0]
    controller = MagicMock()
    controller.config.ipmi_zone = zones
    controller.count = count
    controller.get_temp.return_value = temp
    return controller


def _make_fake_hd_controller(zones: Optional[List[int]] = None, count: int = 4, temp: float = 34.1,
                             standby_enabled: bool = False, standby_hd_limit: int = 1,
                             standby_states: Optional[List[bool]] = None,
                             hd_names: Optional[List[str]] = None) -> MagicMock:
    """Build a fake HdFc-like controller used in _format_report tests."""
    zones = zones if zones is not None else [1]
    hd_names = hd_names if hd_names is not None else [f"/dev/sd{chr(ord('a') + i)}" for i in range(count)]
    controller = MagicMock()
    controller.config.ipmi_zone = zones
    controller.config.standby_guard_enabled = standby_enabled
    controller.config.standby_hd_limit = standby_hd_limit
    controller.count = count
    controller.get_temp.return_value = temp
    controller.hd_device_names = hd_names
    if standby_enabled and standby_states is not None:
        controller.standby_array_states = standby_states
        controller.get_standby_state_str.return_value = "".join("S" if s else "A" for s in standby_states)
    else:
        # Make sure getattr(... , None) returns None
        del controller.standby_array_states
    return controller


def _make_fake_const_controller(zones: Optional[List[int]] = None, level: int = 50) -> MagicMock:
    """Build a fake ConstFc-like controller used in _format_report tests."""
    zones = zones if zones is not None else [2]
    controller = MagicMock()
    controller.config.ipmi_zone = zones
    controller.config.level = level
    controller.count = 0
    return controller


class TestParseArgs:
    """Unit tests for smfc.client._parse_args()."""

    def test_defaults(self) -> None:
        """Default values are picked up when no flags are supplied."""
        args = client._parse_args([])
        assert args.config_file == client.DEFAULT_CONFIG_PATH
        assert args.sudo is False
        assert args.no_color is False

    def test_short_flags(self) -> None:
        """All short flags map to the right destinations."""
        args = client._parse_args(["-c", "/tmp/foo.conf", "-s", "-nc"])
        assert args.config_file == "/tmp/foo.conf"
        assert args.sudo is True
        assert args.no_color is True

    def test_long_flags(self) -> None:
        """Long-form flags map to the right destinations."""
        args = client._parse_args(["--config", "/tmp/bar.conf", "--sudo", "--no-color"])
        assert args.config_file == "/tmp/bar.conf"
        assert args.sudo is True
        assert args.no_color is True


class TestUseColor:
    """Unit tests for smfc.client._use_color()."""

    def test_no_color_flag_disables(self, mocker: MockerFixture) -> None:
        """--no-color forces colors off even when stdout is a TTY."""
        mocker.patch("sys.stdout.isatty", return_value=True)
        assert client._use_color(True) is False

    def test_tty_enables(self, mocker: MockerFixture) -> None:
        """When stdout is a TTY and --no-color is not set, colors are on."""
        mocker.patch("sys.stdout.isatty", return_value=True)
        assert client._use_color(False) is True

    def test_pipe_disables(self, mocker: MockerFixture) -> None:
        """When stdout is not a TTY (piped), colors are off."""
        mocker.patch("sys.stdout.isatty", return_value=False)
        assert client._use_color(False) is False


class TestFormatReport:
    """Unit tests for smfc.client._format_report() and helpers."""

    def test_basic_report_no_color(self) -> None:
        """A minimal CPU+HD report contains all expected sections without ANSI sequences."""
        ipmi = _make_fake_ipmi(fan_mode_value=1, fan_level_value=55)
        cpu = _make_fake_cpu_controller(zones=[0], count=1, temp=42.3)
        hd = _make_fake_hd_controller(zones=[1], count=4, temp=34.1)
        entries: List[Tuple[str, str, Any, Optional[str]]] = [
            ("CPU", "cpu", cpu, None),
            ("HD", "hd", hd, None),
        ]
        out = client._format_report(ipmi, entries, "/etc/smfc/smfc.conf", use_color=False)
        assert "smfc-client" in out
        assert "/etc/smfc/smfc.conf" in out
        assert "BMC" in out
        assert "Super Micro Computer Inc." in out
        assert "X11SCH-LN4F" in out
        assert "IPMI fan mode" in out
        assert "FULL" in out
        assert "Controllers" in out
        assert "CPU" in out and "HD" in out
        assert "42.3 C" in out
        assert "34.1 C" in out
        assert "IPMI zones (live)" in out
        assert "\x1b[" not in out  # No ANSI sequences in non-color mode

    def test_controller_error_row(self) -> None:
        """A controller construction error renders as ERROR but does not break other rows."""
        ipmi = _make_fake_ipmi()
        cpu = _make_fake_cpu_controller()
        entries = [
            ("CPU", "cpu", cpu, None),
            ("GPU", "gpu", None, "nvidia-smi not found"),
        ]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False)
        assert "ERROR" in out
        assert "nvidia-smi not found" in out
        # The CPU row is still rendered correctly.
        assert "42.3 C" in out

    def test_const_controller_row(self) -> None:
        """A ConstFc row shows '-' for temp and the configured level."""
        ipmi = _make_fake_ipmi()
        const_fc = _make_fake_const_controller(zones=[2], level=50)
        entries = [("CONST", "const", const_fc, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False)
        assert "CONST" in out
        assert "const" in out
        assert " 50 %" in out
        assert "ok (target)" in out

    def test_standby_guard_section_present(self) -> None:
        """Standby Guard section is present when an HD has it enabled with count>1."""
        ipmi = _make_fake_ipmi()
        hd = _make_fake_hd_controller(zones=[1], count=4, standby_enabled=True,
                                      standby_hd_limit=1,
                                      standby_states=[False, False, True, True])
        entries = [("HD", "hd", hd, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False)
        assert "Standby Guard" in out
        assert "/dev/sda" in out
        assert "ACTIVE" in out
        assert "STANDBY" in out
        assert "AASS" in out
        assert "2/4 standby" in out

    def test_standby_guard_section_absent(self) -> None:
        """Standby Guard section is omitted when no HD has it enabled."""
        ipmi = _make_fake_ipmi()
        hd = _make_fake_hd_controller(zones=[1], count=4, standby_enabled=False)
        entries = [("HD", "hd", hd, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False)
        assert "Standby Guard" not in out

    def test_color_mode_emits_ansi(self) -> None:
        """When color mode is enabled, ANSI sequences appear in output."""
        ipmi = _make_fake_ipmi()
        cpu = _make_fake_cpu_controller()
        entries = [("CPU", "cpu", cpu, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=True)
        assert "\x1b[" in out
        # Banner should be bold
        assert client.BOLD in out
        assert client.RESET in out

    def test_fan_mode_standard_renders(self) -> None:
        """STANDARD fan mode (smfc not running) renders without warnings/errors."""
        ipmi = _make_fake_ipmi(fan_mode_value=0)
        cpu = _make_fake_cpu_controller()
        entries = [("CPU", "cpu", cpu, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False)
        assert "STANDARD" in out
        assert "ERROR" not in out

    def test_zones_table_unions_zones(self) -> None:
        """The IPMI zones (live) table contains the union of zones across enabled controllers."""
        ipmi = _make_fake_ipmi()
        cpu = _make_fake_cpu_controller(zones=[0])
        hd = _make_fake_hd_controller(zones=[1])
        const = _make_fake_const_controller(zones=[2])
        entries = [
            ("CPU", "cpu", cpu, None),
            ("HD", "hd", hd, None),
            ("CONST", "const", const, None),
        ]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False)
        # All three zones appear in the live table.
        zone_section = out.split("IPMI zones (live)", 1)[1]
        assert "0" in zone_section
        assert "1" in zone_section
        assert "2" in zone_section


class TestMain:
    """Unit tests for smfc.client.main()."""

    def test_missing_config(self, mocker: MockerFixture, capsys: pytest.CaptureFixture) -> None:
        """A missing config file results in EXIT_CONFIG_ERROR with a hint on stderr."""
        mocker.patch("smfc.client.Config", side_effect=FileNotFoundError("Cannot load configuration file: /nope.conf"))
        rc = client.main(["-c", "/nope.conf"])
        assert rc == EXIT_CONFIG_ERROR
        captured = capsys.readouterr()
        assert "config" in captured.err.lower()

    def test_ipmi_error_emits_sudo_hint(self, mocker: MockerFixture, capsys: pytest.CaptureFixture) -> None:
        """An Ipmi initialization error returns EXIT_IPMI_ERROR with a sudo hint on stderr."""
        mocker.patch("smfc.client.Config", return_value=_make_offline_cfg())
        mocker.patch("smfc.client.Ipmi", side_effect=RuntimeError("ipmitool error (1): permission denied."))
        rc = client.main(["-c", "/dummy.conf"])
        assert rc == EXIT_IPMI_ERROR
        captured = capsys.readouterr()
        assert "sudo" in captured.err.lower()
        assert "ipmitool" in captured.err.lower()

    def test_happy_path(self, mocker: MockerFixture, capsys: pytest.CaptureFixture) -> None:
        """When all stages succeed, main() prints the report and returns EXIT_OK."""
        cfg = _make_offline_cfg()
        mocker.patch("smfc.client.Config", return_value=cfg)
        fake_ipmi = _make_fake_ipmi()
        mocker.patch("smfc.client.Ipmi", return_value=fake_ipmi)
        mocker.patch("smfc.client.Context", return_value=MagicMock())
        cpu = _make_fake_cpu_controller()
        mocker.patch("smfc.client._construct_controllers", return_value=[("CPU", "cpu", cpu, None)])
        # Force no-color so output is deterministic.
        rc = client.main(["-c", "/dummy.conf", "-nc"])
        assert rc == EXIT_OK
        captured = capsys.readouterr()
        assert "smfc-client" in captured.out
        assert "BMC" in captured.out
        assert "Controllers" in captured.out
        assert "CPU" in captured.out
        assert "\x1b[" not in captured.out

    def test_no_tty_disables_color(self, mocker: MockerFixture) -> None:
        """When stdout is not a TTY, the report contains no ANSI sequences even without -nc."""
        cfg = _make_offline_cfg()
        mocker.patch("smfc.client.Config", return_value=cfg)
        fake_ipmi = _make_fake_ipmi()
        mocker.patch("smfc.client.Ipmi", return_value=fake_ipmi)
        mocker.patch("smfc.client.Context", return_value=MagicMock())
        cpu = _make_fake_cpu_controller()
        mocker.patch("smfc.client._construct_controllers", return_value=[("CPU", "cpu", cpu, None)])
        # Replace sys.stdout with a non-TTY StringIO and capture writes.
        buf = io.StringIO()
        mocker.patch("sys.stdout", buf)
        rc = client.main(["-c", "/dummy.conf"])
        assert rc == EXIT_OK
        assert "\x1b[" not in buf.getvalue()

    def test_ipmi_invoked_in_client_mode(self, mocker: MockerFixture) -> None:
        """main() must construct Ipmi with in_client=True and a short bmc_init_timeout."""
        cfg = _make_offline_cfg()
        mocker.patch("smfc.client.Config", return_value=cfg)
        ipmi_ctor = mocker.patch("smfc.client.Ipmi", return_value=_make_fake_ipmi())
        mocker.patch("smfc.client.Context", return_value=MagicMock())
        mocker.patch("smfc.client._construct_controllers", return_value=[])
        rc = client.main(["-c", "/dummy.conf", "-nc"])
        assert rc == EXIT_OK
        # Verify the Ipmi class was called with in_client=True
        kwargs = ipmi_ctor.call_args.kwargs
        assert kwargs.get("in_client") is True
        assert kwargs.get("bmc_init_timeout") == client.CLIENT_BMC_INIT_TIMEOUT

    def test_udev_error(self, mocker: MockerFixture, capsys: pytest.CaptureFixture) -> None:
        """A pyudev Context() failure returns EXIT_UDEV_ERROR with a hint on stderr."""
        cfg = _make_offline_cfg()
        mocker.patch("smfc.client.Config", return_value=cfg)
        mocker.patch("smfc.client.Ipmi", return_value=_make_fake_ipmi())
        mocker.patch("smfc.client.Context", side_effect=OSError("libudev not available"))
        rc = client.main(["-c", "/dummy.conf", "-nc"])
        assert rc == EXIT_UDEV_ERROR
        assert "udev" in capsys.readouterr().err.lower()


class TestUseColorEdgeCases:
    """Cover _use_color() when sys.stdout has no isatty()."""

    def test_isatty_attribute_error(self, mocker: MockerFixture) -> None:
        """A stdout without isatty() (e.g. swapped object) yields no color."""
        fake_stdout = MagicMock(spec=[])  # no isatty attribute
        mocker.patch("sys.stdout", fake_stdout)
        assert client._use_color(False) is False

    def test_isatty_value_error(self, mocker: MockerFixture) -> None:
        """A closed stdout where isatty() raises ValueError yields no color."""
        mocker.patch("sys.stdout.isatty", side_effect=ValueError("I/O on closed file"))
        assert client._use_color(False) is False


class TestSafeHelpers:
    """Cover _safe_temp_str() and _safe_zone_level()."""

    def test_safe_temp_str_none_controller(self) -> None:
        """A None controller renders as '-'."""
        assert client._safe_temp_str(None, "cpu") == "-"

    def test_safe_temp_str_const(self) -> None:
        """A const controller renders as '-' (no temperature concept)."""
        controller = MagicMock()
        assert client._safe_temp_str(controller, "const") == "-"

    def test_safe_temp_str_get_temp_raises(self) -> None:
        """A controller whose get_temp() raises renders as 'ERROR'."""
        controller = MagicMock()
        controller.get_temp.side_effect = RuntimeError("smartctl failed")
        assert client._safe_temp_str(controller, "cpu") == "ERROR"

    def test_safe_zone_level_raises(self) -> None:
        """When ipmi.get_fan_level() raises, the level renders as 'ERROR'."""
        ipmi = MagicMock()
        ipmi.get_fan_level.side_effect = RuntimeError("ipmitool failed")
        assert client._safe_zone_level(ipmi, 0) == "ERROR"


class TestFormatReportErrorPaths:
    """Cover the error branches in _format_*() and _format_report()."""

    def test_controllers_table_error_status(self) -> None:
        """When temp/level read fails the controller row shows 'error' status."""
        ipmi = _make_fake_ipmi()
        ipmi.get_fan_level.side_effect = RuntimeError("ipmitool failed")
        cpu = _make_fake_cpu_controller()
        out = client._format_report(ipmi, [("CPU", "cpu", cpu, None)], "x.conf", use_color=False)
        # ERROR appears in the level column and 'error' is the status word.
        assert "ERROR" in out
        assert "error" in out

    def test_standby_states_truncated(self) -> None:
        """When hd_device_names is longer than standby_array_states, the loop breaks early."""
        ipmi = _make_fake_ipmi()
        # 4 device names but only 2 standby states → loop breaks at i=2.
        hd = _make_fake_hd_controller(zones=[1], count=4, standby_enabled=True,
                                      standby_hd_limit=1, standby_states=[False, False],
                                      hd_names=["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"])
        out = client._format_report(ipmi, [("HD", "hd", hd, None)], "x.conf", use_color=False)
        assert "/dev/sda" in out
        assert "/dev/sdb" in out
        # Devices beyond the standby_states length are not rendered.
        assert "/dev/sdc" not in out
        assert "/dev/sdd" not in out

    def test_standby_states_str_raises(self) -> None:
        """When get_standby_state_str() raises, the per-disk rows still render."""
        ipmi = _make_fake_ipmi()
        hd = _make_fake_hd_controller(zones=[1], count=2, standby_enabled=True,
                                      standby_hd_limit=1, standby_states=[False, True])
        hd.get_standby_state_str.side_effect = RuntimeError("boom")
        out = client._format_report(ipmi, [("HD", "hd", hd, None)], "x.conf", use_color=False)
        assert "Standby Guard" in out
        assert "/dev/sda" in out
        # The "Array state:" summary line is omitted.
        assert "Array state" not in out

    def test_fan_mode_read_error(self) -> None:
        """When ipmi.get_fan_mode() raises, the IPMI fan mode line shows ERROR."""
        ipmi = _make_fake_ipmi()
        ipmi.get_fan_mode.side_effect = RuntimeError("ipmitool failed")
        cpu = _make_fake_cpu_controller()
        out = client._format_report(ipmi, [("CPU", "cpu", cpu, None)], "x.conf", use_color=False)
        assert "IPMI fan mode" in out
        assert "ERROR" in out

    def test_standby_states_attribute_missing(self) -> None:
        """When standby is enabled but standby_array_states is missing, section is skipped."""
        ipmi = _make_fake_ipmi()
        # standby_enabled=True with standby_states=None deletes the attribute on the mock,
        # so getattr(..., None) returns None and the section is omitted.
        hd = _make_fake_hd_controller(zones=[1], count=4, standby_enabled=True,
                                      standby_hd_limit=1, standby_states=None)
        out = client._format_report(ipmi, [("HD", "hd", hd, None)], "x.conf", use_color=False)
        assert "Standby Guard" not in out


class TestConstructControllers:
    """Cover _construct_controllers() — instantiation and per-controller error handling."""

    def _make_cfg(self, cpu=None, hd=None, nvme=None, gpu=None, const=None) -> MagicMock:
        """Build a minimal Config-like object exposing the five controller lists."""
        cfg = MagicMock()
        cfg.cpu = cpu or []
        cfg.hd = hd or []
        cfg.nvme = nvme or []
        cfg.gpu = gpu or []
        cfg.const = const or []
        return cfg

    @staticmethod
    def _entry(section: str, enabled: bool = True) -> MagicMock:
        """Build a per-controller config entry with .section and .enabled."""
        entry = MagicMock()
        entry.section = section
        entry.enabled = enabled
        return entry

    def test_disabled_entries_are_skipped(self, mocker: MockerFixture) -> None:
        """Entries with enabled=False are not constructed."""
        cfg = self._make_cfg(
            cpu=[self._entry("CPU", enabled=False)],
            hd=[self._entry("HD", enabled=False)],
            nvme=[self._entry("NVME", enabled=False)],
            gpu=[self._entry("GPU", enabled=False)],
            const=[self._entry("CONST", enabled=False)],
        )
        cpu_ctor = mocker.patch("smfc.client.CpuFc")
        hd_ctor = mocker.patch("smfc.client.HdFc")
        nvme_ctor = mocker.patch("smfc.client.NvmeFc")
        gpu_ctor = mocker.patch("smfc.client.GpuFc")
        const_ctor = mocker.patch("smfc.client.ConstFc")
        log = MagicMock()
        ipmi = MagicMock()
        udevc = MagicMock()
        entries = client._construct_controllers(log, cfg, ipmi, udevc, sudo=False)
        assert not entries
        cpu_ctor.assert_not_called()
        hd_ctor.assert_not_called()
        nvme_ctor.assert_not_called()
        gpu_ctor.assert_not_called()
        const_ctor.assert_not_called()

    def test_all_enabled_construct_successfully(self, mocker: MockerFixture) -> None:
        """All five controller types get instantiated and returned in order."""
        cfg = self._make_cfg(
            cpu=[self._entry("CPU")],
            hd=[self._entry("HD")],
            nvme=[self._entry("NVME")],
            gpu=[self._entry("GPU")],
            const=[self._entry("CONST")],
        )
        cpu_obj = MagicMock(name="cpu")
        hd_obj = MagicMock(name="hd")
        nvme_obj = MagicMock(name="nvme")
        gpu_obj = MagicMock(name="gpu")
        const_obj = MagicMock(name="const")
        mocker.patch("smfc.client.CpuFc", return_value=cpu_obj)
        mocker.patch("smfc.client.HdFc", return_value=hd_obj)
        mocker.patch("smfc.client.NvmeFc", return_value=nvme_obj)
        mocker.patch("smfc.client.GpuFc", return_value=gpu_obj)
        mocker.patch("smfc.client.ConstFc", return_value=const_obj)
        log = MagicMock()
        ipmi = MagicMock()
        udevc = MagicMock()
        entries = client._construct_controllers(log, cfg, ipmi, udevc, sudo=True)
        assert list(entries) == [
            ("CPU", "cpu", cpu_obj, None),
            ("HD", "hd", hd_obj, None),
            ("NVME", "nvme", nvme_obj, None),
            ("GPU", "gpu", gpu_obj, None),
            ("CONST", "const", const_obj, None),
        ]

    def test_per_controller_failures_become_error_rows(self, mocker: MockerFixture) -> None:
        """A constructor exception in any of the five controller types becomes an ERROR row."""
        cfg = self._make_cfg(
            cpu=[self._entry("CPU")],
            hd=[self._entry("HD")],
            nvme=[self._entry("NVME")],
            gpu=[self._entry("GPU")],
            const=[self._entry("CONST")],
        )
        mocker.patch("smfc.client.CpuFc", side_effect=RuntimeError("cpu boom"))
        mocker.patch("smfc.client.HdFc", side_effect=RuntimeError("hd boom"))
        mocker.patch("smfc.client.NvmeFc", side_effect=ValueError("nvme boom"))
        mocker.patch("smfc.client.GpuFc", side_effect=FileNotFoundError("nvidia-smi missing"))
        mocker.patch("smfc.client.ConstFc", side_effect=RuntimeError("const boom"))
        log = MagicMock()
        ipmi = MagicMock()
        udevc = MagicMock()
        entries = client._construct_controllers(log, cfg, ipmi, udevc, sudo=False)
        # All five produced ERROR rows; ordering matches iteration order.
        assert entries[0][0:3] == ("CPU", "cpu", None) and "cpu boom" in entries[0][3]
        assert entries[1][0:3] == ("HD", "hd", None) and "hd boom" in entries[1][3]
        assert entries[2][0:3] == ("NVME", "nvme", None) and "nvme boom" in entries[2][3]
        assert entries[3][0:3] == ("GPU", "gpu", None) and "nvidia-smi" in entries[3][3]
        assert entries[4][0:3] == ("CONST", "const", None) and "const boom" in entries[4][3]


def _sample_snapshot_dict() -> dict:
    """A minimal valid /snapshot response for online-path tests."""
    return {
        "version": 1,
        "generated_at": 1716902400.0,
        "smfc_version": "5.4.0",
        "bmc": {
            "manufacturer_name": "Super Micro Computer Inc.",
            "manufacturer_id": 10876,
            "product_name": "X11SCH-LN4F",
            "product_id": 6929,
            "firmware_rev": "1.74",
            "ipmi_version": "2.0",
            "platform_name": "X11SCH-LN4F",
            "platform_class": "GenericPlatform",
        },
        "fan_mode": {"id": 1, "name": "FULL", "age_s": 0.5},
        "controllers": [
            {
                "section": "CPU", "type": "cpu", "enabled": True,
                "ipmi_zones": [0], "device_count": 1, "polling": 2.0,
                "last_temp_c": 42.3, "last_level_pct": 45, "deferred_apply": False,
            },
            {
                "section": "HD", "type": "hd", "enabled": True,
                "ipmi_zones": [1], "device_count": 4, "polling": 10.0,
                "last_temp_c": 34.1, "last_level_pct": 55, "deferred_apply": False,
                "device_names": ["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"],
                "standby": {
                    "enabled": True, "limit": 1,
                    "states": [False, False, True, True],
                    "array_state": "AASS", "standby_count": 2,
                },
            },
        ],
        "zones": {"0": {"applied_level_pct": 45}, "1": {"applied_level_pct": 55}},
    }


class TestFormatReportFromSnapshot:
    """Unit tests for _format_report_from_snapshot()."""

    def test_basic_report(self) -> None:
        """The online-path report emits the Source line and all the standard sections."""
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "/etc/smfc/smfc.conf", use_color=False)
        assert out.startswith("smfc-client 5.4.0\n")
        assert "    config: /etc/smfc/smfc.conf\n" in out
        assert "    source: online (via smfc service)\n" in out
        assert "/etc/smfc/smfc.conf" in out
        assert "BMC" in out
        assert "Super Micro Computer Inc." in out
        assert "FULL" in out
        assert "Controllers" in out
        assert "42.3 C" in out
        assert "34.1 C" in out
        assert "IPMI zones (live)" in out

    def test_standby_section_present_when_enabled(self) -> None:
        """The Standby Guard section renders the per-disk states from the snapshot."""
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False)
        assert "Standby Guard" in out
        assert "/dev/sda" in out
        assert "ACTIVE" in out
        assert "STANDBY" in out
        assert "AASS" in out
        assert "2/4 standby" in out

    def test_standby_section_absent_when_disabled(self) -> None:
        """If no HD has standby enabled, the Standby Guard section is omitted."""
        snap = _sample_snapshot_dict()
        snap["controllers"][1]["standby"] = {"enabled": False}
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False)
        assert "Standby Guard" not in out

    def test_color_mode_emits_ansi(self) -> None:
        """ANSI sequences appear in the report when colors are enabled."""
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=True)
        assert "\x1b[" in out
        assert client.BOLD in out
        assert client.DIM in out  # Source line is dim

    def test_const_controller_shows_target_level(self) -> None:
        """A ConstFc entry's row shows the configured target level and the (target) status hint."""
        snap = _sample_snapshot_dict()
        snap["controllers"].append({
            "section": "CONST", "type": "const", "enabled": True,
            "ipmi_zones": [2], "device_count": 0, "polling": 30.0,
            "last_temp_c": 0.0, "last_level_pct": 50, "deferred_apply": False,
            "target_level_pct": 50,
        })
        snap["zones"]["2"] = {"applied_level_pct": 50}
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False)
        assert "CONST" in out
        assert " 50 %" in out
        assert "ok (target)" in out

    def test_non_full_fan_mode_renders_red(self) -> None:
        """When the cached fan_mode is not FULL, the value is emphasized differently (color test)."""
        snap = _sample_snapshot_dict()
        snap["fan_mode"] = {"id": 0, "name": "STANDARD", "age_s": 0.5}
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=True)
        # The label is wrapped in RED (not GREEN) when mode != FULL.
        assert client.RED in out

    def test_standby_states_shorter_than_devices_truncates(self) -> None:
        """Defensive: when standby.states is shorter than device_names, the loop stops at the shorter length."""
        snap = _sample_snapshot_dict()
        # 4 device names but only 2 states — the loop must break at i=2.
        snap["controllers"][1]["standby"] = {
            "enabled": True, "limit": 1, "states": [False, False],
            "array_state": "AA", "standby_count": 0,
        }
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False)
        assert "/dev/sda" in out
        assert "/dev/sdb" in out
        # Devices beyond the states length are not rendered.
        assert "/dev/sdc" not in out
        assert "/dev/sdd" not in out


class TestTryFetchSnapshot:
    """Unit tests for _try_fetch_snapshot()."""

    def _exporter_cfg(self, host: str = "127.0.0.1", port: int = 9099) -> MagicMock:
        cfg = MagicMock()
        cfg.bind_address = host
        cfg.port = port
        return cfg

    def test_success(self, mocker: MockerFixture) -> None:
        """A 200 response with valid JSON returns the parsed dict."""
        body = b'{"version": 1, "ok": true}'
        fake_resp = MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = body
        ctx = MagicMock()
        ctx.__enter__.return_value = fake_resp
        ctx.__exit__.return_value = False
        mocker.patch("smfc.client.urllib.request.urlopen", return_value=ctx)
        result = client._try_fetch_snapshot(self._exporter_cfg())
        assert result == {"version": 1, "ok": True}

    def test_connection_refused_returns_none(self, mocker: MockerFixture) -> None:
        """A URLError (e.g. connection refused) yields None, not an exception."""
        import urllib.error  # pylint: disable=import-outside-toplevel
        mocker.patch("smfc.client.urllib.request.urlopen",
                     side_effect=urllib.error.URLError("Connection refused"))
        assert client._try_fetch_snapshot(self._exporter_cfg()) is None

    def test_timeout_returns_none(self, mocker: MockerFixture) -> None:
        """A TimeoutError yields None."""
        mocker.patch("smfc.client.urllib.request.urlopen", side_effect=TimeoutError("slow"))
        assert client._try_fetch_snapshot(self._exporter_cfg()) is None

    def test_non_200_returns_none(self, mocker: MockerFixture) -> None:
        """A non-200 status (500) yields None."""
        fake_resp = MagicMock()
        fake_resp.status = 500
        fake_resp.read.return_value = b""
        ctx = MagicMock()
        ctx.__enter__.return_value = fake_resp
        ctx.__exit__.return_value = False
        mocker.patch("smfc.client.urllib.request.urlopen", return_value=ctx)
        assert client._try_fetch_snapshot(self._exporter_cfg()) is None

    def test_malformed_json_returns_none(self, mocker: MockerFixture) -> None:
        """A 200 with non-JSON body yields None."""
        fake_resp = MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = b"not json"
        ctx = MagicMock()
        ctx.__enter__.return_value = fake_resp
        ctx.__exit__.return_value = False
        mocker.patch("smfc.client.urllib.request.urlopen", return_value=ctx)
        assert client._try_fetch_snapshot(self._exporter_cfg()) is None

    def test_non_dict_payload_returns_none(self, mocker: MockerFixture) -> None:
        """A JSON list or scalar (not a dict) yields None — the schema is a dict."""
        fake_resp = MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = b"[1,2,3]"
        ctx = MagicMock()
        ctx.__enter__.return_value = fake_resp
        ctx.__exit__.return_value = False
        mocker.patch("smfc.client.urllib.request.urlopen", return_value=ctx)
        assert client._try_fetch_snapshot(self._exporter_cfg()) is None

    def test_unspecified_bind_address_uses_localhost(self, mocker: MockerFixture) -> None:
        """When the service binds to 0.0.0.0, the client connects to 127.0.0.1 instead."""
        captured = {}

        def fake_urlopen(url, timeout):  # pylint: disable=unused-argument
            captured["url"] = url
            raise TimeoutError("fake")

        mocker.patch("smfc.client.urllib.request.urlopen", side_effect=fake_urlopen)
        client._try_fetch_snapshot(self._exporter_cfg(host="0.0.0.0", port=9099))
        assert captured["url"] == "http://127.0.0.1:9099/snapshot"


class TestMainOnlinePath:
    """Integration tests: main() with [Exporter] enabled."""

    def _exporter_enabled_cfg(self) -> MagicMock:
        cfg = MagicMock()
        cfg.exporter.enabled = True
        cfg.exporter.bind_address = "127.0.0.1"
        cfg.exporter.port = 9099
        return cfg

    def test_online_path_taken_when_reachable(self, mocker: MockerFixture, capsys: pytest.CaptureFixture) -> None:
        """When [Exporter] enabled and /snapshot reachable, online formatter is used and standalone is skipped."""
        mocker.patch("smfc.client.Config", return_value=self._exporter_enabled_cfg())
        mocker.patch("smfc.client._try_fetch_snapshot", return_value=_sample_snapshot_dict())
        # Standalone path setup — we want to verify these are NOT touched on the online path.
        ipmi_ctor = mocker.patch("smfc.client.Ipmi", return_value=_make_fake_ipmi())
        ctx_ctor = mocker.patch("smfc.client.Context", return_value=MagicMock())
        construct = mocker.patch("smfc.client._construct_controllers", return_value=[])
        rc = client.main(["-c", "/dummy.conf", "-nc"])
        assert rc == EXIT_OK
        captured = capsys.readouterr()
        assert "    source: online" in captured.out
        # Online path means none of the standalone construction work happens.
        assert ipmi_ctor.call_count == 0, "Ipmi must not be constructed on the online path"
        assert ctx_ctor.call_count == 0, "pyudev Context must not be constructed on the online path"
        assert construct.call_count == 0, "controllers must not be constructed on the online path"

    def test_falls_back_to_standalone_on_unreachable(self, mocker: MockerFixture,
                                                     capsys: pytest.CaptureFixture) -> None:
        """When [Exporter] enabled but /snapshot unreachable, main() falls back to the standalone path."""
        mocker.patch("smfc.client.Config", return_value=self._exporter_enabled_cfg())
        mocker.patch("smfc.client._try_fetch_snapshot", return_value=None)
        mocker.patch("smfc.client.Ipmi", return_value=_make_fake_ipmi())
        mocker.patch("smfc.client.Context", return_value=MagicMock())
        cpu = _make_fake_cpu_controller()
        mocker.patch("smfc.client._construct_controllers", return_value=[("CPU", "cpu", cpu, None)])
        rc = client.main(["-c", "/dummy.conf", "-nc"])
        assert rc == EXIT_OK
        out = capsys.readouterr().out
        assert "    source: offline (smfc service not running)" in out
        assert "smfc-client" in out

    def test_standalone_flag_forces_offline(self, mocker: MockerFixture,
                                            capsys: pytest.CaptureFixture) -> None:
        """`--standalone` skips /snapshot even when the exporter is reachable."""
        mocker.patch("smfc.client.Config", return_value=self._exporter_enabled_cfg())
        # If the online path were attempted, this would assert.
        try_fetch = mocker.patch("smfc.client._try_fetch_snapshot", return_value=_sample_snapshot_dict())
        mocker.patch("smfc.client.Ipmi", return_value=_make_fake_ipmi())
        mocker.patch("smfc.client.Context", return_value=MagicMock())
        cpu = _make_fake_cpu_controller()
        mocker.patch("smfc.client._construct_controllers", return_value=[("CPU", "cpu", cpu, None)])
        rc = client.main(["-c", "/dummy.conf", "-nc", "--standalone"])
        assert rc == EXIT_OK
        out = capsys.readouterr().out
        assert "    source: offline (smfc service not running)" in out
        assert try_fetch.call_count == 0, "_try_fetch_snapshot must not be called when --standalone is passed"


# End.
