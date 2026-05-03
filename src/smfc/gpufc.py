#
#   gpufc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.GpuFc() class implementation.
#
import subprocess
import time
import re
import json
from configparser import ConfigParser
from typing import List
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class GpuFc(FanController):
    """Class for GPU fan controller."""

    # GpuFc specific parameters.
    gpu_type: str                   # GPU type: 'nvidia' or 'amd'
    gpu_device_ids: List[int]       # GPU device IDs (indexes)
    nvidia_smi_path: str            # Path for `nvidia-smi` command
    rocm_smi_path: str              # Path for `rocm-smi` command
    amd_temp_sensor: int            # AMD temperature sensor (0-junction, 1-edge, 2-memory)
    smi_called: float               # Timestamp when SMI command executed
    gpu_temperature: List[float]    # List of GPU temperatures

    # Constant values for the configuration parameters.
    CS_GPU_FC: str = "GPU"
    CV_GPU_FC_ENABLED: str = "enabled"
    CV_GPU_FC_IPMI_ZONE: str = "ipmi_zone"
    CV_GPU_FC_TEMP_CALC: str = "temp_calc"
    CV_GPU_FC_STEPS: str = "steps"
    CV_GPU_FC_SENSITIVITY: str = "sensitivity"
    CV_GPU_FC_POLLING: str = "polling"
    CV_GPU_FC_MIN_TEMP: str = "min_temp"
    CV_GPU_FC_MAX_TEMP: str = "max_temp"
    CV_GPU_FC_MIN_LEVEL: str = "min_level"
    CV_GPU_FC_MAX_LEVEL: str = "max_level"
    CV_GPU_FC_SMOOTHING: str = "smoothing"
    CV_GPU_FC_GPU_TYPE: str = "gpu_type"
    CV_GPU_FC_GPU_IDS: str = "gpu_device_ids"
    CV_GPU_FC_NVIDIA_SMI_PATH: str = "nvidia_smi_path"
    CV_GPU_FC_ROCM_SMI_PATH: str = "rocm_smi_path"
    CV_GPU_FC_AMD_TEMP_SENSOR: str = "amd_temp_sensor"
    CV_AMD_TEMP_JUNCTION: str = "Temperature (Sensor junction) (C)"
    CV_AMD_TEMP_EDGE: str = "Temperature (Sensor edge) (C)"
    CV_AMD_TEMP_MEMORY: str = "Temperature (Sensor memory) (C)"
    CV_AMD_TEMP_KEYS: tuple = (CV_AMD_TEMP_JUNCTION, CV_AMD_TEMP_EDGE, CV_AMD_TEMP_MEMORY)

    def __init__(self, log: Log, ipmi: Ipmi, config: ConfigParser, section: str = CS_GPU_FC) -> None:
        """Initialize the GPU fan controller class and raise exception in case of invalid configuration.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            config (ConfigParser): reference to the configuration
            section (str): configuration section name (default: CS_GPU_FC)
        Raises:
            ValueError: invalid configuration parameters
        """
        gpu_id_list: str    # String for gpu_device_ids=
        count: int          # GPU count.

        # Save and validate GpuFc class-specific parameters.
        self.gpu_type = config[section].get(self.CV_GPU_FC_GPU_TYPE, "nvidia").lower()
        if self.gpu_type not in ["nvidia", "amd"]:
            raise ValueError(f"invalid value: {self.CV_GPU_FC_GPU_TYPE}={self.gpu_type}.")

        gpu_id_list = config[section].get(self.CV_GPU_FC_GPU_IDS, "0")
        gpu_id_list = re.sub(" +", " ", gpu_id_list.strip())
        # May raise ValueError if GPU ID string contains non-integer values.
        self.gpu_device_ids = [int(s) for s in gpu_id_list.split("," if "," in gpu_id_list else " ")]
        for gid in self.gpu_device_ids:
            if gid not in range(0, 101):
                raise ValueError(f"invalid value: {self.CV_GPU_FC_GPU_IDS}={gpu_id_list}.")
        count = len(self.gpu_device_ids)
        self.nvidia_smi_path = config[section].get(GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH, "/usr/bin/nvidia-smi")
        self.rocm_smi_path = config[section].get(GpuFc.CV_GPU_FC_ROCM_SMI_PATH, "/usr/bin/rocm-smi")
        self.amd_temp_sensor = config[section].getint(GpuFc.CV_GPU_FC_AMD_TEMP_SENSOR, fallback=0)
        if self.amd_temp_sensor not in range(0, 3):
            raise ValueError(f"invalid value: {self.CV_GPU_FC_AMD_TEMP_SENSOR}={self.amd_temp_sensor}.")
        self.smi_called = 0

        # Initialize FanController class.
        super().__init__(
            log, ipmi,
            config[section].get(GpuFc.CV_GPU_FC_IPMI_ZONE, fallback=f"{Ipmi.HD_ZONE}"),
            section, count,
            config[section].getint(GpuFc.CV_GPU_FC_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[section].getint(GpuFc.CV_GPU_FC_STEPS, fallback=5),
            config[section].getfloat(GpuFc.CV_GPU_FC_SENSITIVITY, fallback=2),
            config[section].getfloat(GpuFc.CV_GPU_FC_POLLING, fallback=2),
            config[section].getfloat(GpuFc.CV_GPU_FC_MIN_TEMP, fallback=40),
            config[section].getfloat(GpuFc.CV_GPU_FC_MAX_TEMP, fallback=70),
            config[section].getint(GpuFc.CV_GPU_FC_MIN_LEVEL, fallback=35),
            config[section].getint(GpuFc.CV_GPU_FC_MAX_LEVEL, fallback=100),
            config[section].getint(GpuFc.CV_GPU_FC_SMOOTHING, fallback=1),
        )

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_GPU_TYPE} = {self.gpu_type}")
            self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_GPU_IDS} = {self.gpu_device_ids}")
            if self.gpu_type == "nvidia":
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_NVIDIA_SMI_PATH} = {self.nvidia_smi_path}")
            else:
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_ROCM_SMI_PATH} = {self.rocm_smi_path}")
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_AMD_TEMP_SENSOR} = {self.amd_temp_sensor}")

    def _exec_smi(self, command_path: str, arguments: List[str]) -> subprocess.CompletedProcess:
        """Execute the SMI command (nvidia-smi or rocm-smi).
        Args:
            command_path (str): path to the SMI command
            arguments (List[str]): list of arguments of SMI command
        Returns:
            subprocess.CompletedProcess: result of the executed subprocess
        Raises:
            FileNotFoundError: command not found
        """
        r: subprocess.CompletedProcess  # Result of the executed process
        args: List[str] = []  # List of arguments

        # Execute command.
        args.append(command_path)
        args.extend(arguments)
        # May raise FileNotFoundError if command is not found.
        r = subprocess.run(args, check=False, capture_output=True, text=True)
        return r

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the nth element in the GPU device list.
        Args:
            index (int): index in GPU device list
        Returns:
            float: temperature value
        Raises:
            FileNotFoundError:  file or command cannot be found
            ValueError:         invalid temperature value
            IndexError:         invalid index
        """
        current_time = time.monotonic()
        if (current_time - self.smi_called) >= self.polling:
            r: subprocess.CompletedProcess  # result of the executed process

            if self.gpu_type == "nvidia":
                nvidia_args = ["--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"]
                r = self._exec_smi(self.nvidia_smi_path, nvidia_args)
                self.smi_called = current_time
                temp_list = r.stdout.splitlines()
                self.gpu_temperature = []
                for gid in self.gpu_device_ids:
                    self.gpu_temperature.append(float(temp_list[gid]))
            else:
                r = self._exec_smi(self.rocm_smi_path, ["-t", "--json"])
                self.smi_called = current_time
                try:
                    data = json.loads(r.stdout)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Failed to parse rocm-smi JSON output: {e}") from e
                self.gpu_temperature = []
                temp_key = self.CV_AMD_TEMP_KEYS[self.amd_temp_sensor]
                for gid in self.gpu_device_ids:
                    card_key = f"card{gid}"
                    if card_key not in data:
                        raise ValueError(f"{card_key} not found in rocm-smi output")
                    card_data = data[card_key]
                    if temp_key not in card_data:
                        raise ValueError(f"No temperature data found for {card_key}")
                    self.gpu_temperature.append(float(card_data[temp_key]))

        return self.gpu_temperature[index]


# End.
