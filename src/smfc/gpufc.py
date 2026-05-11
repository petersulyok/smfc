#
#   gpufc.py (C) 2020-2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.GpuFc() class implementation.
#
import subprocess
import time
import json
from typing import List
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import GpuConfig, Config


class GpuFc(FanController):
    """Class for GPU fan controller."""

    config: GpuConfig

    # GpuFc specific parameters.
    smi_called: float               # Timestamp when SMI command executed
    gpu_temperature: List[float]    # List of GPU temperatures

    def __init__(self, log: Log, ipmi: Ipmi, cfg: GpuConfig) -> None:
        """Initialize the GPU fan controller class and raise exception in case of invalid configuration.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            cfg (GpuConfig): GPU fan controller configuration
        Raises:
            ValueError: invalid configuration parameters
        """
        # Store config reference first (required by base class)
        self.config = cfg
        self.smi_called = 0
        self.hwmon_path = []  # GPU doesn't use hwmon_path, but base class expects it

        # Initialize FanController class.
        super().__init__(log, ipmi, cfg.section, len(cfg.gpu_device_ids))

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   gpu_type = {self.config.gpu_type}")
            self.log.msg(Log.LOG_CONFIG, f"   gpu_device_ids = {self.config.gpu_device_ids}")
            if self.config.gpu_type == "nvidia":
                self.log.msg(Log.LOG_CONFIG, f"   nvidia_smi_path = {self.config.nvidia_smi_path}")
            else:
                self.log.msg(Log.LOG_CONFIG, f"   rocm_smi_path = {self.config.rocm_smi_path}")
                self.log.msg(Log.LOG_CONFIG, f"   amd_temp_sensor = {self.config.amd_temp_sensor}")

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
        if (current_time - self.smi_called) >= self.config.polling:
            r: subprocess.CompletedProcess  # result of the executed process

            if self.config.gpu_type == "nvidia":
                nvidia_args = ["--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"]
                r = self._exec_smi(self.config.nvidia_smi_path, nvidia_args)
                self.smi_called = current_time
                temp_list = r.stdout.splitlines()
                self.gpu_temperature = []
                for gid in self.config.gpu_device_ids:
                    self.gpu_temperature.append(float(temp_list[gid]))
            else:
                r = self._exec_smi(self.config.rocm_smi_path, ["-t", "--json"])
                self.smi_called = current_time
                try:
                    data = json.loads(r.stdout)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Failed to parse rocm-smi JSON output: {e}") from e
                self.gpu_temperature = []
                temp_key = Config.CV_AMD_TEMP_KEYS[self.config.amd_temp_sensor]
                for gid in self.config.gpu_device_ids:
                    card_key = f"card{gid}"
                    if card_key not in data:
                        raise ValueError(f"{card_key} not found in rocm-smi output")
                    card_data = data[card_key]
                    if temp_key not in card_data:
                        raise ValueError(f"No temperature data found for {card_key}")
                    self.gpu_temperature.append(float(card_data[temp_key]))

        return self.gpu_temperature[index]


# End.
