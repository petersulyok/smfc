# Correct and harden the `generic_x14` OpenBMC implementation

> **Revision 3.** Supersedes the dual-stack plan, which is implemented. This revision is about the
> OpenBMC half being built on hardware facts that turned out to be wrong, and about the fact that
> nothing in the repository noticed.

## Context

The dual-stack refactor landed: `platform_name=generic_x14` is a platform family, `create_platform()`
probes for the stack instead of routing on the board name, `X14OpenBmcPlatform` and `X14AtenPlatform`
both exist, `end()` releases the lever on every exit path, and `Service` drives it all through
`ControlState`/`ControlStatus`. None of that changes here.

What changed is the source material. Two revisions of `doc/X14H14_MANUAL_FANCONTROL.md` on
2026-08-27…29, both driven by measurements on a real X14SAE-F, corrected three facts the OpenBMC
implementation was built on:

| Was | Is | Source |
| --- | --- | --- |
| OEM manual/failsafe commands on netfn `0x2c` | netfn **`0x2e`** (OEM/Group), IANA ID `cf c2 00` | Part 3.1 |
| the flag read replies with one byte | replies **`cf c2 00 <flag>`** — the flag is the **last** byte | Part 3.1, 3.6 |
| OpenBMC writes duty with `0x66 **0x00** <z> <d>` | `0x66 **0x01** <z> <d>`; `0x66 0x00 <z>` is a **read** on both stacks | Part 1.3, 3.1 |

The third is the severe one. `X14OpenBmcPlatform.set_fan_level()` sends the read selector with a
trailing duty byte the firmware ignores, so **smfc never sets a duty on an OpenBMC board**. It latches
manual mode correctly and then leaves every zone frozen wherever the automatic curve last put it. The
first two make it worse: the netfn is rejected outright, so the Part 1 probe reads `0xC1` on a real
OpenBMC board and classifies it as ATEN — after which smfc drives it with the ATEN command set.

The ATEN half is untouched by all of this. ATEN was always `0x66 0x00` read / `0x66 0x01` write, which
is what `X14AtenPlatform` inherits from `GenericPlatform`, and that path is confirmed on H14 hardware.
The doc revision did not discover new ATEN behaviour — it discovered that OpenBMC does what ATEN does.

### The finding that actually matters

Those bytes were wrong for the entire life of the branch, and the full test suite was green the whole
time. `test_platforms.py:62-72` builds the expected argv the same way the implementation builds it, and
`check_smoke.py:209-213` greps the log for command strings. Both are mirrors: they can only confirm
that smfc agrees with itself, so a wrong opcode passes as long as both sides are wrong together.

So the defect was never `0x2c`. It was that a hardware fact lived as a bare literal in two files, with
no link to the doc section that justified it and no test that could contradict it. This revision fixes
the bytes, and then closes that gap — because these facts have now been revised twice in three days and
there is no reason to assume they are finished.

### Why this is not a rewrite

Both doc revisions changed opcodes, a reply shape and a selector. Neither touched the lifecycle, the
1-based/0-based isolation in `_manual_zone()`, the latch bookkeeping in `latched_zones`, the
read-back confirmation in `start()`, or the release in `finally`. An abstraction that absorbs two
rounds of "the hardware facts were wrong" without deforming is the correct abstraction; rewriting would
discard the validated part and re-derive the part that keeps moving.

`X14AtenPlatform` is not touched in any phase below.

### Decisions taken with the user

- Fix in place, phase by phase; no rewrite, no merging of the two platform classes.
- Correctness first (§1), then the test gate (§2), then behaviour (§3), then removal (§4).
- Each phase is a standalone commit that leaves the branch green.

### Decisions taken with the user, continued

- **The OpenBMC duty floor is 5 %**, the same clamp `X14AtenPlatform` applies, so both X14 stacks behave
  identically. It guards against a written `0x00` stopping the fans of a latched zone with nothing
  regulating them; it does not second-guess a user who deliberately wants a very low duty.
- **A failsafe trip is reported as `LOST`** with its own `ControlStatus.detail`, not as a new
  `ControlState`. `ControlState` keeps its two values and the base-class contract is untouched. The cost is
  accepted: `Service` re-acquires on every poll and re-acquiring cannot clear a failsafe trip, so the
  detail must name the cause and must not repeat on every poll - `X14AtenPlatform.PINNED_REPORT_AFTER`
  is the precedent.
- **§4 is in scope**: `x14_zone_sensors` is removed in this change, while doing so is still free.

---

## 1. Phase 0 — Correct the wire format

Pure bug fix. No design change, no new behaviour. Lands first so the later phases have something
correct to build on.

| File | Change |
| --- | --- |
| `src/smfc/genericx14.py:40` | `OEM_PREFIX` netfn → `"0x2e"` |
| `src/smfc/genericx14.py:72` | `int(r.stdout, 16)` → `int(r.stdout.split()[-1], 16)` |
| `src/smfc/genericx14.py:33` | `FANCTL_COUNT` `4` → `5` (interim — §3 removes the constant) |
| `src/smfc/genericx14.py:203,212` | duty selector `"0x00"` → `"0x01"` |
| `src/smfc/platform_factory.py:18` | `X14_STACK_PROBE` netfn → `"0x2e"` |
| `src/smfc/platform_factory.py:55` | `r.stdout.split()[0]` → `r.stdout.split()[-1]` |

`FANCTL_COUNT = 5` because Part 3.2 rejects a duty zone above `0x04`, and Part 5.1 documents an
X14SAE-F with five zones. It is still a guess from one board's table — the same category of statement
as `0x2c` was — which is why §3 replaces it with a probe rather than leaving it as a better constant.

Tests move mechanically: `test_platforms.py:62,67,72`, `test_platform_factory.py:56`,
`test_fixtures.py:280-303`, `check_smoke.py:209-213` and `automatic_smoke_runner/README.md:97`.

Two fixture changes that are **not** mechanical and carry the phase:

- the emulated flag reply becomes the four-byte `cf c2 00 <flag>` form, so the `split()[-1]` fix is
  actually exercised rather than asserted;
- the `0x66` branch splits by selector — `0x00` returns a duty and writes nothing, `0x01` stores one.
  Until it does, the fixture cannot tell a read from a write, which is precisely how the selector bug
  survived.

**Verification:** the existing suite goes green. This phase provably cannot yet catch the class of bug
it is fixing — that is §2's job, and it is the reason §2 is not optional.

---

## 2. Phase 1 — Make the fixture a BMC model, and make it the gate

The highest-value phase in this plan.

`test_fixtures.py` already keeps real state for the manual latch (`MANUAL_FLAG_FILE`) and the ATEN duty
register (`ATEN_DUTY_FILE`). Finish it into a behavioural model of the OpenBMC stack:

- a per-zone duty register and a per-zone manual flag;
- 🔴 **the rule from Part 3.6: a duty write only sticks while that zone's flag is latched.** Otherwise
  the model overwrites it with a moving "automatic curve" value. This single rule is what turns the
  fixture from a command echo into a model — it is the difference between "smfc sent something" and
  "the fans are where smfc wants them";
- a per-zone failsafe flag the test can set, pinning that zone at 100 % and ignoring duty writes;
- zones above the modelled count return `0xCC` for duty and an error for the manual flag.

Then a behavioural test class that asserts outcomes rather than calls:

| Scenario | Assertion |
| --- | --- |
| `start([0, 2])` | zones 0 and 2 latched, zone 1 untouched and still automatic |
| `set_fan_level(2, 40)` | `get_fan_level(2) == 40` — 40% is on the PWM grid, so it round-trips exactly |
| duty write to an unlatched zone | does **not** stick; the model's automatic value wins |
| model clears a flag | next `check_fan_mode()` reports `LOST` naming that zone |
| `end()` on all three exit paths | nothing latched afterwards (`exit_level=-1`, normal, level write raising) |

Under these, a wrong selector fails because the duty never changes, a wrong netfn fails because nothing
latches, and `split()[0]` fails because the flag never reads as set. All three §1 bugs die to the same
tests, and so does the next one.

**The argv assertions stay.** `test_platforms.py`'s `PlatformSpec` matrix pins the 1-based/0-based zone
split cheaply and gives a reviewer one place to diff against the doc's command table. What changes is
that it stops being the *only* gate. Deleting 1000 lines of working tests to make a point about
mirrors would be its own kind of mistake.

**Verification:** revert each §1 fix individually and confirm the new tests go red. If a revert stays
green, the model is not yet faithful enough and the phase is not done. This is the phase's actual
acceptance criterion — not coverage percentage.

---

## 3. Phase 2 — Ask the BMC instead of hardcoding it

Three constants encode one board's facts. Each is replaced by something read from the BMC.

### 3.1 Zone count

`FANCTL_COUNT = 5` becomes a probe. Part 5.1 documents the procedure: read the manual flag for zone 1,
2, 3 … and stop at the first error; existing zones answer, missing zones do not. It is a read, it
changes nothing, and it runs once in `start()`.

Two gains beyond removing a guess: a configured zone beyond what the board has fails at startup with a
message naming the discovered count, instead of failing at the first duty write; and the code becomes
correct on boards nobody has tested, which is most of them.

### 3.2 Supported fan modes

`valid_fan_modes` (`genericx14.py:35`) hardcodes `0x00`–`0x0B`. Part 3.1 documents
`raw 0x30 0x45 0x02`, a two-byte little-endian bitmask of the modes this board actually supports
(`02 0c` = bits 1, 10, 11 = FullSpeed, Performance, Silent). Read it instead of asserting the range.

This matters more than it looks: Part 3.4 states that an unsupported mode is **accepted silently and
reads back correctly** while a different fan table is loaded. The bitmask is the only way to know a
mode is real, and smfc currently has no way to warn about it.

### 3.3 Failsafe

`check_fan_mode()` polls the manual flag only. Part 3.1 documents op `0x02` as a readable per-zone
failsafe flag meaning "the BMC has forced this zone to 100 %". On a fan-failure trip today, smfc
reports `OK` while the zone runs at full and silently discards every duty it writes.

`X14AtenPlatform` already reasons carefully about this case — `PINNED_LEVEL`, `PINNED_REPORT_AFTER`,
`_lost_detail()` — precisely *because* the ATEN bypass is write-only and it has to infer the trip from
a duty read-back. OpenBMC can read the flag directly. The asymmetry is backwards, and closing it also
lets the OpenBMC class report the cause with certainty where ATEN can only call it likely.

Cost: one extra read per zone per poll, the same order as what `X14AtenPlatform.check_fan_mode()`
already does. A trip is reported as `LOST` with its own detail, which must name the cause and must not
repeat on every poll.

> ⚠️ Part 2 of the guide notes that on workstation boards fitted with slow fans the tacho counter
> cannot resolve below roughly 420 RPM and reports 0, which the BMC reads as a fan failure. On such a
> board a failsafe trip is not a hardware fault and no `min_level` avoids it. Whatever §3.3 reports
> must not read as "your fan is broken".

---

## 4. Phase 3 — Delete `x14_zone_sensors`, centralise the command table

### 4.1 The removal

Part 3.1 documents a direct per-zone duty read, `raw 0x30 0x70 0x66 0x00 <z>`, using the same 0-based
zone byte the write already uses:

```python
def get_fan_level(self, zone: int) -> int:
    validate_input_range(zone, "zone", 0, self.FANCTL_COUNT - 1)
    r = self._exec(["raw", "0x30", "0x70", "0x66", "0x00", f"0x{zone:02x}"])
    return int(r.stdout.split()[-1], 16)
```

`0x30 0x70 0x88 <sensorNum>` is still documented and still works — it is not wrong, it is merely the
only reason the sensor-number apparatus exists. Replacing it deletes, in cascade:

- `genericx14.py:43,45,56-61,185-195` — `zone_sensors`, `DEFAULT_ZONE_SENSOR`, the `__init__` parameter
  and the per-board sensor table in the class docstring;
- `config.py:33,175,368-385,488,501` — the field, the `CV_` constant and `parse_x14_zone_sensors()`;
- the plumbing at `ipmi.py:170`, the `platform_factory` signatures, and `service.py:425-433`;
- **`FanLevelUnavailable` entirely.** `genericx14.py:191` is its only raise site, so `platform.py:50`
  and the two catch sites at `constfc.py:83` and `service.py:431` become dead code.

It also removes the setting's worst trap. Part 5.1 documents that `ipmitool`'s fan labels are **not**
the names the firmware zone tables use — on an X14SAE-F the label `FAN2` is sensor `0x44` while the
zone table's `FAN2` is `0x42`, which `ipmitool` calls `FAN1A`. A user configuring `x14_zone_sensors=`
by name gets a plausible, wrong answer. And `DEFAULT_ZONE_SENSOR = 0x41` is documented as "FAN1, zone 0
on every documented X14 board", which the X14SAE-F table already falsifies: there zone 1 is FAN2+FAN3
(`0x44`) and `0x41` is zone 4.

The `pwm = pct * 255 / 100` conversion stays, because it happens inside the BMC's own duty register
rather than on the way to a fan sensor: a duty reads back exact at multiples of 20 and one percent low
elsewhere, whichever command reads it (Part 3.1). So `ConstFc`'s redundant-write check
(`constfc.py:81-92`) still mismatches on most levels and rewrites the duty on every poll. That is
accepted, not overlooked - it is what the ATEN PWM duty path already does, and a duty write costs one
IPMI command with no effect on the fans.

**Safe to remove:** `x14_zone_sensors` is not on `main` — it exists only on this branch, so no released
configuration breaks and no deprecation cycle is owed.

### 4.2 One command table

`OEM_PREFIX` (`genericx14.py:40`) and `X14_STACK_PROBE` (`platform_factory.py:18`) duplicate the same
bytes in two modules with nothing enforcing that they agree; the duty bytes are inline literals in
`set_fan_level()` and `set_multiple_fan_levels()`, so the §1 selector fix touches two places that could
have diverged.

Collapse every raw sequence for this stack into one table, each entry naming the doc section it comes
from. The value is not tidiness — it is that reconciling the code against Part 3.1/3.2 becomes reading
one screen against one table instead of grepping four files. Given that this knowledge has been revised
twice already, make the reconciliation cheap enough that it actually happens next time.

---

## 5. Phase 4 — Hardware validation, then documentation

### 5.1 The run that settles it

Every argument in §2–§4 is about compensating for not being able to observe the hardware. An X14SAE-F
is on the bench, so:

1. latch manual mode on one zone, confirm the flag reads back;
2. drive a low duty and confirm the RPM moves;
3. **hold it for several minutes** and confirm the automatic loop does not overwrite it — this is the
   one thing still genuinely unknown. The deleted Part 5.3 table said the write reached the fans but
   *"whether a low duty holds against the automatic loop is still open"*, and no unit test can answer
   it;
4. verify the zone map with a read-back: drive zone 1 to 100 %, confirm a zone-2 fan did not move;
5. `systemctl stop smfc` and confirm the BMC takes the fans back.

Until step 3 passes, the OpenBMC path stays flagged experimental in `README.md`.

### 5.2 Documentation

Last, once behaviour is settled:

- `ARCHITECTURE.md:291,391` — the probe command and the OEM command description.
- `TESTING.md:445` and `automatic_smoke_runner/README.md:97` — the scenario descriptions.
- `platform_factory.py:32-38` — rewrite the `_create_x14_platform()` docstring. Its no-fallback
  rationale still cites the Part 1.3 hazard the doc **retracted**: the two stacks no longer have
  conflicting layouts for `0x66`, so "guessing the stack moves fans" is no longer true. The probe
  stays — it is a read that changes nothing and it returns the right *class* — but the reasoning
  becomes "the stacks share the `0x66` layout but not the meaning of selector `0x02`, so a fallback
  would silently apply the wrong lever". `platform.py:34-35` and `ipmi.py:27` carry the same retracted claim.
- `README.md` / `config/smfc.conf` — remove `x14_zone_sensors=`, and note that `min_level=0` is raised to
  the 5 % floor on both X14 stacks.
- `CHANGELOG.md` — the OpenBMC duty write never having worked is a user-visible fix, not an internal
  correction, and should say so plainly.
- `doc/X14H14_MANUAL_FANCONTROL.md` — fix the internal contradiction: §3.2 (`:243-244`) says the flag
  reply is `1 byte 01/00`, while `:229-230`, `:463` and `:56` say `cf c2 00 <flag>`. The four-byte form
  is the one measured on hardware and the one `awk '{print $NF}'` in the §3.6 script depends on.

---

## 6. Verification

1. `pytest test/ -x` — with §2 in place this is a real gate rather than a mirror.
2. The §2 revert check: each §1 fix reverted individually must turn the suite red.
3. `pytest --cov=smfc --cov-report=term-missing test/` — coverage of the touched modules does not drop.
4. `pylint src/smfc` — clean today, stays clean.
5. `test/run_smoke.sh` and `test/automatic_smoke_runner/run_all.sh`.
6. The §5.1 hardware run on the X14SAE-F. Nothing ships on the OpenBMC path without it.

## Out of scope

- **`X14AtenPlatform`.** Confirmed on H14 hardware, unaffected by every fact this revision corrects.
- Any change to `ControlState`/`ControlStatus`: the two states and the base-class contract stay as they are.
- `/snapshot`, `/metrics` and the Grafana contract.
- Whether the ATEN bypass also helps X13 and older boards — same firmware line, plausible, untested,
  separate decision.

## Open topics (deferred, carried from revision 2)

- **The startup DEBUG level read is unguarded** (`service.py:425-433`): a BMC error there aborts
  startup before the control loop begins. §4 removes its `FanLevelUnavailable` guard, so this gets
  slightly more exposed, not less.
- **`ipmitool` has no timeout.** `subprocess.run()` is called without `timeout=` (`ipmi.py:207`), so a
  wedged `/dev/ipmi0` blocks the control loop indefinitely. §3.3 adds a read per zone per poll.
- **Fan-level write errors terminate the service** — unguarded in the control loop, every platform.
- **`ControlStatus.detail` is platform-composed user-facing text**, and §3.3 adds to it.
