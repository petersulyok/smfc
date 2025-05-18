#
#   gpuzone.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.GpuZone() class implementation.
#
import subprocess
import time
import re
from configparser import ConfigParser
from typing import List
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log


class GpuZone(FanController):
    """Class for GPU zone fan control."""

    # GpuZone specific parameters.
    gpu_device_ids: List[int]           # GPU device IDs (indexes)
    nvidia_smi_path: str                # Path for `nvidia-smi` command
    nvidia_smi_called: float            # Timestamp when `nvidia-smi` command executed
    gpu_temperature: List[float]        # List of GPU temperatures

    # Constant values for the configuration parameters.
    CS_GPU_ZONE: str = 'GPU zone'
    CV_GPU_ZONE_ENABLED: str = 'enabled'
    CV_GPU_IPMI_ZONE: str = 'ipmi_zone'
    CV_GPU_ZONE_TEMP_CALC: str = 'temp_calc'
    CV_GPU_ZONE_STEPS: str = 'steps'
    CV_GPU_ZONE_SENSITIVITY: str = 'sensitivity'
    CV_GPU_ZONE_POLLING: str = 'polling'
    CV_GPU_ZONE_MIN_TEMP: str = 'min_temp'
    CV_GPU_ZONE_MAX_TEMP: str = 'max_temp'
    CV_GPU_ZONE_MIN_LEVEL: str = 'min_level'
    CV_GPU_ZONE_MAX_LEVEL: str = 'max_level'
    CV_GPU_ZONE_GPU_IDS: str = 'gpu_device_ids'
    CV_GPU_ZONE_NVIDIA_SMI_PATH: str = 'nvidia_smi_path'

    def __init__(self, log: Log, ipmi: Ipmi, config: ConfigParser) -> None:
        """Initialize the GpuZone class. Abort in case of configuration errors.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            config (configparser.ConfigParser): reference to the configuration (default=None)
        Raises:
            ValueError: invalid parameters
        """
        gpu_id_list: str    # String for gpu_device_ids=
        count: int          # GPU count.

        # Save and validate GpuZone class-specific parameters.
        gpu_id_list = config[self.CS_GPU_ZONE].get(self.CV_GPU_ZONE_GPU_IDS, '0')
        gpu_id_list = re.sub(' +', ' ', gpu_id_list.strip())
        try:
            self.gpu_device_ids = [int(s) for s in gpu_id_list.split(',' if ',' in gpu_id_list else ' ')]
        except ValueError as e:
            raise e
        for gid in self.gpu_device_ids:
            if gid not in range(0, 101):
                raise ValueError(f'invalid value: {self.CV_GPU_ZONE_GPU_IDS}={gpu_id_list}.')
        count = len(self.gpu_device_ids)
        self.nvidia_smi_path = config[GpuZone.CS_GPU_ZONE].get(GpuZone.CV_GPU_ZONE_NVIDIA_SMI_PATH,
                                                              '/usr/bin/nvidia-smi')
        self.nvidia_smi_called = 0

        # Initialize FanController class.
        super().__init__(log, ipmi,
            config[GpuZone.CS_GPU_ZONE].get(GpuZone.CV_GPU_IPMI_ZONE, fallback=f'{Ipmi.HD_ZONE}'),
            GpuZone.CS_GPU_ZONE, count,
            config[GpuZone.CS_GPU_ZONE].getint(GpuZone.CV_GPU_ZONE_TEMP_CALC, fallback=FanController.CALC_AVG),
            config[GpuZone.CS_GPU_ZONE].getint(GpuZone.CV_GPU_ZONE_STEPS, fallback=5),
            config[GpuZone.CS_GPU_ZONE].getfloat(GpuZone.CV_GPU_ZONE_SENSITIVITY, fallback=2),
            config[GpuZone.CS_GPU_ZONE].getfloat(GpuZone.CV_GPU_ZONE_POLLING, fallback=2),
            config[GpuZone.CS_GPU_ZONE].getfloat(GpuZone.CV_GPU_ZONE_MIN_TEMP, fallback=40),
            config[GpuZone.CS_GPU_ZONE].getfloat(GpuZone.CV_GPU_ZONE_MAX_TEMP, fallback=70),
            config[GpuZone.CS_GPU_ZONE].getint(GpuZone.CV_GPU_ZONE_MIN_LEVEL, fallback=35),
            config[GpuZone.CS_GPU_ZONE].getint(GpuZone.CV_GPU_ZONE_MAX_LEVEL, fallback=100)
        )

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f'   {self.CV_GPU_ZONE_GPU_IDS} = {self.gpu_device_ids}')
            self.log.msg(Log.LOG_CONFIG, f'   {self.CV_GPU_ZONE_NVIDIA_SMI_PATH} = {self.nvidia_smi_path}')

    def _exec_nvidia_smi(self, arguments: List[str]) -> subprocess.CompletedProcess:
        """Execution of the `nvidia-smi` command.
            Args:
                arguments (List[str]): list of argument of `nvidia-smi` command
            Raises:
                FileNotFoundError: command not found
        """
        r: subprocess.CompletedProcess  # Result of the executed process
        args: List[str] = []            # List of arguments

        # Execute `nvidia-smi` command.
        try:
            args.append(self.nvidia_smi_path)
            args.extend(arguments)
            r = subprocess.run(args, check=False, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise e
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

            r = self._exec_nvidia_smi(['--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'])
            self.nvidia_smi_called = current_time
            temp_list = r.stdout.splitlines()
            self.gpu_temperature = []
            for gid in self.gpu_device_ids:
                self.gpu_temperature.append(int(temp_list[gid]))

        return self.gpu_temperature[index]


# End.
