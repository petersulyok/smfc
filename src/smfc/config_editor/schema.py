#
#   schema.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.schema: field and section metadata of the configuration file, used by smfc-config.
#
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from smfc.config import Config, PlatformName


class FieldKind(str, Enum):
    """Value kind of a configuration parameter. It decides how the value is parsed, validated and edited."""
    BOOL = "bool"                   # 0/1 flag
    INT = "int"                     # integer number
    FLOAT = "float"                 # floating point number
    STR = "str"                     # free text
    PATH = "path"                   # path of a command or a file
    ENUM = "enum"                   # one value of a fixed set
    INT_LIST = "int_list"           # comma- or space-separated list of integers
    STR_LIST = "str_list"           # comma- or space-separated list of strings
    DEVICE_LIST = "device_list"     # multi-line list of /dev/disk/by-id/... names
    CURVE = "curve"                 # temperature-level pairs of control_function=


class Widget(str, Enum):
    """Editor widget of a configuration parameter."""
    INLINE = "inline"       # typed in the value cell of the right pane
    POPUP = "popup"         # typed in a popup with a wide input field
    SELECT = "select"       # one value picked from a list
    DEVICES = "devices"     # several values ticked in the device popup


# Value kinds edited in a popup, because their value is longer than the value cell of the right pane.
_POPUP_KINDS: Tuple[FieldKind, ...] = (FieldKind.STR, FieldKind.PATH, FieldKind.CURVE,
                                      FieldKind.STR_LIST)

# Value kinds edited in the multi-select device popup.
_DEVICE_KINDS: Tuple[FieldKind, ...] = (FieldKind.DEVICE_LIST, FieldKind.INT_LIST)

# Names of the four keys a control_function= value overrides. They are ignored and not validated by Config.
CURVE_OVERRIDES: Tuple[str, ...] = (Config.CV_MIN_TEMP, Config.CV_MAX_TEMP, Config.CV_MIN_LEVEL,
                                    Config.CV_MAX_LEVEL)


@dataclass(frozen=True)
class Field:
    """Metadata of one configuration parameter.
    `summary` and `detail` feed the help pane of smfc-config: the summary is one line beside the key name, the
    detail is the two lines below it. They are not a copy of the comment in the configuration file: a comment
    is one short line, while the pane has room to say when to change the value and what it interacts with.
    """
    key: str                                # Parameter name, as written in the configuration file
    kind: FieldKind                         # Value kind (decides parsing, validation and widget)
    default: Any                            # Default value applied when the key is missing
    summary: str                            # One-line summary (help pane, line 1)
    detail: str                             # Longer explanation (help pane, lines 2 and 3)
    unit: str = ""                          # Unit of the value ("C", "%", "s"), empty if it has none
    minimum: Optional[float] = None         # Smallest accepted value, None if unbounded
    maximum: Optional[float] = None         # Largest accepted value, None if unbounded
    choices: Tuple[Any, ...] = ()           # Accepted values of an ENUM field
    labels: Tuple[str, ...] = ()            # Human-readable label of each choice, in the same order
    provider: str = ""                      # Name of the function listing the candidates of a list field

    @property
    def widget(self) -> Widget:
        """Editor widget of this field.
        Returns:
            Widget: the widget smfc-config opens when the user edits this field
        """
        if self.kind in _DEVICE_KINDS and self.provider:
            return Widget.DEVICES
        if self.kind is FieldKind.ENUM:
            return Widget.SELECT
        if self.kind in _POPUP_KINDS:
            return Widget.POPUP
        return Widget.INLINE

    @property
    def overridden_by_curve(self) -> bool:
        """True if a control_function= value in the same section makes this field inactive.
        Returns:
            bool: True for min_temp, max_temp, min_level and max_level
        """
        return self.key in CURVE_OVERRIDES

    def range_text(self) -> str:
        """Render the type, the unit, the default and the valid range for line 4 of the help pane.
        Returns:
            str: for example "float, C, default 30.0, 0.0 or more"
        """
        parts: List[str] = [self.kind.value]
        if self.unit:
            parts.append(self.unit)
        parts.append("default empty" if self.default in ("", [], ()) else f"default {self.default}")
        if self.choices:
            parts.append("one of " + ", ".join(str(c) for c in self.choices))
        elif self.minimum is not None and self.maximum is not None:
            parts.append(f"{self.minimum} to {self.maximum}")
        elif self.minimum is not None:
            parts.append(f"{self.minimum} or more")
        elif self.maximum is not None:
            parts.append(f"{self.maximum} or less")
        return ", ".join(parts)


@dataclass(frozen=True)
class Section:
    """Metadata of one configuration section.
    A family may hold several instances ([CPU], [CPU:0], [CPU:1] ...). Each instance is a complete, independent
    fan controller with its own parameters; the instances share only the temperature source.
    """
    name: str                       # Family name, as written in the configuration file
    summary: str                    # One-line summary (help pane, line 1)
    detail: str                     # Longer explanation (help pane, lines 2 and 3)
    fields: Tuple[Field, ...]       # Parameters of the section, in the order the shipped file uses
    mandatory: bool = False         # True if the configuration file is invalid without this section
    repeatable: bool = False        # True if numbered instances are allowed
    toggleable: bool = True         # True if the section carries an enabled= key

    def field(self, key: str) -> Optional[Field]:
        """Look up one parameter of this section.
        Args:
            key (str): parameter name
        Returns:
            Optional[Field]: the field, or None if this section does not define it
        """
        for f in self.fields:
            if f.key == key:
                return f
        return None


def _enabled_field(source: str) -> Field:
    """Build the enabled= field of a fan controller section.
    Args:
        source (str): temperature source of the family, for the help text
    Returns:
        Field: the enabled= field
    """
    return Field(
        key=Config.CV_ENABLED, kind=FieldKind.BOOL, default=False,
        summary="Run this fan controller",
        detail=f"When it is off, smfc ignores this section and never reads the {source} temperature. "
               "A section that is missing from the file counts as off.")


def _zone_field(default_zone: int) -> Field:
    """Build the ipmi_zone= field of a fan controller section.
    Args:
        default_zone (int): zone applied when the key is missing
    Returns:
        Field: the ipmi_zone= field
    """
    return Field(
        key=Config.CV_IPMI_ZONE, kind=FieldKind.INT_LIST, default=[default_zone], minimum=0,
        summary="IPMI fan zones this controller drives",
        detail="Zone 0 is the CPU zone and zone 1 the peripheral zone on most boards. Two enabled instances "
               "of one family must not share a zone; different families may.")


def _common_fields(source: str, default_zone: int, temp_calc: int, sensitivity: float, polling: float,
                   steps: int, min_temp: float, max_temp: float, min_level: int, max_level: int) -> List[Field]:
    """Build the parameter block that every temperature-driven fan controller shares.
    Six families use it: CPU, HD, NVME, GPU, NPU and PCI. Only the default values differ between them.
    Args:
        source (str): temperature source of the family, for the help text
        default_zone (int): default IPMI zone
        temp_calc (int): default temperature calculation method
        sensitivity (float): default sensitivity (C)
        polling (float): default polling interval (sec)
        steps (int): default number of discrete steps
        min_temp (float): default minimum temperature (C)
        max_temp (float): default maximum temperature (C)
        min_level (int): default minimum fan level (%)
        max_level (int): default maximum fan level (%)
    Returns:
        List[Field]: the shared fields, in the order the shipped configuration file uses
    """
    return [
        _enabled_field(source),
        _zone_field(default_zone),
        Field(
            key=Config.CV_TEMP_CALC, kind=FieldKind.ENUM, default=temp_calc,
            choices=(Config.CALC_MIN, Config.CALC_AVG, Config.CALC_MAX),
            labels=("minimum", "average", "maximum"),
            summary=f"How several {source} temperatures become one value",
            detail="It has no effect while the section covers a single device. Maximum protects the hottest "
                   "device, average keeps the fans quieter."),
        Field(
            key=Config.CV_SENSITIVITY, kind=FieldKind.FLOAT, default=sensitivity, unit="C", minimum=0.1,
            summary="Temperature change that triggers a new fan level",
            detail="Below this change smfc leaves the fans alone. Raise it if the fans keep chasing small "
                   "temperature swings."),
        Field(
            key=Config.CV_POLLING, kind=FieldKind.FLOAT, default=polling, unit="s", minimum=0.0,
            summary=f"Seconds between two {source} temperature readings",
            detail="A short interval reacts faster and costs more reads. A source that is slow to read needs "
                   "a longer interval."),
        Field(
            key=Config.CV_STEPS, kind=FieldKind.INT, default=steps, minimum=1,
            summary="Discrete steps between the minimum and the maximum level",
            detail="More steps give a smoother curve and more level changes. It must not exceed "
                   "max_level minus min_level."),
        Field(
            key=Config.CV_MIN_TEMP, kind=FieldKind.FLOAT, default=min_temp, unit="C", minimum=0.0, maximum=200.0,
            summary="Lowest temperature of the fan curve",
            detail="Below this temperature the fans stay at min_level. Raise it if the fans spin up too "
                   "early. It must stay below max_temp."),
        Field(
            key=Config.CV_MAX_TEMP, kind=FieldKind.FLOAT, default=max_temp, unit="C", minimum=0.0, maximum=200.0,
            summary="Highest temperature of the fan curve",
            detail="At this temperature the fans reach max_level. Lower it to reach full speed sooner. It "
                   "must stay above min_temp."),
        Field(
            key=Config.CV_MIN_LEVEL, kind=FieldKind.INT, default=min_level, unit="%", minimum=0, maximum=100,
            summary="Fan level at and below min_temp",
            detail="On an X14 or H14 board a value below 5 is raised to 5%, because smfc suspends the BMC "
                   "thermal loop and the duty it writes has no floor of its own."),
        Field(
            key=Config.CV_MAX_LEVEL, kind=FieldKind.INT, default=max_level, unit="%", minimum=0, maximum=100,
            summary="Fan level at and above max_temp",
            detail="Lower it to cap the noise. The fans then never reach full speed, whatever the "
                   "temperature."),
        Field(
            key=Config.CV_CONTROL_FUNCTION, kind=FieldKind.CURVE, default=[],
            summary="Fan curve written as temperature-level pairs",
            detail="At least two pairs, with rising temperatures, for example 30-35, 50-55, 65-100. While it "
                   "carries a value, min_temp, max_temp, min_level and max_level are ignored."),
        Field(
            key=Config.CV_SMOOTHING, kind=FieldKind.INT, default=1, minimum=1,
            summary="Readings averaged together before the curve is applied",
            detail="1 turns smoothing off. A larger window hides short temperature spikes and makes the "
                   "controller react later."),
        Field(
            key=Config.CV_ERROR_TOLERANCE, kind=FieldKind.INT, default=3, minimum=0,
            summary="Failed temperature reads tolerated per device",
            detail="Inside this budget smfc reuses the last good temperature. Above it smfc stops. 0 turns "
                   "the tolerance off, so the first failure stops the service."),
    ]


IPMI_SECTION: Section = Section(
    name=Config.CS_IPMI,
    summary="How smfc talks to the BMC of the board",
    detail="Every fan controller sends its levels through this interface. The section is mandatory and it "
           "has no enabled= key.",
    mandatory=True, repeatable=False, toggleable=False,
    fields=(
        Field(
            key=Config.CV_IPMI_COMMAND, kind=FieldKind.PATH, default=Config.DV_IPMI_COMMAND,
            summary="Path of the ipmitool command",
            detail="smfc drives the fans through this program. It needs root rights, or the sudo flag of "
                   "smfc-config and smfc-client."),
        Field(
            key=Config.CV_IPMI_FAN_MODE_DELAY, kind=FieldKind.INT, default=Config.DV_IPMI_FAN_MODE_DELAY,
            unit="s", minimum=0,
            summary="Wait after the fan mode is changed",
            detail="A BMC needs time to apply a new fan mode. Raise it if the first level after a mode "
                   "change is ignored."),
        Field(
            key=Config.CV_IPMI_FAN_LEVEL_DELAY, kind=FieldKind.INT, default=Config.DV_IPMI_FAN_LEVEL_DELAY,
            unit="s", minimum=0,
            summary="Wait after a fan level is written",
            detail="A BMC needs time to apply a new level. Raise it if a level read back straight after a "
                   "write returns the old value."),
        Field(
            key=Config.CV_IPMI_REMOTE_PARAMETERS, kind=FieldKind.STR, default=Config.DV_IPMI_REMOTE_PARAMETERS,
            summary="Extra ipmitool arguments for a remote BMC",
            detail="Empty means the local BMC through /dev/ipmi0. A remote board needs the user, the "
                   "password and the host, for example -U ADMIN -P ADMIN -H 10.0.0.5."),
        Field(
            key=Config.CV_IPMI_PLATFORM_NAME, kind=FieldKind.ENUM, default=Config.DV_IPMI_PLATFORM_NAME,
            choices=tuple(p.value for p in PlatformName),
            labels=("read it from the BMC", "Supermicro X10 to X13, H10 to H13", "Supermicro X9",
                    "Supermicro X14 and H14", "Supermicro X10QBi"),
            summary="Supermicro platform smfc drives",
            detail="auto reads the board family from the BMC. Name it explicitly when the board reports a "
                   "product name smfc does not know."),
        Field(
            key=Config.CV_IPMI_ENFORCE_FAN_MODE, kind=FieldKind.BOOL, default=Config.DV_IPMI_ENFORCE_FAN_MODE,
            summary="Take fan control back when the BMC drifts out of it",
            detail="On means smfc re-asserts the mode and every zone level. Off means smfc exits with code "
                   "11 instead, so a service unit can decide what happens."),
        Field(
            key=Config.CV_IPMI_EXIT_LEVEL, kind=FieldKind.INT, default=Config.DV_IPMI_EXIT_LEVEL, unit="%",
            minimum=Config.EXIT_LEVEL_NONE, maximum=100,
            summary="Fan level written to every zone when smfc stops",
            detail="-1 leaves the levels untouched. On an X14 or H14 board this level is only a transition, "
                   "because the BMC takes fan control back and rewrites the levels."),
        Field(
            key=Config.CV_IPMI_IPMITOOL_TIMEOUT, kind=FieldKind.INT, default=Config.DV_IPMI_IPMITOOL_TIMEOUT,
            unit="s", minimum=0,
            summary="Time one ipmitool call may take",
            detail="It stops a wedged /dev/ipmi0 from parking the control loop, and a call that times out "
                   "counts as an IPMI error. 0 waits for ever."),
    ))


CPU_SECTION: Section = Section(
    name=Config.CS_CPU,
    summary="Drives fan zones from the CPU temperature",
    detail="It reads the coretemp or k10temp hwmon files, so one of those kernel modules must be loaded. "
           "CPU temperature moves fast, so its defaults poll often.",
    repeatable=True,
    fields=tuple(_common_fields(
        source="CPU", default_zone=Config.CPU_ZONE, temp_calc=Config.CALC_AVG,
        sensitivity=Config.DV_CPU_SENSITIVITY, polling=Config.DV_CPU_POLLING, steps=Config.DV_CPU_STEPS,
        min_temp=Config.DV_CPU_MIN_TEMP, max_temp=Config.DV_CPU_MAX_TEMP,
        min_level=Config.DV_CPU_MIN_LEVEL, max_level=Config.DV_CPU_MAX_LEVEL)))


HD_SECTION: Section = Section(
    name=Config.CS_HD,
    summary="Drives fan zones from the temperature of SATA and SAS disks",
    detail="It reads the drivetemp hwmon files, or smartctl where that module is missing. Every disk must "
           "be named in /dev/disk/by-id/ form.",
    repeatable=True,
    fields=tuple(_common_fields(
        source="disk", default_zone=Config.HD_ZONE, temp_calc=Config.CALC_AVG,
        sensitivity=Config.DV_HD_SENSITIVITY, polling=Config.DV_HD_POLLING, steps=Config.DV_HD_STEPS,
        min_temp=Config.DV_HD_MIN_TEMP, max_temp=Config.DV_HD_MAX_TEMP,
        min_level=Config.DV_HD_MIN_LEVEL, max_level=Config.DV_HD_MAX_LEVEL) + [
        Field(
            key=Config.CV_HD_NAMES, kind=FieldKind.DEVICE_LIST, default=[], provider="discover_hds",
            summary="Disks this controller reads",
            detail="They are written in /dev/disk/by-id/ form, which survives a reboot. Each instance of the "
                   "family has its own list, so a front cage and a rear cage can differ."),
        Field(
            key=Config.CV_HD_SMARTCTL_PATH, kind=FieldKind.PATH, default=Config.DV_HD_SMARTCTL_PATH,
            summary="Path of the smartctl command",
            detail="It is used where the drivetemp module is missing, and by the standby guard. Reading a "
                   "sleeping disk with smartctl wakes it."),
        Field(
            key=Config.CV_HD_STANDBY_GUARD_ENABLED, kind=FieldKind.BOOL, default=False,
            summary="Send the whole array to standby together",
            detail="For a RAID array of SATA disks. When enough disks have gone to standby on their own, "
                   "smfc puts the rest there too, so the array spins down as one."),
        Field(
            key=Config.CV_HD_STANDBY_HD_LIMIT, kind=FieldKind.INT, default=Config.DV_HD_STANDBY_HD_LIMIT,
            minimum=0,
            summary="Disks in standby before the rest follow",
            detail="It must not exceed the number of disks listed above. It has no effect while the standby "
                   "guard is off."),
    ]))


NVME_SECTION: Section = Section(
    name=Config.CS_NVME,
    summary="Drives fan zones from the temperature of NVMe SSDs",
    detail="It reads the hwmon files of the NVMe driver, so no external command is needed. Every drive must "
           "be named in /dev/disk/by-id/ form.",
    repeatable=True,
    fields=tuple(_common_fields(
        source="NVMe", default_zone=Config.HD_ZONE, temp_calc=Config.CALC_AVG,
        sensitivity=Config.DV_NVME_SENSITIVITY, polling=Config.DV_NVME_POLLING, steps=Config.DV_NVME_STEPS,
        min_temp=Config.DV_NVME_MIN_TEMP, max_temp=Config.DV_NVME_MAX_TEMP,
        min_level=Config.DV_NVME_MIN_LEVEL, max_level=Config.DV_NVME_MAX_LEVEL) + [
        Field(
            key=Config.CV_NVME_NAMES, kind=FieldKind.DEVICE_LIST, default=[],
            provider="discover_nvmes",
            summary="NVMe drives this controller reads",
            detail="They are written in /dev/disk/by-id/ form, which survives a reboot. A SATA disk belongs "
                   "in an HD section instead."),
    ]))


GPU_SECTION: Section = Section(
    name=Config.CS_GPU,
    summary="Drives fan zones from the temperature of Nvidia or AMD GPUs",
    detail="It calls nvidia-smi or rocm-smi, so those calls cost seconds rather than microseconds. The "
           "device IDs are indexes in the output of that command.",
    repeatable=True,
    fields=(
        _enabled_field("GPU"),
        _zone_field(Config.HD_ZONE),
        Field(
            key=Config.CV_GPU_TYPE, kind=FieldKind.ENUM, default=Config.DV_GPU_TYPE,
            choices=("nvidia", "amd"), labels=("Nvidia", "AMD"),
            summary="Which vendor tool reads the temperature",
            detail="nvidia calls nvidia-smi and amd calls rocm-smi. It decides which of the two path keys "
                   "below is used."),
        Field(
            key=Config.CV_GPU_AMD_TEMP_SENSOR, kind=FieldKind.ENUM, default=Config.DV_GPU_AMD_TEMP_SENSOR,
            choices=(0, 1, 2), labels=("junction", "edge", "memory"),
            summary="Which AMD sensor is read",
            detail="Junction is the hottest point of the die and the safest choice. It has no meaning while "
                   "the type above is nvidia."),
    ) + tuple(_common_fields(
        source="GPU", default_zone=Config.HD_ZONE, temp_calc=Config.CALC_AVG,
        sensitivity=Config.DV_GPU_SENSITIVITY, polling=Config.DV_GPU_POLLING, steps=Config.DV_GPU_STEPS,
        min_temp=Config.DV_GPU_MIN_TEMP, max_temp=Config.DV_GPU_MAX_TEMP,
        min_level=Config.DV_GPU_MIN_LEVEL, max_level=Config.DV_GPU_MAX_LEVEL)[2:] + [
        Field(
            key=Config.CV_GPU_IDS, kind=FieldKind.INT_LIST, default=[0], minimum=0,
            provider="discover_gpus",
            summary="GPUs this controller reads",
            detail="They are indexes in the temperature report of the vendor tool, counted from 0. Listing "
                   "them needs the tool, so the popup fills only when you scan."),
        Field(
            key=Config.CV_GPU_NVIDIA_SMI_PATH, kind=FieldKind.PATH, default=Config.DV_GPU_NVIDIA_SMI_PATH,
            summary="Path of the nvidia-smi command",
            detail="It is used while the type above is nvidia. The driver package installs it."),
        Field(
            key=Config.CV_GPU_ROCM_SMI_PATH, kind=FieldKind.PATH, default=Config.DV_GPU_ROCM_SMI_PATH,
            summary="Path of the rocm-smi command",
            detail="It is used while the type above is amd. The ROCm package installs it."),
    ]))


NPU_SECTION: Section = Section(
    name=Config.CS_NPU,
    summary="Drives fan zones from the temperature of Ascend NPU cards",
    detail="It calls npu-smi, which is slow, so its polling interval is longer than the rest. A card with "
           "several chips reports its hottest chip.",
    repeatable=True,
    fields=tuple(_common_fields(
        source="NPU", default_zone=Config.HD_ZONE, temp_calc=Config.CALC_AVG,
        sensitivity=Config.DV_NPU_SENSITIVITY, polling=Config.DV_NPU_POLLING, steps=Config.DV_NPU_STEPS,
        min_temp=Config.DV_NPU_MIN_TEMP, max_temp=Config.DV_NPU_MAX_TEMP,
        min_level=Config.DV_NPU_MIN_LEVEL, max_level=Config.DV_NPU_MAX_LEVEL) + [
        Field(
            key=Config.CV_NPU_IDS, kind=FieldKind.INT_LIST, default=[0], minimum=0,
            provider="discover_npus",
            summary="NPU cards this controller reads",
            detail="They are the card IDs of npu-smi info -m, which need not start at 0. Listing them needs "
                   "the tool, so the popup fills only when you scan."),
        Field(
            key=Config.CV_NPU_SMI_PATH, kind=FieldKind.PATH, default=Config.DV_NPU_SMI_PATH,
            summary="Path or name of the npu-smi command",
            detail="A bare name is looked up on PATH. The Ascend toolkit also installs it under a full path "
                   "of its own."),
        Field(
            key=Config.CV_NPU_SMI_TIMEOUT, kind=FieldKind.FLOAT, default=Config.DV_NPU_SMI_TIMEOUT, unit="s",
            minimum=0.1,
            summary="Time one npu-smi call may take",
            detail="One call needs about 1.5 seconds on a healthy card. Raise it only if the readings time "
                   "out on a loaded machine."),
    ]))


PCI_SECTION: Section = Section(
    name=Config.CS_PCI,
    summary="Drives fan zones from the hwmon temperature of PCI devices",
    detail="Name the cards in exactly one of three ways: by slot address, by vendor and device ID, or by "
           "the driver that serves them.",
    repeatable=True,
    fields=tuple(_common_fields(
        source="PCI device", default_zone=Config.HD_ZONE, temp_calc=Config.CALC_MAX,
        sensitivity=Config.DV_PCI_SENSITIVITY, polling=Config.DV_PCI_POLLING, steps=Config.DV_PCI_STEPS,
        min_temp=Config.DV_PCI_MIN_TEMP, max_temp=Config.DV_PCI_MAX_TEMP,
        min_level=Config.DV_PCI_MIN_LEVEL, max_level=Config.DV_PCI_MAX_LEVEL) + [
        Field(
            key=Config.CV_PCI_ADDRESS, kind=FieldKind.STR_LIST, default=[],
            summary="Slot addresses of the cards",
            detail="For example 0000:05:00.0. Every listed card must be present, and they must all be the "
                   "same model. Use only one of the three addressing keys."),
        Field(
            key=Config.CV_PCI_ID, kind=FieldKind.STR, default="",
            summary="Vendor and device ID of one card model",
            detail="Four hexadecimal digits on each side, for example 1d6a:07b1. It selects every card of "
                   "that model. Use only one of the three addressing keys."),
        Field(
            key=Config.CV_PCI_DRIVER, kind=FieldKind.STR, default="",
            summary="Driver that serves the cards",
            detail="For example atlantic. It selects every PCI device that driver owns. Use only one of the "
                   "three addressing keys."),
        Field(
            key=Config.CV_PCI_TEMP_SENSOR, kind=FieldKind.INT, default=Config.DV_PCI_TEMP_SENSOR, minimum=1,
            summary="Which hwmon sensor of the card is read",
            detail="1 reads temp1_input. A card can expose several sensors; read their labels with "
                   "cat /sys/class/hwmon/hwmon*/temp*_label."),
    ]))


CONST_SECTION: Section = Section(
    name=Config.CS_CONST,
    summary="Holds fan zones at a constant level, with no temperature source",
    detail="Its level is a guaranteed floor for its zones: a zone it drives never drops below it, whatever "
           "the other controllers ask for.",
    repeatable=True,
    fields=(
        _enabled_field("constant"),
        _zone_field(Config.HD_ZONE),
        Field(
            key=Config.CV_POLLING, kind=FieldKind.FLOAT, default=Config.DV_CONST_POLLING, unit="s", minimum=0.0,
            summary="Seconds between two level checks",
            detail="This controller reads no temperature. It only re-applies its level when something else "
                   "has changed it."),
        Field(
            key=Config.CV_CONST_LEVEL, kind=FieldKind.INT, default=Config.DV_CONST_LEVEL, unit="%",
            minimum=1, maximum=100,
            summary="Level held on the zones above",
            detail="It is the only way to drive a zone that has no sensor, for example fans cooling a "
                   "passive backplane."),
    ))


EXPORTER_SECTION: Section = Section(
    name=Config.CS_EXPORTER,
    summary="Serves the readings of smfc over HTTP",
    detail="It answers /snapshot for smfc-client and /metrics in Prometheus format. It changes nothing "
           "about the fans.",
    repeatable=False,
    fields=(
        Field(
            key=Config.CV_EXPORTER_ENABLED, kind=FieldKind.BOOL, default=Config.DV_EXPORTER_ENABLED,
            summary="Serve the readings over HTTP",
            detail="When it is off, smfc-client reads the sensors itself instead of asking the service."),
        Field(
            key=Config.CV_EXPORTER_BIND_ADDRESS, kind=FieldKind.STR,
            default=Config.DV_EXPORTER_BIND_ADDRESS,
            summary="Address the HTTP server listens on",
            detail="127.0.0.1 keeps it on this machine. Use 0.0.0.0 or one LAN address when a remote "
                   "Prometheus has to reach it."),
        Field(
            key=Config.CV_EXPORTER_PORT, kind=FieldKind.INT, default=Config.DV_EXPORTER_PORT,
            minimum=1, maximum=65535,
            summary="TCP port the HTTP server listens on",
            detail="Changing it breaks every scraper configured for the old port."),
    ))


# Every section of the configuration file, in the order smfc-config lists them.
SECTIONS: Dict[str, Section] = {
    s.name: s for s in (IPMI_SECTION, CPU_SECTION, HD_SECTION, NVME_SECTION, GPU_SECTION, NPU_SECTION,
                        PCI_SECTION, CONST_SECTION, EXPORTER_SECTION)
}


def family_of(section_name: str) -> str:
    """Return the family name of a section name.
    Args:
        section_name (str): section name, with or without an instance number (e.g. "CPU" or "CPU:1")
    Returns:
        str: the family name (e.g. "CPU")
    """
    return section_name.split(":", 1)[0]


def section_of(section_name: str) -> Optional[Section]:
    """Look up the metadata of a section name.
    Args:
        section_name (str): section name, with or without an instance number (e.g. "CPU" or "CPU:1")
    Returns:
        Optional[Section]: the section metadata, or None for a name smfc does not know
    """
    return SECTIONS.get(family_of(section_name))


def field_of(section_name: str, key: str) -> Optional[Field]:
    """Look up the metadata of one parameter.
    Args:
        section_name (str): section name, with or without an instance number
        key (str): parameter name
    Returns:
        Optional[Field]: the field metadata, or None for a section or a key smfc does not know
    """
    section = section_of(section_name)
    return section.field(key) if section else None


# End.
