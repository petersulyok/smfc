# `control_function` — Implementation Plan

Branch: `feature/new_user_defined_function`

## 1. Feature summary

Introduce a new section-level config parameter that lets the user describe the
temperature → fan-level mapping directly as a piecewise-linear curve:

```ini
control_function = T1-L1, T2-L2, T3-L3, ...
```

Internally this becomes the **single representation** of the fan curve. The
existing `min_temp` / `max_temp` / `min_level` / `max_level` keys remain
supported, but `Config` rewrites them into an equivalent 2-point
`control_function` at parse time, so the runtime (`FanController.run()`) has
exactly one code path: look up the level in a pre-built LUT indexed by
temperature.

## 2. Design decisions (settled)

- **Co-existence rule**: when `control_function` is set, it wins. When it is
  absent, `Config` synthesizes the canonical form from the legacy keys
  (`f"{int(min_temp)}-{min_level}, {int(max_temp)}-{max_level}"`).
- **Mutual exclusion**: explicitly setting both `control_function` AND any of
  the four legacy keys in the same section is a `ValueError`. Keeps the user
  contract unambiguous.
- **Validation home**: `Config` owns parsing and validation of
  `control_function` (mirrors `parse_ipmi_zones`, `parse_gpu_ids`).
  `FanController` only consumes already-validated pairs and produces the LUT.

## 3. Open questions

1. **`steps` semantics when `control_function` is set** — **DECIDED: keep
   `steps` and digitalize, but only the interior `[t_first+1 .. t_last-1]`.**
   `steps` defines the number of equal-width sub-intervals across the
   interior; the two breakpoint temperatures `t_first` and `t_last` are
   single-point plateaus written directly with `l_first` and `l_last`. Total
   plateau count = `steps + 2`. This preserves the per-controller `steps`
   defaults (CPU=6, HD/NVME=4, GPU=5) as a hysteresis knob — the runtime
   `current_level != self.last_level` gate keeps absorbing intra-plateau
   temperature drift, so `sensitivity` retains its original role and no
   default tuning is required.
   - Why interior-only (rather than the original "digitalize all of
     `[t_first..t_last]`"): the original algorithm's last sub-interval
     averages values that include the user's `l_last`, so the LUT entry at
     `T=t_last` ends up below `l_last` and the visible step UP to `l_last`
     lands at `T=t_last+1` (the tail-fill start), not at `T=t_last`
     (the user's contract). Carving out `t_first` and `t_last` as
     single-point plateaus restores the contract: `LUT[t_first]=l_first`,
     `LUT[t_last]=l_last`, exact.

2. **Scope of the rollout** — **DECIDED: (a).**
   Implement `control_function` for all four temperature-driven controllers
   (CPU, HD, NVME, GPU) in a single PR. After merge, cut a **pre-release**
   for user testing and feedback before the final release — the pre-release
   captures the upside of piloting (real-world signal on the `sensitivity`
   migration in §3 Q1) without splintering the codebase. Suggested commit
   ordering: core (`create_control_function()` + `run()` LUT path + ASCII
   chart) → CPU wiring → HD wiring → NVME wiring → GPU wiring → docs.

3. **Backward compatibility of the mapping itself** — see §4.

## 4. Compatibility with the existing staircase mapping

The old and new mappings are **not** bit-for-bit compatible, even when the
new mapping is fed a 2-point input synthesized from the legacy keys.
*Endpoints do match exactly* (both algorithms hit `min_level` at `min_temp`
and `max_level` at `max_temp`), but plateau placement and count differ.

Example: 2-point `(30, 35) → (65, 100)` at `steps=5`.

| Temp (°C) | Legacy run() staircase | New (interior digital + pinned) | Δ |
|-----------|------------------------|---------------------------------|----|
| 30        | 35                     | 35                              | 0  |
| 31..33    | 35                     | 42                              | +7 |
| 34..37    | 48                     | 42                              | −6 |
| 38..40    | 48                     | 55                              | +7 |
| 41..44    | 61                     | 55                              | −6 |
| 45..47    | 61                     | 68                              | +7 |
| 48..51    | 74                     | 68                              | −6 |
| 52..54    | 74                     | 81                              | +7 |
| 55..58    | 87                     | 81                              | −6 |
| 59..61    | 87                     | 94                              | +7 |
| 62..64    | 100                    | 94                              | −6 |
| 65        | 100                    | 100                             | 0  |

Structural differences:
- **Plateau count**: legacy = `steps + 1`; new = `steps + 2` (extra plateau
  from the two single-point pinned endpoints).
- **Endpoint shape**: legacy uses half-width plateaus at both bookends
  (T=30..33 holds L=35); new uses single-point plateaus (only T=30 holds
  L=35 explicitly — though by truncation accident the next-interior
  plateau may also hold L=35 in shallow-slope curves).
- **Interior plateau placement**: legacy centers plateaus on `step ticks`
  computed as `gain * temp_step`; new partitions the interior into equal
  sub-intervals and uses the averaged per-degree value.
- The endpoint contract (`LUT[min_temp]=min_level`, `LUT[max_temp]=max_level`)
  holds exactly in both algorithms.

### Options

| Option | Behavior |
|---|---|
| **A. Preserve legacy semantics**: keep the old formula in `run()` for legacy sections; only use the LUT when `control_function` is explicitly set. Two runtime paths. | Bit-for-bit identical for existing users. |
| **B. Make the 2-point case match the old staircase**: special-case `create_control_function()` when given exactly 2 points so it reproduces the legacy formula. Single runtime path, two LUT-build paths. | Identical for existing users; new users get the per-degree curve. |
| **C. Center the digitalization on step ticks** in `create_control_function()` step 4. Single runtime path, one algorithm. | Close but not identical (≤ 1°C drift remains from float interpolation vs. discrete arithmetic). |
| **D. Accept the drift** and document in CHANGELOG ("retune if needed"). | Cleanest code, breaks an implicit guarantee for existing users. |

**Recommendation: B.** Keeps one runtime path, preserves backward compatibility
exactly for everyone who hasn't opted into `control_function`, and isolates the
special case in one well-tested helper.

**DECIDED: D (accept the drift), softened by §3 Q1.** Digitalization is
*kept* but restructured (interior-only, with endpoints pinned). For the
legacy 2-point synthesis, the resulting staircase still differs from the old
formula in plateau placement (off-by-one drift remains) but the endpoint
contract is identical: `LUT[min_temp] = min_level`, `LUT[max_temp] =
max_level`. Document the plateau-placement drift in the CHANGELOG; no
`sensitivity` retuning needed.

## 5. Issues with the current `create_control_function()`

**Note:** §3 Q1 is settled — digitalization is *kept* but restructured to
interior-only with endpoint pinning. So all five sub-sections (A–F) still
apply: Step 4 stays but operates on a narrower index range and gets a
`round()` fix; the loop-variable leak in D is fixed by reading
`pairs[-1]` explicitly and by the endpoint-pinning write that runs after
the loop.


Found while reviewing `src/smfc/fancontroller.py` lines 166–234.

### A. Signature
- Missing `@staticmethod`. Defined inside `FanController` with no `self`.
  An instance call would silently pass `self` as `input_str`.

### B. Input validation gaps
- No range check on T or L. `"30-35, 150-100"` builds a 151-element LUT;
  `"30-150"` produces a fan level of 150% with no error.
- No monotonicity check. `"50-35, 30-80"` makes `temps = t2 − t1 = −20`,
  the interpolation comprehension iterates over an empty range, step 3.3
  then uses `t2 = 30, l2 = 80` and silently fills `[30..100]` with 80.
- No "≥2 distinct temperatures" check. `"30-35, 30-100"` makes `temps = 0`.
  In step 4, with `length = 1` and `steps > 1`, later iterations get
  `size = 0` and the inner average loop divides by zero (`ZeroDivisionError`).
- Unhelpful parser errors. `"30:35"` (wrong separator) or `"30-35-extra"`
  (too many hyphens) bubble up as a bare `ValueError` from tuple unpack.
  `"30.5-50"` fails on `int()` with a generic message.

### C. Math / precision
- Step 3.2 uses `int(...)` (truncation) for linear interpolation, biasing
  levels downward by up to 1 percentage point per degree. Should be
  `round(...)`.
- Step 4 uses `int(average / size)` (truncation) for the plateau value.
  Same fix.
- Inconsistent endpoint handling: step 3.2 fills `[t1..t2−1]` per segment;
  step 3.3 then fills `[t_n..100]`. Correct but non-obvious — warrants a
  one-line comment.

### D. Bounds / off-by-one
- Out-of-range `t_n` corrupts the LUT length. If the last pair's
  temperature is > 100, `(100 − t2 + 1)` is negative, `[l2] * negative = []`,
  the LUT ends short, and `levels_lut[100]` in `run()` raises `IndexError`.
- Out-of-range `t_1`. If the first temperature is < 0, the initial
  `[l_1] * t_1` extension produces 0 entries; the lower part of the LUT
  is missing.
- Loop-variable leak. Step 3.3 uses `t2`, `l2` from the loop's last
  iteration. Works only because the `len < 2` check runs first; otherwise
  `UnboundLocalError`. Move them to explicit `tl_pairs[-1]` reads.

### E. Naming / readability
- Outer loop counter `i` is shadowed by the inner list comprehension's `i`.
  Python 3 scoping makes it work, but it reads like a bug. Rename the inner
  one to `di` or `offset`.
- `temps` (segment width in degrees) is confusing next to `tl_pairs`
  ("temperatures"). `dt` or `width` is clearer.
- Error messages start with `"ERROR:"`; the rest of the codebase uses
  lowercase `"invalid value: …"` (`Config._validate_fan_controller_config`).
- Typos: `"intervall"` → `"interval"`, `"ont input string"` → `"on input string"`.

### F. Style (vs. CLAUDE.md + project conventions)
- Triple-quoted docstring uses `'''`; project uses `"""`.
- Missing spaces around `=`: `tl_pairs=[]`, `temp=int(...)`, `average=0`.
- Trailing whitespace.
- Rolls its own separator detection. `parse_ipmi_zones` already uses the
  canonical `re.sub(" +", " ", s.strip())` pattern. Reuse for consistency.

## 6. Where validation lives

| Concern | Location |
|---|---|
| Syntactic: ≥2 pairs, each pair `"T-L"`, both parse as int | `Config.parse_control_function()` |
| Range: T ∈ [0..100], L ∈ [0..100] | `Config.parse_control_function()` |
| Monotonicity: temperatures strictly ascending | `Config.parse_control_function()` |
| Cross-field with `steps`: `(t_n − t_1 − 1) ≥ steps` (interior digitalization) | `Config._validate_fan_controller_config()` |
| Mutually exclusive with legacy keys | `_parse_<x>_sections()` (needs `parser.has_option`, not just the dataclass value) |
| Legacy → canonical synthesis when `control_function` absent | `_parse_<x>_sections()` |
| LUT generation (101-element array, digitalize by `steps`) | `FanController.create_control_function()` (derived runtime state, like `temp_step`/`level_step` today) |

## 7. Sketches

### `Config.parse_control_function()`

```python
CV_CONTROL_FUNCTION: str = "control_function"

@staticmethod
def parse_control_function(cf_str: str) -> List[Tuple[int, int]]:
    """Parse 'T1-L1, T2-L2, ...' into validated (T, L) pairs.
    Raises ValueError on malformed input, out-of-range values,
    duplicate temperatures, or non-ascending temperatures."""
    s = re.sub(" +", " ", cf_str.strip())
    parts = [p.strip() for p in s.split("," if "," in s else " ")]
    if len(parts) < 2:
        raise ValueError(f"invalid value: {CV_CONTROL_FUNCTION} needs >=2 points ({cf_str})")
    pairs: List[Tuple[int, int]] = []
    for p in parts:
        tl = p.split("-")
        if len(tl) != 2:
            raise ValueError(f"invalid value: malformed pair '{p}' in {CV_CONTROL_FUNCTION}")
        try:
            t, l = int(tl[0].strip()), int(tl[1].strip())
        except ValueError as e:
            raise ValueError(f"invalid value: non-integer pair '{p}' in {CV_CONTROL_FUNCTION}") from e
        if not 0 <= t <= 100:
            raise ValueError(f"invalid value: temperature {t} out of [0..100] in {CV_CONTROL_FUNCTION}")
        if not 0 <= l <= 100:
            raise ValueError(f"invalid value: level {l} out of [0..100] in {CV_CONTROL_FUNCTION}")
        pairs.append((t, l))
    for i in range(1, len(pairs)):
        if pairs[i][0] <= pairs[i-1][0]:
            raise ValueError(f"invalid value: temperatures must be strictly ascending in {CV_CONTROL_FUNCTION}")
    return pairs
```

### Section parser snippet (CPU shown; same shape for HD/NVME/GPU)

```python
has_legacy = any(parser.has_option(s, k) for k in
                 (self.CV_MIN_TEMP, self.CV_MAX_TEMP, self.CV_MIN_LEVEL, self.CV_MAX_LEVEL))
raw_cf = parser[s].get(self.CV_CONTROL_FUNCTION, fallback="").strip()
if raw_cf and has_legacy:
    raise ValueError(f"[{s}] {self.CV_CONTROL_FUNCTION} is mutually exclusive with "
                     f"{self.CV_MIN_TEMP}/{self.CV_MAX_TEMP}/{self.CV_MIN_LEVEL}/{self.CV_MAX_LEVEL}")
if raw_cf:
    cf_pairs = self.parse_control_function(raw_cf)
else:
    cf_pairs = [(int(min_temp), min_level), (int(max_temp), max_level)]
```

### Dataclass change

```python
@dataclass
class CpuConfig:
    ...
    control_function: List[Tuple[int, int]]   # Validated user-defined control points
```

Same field added to `HdConfig`, `NvmeConfig`, `GpuConfig`. The legacy
`min_temp / max_temp / min_level / max_level` fields stay, since they are
used to synthesize `control_function` and remain handy for logging.

### `FanController.create_control_function()`

No longer parses strings. Takes already-validated pairs plus `steps` and
produces the 101-entry LUT via **interior-only digitalization with endpoint
pinning**:

1. Build the per-degree piecewise-linear LUT (with `round()`, not `int()`).
2. Digitalize only the interior `[t_first+1 .. t_last-1]` into `steps`
   equal-width sub-intervals, averaging the per-degree values within each
   and writing the average (with `round()`) to every degree in the
   sub-interval.
3. Write the user-defined endpoints directly: `LUT[t_first] = l_first`,
   `LUT[t_last] = l_last`. (Step 2 doesn't touch these indices, so this is
   really just a clarity step.)

```python
@staticmethod
def create_control_function(pairs: List[Tuple[int, int]], steps: int) -> List[int]:
    """Build a 101-element LUT from validated (T, L) breakpoints, digitalized
    on the interior with the two breakpoint temperatures pinned. Produces
    steps+2 plateaus total: 1 at t_first, steps in the interior, 1 at t_last."""
    t_first, l_first = pairs[0]
    t_last,  l_last  = pairs[-1]

    # Step 1: per-degree piecewise-linear LUT.
    levels: List[int] = [l_first] * t_first
    for i in range(len(pairs) - 1):
        t1, l1 = pairs[i]
        t2, l2 = pairs[i + 1]
        dt = t2 - t1
        levels.extend([round(l1 + (di * (l2 - l1) / dt)) for di in range(dt)])
    levels.extend([l_last] * (100 - t_last + 1))

    # Step 2: digitalize interior [t_first+1 .. t_last-1] into `steps` plateaus.
    interior_len = t_last - t_first - 1
    if interior_len > 0 and steps >= 1:
        base = interior_len // steps
        remainder = interior_len % steps
        start = t_first + 1
        for i in range(steps):
            size = base + (1 if i < remainder else 0)
            if size == 0:
                continue
            end = start + size - 1
            avg = round(sum(levels[start:end + 1]) / size)
            for t in range(start, end + 1):
                levels[t] = avg
            start = end + 1

    # Step 3: pin endpoints (Step 2 already leaves these untouched; explicit
    # writes make the contract obvious to readers).
    levels[t_first] = l_first
    levels[t_last]  = l_last
    return levels
```

Validation note: §6's "Cross-field: `(t_n − t_1 + 1) ≥ steps`" should become
`(t_n − t_1 − 1) ≥ steps` to account for the interior-only range.

### `FanController` runtime

- `__init__`: build `self.levels_lut = FanController.create_control_function(self.config.control_function, self.config.steps)` and drop `temp_step`/`level_step` (or keep them only for log output).
- `run()`: replace the staircase block with one lookup:

```python
idx = max(0, min(100, int(round(current_temp))))
current_level = self.levels_lut[idx]
```

- `print_temp_level_mapping()`: render the LUT as an ASCII vertical bar chart
  at `LOG_CONFIG` so the user can eyeball the curve shape at startup. Y-axis
  = fan level (0..100% in 10% rows), X-axis = temperature (one bar every 5°C
  by default, always including each user breakpoint), `^` markers under the
  axis flag the breakpoints. Example output (`steps=5`, interior-only
  digitalization, so plateau values are 35/35/37/39/65/92/100):

  ```
     control_function = 30-35, 50-40, 60-90, 65-100  (steps = 5)
     100% |                                ###|
      90% |                            ### ###|
      80% |                            ### ###|
      70% |                            ### ###|
      60% |                        ### ### ###|
      50% |                        ### ### ###|
      40% |        ### ### ### ### ### ### ###|
      30% |### ### ### ### ### ### ### ### ###|
      20% |### ### ### ### ### ### ### ### ###|
      10% |### ### ### ### ### ### ### ### ###|
       0% |### ### ### ### ### ### ### ### ###|
          +-----------------------------------+
            30  35  40  45  50  55  60  65  70  (C)
            ^               ^       ^   ^       ^ = user breakpoint
  ```

  ASCII-only characters (`#`, `.`, `^`) so log files remain clean for
  grep/journalctl/syslog.

## 8. Tests

### `test/test_config.py`
- Positive: section without `control_function` → field is the synthesized
  2-point list matching the legacy keys.
- Positive: section with `control_function` only → field matches parsed pairs;
  legacy keys not required.
- Negative: both `control_function` and any of the four legacy keys set →
  `ValueError`.
- Negative cases for `parse_control_function()`: <2 pairs, malformed pair,
  non-integer, out-of-range T/L, non-ascending T, duplicate T.
- Cross-field: `(t_n − t_1 + 1) < steps` → `ValueError`.

### `test/test_fancontroller.py`
- Unit tests for `create_control_function()` taking a list of pairs and
  `steps`: 2-point, 3-point, 4-point curves; verify LUT length = 101,
  `LUT[t_first] == l_first`, `LUT[t_last] == l_last`, plateau count =
  `steps + 2`, interior plateau averages, and tail-fill regions.
- `run()` driven by a `control_function` config — verify the LUT-driven level
  matches the curve at breakpoints and between them.

### `test/test_data.py`
- Extend `create_cpu_config / create_hd_config / create_nvme_config /
  create_gpu_config` with a `control_function=None` kwarg. When `None`, the
  factory synthesizes from min/max (same as `Config` does).

## 9. Sample config and docs

- `config/smfc.conf`: add a commented example next to the existing keys in
  each temperature-driven section.

  ```ini
  # User-defined fan curve as a list of "temperature-level" pairs (str, default='').
  # When set, this overrides min_temp / max_temp / min_level / max_level.
  # Example: control_function=30-35, 50-50, 60-80, 70-100
  #control_function=
  ```

- `ARCHITECTURE.md` §7.1.2: replace the staircase ASCII diagram with a
  piecewise-linear example; explain the LUT and the legacy synthesis.
- `README.md` / `doc/`: reference `doc/userdefined_control_function.png` and
  give a worked example with `control_function`.
- `CHANGELOG.md`: new entry under the unreleased section. If option D from
  §4 is chosen, call out the behavior change explicitly.

## 10. Suggested commit order

1. **`create_control_function()` fix-up** — `@staticmethod`, accept already-
   parsed pairs (no string parsing), apply the interior-only digitalization
   + endpoint-pinning algorithm from §7, use `round()` (not `int()`), fix
   variable shadowing, docstring/style. Add isolated unit tests in
   `test_fancontroller.py` covering: LUT length=101, `LUT[t_first]=l_first`,
   `LUT[t_last]=l_last`, plateau count = `steps + 2`, 2-/3-/4-point curves.
2. **`Config.parse_control_function()` + dataclass field + mutual-exclusion
   check + cross-field validation with `steps`.** Add positive/negative tests
   in `test_config.py`. Update factories in `test_data.py`.
3. **Wire the LUT into `FanController.__init__` and `run()`.** Decide §4 here:
   if option B, add the 2-point special case in `create_control_function()`.
   Update `print_temp_level_mapping()`.
4. **Sample config, ARCHITECTURE.md, README, CHANGELOG.**
