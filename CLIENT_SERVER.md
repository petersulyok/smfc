# Plan: smfc service exporter (smfc-client IPC + Prometheus)

## Context

Two requested features land naturally together:

1. **smfc-client should reuse live state from a running smfc service** instead of
   re-querying ipmitool/smartctl independently. Today
   [src/smfc/client.py](src/smfc/client.py) is a fully standalone CLI: it loads
   the same config, opens its own `Ipmi(in_client=True)`, instantiates each
   controller, and reads sensors itself. When the service is already running,
   that means up to ~10 ipmitool subprocesses per invocation contending with
   the daemon's main loop, plus a duplicate smartctl pass per disk (which can
   wake disks that the daemon's Standby Guard put to sleep — the only real
   correctness risk in the current design).

2. **A Prometheus exporter** so the service's metrics (temps, fan levels, fan
   mode, standby states) can be scraped from a Prometheus instance — in this
   environment, Prometheus runs in Docker inside an LXC on a different host
   than smfc itself, so the exporter needs to bind on a network-reachable
   interface (not localhost-only).

Both features need the same artifact: a structured snapshot of the live
service state. We give the service one HTTP server with two routes that share
a single snapshot builder. The smfc-client gains a "talk to the service first,
fall back to standalone" mode. No new third-party dependencies.

## Design choices (locked in with user)

- Combined into one HTTP server + one config section.
- Stdlib only (`http.server`, `socketserver`, `urllib.request`, `json`, `threading`).
- One `[Exporter]` section with `enabled`, `bind_address`, `port`.
- Two routes on the same server: `/snapshot` (JSON, for smfc-client) and
  `/metrics` (Prometheus text format, for Prometheus scraping).
- smfc-client tries `/snapshot` first; on connection refused / timeout, falls
  back to the existing standalone path.
- Disabled by default; users opt in by setting `enabled=true`.
- **Snapshot is built from cached state only** — the request thread issues
  zero ipmitool/smartctl subprocesses. See *Concurrency & freshness* below.

## Prerequisite: cached fan mode on `Service`

The [`enforce_fan_mode` feature](ENFORCE_FAN_MODE.md) (already implemented)
runs an `ipmi.get_fan_mode()` poll on every main-loop iteration, caching the
result on `self.last_fan_mode` (and `self.last_fan_mode_at`). The exporter's
snapshot builder reads those attributes directly — no ipmitool call on the
request thread.

## Approach

### Phase 1 — Snapshot builder (shared core)

A new module [src/smfc/snapshot.py](src/smfc/snapshot.py) exposes one function:

```python
def build_snapshot(service: "Service") -> dict:
    ...
```

Returns a versioned dict assembled entirely from already-cached state on the
`Service`, its controllers, and the `Ipmi` instance — **the snapshot builder
issues zero subprocesses (no ipmitool, no smartctl) on the request thread**.

What's read:
- BMC info attributes on `Ipmi` (set once at startup, never mutated).
- `fc.last_temp` / `fc.last_level` from each controller (refreshed by the
  loop on every iteration).
- `HdFc.standby_array_states` / `HdFc.hd_device_names` (refreshed by the loop).
- `Service.applied_levels` (snapshotted defensively as `dict(...)`).
- `Service.last_fan_mode` / `last_fan_mode_at` (refreshed by the loop's
  periodic mode check — see [ENFORCE_FAN_MODE.md](ENFORCE_FAN_MODE.md)).

Schema sketch (JSON-shaped):

```json
{
  "version": 1,
  "generated_at": 1716902400.123,
  "smfc_version": "5.4.0",
  "bmc": {
    "manufacturer_name": "Super Micro Computer Inc.",
    "manufacturer_id": 10876,
    "product_name": "X11SCH-LN4F",
    "product_id": 6929,
    "firmware_rev": "1.74",
    "ipmi_version": "2.0",
    "platform_name": "X11SCH-LN4F",
    "platform_class": "GenericPlatform"
  },
  "fan_mode": {"id": 1, "name": "FULL", "age_s": 12.4},
  "controllers": [
    {
      "section": "CPU",
      "type": "cpu",
      "enabled": true,
      "ipmi_zones": [0],
      "device_count": 1,
      "polling": 2.0,
      "last_temp_c": 42.3,
      "last_level_pct": 45,
      "deferred_apply": false
    },
    {
      "section": "HD",
      "type": "hd",
      "ipmi_zones": [1],
      "device_count": 4,
      "last_temp_c": 34.1,
      "last_level_pct": 55,
      "device_names": ["/dev/sda", "/dev/sdb", "/dev/sdc", "/dev/sdd"],
      "standby": {
        "enabled": true,
        "limit": 1,
        "states": [false, false, true, true],
        "array_state": "AASS",
        "standby_count": 2
      }
    }
  ],
  "zones": {"0": {"applied_level_pct": 45}, "1": {"applied_level_pct": 55}}
}
```

`zones` mirrors `Service.applied_levels`. The HTTP layer can serve this dict
straight as `/snapshot` JSON, or transform it to Prometheus text for `/metrics`.

### Phase 2 — Exporter HTTP server

New module [src/smfc/exporter.py](src/smfc/exporter.py).

- `class _ExporterHandler(http.server.BaseHTTPRequestHandler)` — routes
  `GET /snapshot`, `GET /metrics`, `GET /healthz`. Anything else → 404. Logs
  via the service Log instance (override `log_message` to silence default
  stderr noise).
- `class _ExporterServer(socketserver.ThreadingMixIn, http.server.HTTPServer)`
  — threaded so a slow client never blocks others (or the loop).
- `class Exporter` — owns the server thread:
  - `start()` — bind, start `serve_forever()` in a daemon thread.
  - `stop()` — `shutdown()` + `server_close()`. Called from
    `Service.exit_func()`.
- The server holds a callback `lambda: build_snapshot(service)`.
  Each request rebuilds the snapshot fresh from already-cached state. The
  loop's mutations of `last_temp`/`last_level` and `last_fan_mode` are
  atomic attribute writes; reading them from the request thread is safe in
  CPython without explicit locking. The only mutable container the request
  thread reads is `Service.applied_levels`, which the snapshot builder
  copies defensively (`dict(self.applied_levels)`) to avoid `RuntimeError:
  dictionary changed size during iteration`.

#### Prometheus text format (no `prometheus_client` dep)

Hand-roll the text format — it's a few lines per metric:

```
# HELP smfc_temperature_celsius Last observed temperature per controller.
# TYPE smfc_temperature_celsius gauge
smfc_temperature_celsius{section="CPU",type="cpu"} 42.3
smfc_temperature_celsius{section="HD",type="hd"} 34.1

# HELP smfc_fan_level_percent Last applied fan level per IPMI zone.
# TYPE smfc_fan_level_percent gauge
smfc_fan_level_percent{zone="0"} 45
smfc_fan_level_percent{zone="1"} 55

# HELP smfc_fan_mode Current IPMI fan mode (0=STANDARD,1=FULL,2=OPTIMAL,3=PUE,4=HEAVY_IO).
# TYPE smfc_fan_mode gauge
smfc_fan_mode 1

# HELP smfc_fan_mode_age_seconds Age of the cached fan_mode reading.
# TYPE smfc_fan_mode_age_seconds gauge
smfc_fan_mode_age_seconds 12.4

# HELP smfc_disk_standby Disk standby state (1=standby, 0=active).
# TYPE smfc_disk_standby gauge
smfc_disk_standby{section="HD",device="/dev/sda"} 0
smfc_disk_standby{section="HD",device="/dev/sdc"} 1

# HELP smfc_up smfc service is up (1).
# TYPE smfc_up gauge
smfc_up{version="5.4.0",bmc_product="X11SCH-LN4F"} 1
```

Label values must escape `\\`, `"`, `\n`. Trivial helper.

### Phase 3 — Config

Add `[Exporter]` section to [src/smfc/config.py](src/smfc/config.py), following
the existing dataclass + `_parse_*` pattern (see `IpmiConfig` for the model):

```ini
[Exporter]
enabled=false             # default off
bind_address=127.0.0.1    # set to LAN IP for remote Prometheus
port=9099
```

New `ExporterConfig` dataclass; `Config.__init__` gains `self.exporter =
self._parse_exporter_section(parser)`. Validation: port in `1..65535`,
bind_address parses as IPv4/IPv6 or `0.0.0.0`. Default values keep behavior
identical when the section is absent.

### Phase 4 — Service wiring

In [src/smfc/service.py](src/smfc/service.py), after the main loop is set up
but before entering `while True:`:

```python
self.exporter = None
if self.config.exporter.enabled:
    self.exporter = Exporter(
        log=self.log,
        bind_address=self.config.exporter.bind_address,
        port=self.config.exporter.port,
        snapshot_fn=lambda: build_snapshot(self),
    )
    self.exporter.start()
```

Update `exit_func` to `self.exporter.stop()` if set, before the
`set_fan_mode(FULL)`. A failure to bind logs an error and continues without
the exporter — the fan-control behavior is the priority and must not be
gated on the HTTP server.

### Phase 5 — Client integration

In [src/smfc/client.py](src/smfc/client.py), `main()` becomes:

```python
args = _parse_args(argv)
cfg = Config(args.config_file)         # already loaded in current code
if cfg.exporter.enabled and not args.standalone:
    snapshot = _try_fetch_snapshot(cfg.exporter, timeout=1.0)
    if snapshot is not None:
        report = _format_report_from_snapshot(snapshot, args.config_file, use_color)
        sys.stdout.write(report); return EXIT_OK
# fall back to current standalone path
...
```

- `_try_fetch_snapshot()` does `urllib.request.urlopen("http://<bind>:<port>/snapshot", timeout=1.0)`.
  Returns the parsed dict on 200, `None` on `URLError`/`OSError`/timeout/non-200.
- New CLI flag `--standalone` forces the current code path (useful for
  diagnostics, testing, and for the case where the user wants a "clean"
  reading independent of the daemon).
- New `_format_report_from_snapshot(snapshot, config_path, use_color)` —
  refactor of the existing `_format_report()`. The current function takes
  `Ipmi` + controller objects and reads attributes off them; the snapshot
  version takes a dict with the same fields. The two share the table-rendering
  helpers (`_format_controllers_table`, `_format_zones_table`,
  `_format_standby_section`) by changing those helpers to read from a small
  intermediate `_RowData` dataclass that both paths build. This keeps the
  output identical regardless of source.
- Header line gains a `Source:` prefix above the banner so the user knows
  which path produced the report:
  - `Source: online (via smfc service)` when the snapshot came from the
    exporter's `/snapshot` endpoint.
  - `Source: offline (smfc service not running)` when the standalone path
    was used (either because the exporter is unreachable or `--standalone`
    was passed).

  This line is rendered in the `DIM` color when colors are enabled (see the
  colorized rendering example in [SMFC_CLIENT.md](SMFC_CLIENT.md)). Both
  formatters (`_format_report` and `_format_report_from_snapshot`) prepend
  it from the same `_format_source_line(online: bool, use_color: bool)`
  helper, so the label is the only piece of behavior that differs between
  paths.

### Concurrency & freshness

The exporter handler thread runs alongside the main loop. The design avoids
all synchronization primitives by following two rules:

1. **Request thread issues no subprocesses.** No `ipmitool`, no `smartctl`.
   This eliminates the only real risk between the loop and the exporter:
   concurrent BMC sessions / disk wakes. The `fan_mode` value comes from
   `Service.last_fan_mode`, refreshed by the loop's periodic mode-check
   (see [ENFORCE_FAN_MODE.md](ENFORCE_FAN_MODE.md)).
2. **Mutable containers are copied, not iterated in place.** The snapshot
   builder takes shallow copies of `Service.applied_levels` (a dict),
   `HdFc.standby_array_states` (a list), and `HdFc.hd_device_names` (a
   list). Scalar attributes (`fc.last_temp`, `fc.last_level`,
   `Service.last_fan_mode`) are read directly — CPython attribute
   reads/writes are atomic under the GIL, so a racing read sees either the
   pre- or post-write value, never a torn one.

What this **does not** guarantee: that a snapshot's `last_temp` and
`last_level` for the same controller come from the same loop iteration.
A request can land between the loop writing `last_temp` and writing
`last_level`, in which case those two scalars are momentarily out of sync.
For a fan-control dashboard sampled at second resolution this is below the
noise floor; tighter consistency would require a lock around the loop body
and the snapshot builder, which is not justified for the use case.

### Phase 6 — Tests

- [test/test_snapshot.py](test/test_snapshot.py) (new) — `build_snapshot()`
  with a mocked `Service` (Ipmi, controllers, `applied_levels`,
  `last_fan_mode`). Asserts the JSON shape, that standby states only
  appear when enabled, that const controllers omit temp, that the
  `fan_mode` block reflects `service.last_fan_mode` and reports
  `age_s`, and that `applied_levels` is copied (snapshot is unaffected
  if the original dict is later mutated).
- [test/test_exporter.py](test/test_exporter.py) (new) — start `Exporter`
  on `127.0.0.1:0` with a fake snapshot fn, hit `/snapshot`, `/metrics`,
  `/healthz`, `/missing` (→ 404). Use `urllib.request` from a thread to
  avoid blocking. Stop the exporter at teardown. Two-three tests:
  routes work, metrics format passes a regex check, server stops cleanly.
- [test/test_config.py](test/test_config.py) — extend with two cases:
  `[Exporter]` section absent → defaults; section present with custom
  values → parsed correctly; invalid port → `ValueError`.
- [test/test_client.py](test/test_client.py) — three new tests:
  exporter-enabled + reachable → `_format_report_from_snapshot` path
  taken (mock `urllib.request.urlopen`); exporter-enabled + unreachable
  → falls back to standalone; `--standalone` flag forces standalone even
  when exporter is reachable.
- [test/test_service.py](test/test_service.py) — one regression:
  `Service` instantiates with `exporter.enabled=False` and runs the loop
  body once with no exporter started.

### Phase 7 — Docs

- README: new "Remote monitoring" section covering `[Exporter]` config,
  Prometheus scrape config example for the LXC-on-different-host setup
  (`bind_address=0.0.0.0` or a specific LAN IP, plus a sample
  `prometheus.yml` job).
- Mention port choice (default 9099) and that smfc-client auto-uses the
  exporter when enabled.

## Files to change

| File | Action |
|------|--------|
| [src/smfc/snapshot.py](src/smfc/snapshot.py) | **new** — `build_snapshot()` |
| [src/smfc/exporter.py](src/smfc/exporter.py) | **new** — `Exporter`, JSON + Prometheus formatters |
| [src/smfc/config.py](src/smfc/config.py) | add `ExporterConfig` dataclass + parser |
| [src/smfc/service.py](src/smfc/service.py) | start/stop exporter around main loop |
| [src/smfc/client.py](src/smfc/client.py) | exporter-aware `main()`, `--standalone` flag, snapshot-driven formatter |
| [test/test_snapshot.py](test/test_snapshot.py) | **new** |
| [test/test_exporter.py](test/test_exporter.py) | **new** |
| [test/test_config.py](test/test_config.py) | new cases |
| [test/test_client.py](test/test_client.py) | new cases |
| [test/test_service.py](test/test_service.py) | one regression |
| [README.md](README.md) | "Remote monitoring" section |
| [config/smfc.conf.sample](config/smfc.conf.sample) | document `[Exporter]` |

## Implementation order

1. `snapshot.py` + `test_snapshot.py` (pure function, easy to unit-test).
2. `ExporterConfig` in `config.py` + tests.
3. `exporter.py` + `test_exporter.py` (uses an in-process server on
   `127.0.0.1:0`).
4. Wire into `service.py` + regression test.
5. Refactor `client.py` formatter to consume a snapshot dict; add
   exporter-aware `main()`; add `--standalone`; add tests.
6. Docs + sample config.

Each step is independently runnable through the existing `pytest` suite.

## Verification

- `pytest` — full suite green.
- Unit: snapshot dict shape, Prometheus text format passes a regex check
  for label syntax, all four routes respond as expected.
- Manual end-to-end on the dev box:
  - `enabled=false` → `smfc-client` behaves identically to today; `curl
    http://127.0.0.1:9099/snapshot` fails with connection refused.
  - `enabled=true, bind_address=127.0.0.1` → `smfc-client` shows `(via
    smfc service)` in the header and runs visibly faster (fewer
    ipmitool subprocesses); `curl /snapshot` returns JSON; `curl /metrics`
    returns parseable Prometheus text.
  - `bind_address=<LAN IP>` → from the Prometheus LXC, `curl
    http://<host>:9099/metrics` works; add a scrape job to `prometheus.yml`
    and confirm metrics appear in Prometheus.
  - Stop the service while a client is mid-request → no zombie threads
    (test by killing & restarting; the daemon thread dies with the process).

## Pros / cons of the combined approach

**Pros**
- One config section, one HTTP server, one snapshot builder. Adding the
  Prometheus exporter later is a 30-line text-format helper, not a new
  subsystem.
- smfc-client gets faster and stops contending with the daemon over
  ipmitool / smartctl. Eliminates the disk-wakeup risk noted earlier, and
  the request thread does **zero** ipmitool/smartctl work.
- Stdlib-only. No new runtime dep; no `prometheus_client`, no `flask`.
- `--standalone` keeps the current code path alive for diagnostics and
  for the case where the service is buggy/hung.

**Cons**
- The service now runs a network listener. Mitigations: off by default;
  `bind_address=127.0.0.1` recommended unless Prometheus is remote;
  metrics aren't sensitive but a misconfigured `0.0.0.0` exposes
  hardware fingerprint info to the LAN.
- Two paths in client.py (standalone vs exporter) means two formatters
  to keep in sync. Mitigation: refactor the rendering helpers to consume
  a common intermediate dataclass so both paths render identically.
- A bug in the HTTP server thread theoretically affects the daemon
  process. Mitigation: handler-level `try/except`, server runs in a
  daemon thread, exporter init failure is logged and the loop continues.

## Risks / open questions

- **Port choice.** 9099 is unassigned in IANA. We could add a
  `smfc-client --discover` to read the config and print the URL the
  exporter would use, but probably overkill — the user knows their config.
- **No auth.** Prometheus has no built-in auth; standard practice is to
  rely on network reachability. Acceptable for homelab. If someone later
  wants TLS / basic auth, that's a follow-up — the snapshot builder
  doesn't change.
- **Schema versioning.** The JSON includes `"version": 1`. If the schema
  changes, smfc-client and the service can be from different smfc
  versions in principle (the user upgrades one, restarts the other).
  Bump the version int and have the client warn (and fall back to
  standalone) on unknown majors.
- **Concurrent ipmitool from `/snapshot` and the loop.** Eliminated by
  design: the request handler issues no subprocesses (see *Concurrency &
  freshness*). The cached `fan_mode` is refreshed by the loop, not the
  request thread.
- **Should `/snapshot` and `/metrics` be on different ports?** Decided
  no: same data, same audience (anyone on the network), one fewer thing
  to configure.
