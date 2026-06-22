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
        assert args.verbose is False

    def test_short_flags(self) -> None:
        """All short flags map to the right destinations."""
        args = client._parse_args(["-c", "/tmp/foo.conf", "-s", "-nc", "-V"])
        assert args.config_file == "/tmp/foo.conf"
        assert args.sudo is True
        assert args.no_color is True
        assert args.verbose is True

    def test_long_flags(self) -> None:
        """Long-form flags map to the right destinations."""
        args = client._parse_args(["--config", "/tmp/bar.conf", "--sudo", "--no-color", "--verbose"])
        assert args.config_file == "/tmp/bar.conf"
        assert args.sudo is True
        assert args.no_color is True
        assert args.verbose is True


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
        # Non-verbose BMC: only Product + Fan mode are shown. Manufacturer is verbose-only.
        assert "Super Micro Computer Inc." not in out
        assert "X11SCH-LN4F" in out
        assert "Fan mode" in out
        assert "FULL" in out
        assert "Fan controllers" in out
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
        # The Status column was removed; the const row carries no status hint.
        assert "Status" not in out

    def test_standby_guard_section_present(self) -> None:
        """Standby Guard line appears inside the HD verbose block when enabled with count>1."""
        ipmi = _make_fake_ipmi()
        hd = _make_fake_hd_controller(zones=[1], count=4, standby_enabled=True,
                                      standby_hd_limit=1,
                                      standby_states=[False, False, True, True])
        hd.device_names.return_value = ["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"]
        hd._get_nth_temp.side_effect = lambda i: [33.0, 34.5, 36.1, 39.0][i]
        entries = [("HD", "hd", hd, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False, verbose=True)
        assert "Standby Guard: enabled (limit=1)" in out
        # The standby line is folded into the [HD] block, not a free-standing section.
        hd_block = out.split("[HD]", 1)[1]
        assert "Standby Guard" in hd_block.split("\n\n", 1)[0]
        # HD device names render as the basename only (full /dev/disk/by-id/... paths get stripped).
        assert "  sda" in out
        assert "/dev/sda" not in out
        assert "ACTIVE" in out
        assert "STANDBY" in out
        assert "AASS" in out
        assert "2/4 standby" in out

    def test_standby_guard_section_absent(self) -> None:
        """Standby Guard line is omitted when no HD has it enabled."""
        ipmi = _make_fake_ipmi()
        hd = _make_fake_hd_controller(zones=[1], count=4, standby_enabled=False)
        hd.device_names.return_value = [f"/dev/sd{chr(ord('a') + i)}" for i in range(4)]
        hd._get_nth_temp.side_effect = lambda i: 34.1
        entries = [("HD", "hd", hd, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False, verbose=True)
        assert "Standby Guard" not in out

    def test_no_devices_section_without_verbose(self) -> None:
        """The standalone path omits per-controller blocks (and thus per-device temps) unless verbose=True."""
        ipmi = _make_fake_ipmi()
        cpu = _make_fake_cpu_controller(zones=[0], count=1, temp=42.3)
        entries = [("CPU", "cpu", cpu, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False)
        # Non-verbose mode emits no per-controller blocks: no Window/Devices lines, no block header.
        assert "[CPU]" not in out
        assert "Window:" not in out

    def test_devices_section_with_verbose(self) -> None:
        """In verbose mode the standalone path renders one block per controller with per-device temps."""
        ipmi = _make_fake_ipmi()
        # An HD controller with two disks; mock device_names() and _get_nth_temp() so we don't shell out.
        hd = _make_fake_hd_controller(zones=[1], count=2, standby_enabled=False,
                                      hd_names=["/dev/sda", "/dev/sdb"])
        hd.device_names.return_value = ["/dev/sda", "/dev/sdb"]
        hd._get_nth_temp.side_effect = lambda i: [33.0, 34.5][i]
        entries = [("HD", "hd", hd, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False, verbose=True)
        # Verbose mode emits a per-controller block: header, window, current, then a Device table.
        assert "[HD]" in out
        assert "Window:" in out
        assert "  Device" in out          # column header at 2-space indent
        assert "  ------" in out          # dashed separator under the headers
        # HD names render as basename only — /dev/ prefix is stripped.
        assert "  sda" in out
        assert "33.0 C" in out
        assert "  sdb" in out
        assert "34.5 C" in out
        assert "/dev/sda" not in out

    def test_devices_section_per_device_error_isolated(self) -> None:
        """A single failing _get_nth_temp() call renders 'ERROR' for that row but does not break the table."""
        ipmi = _make_fake_ipmi()
        hd = _make_fake_hd_controller(zones=[1], count=2, standby_enabled=False,
                                      hd_names=["/dev/sda", "/dev/sdb"])
        hd.device_names.return_value = ["/dev/sda", "/dev/sdb"]

        def _read(i: int) -> float:
            if i == 1:
                raise RuntimeError("smartctl failed")
            return 33.0
        hd._get_nth_temp.side_effect = _read
        entries = [("HD", "hd", hd, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False, verbose=True)
        assert "33.0 C" in out
        assert "ERROR" in out

    def test_devices_section_skips_const(self) -> None:
        """CONST controllers are excluded from the per-controller blocks even in verbose mode."""
        ipmi = _make_fake_ipmi()
        const_fc = _make_fake_const_controller(zones=[2], level=50)
        entries = [("CONST", "const", const_fc, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False, verbose=True)
        # CONST is in the Controllers table but never gets its own verbose block.
        assert "[CONST]" not in out
        assert "Window:" not in out

    def test_devices_section_device_names_error(self) -> None:
        """If device_names() itself raises, the controller is silently skipped (defensive guard)."""
        ipmi = _make_fake_ipmi()
        cpu = _make_fake_cpu_controller(zones=[0], count=1, temp=42.3)
        cpu.device_names.side_effect = RuntimeError("device_names failed")
        # Add a healthy HD so the Devices section still renders for the surviving controller.
        hd = _make_fake_hd_controller(zones=[1], count=1, hd_names=["/dev/sda"])
        hd.device_names.return_value = ["/dev/sda"]
        hd._get_nth_temp.side_effect = lambda i: 33.0
        entries = [("CPU", "cpu", cpu, None), ("HD", "hd", hd, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False, verbose=True)
        # HD name renders as basename only.
        assert "  sda" in out
        assert "/dev/sda" not in out
        # cpu0 must NOT appear because device_names() raised for the CPU controller.
        assert "cpu0" not in out

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
        """STANDARD fan mode (offline) renders the mode plus a 'not in FULL mode' warning."""
        ipmi = _make_fake_ipmi(fan_mode_value=0)
        cpu = _make_fake_cpu_controller()
        entries = [("CPU", "cpu", cpu, None)]
        out = client._format_report(ipmi, entries, "x.conf", use_color=False)
        assert "STANDARD" in out
        assert "not in FULL mode" in out
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

    def test_ipmi_not_found_emits_install_hint(self, mocker: MockerFixture,
                                               capsys: pytest.CaptureFixture) -> None:
        """A missing ipmitool (FileNotFoundError) returns EXIT_IPMI_ERROR with an install hint, not the sudo hint."""
        mocker.patch("smfc.client.Config", return_value=_make_offline_cfg())
        mocker.patch("smfc.client.Ipmi",
                     side_effect=FileNotFoundError("[Errno 2] No such file or directory: 'ipmitool'"))
        rc = client.main(["-c", "/dummy.conf"])
        assert rc == EXIT_IPMI_ERROR
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()
        assert "ipmi_command" in captured.err
        assert "sudo" not in captured.err.lower()

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
        assert "Fan controllers" in captured.out
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
    """Cover _safe_temp_str(), _safe_zone_level(), _band_color(), _parse_*_cell()."""

    def test_band_color_below_floor_is_dim(self) -> None:
        """A value below the floor of the steering window paints DIM (idle)."""
        assert client._band_color(28.0, 35.0, 48.0) == client.DIM

    def test_band_color_in_range_is_green(self) -> None:
        """A value in the lower 70 % of the steering window paints GREEN (working)."""
        # 35 + 0.4*(48-35) = 40.2 → 40 % through window → GREEN
        assert client._band_color(40.0, 35.0, 48.0) == client.GREEN

    def test_band_color_upper_30_is_yellow(self) -> None:
        """A value in the upper 30 % of the steering window paints YELLOW (warm)."""
        # 35 + 0.85*(48-35) = 46.05 → 85 % through window → YELLOW
        assert client._band_color(46.0, 35.0, 48.0) == client.YELLOW

    def test_band_color_above_ceiling_is_red(self) -> None:
        """A value at or above the ceiling paints RED (at/over the curve max)."""
        assert client._band_color(48.0, 35.0, 48.0) == client.RED
        assert client._band_color(60.0, 35.0, 48.0) == client.RED

    def test_band_color_degenerate_window_returns_empty(self) -> None:
        """A degenerate window (hi <= lo) returns '' so the caller renders default colour."""
        # CONST controllers have level_min == level_max — the band logic has nothing to do.
        assert client._band_color(50.0, 50.0, 50.0) == ""
        assert client._band_color(50.0, 60.0, 40.0) == ""  # inverted

    def test_parse_temp_cell(self) -> None:
        """Formatted temp cells parse back to their numeric value; sentinels yield None."""
        assert client._parse_temp_cell("42.3 C") == 42.3
        assert client._parse_temp_cell("ERROR") is None
        assert client._parse_temp_cell("-") is None
        assert client._parse_temp_cell("") is None

    def test_parse_level_cell(self) -> None:
        """Formatted level cells parse back to their numeric value; sentinels yield None."""
        assert client._parse_level_cell(" 55 %") == 55.0
        assert client._parse_level_cell("ERROR") is None
        assert client._parse_level_cell("-") is None

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

    def test_safe_nth_temp_str_none_controller(self) -> None:
        """A None controller renders as '-' (mirrors _safe_temp_str)."""
        assert client._safe_nth_temp_str(None, 0) == "-"

    def test_safe_nth_temp_str_raises(self) -> None:
        """A controller whose _get_nth_temp() raises renders as 'ERROR'."""
        controller = MagicMock()
        controller._get_nth_temp.side_effect = RuntimeError("smartctl failed")
        assert client._safe_nth_temp_str(controller, 0) == "ERROR"

    def test_display_device_name_strips_hd_path(self) -> None:
        """HD device paths render as the basename — /dev/disk/by-id/... is too noisy in the verbose list."""
        assert client._display_device_name(
            "/dev/disk/by-id/ata-WDC_WD120EFAX-68UNTN0_2AH1BHVY", "hd"
        ) == "ata-WDC_WD120EFAX-68UNTN0_2AH1BHVY"
        assert client._display_device_name("/dev/sda", "hd") == "sda"

    def test_display_device_name_strips_nvme_path(self) -> None:
        """NVMe device paths also get stripped to the basename."""
        assert client._display_device_name(
            "/dev/disk/by-id/nvme-CT4000P3PSSD8_2336E8740474", "nvme"
        ) == "nvme-CT4000P3PSSD8_2336E8740474"

    def test_display_device_name_preserves_cpu_and_gpu_labels(self) -> None:
        """CPU/GPU labels are synthesized ordinals (cpu0, gpu0) — they must not be touched."""
        assert client._display_device_name("cpu0", "cpu") == "cpu0"
        assert client._display_device_name("gpu0", "gpu") == "gpu0"
        # Empty / non-disk strings are returned as-is for HD/NVMe too.
        assert client._display_device_name("", "hd") == ""

    def test_format_uptime_under_one_day(self) -> None:
        """Sub-day durations omit the day field entirely (HH:MM:SS form)."""
        assert client._format_uptime(3661.0) == "01:01:01"

    def test_format_uptime_one_day_and_change(self) -> None:
        """Multi-day durations prefix the day count."""
        assert client._format_uptime(86400 + 7322) == "1d 02:02:02"


class TestFormatReportErrorPaths:
    """Cover the error branches in _format_*() and _format_report()."""

    def test_controllers_table_error_status(self) -> None:
        """When the level read fails, the controller row shows ERROR in the Level column."""
        ipmi = _make_fake_ipmi()
        ipmi.get_fan_level.side_effect = RuntimeError("ipmitool failed")
        cpu = _make_fake_cpu_controller()
        out = client._format_report(ipmi, [("CPU", "cpu", cpu, None)], "x.conf", use_color=False)
        # ERROR appears in the Level column (the Status column was removed).
        assert "ERROR" in out

    def test_standby_states_truncated(self) -> None:
        """When standby_array_states is shorter than the device list, only matching rows render."""
        ipmi = _make_fake_ipmi()
        # 4 device names but only 2 standby states → only the first two devices render.
        hd = _make_fake_hd_controller(zones=[1], count=4, standby_enabled=True,
                                      standby_hd_limit=1, standby_states=[False, False],
                                      hd_names=["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"])
        hd.device_names.return_value = ["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"]
        hd._get_nth_temp.side_effect = lambda i: 33.0 + i
        out = client._format_report(ipmi, [("HD", "hd", hd, None)], "x.conf", use_color=False, verbose=True)
        # Device names render as the basename — full /dev/ paths get stripped for HD/NVMe.
        assert "  sda" in out
        assert "  sdb" in out
        # Devices beyond the standby_states length still render in the block (they just have no state),
        # but in the new layout the device list is keyed by device_names(), so all four appear.
        assert "  sdc" in out
        assert "  sdd" in out
        assert "/dev/sda" not in out
        # The Standby Guard line carries the truncated state string.
        assert "Standby Guard" in out

    def test_standby_states_str_raises(self) -> None:
        """When get_standby_state_str() raises, the per-disk rows still render."""
        ipmi = _make_fake_ipmi()
        hd = _make_fake_hd_controller(zones=[1], count=2, standby_enabled=True,
                                      standby_hd_limit=1, standby_states=[False, True])
        hd.device_names.return_value = ["/dev/sda", "/dev/sdb"]
        hd._get_nth_temp.side_effect = lambda i: 33.0
        hd.get_standby_state_str.side_effect = RuntimeError("boom")
        out = client._format_report(ipmi, [("HD", "hd", hd, None)], "x.conf", use_color=False, verbose=True)
        assert "  sda" in out
        assert "/dev/sda" not in out
        # The Standby Guard summary line is omitted when get_standby_state_str() raises.
        assert "Standby Guard" not in out

    def test_fan_mode_read_error(self) -> None:
        """When ipmi.get_fan_mode() raises, the BMC block's Fan mode line shows ERROR."""
        ipmi = _make_fake_ipmi()
        ipmi.get_fan_mode.side_effect = RuntimeError("ipmitool failed")
        cpu = _make_fake_cpu_controller()
        out = client._format_report(ipmi, [("CPU", "cpu", cpu, None)], "x.conf", use_color=False)
        assert "Fan mode" in out
        assert "ERROR" in out

    def test_standby_states_attribute_missing(self) -> None:
        """When standby is enabled but standby_array_states is missing, the line is skipped."""
        ipmi = _make_fake_ipmi()
        # standby_enabled=True with standby_states=None deletes the attribute on the mock,
        # so getattr(..., None) returns None and the Standby Guard line is omitted.
        hd = _make_fake_hd_controller(zones=[1], count=4, standby_enabled=True,
                                      standby_hd_limit=1, standby_states=None)
        hd.device_names.return_value = [f"/dev/sd{chr(ord('a') + i)}" for i in range(4)]
        hd._get_nth_temp.side_effect = lambda i: 33.0
        out = client._format_report(ipmi, [("HD", "hd", hd, None)], "x.conf", use_color=False, verbose=True)
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
        "start_time": 1716816000.0,
        "fan_mode_enforced_count": 3,
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
        "fan_controllers": [
            {
                "section": "CPU", "type": "cpu", "enabled": True,
                "ipmi_zones": [0], "device_count": 1, "polling": 2.0,
                "last_temp_c": 42.3, "last_level_pct": 45, "deferred_apply": False,
                "devices": [{"name": "cpu0", "temp_c": 42.3}],
            },
            {
                "section": "HD", "type": "hd", "enabled": True,
                "ipmi_zones": [1], "device_count": 4, "polling": 10.0,
                "last_temp_c": 34.1, "last_level_pct": 55, "deferred_apply": False,
                "devices": [
                    {"name": "/dev/sda", "temp_c": 33.0},
                    {"name": "/dev/sdb", "temp_c": 34.5},
                    {"name": "/dev/sdc", "temp_c": 36.1},
                    {"name": "/dev/sdd", "temp_c": 39.0},
                ],
                "standby_guard": {
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
        assert "  config: /etc/smfc/smfc.conf\n" in out
        assert "  source: smfc service (live snapshot)\n" in out
        # Uptime is verbose-only — it must not appear in the non-verbose header.
        assert "uptime:" not in out
        assert "/etc/smfc/smfc.conf" in out
        assert "BMC" in out
        # Non-verbose BMC: Manufacturer and Platform are verbose-only; Product + Fan mode remain.
        assert "Super Micro Computer Inc." not in out
        assert "X11SCH-LN4F" in out
        assert "Platform" not in out

    def test_verbose_header_shows_uptime(self) -> None:
        """In verbose mode the online-path header additionally renders the service uptime line."""
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        # Uptime = generated_at - start_time = 86400 s = exactly one day.
        assert "  uptime: 1d 00:00:00\n" in out
        # And the rest of the header is still present.
        assert "  config: x.conf\n" in out
        assert "  source: smfc service (live snapshot)\n" in out
        # Verbose BMC: full layout. Manufacturer is back, Platform shows the factory class only
        # (no product repetition).
        assert "Super Micro Computer Inc." in out
        assert "Platform      : GenericPlatform" in out
        # The old "name (class)" form must not regress.
        assert "Platform      : X11SCH-LN4F" not in out
        assert "FULL" in out
        # The fan-mode line carries the enforced count and reading age (online only).
        assert "enforced 3x" in out
        assert "Fan controllers" in out
        assert "42.3 C" in out
        assert "34.1 C" in out
        assert "IPMI zones (live)" in out

    def test_standby_section_present_when_enabled(self) -> None:
        """The Standby Guard line is folded into the [HD] verbose block when enabled."""
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        assert "Standby Guard: enabled (limit=1)" in out
        # The standby line lives inside the [HD] block (before the next blank line).
        hd_block = out.split("[HD]", 1)[1].split("\n\n", 1)[0]
        assert "Standby Guard" in hd_block
        assert "  sda" in out
        assert "/dev/sda" not in out
        assert "ACTIVE" in out
        assert "STANDBY" in out
        assert "AASS" in out
        assert "2/4 standby" in out

    def test_standby_section_absent_when_disabled(self) -> None:
        """If no HD has standby enabled, the Standby Guard line is omitted from the HD block."""
        snap = _sample_snapshot_dict()
        snap["fan_controllers"][1]["standby_guard"] = {"enabled": False}
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        assert "Standby Guard" not in out

    def test_color_mode_emits_ansi(self) -> None:
        """ANSI sequences appear in the report when colors are enabled."""
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=True)
        assert "\x1b[" in out
        assert client.BOLD in out
        assert client.DIM in out  # Source line is dim
        # Section headers (BMC, Fan controllers, [HD], IPMI zones (live)) are bold-cyan.
        assert client.BLUE in out
        # And the section labels appear after the BLUE escape — pin a couple.
        assert f"{client.BLUE}BMC{client.RESET}" in out
        assert f"{client.BLUE}Fan controllers{client.RESET}" in out
        # No-color mode must produce no BLUE escapes at all.
        plain = client._format_report_from_snapshot(snap, "x.conf", use_color=False)
        assert client.BLUE not in plain

    def test_band_color_paints_temp_and_level_cells(self) -> None:
        """Each controller's Temp/Level cells are painted according to where they sit in the steering window.

        Snapshot has four controllers, one per band:
          CPU  at 40 C in [30..60] → 33% through → GREEN
          HD   at 31 C below floor [35..48]      → DIM (level still in lower 70% → GREEN)
          NVME at 60 C in [38..65] → 81% through → YELLOW
          GPU  at 90 C above ceiling [35..85]    → RED
        """
        snap = {
            "version": 1, "generated_at": 1716902400.0, "start_time": 1716816000.0,
            "fan_mode_enforced_count": 0, "smfc_version": "5.4.0",
            "bmc": {"manufacturer_name": "X", "manufacturer_id": 0, "product_name": "Y",
                    "product_id": 0, "firmware_rev": "0", "ipmi_version": "0",
                    "platform_name": "Y", "platform_class": "P"},
            "fan_mode": {"id": 1, "name": "FULL", "age_s": 0.0},
            "fan_controllers": [
                {"section": "CPU", "type": "cpu", "enabled": True, "ipmi_zones": [0],
                 "device_count": 1, "polling": 2.0, "deferred_apply": False,
                 "last_temp_c": 40.0, "last_level_pct": 50,
                 "temp_min_c": 30.0, "temp_max_c": 60.0,
                 "level_min_pct": 35, "level_max_pct": 100,
                 "devices": [{"name": "cpu0", "temp_c": 40.0}]},
                {"section": "HD", "type": "hd", "enabled": True, "ipmi_zones": [1],
                 "device_count": 1, "polling": 10.0, "deferred_apply": False,
                 "last_temp_c": 31.0, "last_level_pct": 35,
                 "temp_min_c": 35.0, "temp_max_c": 48.0,
                 "level_min_pct": 35, "level_max_pct": 100,
                 "devices": [{"name": "/dev/sda", "temp_c": 31.0}],
                 "standby_guard": {"enabled": False}},
                {"section": "NVME", "type": "nvme", "enabled": True, "ipmi_zones": [2],
                 "device_count": 1, "polling": 2.0, "deferred_apply": False,
                 "last_temp_c": 60.0, "last_level_pct": 85,
                 "temp_min_c": 38.0, "temp_max_c": 65.0,
                 "level_min_pct": 35, "level_max_pct": 100,
                 "devices": [{"name": "/dev/nvme0n1", "temp_c": 60.0}]},
                {"section": "GPU", "type": "gpu", "enabled": True, "ipmi_zones": [3],
                 "device_count": 1, "polling": 2.0, "deferred_apply": False,
                 "last_temp_c": 90.0, "last_level_pct": 100,
                 "temp_min_c": 35.0, "temp_max_c": 85.0,
                 "level_min_pct": 35, "level_max_pct": 100,
                 "devices": [{"name": "gpu0", "temp_c": 90.0}]},
            ],
            "zones": {"0": {"applied_level_pct": 50}, "1": {"applied_level_pct": 35},
                      "2": {"applied_level_pct": 85}, "3": {"applied_level_pct": 100}},
        }
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=True)
        # The Fan controllers table row for each band carries the expected colour around the temp.
        cpu_row = [l for l in out.splitlines() if l.lstrip().startswith("CPU ")][0]
        hd_row = [l for l in out.splitlines() if l.lstrip().startswith("HD ")][0]
        nvme_row = [l for l in out.splitlines() if l.lstrip().startswith("NVME ")][0]
        gpu_row = [l for l in out.splitlines() if l.lstrip().startswith("GPU ")][0]
        assert client.GREEN in cpu_row and "40.0 C" in cpu_row
        assert client.DIM in hd_row and "31.0 C" in hd_row
        assert client.YELLOW in nvme_row and "60.0 C" in nvme_row
        assert client.RED in gpu_row and "90.0 C" in gpu_row

    def test_band_color_standby_disks_render_dim(self) -> None:
        """Per-device temps for STANDBY disks render DIM regardless of where they sit in the window.

        Two HD disks: one at 28 C (below floor — already DIM), one at 46 C (would be YELLOW if
        ACTIVE). Both are in STANDBY, so both must paint DIM.
        """
        snap = _sample_snapshot_dict()
        # Override states so both disks are STANDBY.
        snap["fan_controllers"][1]["standby_guard"] = {
            "enabled": True, "limit": 1, "states": [True, True, False, False],
            "array_state": "SSAA", "standby_count": 2,
        }
        # Override one disk to be in YELLOW range (upper 30 %) when ACTIVE — to prove standby wins.
        snap["fan_controllers"][1]["devices"][1]["temp_c"] = 46.0
        snap["fan_controllers"][1]["temp_min_c"] = 35.0
        snap["fan_controllers"][1]["temp_max_c"] = 48.0
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=True, verbose=True)
        # Find the HD block's first two device rows (the standby ones).
        hd_block = out.split("[HD]", 1)[1].split("\n\n", 1)[0]
        sda_row = [l for l in hd_block.splitlines() if l.lstrip().startswith("sda ")][0]
        sdb_row = [l for l in hd_block.splitlines() if l.lstrip().startswith("sdb ")][0]
        # Both rows paint DIM (the standby override), not YELLOW or anything else.
        assert client.DIM in sda_row
        assert client.DIM in sdb_row
        assert client.YELLOW not in sdb_row  # 46 C would be YELLOW if ACTIVE — confirm override wins

    def test_band_color_const_level_uncoloured(self) -> None:
        """CONST controllers (level_min == level_max, no temp window) leave their Level cell uncoloured."""
        snap = _sample_snapshot_dict()
        snap["fan_controllers"].append({
            "section": "CONST", "type": "const", "enabled": True, "ipmi_zones": [9],
            "device_count": 0, "polling": 30.0, "deferred_apply": False,
            "last_temp_c": 0.0, "last_level_pct": 60, "target_level_pct": 60,
            "level_min_pct": 60, "level_max_pct": 60,
        })
        snap["zones"]["9"] = {"applied_level_pct": 60}
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=True)
        const_row = [l for l in out.splitlines() if l.lstrip().startswith("CONST ")][0]
        # CONST level cell carries no band escape — neither DIM/GREEN/YELLOW/RED appears in it
        # (other than the leading "  CONST" which is plain text).
        for color in (client.DIM, client.GREEN, client.YELLOW, client.RED):
            assert color not in const_row

    def test_const_controller_shows_target_level(self) -> None:
        """A ConstFc entry's row shows the configured target level (the Status column was removed)."""
        snap = _sample_snapshot_dict()
        snap["fan_controllers"].append({
            "section": "CONST", "type": "const", "enabled": True,
            "ipmi_zones": [2], "device_count": 0, "polling": 30.0,
            "last_temp_c": 0.0, "last_level_pct": 50, "deferred_apply": False,
            "target_level_pct": 50,
        })
        snap["zones"]["2"] = {"applied_level_pct": 50}
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False)
        assert "CONST" in out
        assert " 50 %" in out
        assert "Status" not in out

    def test_non_full_fan_mode_renders_red(self) -> None:
        """When the cached fan_mode is not FULL, the value is emphasized differently (color test)."""
        snap = _sample_snapshot_dict()
        snap["fan_mode"] = {"id": 0, "name": "STANDARD", "age_s": 0.5}
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=True)
        # The label is wrapped in RED (not GREEN) when mode != FULL.
        assert client.RED in out

    def test_standby_states_shorter_than_devices_truncates(self) -> None:
        """Defensive: when standby.states is shorter than the devices list, the block truncates to the shorter length."""
        snap = _sample_snapshot_dict()
        # 4 device names but only 2 states — the verbose block must show only the first 2 disks.
        snap["fan_controllers"][1]["standby_guard"] = {
            "enabled": True, "limit": 1, "states": [False, False],
            "array_state": "AA", "standby_count": 0,
        }
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        # Device names render as the basename — full /dev/ paths get stripped for HD/NVMe.
        assert "  sda" in out
        assert "  sdb" in out
        # Devices beyond the states length are not rendered.
        assert "  sdc" not in out
        assert "  sdd" not in out
        assert "/dev/sda" not in out

    def test_no_devices_section_without_verbose(self) -> None:
        """Without verbose=True the per-controller blocks are not rendered (default behaviour unchanged)."""
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False)
        # Non-verbose mode emits no per-controller blocks: no Window/[CPU]/[HD] lines.
        assert "[CPU]" not in out
        assert "[HD]" not in out
        assert "Window:" not in out
        # And no per-device temps leak through (33.0 only appears in the devices array).
        assert "33.0 C" not in out

    def test_devices_section_present_with_verbose(self) -> None:
        """With verbose=True one block per non-CONST controller renders its devices with cached temps."""
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        # Both non-CONST controllers got their own verbose block.
        assert "[CPU]" in out
        assert "[HD]" in out
        # CPU labels (cpu0) keep their bare name; HD names render as the basename only.
        assert "cpu0" in out
        assert "42.3 C" in out
        for basename, temp in [("sda", "33.0 C"), ("sdb", "34.5 C"),
                               ("sdc", "36.1 C"), ("sdd", "39.0 C")]:
            assert f"  {basename}" in out
            assert temp in out
        assert "/dev/sda" not in out

    def test_devices_section_skips_const_online(self) -> None:
        """CONST controllers stay in the Controllers table but never get their own verbose block."""
        snap = _sample_snapshot_dict()
        snap["fan_controllers"].append({
            "section": "CONST", "type": "const", "enabled": True,
            "ipmi_zones": [2], "device_count": 0, "polling": 30.0,
            "last_temp_c": 0.0, "last_level_pct": 50, "deferred_apply": False,
            "target_level_pct": 50,
        })
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        # CPU + HD render their own block; CONST does not.
        assert "[CPU]" in out
        assert "[HD]" in out
        assert "[CONST]" not in out

    def test_verbose_emits_one_block_per_controller(self) -> None:
        """Each non-CONST controller in the snapshot gets its own verbose block, in order."""
        snap = _sample_snapshot_dict()
        snap["fan_controllers"].append({
            "section": "NVME", "type": "nvme", "enabled": True,
            "ipmi_zones": [0], "device_count": 1, "polling": 2.0,
            "deferred_apply": False, "last_temp_c": 25.0, "last_level_pct": 35,
            "temp_min_c": 38.0, "temp_max_c": 65.0, "level_min_pct": 35, "level_max_pct": 100,
            "devices": [{"name": "/dev/nvme0n1", "temp_c": 25.0}],
        })
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        # Block headers appear in controller order.
        cpu_idx = out.find("[CPU]")
        hd_idx = out.find("[HD]")
        nvme_idx = out.find("[NVME]")
        assert 0 < cpu_idx < hd_idx < nvme_idx

    def test_verbose_block_shows_window_and_current(self) -> None:
        """Each verbose block exposes the steering window and the current Temp → Level pair."""
        snap = _sample_snapshot_dict()
        # Pin the CPU controller's window so the assertions are exact.
        snap["fan_controllers"][0].update({
            "temp_min_c": 30.0, "temp_max_c": 60.0, "level_min_pct": 35, "level_max_pct": 100,
            "last_temp_c": 35.0, "last_level_pct": 35, "polling": 2.0, "deferred_apply": True,
        })
        snap["zones"]["0"] = {"applied_level_pct": 35}
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        # Window and Temp/Level lines render inside the [CPU] block.
        cpu_block = out.split("[CPU]", 1)[1].split("\n\n", 1)[0]
        assert "Window: T=[30..60]C → L=[35..100]%" in cpu_block
        assert "Temp:   35.0 C" in cpu_block
        assert "shared=yes" in cpu_block
        # No control_function configured for the sample CPU — the Curve: line is suppressed.
        assert "Curve:" not in cpu_block

    def test_verbose_block_shows_curve_when_control_function_set(self) -> None:
        """When control_function is configured the block adds a Curve: line under Window: with
        the breakpoint pairs. The Window endpoints come from the curve's first/last pair, not
        from the legacy temp_min_c/temp_max_c keys (which the runtime ignores in this mode)."""
        snap = _sample_snapshot_dict()
        # CPU runs in curve mode. The snapshot exporter is supposed to already set
        # temp_min_c/temp_max_c/level_min_pct/level_max_pct from the curve's endpoints; mirror
        # that here so client-side rendering sees consistent data.
        snap["fan_controllers"][0].update({
            "control_function": [[35, 35], [55, 50], [70, 80], [85, 100]],
            "temp_min_c": 35.0, "temp_max_c": 85.0,
            "level_min_pct": 35, "level_max_pct": 100,
            "last_temp_c": 67.8, "last_level_pct": 76,
        })
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        cpu_block = out.split("[CPU]", 1)[1].split("\n\n", 1)[0]
        # Window reflects the curve's envelope.
        assert "Window: T=[35..85]C → L=[35..100]%" in cpu_block
        # Curve line lives directly after Window, in the same indentation and arrow style.
        assert "Curve:  35→35, 55→50, 70→80, 85→100" in cpu_block
        # Curve appears between Window and Temp.
        assert cpu_block.index("Window:") < cpu_block.index("Curve:") < cpu_block.index("Temp:")

    def test_verbose_block_no_curve_line_in_legacy_mode(self) -> None:
        """Without control_function (legacy linear mode) the Curve: line is suppressed."""
        snap = _sample_snapshot_dict()
        # HD entry has no control_function key in the sample dict — make it explicit.
        snap["fan_controllers"][1]["control_function"] = []
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        hd_block = out.split("[HD]", 1)[1].split("\n\n", 1)[0]
        assert "Window:" in hd_block
        assert "Curve:" not in hd_block

    def test_verbose_block_folds_standby_into_hd(self) -> None:
        """The Standby Guard line lives inside the [HD] block, not after IPMI zones."""
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        # Standby Guard occurs once, and that occurrence is inside the [HD] block (before the next
        # blank line that closes the block, and before "IPMI zones (live)" which closes the report).
        assert out.count("Standby Guard") == 1
        hd_block = out.split("[HD]", 1)[1].split("\n\n", 1)[0]
        assert "Standby Guard" in hd_block
        # And the IPMI zones section that follows does NOT contain it.
        zones_section = out.split("IPMI zones (live)", 1)[1]
        assert "Standby Guard" not in zones_section

    def test_verbose_devices_table_has_aligned_headers(self) -> None:
        """The Devices subsection emits column headers that line up with the data rows.

        HD block (standby enabled) has Device/Temp/State; CPU (no standby) has Device/Temp only.
        The 'Temp' header column must start at the same character offset as the temperature
        value on the data row beneath it, and the 'State' header (when present) must align with
        the STANDBY/ACTIVE cell. A dashed separator sits between the header and the first data
        row, so the comparison must skip that line.
        """
        snap = _sample_snapshot_dict()
        out = client._format_report_from_snapshot(snap, "x.conf", use_color=False, verbose=True)
        # HD block (three columns: Device / Temp / State).
        hd_block = out.split("[HD]", 1)[1].split("\n\n", 1)[0]
        hd_lines = hd_block.splitlines()
        hd_header_idx = next(i for i, l in enumerate(hd_lines) if l.lstrip().startswith("Device "))
        hd_header = hd_lines[hd_header_idx]
        hd_separator = hd_lines[hd_header_idx + 1]
        hd_first_row = hd_lines[hd_header_idx + 2]  # /dev/sda → "sda" with temp 33.0 C
        assert "Device" in hd_header and "Temp" in hd_header and "State" in hd_header
        assert hd_separator.lstrip().startswith("-")  # dashed separator under the headers
        assert hd_header.index("Temp") == hd_first_row.index("33.0 C")
        assert hd_header.index("State") == hd_first_row.index("ACTIVE")
        # CPU block (two columns: Device / Temp).
        cpu_block = out.split("[CPU]", 1)[1].split("\n\n", 1)[0]
        cpu_lines = cpu_block.splitlines()
        cpu_header_idx = next(i for i, l in enumerate(cpu_lines) if l.lstrip().startswith("Device "))
        cpu_header = cpu_lines[cpu_header_idx]
        cpu_separator = cpu_lines[cpu_header_idx + 1]
        cpu_row = cpu_lines[cpu_header_idx + 2]
        assert "Device" in cpu_header and "Temp" in cpu_header and "State" not in cpu_header
        assert cpu_separator.lstrip().startswith("-")
        assert cpu_header.index("Temp") == cpu_row.index("42.3 C")


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
        assert "  source: smfc service" in captured.out
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
        assert "  source: ipmitool (smfc service is not reachable)" in out
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
        assert "  source: ipmitool (smfc service is not reachable)" in out
        assert try_fetch.call_count == 0, "_try_fetch_snapshot must not be called when --standalone is passed"


# End.
