#
#   pcifc.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.PciFc() class implementation.
#
from typing import List
from pyudev import Context, Device, Devices, DeviceNotFoundByNameError
from smfc.fancontroller import FanController
from smfc.ipmi import Ipmi
from smfc.log import Log
from smfc.config import PciConfig


class PciFc(FanController):
    """Class for generic PCI device fan controller.

    Temperatures are read from the HWMON files of PCI devices that have no fan controller of their own
    (e.g. a 10 Gbit network card). The cards are named with one of three parameters - `pci_address=`,
    `pci_id=` or `pci_driver=` - and their HWMON devices are discovered through the udev database.

    One section covers one kind of PCI device, because the section has a single temperature window and a
    single `temp_sensor=` index. A mixed section would compare temperatures with different safe ranges.
    """

    config: PciConfig

    # PciFc specific parameters.
    pci_devices: List[str]  # PCI slot addresses of the resolved cards, sorted

    def __init__(self, log: Log, udevc: Context, ipmi: Ipmi, cfg: PciConfig) -> None:
        """Initialize the PCI fan controller class and raise exception in case of invalid configuration.

        Args:
            log (Log): reference to a Log class instance
            udevc (Context): reference to an udev database connection (instance of Context from pyudev)
            ipmi (Ipmi): reference to an Ipmi class instance
            cfg (PciConfig): PCI fan controller configuration

        Raises:
            RuntimeError: no PCI device found, the resolved cards are different models, a card has no HWMON
                          device, or a HWMON device has no temperature file with the configured index
        """
        # Store config reference first (required by base class)
        self.config = cfg

        # Resolve the PCI devices and sort them by slot address, so the device order is stable across
        # reboots and device_names()[i] keeps naming the same card.
        devices = self._resolve_devices(udevc, cfg)
        devices.sort(key=lambda d: d.properties["PCI_SLOT_NAME"])
        # Only pci_address= can name different kinds of hardware: pci_id= is one model by definition and a
        # PCI driver binds to one device class. The models a driver serves may still differ (e.g. the `nvme`
        # driver serves every NVMe drive of the machine), and that is intended.
        if cfg.pci_address:
            self._validate_same_model(devices, cfg.section)
        self.pci_devices = [d.properties["PCI_SLOT_NAME"] for d in devices]

        # Collect the HWMON temperature files. One card can carry several HWMON devices (e.g. a SATA
        # controller carries one per disk), so the controlled entity is the HWMON device, not the card.
        self.hwmon_path = []
        self.device_labels: List[str] = []
        for device in devices:
            paths = self.get_hwmon_paths(udevc, device, cfg.temp_sensor)
            if not paths:
                raise RuntimeError(f"[{cfg.section}] '{device.properties['PCI_SLOT_NAME']}' has no HWMON device")
            self.hwmon_path.extend(paths)
            self.device_labels.extend(self._device_labels(device, paths))

        # Initialize FanController class.
        super().__init__(log, ipmi, cfg.section, len(self.hwmon_path))

        # Print configuration in CONFIG log level (or higher).
        if self.log.log_level >= Log.LOG_CONFIG:
            if cfg.pci_address:
                self.log.msg(Log.LOG_CONFIG, f"   pci_address = {cfg.pci_address}")
            if cfg.pci_id:
                self.log.msg(Log.LOG_CONFIG, f"   pci_id = {cfg.pci_id}")
            if cfg.pci_driver:
                self.log.msg(Log.LOG_CONFIG, f"   pci_driver = {cfg.pci_driver}")
            self.log.msg(Log.LOG_CONFIG, f"   temp_sensor = {cfg.temp_sensor}")
            self.log.msg(Log.LOG_CONFIG, f"   pci devices = {self.pci_devices}")

    @staticmethod
    def _resolve_devices(udevc: Context, cfg: PciConfig) -> List[Device]:
        """Resolve the PCI devices of the section with the addressing parameter it specifies. Config has
        already validated that exactly one of the three parameters is present.

        Args:
            udevc (Context): pyudev Context
            cfg (PciConfig): PCI fan controller configuration

        Returns:
            List[Device]: the resolved PCI devices (unsorted)

        Raises:
            RuntimeError: an address names a card that is not present, or no card matches at all
        """
        devices: List[Device] = []
        if cfg.pci_address:
            for address in cfg.pci_address:
                try:
                    devices.append(Devices.from_name(udevc, "pci", address))
                except DeviceNotFoundByNameError as e:
                    raise RuntimeError(f"[{cfg.section}] PCI device '{address}' cannot be found") from e
        elif cfg.pci_id:
            # udev stores PCI_ID in upper case, the configuration file usually holds it in lower case.
            wanted = cfg.pci_id.upper()
            devices = [d for d in udevc.list_devices(subsystem="pci") if d.properties.get("PCI_ID") == wanted]
            if not devices:
                raise RuntimeError(f"[{cfg.section}] no PCI device found with pci_id={cfg.pci_id}")
        else:
            devices = list(udevc.list_devices(subsystem="pci", DRIVER=cfg.pci_driver))
            if not devices:
                raise RuntimeError(f"[{cfg.section}] no PCI device found with pci_driver={cfg.pci_driver}")
        return devices

    @staticmethod
    def _validate_same_model(devices: List[Device], section: str) -> None:
        """Validate that all resolved cards are the same model. This check runs for the `pci_address=` form
        only, because that is the one the user fills in card by card. A mixed section would feed
        temperatures with different safe ranges into one temperature window.

        Args:
            devices (List[Device]): the resolved PCI devices
            section (str): section name for the error message

        Raises:
            RuntimeError: the resolved cards are different models
        """
        ids = {d.properties.get("PCI_ID", "") for d in devices}
        if len(ids) > 1:
            raise RuntimeError(f"[{section}] pci_address= lists different PCI devices: {sorted(ids)}")

    @staticmethod
    def _device_labels(device: Device, paths: List[str]) -> List[str]:
        """Build a unique label for every HWMON temperature file of one card. The PCI slot address alone is
        not unique when a card carries several HWMON devices (e.g. a SATA controller with several disks), so
        the HWMON device name is appended there.

        Args:
            device (Device): the PCI device
            paths (List[str]): temperature file paths of the card

        Returns:
            List[str]: one label per path
        """
        address = device.properties["PCI_SLOT_NAME"]
        if len(paths) == 1:
            return [address]
        # os.path.dirname() of '/sys/.../hwmon/hwmon4/temp1_input' is the HWMON device path.
        return [f"{address}/{path.rsplit('/', 2)[-2]}" for path in paths]

    def device_names(self) -> List[str]:
        """Return per-device labels (PCI slot address, plus the HWMON device name when a card has several)
        matching last_per_device_temps positionally."""
        return list(self.device_labels)


# End.
