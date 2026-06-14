#!/usr/bin/env python3
#
#   test_exporter.py (C) 2021-2026, Peter Sulyok
#   Unit tests for smfc.exporter (HTTP server + Prometheus rendering).
#
# pylint: disable=protected-access,redefined-outer-name,missing-function-docstring
import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, List
import pytest
from smfc.exporter import (
    Exporter,
    HEALTHZ_PATH,
    METRICS_PATH,
    SNAPSHOT_PATH,
    _escape_label_value,
    render_prometheus,
)


def _sample_snapshot() -> Dict[str, Any]:
    """A minimal, well-formed snapshot dict used in most tests."""
    return {
        "version": 1,
        "generated_at": 1716902400.0,
        "smfc_version": "5.4.0",
        "start_time": 1716902400.0,
        "fan_mode_enforced_count": 2,
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
        "fan_mode": {"id": 1, "name": "FULL", "age_s": 1.5},
        "controllers": [
            {
                "section": "CPU", "type": "cpu", "enabled": True,
                "ipmi_zones": [0], "device_count": 1, "polling": 2.0,
                "last_temp_c": 42.3, "last_level_pct": 45, "deferred_apply": False,
                "temp_min_c": 30.0, "temp_max_c": 70.0, "level_min_pct": 25, "level_max_pct": 100,
                "devices": [{"name": "cpu0", "temp_c": 42.3}],
            },
            {
                "section": "HD", "type": "hd", "enabled": True,
                "ipmi_zones": [1], "device_count": 4, "polling": 10.0,
                "last_temp_c": 34.1, "last_level_pct": 55, "deferred_apply": False,
                "temp_min_c": 32.0, "temp_max_c": 50.0, "level_min_pct": 35, "level_max_pct": 100,
                "device_names": ["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"],
                "devices": [
                    {"name": "/dev/sda", "temp_c": 33.0},
                    {"name": "/dev/sdb", "temp_c": 34.5},
                    {"name": "/dev/sdc", "temp_c": 36.1},
                    {"name": "/dev/sdd", "temp_c": 39.0},
                ],
                "standby": {
                    "enabled": True, "limit": 1,
                    "states": [False, False, True, True],
                    "array_state": "AASS", "standby_count": 2,
                },
            },
            {
                "section": "CONST", "type": "const", "enabled": True,
                "ipmi_zones": [2], "device_count": 0, "polling": 30.0,
                "last_temp_c": 0.0, "last_level_pct": 50, "deferred_apply": False,
                "target_level_pct": 50, "level_min_pct": 50, "level_max_pct": 50,
            },
        ],
        "zones": {"0": {"applied_level_pct": 45}, "1": {"applied_level_pct": 55},
                  "2": {"applied_level_pct": 50}},
    }


@pytest.fixture
def running_exporter() -> Iterator[Exporter]:
    """Start an exporter on an ephemeral port and tear it down at the end of the test."""
    snap = _sample_snapshot()
    exporter = Exporter(log=None, bind_address="127.0.0.1", port=0, snapshot_fn=lambda: snap)
    exporter.start()
    try:
        yield exporter
    finally:
        exporter.stop()


def _get(url: str, timeout: float = 2.0) -> tuple:
    """Issue a GET request, returning (status, content_type, body_bytes)."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


class TestPrometheusRenderer:
    """Unit tests for render_prometheus() (no HTTP server involved)."""

    def test_well_formed_output(self) -> None:
        """Output ends with a newline and carries HELP+TYPE for every gauge plus the enforcement counter."""
        out = render_prometheus(_sample_snapshot())
        assert out.endswith("\n")
        for metric in ("smfc_up", "smfc_start_time_seconds", "smfc_bmc_info",
                       "smfc_controller_zone", "smfc_temperature_celsius",
                       "smfc_device_temperature_celsius",
                       "smfc_controller_level_percent", "smfc_fan_level_percent",
                       "smfc_controller_temperature_min_celsius", "smfc_controller_temperature_max_celsius",
                       "smfc_controller_level_min_percent", "smfc_controller_level_max_percent",
                       "smfc_disk_standby"):
            assert f"# HELP {metric} " in out, f"missing HELP for {metric}"
            assert f"# TYPE {metric} gauge" in out, f"missing TYPE for {metric}"
        # The enforcement metric is a counter, not a gauge.
        assert "# HELP smfc_fan_mode_enforced_total " in out
        assert "# TYPE smfc_fan_mode_enforced_total counter" in out
        # Removed metrics must not reappear.
        assert "smfc_fan_mode " not in out
        assert "smfc_fan_mode_age_seconds" not in out

    def test_up_and_bmc_info(self) -> None:
        """smfc_up carries only the version; BMC identity moves to smfc_bmc_info."""
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_up{version="5.4.0"} 1' in out
        assert "bmc_product" not in out
        expected = ('smfc_bmc_info{product_name="X11SCH-LN4F",firmware_version="1.74",'
                    'manufacturer_name="Super Micro Computer Inc."} 1')
        assert expected in out

    def test_start_time_and_enforcement_counter(self) -> None:
        """The start timestamp and enforcement counter are rendered from the snapshot."""
        out = render_prometheus(_sample_snapshot())
        assert "smfc_start_time_seconds 1716902400.0" in out
        assert "smfc_fan_mode_enforced_total 2" in out

    def test_controller_zone_mapping(self) -> None:
        """smfc_controller_zone emits value 1 per enabled controller, one series per targeted zone."""
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_controller_zone{section="CPU",type="cpu",zone="0"} 1' in out
        assert 'smfc_controller_zone{section="HD",type="hd",zone="1"} 1' in out
        assert 'smfc_controller_zone{section="CONST",type="const",zone="2"} 1' in out

    def test_controller_level_includes_const_per_zone(self) -> None:
        """smfc_controller_level_percent carries a zone label and includes CONST."""
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_controller_level_percent{section="CPU",type="cpu",zone="0"} 45' in out
        assert 'smfc_controller_level_percent{section="CONST",type="const",zone="2"} 50' in out

    def test_multi_zone_controller_expands_per_zone(self) -> None:
        """A controller targeting two zones yields one series per zone for temp/level/mapping."""
        snap = _sample_snapshot()
        snap["controllers"][0]["ipmi_zones"] = [0, 1]
        out = render_prometheus(snap)
        assert 'smfc_temperature_celsius{section="CPU",type="cpu",zone="0"} 42.3' in out
        assert 'smfc_temperature_celsius{section="CPU",type="cpu",zone="1"} 42.3' in out
        assert 'smfc_controller_zone{section="CPU",type="cpu",zone="1"} 1' in out

    def test_controller_zone_skips_disabled_controllers(self) -> None:
        """smfc_controller_zone omits controllers with enabled=False."""
        snap = _sample_snapshot()
        snap["controllers"][0]["enabled"] = False
        out = render_prometheus(snap)
        # The disabled CPU controller's zone mapping must NOT appear.
        assert 'smfc_controller_zone{section="CPU",type="cpu",zone="0"} 1' not in out
        # The other controllers (HD, CONST) still emit their mappings.
        assert 'smfc_controller_zone{section="HD",type="hd",zone="1"} 1' in out

    def test_per_zone_levels(self) -> None:
        """smfc_fan_level_percent emits one line per zone in numerical order."""
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_fan_level_percent{zone="0"} 45' in out
        assert 'smfc_fan_level_percent{zone="1"} 55' in out
        assert 'smfc_fan_level_percent{zone="2"} 50' in out

    def test_temperature_skips_const(self) -> None:
        """smfc_temperature_celsius is emitted (with a zone label) for cpu and hd but not const."""
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_temperature_celsius{section="CPU",type="cpu",zone="0"} 42.3' in out
        assert 'smfc_temperature_celsius{section="HD",type="hd",zone="1"} 34.1' in out
        temp_block = out.split("# TYPE smfc_temperature_celsius", 1)[1].split("# HELP")[0]
        assert 'section="CONST"' not in temp_block

    def test_per_device_temperature_emitted(self) -> None:
        """smfc_device_temperature_celsius is emitted once per device with section/type/device labels."""
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_device_temperature_celsius{section="CPU",type="cpu",device="cpu0"} 42.3' in out
        assert 'smfc_device_temperature_celsius{section="HD",type="hd",device="/dev/sda"} 33.0' in out
        assert 'smfc_device_temperature_celsius{section="HD",type="hd",device="/dev/sdd"} 39.0' in out

    def test_per_device_temperature_skips_const(self) -> None:
        """smfc_device_temperature_celsius is omitted for CONST controllers (no temperature concept)."""
        out = render_prometheus(_sample_snapshot())
        block = out.split("# TYPE smfc_device_temperature_celsius", 1)[1].split("# HELP")[0]
        assert 'section="CONST"' not in block

    def test_steering_window_metrics(self) -> None:
        """The static [T_min,T_max]->[L_min,L_max] window is emitted, one series per targeted zone."""
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_controller_temperature_min_celsius{section="CPU",type="cpu",zone="0"} 30.0' in out
        assert 'smfc_controller_temperature_max_celsius{section="HD",type="hd",zone="1"} 50.0' in out
        assert 'smfc_controller_level_min_percent{section="HD",type="hd",zone="1"} 35' in out
        assert 'smfc_controller_level_max_percent{section="CPU",type="cpu",zone="0"} 100' in out

    def test_steering_window_temperature_skips_const(self) -> None:
        """The temperature window is omitted for CONST, but the level window includes it (L_min=L_max)."""
        out = render_prometheus(_sample_snapshot())
        tmin_block = out.split("# TYPE smfc_controller_temperature_min_celsius", 1)[1].split("# HELP")[0]
        tmax_block = out.split("# TYPE smfc_controller_temperature_max_celsius", 1)[1].split("# HELP")[0]
        assert 'section="CONST"' not in tmin_block
        assert 'section="CONST"' not in tmax_block
        assert 'smfc_controller_level_min_percent{section="CONST",type="const",zone="2"} 50' in out
        assert 'smfc_controller_level_max_percent{section="CONST",type="const",zone="2"} 50' in out

    def test_disk_standby_per_device(self) -> None:
        """smfc_disk_standby renders one row per (section, device) with 1/0 reflecting the state."""
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_disk_standby{section="HD",device="/dev/sda"} 0' in out
        assert 'smfc_disk_standby{section="HD",device="/dev/sdb"} 0' in out
        assert 'smfc_disk_standby{section="HD",device="/dev/sdc"} 1' in out
        assert 'smfc_disk_standby{section="HD",device="/dev/sdd"} 1' in out

    def test_disk_standby_omitted_when_disabled(self) -> None:
        """If no HD has standby enabled, smfc_disk_standby is omitted entirely."""
        snap = _sample_snapshot()
        snap["controllers"][1]["standby"] = {"enabled": False}
        out = render_prometheus(snap)
        assert "smfc_disk_standby" not in out

    def test_label_lines_match_prometheus_grammar(self) -> None:
        """Every metric line satisfies a basic Prometheus exposition regex."""
        out = render_prometheus(_sample_snapshot())
        # Match: name{...}? value
        # Names start with [a-zA-Z_:] and continue with [a-zA-Z0-9_:].
        line_re = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*(\{[^}]*\})? -?\d+(\.\d+)?$")
        for line in out.splitlines():
            if not line or line.startswith("#"):
                continue
            assert line_re.match(line), f"non-conforming metric line: {line!r}"

    def test_label_value_escaping(self) -> None:
        """Backslashes, double quotes, and newlines in label values are escaped per the spec."""
        assert _escape_label_value('a "b" c') == 'a \\"b\\" c'
        assert _escape_label_value("a\\b") == "a\\\\b"
        assert _escape_label_value("a\nb") == "a\\nb"


class TestExporterHTTP:
    """Integration tests: real HTTP server bound to an ephemeral port on 127.0.0.1."""

    def test_snapshot_endpoint(self, running_exporter: Exporter) -> None:
        host, port = running_exporter.bound_address()
        status, ctype, body = _get(f"http://{host}:{port}{SNAPSHOT_PATH}")
        assert status == 200
        assert "application/json" in ctype
        snap = json.loads(body.decode("utf-8"))
        assert snap["version"] == 1
        assert snap["bmc"]["product_name"] == "X11SCH-LN4F"

    def test_metrics_endpoint(self, running_exporter: Exporter) -> None:
        host, port = running_exporter.bound_address()
        status, ctype, body = _get(f"http://{host}:{port}{METRICS_PATH}")
        assert status == 200
        assert "text/plain" in ctype
        text = body.decode("utf-8")
        assert "# HELP smfc_up " in text
        assert 'smfc_fan_level_percent{zone="0"} 45' in text

    def test_healthz_endpoint(self, running_exporter: Exporter) -> None:
        host, port = running_exporter.bound_address()
        status, _ctype, body = _get(f"http://{host}:{port}{HEALTHZ_PATH}")
        assert status == 200
        assert body == b"ok\n"

    def test_unknown_path_returns_404(self, running_exporter: Exporter) -> None:
        host, port = running_exporter.bound_address()
        with pytest.raises(urllib.error.HTTPError) as cm:
            _get(f"http://{host}:{port}/unknown")
        assert cm.value.code == 404
        cm.value.close()  # release the underlying response to silence ResourceWarning

    def test_snapshot_callback_error_returns_500(self) -> None:
        """If the snapshot callback raises, the server returns 500 and stays alive for the next request."""
        calls = {"n": 0}

        def flaky() -> Dict[str, Any]:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("snapshot failure")
            return _sample_snapshot()

        exporter = Exporter(log=None, bind_address="127.0.0.1", port=0, snapshot_fn=flaky)
        exporter.start()
        try:
            host, port = exporter.bound_address()
            with pytest.raises(urllib.error.HTTPError) as cm:
                _get(f"http://{host}:{port}{SNAPSHOT_PATH}")
            assert cm.value.code == 500
            cm.value.close()
            # Server is still alive: the next call succeeds.
            status, _ctype, _body = _get(f"http://{host}:{port}{SNAPSHOT_PATH}")
            assert status == 200
        finally:
            exporter.stop()

    def test_stop_is_idempotent(self) -> None:
        """Calling stop() twice is safe (and stop() before start() is a no-op)."""
        exporter = Exporter(log=None, bind_address="127.0.0.1", port=0, snapshot_fn=_sample_snapshot)
        exporter.stop()  # before start: no-op
        exporter.start()
        exporter.stop()
        exporter.stop()  # after stop: no-op

    def test_bound_address_before_start(self) -> None:
        """bound_address() before start() returns the configured (host, port) without binding."""
        exporter = Exporter(log=None, bind_address="127.0.0.1", port=12345, snapshot_fn=_sample_snapshot)
        assert exporter.bound_address() == ("127.0.0.1", 12345)

    def test_log_at_info_on_start(self) -> None:
        """When a Log instance is wired in at LOG_INFO, the exporter emits a 'listening on ...' line."""
        from smfc.log import Log  # pylint: disable=import-outside-toplevel
        log = Log(Log.LOG_INFO, Log.LOG_STDOUT)
        seen: List[tuple] = []
        log.msg = lambda level, msg: seen.append((level, msg))
        exporter = Exporter(log=log, bind_address="127.0.0.1", port=0, snapshot_fn=_sample_snapshot)
        exporter.start()
        try:
            assert any("Exporter listening on http://" in m for _lvl, m in seen)
        finally:
            exporter.stop()

    def test_handler_exception_is_logged_when_log_present(self) -> None:
        """When the snapshot callback raises and a Log is wired in, an ERROR line is emitted to the log."""
        from smfc.log import Log  # pylint: disable=import-outside-toplevel
        log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        recorded: List[tuple] = []
        log.msg = lambda level, msg: recorded.append((level, msg))
        exporter = Exporter(log=log, bind_address="127.0.0.1", port=0,
                            snapshot_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        exporter.start()
        try:
            host, port = exporter.bound_address()
            with pytest.raises(urllib.error.HTTPError) as cm:
                _get(f"http://{host}:{port}{SNAPSHOT_PATH}")
            assert cm.value.code == 500
            cm.value.close()
        finally:
            exporter.stop()
        assert any("handler error" in m for _lvl, m in recorded), \
            "expected an ERROR log line about the handler exception"

    def test_default_log_message_routes_to_log_at_debug(self) -> None:
        """The HTTP server's per-request access log lines route through Log.msg at DEBUG when set."""
        from smfc.log import Log  # pylint: disable=import-outside-toplevel
        log = Log(Log.LOG_DEBUG, Log.LOG_STDOUT)
        recorded: List[tuple] = []
        log.msg = lambda level, msg: recorded.append((level, msg))
        exporter = Exporter(log=log, bind_address="127.0.0.1", port=0, snapshot_fn=_sample_snapshot)
        exporter.start()
        try:
            host, port = exporter.bound_address()
            _get(f"http://{host}:{port}{SNAPSHOT_PATH}")
        finally:
            exporter.stop()
        # The successful GET produced an access-log line tagged "exporter:".
        assert any("exporter:" in msg for _lvl, msg in recorded), \
            "expected the per-request access log line to be routed through Log.msg"


# End.
