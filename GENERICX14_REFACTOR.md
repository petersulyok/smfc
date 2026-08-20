# Fix X14 fan control and refactor the Platform control contract

## Context

`X14_MANUAL_FANCONTROL.md` (repo root) documents the confirmed IPMI raw command set of the
X14/AST2600 BMC. Comparing it with `src/smfc/genericx14.py` shows `GenericX14Platform` cannot
control an X14 board at all:

- the duty **write** uses `0x30 0x70 0x88` (the *read* opcode) instead of `0x30 0x70 0x66 0x00 …`;
- the duty **read** passes a *zone* where a *fan sensor number* (`0x41`+) is required, and parses a
  two-byte `[duty, temp]` reply with `int(stdout, 16)`, which raises `ValueError`;
- the manual-mode OEM command omits its `<op>` byte (`0x2c 0x04 0xcf 0xc2 0x00 <op> <zone> [<val>]`),
  so the loop variable lands in the op slot — manual mode is **never** enabled or released;
- manual-command zones are 1-based, duty-command zones 0-based; the code uses 0-based for both;
- `FANCTL_COUNT = 6` matches no documented X14 board (1–4 zones).

Beyond those, there is a structural problem the current `Platform` ABC cannot express. `Platform`
only translates commands; the *policy* of "acquire control, verify it is still held, release it"
lives in `Service`, hard-coded as "the BMC must be in FULL fan mode":

- `Ipmi.__init__` (`ipmi.py:141`) calls `platform.start()`, and `Service.run()`
  (`service.py:428`) *afterwards* may call `set_fan_mode(FULL)` — which per §4.1 of the guide
  **clears manual mode on every zone**, undoing the `start()` that just ran;
- `Service._check_fan_mode()` (`service.py:274`) re-asserts FULL on drift, which on X14 destroys
  manual mode on every poll where drift is seen, and it never checks the flag that actually matters;
- on X14 the base fan mode is only the *fallback curve*; enforcing FULL is meaningless there.

Outcome: X14 boards actually controllable, and a `Platform` contract where each platform owns its
own "am I in control?" semantics instead of `Service` assuming FULL mode for everyone.

Decisions taken with the user:

- **X14 base fan mode is left as found** — read only (it selects the zone map), never written.
- **X14 level reads** get their zone→fan-sensor map from a new `[Ipmi] x14_zone_sensors=` setting
  (default `0x41` for zone 0, other zones unmapped) instead of being inferred or measured.
- **An unreadable state counts as lost** — smfc re-acquires rather than skipping the cycle, so
  `ControlState` is just `OK`/`LOST`; a separate `confirmed` flag keeps an unreachable BMC out of the
  `fan_mode_enforced_total` metric.
- **X14 supports 4 zones (0-3)** — `FANCTL_COUNT: 6 → 4`, the documented board maximum of §3.
- **The zone limit stays platform-only**: `Config.parse_ipmi_zones()` keeps accepting 0-100 and
  `GenericPlatform` keeps its 0-100 range; neither is touched by this refactor.
- **H14 routing stays** as it is (only one known, non-working board); the §4.0 preflight is added as
  a *log warning*, not a hard failure.
- **`/snapshot` and `/metrics` output stays byte-for-byte as it is today.**

---

## 1. Widened `Platform` control contract (`src/smfc/platform.py`)

`start()` is **kept**, and its meaning widens from "prepare for manual control" to "bring this
platform into the state where smfc controls the fans" — which includes the FULL-mode write on the
platforms that need one. The FULL-mode policy moves out of `Service` into the platforms that
actually want it, and `start()` becomes **idempotent**, so drift recovery is simply calling it again.

That keeps the new surface to a single new method (`check_fan_mode()`): `end()` already exists and
already releases X14 manual mode, and re-acquiring is `start()` itself, so no separate
`restore_control()` / `leave_manual_mode()` / `enter_manual_mode()` are introduced.

```python
class ControlState(IntEnum):
    OK = 0     # smfc is in control of the fans
    LOST = 1   # control was lost: mode drifted, manual flag cleared, or the state could not be read


@dataclass(frozen=True)
class ControlStatus:
    state: ControlState
    detail: str            # human-readable reason, logged verbatim by Service
    fan_mode: int          # observed base fan mode, for the snapshot cache (-1 = not read)
    confirmed: bool = True # False when the state could not be read at all (BMC error)
```

**There is no `UNKNOWN` state.** An earlier draft had one for "the read itself failed", mapped to
"skip this cycle" (which is what `Service` does today, `service.py:249-256`). In practice an
unreadable state is a lost state: smfc cannot demonstrate it is in control, so it re-acquires. This
matches the guide's §4.5 watchdog, which re-asserts on any unreadable reply rather than waiting.
`check_fan_mode()` therefore catches `(RuntimeError, ValueError)` internally — a BMC completion-code
error surfaces as `RuntimeError` from `Ipmi._exec_ipmitool()` (`ipmi.py:213-217`) — and returns
`LOST` with `confirmed=False` and a `detail` that says the state could not be read.
`FileNotFoundError` (no `ipmitool` at all) still propagates.

`confirmed` exists so an unreachable BMC does not look like fan-mode drift in the metrics: a
rebooting BMC reports `LOST` on every poll, and counting each one would inflate
`smfc_fan_mode_enforced_total` (see §3 for the exact rules).

Methods:

| Method | Change | Purpose |
| --- | --- | --- |
| `start(zones) -> bool` | signature + semantics, **concrete in the ABC** | acquire **and re-acquire** control; idempotent. Gains the zone list; returns `True` if it wrote the fan mode, so the caller knows to apply `fan_mode_delay`. |
| `check_fan_mode(zones) -> ControlStatus` | **new**, concrete in the ABC | "am I still in the demanded state?" — the platform, not `Service`, defines what is demanded. |
| `end(zones, level)` | unchanged signature, concrete in the ABC | `set_multiple_fan_levels(zones, level)`; only X14 overrides it (§2). |
| `get_fan_mode()` / `set_fan_mode(mode)` | **hoisted** into the ABC | byte-identical (`raw 0x30 0x45 0x00`) and near-identical (only the `valid_fan_modes` check differs) in all four platforms today. |

`start()` takes the zone list because X14 must know which zones to latch — latching a zone smfc does
not drive freezes it at its current duty with nothing regulating it (today's code latches all six,
which has exactly that hazard).

### Shared implementation lives in the ABC

Three of the four platforms want identical behaviour, so it is written once as a concrete default and
the outlier overrides. `Platform` stops being a pure interface and carries the majority policy —
"FULL fan mode means smfc is in control" — which is true for every Supermicro generation except X14:

```python
class Platform(ABC):
    valid_fan_modes: List[int] = [...]      # per subclass
    ENFORCES_FULL_MODE: bool = True         # False on X14; also gates the smfc-client warning (§3)

    def start(self, zones: List[int]) -> bool:
        """Acquire (or re-acquire) control of the fans. Idempotent."""
        if self.get_fan_mode() != FanMode.FULL:
            self.set_fan_mode(FanMode.FULL)     # read-then-conditional-write from service.py:419-431
            return True
        return False

    def check_fan_mode(self, zones: List[int]) -> ControlStatus: ... # OK iff mode == FULL
    def end(self, zones: List[int], level: int) -> None: ...          # level write only
    def get_fan_mode(self) -> int: ...                                # raw 0x30 0x45 0x00
    def set_fan_mode(self, mode: int) -> None: ...                    # validates against valid_fan_modes
```

The abstract set shrinks to what genuinely differs per board: `get_fan_level`, `set_fan_level`,
`set_multiple_fan_levels`. This deletes roughly fourteen duplicated methods (four `get_fan_mode`,
four `set_fan_mode`, four `end`, two `start`) — the same duplication that let the wrong X14 opcode sit
unnoticed. `test_platforms.py` still drives every platform through the shared `PlatformSpec` matrix,
so inherited behaviour stays asserted per platform rather than assumed.

### Platforms get no `Log`

`Platform.__init__` keeps its `(name, exec_ipmitool)` signature; platforms never log and never exit.
Everything they need to communicate has a channel already:

- failures → **raise** (`RuntimeError`/`ValueError`); `Service` logs and exits (§3);
- "I wrote the fan mode" → `start()`'s `bool`, which `Service` turns into the existing
  `Set IPMI fan mode = FULL` DEBUG line;
- "control was lost, because…" → `ControlStatus.detail`, logged verbatim;
- command-level tracing → already free: `Ipmi._exec_ipmitool()` logs every argument list and reply
  at DEBUG (`ipmi.py:204,209`), and all four platforms share that callback.

Earlier drafts needed a logger for X14 diagnostics (measured sensor map, active failsafe, §4.0
preflight warning); all three of those features are gone. If a future need appears, adding a `Log`
argument to `Platform.__init__` and `create_platform()` is a contained change.

Per-platform behaviour:

- **`GenericPlatform` / `GenericX9Platform`** (`generic.py`, `genericx9.py`): declare
  `valid_fan_modes` and their three level methods, and **nothing else** — `start()`, `check_fan_mode()`,
  `end()`, `get_fan_mode()` and `set_fan_mode()` are all inherited. `check_fan_mode()` reports `LOST`
  with `detail="fan mode drifted from FULL to <name>"`, and calling `start()` again re-asserts FULL,
  which is what the recovery path at `service.py:274` does today.
- **`X10QBi`** (`x10qbi.py`): inherits the FULL logic and overrides `start()` only to add the chip
  setup — `self._configure_chip(); return super().start(zones)`. The register setup
  **must** move out of `start()` into a private `_configure_chip()`, because `set_fan_level()` and
  `set_multiple_fan_levels()` call `self.start()` on every duty write (`x10qbi.py:85`, `x10qbi.py:97`)
  — leaving it there would make every level change write the fan mode as well. The two write paths
  call `_configure_chip()` only, so the test matrix's `set_level_extra_calls: 11` stays valid.
- **`GenericX14Platform`**: the outlier — overrides `start()`, `check_fan_mode()` and `end()` in full
  and sets `ENFORCES_FULL_MODE = False`. See §2.

## 2. `GenericX14Platform` rewrite (`src/smfc/genericx14.py`)

Zone numbering is the crux: **manual/failsafe commands are 1-based, duty commands 0-based.** smfc's
zone IDs stay 0-based everywhere (config, controllers, other platforms); the +1 is applied only when
building a `0x2c 0x04` command, via a single helper so it is stated once.

| Operation | Command |
| --- | --- |
| set duty, zone z | `raw 0x30 0x70 0x66 0x00 <z> <duty%>` |
| read duty+temp | `raw 0x30 0x70 0x88 <sensorNum>` → first byte is duty, `ff` = unavailable |
| manual ON/OFF, zone z | `raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 <z+1> <0/1>` |
| read manual flag, zone z | `raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 <z+1>` |
| read failsafe flag, zone z | `raw 0x2c 0x04 0xcf 0xc2 0x00 0x02 <z+1>` |
| release all zones | `raw 0x30 0x70 0x66 0x02 0x00` |

- `FANCTL_COUNT`: `6` → `4`, i.e. zones **0-3**. §3 documents 1-zone boards (no specific fan table),
  2-zone boards (X14DBI-SP/-T, X14SBI-F/-TF, X14DBG-AP) and one 4-zone layout (X14SRG-TF in
  Performance); no board has more. The firmware itself accepts one index more — the duty command
  returns `0xCC` only *above* `0x04` — but no documented board has a 5th zone, and `6` matches
  neither number. Writes to a zone the board lacks are harmless (§4.3), so the cost of the tighter
  bound is only a rejected config on a hypothetical undocumented board.
- `start(zones)` — also the recovery path, so every step must tolerate being run again:
  1. `get_fan_mode()` for the snapshot cache only — **never** write the base mode.
  2. enable manual on each requested zone, then read the flag back; a zone that does not confirm
     `01` raises `RuntimeError` naming the zone — smfc is not in control of it and must not pretend
     otherwise.
  3. return `False` (no fan-mode write ⇒ no `fan_mode_delay` sleep).

  The platform never logs and never exits: it raises, and the caller decides (§3).

  **No separate §4.0 preflight.** An earlier draft read the manual flag of zone 0 first to detect a
  BMC without per-zone manual mode (H14 answers `0xC1`). Step 2 already covers it: on such a board
  the latch write and its read-back fail, `start()` raises, and `Service` exits 8 with the zone
  named. A dedicated preflight would only duplicate that — and with no `Log` in the platform it had
  nowhere to put its warning anyway. The error message should name
  `X14_MANUAL_FANCONTROL.md` §4.0 so an H14 user understands why.

  **The failsafe flag (`op 0x02`) is not read** — with nothing to report it to, it is a wasted BMC
  call per zone, and a failsafe zone is pinned at 100 % by the BMC, which is safe.
- `check_fan_mode(zones)`: read the manual flag of every zone. Any `00` → `LOST`
  (`detail="manual fan mode cleared in zone(s) [...]"`); an unreadable or erroring reply → also
  `LOST`, with `detail` naming the read failure (§1). The base fan mode is read too and carried in
  `ControlStatus.fan_mode` so the snapshot cache stays populated as today — but it plays no part in
  the decision on this platform.
- `end(zones, level)`: unchanged order — level write first, then release manual — but the release
  becomes the all-zones shortcut `0x30 0x70 0x66 0x02 0x00`, falling back to the corrected per-zone
  command if it errors. The existing `test_end` ordering assertion still applies.
- `get_fan_level(zone)`: `raw 0x30 0x70 0x88 <sensor>`, split the reply, take the **first** byte;
  `ff` → raise `ValueError` ("fan duty unavailable").
- `set_fan_level` / `set_multiple_fan_levels`: `0x30 0x70 0x66 0x00 <zone> <level>`.

### Zone → fan sensor map: configured, not inferred

`get_fan_level(zone)` needs one representative fan sensor per zone, and that mapping cannot be
derived from fan names — §3 gives zone 1's first sensor as `0x46` on X14SBI-F, `0x47` on X14DBI-SP,
`0x46` (FAN6, a *numbered* fan) on X14DBG-AP and `0x44` on X14SRG-TF, and only X14SRG-TF has zones
2-3 at all. Any name-based rule is wrong on at least one documented board.

So smfc does not infer it: **the user supplies it.**

- New setting `[Ipmi] x14_zone_sensors=0x41,0x46` — comma- or space-separated sensor numbers, list
  index = smfc zone, parsed like the existing `ipmi_zone=` (`Config.parse_ipmi_zones`,
  `config.py:341`). Values accept `0x` hex or decimal; each must be a byte (0-255).
- **Default when unset: `{0: 0x41}`.** Zone 0 is `0x41` on every board in §3, so the common case
  works out of the box.
- `get_fan_level(zone)` for a zone with no mapping raises
  `RuntimeError("IPMI zone N has no fan sensor configured (see [Ipmi] x14_zone_sensors=)")`.
  The control loop never reads levels back, so this only affects the startup DEBUG line and
  `smfc-client`. ⚠️ But the startup DEBUG loop is **currently unguarded** (`service.py:417`), so at
  `log_level=4` that raise would abort startup — see "Open topics" at the end of this document.
- The users who need it can read the numbers straight off their board with
  `ipmitool sdr elist full | grep -i fan` (second field, e.g. `41h`), or take them from §3.

This is a deliberate reversal of an earlier draft that measured the map by writing distinct probe
duties per zone and grouping fans by what they reported. Measuring worked, but it cost `sdr`
parsing, several seconds of deliberate fan movement at every startup, an ordering constraint against
the manual latch, a "probe once, not on recovery" guard, and four invented probe-level constants —
all to populate a read that feeds only a DEBUG line and `smfc-client`. One documented setting is a
better trade.

Consequence worth stating: the probe would have caught an `ipmi_zone` the board does not have (no
fan reports that zone's duty ⇒ smfc is writing duty that cools nothing, since §4.3 makes writes to a
nonexistent zone harmless *and* ineffective). Configuration cannot catch that, so on X14 a wrong
`ipmi_zone` fails silently — exactly as it already does on every other platform, where
`Config.parse_ipmi_zones()` accepts 0-100 and `GenericPlatform` writes it unchecked.

### Timing: what waits where

No new delay parameters. The existing ones apply, and the X14 sequence needs none of its own:

| After | Delay | Why |
| --- | --- | --- |
| fan mode write (non-X14 `start()`) | `fan_mode_delay` (default 10 s) | guide §4.1 asks for `sleep 8`; `Service` applies it when `start()` returns `True` |
| duty write | `fan_level_delay` (default 2 s) | unchanged, applied by `Ipmi.set_fan_level()` / `set_multiple_fan_levels()` |
| manual latch → read-back confirm | none | §4.2 issues the confirm read immediately after the set |
| manual latch → first duty write | none | the §4.5 watchdog runs them back-to-back |
| duty write → duty read | none | the duty register returns the commanded value; the 5-10 s in §4.4 is RPM spin-up, not duty |

X14 `start()` never writes the base fan mode, so it returns `False` and costs no `fan_mode_delay` —
recovery after drift is therefore fast, which matters because §1 of the guide notes automatic control
takes the fans back within ~1 s of the latch being cleared.

## 3. Call-site changes

- **`src/smfc/ipmi.py`**: drop `self.platform.start()` from `__init__` — the zone list is not known
  there, and the acquire has to happen after the DEBUG "old mode / old level" logging so those stay
  genuinely pre-change. `in_client` then governs only the fan-sensor readiness gate (update its
  docstring). No new `Ipmi` wrapper methods: `Service` already calls `self.ipmi.platform.end(...)`
  directly at `service.py:98`, so it calls `start()` the same way. `Ipmi.set_fan_mode()` stays as
  public API but loses its internal callers.
- **`src/smfc/service.py`**:
  - `run()`: delete the `if self.last_fan_mode != Ipmi.FULL_MODE: set_fan_mode(FULL)` block
    (`service.py:419-431`) and call `self.ipmi.platform.start(self._exit_zones())` instead —
    `_exit_zones()` already falls back to a config scan when the controllers do not exist yet, which
    is exactly this moment. Wrap it in `try/except (RuntimeError, ValueError)` → log the message and
    `sys.exit(8)`, matching how an `Ipmi` initialization failure is already handled a few lines above
    (`service.py:399-403`): this is where an X14 latch failure surfaces to the user. Sleep
    `config.ipmi.fan_mode_delay` when `start()` returns `True`. The DEBUG "old level in IPMI zone"
    loop keeps its current position and behaviour — with a static map there is no ordering
    constraint, and on X14 an unmapped zone simply logs as unavailable.
  - `_check_fan_mode()` **keeps its name** (as do `enforce_fan_mode=` and
    `fan_mode_enforced_total`): it calls `platform.check_fan_mode(zones)`, caches
    `status.fan_mode` into `self.last_fan_mode`/`last_fan_mode_at` as today, then
    then acts on `state` and `confirmed`:

    | `state` | `confirmed` | `enforce_fan_mode` | Action |
    | --- | --- | --- | --- |
    | `OK` | — | — | nothing |
    | `LOST` | `True` | on | `fan_mode_enforced_count += 1`, `platform.start(zones)`, re-apply `applied_levels` |
    | `LOST` | `True` | off | log `detail`, `sys.exit(11)` — real drift, today's behaviour |
    | `LOST` | `False` | on | `platform.start(zones)`, re-apply `applied_levels`, **no count** |
    | `LOST` | `False` | off | log `detail` and continue — nothing was observed to drift, so exiting 11 would be wrong |

    The re-apply loop is unchanged. The `confirmed=False` rows are the BMC-unreachable case: smfc
    still tries to re-acquire (the writes will fail too and land in the existing
    `except (RuntimeError, ValueError)` at `service.py:277-281`), but the metric stays clean.
  - Cache the controlled zone list once after the controllers are built rather than recomputing per
    poll.
- **`src/smfc/client.py:588-595`**: the "not in FULL mode" warning is misleading on X14, where the
  base mode is deliberately left alone. Gate the red warning on `platform.ENFORCES_FULL_MODE` (§1);
  the mode line itself keeps printing for every platform. **No change to `/snapshot` or `/metrics`.**

## 4. Tests

- **`test/test_platforms.py`**: `PlatformSpec` keeps `start_calls`/`end_calls` (their contents change)
  and gains `check_*` vectors; `start()` now takes a zone list, so the existing `test_start` grows a
  parameter. Add X14 cases for the corrected byte layouts,
  the 1-based/0-based zone split, the two-byte duty parse (` 64 2d` → 100), `ff` → `ValueError`, and
  the `OK`/`LOST` classifications including an unreadable flag. This is the file that encodes the wrong opcodes today
  (`_x14_get_cmd`/`_x14_set_cmd`, `_X14_START_CALLS`), so it must be rewritten alongside the source.
- **`test/test_fixtures.py`**: the fake `ipmitool` script (lines 200-212) answers `0x30 0x70 0x88`
  by arg count and `0x2c 0x04 …` unconditionally. Teach it the real layouts: `0x88` returns two
  bytes, `0x66 0x00` accepts a duty write, and the `0x2c` read ops return `01`/`00`.
- **`test/test_ipmi.py`**: `platform.start()` is no longer called from `__init__` (and `in_client`
  no longer gates it).
- **`test/test_config.py`**: parsing and validation of the new `x14_zone_sensors=` setting —
  unset (default `{0: 0x41}`), hex and decimal forms, comma and space separators, and a rejected
  out-of-range value.
- **`test/test_service.py`**: startup no longer writes FULL directly (tests at lines 66-93, 917-989);
  `_check_fan_mode` tests (from line 1004) keep their name but drive a stubbed platform returning
  each `ControlState`. Keep the exit-11 and `fan_mode_enforced_count` assertions.
- Test docstrings follow the existing "It contains the steps:" + ASSERT-bullet style.

## 5. Documentation

- `ARCHITECTURE.md`: lines 261, 317, 337 and 756 describe `start()`, the wrong X14 opcode and the
  6-zone claim; update those plus the class diagram to the widened `start()` + `check_fan_mode()`.
- `README.md`: chapter 5 platform table (line 335: "6 fan zones") and the X14 note at lines 195-203
  (the exit-level explanation stays correct, the mode handling does not).
- `config/smfc.conf` + README's embedded copy + README chapter 5: document
  `x14_zone_sensors=`, including how to read the numbers off a board
  (`ipmitool sdr elist full | grep -i fan`) and the per-board table from the X14 guide's §3.
- `CHANGELOG.md`: X14 fan control was non-functional; note the zone-count change 6 → 4 as a
  behaviour change.
- Move `X14_MANUAL_FANCONTROL.md` under `doc/` and link it from README chapter 5 as the reference for
  the raw commands (currently it is an untracked file in the repo root).

## 6. Verification

1. `pytest test/ -x` — full unit suite; the platform matrix is the primary gate.
2. Coverage for the touched modules should stay at the project's current level
   (`pytest --cov=smfc --cov-report=term-missing test/`).
3. `pylint src/smfc` — the repo lints clean today.
4. `test/run_smoke.sh` (and `test/automatic_smoke_runner/run_all.sh`) against the fake-`ipmitool`
   scenarios, including a `platform_name=generic_x14` scenario driven through startup → level
   changes → manual-flag loss → re-assert → `systemctl stop` exit level.
5. Hardware, if an X14 board is available: set `x14_zone_sensors=` from §3 for that board, then run
   the guide's §4.4 check once — drive zone 0 to 100 %, read a fan of zone 0 and one of zone 1, and
   confirm only the first moved. That validates both the setting and the zone map. Then confirm the
   manual flags hold across a poll, and stop the service and confirm the fans return to the base
   curve. Without hardware the X14 path stays flagged experimental in the README.

## Out of scope

- No watchdog/poll-interval change: the existing control-loop cadence is the poll, and `check_fan_mode()`
  runs in it.
- No change to `/snapshot`, `/metrics`, or the Grafana contract.
- No H14-specific platform class.
- No change to zone validation outside `GenericX14Platform`: `Config.parse_ipmi_zones()`
  (`config.py:352`) keeps its 0-100 range and `GenericPlatform` keeps `validate_input_range(zone,
  "zone", 0, 100)` (`generic.py:22,42`). Both are looser than any real board, but tightening them is
  a separate change with its own regression risk.

## Open topics (deferred, not part of this change)

- **The startup DEBUG level read is unguarded.** `service.py:417` calls `get_fan_level(zone)` inside
  the `log_level >= LOG_DEBUG` block with no `try/except`, so any BMC error there — a transient
  failure on any platform, or an X14 zone missing from `x14_zone_sensors=` — aborts startup before
  the control loop begins. Deferred to a separate refactor; until then, X14 users running at DEBUG
  should configure a sensor for every zone they use.
- **`ipmitool` has no timeout.** `Ipmi._exec_ipmitool()` calls `subprocess.run()` without
  `timeout=` (`ipmi.py:207`), so a wedged `/dev/ipmi0` or an unreachable remote BMC blocks the
  control loop indefinitely — no log line, no recovery. Not X14-specific, but more exposed after
  this change: X14 issues N+1 invocations per poll instead of 1, plus writes during enforcement.
  Suggested fix (~3 lines): a module-level timeout constant, `subprocess.TimeoutExpired` mapped to
  the same `RuntimeError` everything else raises, so a hang becomes a `LOST` result the loop retries.
- **Fan-level write errors kill the service.** `set_fan_level()` / `set_multiple_fan_levels()` in the
  control loop are likewise unguarded, so a transient `ipmitool` failure terminates smfc on every
  platform. Pre-existing, unchanged by this work, and worth its own decision about retry vs exit.
- **`ControlStatus.detail` is platform-composed user-facing text.** Acceptable (exception messages
  work the same way), but if `Service` should own all phrasing, `detail` would become structured
  data — the drifted-to mode, the list of cleared zones — that `Service` formats.
