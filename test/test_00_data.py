#!/usr/bin/python3
#
#   test_00_data.py (C) 2022-2024, Peter Sulyok
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

    # HD types
    HT_NVME: int = 0
    HT_SATA: int = 1
    HT_SCSI: int = 2

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
            new_path = new_dir + 'coretemp.' + str(i) + '/'
            os.makedirs(new_path, exist_ok=True)
            real_path = new_path + 'hwmon/hwmon' + str(i) + '/'
            if wildchar:
                list_path = new_path + 'hwmon/hwmon*/'
            else:
                list_path = real_path
            os.makedirs(real_path, exist_ok=True)
            real_name = real_path + 'temp1_input'
            list_name = list_path + 'temp1_input'
            with open(real_name, "w+t", encoding="UTF-8") as f:
                if temp_list:
                    v = temp_list[i]
                else:
                    v = random.uniform(30.0, 60.0)
                f.write(str(v * 1000))
            new_list = new_list + list_name + '\n'
        return new_list

    def create_hd_temp_files(self, count: int, temp_list: List[float] = None, wildchar: bool = False,
                             hd_types: List[int] = None) -> str:
        """Generic method to create temporary test data files (similarly to hwmon naming convention and content)."""
        letters: list[str] = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']
        new_list: str = ''
        new_dir: str
        new_path: str
        sata_counter: int = 0
        nvme_counter: int = 0

        # If no disk types are specified then the default type is SATA.
        if not hd_types:
            hd_types = [self.HT_SATA] * count

        # Create test data for different disk types.
        for i in range(count):

            # ATA/SATA disk type.
            if hd_types[i] == self.HT_SATA:
                new_dir = self.td_dir + '/sys/class/scsi_disk/'
                new_path = new_dir + str(i) + ':0:0:0/device/'
                os.makedirs(new_path, exist_ok=True)
                os.makedirs(new_path + 'block/sd' + letters[sata_counter], exist_ok=True)
                real_path = new_path + 'hwmon/hwmon' + str(i) + '/'
                if wildchar:
                    list_path = new_path + 'hwmon/hwmon*/'
                else:
                    list_path = real_path
                os.makedirs(real_path, exist_ok=True)
                real_name = real_path + 'temp1_input'
                list_name = list_path + 'temp1_input'
                with open(real_name, "w+t", encoding="UTF-8") as f:
                    if temp_list:
                        v = temp_list[i]
                    else:
                        v = random.uniform(32.0, 45.0)
                    v *= 1000
                    f.write(f"{v:.1f}")
                new_list = new_list + list_name + '\n'
                sata_counter += 1

            # NVME disk type.
            elif hd_types[i] == self.HT_NVME:
                new_dir = self.td_dir + '/sys/class/nvme/'
                new_path = new_dir + "nvme" + str(nvme_counter) + '/' + "nvme" + str(nvme_counter) + 'n1'
                os.makedirs(new_path, exist_ok=True)

                real_path = new_path + '/hwmon' + str(i) + '/'
                if wildchar:
                    list_path = new_path + '/hwmon*/'
                else:
                    list_path = real_path
                os.makedirs(real_path, exist_ok=True)
                real_name = real_path + 'temp1_input'
                list_name = list_path + 'temp1_input'
                with open(real_name, "w+t", encoding="UTF-8") as f:
                    if temp_list:
                        v = temp_list[i]
                    else:
                        v = random.uniform(45.0, 75.0)
                    v *= 1000
                    f.write(f"{v:.1f}")
                new_list = new_list + list_name + '\n'
                nvme_counter += 1

            # SAS/SCSI disk
            elif hd_types[i] == self.HT_SCSI:
                new_list = new_list + "hddtemp" + '\n'

        return new_list

    def get_cpu_1(self, temperatures: List[float] = None) -> str:
        """Generates hwmon files for 1 CPU."""
        return self.create_cpu_temp_files(1, temp_list=temperatures, wildchar=False)

    def get_cpu_1w(self, temperatures: List[float] = None) -> str:
        """Generates hwmon files with wild characters for 1 CPU."""
        return self.create_cpu_temp_files(1, temp_list=temperatures, wildchar=True)

    def get_cpu_2(self, temperatures: List[float] = None) -> str:
        """Generates hwmon files for 2 CPUs."""
        return self.create_cpu_temp_files(2, temp_list=temperatures, wildchar=False)

    def get_cpu_2w(self, temperatures: List[float] = None) -> str:
        """Generates hwmon files with wild characters for 2 CPUs."""
        return self.create_cpu_temp_files(2, temp_list=temperatures, wildchar=True)

    def get_cpu_4(self, temperatures: List[float] = None) -> str:
        """Generates hwmon files for 4 CPUs."""
        return self.create_cpu_temp_files(4, temp_list=temperatures, wildchar=False)

    def get_cpu_4w(self, temperatures: List[float] = None) -> str:
        """Generates hwmon files with wild characters for 4 CPUs."""
        return self.create_cpu_temp_files(4, temp_list=temperatures, wildchar=True)

    def get_hd_1(self, temperatures: List[float] = None, types: List[int] = None) -> str:
        """Generates hwmon files for 1 HD."""
        return self.create_hd_temp_files(1, temp_list=temperatures, wildchar=False, hd_types=types)

    def get_hd_1w(self, temperatures: List[float] = None, types: List[int] = None) -> str:
        """Generates hwmon files with wild characters for 1 HD."""
        return self.create_hd_temp_files(1, temp_list=temperatures, wildchar=True, hd_types=types)

    def get_hd_2(self, temperatures: List[float] = None, types: List[int] = None) -> str:
        """Generates hwmon files for 2 HDs."""
        return self.create_hd_temp_files(2, temp_list=temperatures, wildchar=False, hd_types=types)

    def get_hd_2w(self, temperatures: List[float] = None, types: List[int] = None) -> str:
        """Generates hwmon files with wild characters for 2 HDs."""
        return self.create_hd_temp_files(2, temp_list=temperatures, wildchar=True, hd_types=types)

    def get_hd_4(self, temperatures: List[float] = None, types: List[int] = None) -> str:
        """Generates hwmon files for 4 HDs."""
        return self.create_hd_temp_files(4, temp_list=temperatures, wildchar=False, hd_types=types)

    def get_hd_4w(self, temperatures: List[float] = None, types: List[int] = None) -> str:
        """Generates hwmon files with wild characters for 4 HDs."""
        return self.create_hd_temp_files(4, temp_list=temperatures, wildchar=True, hd_types=types)

    def get_hd_8(self, temperatures: List[float] = None, types: List[int] = None) -> str:
        """Generates hwmon files for 8 HDs."""
        return self.create_hd_temp_files(8, temp_list=temperatures, wildchar=False, hd_types=types)

    def get_hd_8w(self, temperatures: List[float] = None, types: List[int] = None) -> str:
        """Generates hwmon files with wild characters for 8 HDs."""
        return self.create_hd_temp_files(8, temp_list=temperatures, wildchar=True, hd_types=types)

    def create_hd_names(self, count: int, hd_types: List[int] = None) -> str:
        """Generates hd_names= list concatenated in a string."""

        def get_random_str(count: int) -> str:
            rnd_str: str = ''
            i: int = 0
            while i < count:
                rnd_str = rnd_str + random.choice('0123456789ABCDEF')
                i += 1
            return rnd_str

        letters: list[str] = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l']
        hd_names: str = ''
        dev_dir: str
        dev_name: str
        sata_counter: int = 0
        nvme_counter: int = 0
        scsi_counter: int = 0

        # Create root folder for disks.
        dev_dir = os.path.join(self.td_dir, 'dev/disk/by-id/')
        separator = ' '
        if random.randint(1, 2) % 2 == 0:
            separator = '\n'
        os.makedirs(dev_dir, exist_ok=True)

        # If no disk types are specified then the default type is SATA.
        if not hd_types:
            hd_types = [self.HT_SATA] * count

        for i in range(count):

            # SATA disk type
            if hd_types[i] == self.HT_SATA:

                # Create /dev/sd? file.
                sdx_name = os.path.join(self.td_dir, 'dev', 'sd' + letters[sata_counter])
                with open(sdx_name, 'w+t', encoding="UTF-8") as f:
                    f.write(str(' '))
                # Create a link with device name.
                dev_name = os.path.join(dev_dir, 'ata-HD_HD1100XOI-' + get_random_str(8))
                os.symlink('../../sd' + letters[sata_counter], dev_name)
                hd_names = hd_names + dev_name + separator
                sata_counter += 1

            # NVME disk type
            elif hd_types[i] == self.HT_NVME:

                # Create /dev/nvme? file.
                sdx_name = os.path.join(self.td_dir, 'dev', 'nvme' + str(nvme_counter))
                with open(sdx_name, 'w+t', encoding="UTF-8") as f:
                    f.write(str(' '))
                # Create a link with device name.
                dev_name = os.path.join(dev_dir, 'nvme-Samsung_SSD_870_PRO_1TB_' + get_random_str(8))
                os.symlink('../../nvme' + str(nvme_counter), dev_name)
                hd_names = hd_names + dev_name + separator
                nvme_counter += 1

            # SAS/SCSI disk type
            elif hd_types[i] == self.HT_SCSI:

                # Create /dev/sg? file.
                sgx_name = os.path.join(self.td_dir, 'dev', 'sg' + letters[scsi_counter])
                with open(sgx_name, 'w+t', encoding="UTF-8") as f:
                    f.write(str(' '))
                # Create a link with device name.
                dev_name = os.path.join(dev_dir, 'scsi-IBM_ST1100YOI_' + get_random_str(8))
                os.symlink('../../sg' + letters[scsi_counter], dev_name)
                hd_names = hd_names + dev_name + separator
                scsi_counter += 1

        return hd_names

    @staticmethod
    def normalize_path(old_list: List[str]) -> List[str]:
        """Normalizes the path in a List[str]"""
        new_list: List[str] = []
        for ol in old_list:
            fn = glob.glob(ol)
            new_list.append(fn[0])
        return new_list

    @staticmethod
    def create_path_list(hwmon_str: str) -> List[str]:
        """Creates a path List[str] with splitting the input string based on its content."""
        new_list: List[str]
        # Convert the string into a string array (respecting multi-line strings).
        if "\n" in hwmon_str:
            new_list = hwmon_str.splitlines()
        else:
            new_list = hwmon_str.split()
        return new_list

    @staticmethod
    def create_normalized_path_list(hwmon_str: str) -> List[str]:
        """Creates path List[str] with normalization."""
        return TestData.normalize_path(TestData.create_path_list(hwmon_str))

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

    def create_text_file(self, content: str) -> str:
        """Creates a text file with the specified content."""
        h, name = tempfile.mkstemp(prefix='text', suffix='.txt', dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            f.write(content)
        return name
