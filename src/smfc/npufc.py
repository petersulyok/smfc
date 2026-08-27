#
#   npufc.py (C) 2026
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.NpuFc() class implementation.
#
import re
import subprocess
import time
from typing import List
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import NpuConfig


class NpuFc(FanController):
    """Class for Ascend NPU (e.g. Atlas 300I Duo) fan controller.

    Temperatures are read with `npu-smi info -t temp -i <card_id>`: one call per card per polling
    window. Each card exposes one line per chip ("Temperature (C)"); the controller tracks the
    hottest chip of every configured card, so a dual-chip card counts as one device.
    """

    config: NpuConfig

    # NpuFc specific parameters.
    smi_called: float                # Timestamp when the last npu-smi call was issued
    npu_temperature: List[float]     # Cached per-card temperatures (hottest chip of each card)
    # Chip-temperature line key, anchored to the line start so "Soc Max Temperature (C)" (from
    # `npu-smi -t sensors`) and the MCU block keys (T_LM75A/T_CORE_M/...) are never matched.
    _temp_line_re = re.compile(r"^\s*Temperature\s*\(C\)\s*:\s*(-?\d+)", re.MULTILINE)

    def __init__(self, log: Log, ipmi: Ipmi, cfg: NpuConfig) -> None:
        """Initialize the NPU fan controller class and raise exception in case of invalid configuration.
        Args:
            log (Log): reference to a Log class instance
            ipmi (Ipmi): reference to an Ipmi class instance
            cfg (NpuConfig): NPU fan controller configuration
        Raises:
            ValueError: invalid configuration parameters
        """
        # Store config reference first (required by base class)
        self.config = cfg
        self.smi_called = 0
        self.npu_temperature = []
        self.hwmon_path = []  # NPU doesn't use hwmon_path, but base class expects it

        # Initialize FanController class.
        super().__init__(log, ipmi, cfg.section, len(cfg.npu_device_ids))

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            self.log.msg(Log.LOG_CONFIG, f"   npu_device_ids = {self.config.npu_device_ids}")
            self.log.msg(Log.LOG_CONFIG, f"   npu_smi_path = {self.config.npu_smi_path}")
            self.log.msg(Log.LOG_CONFIG, f"   npu_smi_timeout = {self.config.npu_smi_timeout}")

    def _exec_smi(self, card_id: int) -> str:
        """Execute `npu-smi info -t temp -i <card_id>` and return its standard output.
        Args:
            card_id (int): NPU card ID
        Returns:
            str: stdout of the executed command
        Raises:
            FileNotFoundError: npu-smi command not found
            RuntimeError: non-zero exit code or the command timed out
        """
        args = [self.config.npu_smi_path, "info", "-t", "temp", "-i", str(card_id)]
        try:
            r = subprocess.run(args, check=False, capture_output=True, text=True,
                               timeout=self.config.npu_smi_timeout)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"npu-smi timed out after {self.config.npu_smi_timeout}s (card {card_id})") from e
        if r.returncode != 0:
            raise RuntimeError(f"npu-smi failed (card {card_id}, rc={r.returncode}): {r.stderr.strip()}")
        return r.stdout

    @classmethod
    def parse_card_temps(cls, output: str) -> List[float]:
        """Parse per-chip temperatures from `npu-smi info -t temp` output.

        Only chip temperature lines ("Temperature (C) : <int>") are matched; MCU block lines
        (T_LM75A/T_CORE_M/...) and "Soc Max Temperature" use different keys and are ignored.
        Args:
            output (str): stdout of `npu-smi info -t temp -i <card_id>`
        Returns:
            List[float]: temperature of each chip in the card
        """
        return [float(m.group(1)) for m in cls._temp_line_re.finditer(output)]

    def _get_nth_temp(self, index: int) -> float:
        """Get the temperature of the nth configured NPU card (hottest chip).
        Args:
            index (int): index in the npu_device_ids list
        Returns:
            float: hottest chip temperature of the card (C)
        Raises:
            FileNotFoundError: npu-smi command not found
            ValueError: no temperature found in the npu-smi output
            RuntimeError: non-zero npu-smi exit code or timeout
        """
        current_time = time.monotonic()
        if (current_time - self.smi_called) >= self.config.polling:
            self.smi_called = current_time
            self.npu_temperature = []
            for nid in self.config.npu_device_ids:
                temps = self.parse_card_temps(self._exec_smi(nid))
                if not temps:
                    raise ValueError(f"npu-smi output contains no chip temperature (card {nid})")
                self.npu_temperature.append(max(temps))
        return self.npu_temperature[index]

    def device_names(self) -> List[str]:
        """Return per-card device labels (npu<id> using configured npu_device_ids)
        matching last_per_device_temps positionally."""
        return [f"npu{gid}" for gid in self.config.npu_device_ids]


# End.
