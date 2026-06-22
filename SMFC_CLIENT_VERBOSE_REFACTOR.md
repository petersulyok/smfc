# smfc-client `--verbose` output refactor — proposals

## Context

The current `smfc-client --verbose` output appends a flat `Devices` table
that lists every disk/CPU core/NVMe/GPU across all fan controllers. That
section is useful but loses the relationship between a device and the
controller that owns it, and it doesn't surface any of the controller's
configured steering window (`temp_min..temp_max → level_min..level_max`)
or runtime parameters.

This document captures three layout proposals for a future refactor that
makes the verbose output **fan-controller-oriented**: each enabled fan
controller gets its own block showing its config, its devices (with
per-device temperatures), and the steering decision it just made. The
proposals were drafted against a real `/snapshot` reading from a running
service (X11SCH-LN4F, CPU + 8-disk HD array + 6 NVMe drives).

## Data already available in the snapshot

Per fan-controller entry, the snapshot already carries:

- `section`, `type`, `enabled`, `ipmi_zones`, `polling`, `deferred_apply`
- `temp_min_c`, `temp_max_c`, `level_min_pct`, `level_max_pct` (steering
  window — static config)
- `last_temp_c` (aggregated input the curve was evaluated against),
  `last_level_pct` (current output)
- `devices: [{name, temp_c}, ...]` (per-device readings)
- `standby_guard` (HD only — `enabled`, `limit`, `states`, `array_state`,
  `standby_count`)

Fields NOT currently in the snapshot but worth adding for the most
detailed proposal: `sensitivity`, `smoothing`, `temp_calc`, `steps`.

---

## Proposal A — Compact, one block per controller

Each controller is a small bordered block. Tight vertical space; reads
top-to-bottom. The header line carries `zone(s)`, `polling` and
`deferred=` flags; everything else lives inside the block.

```
[CPU]  cpu  zone(s)=[0]  polling=2.0s  deferred=yes
  Window: T=[30..60]C → L=[35..100]%
  Temp:   35.0 C  →  Level: 35 %
  Devices:
    cpu0     35.0 C

[HD]  hd  zone(s)=[1]  polling=960.0s  deferred=no
  Window: T=[35..48]C → L=[35..100]%
  Temp:   31.0 C  →  Level: 35 %
  Standby Guard: enabled (limit=2)  Array: SSSSSSSS  (8/8 standby)
  Devices:                                            State
    /dev/disk/by-id/ata-WDC_WD120EFAX-..._99GMFQVW    28.0 C   STANDBY
    /dev/disk/by-id/ata-WDC_WD120EFAX-..._ASWRX1X8    29.0 C   STANDBY
    /dev/disk/by-id/ata-WDC_WD120EFAX-..._D7THCLWZ    31.0 C   STANDBY
    /dev/disk/by-id/ata-WDC_WD120EFAX-..._F9ZAPZG7    29.0 C   STANDBY
    /dev/disk/by-id/ata-WDC_WD120EFAX-..._G0NPRV4J    30.0 C   STANDBY
    /dev/disk/by-id/ata-WDC_WD120EFAX-..._MPZ04PTK    27.0 C   STANDBY
    /dev/disk/by-id/ata-WDC_WD120EFAX-..._PGPWM9LU    29.0 C   STANDBY
    /dev/disk/by-id/ata-WDC_WD120EFAX-..._SZCYJMFR    30.0 C   STANDBY

[NVME]  nvme  zone(s)=[0]  polling=2.0s  deferred=yes
  Window: T=[38..65]C → L=[35..100]%
  Temp:   0.0 C  →  Level: 0 %
  Devices:
    /dev/disk/by-id/nvme-ADATA_LEGEND_800_2O4429AJ8DPT     0.0 C
    /dev/disk/by-id/nvme-ADATA_LEGEND_800_2O4429AJ8GEX     0.0 C
    /dev/disk/by-id/nvme-CT4000P3PSSD8_2336E8740474        0.0 C
    /dev/disk/by-id/nvme-CT4000P3PSSD8_2340E87B3E4F        0.0 C
    /dev/disk/by-id/nvme-CT4000P3PSSD8_2340E87B40B1        0.0 C
    /dev/disk/by-id/nvme-CT4000P3PSSD8_2515E9B5D525        0.0 C

IPMI zones (live)
  Zone    Level
  ------  -----
  0        35 %
  1        35 %
```

**Pros**
- Scans well; every block is self-contained.
- Header line gives zone/polling/deferred at a glance — the three knobs
  that matter for understanding what a controller is doing.
- No new snapshot fields needed.

**Cons**
- The `Window: ... → ...` line packs two pieces of information past the
  eye on one line.
- Long device paths still wrap or force the column wide.

---

## Proposal B — Tabular per controller, with a "position" indicator

Each controller still has its own block, but the static config goes in a
small property table on the left and the devices in a table on the right.
The aggregated temperature gets a visual bar showing where it sits inside
the steering window — **the `●━━━━━━` indicator is the killer feature**:
at a glance you can tell how close the temperature is to triggering a
fan ramp-up.

```
[CPU]   cpu   zones=[0]   polling=2.0s   deferred=yes
  ┌───────────────────────────────┬────────────────────────────────┐
  │ Temperature window            │ Devices                        │
  │   30 C ━━●━━━━━━━━━━━━━ 60 C  │   cpu0          35.0 C         │
  │              35.0 C           │                                │
  │ Level window                  │                                │
  │   35 %  ●━━━━━━━━━━━━━ 100 %  │                                │
  │              35 %             │                                │
  └───────────────────────────────┴────────────────────────────────┘

[HD]   hd   zones=[1]   polling=960.0s   deferred=no
  ┌───────────────────────────────┬─────────────────────────────────────────────────┐
  │ Temperature window            │ Devices                                  State  │
  │   35 C ●━━━━━━━━━━━━━━━ 48 C  │   ata-WDC..._99GMFQVW     28.0 C        STANDBY │
  │              31.0 C           │   ata-WDC..._ASWRX1X8     29.0 C        STANDBY │
  │ Level window                  │   ata-WDC..._D7THCLWZ     31.0 C        STANDBY │
  │   35 %  ●━━━━━━━━━━━━━ 100 %  │   ata-WDC..._F9ZAPZG7     29.0 C        STANDBY │
  │              35 %             │   ata-WDC..._G0NPRV4J     30.0 C        STANDBY │
  │                               │   ata-WDC..._MPZ04PTK     27.0 C        STANDBY │
  │ Standby Guard: on (limit=2)   │   ata-WDC..._PGPWM9LU     29.0 C        STANDBY │
  │ Array: SSSSSSSS (8/8 standby) │   ata-WDC..._SZCYJMFR     30.0 C        STANDBY │
  └───────────────────────────────┴─────────────────────────────────────────────────┘

[NVME]   nvme   zones=[0]   polling=2.0s   deferred=yes
  ┌───────────────────────────────┬─────────────────────────────────────────────────┐
  │ Temperature window            │ Devices                                         │
  │   38 C ●━━━━━━━━━━━━━━━ 65 C  │   nvme-ADATA_LEGEND_800_2O4429AJ8DPT      0.0 C │
  │               0.0 C           │   nvme-ADATA_LEGEND_800_2O4429AJ8GEX      0.0 C │
  │ Level window                  │   nvme-CT4000P3PSSD8_2336E8740474         0.0 C │
  │   35 %  ●━━━━━━━━━━━━━ 100 %  │   nvme-CT4000P3PSSD8_2340E87B3E4F         0.0 C │
  │              0 %              │   nvme-CT4000P3PSSD8_2340E87B40B1         0.0 C │
  │                               │   nvme-CT4000P3PSSD8_2515E9B5D525         0.0 C │
  └───────────────────────────────┴─────────────────────────────────────────────────┘

IPMI zones (live)
  Zone    Level
  ------  -----
  0        35 %
  1        35 %
```

**Pros**
- The `●━━━━━━` bar makes it instantly obvious how close the controller
  is to ramping up.
- Standby Guard moves into the controller's own block where it belongs.
- Side-by-side layout uses horizontal screen real-estate effectively.

**Cons**
- Wider (≈90 cols at minimum).
- Uses Unicode box drawing — fine for modern terminals; needs a `+--+`
  ASCII fallback for `--no-color` or for terminals that don't render it.
- Strips the `/dev/disk/by-id/` prefix from device names to keep the
  column readable; arguable whether that's acceptable.

---

## Proposal C — Maximum detail (one screen per controller)

Each controller gets a full info block including the LUT plateau curve
(which `print_temp_level_mapping()` already produces at `LOG_CONFIG`).
This is closest to "tell me everything about this controller right now".

```
═══════════════════════════════════════════════════════════════════════
[HD]   hd                                              IPMI zone(s): [1]
═══════════════════════════════════════════════════════════════════════
  Polling           : 960.0 s                  Deferred apply  : no
  Sensitivity       : 2.0 C                    Smoothing       : 1
  Temp calc         : avg                      Steps           : 5

  Steering window:
    Temperature  : 35 C ─────●─── 48 C   current = 31.0 C  (below floor)
    Level        : 35 %  ●──────── 100 %   current = 35 %

  Curve (T → L):
    T=[ 0..35]C → L=35%   T=[36..38]C → L=48%   T=[39..40]C → L=61%
    T=[41..43]C → L=74%   T=[44..45]C → L=87%   T=[46..100]C → L=100%

  Devices                                       Temp     State
  ─────────────────────────────────────────────  ──────   ───────
  /dev/disk/by-id/ata-WDC_WD120EFAX-..._99GMFQVW  28.0 C  STANDBY
  /dev/disk/by-id/ata-WDC_WD120EFAX-..._ASWRX1X8  29.0 C  STANDBY
  /dev/disk/by-id/ata-WDC_WD120EFAX-..._D7THCLWZ  31.0 C  STANDBY
  /dev/disk/by-id/ata-WDC_WD120EFAX-..._F9ZAPZG7  29.0 C  STANDBY
  /dev/disk/by-id/ata-WDC_WD120EFAX-..._G0NPRV4J  30.0 C  STANDBY
  /dev/disk/by-id/ata-WDC_WD120EFAX-..._MPZ04PTK  27.0 C  STANDBY
  /dev/disk/by-id/ata-WDC_WD120EFAX-..._PGPWM9LU  29.0 C  STANDBY
  /dev/disk/by-id/ata-WDC_WD120EFAX-..._SZCYJMFR  30.0 C  STANDBY

  Standby Guard: enabled  (limit=2)
    Array state: SSSSSSSS  →  8/8 disks in standby
```

**Pros**
- Complete picture of one controller.
- "below floor" / "above ceiling" / "N% through window" annotation on
  the temperature is extremely useful — tells the user the current
  reading is outside the steering range.
- The plateau curve is genuinely diagnostic for tuning the fan curve.

**Cons**
- Lots of vertical space — three controllers can fill a screen and a
  half.
- Some fields (`sensitivity`, `smoothing`, `temp_calc`, `steps`) aren't
  in the snapshot today; would need adding to `_build_controller_entry()`
  in `src/smfc/snapshot.py`.

---

## Recommended path

**Start with Proposal A.** It's the smallest behaviour change (just
rearrange what's already shown), gives every controller its own clearly
labelled block, and requires zero new fields in the snapshot.

The cleanest next step — getting most of Proposal B's visual benefit
without box-drawing — is to add the steering-window indicator as a
single line inside Proposal A:

```
[HD]  hd  zone(s)=[1]  polling=960.0s  deferred=no
  Window:  T 35 C ●━━━━━━━━━━━━━━━ 48 C    L 35 %  ●━━━━━━━━━━━━━ 100 %
  Now:     T 31.0 C (below)                L 35 %
  Standby Guard: enabled (limit=2)  Array: SSSSSSSS  (8/8 standby)
  Devices:
    /dev/disk/by-id/ata-WDC_WD120EFAX-..._99GMFQVW   28.0 C   STANDBY
    ...
```

The `(below)` / `(above)` / `(40 % through window)` annotation is the
highest-signal addition for fan-curve tuning.

---

## Open questions to settle before implementation

1. **Long device paths.** `/dev/disk/by-id/ata-WDC_WD120EFAX-68UNTN0_99GMFQVW`
   is 51 characters. Options:
   - Leave as-is and let the column auto-widen (current Devices-section
     behaviour; works at ≥ 90 cols).
   - Truncate the middle to a fixed width with `…`.
   - Strip the `/dev/disk/by-id/` prefix in display only (keep it in
     Prometheus labels).

2. **Snapshot fields not yet exposed.** `sensitivity`, `smoothing`,
   `temp_calc`, `steps` would need adding to `_build_controller_entry()`
   in `src/smfc/snapshot.py` if Proposal C is chosen. Worth doing if the
   verbose mode is meant to be a complete diagnostic view.

3. **Aggregated `Temp` column in the existing Controllers table.** Once
   each controller has its own block in verbose mode, the
   top-of-report Controllers table duplicates information. Options:
   - Keep it (overview at a glance).
   - Omit it in verbose mode (saves a screen).
   - Replace it in verbose mode with a one-line summary (e.g. "5
     controllers across zones [0, 1, 2]").

4. **ASCII vs Unicode.** Proposal B and the steering bar use `●━━━━━━`
   Unicode glyphs. With `--no-color` or on terminals without good
   Unicode rendering, fall back to `*-----` ASCII. Decide whether the
   fallback should be tied to `--no-color` or to a separate
   `--ascii-only` flag.

5. **Standby Guard placement.** Currently a separate top-level section.
   In all three proposals it migrates into the HD controller's block.
   Confirm that's the intended direction (it removes the dedicated
   standby section from non-verbose output as well, or only in verbose
   mode?).
