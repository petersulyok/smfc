# Cover both X14/H14 BMC firmware stacks in the `generic_x14` platform

## Context

`doc/X14H14_MANUAL_FANCONTROL.md` supersedes the two per-generation guides (`X14_MANUAL_FANCONTROL.md`
and `H14_MANUAL_FANCONTROL.md`, both deleted). It documents that Supermicro's 14th generation ships
**two unrelated BMC firmware stacks**, and that the split does not follow the board generation:

- **OpenBMC** (`openbmc-phosphor`) — most X14 boards, *plus* `H14SHM`.
- **ATEN** (the firmware line Supermicro shipped through X9–X13) — all other H14 boards, *plus* the
  SoC boards `X14SDW` and `X14SDV`.

The BMC product name therefore cannot decide which command set applies, and the current code decides
exactly that way:

- `create_platform()` routes on the `X14` prefix, so `X14SDW`/`X14SDV` receive the OpenBMC manual
  latch, the BMC answers `0xC1`, and `smfc` exits 8 on boards that are perfectly controllable.
- The CHANGELOG entry added on this branch deliberately excludes `H14` from auto-detection, which
  sends `H14SHM` — an OpenBMC board — to `GenericPlatform` for the same wrong reason.

Two further facts change the shape of the work:

**The ATEN duty commands are byte-for-byte `GenericPlatform`'s.**

```
GenericPlatform.get_fan_level(z)      raw 0x30 0x70 0x66 0x00 <z>          generic.py:18
ATEN duty read (Part 4.2)             raw 0x30 0x70 0x66 0x00 <z>

GenericPlatform.set_fan_level(z, d)   raw 0x30 0x70 0x66 0x01 <z> <d>      generic.py:25
ATEN duty write (Part 4.2)            raw 0x30 0x70 0x66 0x01 <z> <d>
```

This is not a coincidence — ATEN *is* the X9–X13 firmware line, so `generic` has been speaking it all
along. It also explains the field reports from H14 owners: the duty commands are correct, the **lever**
is wrong. `smfc` sets FULL fan mode, but Part 4.1 states that the automatic control loop re-asserts its
own duty in every fan mode; only the global bypass flag suspends it. Hence "smfc writes the level, the
fans drift back within a second".

**The testing status is the reverse of what the previous revision assumed.** Per Part 5.3, the ATEN
path — bypass, duty write, read-back and release — is *confirmed on H14 hardware*, while the OpenBMC
duty write is *not yet confirmed on any board*. Shipping only the OpenBMC half would ship only the
unverified half.

Outcome: `platform_name=generic_x14` becomes a platform **family** covering both stacks, with the
concrete implementation chosen by a runtime probe instead of by board name. H14 boards become
controllable for the first time.

### What has already landed on this branch

The previous revision's §1 and §3 — the widened `Platform` contract — are **implemented**:
`ControlState`, `ControlStatus`, the concrete `start()`/`check_fan_mode()`/`end()`/`get_fan_mode()`/
`set_fan_mode()` in the ABC, `ENFORCES_FULL_MODE`, the `Service._check_fan_mode()` state table, and
the `x14_zone_sensors=` setting. This revision builds on that and does not revisit it.

### Decisions taken with the user

- **Both stacks in this change**, not OpenBMC first and ATEN later.
- **Two concrete classes**, both in `src/smfc/genericx14.py`; no shared X14 base class.
- **`X14AtenPlatform` subclasses `GenericPlatform`** and inherits its duty read and duty write,
  overriding only the write's lower bound (§4.5).
- **One configuration name.** `platform_name=generic_x14` selects the family; the probe selects the
  class. There is no way to force a stack from the configuration file.
- **Exit applies `exit_level`, then always releases** the latch or bypass — including when
  `exit_level=-1`.
- **The ATEN frozen-zone hazard is documented in `README.md`**, not handled at runtime: no warning
  log, and no driving of zones the user did not configure.

---

## 1. Stack detection

### 1.1 The probe

The guide's Part 1 read is the authority, and it is the only command that is safe to send to a board
whose stack is unknown:

```
raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 0x01     # read the manual-mode flag of zone 1
```

| Reply | Stack |
| --- | --- |
| a data byte (`00` or `01`) | OpenBMC |
| completion code `0xC1` | ATEN |
| anything else | undetermined — **fail** |

### 1.2 🔴 There is no fallback branch

Part 1.3: `0x30 0x70 0x66 0x00 <zone>` is a duty **read** on ATEN and a **truncated duty write** on
OpenBMC. The OpenBMC handler accepts payloads of two *or* three bytes, so the short form is not caught
by a length check — it executes as a duty write with no duty value. Guessing the stack does not return
an error; it moves fans.

Consequently, "try OpenBMC, fall back to ATEN" is not an acceptable implementation, and neither is
treating any error as ATEN. `Ipmi._exec_ipmitool()` (`ipmi.py:213-217`) flattens every failure into

```python
raise RuntimeError(f"ipmitool error ({r.returncode}): {r.stderr}.")
```

so an unreachable BMC, a wedged `/dev/ipmi0` and a genuine `0xC1` are indistinguishable by type. Only
`rsp=0xc1` means ATEN.

**Implementation:** give `_exec_ipmitool()` a structured exception rather than matching text.

```python
class IpmiError(RuntimeError):
    """An ipmitool failure, carrying the IPMI completion code when the BMC returned one."""
    completion_code: Optional[int]      # e.g. 0xC1; None when ipmitool failed for another reason
```

`ipmitool` prints the code in its failure line (`… cmd=0x4 rsp=0xc1): Invalid command`), so
`_exec_ipmitool()` parses `rsp=0x..` out of `stderr` once, in one place, and every caller keeps
catching `RuntimeError` as it does today. Matching the string at the call site would work but leaves a
latent trap: a future change to the error message silently turns a fatal condition into a wrong-stack
guess.

Detection failure is fatal with a message naming the guide:

```
Cannot determine the BMC fan control stack (see doc/X14H14_MANUAL_FANCONTROL.md, Part 1): <reason>
```

### 1.3 Where detection runs

In `create_platform()` (`src/smfc/platform_factory.py`), not lazily inside the platform:

- `Ipmi.__init__` calls the factory immediately after parsing `mc info` (`ipmi.py:139`), so the BMC
  has just been proven responsive — the ambiguous "BMC unreachable" case is largely excluded by
  construction.
- Returning the correct *class* keeps `type(platform).__name__` honest everywhere it is already
  displayed: the CONFIG log line (`ipmi.py:151`), `smfc-client`'s `Platform :` line
  (`client.py:584`), and the snapshot.
- A lazy probe would leave the class name unable to tell the user which stack was found, and would
  put a `self._stack` guard in every method.

The factory resolves the **family** first, then probes within it:

```python
def create_platform(platform_name, exec_ipmitool, zone_sensors=None) -> Platform:
    if platform_name in (PlatformName.GENERIC_X14,) or platform_name.startswith(("X14", "H14")):
        return _create_x14_platform(platform_name, exec_ipmitool, zone_sensors)
    ...                                  # unchanged: generic_x9 / X10QBi / generic + prefixes
```

No OEM command is ever sent to a board outside the family, so X9–X13 auto-detection is untouched.
`H14` prefixes route into the family again, **reverting the CHANGELOG entry made on this branch**.

---

## 2. Class layout (`src/smfc/genericx14.py`)

Two concrete classes. There is no shared X14 base class: with the duty methods coming from
`GenericPlatform` on one side and being genuinely X14-specific on the other, the two stacks share only
`ENFORCES_FULL_MODE = False`, "read the base fan mode but never write it", and the release opcode.
Three constants do not justify a base class, and the previous revision's own argument applies — an
abstraction that exists only to hold constants is where wrong opcodes hide.

```python
class X14OpenBmcPlatform(Platform):        # today's GenericX14Platform body, renamed
class X14AtenPlatform(GenericPlatform):    # duty commands inherited, lever replaced
```

| | `X14OpenBmcPlatform` | `X14AtenPlatform` |
| --- | --- | --- |
| acquire | per-zone latch `0x2c 04 cf c2 00 01 <z+1> 01`, read back | global bypass `0x30 70 66 02 01` |
| scope of the lever | only the latched zones | every zone on the board |
| lever readable | yes | **no** |
| "still in control?" | read the manual flag per zone | compare a duty read-back with `accepted()` |
| duty write | `0x30 70 66 **00** <z> <d>` | inherited from `GenericPlatform` |
| duty read | `0x30 70 88 <sensor>` → 2 bytes | inherited (`0x30 70 66 00 <z>`) |
| zone numbering | manual 1-based, duty 0-based | 0-based throughout |
| duty range | 0–100 | 5–100 on the PWM path, unclamped on the percent path — `smfc` clamps to ≥ 5 (§4.5) |
| duty read-back | exact (a separate read command) | one of two values, board-dependent (§4.2) |
| `x14_zone_sensors=` | required | unused |
| base fan mode | read only | read only |
| `ENFORCES_FULL_MODE` | `False` | `False` |

`X14AtenPlatform(GenericPlatform)` is the repository's first two-level platform hierarchy — every
platform subclasses `Platform` directly today. It is justified because the relationship is real: the
same firmware, the same duty commands, a different lever. The alternative, copying those methods out
of `generic.py`, reintroduces exactly the duplication this refactor set out to remove. The one
override (§4.5) is a bound on an argument, not a different command.

The class name `GenericX14Platform` disappears. `PlatformName.GENERIC_X14` stays as the configuration
value and is no longer a one-to-one mapping to a class, so the `platform_factory` dictionary lookup is
replaced by the family resolution in §1.3.

---

## 3. `X14OpenBmcPlatform`

The body of today's `GenericX14Platform` is correct and is kept: the `_manual_zone()` helper that
applies the 1-based offset in exactly one place, `start()`'s latch-and-read-back, the per-zone flag
check in `check_fan_mode()`, the two-byte duty parse with `ff` → `ValueError`, `FANCTL_COUNT = 4`, and
the configured zone → fan sensor map. Changes:

- **Rename** to `X14OpenBmcPlatform`.
- **The H14 error message is obsolete.** `start()` currently says a zone that refuses the latch means
  an H14 board and points at the old guide's §4.0 preflight. Detection now guarantees the class
  matches the board, so a refusal means the zone does not exist or the BMC rejected the command:

  ```
  IPMI zone {zone} did not accept manual fan mode
  (see doc/X14H14_MANUAL_FANCONTROL.md, Part 3.5).
  ```

- **All guide references renumber.** The old §3 board tables are **Part 5.1**, the old §4 procedure is
  **Part 3**, and the file is `doc/X14H14_MANUAL_FANCONTROL.md`. Affected: the class docstring
  (`genericx14.py:24`) and the two `start()` references (`genericx14.py:80,97`).
- `x14_zone_sensors=` remains documented against the Part 5.1 per-board table, with one addition
  from the guide's Part 3.5: **the zone map belongs to the active base fan mode, not to the board.**
  Selecting a base mode makes the BMC load a fan table, and that table is what defines how many zones
  exist and which fans are in each — on most boards the everyday modes load a single zone holding
  every fan, while Performance and Silent carry a three-zone table and some boards override the
  common modes with a board-specific two-zone one. So a `x14_zone_sensors=` that is correct today
  becomes wrong if anyone changes the fan mode from the web UI or Redfish, and `smfc` cannot detect
  that: it reads the mode but the mode name does not imply the table (Part 3.4 — an unsupported mode
  is accepted silently and reads back correctly while a different table is loaded).
- Consequently `ControlStatus.fan_mode` is reported as read and nothing is inferred from it. It is a
  snapshot field, never an input to the zone map.

---

## 4. `X14AtenPlatform`

### 4.1 `start(zones)`

```
raw 0x30 0x70 0x66 0x02 0x01        # suspend the automatic loop, all zones
```

- One command, global; the zone list is recorded for §5's release but not otherwise used.
- Returns `False` — the base fan mode is never written, so no `fan_mode_delay` is due.
- 🔴 **Never write the base fan mode.** Part 4.1: the mode is persistent while the bypass is not, so a
  board left in Full Speed comes back at 100 % after a BMC restart with nothing to stop it.
- `0xD4` means System Lockdown is enabled; the raised message must say so, because the fix is in the
  BMC web UI and nothing in `smfc` can work around it.
- 🔴 **`0xCC` here means this firmware build has no fan-duty sub-command at all.** Part 4.6: on some
  ATEN builds every `0x30 0x70 0x66` command returns `0xCC` while `0x30 0x45` still works. The `0xC1`
  probe of §1.1 identifies the *stack*, not that duty control exists, so this is the first point where
  such a build can be recognised. It needs its own fatal message, because the only recourse is a
  firmware change and a generic `ipmitool error (…)` sends the user hunting the wrong thing:

  ```
  This BMC build implements no IPMI fan duty control (0x30 0x70 0x66 rejected with 0xCC); only the
  base fan mode can be set (see doc/X14H14_MANUAL_FANCONTROL.md, Part 4.6).
  ```

- Idempotent by construction, which is what the recovery path in `Service._check_fan_mode()` needs.

### 4.2 `check_fan_mode(zones)` — the read-back watchdog

The bypass flag is **write-only**, so there is no flag to poll. The detector is the guide's Part 4.5
comparison: read each zone's duty and compare it against what we wrote — but the read-back is not one
predictable value.

🔴 **There is no single expected read-back on this stack.** Part 4.4: the truncation formula was
verified on the AST2600 hardware monitor the H14 boards use, and the **X14SDW / X14SDV** firmware
carries a **second duty path** that stores the percentage itself and reads it back **exactly**, with no
truncation and no 5 % clamp. A configuration byte picks the path when the BMC starts, so *the board
name does not tell you which one is active* and neither does anything `smfc` can read. Part 4.1 says
the same thing in one line — "measure your board once".

A single computed expectation is therefore wrong on one of the two paths, and getting it wrong is not
cosmetic in either direction:

- computing the truncated value on a percent-path board makes **every** duty that is not a multiple of
  20 mismatch on **every** poll — a permanent `LOST`, re-arming the bypass and logging control loss
  forever;
- comparing against the written value on a PWM-path board does the same, one count the other way.

The two paths never differ by more than one count, so the comparison is against an **accepted set**
rather than a value. This is self-calibrating: no probe write, no extra IPMI traffic, no per-board
table to maintain.

```python
@staticmethod
def accepted(level: int) -> set[int]:
    """Duty bytes the BMC may report back after `level` was written (Part 4.4).

    ATEN firmware has two duty paths and the board name does not say which is active: an
    8-bit PWM path that clamps to 5-100 and truncates twice, and a path that stores the
    percentage exactly. The two never differ by more than one count.
    """
    pwm = max(5, min(100, level))
    return {((pwm * 255) // 100) * 100 // 255, pwm, max(0, min(100, level))}
```

On the PWM path: `50 → 127 → 49`, `20 → 51 → 20`, `100 → 255 → 100`, `0 → 12 → 4` — exact at multiples
of 20, exactly one low elsewhere. On the percent path the write itself is returned. `accepted()` holds
both, plus the unclamped value for the `min_level=0` case that `config.py:787` permits.

The cost is that a genuine takeover landing within one count of our own value is missed for a single
poll. That is not a real exposure: the automatic curve keeps moving, so the next poll sees it.

- **The map of accepted values lives on the platform**, recorded by `set_fan_level()` and
  `set_multiple_fan_levels()` from the level they actually wrote (post-clamp, §4.5). It is not read
  out of `Service.applied_levels`: the platform must not depend on its caller's bookkeeping.
- **Before the first duty write there is nothing to compare**, so the first call reports `OK`.
  `Service` writes levels on every iteration, so that window is one poll.
- **The read happens before this pass's write** (Part 4.5): reading straight after our own
  write returns our own value regardless of the bypass, because the automatic loop needs about a
  second to overwrite.
- **A zone reading `64` that we did not ask for is most likely a fan-failure trip**, not a lost
  bypass — but the two boards differ and `smfc` cannot tell which it is on. Part 5.2: on the H14
  boards the fan-failure check runs *before* the bypass check, so a trip forces 100 % on every tick
  and re-arming can never win it back; on **X14SDW / X14SDV** the bypass is checked first and holds
  *through* a fan failure, so a pinned zone there has some other cause. Count consecutive occurrences
  per zone, and from the third on make `ControlStatus.detail` name the likely cause without asserting
  it:

  ```
  IPMI zone 0 is pinned at 100% and is most likely a fan failure rather than a lost bypass; on
  boards where fan failure outranks the bypass, re-arming cannot recover it (see
  doc/X14H14_MANUAL_FANCONTROL.md, Part 4.6 and Part 5.2).
  ```

  Without this the log repeats "control lost" forever and points the user at the wrong thing.
- **The base fan mode is read too**, purely to populate `ControlStatus.fan_mode` for the snapshot
  cache, exactly as the OpenBMC class already does. It plays no part in the decision.

Mapping onto the existing contract, with no extension to `ControlStatus`:

| Observation | Result |
| --- | --- |
| every zone reads a value in its accepted set | `OK` |
| a zone reads something else | `LOST`, `confirmed=True` — the automatic loop resumed |
| a read fails | `LOST`, `confirmed=False` — the BMC could not be read |

`Service._check_fan_mode()` (`service.py:260-287`) is unchanged, and its "re-acquire, then re-apply
`applied_levels`" recovery *is* the guide's Part 4.5 loop.

### 4.3 `end(zones, level)`

Apply the exit level (unless `level < 0`, see §5), then release the bypass with
`raw 0x30 0x70 0x66 0x02 0x00`. The order matters only in that releasing first would make the level
write pointless.

### 4.4 The frozen-zone hazard — documented, not handled

The bypass is **global**. A zone the user did not list in `ipmi_zone=` is bypassed along with the rest
and sits **frozen at its last duty with nothing regulating it** — unlike OpenBMC, where an unlatched
zone keeps running under automatic control. This cannot be fixed in code: there is no reliable way to
learn how many zones a board has (several ATEN boards accept any zone byte silently, Part 5.2), and
driving zones the user did not configure would make `smfc` move fans nobody asked it to move.

It is therefore a documented warning in `README.md` (§8), telling ATEN users to list every zone their
board has.

### 4.5 🔴 Never write a duty of 0

`X14AtenPlatform` clamps every duty write to **≥ 5 %**, overriding `GenericPlatform.set_fan_level()`
and `set_multiple_fan_levels()` for that one bound. `Config` permits `min_level=0` (`config.py:787`),
and on the PWM path that is harmless — the firmware clamps it to 5 % and reports 4. Part 4.4 🔴 states
that the **percent path has no floor**, so on X14SDW / X14SDV a written `0x00` may reach the fans as a
real 0 % — with the BMC's own thermal loop suspended by our bypass and nothing else regulating them.

This is a safety clamp, not a read-back concern: `accepted()` (§4.2) already tolerates either path, so
the clamp exists purely so that a legal configuration cannot stop the fans on a board whose duty path
we cannot identify. The clamped value is what `accepted()` is asked about, so the two stay consistent
by construction.

`X14OpenBmcPlatform` needs no such clamp: its duty range is a documented 0–100 and it does not suspend
a thermal loop globally.

---

## 5. Release must not depend on `exit_level`

A defect on this branch, affecting both stacks. `Service.exit_func()` (`service.py:97`) calls
`platform.end()` only when `exit_level != EXIT_LEVEL_NONE` **and** the zone list is non-empty:

```python
if level != Config.EXIT_LEVEL_NONE and zones:
    self.ipmi.platform.end(zones, level)
```

On FULL-mode platforms `end()` is only a level write, so skipping it is harmless. On X14/H14 it means
the manual latch or the global bypass is **never released**: the fans stay frozen at whatever duty
`smfc` last wrote, permanently, with no thermal regulation behind them. Part 4.1 states it directly —
*"If your controller dies, the fans freeze at their last duty — they do not fall back to automatic.
Always release the bypass on exit."*

The fix does not add a method to the `Platform` contract:

- `exit_func()` calls `platform.end(zones, level)` **unconditionally** whenever `self.ipmi` exists,
  passing `Config.EXIT_LEVEL_NONE` (`-1`) straight through instead of branching on it.
- `Platform.end()` in the ABC writes the level only when `level >= 0`. This is a no-op behaviour change
  for `generic`, `generic_x9` and `X10QBi`.
- Both X14 classes record in `start()` which zones they latched, so the release covers exactly those
  and no longer depends on `_exit_zones()` returning the right list during interpreter shutdown.
- The existing log lines are kept, including the `no IPMI zone was controlled` / `exit_level=-1`
  messages — with their wording adjusted so they no longer imply that nothing at all was done.

**State this plainly in the user documentation:** on both X14/H14 stacks the exit level is a
*transition*, not a resting state. Within about a second the BMC's own curve takes over — and that
curve regulates on CPU and system sensors only, so drive temperatures are not part of it.

---

## 6. Call-site changes

- **`src/smfc/platform_factory.py`** — family resolution and the probe (§1.3); `H14` prefix restored;
  the `PlatformName.GENERIC_X14 → class` dictionary entry replaced.
- **`src/smfc/ipmi.py`** — `IpmiError` with the parsed completion code (§1.2). No other change; the
  removal of `platform.start()` from `__init__` already landed.
- **`src/smfc/service.py`** — the unconditional `end()` of §5. `run()` and `_check_fan_mode()` are
  otherwise unchanged: the state table already handles everything both stacks report.
- **`src/smfc/client.py`** — no change. The `ENFORCES_FULL_MODE` gate on the "not in FULL mode"
  warning (`client.py:592`) already covers both new classes, and `Platform :` now prints the detected
  stack for free.
- **`src/smfc/config.py`** — no parsing change, and in particular **no new validation of
  `min_level`**. The 0–100 range stays as it is; the ≥ 5 % floor is a property of one platform, not of
  the configuration, and it is applied in `X14AtenPlatform` (§4.5). `parse_x14_zone_sensors()`
  (`config.py:361`) stays as it is; only its documentation changes, to say the setting is
  **OpenBMC-only** and scoped to the active base fan mode. The setting is unreleased, so renaming it
  is still free — the recommendation is to keep the name.

---

## 7. Tests

- **`test/test_fixtures.py`** — the fake `ipmitool` must model **both** stacks, selected by an
  environment variable, and answer the Part 1 probe accordingly. It currently conflates them: `0x66
  0x00` with five arguments returns a level while six arguments is a write (lines 193-199). That
  ambiguity is the real hardware behaviour and must become stack-dependent, so that an OpenBMC
  scenario treats the short form as a write and an ATEN scenario treats it as a read.
  The ATEN side needs a **second switch for the duty read-back path** — PWM truncation or exact
  percentage (Part 4.4) — because that is the difference §4.2's `accepted()` exists to absorb, and a
  fixture that models only one path cannot fail a regression that reintroduces a single expectation.
- **`test/test_platforms.py`** — `PlatformSpec` gains a second X14 row. The existing `_x14_*` command
  builders become the OpenBMC ones; the ATEN row reuses the `_generic_*` builders, which is itself an
  assertion that the two command sets are identical. New vectors:
  - detection: data → `X14OpenBmcPlatform`, `0xC1` → `X14AtenPlatform`, any other error → raises;
  - `accepted()` from Part 4.4, asserted as a set per level: `50 → {49, 50}`, `20 → {20}`,
    `100 → {100}`, `0 → {4, 5, 0}`, `120 → {100}` — the PWM read-back, the clamped write and the raw
    write, so both duty paths pass;
  - `check_fan_mode()` classification driven from **both** read-back paths: for each level, the PWM
    value → `OK` *and* the exact value → `OK`; a value outside the set → `LOST/confirmed=True`; a read
    error → `LOST/confirmed=False`; and the fan-failure wording after three consecutive pinned passes;
  - the §4.5 write clamp: a configured level of 0 reaches the BMC as `0x05`, never `0x00`;
  - `start()` translating `0xCC` into the "no fan-duty sub-command" message of §4.1, distinct from the
    `0xD4` System Lockdown message;
  - `end()` with `level=-1`: releases without writing a level.
- **`test/test_service.py`** — `exit_func()` now calls `end()` with `-1` instead of skipping it;
  the existing exit-level assertions are extended rather than replaced.
- **`test/run_smoke.sh`** and `test/automatic_smoke_runner/` — one scenario per stack, each driven
  through startup → level changes → control loss → re-assert → `systemctl stop` exit level.
- Test docstrings follow the existing "It contains the steps:" + ASSERT-bullet style.

---

## 8. Documentation

- **`README.md`** chapter 5 — the platform table and the X14 note: `generic_x14` covers both stacks
  and selects by probe; `x14_zone_sensors=` is OpenBMC-only; the exit level is a transition on both
  stacks; and the 🔴 **frozen-zone warning** of §4.4 for ATEN boards. Two additions from the current
  guide: on ATEN boards `min_level=0` is silently raised to 5 % (§4.5), and on OpenBMC boards
  `x14_zone_sensors=` is only valid for the base fan mode that was active when it was measured — a
  fan-mode change from the web UI or Redfish reshapes the zones and the map must be re-probed
  (Part 3.5).
- **`CHANGELOG.md`** — revert the "H14 BMC product names are not auto-detected any more" entry; add
  the dual-stack detection, the H14 boards becoming controllable, and the `exit_level=-1` release fix
  (a behaviour change on X14).
- **`ARCHITECTURE.md`** — line 327 and the class diagram: two X14 classes, the probe, the widened
  `end()` semantics.
- **`config/smfc.conf`** and its embedded copy in `README.md` — `x14_zone_sensors=` marked
  OpenBMC-only and mode-scoped, pointing at Part 5.1 and Part 3.5; the `min_level=` comment notes the
  ATEN 5 % floor.
- **Repoint every dangling `doc/X14_MANUAL_FANCONTROL.md` link** — the file is deleted:
  `README.md:337,344,746`, `CHANGELOG.md:11,12`, `ARCHITECTURE.md:327`, `config/smfc.conf:36`,
  `src/smfc/genericx14.py:24,80,97`. All become `doc/X14H14_MANUAL_FANCONTROL.md` with the new Part
  numbers (board tables: Part 5.1 / 5.2; OpenBMC procedure: Part 3; ATEN procedure: Part 4).

---

## 9. Verification

1. `pytest test/ -x` — the platform matrix is the primary gate.
2. `pytest --cov=smfc --cov-report=term-missing test/` — coverage of the touched modules stays at the
   project's current level.
3. `pylint src/smfc` — the repository lints clean today.
4. `test/run_smoke.sh` and `test/automatic_smoke_runner/run_all.sh`, with the two new stack scenarios.
5. **ATEN hardware** (available — an H14 board, i.e. the PWM duty path): run the guide's Part 4.4
   spot-check once — write a duty that is not a multiple of 20, wait ~3 s, read it back and confirm
   the value is in `accepted()`; then confirm the level holds across several polls, and that
   `systemctl stop smfc` returns the fans to the automatic curve.
   Per Part 5.3 this confirms the ATEN path **on H14 only**. `X14SDW` / `X14SDV` are untested and
   their read-back path is explicitly *unknown* — that is precisely why §4.2 compares against a set
   instead of a computed value, so no board-specific verification is owed before shipping.
6. **OpenBMC hardware** (if a board is available): set `x14_zone_sensors=` from Part 5.1, drive zone 0
   to 100 %, and confirm a zone-1 fan did not move — this validates the setting and the zone map at
   once. Until that is done the OpenBMC path stays flagged experimental in `README.md`.

## Out of scope

- No `/snapshot`, `/metrics` or Grafana contract change.
- No zone-validation change outside the X14 classes: `Config.parse_ipmi_zones()` keeps its 0-100 range
  and `GenericPlatform` keeps its 0-100 check.
- **Whether the ATEN bypass also improves X13 and older boards is untested and stays out.** The same
  firmware line runs there, so `0x66 0x02 0x01` may well work — but `generic` with FULL fan mode is
  proven on those boards and changing it is a separate decision with its own regression risk.
- No H14-specific platform class: H14 boards are ATEN or OpenBMC like any other, and the probe says
  which.

## Open topics (deferred, not part of this change)

- **The startup DEBUG level read is unguarded** (`service.py:417`): any BMC error there aborts startup
  before the control loop begins.
- **`ipmitool` has no timeout.** `subprocess.run()` is called without `timeout=` (`ipmi.py:207`), so a
  wedged `/dev/ipmi0` blocks the control loop indefinitely. More exposed after this change: the ATEN
  watchdog adds one read per zone per poll.
- **Fan-level write errors terminate the service** — unguarded in the control loop, on every platform.
- **`ControlStatus.detail` is platform-composed user-facing text**, now including the fan-failure
  wording of §4.2.
