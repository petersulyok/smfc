# Config class refactoring plan

## Motivation

Currently `ConfigParser` is passed directly into every `*Fc.__init__()`. Each controller class
carries ~12 `CV_*` / `CS_*` string constants that are purely config-parsing artifacts unrelated
to fan control logic. Validation is scattered across `*Fc.__init__()` and `FanController.__init__()`.

The goal is to encapsulate all INI parsing inside a single `Config` class that reads and validates
the whole file at startup, producing typed dataclass instances that controllers simply consume.

## Design

### Typed per-controller dataclasses

One `@dataclass` per controller type holds all parsed, typed values for one configuration section:

```python
@dataclass
class IpmiConfig:
    command: str
    fan_mode_delay: int
    fan_level_delay: int
    remote_parameters: str
    platform_name: str

@dataclass
class CpuConfig:
    section: str          # section name used for logging (e.g. "CPU", "CPU:1")
    enabled: bool
    ipmi_zone: List[int]
    temp_calc: int
    steps: int
    sensitivity: float
    polling: float
    min_temp: float
    max_temp: float
    min_level: int
    max_level: int
    smoothing: int

@dataclass
class HdConfig:
    section: str
    enabled: bool
    ipmi_zone: List[int]
    temp_calc: int
    steps: int
    sensitivity: float
    polling: float
    min_temp: float
    max_temp: float
    min_level: int
    max_level: int
    smoothing: int
    hd_names: List[str]
    smartctl_path: str
    standby_guard_enabled: bool
    standby_hd_limit: int

# NvmeConfig, GpuConfig, ConstConfig follow the same pattern
```

### Config class

`Config.__init__()` reads the INI file once via `ConfigParser`, parses every section into typed
dataclasses, and validates all values upfront. No `ConfigParser` instance escapes this class.

```python
class Config:
    ipmi: IpmiConfig
    cpu: List[CpuConfig]    # one entry per [CPU], [CPU:1], [CPU:0] etc.
    hd: List[HdConfig]
    nvme: List[NvmeConfig]
    gpu: List[GpuConfig]
    const: List[ConstConfig]

    def __init__(self, path: str):
        parser = ConfigParser()
        if not parser.read(path):
            raise FileNotFoundError(f"Cannot load configuration file: {path}")
        self.ipmi = self._parse_ipmi(parser)
        self.cpu = self._parse_cpu_sections(parser)
        self.hd = self._parse_hd_sections(parser)
        self.nvme = self._parse_nvme_sections(parser)
        self.gpu = self._parse_gpu_sections(parser)
        self.const = self._parse_const_sections(parser)

    @staticmethod
    def _get_sections(parser: ConfigParser, base_name: str) -> List[str]:
        """Collect [BASE], [BASE:0], [BASE:1] ... sections in order."""
        sections = []
        if parser.has_section(base_name):
            sections.append(base_name)
        prefix = f"{base_name}:"
        numbered = sorted(
            [s for s in parser.sections() if s.startswith(prefix) and s[len(prefix):].isdigit()],
            key=lambda s: int(s[len(prefix):])
        )
        sections.extend(numbered)
        return sections

    def _parse_cpu_sections(self, parser: ConfigParser) -> List[CpuConfig]:
        result = []
        for s in self._get_sections(parser, "CPU"):
            result.append(CpuConfig(
                section=s,
                enabled=parser[s].getboolean("enabled", fallback=False),
                ipmi_zone=FanController.parse_ipmi_zones(parser[s].get("ipmi_zone", "0")),
                temp_calc=parser[s].getint("temp_calc", fallback=FanController.CALC_AVG),
                steps=parser[s].getint("steps", fallback=6),
                sensitivity=parser[s].getfloat("sensitivity", fallback=3.0),
                polling=parser[s].getfloat("polling", fallback=2.0),
                min_temp=parser[s].getfloat("min_temp", fallback=30.0),
                max_temp=parser[s].getfloat("max_temp", fallback=60.0),
                min_level=parser[s].getint("min_level", fallback=35),
                max_level=parser[s].getint("max_level", fallback=100),
                smoothing=parser[s].getint("smoothing", fallback=1),
            ))
        return result
    # _parse_hd_sections(), _parse_nvme_sections(), etc. follow the same pattern
```

### Fan controllers receive a typed config object

`CpuFc.__init__()` receives a `CpuConfig` and reads fields directly — no INI parsing, no string
constants:

```python
class CpuFc(FanController):
    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: CpuConfig) -> None:
        # discover hwmon_path from udev ...
        super().__init__(log, ipmi, cfg.ipmi_zone, cfg.section, count,
                         cfg.temp_calc, cfg.steps, cfg.sensitivity, cfg.polling,
                         cfg.min_temp, cfg.max_temp, cfg.min_level, cfg.max_level, cfg.smoothing)
```

### service.py becomes the wiring layer

```python
cfg = Config(parsed_results.config_file)
for cpu_cfg in cfg.cpu:
    if cpu_cfg.enabled:
        self.controllers.append(CpuFc(self.log, self.udevc, self.ipmi, cpu_cfg))
        time.sleep(cfg.ipmi.fan_level_delay)
```

## Benefits

- **Controllers lose all `CV_*` / `CS_*` string constants** — they are purely parsing artifacts and
  do not belong in the fan control logic classes.
- **Validation is centralised** — all type errors and out-of-range values are caught in
  `Config.__init__()` before any controller is created. A bad `[CPU:1]` section fails immediately
  at startup rather than when that controller is first instantiated.
- **Testing controllers becomes trivial** — instead of constructing a `ConfigParser` with correct
  sections and keys, tests simply instantiate a `CpuConfig(steps=6, min_temp=30.0, ...)` dataclass.
- **`ConfigParser` is fully encapsulated** — no `ConfigParser` object is passed between classes;
  only typed values flow out of `Config`.
- **Natural fit for multiple controller sections** — `Config.cpu: List[CpuConfig]` maps directly
  onto the `[CPU]` / `[CPU:1]` naming convention already implemented.

## Costs

- **More upfront code** — one `@dataclass` and one `_parse_*()` method per controller type
  (roughly five of each).
- **Migration effort** — all `*Fc` classes, `service.py`, `Ipmi`, and tests need updating.
- **`check_dependencies()`** — currently reads config inline; would move to `Config` or take a
  `Config` argument.

## Files affected

| File | Change |
|---|---|
| `config.py` (new) | `Config` class + all dataclasses + `_parse_*()` methods |
| `service.py` | Create `Config`, iterate typed lists, pass dataclasses to controllers |
| `cpufc.py` | Replace `ConfigParser` param with `CpuConfig`; remove all `CV_*` constants |
| `hdfc.py` | Replace `ConfigParser` param with `HdConfig`; remove all `CV_*` constants |
| `nvmefc.py` | Replace `ConfigParser` param with `NvmeConfig`; remove all `CV_*` constants |
| `gpufc.py` | Replace `ConfigParser` param with `GpuConfig`; remove all `CV_*` constants |
| `constfc.py` | Replace `ConfigParser` param with `ConstConfig`; remove all `CV_*` constants |
| `ipmi.py` | Replace `ConfigParser` param with `IpmiConfig` |
| `test_*.py` | Replace `ConfigParser` fixtures with dataclass construction |
