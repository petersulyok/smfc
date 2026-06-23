#
#   exporter.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   HTTP exporter: serves /snapshot (JSON) and /metrics (Prometheus text format) to smfc-client and Prometheus.
#
import http.server
import json
import socketserver
import threading
from typing import Any, Callable, Dict, List, Optional

from smfc.log import Log


SNAPSHOT_PATH: str = "/snapshot"
METRICS_PATH: str = "/metrics"
HEALTHZ_PATH: str = "/healthz"


def _escape_label_value(value: str) -> str:
    """Escape a Prometheus label value per the exposition format spec.

    Backslashes, double quotes, and newlines must be escaped; everything else passes through.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_labels(pairs: List[tuple]) -> str:
    """Render a non-empty list of (name, value) label pairs into the Prometheus `{n1="v1",n2="v2"}` form.

    Callers that emit label-less metrics (e.g. smfc_fan_mode) skip this helper entirely.
    """
    parts = [f'{name}="{_escape_label_value(str(value))}"' for name, value in pairs]
    return "{" + ",".join(parts) + "}"


def render_prometheus(snapshot: Dict[str, Any]) -> str:
    """Render a snapshot dict as Prometheus text format.

    The output uses the standard `# HELP` / `# TYPE` headers and gauge metrics. Label values are
    properly escaped. A trailing newline is included so the response body is well-formed.
    """
    lines: List[str] = []

    bmc = snapshot.get("bmc", {})
    smfc_version = str(snapshot.get("smfc_version", ""))

    # --- Service identity ---
    lines.append("# HELP smfc_up smfc service is up (1); carries the running version.")
    lines.append("# TYPE smfc_up gauge")
    lines.append(f'smfc_up{_format_labels([("version", smfc_version)])} 1')

    lines.append("")
    lines.append("# HELP smfc_start_time_seconds Unix start time of the smfc service.")
    lines.append("# TYPE smfc_start_time_seconds gauge")
    lines.append(f"smfc_start_time_seconds {float(snapshot.get('start_time', 0.0))}")

    bmc_labels = _format_labels([("product_name", bmc.get("product_name", "")),
                                 ("firmware_version", bmc.get("firmware_rev", "")),
                                 ("manufacturer_name", bmc.get("manufacturer_name", ""))])
    lines.append("")
    lines.append("# HELP smfc_bmc_info BMC identity reported by ipmitool bmc info.")
    lines.append("# TYPE smfc_bmc_info gauge")
    lines.append(f"smfc_bmc_info{bmc_labels} 1")

    lines.append("")
    lines.append("# HELP smfc_fan_mode_enforced_total Times smfc re-asserted FULL after the BMC fan mode drifted.")
    lines.append("# TYPE smfc_fan_mode_enforced_total counter")
    lines.append(f"smfc_fan_mode_enforced_total {int(snapshot.get('fan_mode_enforced_count', 0))}")

    controllers = snapshot.get("fan_controllers", []) or []

    # --- Static config ---
    lines.append("")
    lines.append("# HELP smfc_controller_zone Enabled fan-controller-to-IPMI-zone mapping (value always 1).")
    lines.append("# TYPE smfc_controller_zone gauge")
    for c in controllers:
        if not c.get("enabled", True):
            continue
        section, ctype = c.get("section", ""), c.get("type", "")
        for zone in c.get("ipmi_zones", []) or []:
            labels = _format_labels([("section", section), ("type", ctype), ("zone", str(zone))])
            lines.append(f"smfc_controller_zone{labels} 1")

    lines.append("")
    lines.append("# HELP smfc_controller_temperature_min_celsius Controller steering-window floor (static config).")
    lines.append("# TYPE smfc_controller_temperature_min_celsius gauge")
    lines.append("# HELP smfc_controller_temperature_max_celsius Controller steering-window ceiling (static config).")
    lines.append("# TYPE smfc_controller_temperature_max_celsius gauge")
    for c in controllers:
        if c.get("type") == "const":
            continue
        section, ctype = c.get("section", ""), c.get("type", "")
        for zone in c.get("ipmi_zones", []) or []:
            labels = _format_labels([("section", section), ("type", ctype), ("zone", str(zone))])
            lines.append(f"smfc_controller_temperature_min_celsius{labels} {float(c.get('temp_min_c', 0.0))}")
            lines.append(f"smfc_controller_temperature_max_celsius{labels} {float(c.get('temp_max_c', 0.0))}")

    lines.append("")
    lines.append("# HELP smfc_controller_level_min_percent Controller fan-level-window floor (static config).")
    lines.append("# TYPE smfc_controller_level_min_percent gauge")
    lines.append("# HELP smfc_controller_level_max_percent Controller fan-level-window ceiling (static config).")
    lines.append("# TYPE smfc_controller_level_max_percent gauge")
    for c in controllers:
        section, ctype = c.get("section", ""), c.get("type", "")
        for zone in c.get("ipmi_zones", []) or []:
            labels = _format_labels([("section", section), ("type", ctype), ("zone", str(zone))])
            lines.append(f"smfc_controller_level_min_percent{labels} {int(c.get('level_min_pct', 0))}")
            lines.append(f"smfc_controller_level_max_percent{labels} {int(c.get('level_max_pct', 0))}")

    # --- Dynamic runtime ---
    lines.append("")
    lines.append("# HELP smfc_controller_temperature_celsius Per-controller temperature, per targeted zone;"
                 " skipped for CONST.")
    lines.append("# TYPE smfc_controller_temperature_celsius gauge")
    for c in controllers:
        if c.get("type") == "const":
            continue
        section, ctype = c.get("section", ""), c.get("type", "")
        temp = float(c.get("last_temp_c", 0.0))
        for zone in c.get("ipmi_zones", []) or []:
            labels = _format_labels([("section", section), ("type", ctype), ("zone", str(zone))])
            lines.append(f"smfc_controller_temperature_celsius{labels} {temp}")

    lines.append("")
    lines.append("# HELP smfc_device_temperature_celsius Per-device temperature reading.")
    lines.append("# TYPE smfc_device_temperature_celsius gauge")
    for c in controllers:
        if c.get("type") == "const":
            continue
        section, ctype = c.get("section", ""), c.get("type", "")
        for d in c.get("devices", []) or []:
            labels = _format_labels([("section", section), ("type", ctype),
                                     ("device", str(d.get("name", "")))])
            lines.append(f"smfc_device_temperature_celsius{labels} {float(d.get('temp_c', 0.0))}")

    lines.append("")
    lines.append("# HELP smfc_controller_level_percent Fan level requested by the controller, per targeted zone.")
    lines.append("# TYPE smfc_controller_level_percent gauge")
    for c in controllers:
        section, ctype = c.get("section", ""), c.get("type", "")
        level = int(c.get("last_level_pct", 0))
        for zone in c.get("ipmi_zones", []) or []:
            labels = _format_labels([("section", section), ("type", ctype), ("zone", str(zone))])
            lines.append(f"smfc_controller_level_percent{labels} {level}")

    zones = snapshot.get("zones", {}) or {}
    lines.append("")
    lines.append("# HELP smfc_zone_level_percent Fan level applied to the IPMI zone after arbitration.")
    lines.append("# TYPE smfc_zone_level_percent gauge")
    for zone, info in sorted(zones.items(), key=lambda kv: int(kv[0])):
        labels = _format_labels([("zone", zone)])
        lines.append(f"smfc_zone_level_percent{labels} {int(info.get('applied_level_pct', 0))}")

    standby_lines: List[str] = []
    for c in controllers:
        if c.get("type") != "hd":
            continue
        sb = c.get("standby_guard") or {}
        if not sb.get("enabled"):
            continue
        section = c.get("section", "")
        names = [d.get("name", "") for d in (c.get("devices", []) or [])]
        states = sb.get("states", []) or []
        for name, state in zip(names, states):
            labels = _format_labels([("section", section), ("device", name)])
            standby_lines.append(f"smfc_disk_standby{labels} {1 if state else 0}")
    if standby_lines:
        lines.append("")
        lines.append("# HELP smfc_disk_standby Disk standby state (1=standby, 0=active).")
        lines.append("# TYPE smfc_disk_standby gauge")
        lines.extend(standby_lines)

    return "\n".join(lines) + "\n"


SnapshotFn = Callable[[], Dict[str, Any]]


class _ExporterHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler routing /snapshot, /metrics, /healthz; everything else is 404."""

    # Set by _ExporterServer at bind time.
    snapshot_fn: SnapshotFn
    log: Optional[Log]

    server_version = "smfc-exporter/1.0"
    sys_version = ""  # don't leak Python version

    def log_message(self, format, *args):  # pylint: disable=redefined-builtin
        """Route default access-log lines through the smfc Log instance at DEBUG level."""
        if self.log is not None and self.log.log_level >= Log.LOG_DEBUG:
            self.log.msg(Log.LOG_DEBUG, "exporter: " + (format % args))

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Route GET requests to /snapshot, /metrics, /healthz; everything else returns 404."""
        path = self.path.split("?", 1)[0]
        try:
            if path == SNAPSHOT_PATH:
                snap = self.snapshot_fn()
                body = json.dumps(snap).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
                return
            if path == METRICS_PATH:
                snap = self.snapshot_fn()
                body = render_prometheus(snap).encode("utf-8")
                # Prometheus exposition format content-type per the spec.
                self._send(200, "text/plain; version=0.0.4; charset=utf-8", body)
                return
            if path == HEALTHZ_PATH:
                self._send(200, "text/plain; charset=utf-8", b"ok\n")
                return
            self._send(404, "text/plain; charset=utf-8", b"not found\n")
        except Exception as e:  # pylint: disable=broad-except
            # Never let a handler exception crash the daemon thread; log + 500.
            if self.log is not None:
                self.log.msg(Log.LOG_ERROR, f"exporter: handler error on {path}: {e}")
            try:
                self._send(500, "text/plain; charset=utf-8", b"internal error\n")
            except Exception:  # pylint: disable=broad-except  # pragma: no cover
                # The 500 response itself failed (e.g. socket already broken). Nothing to do.
                pass


class _ExporterServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Threaded HTTP server: requests run on per-request threads so a slow client never blocks the loop."""

    daemon_threads = True
    allow_reuse_address = True


class Exporter:
    """Owns the exporter's HTTP server thread and its lifecycle.

    Public API:
      - start(): bind socket and spawn the daemon serve_forever() thread.
      - stop():  shutdown() + server_close(). Idempotent.
      - bound_address(): returns (host, port) actually bound (useful when port=0).
    """

    def __init__(self, log: Optional[Log], bind_address: str, port: int, snapshot_fn: SnapshotFn) -> None:
        """Create an exporter instance. The HTTP server is not yet started; call start() to bind.

        Args:
            log: Log instance (or None to suppress logging).
            bind_address: IP to bind to (e.g. "127.0.0.1", "0.0.0.0", LAN IP).
            port: TCP port (1..65535, or 0 for ephemeral — useful in tests).
            snapshot_fn: callable returning the live snapshot dict for /snapshot and /metrics.
        """
        self._log = log
        self._bind_address = bind_address
        self._port = port
        self._snapshot_fn = snapshot_fn
        self._server: Optional[_ExporterServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Bind the listener and spawn the daemon serve_forever() thread.

        Raises OSError on bind failure (e.g. port already in use). The caller is responsible for
        catching this and continuing without the exporter — fan control must not be gated on HTTP.
        """
        # Build a Handler subclass with our snapshot callback and Log baked in as class attributes.
        # Each per-request handler instance reads them from the class.
        log_ref = self._log
        snapshot_fn_ref = self._snapshot_fn

        class _BoundHandler(_ExporterHandler):
            snapshot_fn = staticmethod(snapshot_fn_ref)
            log = log_ref

        self._server = _ExporterServer((self._bind_address, self._port), _BoundHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="smfc-exporter",
            daemon=True,
        )
        self._thread.start()
        if self._log is not None:
            host, port = self.bound_address()
            self._log.msg(Log.LOG_INFO, f"Exporter listening on http://{host}:{port}")

    def stop(self) -> None:
        """Shut the server down and join the worker thread. Idempotent."""
        if self._server is None:
            return
        try:
            self._server.shutdown()
            self._server.server_close()
        finally:
            if self._thread is not None:
                self._thread.join(timeout=5.0)
            self._server = None
            self._thread = None

    def bound_address(self) -> tuple:
        """Return the (host, port) the server is actually bound to (resolves port=0 to the OS-chosen port)."""
        if self._server is None:
            return (self._bind_address, self._port)
        return self._server.server_address[:2]


# End.
