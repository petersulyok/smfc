#!/usr/bin/env python3
#
#   test_config_builders.py (C) 2022-2026, Peter Sulyok
#   Stateless builders for smfc config dataclasses used by unit tests.
#
#   Each `create_*_config(...)` returns a fully-populated config instance with defaults sourced from
#   `Config.DV_*` constants, so a test can write e.g. `create_cpu_config(steps=4)` without touching a
#   real config file. The module is intentionally stateless: no temp dirs, no fixtures, no lifecycle.
#
from smfc.config import (Config, IpmiConfig, CpuConfig, HdConfig, NvmeConfig, GpuConfig, ConstConfig)


def create_ipmi_config(command=Config.DV_IPMI_COMMAND, fan_mode_delay=Config.DV_IPMI_FAN_MODE_DELAY,
                       fan_level_delay=Config.DV_IPMI_FAN_LEVEL_DELAY,
                       remote_parameters=Config.DV_IPMI_REMOTE_PARAMETERS,
                       platform_name=Config.DV_IPMI_PLATFORM_NAME,
                       enforce_fan_mode=Config.DV_IPMI_ENFORCE_FAN_MODE):
    """Factory function to create IpmiConfig instances for testing without needing a config file.

    Args:
        command (str): Full path for ipmitool command (default: "/usr/bin/ipmitool")
        fan_mode_delay (int): Delay time after execution of IPMI set fan mode function (default: 10)
        fan_level_delay (int): Delay time after execution of IPMI set fan level function (default: 2)
        remote_parameters (str): Remote IPMI parameters (default: "")
        platform_name (str): Platform name (default: "auto")
        enforce_fan_mode (bool): Re-assert FULL fan mode on BMC drift (default: True)

    Returns:
        IpmiConfig: configured IpmiConfig instance
    """
    return IpmiConfig(command=command, fan_mode_delay=fan_mode_delay, fan_level_delay=fan_level_delay,
                      remote_parameters=remote_parameters, platform_name=platform_name,
                      enforce_fan_mode=enforce_fan_mode)


def create_cpu_config(section="CPU", enabled=False, ipmi_zone=None, temp_calc=Config.CALC_AVG,
                      steps=Config.DV_CPU_STEPS, sensitivity=Config.DV_CPU_SENSITIVITY,
                      polling=Config.DV_CPU_POLLING, min_temp=Config.DV_CPU_MIN_TEMP,
                      max_temp=Config.DV_CPU_MAX_TEMP, min_level=Config.DV_CPU_MIN_LEVEL,
                      max_level=Config.DV_CPU_MAX_LEVEL, smoothing=Config.DV_CPU_SMOOTHING,
                      control_function=None):
    """Factory function to create CpuConfig instances for testing without needing a config file.

    Args:
        section (str): section name (default: "CPU")
        enabled (bool): fan controller enabled flag (default: False)
        ipmi_zone (list): IPMI zones (default: [0])
        temp_calc (int): temperature calculation method (default: 1 = avg)
        steps (int): discrete steps (default: 6) - matches Config._parse_cpu_sections
        sensitivity (float): temperature change sensitivity (default: 3.0) - matches Config._parse_cpu_sections
        polling (float): polling interval (default: 2.0)
        min_temp (float): minimum temperature (default: 30.0)
        max_temp (float): maximum temperature (default: 60.0) - matches Config._parse_cpu_sections
        min_level (int): minimum fan level (default: 35)
        max_level (int): maximum fan level (default: 100)
        smoothing (int): smoothing window size (default: 1)

    Returns:
        CpuConfig: configured CpuConfig instance
    """
    zones = ipmi_zone if ipmi_zone is not None else [Config.CPU_ZONE]
    return CpuConfig(section=section, enabled=enabled, ipmi_zone=zones,
                     temp_calc=temp_calc, steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                     max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing,
                     control_function=control_function if control_function is not None else [])


def create_hd_config(section="HD", enabled=False, ipmi_zone=None, temp_calc=Config.CALC_AVG,
                     steps=Config.DV_HD_STEPS, sensitivity=Config.DV_HD_SENSITIVITY,
                     polling=Config.DV_HD_POLLING, min_temp=Config.DV_HD_MIN_TEMP,
                     max_temp=Config.DV_HD_MAX_TEMP, min_level=Config.DV_HD_MIN_LEVEL,
                     max_level=Config.DV_HD_MAX_LEVEL, smoothing=Config.DV_HD_SMOOTHING, hd_names=None,
                     smartctl_path=Config.DV_HD_SMARTCTL_PATH, standby_guard_enabled=False,
                     standby_hd_limit=Config.DV_HD_STANDBY_HD_LIMIT, control_function=None):
    """Factory function to create HdConfig instances for testing without needing a config file.

    Args:
        section (str): section name (default: "HD")
        enabled (bool): fan controller enabled flag (default: False)
        ipmi_zone (list): IPMI zones (default: [1])
        temp_calc (int): temperature calculation method (default: 1 = avg)
        steps (int): discrete steps (default: 4)
        sensitivity (float): temperature change sensitivity (default: 2.0)
        polling (float): polling interval (default: 10.0)
        min_temp (float): minimum temperature (default: 32.0)
        max_temp (float): maximum temperature (default: 46.0)
        min_level (int): minimum fan level (default: 35)
        max_level (int): maximum fan level (default: 100)
        smoothing (int): smoothing window size (default: 1)
        hd_names (list): HD device names (default: [])
        smartctl_path (str): path to smartctl (default: "/usr/sbin/smartctl")
        standby_guard_enabled (bool): standby guard flag (default: False)
        standby_hd_limit (int): standby HD limit (default: 1)

    Returns:
        HdConfig: configured HdConfig instance
    """
    zones = ipmi_zone if ipmi_zone is not None else [Config.HD_ZONE]
    return HdConfig(section=section, enabled=enabled, ipmi_zone=zones,
                    temp_calc=temp_calc, steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                    max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing,
                    hd_names=hd_names if hd_names is not None else [], smartctl_path=smartctl_path,
                    standby_guard_enabled=standby_guard_enabled, standby_hd_limit=standby_hd_limit,
                    control_function=control_function if control_function is not None else [])


def create_nvme_config(section="NVME", enabled=False, ipmi_zone=None, temp_calc=Config.CALC_AVG,
                       steps=Config.DV_NVME_STEPS, sensitivity=Config.DV_NVME_SENSITIVITY,
                       polling=Config.DV_NVME_POLLING, min_temp=Config.DV_NVME_MIN_TEMP,
                       max_temp=Config.DV_NVME_MAX_TEMP, min_level=Config.DV_NVME_MIN_LEVEL,
                       max_level=Config.DV_NVME_MAX_LEVEL, smoothing=Config.DV_NVME_SMOOTHING,
                       nvme_names=None, control_function=None):
    """Factory function to create NvmeConfig instances for testing without needing a config file.

    Args:
        section (str): section name (default: "NVME")
        enabled (bool): fan controller enabled flag (default: False)
        ipmi_zone (list): IPMI zones (default: [1])
        temp_calc (int): temperature calculation method (default: 1 = avg)
        steps (int): discrete steps (default: 4)
        sensitivity (float): temperature change sensitivity (default: 2.0)
        polling (float): polling interval (default: 10.0)
        min_temp (float): minimum temperature (default: 35.0)
        max_temp (float): maximum temperature (default: 70.0)
        min_level (int): minimum fan level (default: 35)
        max_level (int): maximum fan level (default: 100)
        smoothing (int): smoothing window size (default: 1)
        nvme_names (list): NVMe device names (default: [])

    Returns:
        NvmeConfig: configured NvmeConfig instance
    """
    zones = ipmi_zone if ipmi_zone is not None else [Config.HD_ZONE]
    return NvmeConfig(section=section, enabled=enabled, ipmi_zone=zones,
                      temp_calc=temp_calc, steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                      max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing,
                      nvme_names=nvme_names if nvme_names is not None else [],
                      control_function=control_function if control_function is not None else [])


def create_gpu_config(section="GPU", enabled=False, ipmi_zone=None, temp_calc=Config.CALC_AVG,
                      steps=Config.DV_GPU_STEPS, sensitivity=Config.DV_GPU_SENSITIVITY,
                      polling=Config.DV_GPU_POLLING, min_temp=Config.DV_GPU_MIN_TEMP,
                      max_temp=Config.DV_GPU_MAX_TEMP, min_level=Config.DV_GPU_MIN_LEVEL,
                      max_level=Config.DV_GPU_MAX_LEVEL, smoothing=Config.DV_GPU_SMOOTHING,
                      gpu_type=Config.DV_GPU_TYPE, gpu_device_ids=None,
                      nvidia_smi_path=Config.DV_GPU_NVIDIA_SMI_PATH, rocm_smi_path=Config.DV_GPU_ROCM_SMI_PATH,
                      amd_temp_sensor=Config.DV_GPU_AMD_TEMP_SENSOR, control_function=None):
    """Factory function to create GpuConfig instances for testing without needing a config file.

    Args:
        section (str): section name (default: "GPU")
        enabled (bool): fan controller enabled flag (default: False)
        ipmi_zone (list): IPMI zones (default: [1])
        temp_calc (int): temperature calculation method (default: 1 = avg)
        steps (int): discrete steps (default: 5)
        sensitivity (float): temperature change sensitivity (default: 2.0)
        polling (float): polling interval (default: 2.0)
        min_temp (float): minimum temperature (default: 40.0)
        max_temp (float): maximum temperature (default: 70.0)
        min_level (int): minimum fan level (default: 35)
        max_level (int): maximum fan level (default: 100)
        smoothing (int): smoothing window size (default: 1)
        gpu_type (str): GPU type - "nvidia" or "amd" (default: "nvidia")
        gpu_device_ids (list): GPU device IDs (default: [0])
        nvidia_smi_path (str): path to nvidia-smi (default: "/usr/bin/nvidia-smi")
        rocm_smi_path (str): path to rocm-smi (default: "/usr/bin/rocm-smi")
        amd_temp_sensor (int): AMD temperature sensor index (default: 0)

    Returns:
        GpuConfig: configured GpuConfig instance
    """
    zones = ipmi_zone if ipmi_zone is not None else [Config.HD_ZONE]
    device_ids = gpu_device_ids if gpu_device_ids is not None else Config.parse_gpu_ids(Config.DV_GPU_DEVICE_IDS)
    return GpuConfig(section=section, enabled=enabled, ipmi_zone=zones,
                     temp_calc=temp_calc, steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                     max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing,
                     gpu_type=gpu_type, gpu_device_ids=device_ids,
                     nvidia_smi_path=nvidia_smi_path, rocm_smi_path=rocm_smi_path, amd_temp_sensor=amd_temp_sensor,
                     control_function=control_function if control_function is not None else [])


def create_const_config(section="CONST", enabled=False, ipmi_zone=None, polling=Config.DV_CONST_POLLING,
                        level=Config.DV_CONST_LEVEL):
    """Factory function to create ConstConfig instances for testing without needing a config file.

    Args:
        section (str): section name (default: "CONST")
        enabled (bool): fan controller enabled flag (default: False)
        ipmi_zone (list): IPMI zones (default: [1])
        polling (float): polling interval (default: 30.0)
        level (int): constant fan level 0-100 (default: 50)

    Returns:
        ConstConfig: configured ConstConfig instance
    """
    zones = ipmi_zone if ipmi_zone is not None else [Config.HD_ZONE]
    return ConstConfig(section=section, enabled=enabled, ipmi_zone=zones,
                       polling=polling, level=level)


# End.
