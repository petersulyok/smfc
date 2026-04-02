#
#   gpufc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.GpuFc() class implementation.
#
import subprocess
import time
import re
from configparser import ConfigParser
from typing import List
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class GpuFc(FanController):
    """Class for GPU fan controller."""

    # GpuFc specific parameters.
    gpu_device_ids: List[int]       # GPU device IDs (indexes)
    nvidia_smi_path: str            # Path for `nvidia-smi` command
    nvidia_smi_called: float        # Timestamp when `nvidia-smi` command executed
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
    CV_GPU_FC_GPU_IDS: str = "gpu_device_ids"
    CV_GPU_FC_NVIDIA_SMI_PATH: str = "nvidia_smi_path"

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
        gpu_id_list = config[self.CS_GPU_FC].get(self.CV_GPU_FC_GPU_IDS, "0")
        gpu_id_list = re.sub(" +", " ", gpu_id_list.strip())
        # May raise ValueError if GPU ID string contains non-integer values.
        self.gpu_device_ids = [int(s) for s in gpu_id_list.split("," if "," in gpu_id_list else " ")]
        for gid in self.gpu_device_ids:
            if gid not in range(0, 101):
                raise ValueError(f"invalid value: {self.CV_GPU_FC_GPU_IDS}={gpu_id_list}.")
        count = len(self.gpu_device_ids)
        self.nvidia_smi_path = config[GpuFc.CS_GPU_FC].get(GpuFc.CV_GPU_FC_NVIDIA_SMI_PATH, "/usr/bin/nvidia-smi")
        self.nvidia_smi_called = 0

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
            self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_GPU_IDS} = {self.gpu_device_ids}")
            self.log.msg(Log.LOG_CONFIG, f"   {self.CV_GPU_FC_NVIDIA_SMI_PATH} = {self.nvidia_smi_path}")

    def _exec_nvidia_smi(self, arguments: List[str]) -> subprocess.CompletedProcess:
        """Execute the `nvidia-smi` command.
        Args:
            arguments (List[str]): list of arguments of `nvidia-smi` command
        Returns:
            subprocess.CompletedProcess: result of the executed subprocess
        Raises:
            FileNotFoundError: command not found
        """
        r: subprocess.CompletedProcess  # Result of the executed process
        args: List[str] = []  # List of arguments

        # Execute `nvidia-smi` command.
        args.append(self.nvidia_smi_path)
        args.extend(arguments)
        # May raise FileNotFoundError if nvidia-smi is not found.
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
        if (current_time - self.nvidia_smi_called) >= self.polling:
            r: subprocess.CompletedProcess  # result of the executed process

            r = self._exec_nvidia_smi(["--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"])
            self.nvidia_smi_called = current_time
            temp_list = r.stdout.splitlines()
            self.gpu_temperature = []
            for gid in self.gpu_device_ids:
                self.gpu_temperature.append(int(temp_list[gid]))

        return self.gpu_temperature[index]


# End.
