# PCI fan controller — implementation plan

> Status: **proposal, for review**. Nothing is implemented yet.
> For the internal structure this plan extends, see
> [ARCHITECTURE.md](https://github.com/petersulyok/smfc/blob/main/ARCHITECTURE.md).

---

## 1. Goal

Add a seventh fan controller, `PCI`, that reads the temperature of a PCI device
through its HWMON files. It covers PCI hardware that has no dedicated fan
controller today — the first target is a 10 Gbit network card.

The controller discovers its HWMON paths with `pyudev`. The user names the
device, not the sensor file.

### 1.1 What already exists

`FanController.get_hwmon_path()` does most of the search:

```python
[hwmon_device] = udevc.list_devices(subsystem="hwmon", parent=parent_dev)
```

The `parent=` filter is recursive. It finds a HWMON node that is a direct child
of the PCI device, and one that sits deeper. Both cases occur:

```
0000:05:00.0 (NIC)  -> /sys/.../0000:05:00.0/hwmon/hwmon2          direct child
0000:02:00.0 (NVMe) -> /sys/.../0000:02:00.0/nvme/nvme1/hwmon0     two levels down
```

Two limits of that helper must be lifted:

- It unpacks a single HWMON node. Two or more nodes return an empty string.
- It always appends `temp1_input`.

### 1.2 Out of scope

`NvmeFc` and `HdFc` stay as they are. `HdFc` cannot use a driver name at all:
every SATA, SAS and USB disk shares the `sd` driver, so only
`/dev/disk/by-id/...` names one disk.

---

## 2. Configuration

### 2.1 Section names

`[PCI]`, `[PCI:0]`, `[PCI:1]` … — the three naming styles of README chapter 1.4,
collected by `Config._get_sections()`.

### 2.2 New parameters

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `pci_address` | list of PCI slot addresses | — | e.g. `0000:05:00.0, 0000:06:00.0` |
| `pci_id` | one `vendor:device` | — | e.g. `1d6a:07b1` |
| `pci_driver` | one driver name | — | e.g. `atlantic` |
| `temp_sensor` | int | `1` | which sensor inside one HWMON node |

### 2.2.1 Complete parameter list and defaults

| Parameter | Type | Default | Constant |
|---|---|---|---|
| `enabled` | bool | `0` | — |
| `ipmi_zone` | list of int | `1` | `HD_ZONE` |
| `pci_address` | list of addresses | — | `CV_PCI_ADDRESS` |
| `pci_id` | `vendor:device` | — | `CV_PCI_ID` |
| `pci_driver` | string | — | `CV_PCI_DRIVER` |
| `temp_sensor` | int | `1` | `DV_PCI_TEMP_SENSOR` |
| `temp_calc` | int | `2` (maximum) | `CALC_MAX` |
| `steps` | int | `6` | `DV_PCI_STEPS` |
| `sensitivity` | float | `2.0` | `DV_PCI_SENSITIVITY` |
| `polling` | float | `2.0` | `DV_PCI_POLLING` |
| `min_temp` | float | `30.0` | `DV_PCI_MIN_TEMP` |
| `max_temp` | float | `60.0` | `DV_PCI_MAX_TEMP` |
| `min_level` | int | `35` | `DV_PCI_MIN_LEVEL` |
| `max_level` | int | `100` | `DV_PCI_MAX_LEVEL` |
| `smoothing` | int | `1` | `DV_PCI_SMOOTHING` |
| `error_tolerance` | int | `3` | `DV_PCI_ERROR_TOLERANCE` |
| `control_function` | list of pairs | empty | — |

`pci_address`, `pci_id` and `pci_driver` have no default. Exactly one of them
must be present (chapter 2.3).

Two defaults differ from every existing family, and both are deliberate:

- `temp_calc = 2` (maximum). A PCI section can hold several cards, and the
  hottest card should drive the fans. The other families default to average.
- The temperature window `30.0 .. 60.0` with `steps = 6` is neutral. The PCI
  class varies too much for a tuned default, so the user narrows it per card.

The rest match the shared values of the existing families.

### 2.3 Addressing rules

**Exactly one of `pci_address`, `pci_id`, `pci_driver` per section.** Zero
raises an error. Two raise an error.

Each form has a different reach:

| Form | Matches | Absent device |
|---|---|---|
| `pci_address` | exactly the listed slots | `DeviceNotFoundByNameError` |
| `pci_id` | every card of that model | empty list |
| `pci_driver` | every card that driver serves | empty list |

`pci_address` takes a list, because several slots can hold identical cards.
`pci_id` and `pci_driver` take one value each. A list there would mean several
kinds of hardware in one section.

`pci_driver` is the wildcard form. A new card of the same kind joins the
section with no config change. That growth is intended. The user sees the new
device in the `CONFIG` log line and in `smfc-client`. Resolution happens once in
`PciFc.__init__`, so a hot-plugged card joins at the next restart.

### 2.4 One kind per section

A section covers **one kind of PCI device**. The section assumes one thermal
profile and one cooling need.

Mixing kinds breaks two things. `temp_calc` would reduce temperatures with
different safe ranges. And `temp_sensor` would mean different things per
device:

```
NIC   temp2_label = MAC Temperature
NVMe  temp2_label = Sensor 1
```

Only `pci_address` can produce a mixed section. The user picks each slot freely
there, so nothing stops `0000:05:00.0, 0000:02:00.0` — a NIC plus an NVMe drive.

The other two forms cannot mix kinds:

| Parameter | Can it mix kinds? | Why |
|---|---|---|
| `pci_address` | **yes** | The user picks each slot freely. |
| `pci_id` | no | One ID is one model, so one kind. |
| `pci_driver` | no in practice | A driver binds to one PCI class. |

So the rule is enforced on `pci_address` only. All listed addresses must resolve
to the same `vendor:device` ID:

```python
ids = {d.properties["PCI_ID"] for d in devs}
if len(ids) > 1:
    raise ValueError(f"[{section}] pci_address= lists different devices: {sorted(ids)}")
```

One model is the strictest reading of "one kind", and it needs no PCI class
code. Two identical cards in two slots still pass, which is the intended use of
the list form.

The one case this blocks: two NVMe drives of different brands cannot share a
`pci_address` list. Those belong in `[NVME]` with by-id names, which is the
better answer for them anyway.

### 2.5 Sensor selection

`temp_sensor` is an integer index. It names one sensor inside one HWMON node:
`1` reads `temp1_input`, `2` reads `temp2_input`, and so on.

Default is `1`, which keeps the behaviour of `get_hwmon_path()` today.

Label matching was considered and rejected. The `drivetemp` driver writes no
`_label` file, so an index is needed anyway, and two forms in one parameter
would only add a parsing rule.

`max` is **not** a valid value. `max` is a calculation, and `temp_calc` already
carries that meaning. One word, one meaning.

One HWMON node stays one device, whatever number of sensors it holds. A card
with two sensors is therefore fully covered: the user names the hotter one. On
the AQC107 that is `MAC Temperature`, about 0.7 °C above `PHY Temperature`.

`Config` rejects a value below 1 with a `ValueError`. `PciFc` raises a
`RuntimeError` when the resolved device has no such file:

```
[PCI] '0000:04:00.0' has no temp3_input file
```

Never fall back in silence. A silent fallback would control the fans from the
wrong sensor.

### 2.6 Example

```ini
[PCI]
enabled     = 1
ipmi_zone   = 1            ; the default
pci_driver  = atlantic
temp_sensor = 2            ; MAC Temperature, the hotter of the two
temp_calc   = 2            ; the default: maximum across cards
min_temp    = 55.0         ; narrowed from the 30.0 default for a 10G NIC
max_temp    = 80.0         ; narrowed from the 60.0 default
min_level   = 35
max_level   = 100
```

---

## 3. Device discovery

### 3.1 Resolve the PCI devices

```python
if cfg.pci_address:
    devs = [Devices.from_name(udevc, "pci", a) for a in cfg.pci_address]
elif cfg.pci_id:
    want = cfg.pci_id.upper()          # udev stores PCI_ID in upper case
    devs = [d for d in udevc.list_devices(subsystem="pci")
            if d.properties.get("PCI_ID") == want]
else:
    devs = list(udevc.list_devices(subsystem="pci", DRIVER=cfg.pci_driver))
devs.sort(key=lambda d: d.properties["PCI_SLOT_NAME"])
```

Sort by `PCI_SLOT_NAME`. The device order is then stable across reboots, so
`device_names()[i]` keeps naming the same card.

De-duplicate the `pci_address` list. A repeated address would get double
weight under `temp_calc = 1` (average).

### 3.2 Expand to HWMON nodes

Each PCI device can carry several HWMON nodes. Verified on real hardware:

```
DRIVER=atlantic  1 PCI device   0000:05:00.0  1 hwmon   temp1, temp2
DRIVER=nvme      2 PCI devices  0000:02:00.0  1 hwmon   temp1, temp2, temp3
                                0000:04:00.0  1 hwmon   temp1
DRIVER=ahci      1 PCI device   0000:00:17.0  3 hwmon   (three SATA disks)
DRIVER=i915      0 PCI devices
```

So the rule is:

> **The device count is the number of HWMON nodes, not the number of PCI cards.**

That rule handles all four cases with no special branch. `count` becomes the
length of `hwmon_path`, exactly as in `NvmeFc`.

### 3.3 Device labels

`device_names()` must return unique strings, because the metric
`smfc_device_temperature_celsius` carries a `device` label.

Use the PCI address, plus the HWMON name when one card has several nodes:

```
pci0000:05:00.0/enp5s0
pci0000:00:17.0/drivetemp/hwmon4
```

Do not put a bare `hwmonN` number in a config file. The numbers are assigned at
boot and can change. They are safe in a label only.

### 3.4 Failures

The exception type follows **where** the error is found, not what it is about:

> `Config` raises `ValueError`. `PciFc` raises `RuntimeError`.

That matches the layering of ARCHITECTURE chapter 4: range checks in `Config`,
existence and reachability checks in the controller constructor.

`Config._parse_pci_sections()` — `ValueError`, no hardware needed:

| Case |
|---|
| Zero, two or three of `pci_address` / `pci_id` / `pci_driver` |
| A malformed address string |
| A malformed `pci_id` |
| `temp_sensor` below 1 |
| The common checks of `_validate_fan_controller_config()` |

`PciFc.__init__()` — `RuntimeError`, the hardware decides:

| Case | Message names |
|---|---|
| An address names an absent card | the address |
| A wildcard matches nothing | the parameter |
| Listed addresses resolve to different models | the IDs |
| A resolved card has no HWMON node | the card |
| A HWMON node has no `tempN_input` file at all | the node |
| The requested `temp_sensor` index is missing | the card |

"Different models" is a configuration mistake, but it is only detectable with
the hardware present. It stays `RuntimeError`, so the rule stays one sentence.

`pyudev` raises `DeviceNotFoundByNameError` for an absent address. `PciFc` must
catch it and re-raise it as `RuntimeError`.

All of them fail at startup, before the main loop. A section with no device
would leave a fan zone uncontrolled.

Two observations on the existing code, neither of them blocking:

- `CpuFc` raises `RuntimeError` for a missing HWMON device, while `NvmeFc`
  raises `ValueError` for the same case. The two are inconsistent today. The
  rule above follows `CpuFc`.
- The controller construction loop in `service.py` has no `try/except` around
  it. Both exception types therefore end in an uncaught traceback, with only
  the `atexit` handler restoring the fans. `client.py` catches both with a broad
  `except Exception`. So the choice of type changes nothing today.

Note the Wi-Fi trap: some network cards report their temperature through the
`thermal` subsystem instead, outside the PCI tree. Example from a real machine:
`/sys/devices/virtual/thermal/thermal_zone1/hwmon8`, named `iwlwifi_1`. A PCI
parent search never finds it. The error message must be clear.

---

## 4. IPMI zone rules

The PCI family follows the same two rules as every other family. Both were
confirmed by running the parser.

**Different controller types may share a zone.** `Service._check_shared_zones()`
keys on the zone alone. The arbiter applies the highest level per zone.

**Two enabled sections of the same type must use different zones.**
`Config._validate_no_duplicate_zones()` raises otherwise. Disabled sections are
skipped.

So `_validate_no_duplicate_zones(self.pci)` is called like the other five. No
exception is made for `PCI`, even though `PCI` is a bus and not one device kind.

### 4.1 Consequence: one kind per zone

The PCI family covers **one hardware class per IPMI zone**, not one in total.
Several `[PCI:n]` sections are allowed while their zones differ.

Different classes are not required. Two PCI sections may cover the same class,
split by slot address, one per zone — the use case ARCHITECTURE chapter 9.4
gives for `[HD]` + `[HD:1]`:

```ini
[PCI]                          ; front NIC -> zone 1
pci_address = 0000:05:00.0
ipmi_zone     = 1
max_temp      = 75

[PCI:1]                        ; rear NIC, less airflow -> zone 2
pci_address = 0000:06:00.0
ipmi_zone     = 2
max_temp      = 70
```

### 4.2 The limit to document

A NIC and an NVMe drive in the same zone cannot both be `[PCI]` sections. The
user puts the drives in `[NVME]` instead. That is a different family, so the
arbiter applies and the highest level wins.

```ini
[PCI]                    ; NIC -> zone 1
pci_driver = atlantic
ipmi_zone  = 1

[NVME]                   ; drives -> zone 1
nvme_names = /dev/disk/by-id/nvme-...
ipmi_zone  = 1
```

Two classes that both need `[PCI]` — a NIC and a RAID controller in zone 1 —
have no solution. On a typical two-zone board zone 0 belongs to `[CPU]`, so one
PCI class fits in practice. Boards with more zones fit one class per free zone.
This limit belongs in README chapter 1.2.

---

## 5. Files to change

| File | Change |
|---|---|
| `src/smfc/config.py` | `PciConfig` dataclass, `CS_PCI`, `CV_PCI_*`, `DV_PCI_*`, `_parse_pci_sections()`, one `_validate_no_duplicate_zones()` call |
| `src/smfc/pcifc.py` | new `PciFc(FanController)` |
| `src/smfc/fancontroller.py` | new `get_hwmon_paths()` returning a list and honouring `temp_sensor`; `get_hwmon_path()` stays untouched |
| `src/smfc/__init__.py` | re-export `PciConfig` and `PciFc` |
| `src/smfc/service.py` | construction loop, the zone set in the DEBUG block, `check_dependencies()` |
| `src/smfc/snapshot.py` | `"pci"` type label |
| `src/smfc/client.py` | offline controller construction, type label, report |
| `config/smfc.conf` | the `[PCI]` section with commented defaults |
| `config/samples/` | one new sample, or an extension of an existing one |
| `README.md` | chapter 1.2 table, chapter 10 parameter list, the zone limit |
| `ARCHITECTURE.md` | chapters 2, 3, 4, 12 (`×6` becomes `×7`) |
| `CHANGELOG.md` | the new feature entry |
| `debian/changelog`, `smfc.spec` | the release note |

`PciFc` subclasses `FanController`. Only `ConstFc` sits outside that tree, and
only because it has no temperature source.

Range checks belong in `Config`. The `pyudev` resolution belongs in
`PciFc.__init__`, exactly as `NvmeFc` does it.

`check_dependencies()` needs no new kernel module check. The HWMON files come
from the device driver itself, which is already loaded if the card is present.

---

## 6. Test plan

Per TESTING.md, a new `FanController` subclass gets a new `test_pcifc.py` that
reuses `test_fc_helpers.py` for the base contract.

| Test module | New cases |
|---|---|
| `test_pcifc.py` | address / id / driver resolution, multi-node expansion, `temp_sensor` index and label, label uniqueness, every failure in §3.4 |
| `test_config.py` | `[PCI]` parsing, the "exactly one of three" rule, duplicate zones, class-mix rejection |
| `test_service.py` | construction loop, PCI in shared-zone arbitration |
| `test_snapshot.py` | the `pci` entry |
| `test_client.py` | offline path with a PCI section |
| `test_mocks.py` | udev mocks for a multi-node PCI device |

The smoke matrix in TESTING.md needs one scenario with a `[PCI]` section.

---

## 7. Open questions

None. Every design question raised during review is decided and written above.

Target release: **6.4.0**. The packaging changelogs (`CHANGELOG.md`,
`debian/changelog`, `smfc.spec`) are written at release time, not with the
implementation.

---

## 8. Verified facts behind this plan

The examples above were read from a live Debian workstation with an Aquantia
AQC107 10G card:

```
hwmon nodes total                : 9
hwmon nodes with a PCI ancestor  : 6
tempN_input files under PCI      : 9

hwmon0  nvme       0000:02:00.0  below nvme  3 sensors
hwmon1  nvme       0000:04:00.0  below nvme  1 sensor
hwmon2  enp5s0     0000:05:00.0  direct      2 sensors  (PHY, MAC)
hwmon4  drivetemp  0000:00:17.0  below scsi  1 sensor
hwmon5  drivetemp  0000:00:17.0  below scsi  1 sensor
hwmon6  drivetemp  0000:00:17.0  below scsi  1 sensor
```

Not reachable through a PCI parent: `coretemp`, `nct6798`, and `iwlwifi_1`.
