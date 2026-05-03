#
#   config.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.Config() class implementation - centralized configuration parsing.
#
import re
from configparser import ConfigParser
from dataclasses import dataclass
from typing import List


@dataclass
class IpmiConfig:
    """Configuration for IPMI interface."""
    command: str            # Full path for ipmitool command
    fan_mode_delay: int     # Delay time after execution of IPMI set fan mode function (sec)
    fan_level_delay: int    # Delay time after execution of IPMI set fan level function (sec)
    remote_parameters: str  # Remote IPMI parameters (e.g. "-I lanplus -U ADMIN -P ADMIN -H 127.0.0.1")
    platform_name: str      # Platform name (from config or "auto" for auto-detection)


@dataclass
class CpuConfig:
    """Configuration for CPU fan controller."""
    section: str            # Section name used for logging (e.g. "CPU", "CPU:1")
    enabled: bool           # Fan controller enabled
    ipmi_zone: List[int]    # IPMI zone(s) assigned to the controller
    temp_calc: int          # Temperature calculation method (0-min, 1-avg, 2-max)
    steps: int              # Discrete steps in temperatures and fan levels
    sensitivity: float      # Temperature change to activate fan controller (C)
    polling: float          # Polling interval to read temperature (sec)
    min_temp: float         # Minimum temperature value (C)
    max_temp: float         # Maximum temperature value (C)
    min_level: int          # Minimum fan level (0..100%)
    max_level: int          # Maximum fan level (0..100%)
    smoothing: int          # Moving average window size for temperature readings (1=disabled)


@dataclass
class HdConfig:
    """Configuration for HD fan controller."""
    section: str                # Section name used for logging (e.g. "HD", "HD:1")
    enabled: bool               # Fan controller enabled
    ipmi_zone: List[int]        # IPMI zone(s) assigned to the controller
    temp_calc: int              # Temperature calculation method (0-min, 1-avg, 2-max)
    steps: int                  # Discrete steps in temperatures and fan levels
    sensitivity: float          # Temperature change to activate fan controller (C)
    polling: float              # Polling interval to read temperature (sec)
    min_temp: float             # Minimum temperature value (C)
    max_temp: float             # Maximum temperature value (C)
    min_level: int              # Minimum fan level (0..100%)
    max_level: int              # Maximum fan level (0..100%)
    smoothing: int              # Moving average window size for temperature readings (1=disabled)
    hd_names: List[str]         # Device names of the hard disks (e.g. '/dev/disk/by-id/...')
    smartctl_path: str          # Path for 'smartctl' command
    standby_guard_enabled: bool # Standby guard feature enabled
    standby_hd_limit: int       # Number of HDs in STANDBY state before the full array goes STANDBY


@dataclass
class NvmeConfig:
    """Configuration for NVME fan controller."""
    section: str            # Section name used for logging (e.g. "NVME", "NVME:1")
    enabled: bool           # Fan controller enabled
    ipmi_zone: List[int]    # IPMI zone(s) assigned to the controller
    temp_calc: int          # Temperature calculation method (0-min, 1-avg, 2-max)
    steps: int              # Discrete steps in temperatures and fan levels
    sensitivity: float      # Temperature change to activate fan controller (C)
    polling: float          # Polling interval to read temperature (sec)
    min_temp: float         # Minimum temperature value (C)
    max_temp: float         # Maximum temperature value (C)
    min_level: int          # Minimum fan level (0..100%)
    max_level: int          # Maximum fan level (0..100%)
    smoothing: int          # Moving average window size for temperature readings (1=disabled)
    nvme_names: List[str]   # Device names of the NVMe drives (e.g. '/dev/disk/by-id/...')


@dataclass
class GpuConfig:
    """Configuration for GPU fan controller."""
    section: str                # Section name used for logging (e.g. "GPU", "GPU:1")
    enabled: bool               # Fan controller enabled
    ipmi_zone: List[int]        # IPMI zone(s) assigned to the controller
    temp_calc: int              # Temperature calculation method (0-min, 1-avg, 2-max)
    steps: int                  # Discrete steps in temperatures and fan levels
    sensitivity: float          # Temperature change to activate fan controller (C)
    polling: float              # Polling interval to read temperature (sec)
    min_temp: float             # Minimum temperature value (C)
    max_temp: float             # Maximum temperature value (C)
    min_level: int              # Minimum fan level (0..100%)
    max_level: int              # Maximum fan level (0..100%)
    smoothing: int              # Moving average window size for temperature readings (1=disabled)
    gpu_type: str               # GPU type: 'nvidia' or 'amd'
    gpu_device_ids: List[int]   # GPU device IDs (indexes)
    nvidia_smi_path: str        # Path for 'nvidia-smi' command
    rocm_smi_path: str          # Path for 'rocm-smi' command
    amd_temp_sensor: int        # AMD temperature sensor (0-junction, 1-edge, 2-memory)


@dataclass
class ConstConfig:
    """Configuration for CONST fan controller."""
    section: str            # Section name used for logging (e.g. "CONST", "CONST:1")
    enabled: bool           # Fan controller enabled
    ipmi_zone: List[int]    # IPMI zone(s) assigned to the controller
    polling: float          # Polling interval to check fan level (sec)
    level: int              # Constant fan level (0..100%)


class Config:
    """Centralized configuration class that parses the INI file and produces typed dataclass instances."""

    # Section names
    CS_IPMI: str = "Ipmi"       # [Ipmi] section name
    CS_CPU: str = "CPU"         # [CPU] section name
    CS_HD: str = "HD"           # [HD] section name
    CS_NVME: str = "NVME"       # [NVME] section name
    CS_GPU: str = "GPU"         # [GPU] section name
    CS_CONST: str = "CONST"     # [CONST] section name

    # Shared variable names (common across multiple controller types)
    CV_ENABLED: str = "enabled"             # Fan controller enabled flag
    CV_IPMI_ZONE: str = "ipmi_zone"         # IPMI zone(s) assigned to controller
    CV_TEMP_CALC: str = "temp_calc"         # Temperature calculation method
    CV_STEPS: str = "steps"                 # Discrete steps in temperatures and fan levels
    CV_SENSITIVITY: str = "sensitivity"     # Temperature change to activate fan controller
    CV_POLLING: str = "polling"             # Polling interval to read temperature
    CV_MIN_TEMP: str = "min_temp"           # Minimum temperature value
    CV_MAX_TEMP: str = "max_temp"           # Maximum temperature value
    CV_MIN_LEVEL: str = "min_level"         # Minimum fan level
    CV_MAX_LEVEL: str = "max_level"         # Maximum fan level
    CV_SMOOTHING: str = "smoothing"         # Moving average window size

    # [Ipmi] section variable names
    CV_IPMI_COMMAND: str = "command"                        # Full path for ipmitool command
    CV_IPMI_FAN_MODE_DELAY: str = "fan_mode_delay"          # Delay after set fan mode
    CV_IPMI_FAN_LEVEL_DELAY: str = "fan_level_delay"        # Delay after set fan level
    CV_IPMI_REMOTE_PARAMETERS: str = "remote_parameters"    # Remote IPMI parameters
    CV_IPMI_PLATFORM_NAME: str = "platform_name"            # Platform name or "auto"

    # [HD] section variable names
    CV_HD_NAMES: str = "hd_names"                            # HD device names
    CV_HD_SMARTCTL_PATH: str = "smartctl_path"               # Path to smartctl command
    CV_HD_STANDBY_GUARD_ENABLED: str = "standby_guard_enabled"  # Enable standby guard
    CV_HD_STANDBY_HD_LIMIT: str = "standby_hd_limit"         # Standby HD limit

    # [NVME] section variable names
    CV_NVME_NAMES: str = "nvme_names"    # NVMe device names

    # [GPU] section variable names
    CV_GPU_TYPE: str = "gpu_type"                   # GPU type: 'nvidia' or 'amd'
    CV_GPU_IDS: str = "gpu_device_ids"              # GPU device IDs (indexes)
    CV_GPU_NVIDIA_SMI_PATH: str = "nvidia_smi_path" # Path to nvidia-smi command
    CV_GPU_ROCM_SMI_PATH: str = "rocm_smi_path"     # Path to rocm-smi command
    CV_GPU_AMD_TEMP_SENSOR: str = "amd_temp_sensor" # AMD temperature sensor index

    # AMD temperature sensor key names (for rocm-smi output parsing)
    CV_AMD_TEMP_JUNCTION: str = "Temperature (Sensor junction) (C)"
    CV_AMD_TEMP_EDGE: str = "Temperature (Sensor edge) (C)"
    CV_AMD_TEMP_MEMORY: str = "Temperature (Sensor memory) (C)"
    CV_AMD_TEMP_KEYS: tuple = (CV_AMD_TEMP_JUNCTION, CV_AMD_TEMP_EDGE, CV_AMD_TEMP_MEMORY)

    # [CONST] section variable names
    CV_CONST_LEVEL: str = "level"   # Constant fan level

    # Constant values for temperature calculation
    CALC_MIN: int = 0   # Use minimum temperature
    CALC_AVG: int = 1   # Use average temperature
    CALC_MAX: int = 2   # Use maximum temperature

    # Constant values for IPMI fan zones (defaults)
    CPU_ZONE: int = 0   # Default CPU zone ID
    HD_ZONE: int = 1    # Default HD zone ID

    # Parsed configuration dataclasses
    ipmi: IpmiConfig            # IPMI configuration
    cpu: List[CpuConfig]        # List of CPU fan controller configurations
    hd: List[HdConfig]          # List of HD fan controller configurations
    nvme: List[NvmeConfig]      # List of NVME fan controller configurations
    gpu: List[GpuConfig]        # List of GPU fan controller configurations
    const: List[ConstConfig]    # List of CONST fan controller configurations

    def __init__(self, path: str) -> None:
        """Initialize the Config class by reading and parsing the INI file.
        Args:
            path (str): path to the configuration file
        Raises:
            FileNotFoundError: configuration file not found
            ValueError: invalid configuration parameters
        """
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
        """Collect [BASE], [BASE:0], [BASE:1] ... sections in order.
        Args:
            parser (ConfigParser): configuration parser
            base_name (str): base section name (e.g. "CPU", "HD")
        Returns:
            List[str]: list of section names in order
        """
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

    @staticmethod
    def parse_ipmi_zones(ipmi_zone: str) -> List[int]:
        """Parse a comma- or space-separated string of IPMI zone IDs into a validated list.
        Args:
            ipmi_zone (str): IPMI zone(s) string
        Returns:
            List[int]: list of zone IDs
        Raises:
            ValueError: invalid zone string or zone value out of range
        """
        zone_str = re.sub(" +", " ", ipmi_zone.strip())
        zones = [int(s) for s in zone_str.split("," if "," in ipmi_zone else " ")]
        for zone in zones:
            if zone not in range(0, 101):
                raise ValueError(f"invalid value: ipmi_zone={ipmi_zone}.")
        return zones

    @staticmethod
    def parse_device_names(names_str: str) -> List[str]:
        """Parse a newline- or space-separated string of device names.
        Args:
            names_str (str): device names string
        Returns:
            List[str]: list of device names
        """
        if "\n" in names_str:
            return names_str.splitlines()
        return names_str.split()

    @staticmethod
    def parse_gpu_ids(gpu_id_str: str) -> List[int]:
        """Parse a comma- or space-separated string of GPU device IDs.
        Args:
            gpu_id_str (str): GPU device IDs string
        Returns:
            List[int]: list of GPU device IDs
        Raises:
            ValueError: invalid GPU ID string or value out of range
        """
        gpu_id_list = re.sub(" +", " ", gpu_id_str.strip())
        ids = [int(s) for s in gpu_id_list.split("," if "," in gpu_id_list else " ")]
        for gid in ids:
            if gid not in range(0, 101):
                raise ValueError(f"invalid value: gpu_device_ids={gpu_id_str}.")
        return ids

    def _parse_ipmi(self, parser: ConfigParser) -> IpmiConfig:
        """Parse [Ipmi] section.
        Args:
            parser (ConfigParser): configuration parser
        Returns:
            IpmiConfig: parsed IPMI configuration
        Raises:
            ValueError: invalid configuration parameters or missing [Ipmi] section
        """
        s = self.CS_IPMI
        if s not in parser:
            raise ValueError(f"Missing mandatory [{s}] section in configuration file")
        fan_mode_delay = parser[s].getint(self.CV_IPMI_FAN_MODE_DELAY, fallback=10)
        if fan_mode_delay < 0:
            raise ValueError(f"Negative {self.CV_IPMI_FAN_MODE_DELAY}= parameter ({fan_mode_delay})")
        fan_level_delay = parser[s].getint(self.CV_IPMI_FAN_LEVEL_DELAY, fallback=2)
        if fan_level_delay < 0:
            raise ValueError(f"Negative {self.CV_IPMI_FAN_LEVEL_DELAY}= parameter ({fan_level_delay})")
        return IpmiConfig(
            command=parser[s].get(self.CV_IPMI_COMMAND, "/usr/bin/ipmitool"),
            fan_mode_delay=fan_mode_delay,
            fan_level_delay=fan_level_delay,
            remote_parameters=parser[s].get(self.CV_IPMI_REMOTE_PARAMETERS, fallback=""),
            platform_name=parser[s].get(self.CV_IPMI_PLATFORM_NAME, fallback="auto"),
        )

    def _parse_cpu_sections(self, parser: ConfigParser) -> List[CpuConfig]:
        """Parse [CPU], [CPU:0], [CPU:1] ... sections.
        Args:
            parser (ConfigParser): configuration parser
        Returns:
            List[CpuConfig]: list of parsed CPU configurations
        Raises:
            ValueError: invalid configuration parameters
        """
        result = []
        for s in self._get_sections(parser, self.CS_CPU):
            cfg = CpuConfig(
                section=s,
                enabled=parser[s].getboolean(self.CV_ENABLED, fallback=False),
                ipmi_zone=self.parse_ipmi_zones(parser[s].get(self.CV_IPMI_ZONE, str(self.CPU_ZONE))),
                temp_calc=parser[s].getint(self.CV_TEMP_CALC, fallback=self.CALC_AVG),
                steps=parser[s].getint(self.CV_STEPS, fallback=6),
                sensitivity=parser[s].getfloat(self.CV_SENSITIVITY, fallback=3.0),
                polling=parser[s].getfloat(self.CV_POLLING, fallback=2.0),
                min_temp=parser[s].getfloat(self.CV_MIN_TEMP, fallback=30.0),
                max_temp=parser[s].getfloat(self.CV_MAX_TEMP, fallback=60.0),
                min_level=parser[s].getint(self.CV_MIN_LEVEL, fallback=35),
                max_level=parser[s].getint(self.CV_MAX_LEVEL, fallback=100),
                smoothing=parser[s].getint(self.CV_SMOOTHING, fallback=1),
            )
            self._validate_fan_controller_config(cfg, s)
            result.append(cfg)
        return result

    def _parse_hd_sections(self, parser: ConfigParser) -> List[HdConfig]:
        """Parse [HD], [HD:0], [HD:1] ... sections.
        Args:
            parser (ConfigParser): configuration parser
        Returns:
            List[HdConfig]: list of parsed HD configurations
        Raises:
            ValueError: invalid configuration parameters
        """
        result = []
        for s in self._get_sections(parser, self.CS_HD):
            enabled = parser[s].getboolean(self.CV_ENABLED, fallback=False)
            hd_names_str = parser[s].get(self.CV_HD_NAMES, "")
            hd_names = self.parse_device_names(hd_names_str) if hd_names_str else []
            # Validate hd_names is specified when enabled
            if enabled and not hd_names:
                raise ValueError(f"[{s}] {self.CV_HD_NAMES} is not specified")
            for name in hd_names:
                if "nvme" in name.lower():
                    raise ValueError(f"NVMe drives are not allowed in [{s}], use [NVME] instead: '{name}'")
            standby_guard_enabled = parser[s].getboolean(self.CV_HD_STANDBY_GUARD_ENABLED, fallback=False)
            standby_hd_limit = parser[s].getint(self.CV_HD_STANDBY_HD_LIMIT, fallback=1)
            if standby_guard_enabled and standby_hd_limit < 0:
                raise ValueError(f"[{s}] {self.CV_HD_STANDBY_HD_LIMIT} < 0")
            cfg = HdConfig(
                section=s,
                enabled=enabled,
                ipmi_zone=self.parse_ipmi_zones(parser[s].get(self.CV_IPMI_ZONE, str(self.HD_ZONE))),
                temp_calc=parser[s].getint(self.CV_TEMP_CALC, fallback=self.CALC_AVG),
                steps=parser[s].getint(self.CV_STEPS, fallback=4),
                sensitivity=parser[s].getfloat(self.CV_SENSITIVITY, fallback=2.0),
                polling=parser[s].getfloat(self.CV_POLLING, fallback=10.0),
                min_temp=parser[s].getfloat(self.CV_MIN_TEMP, fallback=32.0),
                max_temp=parser[s].getfloat(self.CV_MAX_TEMP, fallback=46.0),
                min_level=parser[s].getint(self.CV_MIN_LEVEL, fallback=35),
                max_level=parser[s].getint(self.CV_MAX_LEVEL, fallback=100),
                smoothing=parser[s].getint(self.CV_SMOOTHING, fallback=1),
                hd_names=hd_names,
                smartctl_path=parser[s].get(self.CV_HD_SMARTCTL_PATH, "/usr/sbin/smartctl"),
                standby_guard_enabled=standby_guard_enabled,
                standby_hd_limit=standby_hd_limit,
            )
            self._validate_fan_controller_config(cfg, s)
            result.append(cfg)
        return result

    def _parse_nvme_sections(self, parser: ConfigParser) -> List[NvmeConfig]:
        """Parse [NVME], [NVME:0], [NVME:1] ... sections.
        Args:
            parser (ConfigParser): configuration parser
        Returns:
            List[NvmeConfig]: list of parsed NVME configurations
        Raises:
            ValueError: invalid configuration parameters
        """
        result = []
        for s in self._get_sections(parser, self.CS_NVME):
            enabled = parser[s].getboolean(self.CV_ENABLED, fallback=False)
            nvme_names_str = parser[s].get(self.CV_NVME_NAMES, "")
            nvme_names = self.parse_device_names(nvme_names_str) if nvme_names_str else []
            # Validate nvme_names is specified when enabled
            if enabled and not nvme_names:
                raise ValueError(f"[{s}] {self.CV_NVME_NAMES} is not specified")
            cfg = NvmeConfig(
                section=s,
                enabled=enabled,
                ipmi_zone=self.parse_ipmi_zones(parser[s].get(self.CV_IPMI_ZONE, str(self.HD_ZONE))),
                temp_calc=parser[s].getint(self.CV_TEMP_CALC, fallback=self.CALC_AVG),
                steps=parser[s].getint(self.CV_STEPS, fallback=4),
                sensitivity=parser[s].getfloat(self.CV_SENSITIVITY, fallback=2.0),
                polling=parser[s].getfloat(self.CV_POLLING, fallback=10.0),
                min_temp=parser[s].getfloat(self.CV_MIN_TEMP, fallback=35.0),
                max_temp=parser[s].getfloat(self.CV_MAX_TEMP, fallback=70.0),
                min_level=parser[s].getint(self.CV_MIN_LEVEL, fallback=35),
                max_level=parser[s].getint(self.CV_MAX_LEVEL, fallback=100),
                smoothing=parser[s].getint(self.CV_SMOOTHING, fallback=1),
                nvme_names=nvme_names,
            )
            self._validate_fan_controller_config(cfg, s)
            result.append(cfg)
        return result

    def _parse_gpu_sections(self, parser: ConfigParser) -> List[GpuConfig]:
        """Parse [GPU], [GPU:0], [GPU:1] ... sections.
        Args:
            parser (ConfigParser): configuration parser
        Returns:
            List[GpuConfig]: list of parsed GPU configurations
        Raises:
            ValueError: invalid configuration parameters
        """
        result = []
        for s in self._get_sections(parser, self.CS_GPU):
            gpu_type = parser[s].get(self.CV_GPU_TYPE, "nvidia").lower()
            if gpu_type not in ["nvidia", "amd"]:
                raise ValueError(f"[{s}] invalid value: {self.CV_GPU_TYPE}={gpu_type}.")
            amd_temp_sensor = parser[s].getint(self.CV_GPU_AMD_TEMP_SENSOR, fallback=0)
            if amd_temp_sensor not in range(0, 3):
                raise ValueError(f"[{s}] invalid value: {self.CV_GPU_AMD_TEMP_SENSOR}={amd_temp_sensor}.")
            cfg = GpuConfig(
                section=s,
                enabled=parser[s].getboolean(self.CV_ENABLED, fallback=False),
                ipmi_zone=self.parse_ipmi_zones(parser[s].get(self.CV_IPMI_ZONE, str(self.HD_ZONE))),
                temp_calc=parser[s].getint(self.CV_TEMP_CALC, fallback=self.CALC_AVG),
                steps=parser[s].getint(self.CV_STEPS, fallback=5),
                sensitivity=parser[s].getfloat(self.CV_SENSITIVITY, fallback=2.0),
                polling=parser[s].getfloat(self.CV_POLLING, fallback=2.0),
                min_temp=parser[s].getfloat(self.CV_MIN_TEMP, fallback=40.0),
                max_temp=parser[s].getfloat(self.CV_MAX_TEMP, fallback=70.0),
                min_level=parser[s].getint(self.CV_MIN_LEVEL, fallback=35),
                max_level=parser[s].getint(self.CV_MAX_LEVEL, fallback=100),
                smoothing=parser[s].getint(self.CV_SMOOTHING, fallback=1),
                gpu_type=gpu_type,
                gpu_device_ids=self.parse_gpu_ids(parser[s].get(self.CV_GPU_IDS, "0")),
                nvidia_smi_path=parser[s].get(self.CV_GPU_NVIDIA_SMI_PATH, "/usr/bin/nvidia-smi"),
                rocm_smi_path=parser[s].get(self.CV_GPU_ROCM_SMI_PATH, "/usr/bin/rocm-smi"),
                amd_temp_sensor=amd_temp_sensor,
            )
            self._validate_fan_controller_config(cfg, s)
            result.append(cfg)
        return result

    def _parse_const_sections(self, parser: ConfigParser) -> List[ConstConfig]:
        """Parse [CONST], [CONST:0], [CONST:1] ... sections.
        Args:
            parser (ConfigParser): configuration parser
        Returns:
            List[ConstConfig]: list of parsed CONST configurations
        Raises:
            ValueError: invalid configuration parameters
        """
        result = []
        for s in self._get_sections(parser, self.CS_CONST):
            polling = parser[s].getfloat(self.CV_POLLING, fallback=30.0)
            if polling < 0:
                raise ValueError(f"[{s}] {self.CV_POLLING} < 0")
            level = parser[s].getint(self.CV_CONST_LEVEL, fallback=50)
            if level not in range(0, 101):
                raise ValueError(f"[{s}] invalid {self.CV_CONST_LEVEL}")
            result.append(ConstConfig(
                section=s,
                enabled=parser[s].getboolean(self.CV_ENABLED, fallback=False),
                ipmi_zone=self.parse_ipmi_zones(parser[s].get(self.CV_IPMI_ZONE, str(self.HD_ZONE))),
                polling=polling,
                level=level,
            ))
        return result

    def _validate_fan_controller_config(self, cfg, section: str) -> None:
        """Validate common fan controller configuration parameters.
        Args:
            cfg: configuration dataclass (CpuConfig, HdConfig, NvmeConfig, or GpuConfig)
            section (str): section name for error messages
        Raises:
            ValueError: invalid configuration parameters
        """
        if cfg.temp_calc not in {self.CALC_MIN, self.CALC_AVG, self.CALC_MAX}:
            raise ValueError(f"[{section}] invalid value: {self.CV_TEMP_CALC} ({cfg.temp_calc}).")
        if cfg.steps <= 0:
            raise ValueError(f"[{section}] invalid value: {self.CV_STEPS} <= 0")
        if cfg.sensitivity <= 0:
            raise ValueError(f"[{section}] invalid value: {self.CV_SENSITIVITY} <= 0")
        if cfg.polling < 0:
            raise ValueError(f"[{section}] {self.CV_POLLING} < 0")
        if cfg.max_temp < cfg.min_temp:
            raise ValueError(f"[{section}] invalid value: {self.CV_MAX_TEMP} < {self.CV_MIN_TEMP}")
        if cfg.max_level < cfg.min_level:
            raise ValueError(f"[{section}] invalid value: {self.CV_MAX_LEVEL} < {self.CV_MIN_LEVEL}")
        if cfg.smoothing < 1:
            raise ValueError(f"[{section}] invalid value: {self.CV_SMOOTHING} < 1")


# End.
