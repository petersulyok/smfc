#!/usr/bin/env python3
#
#   test_data.py (C) 2022-2026, Peter Sulyok
#   Test data handling class for unit tests.
#
import configparser
import json
import os
import random
import shutil
import tempfile
from typing import List
from pyudev import DeviceNotFoundByFileError
from smfc.config import Config


class TestData:
    """Class for test data handling."""

    td_dir: str = ""  # Test data directory
    cpu_files: List[str] = []  # CPU hwmon files

    hd_names: str  # HD names in configuration parameter form
    hd_name_list: List[str] = []  # HD names in a list
    hd_files: List[str] = []  # HD hwmon files

    nvme_names: str  # NVMe names in configuration parameter form
    nvme_name_list: List[str] = []  # NVMe names in a list
    nvme_files: List[str] = []  # NVMe hwmon files

    def __init__(self):
        """Initialize the class. It creates a temporary directory."""
        self.td_dir = tempfile.mkdtemp()

    def __del__(self):
        """It deletes the temporary directory with is all content."""
        shutil.rmtree(self.td_dir)

    def create_cpu_data(self, count: int, temp_list: List[float] = None) -> None:
        """Generic method to create temporary test data files (similarly to hwmon naming convention and content)."""
        hwmon_file: str

        self.cpu_files = []
        for i in range(count):
            hwmon_file = os.path.join(self.td_dir, "cpu", "coretemp." + str(i), "hwmon")
            os.makedirs(hwmon_file, exist_ok=True)
            hwmon_file = os.path.join(hwmon_file, "temp1_input")
            with open(hwmon_file, "w+t", encoding="UTF-8") as f:
                if temp_list:
                    v = temp_list[i]
                else:
                    v = random.uniform(30.0, 60.0)
                f.write(str(v * 1000))
            self.cpu_files.append(hwmon_file)

    def create_hd_data(self, count: int, temp_list: List[float] = None) -> None:
        """Generic method to create temporary test data files (similarly to hwmon naming convention and content)."""
        letters: List[str] = [
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "q",
        ]
        hwmon_path: str
        disk_name: str

        self.hd_names = ""
        self.hd_name_list = []
        self.hd_files = []
        separator = random.choice([" ", "\n"])
        for i in range(count):
            disk_name = "/dev/sd" + letters[i]
            self.hd_names += disk_name + separator
            self.hd_name_list.append(disk_name)
            hwmon_path = os.path.join(self.td_dir, "disks", str(i) + ":0:0:0", "hwmon")
            os.makedirs(hwmon_path, exist_ok=True)
            hwmon_path = os.path.join(hwmon_path, "temp1_input")
            with open(hwmon_path, "w+t", encoding="UTF-8") as f:
                if temp_list:
                    v = temp_list[i]
                else:
                    v = random.uniform(32.0, 45.0)
                v *= 1000
                f.write(f"{v:.0f}")
            self.hd_files.append(hwmon_path)

    def create_nvme_data(self, count: int, temp_list: List[float] = None) -> None:
        """Generic method to create temporary test data files for NVMe devices
        (similarly to hwmon naming convention and content)."""
        hwmon_path: str
        device_name: str

        self.nvme_names = ""
        self.nvme_name_list = []
        self.nvme_files = []
        separator = random.choice([" ", "\n"])
        for i in range(count):
            device_name = f"/dev/nvme{i}n1"
            self.nvme_names += device_name + separator
            self.nvme_name_list.append(device_name)
            hwmon_path = os.path.join(self.td_dir, "nvme", str(i), "hwmon")
            os.makedirs(hwmon_path, exist_ok=True)
            hwmon_path = os.path.join(hwmon_path, "temp1_input")
            with open(hwmon_path, "w+t", encoding="UTF-8") as f:
                if temp_list:
                    v = temp_list[i]
                else:
                    v = random.uniform(30.0, 50.0)
                v *= 1000
                f.write(f"{v:.0f}")
            self.nvme_files.append(hwmon_path)

    def create_config_file(self, my_config: configparser.ConfigParser) -> str:
        """Creates a config file from a ConfigParser object."""
        h, name = tempfile.mkstemp(prefix="config", suffix=".conf", dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            my_config.write(f)
        return name

    def create_command_file(self, content: str = "echo OK") -> str:
        """Creates an executable bash script."""
        h, name = tempfile.mkstemp(suffix=".sh", dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            f.write(str("#!/bin/bash\n"))
            f.write(str(content + "\n"))
        os.system("chmod +x " + name)
        return name

    @staticmethod
    def delete_file(path: str) -> None:
        """Deletes the specified file."""
        os.remove(path)

    def create_ipmi_command(self) -> str:
        """Creates a bash script emulating ipmitool."""
        return self.create_command_file("""
# ipmitool emulation

if [[ $1 = "sdr" ]] ; then
	echo OK
	exit 0
fi

if [[ $1 = "bmc" && $2 = "info" ]] ; then
    cat << 'BMCEOF'
Device ID                 : 32
Device Revision           : 1
Firmware Revision         : 1.74
IPMI Version              : 2.0
Manufacturer ID           : 10876
Manufacturer Name         : Super Micro Computer Inc.
Product ID                : 6929 (0x1b11)
Product Name              : X11SCH-LN4F
Device Available          : yes
Provides Device SDRs      : yes
BMCEOF
    exit 0
fi

# IPMI get fan mode (raw 0x30 0x45 0x00)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x45" && $4 = "0x00" ]] ; then
  r=$((1 + (RANDOM % 4)))
  if [[ "$r" -eq "3" ]] ; then
    r=1
  fi
	echo "$r"
	exit 0
fi

# IPMI set fan mode (raw 0x30 0x45 0x01)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x45" && $4 = "0x01" ]] ; then
	exit 0
fi

# IPMI get fan level (raw 0x30 0x70 0x66 0x00)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x70" && $4 = "0x66" && $5 = "0x00" ]] ; then
	echo " 32"
	exit 0
fi

# IPMI set fan level (raw 0x30 0x70 0x66 0x01)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x70" && $4 = "0x66" && $5 = "0x01" ]] ; then
	exit 0
fi
        """)

    def create_smart_command(self) -> str:
        """Creates a shell script emulating `smartctl`."""
        return self.create_command_file("""
# smartctl emulation script.

# Print header
cat << EOF
smartctl 7.3 2022-02-28 r5338 [x86_64-linux-6.1.0-32-amd64] (local build)
Copyright (C) 2002-22, Bruce Allen, Christian Franke, www.smartmontools.org

EOF

# smartctl -a /dev/sd?
if [[ $1 = "-a" ]] ; then
    r=$((RANDOM % 3))	
    case "$r" in 
        "0")
            echo "Current Drive Temperature:     37 C" ;;
        "1")
            echo "190 Airflow_Temperature_Cel 0x0032   075   045   000    Old_age   Always       -       25" ;;
        "2")
            echo "194 Temperature_Celsius     0x0002   232   232   000    Old_age   Always       -       28 (Min/Max 17/45)" ;;
    esac
fi

# smartctl -i -n standby /dev/sd?
if [[ $1 = "-i" && $2 = "-n" && $3 = "standby" ]] ; then
    r=$((RANDOM % 2))	
    case "$r" in 
        "0")
            cat << EOF
=== START OF INFORMATION SECTION ===
Model Family:     Samsung based SSDs
Device Model:     Samsung SSD 870 QVO 8TB
Serial Number:    S5SSNG1NB01829M
LU WWN Device Id: 5 002538 f70b0ee2f
Firmware Version: SVQ01B6Q
User Capacity:    8,001,563,222,016 bytes [8.00 TB]
Sector Size:      512 bytes logical/physical
Rotation Rate:    Solid State Device
Form Factor:      2.5 inches
TRIM Command:     Available, deterministic, zeroed
Device is:        In smartctl database [for details use: -P show]
ATA Version is:   ACS-4 T13/BSR INCITS 529 revision 5
SATA Version is:  SATA 3.3, 6.0 Gb/s (current: 6.0 Gb/s)
Local Time is:    Sat May 15 14:26:26 2021 CEST
SMART support is: Available - device has SMART capability.
SMART support is: Enabled
Power mode is:    ACTIVE or IDLE
EOF
            r=0 ;;
            
        "1")
            cat << EOF
Device is in STANDBY mode, exit(2)
EOF
            r=2 ;;            
    esac
    exit $r
fi

# smartctl -s standby,now /dev/sd?
if [[ $1 = "-s" && $2 = "standby,now" ]] ; then
    echo "Device placed in STANDBY mode"
    exit 0  
fi

exit 0
""")

    def update_hwmon_temperatures(self, files: List[str], min_temp: float, max_temp: float) -> None:  # pragma: no cover
        """Updates hwmon temperature files with gradual changes (+/- 0-3 degrees) within the given range.
        Called only from smoke_runner.py background thread."""
        for path in files:
            with open(path, "r", encoding="UTF-8") as f:
                current = float(f.read()) / 1000
            delta = random.choice([-3, -2, -1, 0, 1, 2, 3])
            new_temp = max(min_temp, min(max_temp, current + delta))
            with open(path, "w+t", encoding="UTF-8") as f:
                f.write(f"{new_temp * 1000:.0f}")

    def create_nvidia_smi_command(self, count: int, temp_list: List[float] = None, min_temp: float = 35.0,
                                  max_temp: float = 75.0) -> str:
        """Creates a shell script emulating `nvidia-smi` with gradual temperature changes."""
        if temp_list:
            file_content = "cat << EOF\n"
            for i in range(count):
                file_content += f"{temp_list[i]:.0f}\n"
            file_content += "EOF\n"
        else:
            min_t = int(min_temp)
            max_t = int(max_temp)
            mid_t = (min_t + max_t) // 2
            file_content = f"""STATE_FILE="${{0}}.state"
if [ ! -f "$STATE_FILE" ]; then
    for i in $(seq 0 {count - 1}); do echo {mid_t}; done > "$STATE_FILE"
fi
temps=($(cat "$STATE_FILE"))
for i in $(seq 0 {count - 1}); do
    delta=$((RANDOM % 7 - 3))
    new_t=$((temps[i] + delta))
    [ $new_t -lt {min_t} ] && new_t={min_t}
    [ $new_t -gt {max_t} ] && new_t={max_t}
    temps[i]=$new_t
    echo $new_t
done
printf '%s\\n' "${{temps[@]}}" > "$STATE_FILE"
"""
        return self.create_command_file(file_content)

    def create_rocm_smi_command(self, count: int, temp_list: List[float] = None, min_temp: float = 35.0,
                                max_temp: float = 75.0) -> str:
        """Creates a shell script emulating `rocm-smi -t --json` with gradual temperature changes."""
        if temp_list:
            data = {}
            for i in range(count):
                v = temp_list[i]
                data[f"card{i}"] = {
                    "Temperature (Sensor junction) (C)": f"{v:.1f}",
                    "Temperature (Sensor edge) (C)": f"{v-2:.1f}",
                    "Temperature (Sensor memory) (C)": f"{v-5:.1f}"
                }
            file_content = "cat << EOF\n"
            file_content += json.dumps(data) + "\n"
            file_content += "EOF\n"
        else:
            min_t = int(min_temp)
            max_t = int(max_temp)
            mid_t = (min_t + max_t) // 2
            fmt_parts = []
            for i in range(count):
                sep = ", " if i < count - 1 else ""
                fmt_parts.append(
                    f'"card{i}": {{"Temperature (Sensor junction) (C)": "%d.0", '
                    f'"Temperature (Sensor edge) (C)": "%d.0", '
                    f'"Temperature (Sensor memory) (C)": "%d.0"}}{sep}'
                )
            fmt_str = "{" + "".join(fmt_parts) + "}\\n"
            file_content = f"""STATE_FILE="${{0}}.state"
if [ ! -f "$STATE_FILE" ]; then
    for i in $(seq 0 {count - 1}); do echo {mid_t}; done > "$STATE_FILE"
fi
temps=($(cat "$STATE_FILE"))
args=""
for i in $(seq 0 {count - 1}); do
    delta=$((RANDOM % 7 - 3))
    new_t=$((temps[i] + delta))
    [ $new_t -lt {min_t} ] && new_t={min_t}
    [ $new_t -gt {max_t} ] && new_t={max_t}
    temps[i]=$new_t
    args="$args $new_t $((new_t - 2)) $((new_t - 5))"
done
printf '%s\\n' "${{temps[@]}}" > "$STATE_FILE"
printf '{fmt_str}' $args
"""
        return self.create_command_file(file_content)

    def create_text_file(self, content: str) -> str:
        """Creates a text file with the specified content."""
        h, name = tempfile.mkstemp(prefix="text", suffix=".txt", dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            f.write(content)
        return name


# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods
class MockDevice:
    """Mock class for pyudev.Device() class"""

    _sys_path: str

    def __init__(self, context=None, _device=None):
        pass

    def __del__(self):
        pass

    @property
    def parent(self):
        return None

    @property
    def sys_path(self):
        return self._sys_path


def factory_mockdevice():
    """Can generate MockDevice() class."""
    return MockDevice()


class MockContext:
    """Mock class for pyudev.Context() class."""

    mocked_devices: List[MockDevice]

    def __init__(self, devices=None):
        self.mocked_devices = devices

    # pylint: disable=unused-argument
    def list_devices(self, **kwargs):
        return iter(self.mocked_devices)

    # pylint: enable=unused-argument


class MockDevices:
    """Mock class for pyudev.Devices() class."""

    @classmethod
    def from_device_file(cls, context=None, filename=None):
        if filename == "raise":
            raise DeviceNotFoundByFileError()
        return MockDevice(context)


class MockedContextError:
    """Mock class for pyudev.Context() class will generate ImportError exception."""

    def __init__(self):
        raise ImportError


class MockedContextGood:
    """Mock class for pyudev.Context() class will not generate any exception."""

    def __init__(self):
        pass


# pylint: enable=missing-function-docstring
# pylint: enable=too-few-public-methods


# Generic config factory functions for unit tests
def create_ipmi_config(command=Config.DV_IPMI_COMMAND, fan_mode_delay=Config.DV_IPMI_FAN_MODE_DELAY,
                       fan_level_delay=Config.DV_IPMI_FAN_LEVEL_DELAY,
                       remote_parameters=Config.DV_IPMI_REMOTE_PARAMETERS,
                       platform_name=Config.DV_IPMI_PLATFORM_NAME):
    """Factory function to create IpmiConfig instances for testing without needing a config file.

    Args:
        command (str): Full path for ipmitool command (default: "/usr/bin/ipmitool")
        fan_mode_delay (int): Delay time after execution of IPMI set fan mode function (default: 10)
        fan_level_delay (int): Delay time after execution of IPMI set fan level function (default: 2)
        remote_parameters (str): Remote IPMI parameters (default: "")
        platform_name (str): Platform name (default: "auto")

    Returns:
        IpmiConfig: configured IpmiConfig instance
    """
    from smfc.config import IpmiConfig
    return IpmiConfig(command=command, fan_mode_delay=fan_mode_delay, fan_level_delay=fan_level_delay,
                      remote_parameters=remote_parameters, platform_name=platform_name)


def create_cpu_config(section="CPU", enabled=False, ipmi_zone=None, temp_calc=Config.CALC_AVG,
                      steps=Config.DV_CPU_STEPS, sensitivity=Config.DV_CPU_SENSITIVITY,
                      polling=Config.DV_CPU_POLLING, min_temp=Config.DV_CPU_MIN_TEMP,
                      max_temp=Config.DV_CPU_MAX_TEMP, min_level=Config.DV_CPU_MIN_LEVEL,
                      max_level=Config.DV_CPU_MAX_LEVEL, smoothing=Config.DV_CPU_SMOOTHING):
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
    from smfc.config import CpuConfig
    return CpuConfig(section=section, enabled=enabled, ipmi_zone=ipmi_zone if ipmi_zone is not None else [Config.CPU_ZONE],
                     temp_calc=temp_calc, steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                     max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing)


def create_hd_config(section="HD", enabled=False, ipmi_zone=None, temp_calc=Config.CALC_AVG,
                     steps=Config.DV_HD_STEPS, sensitivity=Config.DV_HD_SENSITIVITY,
                     polling=Config.DV_HD_POLLING, min_temp=Config.DV_HD_MIN_TEMP,
                     max_temp=Config.DV_HD_MAX_TEMP, min_level=Config.DV_HD_MIN_LEVEL,
                     max_level=Config.DV_HD_MAX_LEVEL, smoothing=Config.DV_HD_SMOOTHING, hd_names=None,
                     smartctl_path=Config.DV_HD_SMARTCTL_PATH, standby_guard_enabled=False,
                     standby_hd_limit=Config.DV_HD_STANDBY_HD_LIMIT):
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
    from smfc.config import HdConfig
    return HdConfig(section=section, enabled=enabled, ipmi_zone=ipmi_zone if ipmi_zone is not None else [Config.HD_ZONE],
                    temp_calc=temp_calc, steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                    max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing,
                    hd_names=hd_names if hd_names is not None else [], smartctl_path=smartctl_path,
                    standby_guard_enabled=standby_guard_enabled, standby_hd_limit=standby_hd_limit)


def create_nvme_config(section="NVME", enabled=False, ipmi_zone=None, temp_calc=Config.CALC_AVG,
                       steps=Config.DV_NVME_STEPS, sensitivity=Config.DV_NVME_SENSITIVITY,
                       polling=Config.DV_NVME_POLLING, min_temp=Config.DV_NVME_MIN_TEMP,
                       max_temp=Config.DV_NVME_MAX_TEMP, min_level=Config.DV_NVME_MIN_LEVEL,
                       max_level=Config.DV_NVME_MAX_LEVEL, smoothing=Config.DV_NVME_SMOOTHING,
                       nvme_names=None):
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
    from smfc.config import NvmeConfig
    return NvmeConfig(section=section, enabled=enabled, ipmi_zone=ipmi_zone if ipmi_zone is not None else [Config.HD_ZONE],
                      temp_calc=temp_calc, steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                      max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing,
                      nvme_names=nvme_names if nvme_names is not None else [])


def create_gpu_config(section="GPU", enabled=False, ipmi_zone=None, temp_calc=Config.CALC_AVG,
                      steps=Config.DV_GPU_STEPS, sensitivity=Config.DV_GPU_SENSITIVITY,
                      polling=Config.DV_GPU_POLLING, min_temp=Config.DV_GPU_MIN_TEMP,
                      max_temp=Config.DV_GPU_MAX_TEMP, min_level=Config.DV_GPU_MIN_LEVEL,
                      max_level=Config.DV_GPU_MAX_LEVEL, smoothing=Config.DV_GPU_SMOOTHING,
                      gpu_type=Config.DV_GPU_TYPE, gpu_device_ids=None,
                      nvidia_smi_path=Config.DV_GPU_NVIDIA_SMI_PATH, rocm_smi_path=Config.DV_GPU_ROCM_SMI_PATH,
                      amd_temp_sensor=Config.DV_GPU_AMD_TEMP_SENSOR):
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
    from smfc.config import GpuConfig
    return GpuConfig(section=section, enabled=enabled, ipmi_zone=ipmi_zone if ipmi_zone is not None else [Config.HD_ZONE],
                     temp_calc=temp_calc, steps=steps, sensitivity=sensitivity, polling=polling, min_temp=min_temp,
                     max_temp=max_temp, min_level=min_level, max_level=max_level, smoothing=smoothing,
                     gpu_type=gpu_type,
                     gpu_device_ids=gpu_device_ids if gpu_device_ids is not None else Config.parse_gpu_ids(Config.DV_GPU_DEVICE_IDS),
                     nvidia_smi_path=nvidia_smi_path, rocm_smi_path=rocm_smi_path, amd_temp_sensor=amd_temp_sensor)


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
    from smfc.config import ConstConfig
    return ConstConfig(section=section, enabled=enabled, ipmi_zone=ipmi_zone if ipmi_zone is not None else [Config.HD_ZONE],
                       polling=polling, level=level)


# End.
