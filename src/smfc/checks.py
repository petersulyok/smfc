#
#   checks.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.checks: run-time dependency checks, reported per section.
#
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence

from smfc.config import Config, CpuConfig, GpuConfig, HdConfig, IpmiConfig, NpuConfig

# Path of the kernel module list.
PROC_MODULES: str = "/proc/modules"

# Kernel modules that report a CPU temperature. One of them must be loaded.
CPU_MODULES: tuple = ("coretemp", "k10temp")

# Kernel module that reports a SATA or SAS disk temperature without smartctl.
HD_MODULE: str = "drivetemp"


class Level(str, Enum):
    """Severity of a check result."""
    ERROR = "error"     # smfc cannot run in this state
    WARN = "warn"       # smfc runs, and this is probably not what the user meant
    INFO = "info"       # an observation, for example a detected device no section covers


@dataclass(frozen=True)
class CheckResult:
    """One finding of one check."""
    level: Level        # Severity of the finding
    section: str        # Section it belongs to (e.g. "Ipmi", "HD:1")
    message: str        # What is wrong, in one line
    fix: str = ""       # One line the user can act on, empty if there is nothing to suggest


def loaded_modules(path: str = PROC_MODULES) -> str:
    """Read the list of loaded kernel modules.
    Args:
        path (str): path of the module list (default: /proc/modules)
    Returns:
        str: the raw content of the file
    """
    with open(path, "rt", encoding="utf-8") as file:
        return file.read()


def _command_found(path: str) -> bool:
    """Check that a command exists, whether it is named by a path or by a bare name.
    A bare name is looked up on PATH, which is how `npu_smi_path=npu-smi` is meant to work.
    Args:
        path (str): path or bare name of the command
    Returns:
        bool: True if the command was found
    """
    if os.path.isabs(path):
        return os.path.exists(path)
    return shutil.which(path) is not None


def check_ipmi(cfg: IpmiConfig) -> List[CheckResult]:
    """Check the run-time dependencies of the [Ipmi] section.
    Args:
        cfg (IpmiConfig): parsed [Ipmi] configuration
    Returns:
        List[CheckResult]: the findings, empty if there are none
    """
    if os.path.exists(cfg.command):
        return []
    return [CheckResult(Level.ERROR, Config.CS_IPMI,
                        f"ERROR: ipmitool command cannot be found {cfg.command}!",
                        f"install ipmitool, or set [Ipmi] {Config.CV_IPMI_COMMAND}= to its path")]


def check_cpu(configs: Sequence[CpuConfig], modules: str) -> List[CheckResult]:
    """Check the run-time dependencies of the CPU fan controller sections.
    The check belongs to the family rather than to one section: a single loaded module serves every
    instance, so one missing module is one finding.
    Args:
        configs (Sequence[CpuConfig]): parsed CPU configurations
        modules (str): content of /proc/modules
    Returns:
        List[CheckResult]: the findings, empty if there are none
    """
    enabled = [cfg for cfg in configs if cfg.enabled]
    if not enabled:
        return []
    if any(name in modules for name in CPU_MODULES):
        return []
    return [CheckResult(Level.ERROR, enabled[0].section,
                        "ERROR: coretemp or k10temp kernel module must be loaded!",
                        "load it with `modprobe coretemp` on Intel, or `modprobe k10temp` on AMD")]


def check_hd(configs: Sequence[HdConfig], modules: str) -> List[CheckResult]:
    """Check the run-time dependencies of the HD fan controller sections.
    Each instance is checked on its own, because each one names its own smartctl command.
    Args:
        configs (Sequence[HdConfig]): parsed HD configurations
        modules (str): content of /proc/modules
    Returns:
        List[CheckResult]: the findings, empty if there are none
    """
    results: List[CheckResult] = []
    no_drivetemp = HD_MODULE not in modules
    for cfg in configs:
        if not cfg.enabled:
            continue
        no_smartctl = not os.path.exists(cfg.smartctl_path)
        if no_smartctl and no_drivetemp:
            results.append(CheckResult(
                Level.ERROR, cfg.section,
                f"ERROR: drivetemp kernel module must be loaded or smartctl command "
                f"({cfg.smartctl_path}) must be installed!",
                "load it with `modprobe drivetemp`, or install smartmontools"))
        if cfg.standby_guard_enabled and no_smartctl:
            results.append(CheckResult(
                Level.ERROR, cfg.section,
                f"ERROR: smartctl command ({cfg.smartctl_path}) must be installed for Standby Guard "
                f"feature!",
                f"install smartmontools, or turn [{cfg.section}] "
                f"{Config.CV_HD_STANDBY_GUARD_ENABLED}= off"))
    return results


def check_gpu(configs: Sequence[GpuConfig]) -> List[CheckResult]:
    """Check the run-time dependencies of the GPU fan controller sections.
    The command it needs follows gpu_type=: nvidia-smi for nvidia, rocm-smi for amd.
    Args:
        configs (Sequence[GpuConfig]): parsed GPU configurations
    Returns:
        List[CheckResult]: the findings, empty if there are none
    """
    results: List[CheckResult] = []
    for cfg in configs:
        if not cfg.enabled:
            continue
        nvidia = cfg.gpu_type == "nvidia"
        path = cfg.nvidia_smi_path if nvidia else cfg.rocm_smi_path
        key = Config.CV_GPU_NVIDIA_SMI_PATH if nvidia else Config.CV_GPU_ROCM_SMI_PATH
        if not os.path.exists(path):
            results.append(CheckResult(
                Level.ERROR, cfg.section, f"ERROR: {path} command cannot be found!",
                f"install the vendor tool, or set [{cfg.section}] {key}= to its path"))
    return results


def check_npu(configs: Sequence[NpuConfig]) -> List[CheckResult]:
    """Check the run-time dependencies of the NPU fan controller sections.
    npu_smi_path= may be an absolute path or a bare command name looked up on PATH.
    Args:
        configs (Sequence[NpuConfig]): parsed NPU configurations
    Returns:
        List[CheckResult]: the findings, empty if there are none
    """
    results: List[CheckResult] = []
    for cfg in configs:
        if not cfg.enabled:
            continue
        if not _command_found(cfg.npu_smi_path):
            results.append(CheckResult(
                Level.ERROR, cfg.section, f"ERROR: {cfg.npu_smi_path} command cannot be found!",
                f"install the Ascend toolkit, or set [{cfg.section}] {Config.CV_NPU_SMI_PATH}= to "
                f"its path"))
    return results


def check_all(config: Config, modules: Optional[str] = None) -> List[CheckResult]:
    """Run every run-time dependency check of a parsed configuration.
    Every section is checked, so the caller sees all the findings at once rather than the first one.
    Args:
        config (Config): parsed configuration
        modules (Optional[str]): content of /proc/modules, read from the system when omitted
    Returns:
        List[CheckResult]: the findings of every section, empty if there are none
    """
    if modules is None:
        modules = loaded_modules()
    results: List[CheckResult] = []
    results.extend(check_ipmi(config.ipmi))
    results.extend(check_cpu(config.cpu, modules))
    results.extend(check_hd(config.hd, modules))
    results.extend(check_gpu(config.gpu))
    results.extend(check_npu(config.npu))
    return results


def check_by_section(config: Config, modules: Optional[str] = None) -> Dict[str, List[CheckResult]]:
    """Run every check and group the findings by the section they belong to.
    Args:
        config (Config): parsed configuration
        modules (Optional[str]): content of /proc/modules, read from the system when omitted
    Returns:
        Dict[str, List[CheckResult]]: findings per section name, sections without a finding omitted
    """
    grouped: Dict[str, List[CheckResult]] = {}
    for result in check_all(config, modules):
        grouped.setdefault(result.section, []).append(result)
    return grouped


def errors(results: Sequence[CheckResult]) -> List[CheckResult]:
    """Filter the findings that stop smfc from running.
    Args:
        results (Sequence[CheckResult]): findings of one or more checks
    Returns:
        List[CheckResult]: the findings of ERROR severity
    """
    return [r for r in results if r.level is Level.ERROR]


def error_text(results: Sequence[CheckResult]) -> str:
    """Render every error of a check run as one message, one finding per line.
    Args:
        results (Sequence[CheckResult]): findings of one or more checks
    Returns:
        str: the error messages, empty if there is no error
    """
    return "\n".join(r.message for r in errors(results))


# End.
