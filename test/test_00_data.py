#!/usr/bin/python3
#
#   test_00_data.py (C) 2022, Peter Sulyok
#   Test data handling class for unit tests.
#
import configparser
import glob
import os
import random
import shutil
import tempfile
from typing import List


class TestData:
    """Class for test data handling."""

    td_dir: str = ''    # Test data directory

    def __init__(self):
        """Initialize the class. It creates a temporary directory."""
        self.td_dir = tempfile.mkdtemp()

    def __del__(self):
        """It deletes the temporary directory with is all content."""
        shutil.rmtree(self.td_dir)

    def create_cpu_temp_files(self, count: int, temp_list: List[float] = None, wildchar: bool = False) -> str:
        """Generic method to create temporary test data files (similarly to hwmon naming convention and content)."""
        new_list: str = ''
        new_dir: str
        new_path: str

        new_dir = self.td_dir + '/sys/devices/platform/'
        for i in range(count):
            new_path = new_dir + 'coretemp.'+str(i) + '/'
            os.makedirs(new_path, exist_ok=True)
            real_path = new_path + 'hwmon/hwmon'+str(i) + '/'
            if wildchar:
                list_path = new_path + 'hwmon/hwmon*/'
            else:
                list_path = real_path
            os.makedirs(real_path, exist_ok=True)
            real_name = real_path + 'temp1_input'
            list_name = list_path + 'temp1_input'
            with open(real_name, "w+t") as f:
                if temp_list:
                    v = temp_list[i]
                else:
                    v = random.uniform(30.0, 60.0)
                f.write(str(v * 1000))
            new_list = new_list + list_name + '\n'
        return new_list

    def create_hd_temp_files(self, count: int, temp_list: List[float] = None, wildchar: bool = False) -> str:
        """Generic method to create temporary test data files (similarly to hwmon naming convention and content)."""
        letters: list[str] = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']
        new_list: str = ''
        new_dir: str
        new_path: str

        new_dir = self.td_dir + '/sys/class/scsi_disk/'
        for i in range(count):
            new_path = new_dir + str(i)+':0:0:0/device/'
            os.makedirs(new_path, exist_ok=True)
            os.makedirs(new_path + 'block/sd'+letters[i], exist_ok=True)
            real_path = new_path + 'hwmon/hwmon'+str(i) + '/'
            if wildchar:
                list_path = new_path + 'hwmon/hwmon*/'
            else:
                list_path = real_path
            os.makedirs(real_path, exist_ok=True)
            real_name = real_path + 'temp1_input'
            list_name = list_path + 'temp1_input'
            with open(real_name, "w+t") as f:
                if temp_list:
                    v = temp_list[i]
                else:
                    v = random.uniform(32.0, 45.0)
                f.write(str(v * 1000))
            new_list = new_list + list_name + '\n'
        return new_list

    def get_cpu_1(self, temperatures: List[float] = None) -> str:
        return self.create_cpu_temp_files(1, temp_list=temperatures, wildchar=False)

    def get_cpu_1w(self, temperatures: List[float] = None) -> str:
        return self.create_cpu_temp_files(1, temp_list=temperatures, wildchar=True)

    def get_cpu_2(self, temperatures: List[float] = None) -> str:
        return self.create_cpu_temp_files(2, temp_list=temperatures, wildchar=False)

    def get_cpu_2w(self, temperatures: List[float] = None) -> str:
        return self.create_cpu_temp_files(2, temp_list=temperatures, wildchar=True)

    def get_cpu_4(self, temperatures: List[float] = None) -> str:
        return self.create_cpu_temp_files(4, temp_list=temperatures, wildchar=False)

    def get_cpu_4w(self, temperatures: List[float] = None) -> str:
        return self.create_cpu_temp_files(4, temp_list=temperatures, wildchar=True)

    def get_hd_1(self, temperatures: List[float] = None) -> str:
        return self.create_hd_temp_files(1, temp_list=temperatures, wildchar=False)

    def get_hd_1w(self, temperatures: List[float] = None) -> str:
        return self.create_hd_temp_files(1, temp_list=temperatures, wildchar=True)

    def get_hd_2(self, temperatures: List[float] = None) -> str:
        return self.create_hd_temp_files(2, temp_list=temperatures, wildchar=False)

    def get_hd_2w(self, temperatures: List[float] = None) -> str:
        return self.create_hd_temp_files(2, temp_list=temperatures, wildchar=True)

    def get_hd_4(self, temperatures: List[float] = None) -> str:
        return self.create_hd_temp_files(4, temp_list=temperatures, wildchar=False)

    def get_hd_4w(self, temperatures: List[float] = None) -> str:
        return self.create_hd_temp_files(4, temp_list=temperatures, wildchar=True)

    def get_hd_8(self, temperatures: List[float] = None) -> str:
        return self.create_hd_temp_files(8, temp_list=temperatures, wildchar=False)

    def get_hd_8w(self, temperatures: List[float] = None) -> str:
        return self.create_hd_temp_files(8, temp_list=temperatures, wildchar=True)

    def get_hd_names(self, count: int) -> str:
        letters: list[str] = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']
        hd_names: str = ''
        dev_dir: str
        dev_name: str
        dev_dir = os.path.join(self.td_dir, 'dev/disk/by-id/')
        separator = ' '
        if random.randint(1, 2) % 2 == 0:
            separator = '\n'
        os.makedirs(dev_dir, exist_ok=True)
        for i in range(count):
            # Create /dev/sd? file.
            sdx_name = os.path.join(self.td_dir, 'dev', 'sd'+letters[i])
            with open(sdx_name, 'w+t') as f:
                f.write(str(' '))
            random_str = ''
            for k in range(8):
                random_str = random_str + random.choice('0123456789ABCDEF')
            # Create a link with device name.
            dev_name = os.path.join(dev_dir, 'ata-HD_HD1100XOI-'+random_str)
            os.symlink('../../sd'+letters[i], dev_name)
            hd_names = hd_names + dev_name + separator
        return hd_names

    @staticmethod
    def normalize_path(old_list: List[str]) -> List[str]:
        new_list: List[str] = []
        for i in range(len(old_list)):
            fn = glob.glob(old_list[i])
            new_list.append(fn[0])
        return new_list

    @staticmethod
    def create_path_list(hwmon_str: str) -> List[str]:
        new_list: List[str]
        # Convert the string into a string array (respecting multi-line strings).
        if "\n" in hwmon_str:
            new_list = hwmon_str.splitlines()
        else:
            new_list = hwmon_str.split()
        return new_list

    @staticmethod
    def create_normalized_path_list(hwmon_str: str) -> List[str]:
        return TestData.normalize_path(TestData.create_path_list(hwmon_str))

    def create_config_file(self, my_config: configparser.ConfigParser) -> str:
        h, name = tempfile.mkstemp(prefix='config', suffix='.conf', dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            my_config.write(f)
        return name

    def create_command_file(self, content: str = 'echo OK') -> str:
        h, name = tempfile.mkstemp(suffix='.sh', dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            f.write(str('#!/bin/bash\n'))
            f.write(str(content + '\n'))
        os.system('chmod +x ' + name)
        return name

    @staticmethod
    def delete_file(path: str) -> None:
        os.remove(path)

    def create_ipmi_command(self) -> str:
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
"""
        )
