# smfc-config: design and implementation plan

## 1. Purpose

`smfc-config` is a text-mode program. It creates and edits `/etc/smfc/smfc.conf`.

Its first job is to help a user finish their **first** configuration file. Its second job is to edit an
existing file safely. It edits the local file only. It never configures a remote host.

Three problems it solves:

- A new user faces 9 section types and about 99 keys. They do not know which five matter.
- A user cannot tell whether `ipmitool`, `smartctl` or a listed disk is really reachable.
- Device names must be written in `/dev/disk/by-id/...` form. Nobody types those by hand.

## 2. Decisions

These are settled.

| # | Decision | Reason |
|---|---|---|
| 1 | Use `curses` from the standard library | zero PyPI packages; no `Depends:` line on Debian, Fedora or Arch |
| 2 | One Python distribution | the release pipeline builds exactly two artifacts; a third touches four workflows |
| 3 | One binary package | no separate `smfc-config` deb or rpm |
| 4 | A third entry point, `smfc-config` | beside `smfc` and `smfc-client` |
| 5 | Keep the name `smfc-config` | matches the `smfc-<role>` pattern; free on PyPI |
| 6 | One master-detail screen | section list on the left, fields on the right; no screen stack |
| 7 | `[Ipmi]` shows a blank enabled glyph | it has no `enabled` key and is always active |
| 8 | Hardware checks run on a key press only | a fresh file must not open as a wall of red |
| 9 | A multi-select popup serves every list-valued key | `hd_names`, `nvme_names`, `gpu_device_ids`, `npu_device_ids` |
| 10 | Reuse the installer device filters | they returned the correct answer on both test machines |

### 2.1 Decisions taken in this plan, open to change

These six were never settled in discussion. I state my choice and the reason. Overturn any of them.

| # | Choice | Reason |
|---|---|---|
| A | **Save by surgical line edit.** Change only the text after `=` on the matching line. | `config/smfc.conf` is mostly comments, and the live file on `nas` carries them too. `ConfigParser.write()` deletes every comment. |
| B | **Edit numbers, booleans and enums in place. Use a popup for text, paths, lists and `control_function`.** | The value cell holds about 21 columns. Four kinds of real value are longer, up to 51. See 5.4. |
| C | **Write a section header plus only the keys the user sets.** A missing section means disabled. | Verified with the parser: a 3-key `[PCI]` section fills every other key from its default. No template text is needed at run time. |
| D | **Offer a service restart after save, only when the process can do it. Never restart alone.** | The tool must stay safe to run on a live server. Without privileges it prints the command instead. |
| E | **Fix `_1+$` to `_[0-9]+$`.** | **Done.** udev numbers duplicates `_1`, `_2`, `_3`; the old pattern matched `_1` and `_11`, never `_2`. |
| F | **Lift the filters into `src/smfc/discover.py`.** The shell scripts call it. | **Done.** The regex existed in three copies, and the `^usb-` fix had to be made three times. |
| G | **A missing config file is an error, not a start state.** Offer to download the template from the release tag; name the local backups when that fails. | Every install path leaves `/etc/smfc/smfc.conf` in place, and `install.sh` backs the old one up. |
| H | **Run as any user. Never require root, never re-exec under `sudo`.** | The config file is `0644`, so reading works for anyone. Writing, restarting and the hardware checks need privileges, and each says so on its own. |

Minimum terminal size: 64 columns and 14 rows. Eight rows are fixed — 2 frame lines, 1 divider, the
4-line help pane and the key line — which leaves 6 section rows, and the list scrolls. 16 rows is
comfortable, and 19 shows the whole list without scrolling. Below the floor, fall back to a single
pane. Never refuse to start.

## 3. What the real config files require

Every item below was observed on a live system, not assumed. Each one breaks a naive editor.

**The section list is dynamic.** Each family is scanned as the base section plus numbered variants,
`[CPU:0]`, `[CPU:1]` and so on. See `Config._get_sections()` in `src/smfc/config.py:418`.
`config/samples/smfc-sample8.conf` uses that form. The left pane is not nine fixed rows.

**A missing section means disabled, and every key has a default.** `config/samples/smfc-sample1.conf`
holds only `[Ipmi]` and `[CPU]`; the parser returns an empty list for every other family and no
error. A three-key `[PCI]` section parses and fills `steps`, `sensitivity`, `min_temp`, `max_temp`,
`min_level`, `max_level` and `temp_sensor` from the defaults. So the editor never needs template
text: it writes the header plus the keys the user sets.

**A file can miss a section.** The live config on `nas` holds 8 sections and no `[PCI]`. It predates
that feature. The left pane still shows `PCI`, as disabled, so an upgrading user can reach a new
feature through the tool. See 5.1.

**The config file is always there after an installation.** `install.sh` copies the template and
saves the old file as `smfc.conf.<tag>`. On DEB it is a conffile and on RPM `%config(noreplace)`, so
an upgrade never replaces an edited file. A fresh install leaves all 9 sections, `[CPU]` and `[HD]`
enabled, and the disks already listed. So the editor always opens an existing file with sensible
defaults. There is no empty-file start to design for.

**`control_function` disables four fields.** When the key carries a value, `min_temp`, `max_temp`,
`min_level` and `max_level` are ignored and never validated. On `nas`, `[CPU]` carries both. The
right pane needs a fourth field state: inactive, greyed, with the reason on the footer line.

**Sharing an IPMI zone is normal.** On `nas`, `CPU` and `NVME` both drive zone 0, both enabled, in
production. `Config._validate_no_duplicate_zones()` at `src/smfc/config.py:965` forbids only the
wrong case: two enabled instances of one family on one zone. The editor writes no zone check of its
own.

**A disabled section holds stale values.** On `nas`, `[GPU]` and `[NPU]` are off and still carry
device IDs. A disabled section is shown and never checked.

**The device list format has a trap.** `Config.parse_device_names()` at `src/smfc/config.py:470`
splits on newlines. The first device must sit on the `hd_names=` line. The other form yields an
empty first element. The trailing `\n\t` after the last entry is harmless; `configparser` strips it.

**The exporter port is held by smfc itself.** On `nas`, `bind_address=0.0.0.0` and `port=9099`, and
`vmagent` scrapes `192.168.0.50:9099` every 30 seconds. A plain bind test reports that working setup
as broken. The check must compare the owning process. `0.0.0.0` is correct there, not a risk.

**IPv6 is disabled on `nas`.** The `bind_address` check must not require an IPv6 address or route.

**The config file needs root.** `smfc-config` must test write permission at start, not at save time.

## 4. Module layout

Three modules are shared by the daemon and the editor. Only the screens belong to the editor.

Two modules have two consumers each, so they stay flat beside the daemon:

| Module | Consumers | Path |
|---|---|---|
| `checks.py` — per-section checks | `service.py` at startup, and the editor | `src/smfc/checks.py` |
| `discover.py` — the by-id filters | `install.sh`, both package scripts, the editor | `src/smfc/discover.py` |

Everything the editor alone uses lives in one subpackage:

```
src/smfc/config_editor/
├── __init__.py
├── schema.py        field metadata, section help, provider names
├── confwriter.py    the comment-preserving writer
├── cmd.py           the smfc-config entry point
├── app.py           main loop and key dispatch
├── panes.py         section list, field list, help pane
└── popups.py        device selector, wide input field
```

Six modules justify a package; the plan's own threshold was four. The name carries the word of the
command, `smfc-config`, without colliding with `config.py`.

**The dependency direction is one way.** `config_editor` imports `config`, `checks` and `discover`.
None of them may import `config_editor`. `src/smfc/__init__.py` imports the whole daemon, so an
import in the other direction would be circular and would fail at start. A grep for `config_editor`
in `src/smfc/__init__.py` must find nothing.

**Packaging trap.** `[tool.setuptools] packages = ["smfc"]` in `pyproject.toml` is an explicit list.
It does not recurse. A subpackage must be added by hand:

```toml
[tool.setuptools]
packages = ["smfc", "smfc.config_editor"]
package-dir = {"" = "src"}
```

This passes every local test and fails only in the built wheel. Verify the artifact:

```bash
uv build && python3 -m zipfile -l dist/smfc-*.whl | grep config_editor
```

`pyproject.toml` gains one line in `[project.scripts]`:

```toml
smfc-config = "smfc.config_editor.cmd:main"
```

No optional dependency. No extras. No second binary package.

## 5. The screen

```
 ┌ Sections ──────────┬ [CPU] ───────────────────────────────┐
 │   Ipmi             │ enabled        yes                   │
 │ > CPU        ✓     │ ipmi_zone      0                     │
 │   HD         ✓     │ temp_calc      1                     │
 │   NVME       ✗     │ sensitivity    3.0                   │
 │   PCI        ✗     │ polling        2                     │
 │   ───────────────  │ steps          6                     │
 │   Overview   !     │ min_temp      [40.0_____]            │
 │                    │ max_temp       60.0                  │
 ├────────────────────┴──────────────────────────────────────┤
 │ min_temp   Lowest temperature of the fan curve            │
 │ Below this temperature the fan stays at min_level. Raise  │
 │ it if the fans spin up too early. Keep it below max_temp. │
 │ ! 40.0 is not below max_temp 60.0 of this section         │
 └───────────────────────────────────────────────────────────┘
  Tab pane   Enter edit   F5 test hardware   F2 save   F10 quit
```

Two glyph columns. The first is the enabled state. The second is the check state.

| Glyph | Column | Meaning |
|---|---|---|
| blank | enabled | `[Ipmi]`, always active, no toggle |
| `✓` / `✗` | enabled | family enabled or disabled |
| `-` | check | not checked yet |
| `!` | check | warning |
| `X` | check | error |

A disabled family gets no check glyph. It never gets a green one.

The `Overview` row holds the checks that belong to no section.

### 5.1 The left pane renders the schema, not the file

The pane always lists the same 9 families. The file supplies their state, not the list.

The reason is in the parser. A missing section and `enabled=0` mean the same thing to smfc:
`smfc-sample1.conf` holds only `[Ipmi]` and `[CPU]`, and every other family reads back as an empty
list with no error. A difference the daemon cannot see must not be shown to the user.

So an absent `[PCI]` shows as `✗`, exactly like a disabled one. There is no `+` glyph and no "add
section" action.

| Action | What is written |
|---|---|
| switch a family on | the section header, `enabled=1`, and the keys the user sets; every other key runs on its default |
| switch a family off | `enabled=0`; the section and the user's values stay |

Switching off never deletes a section. A user who turns `[HD]` off for a week must find their disk
list intact.

**The rows are instances, not families.** A family can hold several instances, and each one is a
complete, independent fan controller with its own full parameter set. They share only the
temperature source. `[CPU]` is itself an instance, so there is no parent row above the numbered
ones.

| The file holds | The pane shows |
|---|---|
| `[CPU]` | one row, `CPU` |
| `[CPU]` and `[CPU:1]` | two rows, `CPU` and `CPU:1` |
| `[CPU:0]` and `[CPU:1]` | two rows, `CPU:0` and `CPU:1` |
| no CPU section at all | one row, `CPU`, disabled — the schema placeholder |

All three naming styles are valid and may be mixed. The suffix number is used only for ordering and
logging; it has no relationship to the `ipmi_zone=` value.

**A new instance can be added at any time. The only rule is a different zone.** Two *enabled*
instances of one family must not share an IPMI zone. `Config._validate_no_duplicate_zones()` enforces
exactly that, and it skips disabled instances, so a disabled one claims no zone.

| The add action | Behaviour |
|---|---|
| when it is offered | on any family row, at any time |
| the zone it proposes | the lowest zone not claimed by an enabled instance of that family |
| the number it writes | the next free suffix; `[CPU]` plus `[CPU:1]` is valid, `[CPU:0]` need not exist |
| the values it writes | the defaults, not a copy |

Defaults rather than a copy, because 9.4 of `ARCHITECTURE.md` states the case plainly: two instances
with the same parameters and different zones are pointless. The value is in tuning them apart. A
copy invites a user to leave two identical curves behind.

For `[HD]` and `[NVME]` the device list is part of that independence. The example in 9.4 gives the
front backplane and the rear cage their own disks:

```ini
[HD]                    ; front backplane -> zone 1
ipmi_zone   = 1
hd_names    = ...front-1 ...front-2
min_temp    = 32

[HD:1]                  ; rear cage, hotter, less airflow -> zone 2
ipmi_zone   = 2
hd_names    = ...rear-1 ...rear-2
min_temp    = 30
sensitivity = 1.0
```

So a new instance starts with an empty device list, and the popup of chapter 7 fills it.

**Splitting a multi-zone section is the same action with a prefill.** When the section the cursor
sits on lists several zones, the add action offers to move one of them into the new instance instead
of proposing a free zone. It is a convenience, not a separate feature and not a gate.

```
[CPU]                     [CPU]                [CPU:1]
enabled=1        ->       enabled=1            enabled=1
ipmi_zone=0,1             ipmi_zone=0          ipmi_zone=1
```

**Removing an instance** asks first, because it deletes lines the user wrote.

Three cases checked against the parser:

| File | Result |
|---|---|
| `[CPU] ipmi_zone=0,1` | one curve on two zones |
| `[CPU]` zone 0 plus `[CPU:1]` zone 1 | two curves, accepted |
| `[CPU]` zone 0,1 plus `[CPU:1]` zone 1 | rejected: `[CPU:1] IPMI zone 1 is already used by [CPU]` |

The editor writes no zone rule of its own. The parser already rejects the one wrong case and names
both sections.

### 5.2 The help pane

The bottom four lines are a pane of their own, inside the frame. They are the part a first-time
user actually reads.

**The help follows the cursor. It does not wait for an edit.** A user who is only looking around
learns what each key does before they touch it.

| Line | Content |
|---|---|
| 1 | the key name, then the one-sentence summary |
| 2 | the detail, first line |
| 3 | the detail, second line |
| 4 | the type, unit, default and range — replaced by the check result when the field has one |

Line 4 stays one fixed row, so the pane never changes height.

**`schema.py` owns the wording.** It is not a copy of the comments in `config/smfc.conf`. The file
comment must stay one short line above the key. The pane has four lines and no such limit, so it
says more: what the value does, when to change it, and what it interacts with.

```python
FIELDS = {
    "min_temp": Field(
        type=float, default=30.0, unit="C", minimum=0.0,
        summary="Lowest temperature of the fan curve",
        detail="Below this temperature the fan stays at min_level. "
               "Raise it if the fans spin up too early. It must stay below max_temp.",
    ),
}
```

The shipped comment stays as it is. The two never contradict each other, and the richer text lives
in one place.

**A section has its own help text.** The cursor spends time in the left pane, and a section name
alone says little to a first-time user. So `schema.py` carries a `SECTIONS` table beside `FIELDS`.

| Line | Content when the cursor is in the left pane |
|---|---|
| 1 | the section name, then what it controls |
| 2 | the detail, first line |
| 3 | the detail, second line |
| 4 | its state: enabled or not, which zones it drives, how many devices it lists — or its check result |

```python
SECTIONS = {
    "CPU": SectionHelp(
        summary="Drives fan zones from the CPU temperature",
        detail="Add CPU:1 for a second fan curve on other zones. "
               "Needs the coretemp or k10temp kernel module.",
    ),
}
```

A section that is absent from the file shows the same text, plus one line saying that Enter adds it.

The key list is the last line, outside the frame. It changes with the context: the list above is the
editor, and a popup shows its own keys.

### 5.3 When the terminal changes size

The screen is recomputed from the terminal size, at start and on every `KEY_RESIZE` event. `curses`
delivers that key when the window changes. The editor keeps the selected section, the selected
field, and any edit in progress.

**What grows with the height**

| Part | Behaviour |
|---|---|
| section rows and field rows | take every extra row |
| help pane | stays 4 rows |
| key line | stays 1 row |

So a taller window shows more sections and more fields, and scrolls less. At 19 rows the whole
section list fits with no scrolling at all.

**What grows with the width**

| Part | Behaviour |
|---|---|
| left pane | fixed at 20 columns; the longest label is `Overview` plus two glyphs |
| right pane | takes every extra column, so longer values show in place |
| help pane | takes the full width, so the detail text wraps over fewer lines |

**The frame stops growing at 100 columns.** Beyond that the window is left empty on the right. Help
text wrapped across 200 columns is hard to read, and a value column that wide is wasted space.

**The popup rule of 5.4 does not change with the width.** A path is edited in a popup on a 200-column
terminal too. A rule that changes with the window is a rule a user cannot learn.

**Below the floor of 64 columns or 14 rows**, drop to a single pane. The section list fills the
screen, and Enter opens the field list of the selected section. Esc returns. That is the only place
where a screen stack exists, and it exists because two panes do not fit. The help pane stays, and
drops to 2 lines below 12 rows. Never refuse to start, and never draw outside the window.

### 5.4 Where a value is typed

The right pane gives a value about 21 columns at the minimum width. Every shipped default fits.
Four kinds of real value do not: `control_function` at 27 characters, `remote_parameters` at 31, a
full `npu_smi_path` at 51, and any device list.

So the rule follows the value, not the preference:

| Field kind | Where |
|---|---|
| numbers, booleans, enums — `min_temp`, `steps`, `enabled`, `port` | in place, in the value cell |
| text and paths — `command`, `smartctl_path`, `npu_smi_path`, `remote_parameters` | a popup with a wide field |
| lists — `hd_names`, `nvme_names`, `gpu_device_ids`, `npu_device_ids` | the multi-select popup of chapter 7 |
| `control_function` | a popup with a wide field |

Most keys are numbers, so most edits stay in place. This also removes the need for a field that
scrolls sideways, which is the fiddly part of `curses` text entry.

## 6. Checks

`src/smfc/checks.py` holds this work. It was a refactor of `Service.check_dependencies()`, which
returned on the first error and was therefore a gate rather than a report. An editor needs every
result at once, so the checks became one function per family, each returning a list. The daemon
calls the same functions and now logs every fault at start, one per line.

```python
@dataclass
class CheckResult:
    level: str      # "error", "warn" or "info"
    message: str
    fix: str = ""   # one line the user can act on
```

One function per section: `check_<section>(cfg) -> List[CheckResult]`.

Three tiers by cost:

| Tier | Cost | When it runs |
|---|---|---|
| value — `min_temp < max_temp`, port range, level 0..100 | microseconds | on leaving a field |
| system — file exists, module loaded, device node present | microseconds | on leaving a section |
| hardware — `ipmitool`, `smartctl`, `nvidia-smi`, `npu-smi` | seconds | on `F5` only |

Start with `F5` only, as agreed. Add the value tier later if editing feels blind.

**`smartctl` on a standby disk wakes it.** An editor that spins up eight sleeping disks on every
refresh is worse than no editor. The key must say so: `F5: test hardware (may wake disks)`.

Hardware checks get generous timeouts, 5 to 10 seconds. The user is knowingly waiting, and some BMCs
are slow. `npu_smi_timeout` is the existing precedent for a per-tool timeout.

### Per section

| Section | Checks |
|---|---|
| Ipmi | `command` exists **and is executable**; `ipmi_si` and `ipmi_devintf` loaded; `platform_name` matches what `platform_factory` probes; `exit_level` in -1..100; every `ipmi_zone` value within the board's zone count where the platform knows it — 4 on `generic_x9` and `X10QBi`, probed on an X14 OpenBMC board, unknown on `generic` |
| CPU | `coretemp` or `k10temp` loaded; a hwmon path exists |
| HD | `drivetemp` loaded or `smartctl_path` exists; every `hd_names` device exists; standby guard needs smartctl; `standby_hd_limit` ≤ number of names |
| NVME | every `nvme_names` device exists; its hwmon temperature reads |
| GPU | nvidia needs `nvidia_smi_path`; amd needs `rocm_smi_path`; IDs within the detected count; `amd_temp_sensor` is meaningless for nvidia |
| NPU | `npu_smi_path` — an absolute path exists, or a bare name resolves through `shutil.which` |
| PCI | exactly one of `pci_address`, `pci_id`, `pci_driver`; the `temp_sensor` path reads a number |
| CONST | `level` in 1..100 |
| Exporter | `port` in 1..65535; the port is free **or held by smfc itself**; `bind_address` is `0.0.0.0` or an address this host holds, IPv4 only |
| Overview | no section enabled at all; detected hardware that no section covers; config file not writable, with the `sudo` hint; the zone map (see below) |

Every zone family shares three: `min_temp < max_temp`, `min_level < max_level`, `steps >= 1`. Skip
all three when `control_function` carries a value.

**The Overview row carries the zone map.** Several families on one zone is normal, not a fault. smfc
arbitrates: the highest requested level wins, and a `[CONST]` level acts as the floor of its zone.
The map is an `info` line, so the user can see what they built:

```
zone 0   CPU, NVME
zone 1   HD, CONST
```

The editor writes no zone rule of its own. `Config._validate_no_duplicate_zones()` already rejects
the one wrong case, two enabled instances of the same family on one zone, and it names both
sections in the message.

Severity rules: an `error` blocks saving. A `warn` asks for confirmation. An `info` is a suggestion.

## 7. The device popup

```
 ┌ Select HDs   8 of 8 selected, 2 rows below ───────────────┐
 │ [x] 3A19R759  10.9T  sdd  WDC WD120EFAX-68UNTN0           │
 │ [x] YV4GL5UQ  10.9T  sdh  WDC WD120EFAX-68UNTN0           │
 │ [x] AW76U6XB  10.9T  sdb  WDC WD120EFAX-68UNTN0           │
 │ [x] ELXQMCBN  10.9T  sde  WDC WD120EFAX-68UNTN0           │
 │ [x] BV3A659W  10.9T  sdg  WDC WD120EFAX-68UNTN0           │
 │ [x] 9820ZBRY  10.9T  sdc  WDC WD120EFAX-68UNTN0           │
 │ [x] R5G2WVEC  (missing)   not present now                 │
 │ ───────────────────────────────────────────────────────── │
 │ writes  ata-WDC_WD120EFAX-68UNTN0_3A19R759                │
 │ Space toggle  a all  n none  Enter OK  Esc cancel         │
 └───────────────────────────────────────────────────────────┘
```

### 7.1 The model and the size do not identify a disk

This is measured on `nas`, and it overturns the obvious design.

| Count | Model | Size |
|---|---|---|
| 8 | `WDC WD120EFAX-68UNTN0` | 10.9T |
| 4 | `CT4000P3PSSD8` | 3.6T |
| 2 | `ADATA LEGEND 800` | 1.8T |

A row that shows only the model and the size prints the same text eight times. The user cannot pick
a disk from such a list.

**The serial number is the only discriminator, so it leads every row.** The by-id name already ends
with it:

```
ata-WDC_WD120EFAX-68UNTN0_AW76U6XB
                          ^^^^^^^^ the serial
```

The model still earns its place. It separates the four Crucial drives from the two ADATA drives in
the `[NVME]` popup. It is the second field, not the first.

### 7.2 Never truncate the tail

The longest by-id name on `nas` is 34 characters, or 50 with the `/dev/disk/by-id/` prefix.

Eight of those names share their first 26 characters. So a row cut at the right edge produces eight
identical rows. **Truncate the middle, never the tail.** The tail carries the identity.

The popup needs at least 64 columns. Below that, drop the model column first, then the kernel name.
Never drop the serial.

### 7.3 Further rules from the live data

**Fourteen devices do not fit one screen.** `nas` holds 8 disks and 6 NVMe drives. The list scrolls.
The title says how many are selected and how many rows lie outside the view.

**The kernel name is display only.** On `nas`, `sda` is the last by-id name alphabetically and `sdd`
the first. A kernel name can change across boots. That is why smfc writes the by-id path. Resolve
the kernel name when the popup opens, and never write it.

**Keep an entry that no longer resolves, marked `(missing)`.** That row is what explains the `warn`
from the HD check. Dropping it hides the problem.

**Sort by the by-id name.** The live file on `nas` is in that order. Any other order rewrites eight
lines for no reason and makes the diff unreadable.

### 7.4 One widget, four providers

| Key | Provider | Writes |
|---|---|---|
| `hd_names` | `discover.discover_hds()` | by-id paths |
| `nvme_names` | `discover.discover_nvmes()` | by-id paths |
| `gpu_device_ids` | `nvidia-smi -L` or `rocm-smi` | integer indexes |
| `npu_device_ids` | `npu-smi info -m` | integer indexes |

Name the provider in the field schema.

The two disk providers read the filesystem and fill at once. The GPU and NPU providers run an
external tool, so they are tier 3. Those popups open empty with a `press F5 to scan` line.

Re-run the section's value checks when the popup closes. Changing `hd_names` can invalidate
`standby_hd_limit`.

## 8. Discovery

`src/smfc/discover.py` owns three things, and the installer, the DEB script and the RPM script all
call it:

1. **The two filters.** `discover_hds()` returns the whole SATA and SAS disks, `discover_nvmes()` the
   whole NVMe drives, each as a `/dev/disk/by-id/...` path.
2. **The write format.** `format_device_list()` puts the first device on the key line, every further
   device on its own tab-indented line, and one trailing separator.
3. **The empty-key guard.** `fill_empty_key()` writes a list only where the key is still empty. A key
   that already carries a value belongs to the user.

The command line is what the three scripts use:

```bash
python3 -m smfc.discover hd --fill /etc/smfc/smfc.conf
python3 -m smfc.discover nvme --fill /etc/smfc/smfc.conf
```

Without `--fill` it prints one path per line, which is what the device popup of chapter 7 reads.

**The filters, and what they drop**

| List | Kept | Dropped |
|---|---|---|
| HD | every name the exclusion does not match | a partition, `wwn-` and `-eui` aliases, any `nvme` name, `usb-`, `dm-`, `lvm-`, `md-`, `zd-`, and a numbered duplicate `_1`, `_2`, `_3` |
| NVMe | names starting `nvme-` | a partition, an `-eui` alias, the NQN-style `-nvme` alias, and a numbered duplicate |

A `usb-` name can never reach the NVMe filter, because that filter is anchored on the `nvme-` prefix.

**Verified against the shell filters they replaced**, on two machines:

| Host | by-id entries | Module output | Ground truth |
|---|---|---|---|
| a workstation | 39 | 1 HD, 2 NVMe | 1 SATA, 2 NVMe |
| `nas` | 102 | 8 HD, 6 NVMe | 8 HDD, 6 NVMe |

On `nas` the filters drop 8 `wwn-` aliases, 6 `nvme-..._1` duplicates, 3 `nvme-eui.` and 3 NQN-style
names. The 17 ZFS volumes produce no by-id entry at all, so `^zd-`, `^dm-`, `^lvm-` and `^md-` are
insurance rather than load-bearing.

## 9. The writer

`confwriter.py` keeps the user's file byte for byte, and changes only what the user changed.

| Operation | Behaviour |
|---|---|
| change a value | replace the text after `=` on that line; keep the comment above it |
| add a key to a section | insert it under the last key of that section, with its template comment |
| add a section | append the section header and only the keys the user sets; the rest run on defaults |
| remove a key | never; set it to its default instead |
| unknown key | leave it exactly as found |

Write through a temporary file in the same directory, then `os.replace()`. A crash must never leave
a half-written config.

A device list is written with the first entry on the key line, each further entry on its own
tab-indented line, and one trailing tab line. This is the exact shape of the live file on `nas`:

```
hd_names=/dev/disk/by-id/ata-WDC_WD120EFAX-68UNTN0_3A19R759
	/dev/disk/by-id/ata-WDC_WD120EFAX-68UNTN0_YV4GL5UQ
	/dev/disk/by-id/ata-WDC_WD120EFAX-68UNTN0_AW76U6XB
	
```

Reproduce that shape, including the trailing tab line. `configparser` strips it, and keeping it
means a user who changes nothing sees no diff. Sort the entries by by-id name, as `install.sh`
already writes them.

Also make `Config.parse_device_names()` drop empty lines. Fix both ends of that trap.

### 9.1 Privileges

`/etc/smfc/smfc.conf` is `root:root` and mode `0644`. Anyone may read it; only root may write it.
The service itself runs as root: `config/smfc.service` sets no `User=`.

So the documented command is `sudo smfc-config`. The program must not require it.

| Capability | Needs root | Without it |
|---|---|---|
| browse sections, fields and help | no | works fully |
| save | yes | read-only mode |
| hardware checks on `F5` | yes | pass `-s`, or they report a permission error |
| restart the service | yes | the command is printed |

**Read-only mode is announced at start, not at save time.** The tool tests `os.access(path, W_OK)`
before drawing anything. The user learns it in the first second, not after editing twenty fields:

```
read-only: /etc/smfc/smfc.conf is not writable by this user
re-run as: sudo smfc-config
```

`F2` is disabled in that mode, and the key line says so.

**Never re-exec under `sudo`.** A full-screen program that relaunches itself loses the terminal state
and surprises the user. Print the command and let them run it.

**The `-s, --sudo` flag is the one `smfc-client` already has**, with the same letter and the same
help text: "use sudo for ipmitool/smartctl (if not run as root)". Pass it to `Ipmi` and `HdFc` exactly
as `client.py` does. Two sibling commands must not differ on a flag that means the same thing.

### 9.2 When the config file is missing

This is rare. Every install path leaves `/etc/smfc/smfc.conf` in place. A missing file means the
user deleted it.

The tool must not create one silently. It offers, in this order:

1. Restore from a local backup: `smfc.conf.<tag>` written by `install.sh`, or `.rpmsave` and
   `.dpkg-old` left by a package removal.
2. Download the template of the installed version:
   `https://raw.githubusercontent.com/petersulyok/smfc/refs/tags/v{version}/config/smfc.conf`.
   The version comes from `importlib.metadata.version("smfc")`, as `client.py` already reads it, so
   the template always matches the installed daemon. Ask before fetching, use a 5 second timeout,
   and try once.
3. Say that neither worked, and name both paths. Never invent a file without telling the user.

After a successful save, verify by loading the file through `Config(path)`. Then offer the restart,
but only when the process can perform it and the service is active:

```
Saved /etc/smfc/smfc.conf

smfc.service is active.
Restart it to apply the changes? [y/N]
```

Without the privilege to restart, print the command instead. Never try and fail:

```
Saved /etc/smfc/smfc.conf

Run this to apply the changes:
  sudo systemctl restart smfc
```

## 10. Phases

Each phase ends with passing tests. Phases 1 to 4 are useful on their own, with no UI.

| # | Deliverable | Notes |
|---|---|---|
| 0 | the `^usb-` and `_[0-9]+$` filter fixes | **done**, commits `a43a79c` and `4fc6452` |
| 1 | `schema.py` | **done**; field metadata and help text for all 9 sections, plus the section help |
| 2 | `checks.py` | **done**; `Service.check_dependencies()` now reports every fault, not the first |
| 3 | `discover.py` | **done**; the three scripts call it and hold no regex of their own |
| 4 | `confwriter.py` | round-trip every sample file unchanged; add and remove an instance; read-only mode; the missing-file path of 9.2 |
| 5 | the editor | the curses master-detail screen |
| 6 | the popups | needs phases 3 and 5 |
| 7 | packaging and docs | `pyproject.toml`, README chapter, man page, changelog entries; see chapter 12 for the rest of the release |

Phase 8 note: `debian/changelog` is DEB-only and `smfc.spec` `%changelog` is RPM-only. Keep the
scopes separate.

## 11. Testing

New test files follow the existing names in `test/`: `test_schema.py`, `test_checks.py`,
`test_discover.py`, `test_confwriter.py`, `test_config_editor.py`.

**The acceptance test already exists.** `config/samples/*.conf` is eleven configurations. They cover
CPU-only, HD-only, mixed, multi-curve, GPU, NPU, PCI, CONST-only, X9, X10QBi and an advanced control
function. The editor must open all eleven, round-trip each one unchanged, and report no false error.

Add two fixtures:

- the live `nas` config — 8 sections, no `[PCI]`, `control_function` in `[CPU]`
- `smfc-sample1.conf`, two sections only, to prove that a missing section reads as disabled

Run the suite with `uv run pytest`.

The curses screen is tested through the key dispatch and the render functions, not through a real
terminal. Keep the drawing code thin and the state code testable.

## 12. The 7.0.0 release

`smfc-config` ships in 7.0.0, together with a change to where a manually installed smfc lives. There
is no 6.5.0. A major release is the right place for both, because one of them asks the user to act.

| # | Item | Breaks anything? |
|---|---|---|
| 1 | `smfc-config`, phases 1 to 7 of chapter 10 | no, it is a new command |
| 2 | the install layout, see 12.1 | yes, for a manual installation only |
| 3 | remove the `-ne` command line option | yes, for anyone still passing it |
| 4 | remove the `genericx9` platform name | yes, silently until now, see 12.4 |
| 5 | replace the `Ipmi.*_MODE` constants with `FanMode` | no, they are internal |
| 6 | warn about an unknown section name, see 12.5 | no, it is a new warning |
| 7 | docs: the README install chapter, `DOCKER.md`, the man pages, the changelogs | no |

Order of work: finish the `smfc-config` phases first, because they are additive and independent.
The install layout comes after, because it needs testing on a Debian and a Fedora machine and it
touches the same documents as the release notes.

### 12.1 Where a manually installed smfc lives

`bin/install.sh` installs into the system Python with `pip --break-system-packages`, and the three
Docker images do the same with `pip install --prefix=/usr`. Both write into directories the
distribution owns, which is what PEP 668 exists to prevent. It works today and the escape hatch
keeps narrowing.

The rule becomes two lines:

| Installer | Location | Owner |
|---|---|---|
| DEB, RPM | `/usr` | the distribution's package manager |
| the manual script, the Docker images | `/opt/smfc` | smfc itself |

```bash
python3 -m venv /opt/smfc
/opt/smfc/bin/pip install -q smfc==$VERSION
ln -sf /opt/smfc/bin/smfc        /usr/local/bin/smfc
ln -sf /opt/smfc/bin/smfc-client /usr/local/bin/smfc-client
ln -sf /opt/smfc/bin/smfc-config /usr/local/bin/smfc-config
```

The unit file stays in `/etc/systemd/system/`, which is the correct place for a locally installed
unit, and **`ExecStart=smfc` stays as it is**. Naming `/opt/smfc/bin/smfc` explicitly would be
safer against shadowing and wrong for this release: see 12.3.

**The migration must fail safe.** An existing manual installation keeps working until the user runs
the script again, and the old copy in `/usr/local/lib/python3*/dist-packages/smfc` must not be left
behind. So the order is fixed:

1. Test that `python3 -m venv` works at all. Debian and Ubuntu ship it as a separate package, so say
   `apt install python3-venv` and stop, before touching anything.
2. Remove any previous `/opt/smfc` and build it again. A venv is cheap, and a rebuild makes a first
   install and a fifth install end the same way.
3. Verify that `/opt/smfc/bin/smfc --version` runs.
4. Only then remove the old copy: `python3 -m pip uninstall -y smfc`. It is safe on a DEB or RPM
   machine, where pip simply reports that smfc is not installed.
5. Only then replace the symlinks, reload systemd, and restart the service if it was running.

If anything before step 4 fails, the old installation is intact and the machine still has fan
control. `bin/uninstall.sh` must then handle both layouts.

**The Docker images need the same change and no migration**, because an image is rebuilt from
scratch. Create the venv with `--without-pip`, install into it with the pip that is already deleted
in the same layer, and symlink `/usr/bin/smfc`. Drop the distro `python3-pyudev` and `py3-udev`
packages: the venv gets `pyudev` from PyPI, which is pure Python and needs no compiler.

### 12.2 What the installer may delete

Today's `install.sh` only overwrites files. It never deletes. The new one has to remove the previous
installation, or a manual upgrade leaves an orphan copy of the package behind and two versions of
smfc exist on one machine.

Deleting needs a rule, and the obvious one does not work. README chapter 9.5 already records why:

> Different Linux distros install the Python package to different folders (tested on Ubuntu 24.04,
> Debian 13, SUSE Leap 15, Proxmox 9, and Arch Linux)

On some of them `pip` installs into `/usr/local`, on others into `/usr`. So the path cannot tell the
script whether a distribution package owns those files.

**Ask the package manager instead.**

```bash
owner_of() {                      # prints the owning package, or nothing
  command -v dpkg   >/dev/null && dpkg -S   "$1" 2>/dev/null && return
  command -v rpm    >/dev/null && rpm -qf   "$1" 2>/dev/null && return
  command -v pacman >/dev/null && pacman -Qo "$1" 2>/dev/null && return
}
```

| Answer | What the script does |
|---|---|
| a package owns it | stop, and say to remove smfc with `apt`, `dnf` or `pacman` first |
| nothing owns it | a manual installation; `pip uninstall -y smfc` is safe wherever it sits |

Three further rules:

1. **Never delete configuration.** `/etc/smfc/smfc.conf` and `/etc/default/smfc` keep the backup
   behaviour they have today.
2. **Delete only after the new installation is proven.** Build `/opt/smfc`, run `--version`, and only
   then remove the old copy. A failure before that leaves a working machine.
3. **Only the unit file, the man pages and the defaults file are still overwritten**, exactly as
   today. Nothing else the script did not create is touched.

**The new layout also ends the variation.** After 7.0.0 a manual installation is `/opt/smfc` on every
distribution, so the README table collapses from "this folder or that one" to a single row. That is a
second reason for the virtual environment, independent of PEP 668.

### 12.3 Upgrading a manual installation from 6.4.2

Two paths reach 7.0.0, and both must work.

**The user fetches the new `install.sh`.** It migrates: build `/opt/smfc`, verify it, remove the old
copy, replace the symlinks. That is 12.1.

**The user runs the `install.sh` they already have.** The 6.4.2 script reads the latest version from
PyPI, so it installs 7.0.0 into the system Python in the old layout. It then downloads the rest from
the matching tag:

```bash
SMFC_VERSION=$(pip index versions smfc ...)        # 7.0.0
pip install --break-system-packages smfc==7.0.0    # old layout, /usr/local/...
curl -o /etc/systemd/system/smfc.service \
     .../refs/tags/v7.0.0/config/smfc.service      # the 7.0.0 unit file
```

An old script therefore installs a new unit file beside an old layout. **That is why the unit file
must not name the binary by path.** `ExecStart=smfc` resolves through systemd's default `PATH` in
every layout:

| Layout | Binary | Resolved |
|---|---|---|
| DEB, RPM | `/usr/bin/smfc` | yes |
| manual, before 7.0.0 | `/usr/local/bin/smfc` | yes |
| manual, 7.0.0 | `/usr/local/bin/smfc` symlinked into `/opt/smfc` | yes |

So the second path leaves a working service in the old layout, and the next run of the new script
migrates it. The release notes name this case, so a user is not puzzled when the documented paths
differ from their machine.

Nothing else fetched from the tag can mismatch: the configuration format, the defaults file and the
man pages are the same for both layouts.

### 12.4 The two removals that break a working configuration

`-ne` has logged a deprecation warning since 6.2.0, so its removal is expected.

`genericx9` has not. `Config.PLATFORM_NAME_ALIASES` maps it to `generic_x9` silently, so a user on
that value has never been told. Removing it in a release that also never warned means the error
message has to do the teaching:

```
[Ipmi] invalid value: platform_name=genericx9.
Use generic_x9. Valid values: auto, generic, generic_x9, generic_x14, X10QBi.
```

Today the message names the bad value and stops there. That is not enough for a value that worked
in the previous release.

### 12.5 An unknown section name is silent today

The section names lost their zone tags in 5.0.0: `[CPU zone]` became `[CPU]`. The parser has no
alias for the old form, and a missing section means disabled, so a file that still uses the old
names parses into a configuration with no fan controller at all and says nothing. The fans then run
on the BMC curve with no explanation.

`checks.py` gains one `warn` per section name the schema does not know, which covers the old names,
a typo like `[CPU1]`, and anything else. The editor shows such a section read-only and never deletes
it, exactly as chapter 5 already says for an unknown key.

The changelog also states that the old section names "will be supported for a while". That has not
been true since 5.0.0 and is corrected in this release.

## 13. Risks

| Risk | Handling |
|---|---|
| `smartctl` wakes sleeping disks | tier 3 only, and the key label says so |
| a false error on the exporter port | compare the owning process, not only the port |
| a subpackage missing from the wheel | check the built artifact, not the source tree |
| the daemon importing the editor | grep `src/smfc/__init__.py`; the import would be circular |
| a comment lost on save | round-trip test over all eleven samples plus the `nas` file |
| an ambiguous-width glyph breaks the frame | `curses` line constants, and ASCII status glyphs |
| the terminal is too narrow | fall back to one pane below 64 columns or 14 rows |
| the config file is not writable | test at start, and say what to do |
| the install migration leaves an orphan copy | uninstall the old package before the symlinks, see 12.2 |
| the installer deletes a file a package manager owns | ask `dpkg`, `rpm` or `pacman` who owns it, see 12.2 |
