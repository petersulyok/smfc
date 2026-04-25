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
from typing import List, Optional
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

    def __init__(self, log: Log, ipmi: Ipmi, config: ConfigParser) -> None:
        """Initialize the GPU fan controller class and raise exception in case of invalid configuration.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            config (ConfigParser): reference to the configuration
        Raises:
            ValueError: invalid configuration parameters
        """
        gpu_id_list: str    # String for gpu_device_ids=
        count: int          # GPU count.

        # Save and validate GpuFc class-specific parameters.
        self.gpu_type = config[self.CS_GPU_FC].get(self.CV_GPU_FC_GPU_TYPE, "nvidia").lower()
        if self.gpu_type not in ["nvidia", "amd"]:
            raise ValueError(f"invalid value: {self.CV_GPU_FC_GPU_TYPE}={self.gpu_type}.")

        gpu_id_list = config[self.CS_GPU_FC].get(self.CV_GPU_FC_GPU_IDS, "0")
        gpu_id_list = re.sub(" +", " ", gpu_id_list.strip())
        # May raise ValueError if GPU ID string contains non-integer values.
        self.gpu_device_ids = [int(s) for s in gpu_id_list.split("," if "," in gpu_id_list else " ")]
        for gid in self.gpu_device_ids:
            if gid not in range(0, 101):
                raise ValueError(f"invalid value: {self.CV_GPU_FC_GPU_IDS}={gpu_id_list}.")
        count = len(self.gpu_device_ids)
        self.nvidia_smi_path = config[GpuFc.CS_GPU_FC].get(GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH, "/usr/bin/nvidia-smi")
        self.rocm_smi_path = config[GpuFc.CS_GPU_FC].get(GpuFc.CV_GPU_FC_ROCM_SMI_PATH, "/usr/bin/rocm-smi")
        self.smi_called = 0

        # Initialize FanController class.
        super().__init__(
            log, ipmi,
            config[GpuFc.CS_GPU_FC].get(GpuFc.CV_GPU_FC_IPMI_ZONE, fallback=f"{Ipmi.HD_ZONE}"),
            GpuFc.CS_GPU_FC, count,
            config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_STEPS, fallback=5),
            config[GpuFc.CS_GPU_FC].getfloat(GpuFc.CV_GPU_FC_SENSITIVITY, fallback=2),
            config[GpuFc.CS_GPU_FC].getfloat(GpuFc.CV_GPU_FC_POLLING, fallback=2),
            config[GpuFc.CS_GPU_FC].getfloat(GpuFc.CV_GPU_FC_MIN_TEMP, fallback=40),
            config[GpuFc.CS_GPU_FC].getfloat(GpuFc.CV_GPU_FC_MAX_TEMP, fallback=70),
            config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_MIN_LEVEL, fallback=35),
            config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_MAX_LEVEL, fallback=100),
            config[GpuFc.CS_GPU_FC].getint(GpuFc.CV_GPU_FC_SMOOTHING, fallback=1),
        )

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_GPU_TYPE} = {self.gpu_type}")
            self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_GPU_IDS} = {self.gpu_device_ids}")
            if self.gpu_type == "nvidia":
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_NVIDIA_SMI_PATH} = {self.nvidia_smi_path}")
            else:
                self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_ROCM_SMI_PATH} = {self.rocm_smi_path}")

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
                r = self._exec_smi(self.nvidia_smi_path, ["--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"])
                self.smi_called = current_time
                temp_list = r.stdout.splitlines()
                self.gpu_temperature = []
                for gid in self.gpu_device_ids:
                    self.gpu_temperature.append(float(temp_list[gid]))
            else:
                # AMD GPUs using rocm-smi
                r = self._exec_smi(self.rocm_smi_path, ["-t", "--json"])
                self.smi_called = current_time
                try:
                    data = json.loads(r.stdout)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Failed to parse rocm-smi JSON output: {e}") from e

                # Sort keys to ensure card0, card1... mapping is consistent if needed,
                # though usually json keys for cards are card0, card1...
                cards = sorted(data.keys(), key=lambda x: int(re.search(r"\d+", x).group()) if re.search(r"\d+", x) else 0)
                self.gpu_temperature = []
                for gid in self.gpu_device_ids:
                    card_name = cards[gid]
                    card_data = data[card_name]
                    # Prefer junction, then edge, then memory temperature.
                    temp: Optional[float] = None
                    for key in ["Temperature (Sensor junction) (C)",
                                "Temperature (Sensor edge) (C)",
                                "Temperature (Sensor memory) (C)"]:
                        if key in card_data:
                            temp = float(card_data[key])
                            break
                    if temp is None:
                        raise ValueError(f"No temperature data found for {card_name}")
                    self.gpu_temperature.append(temp)

        return self.gpu_temperature[index]


# End.
