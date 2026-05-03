# Multiple fan curves per IPMI zone

## Background

Issue [#111](https://github.com/petersulyok/smfc/issues/111) requested the ability to define a
different fan speed curve per IPMI zone. The motivation: fans in different zones can have very
different noise and cooling characteristics, so a single shared curve produces suboptimal results.

## Concept

Instead of adding per-zone curve parameters inside a single controller section, the solution
creates **multiple independent instances of the same controller type**, each assigned to a
different IPMI zone with its own full set of curve parameters.

Each instance is a complete, independent fan controller sharing the same physical temperature
source (e.g. CPU temperature) but applying a different curve to its assigned zone.

## Configuration: section naming conventions

Three naming styles are supported and can be freely mixed:

```ini
# 1. Single instance — original format, unchanged behaviour
[CPU]
enabled=1
ipmi_zone=0
...

# 2. Base section plus numbered extras
[CPU]
enabled=1
ipmi_zone=0
...

[CPU:1]
enabled=1
ipmi_zone=1
...

# 3. All-numbered instances
[CPU:0]
enabled=1
ipmi_zone=0
...

[CPU:1]
enabled=1
ipmi_zone=1
...
```

The same applies to `[HD]`, `[NVME]`, `[GPU]`, and `[CONST]`.

The suffix number after `:` is used only for ordering and logging. It has no relationship to the
`ipmi_zone=` value inside the section — `[CPU:1]` can control zone 0, and `[CPU:0]` can control
zone 1.

## Example: issue #111 use case

Setup: zone 0 = mid-plane fans (noisy above 40% PWM), zone 1 = CPU coolers (silent up to 90%).

```ini
[Ipmi]
command=/usr/bin/ipmitool
fan_mode_delay=10
fan_level_delay=2
platform_name=auto

# CPU controls both zones with different curves
[CPU:0]
enabled=1
ipmi_zone=0
temp_calc=1
steps=5
sensitivity=3.0
polling=2
smoothing=1
min_temp=55.0    # react later — mid-plane fans are noisy
max_temp=75.0
min_level=20
max_level=80

[CPU:1]
enabled=1
ipmi_zone=1
temp_calc=1
steps=6
sensitivity=3.0
polling=2
smoothing=1
min_temp=40.0    # react earlier — CPU coolers are silent
max_temp=80.0
min_level=20
max_level=100

# HD also controls zone 0 — shared with CPU:0, max wins
[HD]
enabled=1
ipmi_zone=0
temp_calc=1
steps=4
sensitivity=2.0
polling=10
smoothing=1
min_temp=30.0
max_temp=46.0
min_level=20
max_level=100
hd_names=
```

### Resulting behaviour

```
CPU = 65°C, HD = 43°C

CPU:0  zone 0 curve (55–75°C → 20–80%):  level = 60%
HD     zone 0 curve (30–46°C → 20–100%): level = 80%
CPU:1  zone 1 curve (40–80°C → 20–100%): level = 76%

Zone 0 arbitration: max(60%, 80%) = 80%  (HD wins)
Zone 1 (unshared):  76%                  (CPU:1 alone)
```

## Implementation

### Section detection (`service.py`)

`_get_controller_sections(config, base_name)` collects all matching sections in order:

- `[CPU]` alone → `["CPU"]`
- `[CPU]` + `[CPU:1]` → `["CPU", "CPU:1"]`
- `[CPU:0]` + `[CPU:1]` → `["CPU:0", "CPU:1"]`

Detection logic (no regex needed):

```python
sections = []
if config.has_section(base_name):
    sections.append(base_name)
prefix = f"{base_name}:"
numbered = sorted(
    [s for s in config.sections() if s.startswith(prefix) and s[len(prefix):].isdigit()],
    key=lambda s: int(s[len(prefix):])
)
sections.extend(numbered)
```

### Controller instantiation (`service.py`)

Each enabled section creates one independent controller instance:

```python
for section in self._get_controller_sections(self.config, CpuFc.CS_CPU_FC):
    if self.config[section].getboolean(CpuFc.CV_CPU_FC_ENABLED, fallback=False):
        self.controllers.append(CpuFc(self.log, self.udevc, self.ipmi, self.config, section))
```

### Controller name and logging

Each instance uses its section name as `name` (e.g. `"CPU:1"`), so all log messages
unambiguously identify which instance is acting:

```
CPU:0 fan controller was initialized with:
   ipmi zone = [0]
   ...
CPU:1 fan controller was initialized with:
   ipmi zone = [1]
   ...
IPMI zone [0]: new level = 80% (HD=43.0C)
IPMI zone [1]: new level = 76% (CPU:1=65.0C)
```

### Shared zone arbitration

Multiple controller instances competing on the same zone is handled by the existing
arbitration logic in `_check_shared_zones()` and `_apply_fan_levels()` — no changes needed.
This covers both same-type sharing (`[CPU:0]` and `[HD]` on zone 0) and cross-type sharing.

### Fan controller `__init__` signatures

Each `*Fc` class gained a `section` parameter (last, with a backward-compatible default):

```python
def __init__(self, log, udevc, ipmi, config, section: str = CS_CPU_FC): ...
def __init__(self, log, udevc, ipmi, config, sudo, section: str = CS_HD_FC): ...
def __init__(self, log, ipmi, config, section: str = CS_GPU_FC): ...
```

All config reads inside `__init__` use `config[section]` instead of the hardcoded class constant.

## Open issue: duplicate zone validation

**No validation currently prevents two instances of the same controller type from accidentally
assigning the same `ipmi_zone`.**

If `[CPU:0]` and `[CPU:1]` both declare `ipmi_zone=0`, `_check_shared_zones()` silently treats
them as shared and applies the max level — one curve is effectively ignored. There is no warning
or error.

### Proposed fix

Add `_check_duplicate_zones()` to `service.py`, called after controller creation and before
`_check_shared_zones()`:

```python
def _check_duplicate_zones(self) -> None:
    """Raise ValueError if two instances of the same controller type share an IPMI zone."""
    by_type: Dict[str, Dict[int, str]] = {}
    for fc in self.controllers:
        base = fc.name.split(":")[0]
        seen = by_type.setdefault(base, {})
        for zone in fc.ipmi_zone:
            if zone in seen:
                raise ValueError(
                    f"[{fc.name}] and [{seen[zone]}] both assign ipmi_zone={zone}"
                )
            seen[zone] = fc.name
```

This fails fast at startup with a clear message instead of silently miscontrolling fans.
