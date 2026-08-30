#!/usr/bin/env python3
#
#   test_fixtures.py (C) 2022-2026, Peter Sulyok
#   On-disk test fixtures for unit and smoke tests.
#
#   TestData materializes fake hwmon trees and shell scripts that emulate
#   ipmitool / nvidia-smi / rocm-smi / arbitrary commands inside a caller-owned
#   temporary directory. The `td` fixture in `conftest.py` injects pytest's
#   `tmp_path` (one fresh dir per test, cleaned up by pytest's own lifecycle
#   logic — no `__del__`/`rmtree` involvement here).
#
import configparser
import json
import os
import random
import subprocess
import tempfile
from typing import Dict, List

from smfc.platform import IpmiError


class TestData:
    """Class for test data handling."""

    cpu_files: List[str] = []  # CPU hwmon files

    hd_names: str  # HD names in configuration parameter form
    hd_name_list: List[str] = []  # HD names in a list
    hd_files: List[str] = []  # HD hwmon files

    nvme_names: str  # NVMe names in configuration parameter form
    nvme_name_list: List[str] = []  # NVMe names in a list
    nvme_files: List[str] = []  # NVMe hwmon files

    def __init__(self, td_dir):
        """Bind to a caller-supplied directory. The caller (pytest's `tmp_path` fixture, or
        an equivalent) owns the directory's lifecycle; TestData only fills it."""
        self.td_dir = str(td_dir)

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

    def create_ipmi_command(self, bmc_stack: str = "", aten_duty_path: str = "pwm") -> str:
        """Creates a bash script emulating ipmitool.

        Supermicro's 14th generation ships two unrelated BMC firmware stacks with different command sets
        (`doc/X14H14_MANUAL_FANCONTROL.md`, Part 1), so the emulation has to be stack-dependent. The
        arguments are baked into the generated script (the matching `SMFC_TEST_*` environment variables
        still override them, for driving the script by hand):

        - `bmc_stack="openbmc"`  the Part 1 probe answers with a data byte, and the OEM manual/failsafe
          command set of netfn `0x2e` exists.
        - `bmc_stack="aten"`     the Part 1 probe answers `0xC1`, and netfn `0x2e` does not exist.

        Both stacks share the `0x30 0x70 0x66` layout: selector `0x00` reads a zone's duty, `0x01` writes
        it, `0x02` toggles automatic control. What differs is what `0x02` means - per-zone manual mode on
        OpenBMC, a global bypass flag on ATEN.
        - `bmc_stack=""` (default): the historical, stack-agnostic behaviour every non-X14 test relies on.

        On the ATEN stack `aten_duty_path` selects which of the two duty paths of Part 4.4 the board has,
        because that is the difference `X14AtenPlatform.accepted()` exists to absorb:

        - `pwm` (default): the 8-bit PWM path, clamping to 5-100 and truncating twice, so the read-back is
          exact at multiples of 20 and exactly one low elsewhere.
        - `percent`: the path that stores the percentage itself and reads it back exactly.
        Args:
            bmc_stack (str): the 14th generation BMC firmware stack to emulate ('openbmc', 'aten' or '')
            aten_duty_path (str): the ATEN duty path to emulate ('pwm' or 'percent')
        Returns:
            str: path of the generated script
        """
        return self.create_command_file(f"""
# ipmitool emulation

# State file emulating the X14 per-zone manual mode latch (see the 0x2e 0x04 branch below).
MANUAL_FLAG_FILE="${{BASH_SOURCE[0]}}.x14manual"
# State file emulating the ATEN per-zone duty register (see the 0x30 0x70 0x66 branches below).
ATEN_DUTY_FILE="${{BASH_SOURCE[0]}}.atenduty"
# State file emulating the OpenBMC per-zone duty register (see the 0x30 0x70 0x66 branches below).
OPENBMC_DUTY_FILE="${{BASH_SOURCE[0]}}.openbmcduty"
# Which of the two 14th generation BMC firmware stacks this fake BMC is: 'openbmc', 'aten' or unset
# (the historical, stack-agnostic behaviour every non-X14 test relies on).
BMC_STACK="${{SMFC_TEST_BMC_STACK:-{bmc_stack}}}"
# Which ATEN duty path the fake board has (Part 4.4): 'pwm' (default) or 'percent'.
ATEN_DUTY_PATH="${{SMFC_TEST_ATEN_DUTY_PATH:-{aten_duty_path}}}"

# Reply of an ATEN duty read for a duty that was written as $1 (decimal %).
aten_readback() {{
	local d=$1
	if [[ "$ATEN_DUTY_PATH" = "percent" ]] ; then
		# The percent path stores the percentage itself: no truncation, no 5% clamp.
		printf " %02x\\n" "$d"
		return
	fi
	# The PWM path clamps to 5-100, converts to an 8-bit PWM value and back, truncating both divisions.
	if [[ "$d" -lt 5 ]] ; then d=5 ; fi
	if [[ "$d" -gt 100 ]] ; then d=100 ; fi
	printf " %02x\\n" "$(( ((d * 255) / 100) * 100 / 255 ))"
}}

if [[ $1 = "sdr" ]] ; then
	echo "CPU Temp         | 45 degrees C      | ok"
	echo "FAN1             | 500 RPM           | ok"
	echo "FANA             | 500 RPM           | ok"
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

# IPMI get supported fan modes (raw 0x30 0x45 0x02) — 2 bytes, little-endian, one bit per mode value.
# 0x0FFF is every documented mode, 0x00-0x0B.
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x45" && $4 = "0x02" ]] ; then
	echo " ff 0f"
	exit 0
fi

# raw 0x30 0x70 0x66 0x00 <zone> — a duty read on both stacks (Part 1.3). A trailing duty byte is ignored,
# so a caller that mistakes this for the write selector changes nothing.
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x70" && $4 = "0x66" && $5 = "0x00" ]] ; then
	if [[ "$BMC_STACK" = "openbmc" ]] ; then
		zone=$(( $6 ))
		duty=50
		if [[ -f "$OPENBMC_DUTY_FILE" ]] ; then
			stored=$(grep "^${{zone}}=" "$OPENBMC_DUTY_FILE" | tail -1 | cut -d= -f2)
			if [[ -n "$stored" ]] ; then duty=$stored ; fi
		fi
		printf " %02x\\n" "$duty"
		exit 0
	fi
	if [[ "$BMC_STACK" = "aten" ]] ; then
		zone=$(( $6 ))
		duty=50
		if [[ -f "$ATEN_DUTY_FILE" ]] ; then
			stored=$(grep "^${{zone}}=" "$ATEN_DUTY_FILE" | tail -1 | cut -d= -f2)
			if [[ -n "$stored" ]] ; then duty=$stored ; fi
		fi
		aten_readback "$duty"
		exit 0
	fi
	# Stack-agnostic default: a read when no level byte is given, a write otherwise.
	if [[ -z "$7" ]] ; then
		echo " 32"
	fi
	exit 0
fi

# X14 manual mode / ATEN bypass flag for all zones (raw 0x30 0x70 0x66 0x02 <0/1>)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x70" && $4 = "0x66" && $5 = "0x02" ]] ; then
	exit 0
fi

# IPMI set fan level (raw 0x30 0x70 0x66 0x01 <zone> <level>)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x70" && $4 = "0x66" && $5 = "0x01" ]] ; then
	if [[ "$BMC_STACK" = "aten" ]] ; then
		echo "$(( $6 ))=$(( $7 ))" >> "$ATEN_DUTY_FILE"
	fi
	if [[ "$BMC_STACK" = "openbmc" ]] ; then
		echo "$(( $6 ))=$(( $7 ))" >> "$OPENBMC_DUTY_FILE"
	fi
	exit 0
fi

# X14 manual/failsafe OEM command (raw 0x2e 0x04 0xcf 0xc2 0x00 <op> <zone> [<value>]):
# op 0x00 reads the manual mode flag, 0x01 writes it, 0x02 reads the failsafe flag. Every reply echoes the
# IANA ID of the command back before the payload, so it reads `cf c2 00 <flag>`.
# This whole command set is what the ATEN stack does not have: it answers 0xC1, which is the Part 1.1
# stack probe. The manual mode flag reads back as latched right after a write and randomly loses the
# latch otherwise, emulating the BMC restart / firmware update that clears it on real hardware.
if [[ $1 = "raw" && $2 = "0x2e" && $3 = "0x04" && $4 = "0xcf" && $5 = "0xc2" ]] ; then
	if [[ "$BMC_STACK" = "aten" ]] ; then
		echo "Unable to send RAW command (channel=0x0 netfn=0x2e lun=0x0 cmd=0x4 rsp=0xc1): Invalid command" >&2
		exit 1
	fi
	if [[ $7 = "0x00" ]] ; then
		if [[ -f "$MANUAL_FLAG_FILE" ]] ; then
			rm -f "$MANUAL_FLAG_FILE"
			echo " cf c2 00 01"
		elif [[ $((RANDOM % 4)) -eq 0 ]] ; then
			echo " cf c2 00 00"
		else
			echo " cf c2 00 01"
		fi
	elif [[ $7 = "0x01" ]] ; then
		touch "$MANUAL_FLAG_FILE"
	elif [[ $7 = "0x02" ]] ; then
		echo " cf c2 00 00"
	fi
	exit 0
fi

# X9 get fan level (raw 0x30 0x90 0x5a 0x03 <reg> 0x01)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x90" && $4 = "0x5a" ]] ; then
	echo "80"
	exit 0
fi

# X9 set fan level (raw 0x30 0x91 0x5a 0x03 <reg> <level>)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x91" && $4 = "0x5a" ]] ; then
	exit 0
fi

# X10QBi get fan level (raw 0x30 0x90 0x5c 0x03 <reg> 0x01)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x90" && $4 = "0x5c" ]] ; then
	echo "80"
	exit 0
fi

# X10QBi set fan level / TMFR init (raw 0x30 0x91 0x5c ...)
if [[ $1 = "raw" && $2 = "0x30" && $3 = "0x91" && $4 = "0x5c" ]] ; then
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

    def create_npu_smi_drift_command(self, cards: int, min_temp: float = 40.0, max_temp: float = 85.0) -> str:
        """Creates a shell script emulating `npu-smi info -t temp -i <card>` with gradual temperature changes.

        The multi-card, drifting counterpart of create_npu_smi_command() (which emits the chips of a
        single card with fixed temperatures). Unlike nvidia-smi/rocm-smi, npu-smi has no multi-card
        query: smfc calls it once per card with `-i <card>`, so the script parses that argument and
        reports only the requested card. Each card emulates a dual-chip Atlas 300I Duo (the second chip
        runs 2C hotter, so the hottest-chip selection of NpuFc is exercised), and the MCU block is
        emitted as well so the parser has the same decoy lines to reject as on real hardware.
        Args:
            cards (int): number of NPU cards
            min_temp (float): lower bound of the drifting temperature (C)
            max_temp (float): upper bound of the drifting temperature (C)
        Returns:
            str: path of the generated script
        """
        min_t = int(min_temp)
        max_t = int(max_temp)
        mid_t = (min_t + max_t) // 2
        file_content = f"""STATE_FILE="${{0}}.state"
CARD=0
while [ $# -gt 0 ]; do
    if [ "$1" = "-i" ]; then CARD="$2"; fi
    shift
done
if [ ! -f "$STATE_FILE" ]; then
    for i in $(seq 0 {cards - 1}); do echo {mid_t}; done > "$STATE_FILE"
fi
temps=($(cat "$STATE_FILE"))
delta=$((RANDOM % 7 - 3))
new_t=$((temps[CARD] + delta))
[ $new_t -lt {min_t} ] && new_t={min_t}
[ $new_t -gt {max_t} ] && new_t={max_t}
temps[CARD]=$new_t
printf '%s\\n' "${{temps[@]}}" > "$STATE_FILE"
chip1=$((new_t + 2))
[ $chip1 -gt {max_t} ] && chip1={max_t}
echo "        NPU ID                         : $CARD"
echo "        Chip Count                     : 2"
echo ""
echo "        Temperature (C)                : $new_t"
echo "        Chip ID                        : 0"
echo ""
echo "        Temperature (C)                : $chip1"
echo "        Chip ID                        : 1"
echo ""
echo "        T_LM75A  (C)                   : 29"
echo "        T_CORE_M (C)                   : 40"
echo "        Chip Name                      : MCU"
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

    def create_npu_smi_command(self, count: int = 1, temp_list: List[float] = None) -> str:
        """Creates a shell script emulating `npu-smi info -t temp -i <id>` for a single card:
        one "Temperature (C)" line per chip, in the key-value layout of the real output."""
        if temp_list is None:
            temp_list = [50.0] * count
        file_content = "cat << 'NPUEOF'\n"
        for i in range(count):
            file_content += f"        Temperature (C)                : {temp_list[i]:.0f}\n"
            file_content += f"        Chip ID                        : {i}\n\n"
        file_content += "NPUEOF\n"
        return self.create_command_file(file_content)

    def create_text_file(self, content: str) -> str:
        """Creates a text file with the specified content."""
        h, name = tempfile.mkstemp(prefix="text", suffix=".txt", dir=self.td_dir)
        with os.fdopen(h, "w+t") as f:
            f.write(content)
        return name


class FakeOpenBmc:
    """In-process model of the fan control of an X14/H14 board running the OpenBMC firmware stack.

    It is an `exec_ipmitool` callback, so a real `Platform` can be driven against it, and it holds the state
    the BMC holds: a per-zone manual mode flag, a per-zone failsafe flag and a per-zone duty register. That
    lets a test assert what the *fans* end up doing rather than which bytes were sent, which is the only way
    to catch a command that the board accepts and ignores.

    Three rules make it a model rather than a command echo, all from
    `doc/X14H14_MANUAL_FANCONTROL.md` Part 3:

    - a written duty is only honoured while that zone's manual mode flag is latched; the automatic control
      loop reclaims every unlatched zone (`auto_duty`) within about a second, which the model applies before
      each command;
    - a zone in failsafe is pinned at 100% and every duty written to it is discarded;
    - selector `0x00` of `0x30 0x70 0x66` reads a duty and writes nothing, whatever follows the zone byte;
    - a written percentage is stored as an 8-bit PWM value and converted back on read, truncating both
      divisions, so a duty is exact at multiples of 20 and one percent low elsewhere.

    Attributes are public so a test can seed a state (`failsafe[2] = True`) or assert one
    (`manual == {0: True, ...}`) directly.
    """

    ZONE_OUT_OF_RANGE: int = 0xCC       # Completion code for a zone the board does not have

    zones: int                          # Number of fan zones the modelled board has
    auto_duty: int                      # Duty the automatic control loop drives an unlatched zone to
    manual: Dict[int, bool]             # IPMI zone -> manual mode flag
    failsafe: Dict[int, bool]           # IPMI zone -> failsafe flag (zone forced to 100%)
    duty: Dict[int, int]                # IPMI zone -> current duty in %
    fan_mode: int                       # Base fan mode, the curve an unlatched zone falls back to
    supported_modes: int                # Bitmask of the base fan modes the modelled board supports
    fan_mode_writes: int                # How often the base fan mode was written
    duty_at_release: Dict[int, int]     # Duty of every zone at the moment manual mode was last released
    commands: List[List[str]]           # Every command received, in order

    def __init__(self, zones: int = 5, auto_duty: int = 30, fan_mode: int = 1,
                 supported_modes: int = 0x0FFF) -> None:
        """Initialize the modelled board.
        Args:
            zones (int): number of fan zones the board has
            auto_duty (int): duty the automatic control loop drives an unlatched zone to
            fan_mode (int): base fan mode reported by `0x30 0x45 0x00`
            supported_modes (int): bitmask of the base fan modes the board reports (default: 0x00-0x0B)
        """
        self.zones = zones
        self.auto_duty = auto_duty
        self.manual = {z: False for z in range(zones)}
        self.failsafe = {z: False for z in range(zones)}
        self.duty = {z: auto_duty for z in range(zones)}
        self.fan_mode = fan_mode
        self.supported_modes = supported_modes
        self.fan_mode_writes = 0
        self.duty_at_release = {}
        self.commands = []

    @property
    def latched_zones(self) -> List[int]:
        """The zones whose manual mode flag is currently set."""
        return sorted(z for z, latched in self.manual.items() if latched)

    def _settle(self) -> None:
        """Let the BMC's own loop run: failsafe pins its zone at 100%, and the automatic curve reclaims
        every zone that is not latched."""
        for zone in range(self.zones):
            if self.failsafe[zone]:
                self.duty[zone] = 100
            elif not self.manual[zone]:
                self.duty[zone] = self.auto_duty

    def _record_release(self) -> None:
        """Snapshot the duty of every zone as manual mode is released.

        The exit level is a transition on this stack: the BMC's own curve takes the zones back within about
        a second, so the level cannot be observed after the fact. This is what makes the ordering inside
        `end()` visible - a release that runs before the level write hands the fans back at the automatic
        duty, and the level never reaches them at all.
        """
        self.duty_at_release = dict(self.duty)

    def _zone(self, arg: str, offset: int = 0) -> int:
        """Decode a zone byte, raising the board's own completion code for a zone it does not have.
        Args:
            arg (str): the zone byte as ipmitool receives it
            offset (int): 1 for the OEM manual/failsafe commands, which count zones from 1
        Returns:
            int: the 0-based zone ID
        """
        zone = int(arg, 16) - offset
        if zone < 0 or zone >= self.zones:
            raise IpmiError(f"ipmitool error (1): rsp=0x{self.ZONE_OUT_OF_RANGE:02x}.", self.ZONE_OUT_OF_RANGE)
        return zone

    @staticmethod
    def _stored(percent: int) -> int:
        """The duty a written percentage actually becomes.

        The BMC keeps an 8-bit PWM value, `pwm = percent * 255 / 100`, and converts back when the duty is
        read, truncating both divisions. So a write of 50% is running at, and reads back as, 49%.
        """
        return ((percent * 255) // 100) * 100 // 255

    @staticmethod
    def _reply(stdout: str) -> subprocess.CompletedProcess:
        """Wrap a reply the way `Ipmi._exec_ipmitool()` hands it to a platform."""
        return subprocess.CompletedProcess([], returncode=0, stdout=stdout, stderr="")

    def _fan_mode(self, args: List[str]) -> subprocess.CompletedProcess:
        """Handle the base fan mode commands: read, supported-mode bitmask, and write."""
        if args[3] == "0x00":
            return self._reply(f"{self.fan_mode}")
        if args[3] == "0x02":
            # Two bytes, little-endian, one bit per mode value.
            return self._reply(f" {self.supported_modes & 0xFF:02x} {self.supported_modes >> 8:02x}")
        self.fan_mode_writes += 1
        self.fan_mode = int(args[4], 16)
        # A base fan mode change clears manual mode on every zone.
        self.manual = {z: False for z in range(self.zones)}
        return self._reply("")

    def _oem(self, args: List[str]) -> subprocess.CompletedProcess:
        """Handle the OEM manual/failsafe commands, whose replies echo the IANA ID before the payload."""
        op = args[6]
        zone = self._zone(args[7], offset=1)
        if op == "0x00":
            return self._reply(f" cf c2 00 {int(self.manual[zone]):02x}")
        if op == "0x02":
            return self._reply(f" cf c2 00 {int(self.failsafe[zone]):02x}")
        if op == "0x01":
            if self.manual[zone] and args[8] == "0x00":
                self._record_release()
            self.manual[zone] = args[8] == "0x01"
            return self._reply("")
        raise IpmiError("ipmitool error (1): rsp=0xc1.", 0xC1)

    def _duty(self, args: List[str]) -> subprocess.CompletedProcess:
        """Handle the duty commands: 0x00 reads, 0x01 writes, 0x02 toggles manual mode in every zone."""
        selector = args[4]
        if selector == "0x00":
            # A trailing duty byte is ignored: this selector never writes.
            return self._reply(f" {self.duty[self._zone(args[5])]:02x}")
        if selector == "0x01":
            zone = self._zone(args[5])
            if not self.failsafe[zone]:
                self.duty[zone] = self._stored(int(args[6], 16))
            return self._reply("")
        if selector == "0x02":
            if args[5] == "0x00" and any(self.manual.values()):
                self._record_release()
            self.manual = {z: args[5] == "0x01" for z in range(self.zones)}
            return self._reply("")
        raise IpmiError("ipmitool error (1): rsp=0xc1.", 0xC1)

    def __call__(self, args: List[str]) -> subprocess.CompletedProcess:
        """Execute one ipmitool command against the modelled board.
        Args:
            args (List[str]): ipmitool arguments, as a platform passes them to its exec callback
        Returns:
            subprocess.CompletedProcess: the BMC reply
        Raises:
            IpmiError: the board rejected the command, carrying its completion code
        """
        self.commands.append(list(args))
        self._settle()
        if args[:3] == ["raw", "0x30", "0x45"]:
            return self._fan_mode(args)
        if args[:6] == ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00"]:
            return self._oem(args)
        if args[:4] == ["raw", "0x30", "0x70", "0x66"]:
            return self._duty(args)
        raise IpmiError("ipmitool error (1): rsp=0xc1.", 0xC1)

# End.
