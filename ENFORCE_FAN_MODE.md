# Plan: enforce_fan_mode — auto-recover BMC fan mode drift

> **Status: implemented** on `feature/smfc-client`. See
> [src/smfc/service.py](src/smfc/service.py) (`_check_fan_mode`,
> `last_fan_mode`/`last_fan_mode_at`) and
> [src/smfc/config.py](src/smfc/config.py) (`IpmiConfig.enforce_fan_mode`).
> Tests live in [test/test_service.py](test/test_service.py) and
> [test/test_config.py](test/test_config.py). The notes below are kept as
> design rationale; the actual code is the source of truth.

## Context

`smfc` controls fan levels by first flipping the BMC into `FULL` fan mode at
startup ([service.py:272-274](src/smfc/service.py#L272-L274)) and then
issuing per-zone level commands. The whole control strategy assumes the BMC
stays in `FULL`. If something else flips the mode out from under us — the
BMC web UI, a one-off `ipmitool raw` command from another tool, an obscure
firmware quirk, a BMC reset — smfc keeps issuing per-zone level commands,
but the BMC may ignore them or apply them through its own profile, and the
fans run at whatever the BMC profile decides. The user has no visibility
into this: smfc looks healthy in syslog while the chassis is too quiet
(or too loud) for the actual workload.

This plan adds a periodic safety check inside the main loop. Every loop
iteration the service reads the current BMC fan mode, caches it, and reacts
to any drift away from `FULL`. The default behavior is to log the drift,
re-assert `FULL`, and re-apply all known per-zone levels — auto-recovery.
A configuration option lets users opt into the stricter "exit on drift"
behavior instead.

The cached `fan_mode` value populated by this feature is also the source the
[smfc-client + Prometheus exporter](CLIENT_SERVER.md) plan reads on every
request, eliminating the only ipmitool subprocess that would otherwise run
on the request thread. The two features are independent but mutually
beneficial.

## Design choices (locked in with user)

- New `[Ipmi] enforce_fan_mode=` option, **default `true`** (auto-recover).
- When `true` and drift detected: log INFO, call `set_fan_mode(FULL)` and
  re-assert all `Service.applied_levels` per-zone, continue loop.
- When `false` and drift detected: log ERROR and exit (`sys.exit(11)`).
- Cadence: every main-loop iteration. No TTL knob in the config — the loop
  is already ~1–2 s; one extra ipmitool subprocess per iteration is
  negligible relative to the per-controller temperature reads happening
  every iteration. Power users can revisit this with a future
  `fan_mode_check_interval=` knob if needed.
- No drift counter exposed yet (deferred — can be added later without
  breaking the snapshot schema or any existing API).

## Approach

### Phase 1 — Config

Add to [src/smfc/config.py](src/smfc/config.py)'s `IpmiConfig` dataclass and
its parser:

```python
@dataclass
class IpmiConfig:
    ...
    enforce_fan_mode: bool = True
```

Parsed via `parser.getboolean("Ipmi", "enforce_fan_mode", fallback=True)`.
Default-on preserves the existing implicit contract that smfc holds the BMC
in `FULL` for the whole runtime.

Sample `[Ipmi]` section:

```ini
[Ipmi]
command=/usr/bin/ipmitool
fan_mode_delay=10
fan_level_delay=2
enforce_fan_mode=true   # default; set to false to exit on drift instead of recovering
```

### Phase 2 — Service state

In [src/smfc/service.py](src/smfc/service.py), add two attributes
populated during `Service.run()` setup, **after** the conditional
`set_fan_mode(FULL_MODE)` block. At that point the BMC is guaranteed to be
in FULL — either it already was, or we just set it — so seeding is a single
unconditional assignment:

```python
self.last_fan_mode: int = Ipmi.FULL_MODE
self.last_fan_mode_at: float = time.monotonic()
```

These are also the source the exporter reads (see
[CLIENT_SERVER.md](CLIENT_SERVER.md)).

### Phase 3 — Main loop guard

Replace the bare main loop ([service.py:332-337](src/smfc/service.py#L332-L337))
with a check at the end of each iteration:

```python
while True:
    for fc in self.controllers:
        fc.run()
    if self.shared_zones:
        self._apply_fan_levels()

    self._check_fan_mode()

    time.sleep(wait)
```

New helper `Service._check_fan_mode()`:

```python
def _check_fan_mode(self) -> None:
    """Read the current BMC fan mode, cache it, and react to drift.

    When enforce_fan_mode is enabled (default), drift away from FULL is
    auto-corrected: re-assert FULL and re-apply all cached per-zone levels.
    When disabled, drift triggers a clean exit with code 11.
    """
    try:
        mode = self.ipmi.get_fan_mode()
    except (RuntimeError, ValueError) as e:
        # Transient BMC error: log and skip this cycle. Don't exit — the
        # control loop is the recovery mechanism for transient errors.
        self.log.msg(Log.LOG_ERROR, f"Fan mode read failed: {e}")
        return

    self.last_fan_mode = mode
    self.last_fan_mode_at = time.monotonic()

    if mode == Ipmi.FULL_MODE:
        return

    mode_name = Ipmi.get_fan_mode_name(mode)
    if not self.config.ipmi.enforce_fan_mode:
        self.log.msg(Log.LOG_ERROR,
                     f"BMC fan mode drifted from FULL to {mode_name}; "
                     f"enforce_fan_mode is disabled, smfc exiting.")
        sys.exit(11)

    # Auto-recovery path: re-assert FULL and re-apply all cached per-zone
    # levels. Some BMC firmwares reset zone levels when the mode changes,
    # so restoring the mode without restoring the levels can leave fans at
    # BMC defaults until the next polling cycle.
    self.log.msg(Log.LOG_INFO,
                 f"BMC fan mode drifted from FULL to {mode_name}; restoring FULL.")
    try:
        self.ipmi.set_fan_mode(Ipmi.FULL_MODE)
        self.last_fan_mode = Ipmi.FULL_MODE
        self.last_fan_mode_at = time.monotonic()
        for zone, level in self.applied_levels.items():
            self.ipmi.set_fan_level(zone, level)
    except (RuntimeError, ValueError) as e:
        # Recovery itself failed transiently; the next loop iteration will
        # try again. Don't exit.
        self.log.msg(Log.LOG_ERROR, f"Fan mode recovery failed: {e}")
```

### Phase 4 — Exit code documentation

Update the exit-code comment block in
[Service.run](src/smfc/service.py#L202-L213) to add code 11:

```
0  - printing help or version text (argument parser)
2  - invalid parameter (argument parser)
5  - log system initialization error
6  - config file error
7  - runtime dependency error
8  - IPMI initialization error
9  - udev initialization error
10 - none of the fan controllers is enabled
11 - BMC fan mode drifted (enforce_fan_mode=false)
```

### Phase 5 — Tests

Add to [test/test_service.py](test/test_service.py):

1. **Guard enabled, mode stays FULL.** Loop iteration runs `_check_fan_mode()`,
   `get_fan_mode()` returns `FULL_MODE`, no recovery actions, no log noise
   above DEBUG.
2. **Guard enabled, mode drifts.** `get_fan_mode()` returns `STANDARD_MODE`.
   Assert: `set_fan_mode(FULL_MODE)` called once, `set_fan_level(zone, level)`
   called for every entry in `applied_levels`, INFO log message contains
   `"drifted"`.
3. **Guard disabled, mode drifts.** `enforce_fan_mode=False`, `get_fan_mode()`
   returns `OPTIMAL_MODE`. Assert: `sys.exit(11)` raised, ERROR log message
   contains `"drifted"`.
4. **Transient `get_fan_mode()` error.** Mocked to raise `RuntimeError("ipmitool ...")`.
   Assert: ERROR logged, no exit, `last_fan_mode` unchanged from previous
   value, loop continues.
5. **Transient `set_fan_mode()` failure during recovery.** Mode drifts; the
   recovery `set_fan_mode(FULL)` raises `RuntimeError`. Assert: ERROR logged,
   no exit, `last_fan_mode` not advanced past the bad reading (so the next
   iteration retries cleanly).

Add to [test/test_config.py](test/test_config.py):

6. `[Ipmi]` section without `enforce_fan_mode=` → defaults to `True`.
7. `enforce_fan_mode=false` parsed correctly to `False`.

### Phase 6 — Docs

- README: brief paragraph in the existing `[Ipmi]` config table covering
  `enforce_fan_mode=` and the two behaviors.
- `config/smfc.conf.sample`: add the `enforce_fan_mode=true` line with a
  comment matching the README copy.

## Files to change

| File | Action |
|------|--------|
| [src/smfc/config.py](src/smfc/config.py) | add `enforce_fan_mode` to `IpmiConfig` + parser |
| [src/smfc/service.py](src/smfc/service.py) | add `last_fan_mode*` attrs, `_check_fan_mode()`, wire into loop, exit code 11 in docstring |
| [test/test_service.py](test/test_service.py) | five new tests |
| [test/test_config.py](test/test_config.py) | two new cases |
| [README.md](README.md) | document `enforce_fan_mode=` |
| [config/smfc.conf.sample](config/smfc.conf.sample) | sample line |

## Implementation order

1. Add `enforce_fan_mode` to `IpmiConfig` + tests. Run `pytest test/test_config.py`
   — defaults to `True`, parses the new value, existing tests pass.
2. Add `last_fan_mode*` and `_check_fan_mode()` to `Service`, wire
   into the main loop, update the exit-code comment block.
3. Add the five service tests. Run full suite.
4. Update sample config and README.

## Verification

End-to-end on the dev box:

- Start `smfc.service`. Confirm DEBUG log shows the periodic
  `_check_fan_mode` call returning FULL each iteration; no INFO drift
  messages.
- Externally flip the BMC fan mode while the service is running:
  `sudo ipmitool raw 0x30 0x45 0x01 0x00` (sets STANDARD).
- With `enforce_fan_mode=true` (default): expect one INFO log line within ~1–2 s
  reading "BMC fan mode drifted from FULL to STANDARD; restoring FULL.",
  followed by silent operation. Confirm fan levels stay at smfc-controlled
  values (not BMC defaults).
- With `enforce_fan_mode=false`: expect one ERROR log line and clean exit
  with code 11. Systemd will restart the unit per the `Restart=` policy.

## Risks / open questions

- **Cost per loop iteration.** One extra ipmitool subprocess per loop. At
  ~1 s cadence on a typical box that's ~86 k extra subprocesses per day —
  comparable to the existing per-controller temperature reads. Not a
  practical concern. If a user reports impact (e.g., very tight polling
  intervals), a future `fan_mode_check_interval=` knob is straightforward
  to add without breaking the API.
- **Recovery race.** Between detecting the drift and re-asserting `FULL`, a
  second external command can flip the mode again. The next loop iteration
  catches it. Acceptable.
- **What about other "wrong" modes besides STANDARD?** Any mode other than
  `FULL` triggers the same path (recover or exit). That includes `OPTIMAL`,
  `PUE`, `HEAVY_IO`. smfc requires `FULL` to do its job; treating all
  non-FULL modes uniformly is correct.
- **Drift counter / Prometheus metric.** Skipped for now per the user's
  decision. Adding `Service.fan_mode_drift_count` later is purely additive:
  one int attribute, one snapshot field, one Prometheus counter line. No
  schema break.
- **Log spam during sustained drift.** If something keeps flipping the mode
  every few seconds, the service emits an INFO line on every loop iteration.
  In practice this is desired (the user wants to know), but rate-limiting
  could be added later if needed.
