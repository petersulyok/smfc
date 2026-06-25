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
        "smfc_version": "6.0.0",
        "start_time": 1716902400.0,
        "fan_mode_enforced_count": 2,
        "bmc": {
            "manufacturer_name": "Super Micro Computer Inc.",
            "manufacturer_id": 10876,
            "product_name": "X11SCH-LN4F",
            "product_id": 6929,
            "firmware_rev": "1.74",
            "ipmi_version": "2.0",
            "platform": "auto -> GenericPlatform",
        },
        "fan_mode": {"id": 1, "name": "FULL", "age_s": 1.5, "enforce_fan_mode": True},
        "fan_controllers": [
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
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: output ends with a trailing newline
        - ASSERT: every expected gauge metric has a "# HELP" line in the output
        - ASSERT: every expected gauge metric has a "# TYPE ... gauge" line in the output
        - ASSERT: the enforcement metric has a "# HELP smfc_fan_mode_enforced_total" line
        - ASSERT: the enforcement metric has a "# TYPE smfc_fan_mode_enforced_total counter" line
        - ASSERT: removed metric "smfc_fan_mode " does not reappear in the output
        - ASSERT: removed metric "smfc_fan_mode_age_seconds" does not reappear in the output
        """
        out = render_prometheus(_sample_snapshot())
        assert out.endswith("\n")
        for metric in ("smfc_up", "smfc_start_time_seconds", "smfc_bmc_info",
                       "smfc_controller_zone", "smfc_controller_temperature_celsius",
                       "smfc_device_temperature_celsius",
                       "smfc_controller_level_percent", "smfc_zone_level_percent",
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
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_up line carries only the version label and value 1
        - ASSERT: legacy "bmc_product" label is not present in the output
        - ASSERT: smfc_bmc_info line carries product_name, firmware_version, and manufacturer_name labels
        """
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_up{version="6.0.0"} 1' in out
        assert "bmc_product" not in out
        expected = ('smfc_bmc_info{product_name="X11SCH-LN4F",firmware_version="1.74",'
                    'manufacturer_name="Super Micro Computer Inc."} 1')
        assert expected in out

    def test_start_time_and_enforcement_counter(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_start_time_seconds line carries the start_time value from the snapshot
        - ASSERT: smfc_fan_mode_enforced_total line carries the fan_mode_enforced_count from the snapshot
        """
        out = render_prometheus(_sample_snapshot())
        assert "smfc_start_time_seconds 1716902400.0" in out
        assert "smfc_fan_mode_enforced_total 2" in out

    def test_controller_zone_mapping(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_controller_zone emits value 1 with CPU/cpu/zone=0 labels
        - ASSERT: smfc_controller_zone emits value 1 with HD/hd/zone=1 labels
        - ASSERT: smfc_controller_zone emits value 1 with CONST/const/zone=2 labels
        """
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_controller_zone{section="CPU",type="cpu",zone="0"} 1' in out
        assert 'smfc_controller_zone{section="HD",type="hd",zone="1"} 1' in out
        assert 'smfc_controller_zone{section="CONST",type="const",zone="2"} 1' in out

    def test_controller_level_includes_const_per_zone(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_controller_level_percent carries CPU/cpu/zone=0 labels with value 45
        - ASSERT: smfc_controller_level_percent carries CONST/const/zone=2 labels with value 50
        """
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_controller_level_percent{section="CPU",type="cpu",zone="0"} 45' in out
        assert 'smfc_controller_level_percent{section="CONST",type="const",zone="2"} 50' in out

    def test_multi_zone_controller_expands_per_zone(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - mutate the CPU controller's ipmi_zones to target two zones [0, 1]
        - call render_prometheus() with the mutated snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_controller_temperature_celsius emits a series for CPU/zone=0
        - ASSERT: smfc_controller_temperature_celsius emits a second series for CPU/zone=1
        - ASSERT: smfc_controller_zone emits a series for CPU/zone=1
        """
        snap = _sample_snapshot()
        snap["fan_controllers"][0]["ipmi_zones"] = [0, 1]
        out = render_prometheus(snap)
        assert 'smfc_controller_temperature_celsius{section="CPU",type="cpu",zone="0"} 42.3' in out
        assert 'smfc_controller_temperature_celsius{section="CPU",type="cpu",zone="1"} 42.3' in out
        assert 'smfc_controller_zone{section="CPU",type="cpu",zone="1"} 1' in out

    def test_controller_zone_skips_disabled_controllers(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - mutate the CPU controller's enabled flag to False
        - call render_prometheus() with the mutated snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: the CPU controller's smfc_controller_zone line does NOT appear in the output
        - ASSERT: smfc_controller_zone for HD/hd/zone=1 still appears in the output
        """
        snap = _sample_snapshot()
        snap["fan_controllers"][0]["enabled"] = False
        out = render_prometheus(snap)
        # The disabled CPU controller's zone mapping must NOT appear.
        assert 'smfc_controller_zone{section="CPU",type="cpu",zone="0"} 1' not in out
        # The other controllers (HD, CONST) still emit their mappings.
        assert 'smfc_controller_zone{section="HD",type="hd",zone="1"} 1' in out

    def test_per_zone_levels(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_zone_level_percent emits zone=0 with value 45
        - ASSERT: smfc_zone_level_percent emits zone=1 with value 55
        - ASSERT: smfc_zone_level_percent emits zone=2 with value 50
        """
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_zone_level_percent{zone="0"} 45' in out
        assert 'smfc_zone_level_percent{zone="1"} 55' in out
        assert 'smfc_zone_level_percent{zone="2"} 50' in out

    def test_temperature_skips_const(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_controller_temperature_celsius is emitted for CPU/cpu/zone=0 with value 42.3
        - ASSERT: smfc_controller_temperature_celsius is emitted for HD/hd/zone=1 with value 34.1
        - ASSERT: smfc_controller_temperature_celsius is NOT emitted for any CONST section
        """
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_controller_temperature_celsius{section="CPU",type="cpu",zone="0"} 42.3' in out
        assert 'smfc_controller_temperature_celsius{section="HD",type="hd",zone="1"} 34.1' in out
        assert 'smfc_controller_temperature_celsius{section="CONST"' not in out

    def test_per_device_temperature_emitted(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_device_temperature_celsius is emitted for CPU device "cpu0" with value 42.3
        - ASSERT: smfc_device_temperature_celsius is emitted for HD device "/dev/sda" with value 33.0
        - ASSERT: smfc_device_temperature_celsius is emitted for HD device "/dev/sdd" with value 39.0
        """
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_device_temperature_celsius{section="CPU",type="cpu",device="cpu0"} 42.3' in out
        assert 'smfc_device_temperature_celsius{section="HD",type="hd",device="/dev/sda"} 33.0' in out
        assert 'smfc_device_temperature_celsius{section="HD",type="hd",device="/dev/sdd"} 39.0' in out

    def test_per_device_temperature_skips_const(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - extract the smfc_device_temperature_celsius block from the rendered output
        - ASSERT: the per-device temperature block does NOT contain section="CONST"
        """
        out = render_prometheus(_sample_snapshot())
        block = out.split("# TYPE smfc_device_temperature_celsius", 1)[1].split("# HELP")[0]
        assert 'section="CONST"' not in block

    def test_steering_window_metrics(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_controller_temperature_min_celsius is emitted for CPU/cpu/zone=0 with value 30.0
        - ASSERT: smfc_controller_temperature_max_celsius is emitted for HD/hd/zone=1 with value 50.0
        - ASSERT: smfc_controller_level_min_percent is emitted for HD/hd/zone=1 with value 35
        - ASSERT: smfc_controller_level_max_percent is emitted for CPU/cpu/zone=0 with value 100
        """
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_controller_temperature_min_celsius{section="CPU",type="cpu",zone="0"} 30.0' in out
        assert 'smfc_controller_temperature_max_celsius{section="HD",type="hd",zone="1"} 50.0' in out
        assert 'smfc_controller_level_min_percent{section="HD",type="hd",zone="1"} 35' in out
        assert 'smfc_controller_level_max_percent{section="CPU",type="cpu",zone="0"} 100' in out

    def test_steering_window_temperature_skips_const(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_controller_temperature_min_celsius is NOT emitted for CONST section
        - ASSERT: smfc_controller_temperature_max_celsius is NOT emitted for CONST section
        - ASSERT: smfc_controller_level_min_percent is emitted for CONST/const/zone=2 with value 50
        - ASSERT: smfc_controller_level_max_percent is emitted for CONST/const/zone=2 with value 50
        """
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_controller_temperature_min_celsius{section="CONST"' not in out
        assert 'smfc_controller_temperature_max_celsius{section="CONST"' not in out
        assert 'smfc_controller_level_min_percent{section="CONST",type="const",zone="2"} 50' in out
        assert 'smfc_controller_level_max_percent{section="CONST",type="const",zone="2"} 50' in out

    def test_disk_standby_per_device(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: smfc_disk_standby for HD device "/dev/sda" is 0 (active)
        - ASSERT: smfc_disk_standby for HD device "/dev/sdb" is 0 (active)
        - ASSERT: smfc_disk_standby for HD device "/dev/sdc" is 1 (standby)
        - ASSERT: smfc_disk_standby for HD device "/dev/sdd" is 1 (standby)
        """
        out = render_prometheus(_sample_snapshot())
        assert 'smfc_disk_standby{section="HD",device="/dev/sda"} 0' in out
        assert 'smfc_disk_standby{section="HD",device="/dev/sdb"} 0' in out
        assert 'smfc_disk_standby{section="HD",device="/dev/sdc"} 1' in out
        assert 'smfc_disk_standby{section="HD",device="/dev/sdd"} 1' in out

    def test_disk_standby_omitted_when_disabled(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - mutate the HD controller's standby_guard.enabled flag to False
        - call render_prometheus() with the mutated snapshot
        - inspect the rendered Prometheus text output
        - ASSERT: the smfc_disk_standby metric is entirely absent from the output
        """
        snap = _sample_snapshot()
        snap["fan_controllers"][1]["standby_guard"] = {"enabled": False}
        out = render_prometheus(snap)
        assert "smfc_disk_standby" not in out

    def test_label_lines_match_prometheus_grammar(self) -> None:
        """Positive unit test for render_prometheus() function. It contains the following steps:
        - build a sample snapshot dict via the _sample_snapshot() fixture helper
        - call render_prometheus() with the snapshot
        - compile a regex matching the Prometheus exposition grammar (name{labels}? value)
        - iterate over every non-blank, non-comment line in the output
        - ASSERT: each metric line matches the Prometheus exposition regex
        """
        out = render_prometheus(_sample_snapshot())
        # Match: name{...}? value
        # Names start with [a-zA-Z_:] and continue with [a-zA-Z0-9_:].
        line_re = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*(\{[^}]*\})? -?\d+(\.\d+)?$")
        for line in out.splitlines():
            if not line or line.startswith("#"):
                continue
            assert line_re.match(line), f"non-conforming metric line: {line!r}"

    def test_label_value_escaping(self) -> None:
        """Positive unit test for _escape_label_value() function. It contains the following steps:
        - call _escape_label_value() with strings containing double quotes, backslashes, and newlines
        - ASSERT: double quotes are escaped to backslash-quote
        - ASSERT: backslashes are doubled
        - ASSERT: newlines are escaped to backslash-n
        """
        assert _escape_label_value('a "b" c') == 'a \\"b\\" c'
        assert _escape_label_value("a\\b") == "a\\\\b"
        assert _escape_label_value("a\nb") == "a\\nb"


class TestExporterHTTP:
    """Integration tests: real HTTP server bound to an ephemeral port on 127.0.0.1."""

    def test_snapshot_endpoint(self, running_exporter: Exporter) -> None:
        """Positive unit test for the Exporter HTTP handler for SNAPSHOT_PATH. It contains the following steps:
        - use the running_exporter fixture (wires a snapshot_fn callable returning _sample_snapshot())
        - issue a GET request to http://host:port/snapshot via urllib.request.urlopen
        - decode the JSON response body
        - ASSERT: response status is 200
        - ASSERT: Content-Type header contains "application/json"
        - ASSERT: decoded snapshot version equals 1
        - ASSERT: decoded snapshot bmc.product_name equals "X11SCH-LN4F"
        """
        host, port = running_exporter.bound_address()
        status, ctype, body = _get(f"http://{host}:{port}{SNAPSHOT_PATH}")
        assert status == 200
        assert "application/json" in ctype
        snap = json.loads(body.decode("utf-8"))
        assert snap["version"] == 1
        assert snap["bmc"]["product_name"] == "X11SCH-LN4F"

    def test_metrics_endpoint(self, running_exporter: Exporter) -> None:
        """Positive unit test for the Exporter HTTP handler for METRICS_PATH. It contains the following steps:
        - use the running_exporter fixture (wires a snapshot_fn callable returning _sample_snapshot())
        - issue a GET request to http://host:port/metrics via urllib.request.urlopen
        - decode the response body as UTF-8 Prometheus text
        - ASSERT: response status is 200
        - ASSERT: Content-Type header contains "text/plain"
        - ASSERT: rendered text contains the "# HELP smfc_up " line
        - ASSERT: rendered text contains the smfc_zone_level_percent line for zone=0 with value 45
        """
        host, port = running_exporter.bound_address()
        status, ctype, body = _get(f"http://{host}:{port}{METRICS_PATH}")
        assert status == 200
        assert "text/plain" in ctype
        text = body.decode("utf-8")
        assert "# HELP smfc_up " in text
        assert 'smfc_zone_level_percent{zone="0"} 45' in text

    def test_healthz_endpoint(self, running_exporter: Exporter) -> None:
        """Positive unit test for the Exporter HTTP handler for HEALTHZ_PATH. It contains the following steps:
        - use the running_exporter fixture (wires a snapshot_fn callable returning _sample_snapshot())
        - issue a GET request to http://host:port/healthz via urllib.request.urlopen
        - ASSERT: response status is 200
        - ASSERT: response body equals b"ok\\n"
        """
        host, port = running_exporter.bound_address()
        status, _ctype, body = _get(f"http://{host}:{port}{HEALTHZ_PATH}")
        assert status == 200
        assert body == b"ok\n"

    def test_unknown_path_returns_404(self, running_exporter: Exporter) -> None:
        """Negative unit test for the Exporter HTTP handler on unknown paths. It contains the following steps:
        - use the running_exporter fixture (wires a snapshot_fn callable returning _sample_snapshot())
        - issue a GET request to http://host:port/unknown via urllib.request.urlopen
        - ASSERT: urllib.error.HTTPError is raised
        - ASSERT: the raised HTTPError carries status code 404
        """
        host, port = running_exporter.bound_address()
        with pytest.raises(urllib.error.HTTPError) as cm:
            _get(f"http://{host}:{port}/unknown")
        assert cm.value.code == 404
        cm.value.close()  # release the underlying response to silence ResourceWarning

    def test_snapshot_callback_error_returns_500(self) -> None:
        """Negative unit test for the Exporter HTTP handler when the snapshot callback raises. It contains the
        following steps:
        - define a flaky snapshot_fn callable that raises RuntimeError on first call, returns sample after
        - construct an Exporter wired to the flaky snapshot_fn and start it on an ephemeral port
        - issue a first GET request to /snapshot via urllib.request.urlopen
        - ASSERT: urllib.error.HTTPError is raised on the first request
        - ASSERT: the raised HTTPError carries status code 500
        - issue a second GET request to /snapshot to verify server is still alive
        - ASSERT: the second request returns status 200
        """
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
        """Positive unit test for Exporter.stop() method idempotency. It contains the following steps:
        - construct an Exporter with snapshot_fn=_sample_snapshot on an ephemeral port
        - call Exporter.stop() before start() and verify it is a no-op
        - call Exporter.start() to bring the server up
        - call Exporter.stop() to bring it down
        - call Exporter.stop() a second time after the prior stop
        - ASSERT: calling stop() before start(), and twice after start(), raises no exceptions
        """
        exporter = Exporter(log=None, bind_address="127.0.0.1", port=0, snapshot_fn=_sample_snapshot)
        exporter.stop()  # before start: no-op
        exporter.start()
        exporter.stop()
        exporter.stop()  # after stop: no-op

    def test_bound_address_before_start(self) -> None:
        """Positive unit test for Exporter.bound_address() method before start. It contains the following steps:
        - construct an Exporter with snapshot_fn=_sample_snapshot, bind_address="127.0.0.1", port=12345
        - call bound_address() without first calling start()
        - ASSERT: bound_address() returns the configured ("127.0.0.1", 12345) tuple
        """
        exporter = Exporter(log=None, bind_address="127.0.0.1", port=12345, snapshot_fn=_sample_snapshot)
        assert exporter.bound_address() == ("127.0.0.1", 12345)

    def test_log_at_info_on_start(self) -> None:
        """Positive unit test for Exporter.start() emitting a Log INFO line. It contains the following steps:
        - construct a real Log instance configured for LOG_INFO/LOG_STDOUT
        - monkey-patch Log.msg with a lambda capturing (level, msg) tuples into a list
        - construct an Exporter wired to the Log on an ephemeral port with snapshot_fn=_sample_snapshot
        - call Exporter.start() and tear it down afterwards
        - ASSERT: at least one captured message contains "Exporter listening on http://"
        """
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
        """Negative unit test for the Exporter HTTP handler logging when the snapshot callback raises. It contains
        the following steps:
        - construct a real Log instance configured for LOG_DEBUG/LOG_STDOUT
        - monkey-patch Log.msg with a lambda capturing (level, msg) tuples into a list
        - construct an Exporter wired to the Log on an ephemeral port with a snapshot_fn that raises RuntimeError
        - call Exporter.start() and issue a GET request to /snapshot via urllib.request.urlopen
        - ASSERT: urllib.error.HTTPError is raised by the request
        - ASSERT: the raised HTTPError carries status code 500
        - ASSERT: at least one captured log message contains "handler error"
        """
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
        """Positive unit test for the Exporter HTTP server access-log routing to Log.msg. It contains the following
        steps:
        - construct a real Log instance configured for LOG_DEBUG/LOG_STDOUT
        - monkey-patch Log.msg with a lambda capturing (level, msg) tuples into a list
        - construct an Exporter wired to the Log on an ephemeral port with snapshot_fn=_sample_snapshot
        - call Exporter.start() and issue a successful GET request to /snapshot via urllib.request.urlopen
        - ASSERT: at least one captured log message contains the "exporter:" access-log tag
        """
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
