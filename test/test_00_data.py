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

    def create_temp_files(self, prefix: str, count: int, temp_list: List[float] = None,
                          wildchar: bool = False) -> List[str]:
        """Generic method to create temporary test data files (similarly to hwmon naming convention and content)."""
        new_list: List[str] = []
        new_dir: str
        new_path: str

        new_dir = tempfile.mkdtemp(prefix=prefix+str(count)+'_', dir=self.td_dir)
        if wildchar:
            wc = '?'
        else:
            wc = '0'
        for i in range(count):
            new_path = os.path.join(new_dir, str(i), wc)
            os.makedirs(new_path)
            h, name = tempfile.mkstemp(dir=new_path)
            with os.fdopen(h, "w+t") as f:
                if temp_list is not None:
                    v = temp_list[i]
                else:
                    v = random.uniform(25.0, 55.0)
                f.write(str(v * 1000))
            new_list.append(name)
        return new_list

    def get_cpu_1(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('cpu', 1, temp_list=temperatures, wildchar=False)

    def get_cpu_1w(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('cpu', 1, temp_list=temperatures, wildchar=True)

    def get_cpu_2(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('cpu', 2, temp_list=temperatures, wildchar=False)

    def get_cpu_2w(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('cpu', 2, temp_list=temperatures, wildchar=True)

    def get_cpu_4(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('cpu', 4, temp_list=temperatures, wildchar=False)

    def get_cpu_4w(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('cpu', 4, temp_list=temperatures, wildchar=True)

    def get_hd_1(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('hd', 1, temp_list=temperatures, wildchar=False)

    def get_hd_1w(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('hd', 1, temp_list=temperatures, wildchar=True)

    def get_hd_2(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('hd', 2, temp_list=temperatures, wildchar=False)

    def get_hd_2w(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('hd', 2, temp_list=temperatures, wildchar=True)

    def get_hd_4(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('hd', 4, temp_list=temperatures, wildchar=False)

    def get_hd_4w(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('hd', 4, temp_list=temperatures, wildchar=True)

    def get_hd_8(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('hd', 8, temp_list=temperatures, wildchar=False)

    def get_hd_8w(self, temperatures: List[float] = None) -> List[str]:
        return self.create_temp_files('hd', 8, temp_list=temperatures, wildchar=True)

    @staticmethod
    def get_hd_names(count: int) -> str:
        letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
        s = ''
        for i in range(count):
            s += '/dev/sd' + letters[i] + ' '
        return s

    @staticmethod
    def normalize_path(old_list: List[str]) -> List[str]:
        new_list: List[str] = []
        for i in range(len(old_list)):
            fn = glob.glob(old_list[i])
            new_list.append(fn[0])
        return new_list

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
""")
