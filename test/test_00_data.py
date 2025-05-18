#!/usr/bin/env python3
#
#   test_00_data.py (C) 2022-2025, Peter Sulyok
#   Test data handling class for unit tests.
#
import configparser
import os
import random
import shutil
import tempfile
from typing import List
from pyudev import DeviceNotFoundByFileError


class TestData:
    """Class for test data handling."""

    td_dir: str = ''                    # Test data directory
    cpu_files: List[str] = []           # CPU hwmon files

    hd_names: str                       # HD names in configuration parameter form
    hd_name_list: List[str] = []        # HD names in a list
    hd_files: List[str] = []            # HD hwmon files

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
            hwmon_file = os.path.join(self.td_dir, 'cpu', 'coretemp.' + str(i), 'hwmon')
            os.makedirs(hwmon_file, exist_ok=True)
            hwmon_file = os.path.join(hwmon_file, 'temp1_input')
            with open(hwmon_file, "w+t", encoding="UTF-8") as f:
                if temp_list:
                    v = temp_list[i]
                else:
                    v = random.uniform(30.0, 60.0)
                f.write(str(v * 1000))
            self.cpu_files.append(hwmon_file)

    def create_hd_data(self, count: int, temp_list: List[float] = None) -> None:
        """Generic method to create temporary test data files (similarly to hwmon naming convention and content)."""
        letters: List[str] = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q' ]
        hwmon_path: str
        disk_name: str

        self.hd_names = ''
        self.hd_name_list = []
        self.hd_files = []
        separator = random.choice([' ', '\n'])
        for i in range(count):
            disk_name = '/dev/sd' + letters[i]
            self.hd_names += disk_name + separator
            self.hd_name_list.append(disk_name)
            hwmon_path = os.path.join(self.td_dir, 'disks', str(i)+':0:0:0', 'hwmon')
            os.makedirs(hwmon_path, exist_ok=True)
            hwmon_path = os.path.join(hwmon_path, 'temp1_input')
            with open(hwmon_path, "w+t", encoding="UTF-8") as f:
                if temp_list:
                    v = temp_list[i]
                else:
                    v = random.uniform(32.0, 45.0)
                v *= 1000
                f.write(f"{v:.0f}")
            self.hd_files.append(hwmon_path)

    def create_config_file(self, my_config: configparser.ConfigParser) -> str:
        """Creates a config file. """
        h, name = tempfile.mkstemp(prefix='config', suffix='.conf', dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            my_config.write(f)
        return name

    def create_command_file(self, content: str = 'echo OK') -> str:
        """Creates an executable bash script. """
        h, name = tempfile.mkstemp(suffix='.sh', dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            f.write(str('#!/bin/bash\n'))
            f.write(str(content + '\n'))
        os.system('chmod +x ' + name)
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
"""
        )

    def create_nvidia_smi_command(self, count: int, temp_list: List[float] = None) -> str:
        """Creates a shell script emulating `nvidia-smi`."""
        file_content = 'cat << EOF\n'
        for i in range(0, count):
            if temp_list:
                v = temp_list[i]
            else:
                v = random.uniform(35.0, 75.0)
            file_content += f'{v:.0f}' + '\n'
        file_content += 'EOF\n'
        return self.create_command_file(file_content)

    def create_text_file(self, content: str) -> str:
        """Creates a text file with the specified content."""
        h, name = tempfile.mkstemp(prefix='text', suffix='.txt', dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            f.write(content)
        return name


#pylint: disable=missing-function-docstring
#pylint: disable=too-few-public-methods
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

    def __del__(self):
        pass

    #pylint: disable=unused-argument
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

#pylint: enable=missing-function-docstring
#pylint: enable=too-few-public-methods


# End.
