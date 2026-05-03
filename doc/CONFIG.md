# Config class refactoring plan

## Motivation

Currently `ConfigParser` is passed directly into every `*Fc.__init__()`. Each controller class
carries ~12 `CV_*` / `CS_*` string constants that are purely config-parsing artifacts unrelated
to fan control logic. Validation is scattered across `*Fc.__init__()` and `FanController.__init__()`.

The goal is to encapsulate all INI parsing inside a single `Config` class that reads and validates
the whole file at startup, producing typed dataclass instances that controllers simply consume.

## Design

### Centralized section and variable name constants

All INI section names (`CS_*`) and variable names (`CV_*`) are defined once in the `Config` class.
Shared variable names (used by multiple controller types) are defined at the top level, while
section-specific names are grouped together.

```python
class Config:
    # Section names
    CS_IPMI: str = "Ipmi"
    CS_CPU: str = "CPU"
    CS_HD: str = "HD"
    CS_NVME: str = "NVME"
    CS_GPU: str = "GPU"
    CS_CONST: str = "CONST"

    # Shared variable names (common across multiple controller types)
    CV_ENABLED: str = "enabled"
    CV_IPMI_ZONE: str = "ipmi_zone"
    CV_TEMP_CALC: str = "temp_calc"
    CV_STEPS: str = "steps"
    CV_SENSITIVITY: str = "sensitivity"
    CV_POLLING: str = "polling"
    CV_MIN_TEMP: str = "min_temp"
    CV_MAX_TEMP: str = "max_temp"
    CV_MIN_LEVEL: str = "min_level"
    CV_MAX_LEVEL: str = "max_level"
    CV_SMOOTHING: str = "smoothing"

    # [Ipmi] section variable names
    CV_IPMI_COMMAND: str = "command"
    CV_IPMI_FAN_MODE_DELAY: str = "fan_mode_delay"
    CV_IPMI_FAN_LEVEL_DELAY: str = "fan_level_delay"
    CV_IPMI_REMOTE_PARAMETERS: str = "remote_parameters"
    CV_IPMI_PLATFORM_NAME: str = "platform_name"

    # [HD] section variable names
    CV_HD_NAMES: str = "hd_names"
    CV_HD_SMARTCTL_PATH: str = "smartctl_path"
    CV_HD_STANDBY_GUARD_ENABLED: str = "standby_guard_enabled"
    CV_HD_STANDBY_HD_LIMIT: str = "standby_hd_limit"

    # [NVME] section variable names
    CV_NVME_NAMES: str = "nvme_names"

    # [GPU] section variable names
    CV_GPU_TYPE: str = "gpu_type"
    CV_GPU_IDS: str = "gpu_device_ids"
    CV_GPU_NVIDIA_SMI_PATH: str = "nvidia_smi_path"
    CV_GPU_ROCM_SMI_PATH: str = "rocm_smi_path"
    CV_GPU_AMD_TEMP_SENSOR: str = "amd_temp_sensor"

    # AMD temperature sensor key names (for rocm-smi output parsing)
    CV_AMD_TEMP_JUNCTION: str = "Temperature (Sensor junction) (C)"
    CV_AMD_TEMP_EDGE: str = "Temperature (Sensor edge) (C)"
    CV_AMD_TEMP_MEMORY: str = "Temperature (Sensor memory) (C)"
    CV_AMD_TEMP_KEYS: tuple = (CV_AMD_TEMP_JUNCTION, CV_AMD_TEMP_EDGE, CV_AMD_TEMP_MEMORY)

    # [CONST] section variable names
    CV_CONST_LEVEL: str = "level"
```

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

### Config class (continued)

`Config.__init__()` reads the INI file once via `ConfigParser`, parses every section into typed
dataclasses, and validates all values upfront. No `ConfigParser` instance escapes this class.

```python
class Config:
    # ... (constants defined above) ...

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
        for s in self._get_sections(parser, self.CS_CPU):
            result.append(CpuConfig(
                section=s,
                enabled=parser[s].getboolean(self.CV_ENABLED, fallback=False),
                ipmi_zone=FanController.parse_ipmi_zones(parser[s].get(self.CV_IPMI_ZONE, "0")),
                temp_calc=parser[s].getint(self.CV_TEMP_CALC, fallback=FanController.CALC_AVG),
                steps=parser[s].getint(self.CV_STEPS, fallback=6),
                sensitivity=parser[s].getfloat(self.CV_SENSITIVITY, fallback=3.0),
                polling=parser[s].getfloat(self.CV_POLLING, fallback=2.0),
                min_temp=parser[s].getfloat(self.CV_MIN_TEMP, fallback=30.0),
                max_temp=parser[s].getfloat(self.CV_MAX_TEMP, fallback=60.0),
                min_level=parser[s].getint(self.CV_MIN_LEVEL, fallback=35),
                max_level=parser[s].getint(self.CV_MAX_LEVEL, fallback=100),
                smoothing=parser[s].getint(self.CV_SMOOTHING, fallback=1),
            ))
        return result
    # _parse_hd_sections(), _parse_nvme_sections(), etc. follow the same pattern
```

### Fan controllers store a config reference

Each controller stores its typed config object as `self.config` and accesses values directly via
attribute access (e.g., `self.config.ipmi_zone`, `self.config.polling`). This eliminates the need
to copy every config value into separate instance attributes:

```python
class CpuFc(FanController):
    config: CpuConfig

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: CpuConfig) -> None:
        self.config = cfg
        # discover hwmon_path from udev ...
        super().__init__(log, ipmi, cfg.section, count)

    def callback(self) -> None:
        # Access config values via self.config
        if self._get_time_delta() >= self.config.polling:
            temp = self._get_temp(self.config.temp_calc)
            # ...
```

The base `FanController` class is simplified — it receives only `log`, `ipmi`, `name`, and `count`.
**Config validation moves to `Config._parse_*()`** (centralized, fail-fast at startup).
Derived classes access their specific config values through `self.config.*`:

```python
class FanController:
    # Base class no longer stores config values — only references and runtime state
    log: Log
    ipmi: Ipmi
    name: str
    count: int
    hwmon_path: List[str]
    # Calculated/runtime attributes
    temp_step: float
    level_step: float
    last_time: float
    last_temp: float
    last_level: int
    deferred_apply: bool
    _temp_history: deque

    def __init__(self, log: Log, ipmi: Ipmi, name: str, count: int) -> None:
        self.log = log
        self.ipmi = ipmi
        self.name = name
        self.count = count
        # Derived classes must set self.config before calling super().__init__()
        # so we can access self.config.* here for calculated values
```

Similarly for other controllers:

```python
class HdFc(FanController):
    config: HdConfig

    def __init__(self, log: Log, ipmi: Ipmi, cfg: HdConfig) -> None:
        self.config = cfg
        # discover HD devices ...
        super().__init__(log, ipmi, cfg.section, count)

    def _check_standby(self) -> None:
        if self.config.standby_guard_enabled:
            # use self.config.standby_hd_limit ...
```

### Base class accesses config via abstract property or duck typing

Since each derived class has a different config type (`CpuConfig`, `HdConfig`, etc.), the base
class accesses shared config fields through `self.config.*` assuming the derived class has set it:

```python
class FanController:
    def __init__(self, log: Log, ipmi: Ipmi, name: str, count: int) -> None:
        # ... basic setup ...
        # Access config values (derived class must set self.config before calling super())
        self.temp_step = (self.config.max_temp - self.config.min_temp) / self.config.steps
        self.level_step = (self.config.max_level - self.config.min_level) / self.config.steps
        self._temp_history = deque(maxlen=self.config.smoothing)
        # ...
```

Alternatively, define a `Protocol` or base dataclass for the shared fields if stricter typing is desired.
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

- **All `CV_*` / `CS_*` constants centralized in `Config`** — controller classes have zero parsing
  artifacts; they only receive typed dataclass instances.
- **Shared variable names defined once** — `CV_ENABLED`, `CV_POLLING`, etc. are single definitions
  used across all section parsers, reducing duplication and typo risk.
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
