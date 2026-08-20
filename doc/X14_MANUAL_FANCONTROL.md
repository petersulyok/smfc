# Manual Fan Control on Supermicro X14 Motherboards — User Guide

How to set fan duty by hand on a Supermicro X14 (AST2600) BMC using **`ipmitool` raw
commands only**. No BMC shell, no web UI.

All commands below assume:

```bash
BMC="-H <bmc-ip> -U <user> -P <password>"     # omit -H/-U/-P entirely for local in-band use
```

> **Validation status.** The command byte layouts are confirmed. What has *not* been
> verified on hardware is that a duty write moves exactly the fans you expect on your
> specific board — check that once with a read-back (§4.4) before relying on it.

---

## 1. Basics

Fan control on X14 is normally automatic: the BMC picks a fan table from the active
**base fan mode** (Standard, FullSpeed, Optimal, …) and drives the fans from
temperature. To set duty by hand you must first switch the BMC into **manual mode**,
otherwise your duty value is overwritten within about a second.

### Terms used in this guide

| Term | Meaning |
| --- | --- |
| **Fan header** | A physical fan connector on the board, labelled `FAN1`, `FAN2`, … (numbered) or `FANA`, `FANB`, … (lettered). This is the name printed on the board and shown by `ipmitool sdr elist`. |
| **Sensor number** (`<sensorNum>`) | The one-byte address of a fan in the IPMI commands that read a fan — e.g. `0x41` for FAN1. Every fan header has one; it is board-specific and listed in §3. Read commands take this byte, never the fan's name. |
| **Fan reading** | What a read command returns for one fan: its **RPM** (measured revolutions per minute, from the fan's tacho wire) and its **duty** (see below). Both are per fan, addressed by sensor number. |
| **Duty** | The commanded fan speed as a percentage, `0`–`100` (`0x00`–`0x64` on the wire). This is what you set; it is not the same as RPM — see §4.4. |
| **Zone** | A group of fan headers that share one speed. A duty write sets a whole zone; every fan in a zone reports the same duty. Zone membership is board- and mode-specific (§3). |
| **Base fan mode** | The BMC's automatic fan profile — Standard, FullSpeed, Optimal, … Selects the temperature-to-speed behaviour used whenever manual mode is not active. |
| **Manual mode** | A per-zone on/off flag. While it is on for a zone, the BMC stops driving that zone automatically and the duty you set stays. |
| **Failsafe** | A per-zone emergency state the BMC enters on fan failure or a missing thermal sensor: the zone is forced to 100 % and ignores your duty. Readable per zone. |

### Facts that shape every procedure in this guide

- **Fans are controlled in zones, not individually.** One duty write moves a whole
  zone. Boards have 1–4 zones depending on model and base mode (§3).
- **Duty is a percentage, 0–100** (`0x00`–`0x64`).
- **Fan sensor numbers start at `0x41` (FAN1) and increase by one per fan**, in the
  order the fans appear in the BMC's sensor list: `FAN1` = `0x41`, `FAN2` = `0x42`,
  and so on. The lettered fans (`FANA`, `FANB`, …) continue the same run after the
  last numbered fan — e.g. on a board with FAN1–FAN5, `FANA` = `0x46`. The count of
  numbered fans differs per board, so the byte for a given fan is board-specific:
  per-board list in §3, or read it off your unit with
  `ipmitool $BMC sdr elist full | grep -i fan`.
- **Manual mode is per zone.** Enabling it on zone 1 leaves every other zone under
  automatic control.
- **Changing the base fan mode always clears manual mode, on every zone.** So it is
  not required before going manual — but if you do want a different base mode, change
  it *first*; doing it afterwards silently drops you back to automatic control.
- **The duty value is sticky; the manual flag is not.** Once set, the duty holds
  indefinitely with no need to re-write it. But a BMC reboot, a firmware update, a
  fan-mode change from any interface (IPMI, web UI, Redfish), or an internal restart
  of the fan controller silently clears the manual flag — and automatic control takes
  the fans back within ~1 s. If a duty must hold unattended, run the watchdog in §4.5:
  **poll the flag, not the duty**.
- **A base mode is also your fallback.** Whenever manual mode is lost, the fans revert
  to the base mode's automatic curve. Standard/Optimal = sane; FullSpeed = 100 %, loud
  but safe; Silent = minimum cooling, risky under load.
- **Failsafe overrides everything.** On fan failure or a missing thermal sensor the
  BMC forces the affected zone to 100 % regardless of manual mode. Failsafe state is
  readable (§2).
- **Standard vs FullSpeed does not matter once you are in manual mode.** They differ
  only in the fallback curve if manual mode is lost, and in how loud the few seconds
  right after the mode switch are.

---

## 2. The commands

| Purpose | Command | Reply / notes |
| --- | --- | --- |
| Get base fan mode | `ipmitool $BMC raw 0x30 0x45 0x00` | 1 byte, mode value (table below) |
| Set base fan mode | `ipmitool $BMC raw 0x30 0x45 0x01 <mode>` | clears manual mode; fans are disturbed for a few seconds |
| Enable manual, zone *z* | `ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 <z> 0x01` | `<z>` is **1-based**: first zone = `0x01` |
| Disable manual, zone *z* | `ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 <z> 0x00` | automatic control resumes |
| Read manual flag, zone *z* | `ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 <z>` | 1 byte: `01` / `00` (see below) |
| Read failsafe flag, zone *z* | `ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x02 <z>` | 1 byte: `01` / `00` |
| Set duty, zone *z* | `ipmitool $BMC raw 0x30 0x70 0x66 0x00 <z> <duty%>` | `<z>` is **0-based**: first zone = `0x00`; `<duty%>` = `0x00`–`0x64` |
| Enable/disable manual, **all** zones | `ipmitool $BMC raw 0x30 0x70 0x66 0x02 <0/1>` | shortcut for multi-zone boards |
| Read duty + temperature of a fan | `ipmitool $BMC raw 0x30 0x70 0x88 <sensorNum>` | 2 bytes: **`[duty%, temp]`** — duty first; `0xff` = unavailable |
| Read RPM of a fan | `ipmitool $BMC raw 0x04 0x2d <sensorNum>` | standard Get Sensor Reading |
| List all fans with RPM + sensor number | `ipmitool $BMC sdr elist full \| grep -i fan` | easiest way to find your board's sensor numbers |

### 🔴 The same zone is addressed by a different number in each command

This is the single most common mistake. The manual/failsafe commands count zones from
**1**, the duty command counts them from **0**. Written out for the first two zones:

```bash
# ---- zone 1 ----
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 0x01 0x01   # manual ON,  zone 1
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 0x01        # read manual flag, zone 1
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00 0x32             # set duty 50%, zone 1   <- 0x00

# ---- zone 2 ----
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 0x02 0x01   # manual ON,  zone 2
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 0x02        # read manual flag, zone 2
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x01 0x32             # set duty 50%, zone 2   <- 0x01
```

So for zone 1 you write `0x01` in the manual commands but `0x00` in the duty command;
for zone 2, `0x02` and `0x01`. Do not "align" the two — `0x00` in a `0x2c 0x04`
command addresses a zone that does not exist and returns an error.

### What each command returns, and what an error means

`ipmitool` prints a successful reply as space-separated **lowercase hex bytes with no
`0x` prefix**, and prints nothing for commands that return no data. ⚠️ **Read every
reply byte as hex**: a duty of 100 % is printed `64`, and 50 % is printed `32` — both
look like decimal numbers but are not. A **completion code** other than success is not data
— `ipmitool` reports it as a failure line naming the code:

```
Unable to send RAW command (channel=0x0 netfn=0x2c lun=0x0 cmd=0x4 rsp=0xc1): Invalid command
```

Never parse such a line as a value. In a script, check the exit status of `ipmitool`
or test the captured output for the byte you expect (as the watchdog in §4.5 does)
rather than assuming an empty result means `00`.

| Command | Success | Error codes it can return |
| --- | --- | --- |
| `0x30 0x45 0x00` (get mode) | 1 byte: the mode value | — |
| `0x30 0x45 0x01 <mode>` (set mode) | no data | **`0xC1`** if `<mode>` is above `0x0B` — no mode is changed |
| `0x2c 0x04 … 0x00 <zone>` (read manual) | 1 byte `01`/`00` | **`0xC1`** if the command is short (both `<op>` and `<zone>` must be present) or `<op>` is above `0x02`; another code if that zone does not exist on the board or the fan controller cannot answer |
| `0x2c 0x04 … 0x02 <zone>` (read failsafe) | 1 byte `01`/`00` | as above |
| `0x2c 0x04 … 0x01 <zone> <0/1>` (set manual) | no data | as above |
| `0x30 0x70 0x66 0x00 <zone> <duty%>` (set duty) | no data | **`0xCC`** if `<zone>` is above `0x04` |
| `0x30 0x70 0x66 0x02 <0/1>` (manual, all zones) | no data | **`0xCC`** if the byte after `0x66` is above `0x02` |
| `0x30 0x70 0x88 <sensorNum>` (duty + temp) | 2 bytes `[duty%, temp]`, both hex — e.g. ` 64 2d` = 100 %, 45 °C; `ff` = unavailable | **`0xC7`** if exactly one sensor byte was not supplied |

Meaning of the codes (standard IPMI):

| Code | Name | In practice |
| --- | --- | --- |
| `0xC1` | Invalid command | The BMC would not run the command at all: a value outside the accepted range, too few bytes, or — if even a correctly formed command returns this — the firmware does not implement it on this unit |
| `0xC7` | Request data length invalid | Wrong number of bytes sent |
| `0xCC` | Invalid data field in request | Command accepted, but an argument is out of range (a zone your board does not have) |

An error never changes anything: a rejected command leaves the fan mode, the manual
flags, and the duty exactly as they were.

### Manual-flag reply values

| Reply | Meaning | Action |
| --- | --- | --- |
| `01` | Manual mode active for that zone — your duty stands | none |
| `00` | Manual mode is off — automatic control is driving the fans | re-enable manual, then re-write the duty |
| *no data byte, error* | The BMC rejected the command or could not answer (bad byte count, invalid zone, controller not running) | treat as **unknown**: re-assert manual and duty |

A failsafe reply of `01` means the zone is forced to 100 % and your duty has no
effect until the cause (usually a dead or unplugged fan) is fixed.

### Base fan mode values (`raw 0x30 0x45 0x01 <mode>`)

| Value | Mode | Value | Mode |
| --- | --- | --- | --- |
| `0x00` | Standard | `0x06` | LiquidCooling |
| `0x01` | FullSpeed (all fans 100 %) | `0x07` | Smart |
| `0x02` | Optimal | `0x08` | PUE |
| `0x03` | PUE2 | `0x09` | SmartCooling |
| `0x04` | HeavyIO | `0x0A` | Performance |
| `0x05` | PUE3 | `0x0B` | Silent (minimum cooling) |

> ⚠️ **Not every board supports every mode, and an unsupported mode is accepted
> silently.** The BMC stores the value you set — `raw 0x30 0x45 0x00` will read it
> back — but the fans run a different table. Known cases:
>
> | Board | Modes that really take effect | An unsupported mode behaves as |
> | --- | --- | --- |
> | X14DBI, X14SBI | Standard, FullSpeed, HeavyIO, Optimal | Standard |
> | X14DBG-AP (10-fan boards) | FullSpeed, Optimal, HeavyIO | **Optimal** |
> | X14SRG-TF and related workstation boards | FullSpeed, Performance, Silent | **Performance** |
>
> Pick a mode your board supports, so the mode you read back is the one that is
> actually running.

---

## 3. Your board: fan sensor numbers and zones

**Fan sensor numbers** start at `0x41` for FAN1 and increase by one per fan. Lettered
fans (FANA, FANB, …) follow the last numbered fan. Confirm on your unit with:

```bash
ipmitool $BMC sdr elist full | grep -i fan
```

| Board | Fans | Sensor numbers |
| --- | --- | --- |
| X14SBW-F / X14SBW-TF | 6 | FAN1–FAN6 = `0x41`–`0x46` |
| X14SBI-F / X14SBI-TF | 7 | FAN1–FAN5 = `0x41`–`0x45`, FANA = `0x46`, FANB = `0x47` |
| X14DBI-SP / X14DBI-T | 8 | FAN1–FAN6 = `0x41`–`0x46`, FANA = `0x47`, FANB = `0x48` |
| X14DBG-AP | 11 | FAN1–FAN10 = `0x41`–`0x4A`, FAN11_STBY = `0x4B` |
| X14SRG-TF | 8 | FAN1–FAN3 = `0x41`–`0x43`, FANA = `0x44`, FANC = `0x45`, FANB = `0x46`, FAND = `0x47`, FAN1A = `0x48` |

**Zones** — which fans one duty write moves:

| Board / mode | Zones | Zone contents |
| --- | --- | --- |
| Standard, FullSpeed, HeavyIO on boards without a specific fan table | 1 | all fans together |
| X14DBI-SP / -T | 2 | zone 1 = FAN1–FAN6 · zone 2 = FANA, FANB |
| X14SBI-F / -TF | 2 | zone 1 = FAN1–FAN5 · zone 2 = FANA, FANB |
| X14DBG-AP (10-fan) | 2 | zone 1 = FAN1–FAN5 · zone 2 = FAN6–FAN10 |
| X14SRG-TF (Performance) | 4 | z1 = FAN1–FAN3 · z2 = FANA, FANC · z3 = FANB, FAND · z4 = FAN1A |

Two practical rules:

- **Drive and watch every zone your board has.** A zone you skip keeps running under
  automatic control.
- **To read a zone's duty, read any one fan in it** — all fans of a zone share the same
  duty. If two fans of the same zone report different duty values, your zone
  assumption is wrong.

If you are unsure how many zones a board has, probe: `raw 0x2c 0x04 0xcf 0xc2 0x00
0x00 0x01`, `… 0x02`, `… 0x03`, … — existing zones answer with `00`/`01`, missing
zones return an error.

---

## 4. Operating manual fan control

One loop: check the board → know the base mode → go manual → set the duty → verify →
hold → release.

**The minimum to get a fixed fan speed is 4.2 + 4.3.** The board is always running some
base mode already, and manual mode can be enabled on top of it — so the usual path is
to start from the mode you find. Step 4.1 is preparation: read the mode, because it
determines your zone map; *changing* it is optional and disturbs the fans. 4.5 is what
keeps a duty in place unattended; 4.6 hands control back.

### 4.0 Preflight — confirm the board supports manual mode

The commands in this guide are X14-specific. Other Supermicro generations answer some
of them, so **run one read first** and stop if it fails:

```bash
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 0x01
```

| Result | Meaning |
| --- | --- |
| `01` or `00` | Per-zone manual mode is present — continue with 4.1 |
| `0xC1` *Invalid command* | This BMC does **not** implement per-zone manual mode. Nothing in §4 applies; stop here |

H14 boards answer `0xC1` to exactly this command — they have no per-zone manual mode
at all, and on them fan control over IPMI is limited to selecting a base fan mode.

> ⚠️ **Do not fall back to trying the other commands on a board that fails this
> check.** Two traps:
> - `0x30 0x45` (fan mode) exists on other generations too, so a working mode command
>   is **not** evidence that the rest of this guide applies.
> - The `0x30 0x70 0x66` opcode also exists on older/other generations, but with a
>   **different payload layout** — there `0x66 0x01 <zone> <duty%>` writes a duty and
>   `0x66 0x00 <zone>` reads one. The X14 form used in 4.3 therefore means something
>   different on those boards.
>
> If the preflight fails, use the board's own documentation for its fan commands.

### 4.1 Know the base fan mode — change it only if you need to (optional)

The BMC is **always** in some base fan mode; there is no "no mode" state. So the normal
case is simply to start from the mode the board is already in — read it and carry on.

**Read it — always:**

```bash
ipmitool $BMC raw 0x30 0x45 0x00                # -> 1 byte, the current mode
```

The mode determines the zone map (§3), so you need to know it to pick the right zone
numbers in 4.2 and 4.3.

**Set it — only when you want a different fallback or zone layout:**

```bash
ipmitool $BMC raw 0x30 0x45 0x01 0x00           # set Standard (0x01 = FullSpeed, …)
sleep 8                                         # fans are disturbed for a few seconds
```

Reasons to set it: the current mode's automatic curve is not a fallback you want if
manual mode is ever lost, or you need a different zone layout (e.g. one zone per fan
instead of all fans on one), or you simply want a known starting state regardless of
what someone configured before. Choose a mode your board actually supports (§2).

Reasons not to: the change disturbs the fans for a few seconds, and it is pointless if
the current mode is already the one you want.

> ⚠️ **If you do set it, it must happen here — before 4.2.** Setting the base fan mode
> clears manual mode on every zone, so doing it later in the loop silently undoes your
> manual control.

### 4.2 Enable manual mode on every zone you will drive

Zone argument here is **1-based**: first zone = `0x01`.

```bash
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 0x01 0x01   # manual ON, zone 1
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 0x01        # confirm  -> expect 01
```

Repeat for zones `0x02`, `0x03`, … on a multi-zone board (§3), or enable all zones in
one command:

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x01                  # manual ON, all zones
```

A zone left out here keeps running under automatic control.

### 4.3 Set the duty

Zone argument here is **0-based**: first zone = `0x00`. Duty is a percentage,
`0x00`–`0x64`.

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00 0x1e   # zone 1, 30%
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00 0x32   # zone 1, 50%
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00 0x64   # zone 1, 100%
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x01 0x32   # zone 2, 50%
```

The value holds indefinitely; there is no need to re-write it periodically. Writing to
a zone that does not exist on your board is harmless — nothing moves.

### 4.4 Verify

```bash
ipmitool $BMC raw 0x30 0x70 0x88 0x41        # duty% + temperature of FAN1 (duty is the FIRST byte)
ipmitool $BMC raw 0x04 0x2d 0x41             # RPM of FAN1
ipmitool $BMC sdr elist full | grep -i fan   # every fan at once
```

Wait 5–10 s after a duty change before reading — fans need time to spin up or down.

**Reading the reply.** The two bytes come back as plain hex:

```
$ ipmitool $BMC raw 0x30 0x70 0x88 0x41
 64 2d
```

`64` is the **duty in hex = 100 %**, `2d` is the temperature = 45 °C. Do not read them
as decimal: `32` means 50 %, not 32 %. A byte of `ff` means the value is unavailable.

To get decimals directly:

```bash
read -r duty temp <<<"$(ipmitool $BMC raw 0x30 0x70 0x88 0x41)"
printf 'duty=%d%% temp=%d C\n' "0x$duty" "0x$temp"
```

Do this once per board to **confirm your zone map**: set zone 1 to 100 %, then read a
fan you believe is in zone 1 and one you believe is in zone 2, and check that only the
first changed.

> A duty read-back does **not** tell you whether manual mode is still active: the duty
> value stays where you left it even after the flag is cleared, until automatic control
> moves it. Only the manual flag (§4.5) answers that.

**Optional — a duty-to-RPM reference for your fans.** RPM is not a fixed fraction of
duty (fans have a minimum spin point) and the BMC stores no such curve, so if you want
to judge speed from RPM alone, measure two points per fan model once:

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00 0x64 ; sleep 10 ; ipmitool $BMC raw 0x04 0x2d 0x41   # RPM100
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00 0x32 ; sleep 10 ; ipmitool $BMC raw 0x04 0x2d 0x41   # RPM50
```

Then estimate `duty% ≈ 50 + (RPM − RPM50) × 50 / (RPM100 − RPM50)`. Redo after a fan
swap.

### 4.5 Hold it — the watchdog

Manual mode can be cleared at any time by a BMC restart, a firmware update, or a
fan-mode change made from another interface, and the fans then return to the base
curve within about a second. To hold a duty unattended, poll the **flag** (not the
duty) every 30–60 s and re-assert both when it drops. Only `ipmitool` and `bash` are
required; Ctrl-C releases manual mode cleanly.

```bash
#!/bin/bash
BMC="-H <bmc-ip> -U <user> -P <password>"
MODE=0x00        # base fan mode to fall back to (0x00 Standard)
ZONE_M=0x01      # zone for manual commands   (1-based)
ZONE_D=0x00      # same zone for duty command (0-based)
DUTY=0x32        # 50%

leave() { ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 $ZONE_M 0x00; exit 0; }

# 4.0 preflight: does this board have per-zone manual mode at all?
if ! ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 $ZONE_M >/dev/null 2>&1; then
  echo "This BMC does not support per-zone manual fan mode - aborting." >&2
  exit 1
fi
trap leave INT TERM

ipmitool $BMC raw 0x30 0x45 0x01 $MODE                          # 4.1 base mode (optional; drop
sleep 8                                                         #     these two lines to keep the
                                                                #     mode the BMC is already in)
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 $ZONE_M 0x01    # 4.2 manual ON
ipmitool $BMC raw 0x30 0x70 0x66 0x00 $ZONE_D $DUTY             # 4.3 duty

fails=0
while :; do
  st=$(ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 $ZONE_M 2>/dev/null | tr -d ' ')
  case "$st" in
    01) fails=0 ;;                    # still manual - nothing to do
    00) fails=0                       # cleared -> re-assert both
        ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 $ZONE_M 0x01
        ipmitool $BMC raw 0x30 0x70 0x66 0x00 $ZONE_D $DUTY ;;
    *)  fails=$((fails + 1))          # unreadable: BMC busy, rebooting, or unreachable
        ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 $ZONE_M 0x01
        ipmitool $BMC raw 0x30 0x70 0x66 0x00 $ZONE_D $DUTY
        if [ "$fails" -ge 10 ]; then
          echo "Manual flag unreadable 10 times in a row - giving up, fans left on the base mode." >&2
          exit 1
        fi ;;
  esac
  sleep 45
done
```

On a multi-zone board extend the loop over each zone pair (`ZONE_M` = 1, 2, … with
`ZONE_D` = 0, 1, …).

### 4.6 Leave manual mode

```bash
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x01 0x01 0x00   # manual OFF, zone 1
ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 0x01        # confirm -> expect 00
```

Repeat for every zone you enabled, or release all at once with
`ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x00`. Automatic control resumes about a second
later, on the base mode from 4.1.

### 4.7 Emergency exit

If fans stop or temperatures climb:

```bash
ipmitool $BMC raw 0x30 0x45 0x01 0x01     # FullSpeed: clears manual mode on ALL zones, fans to 100%
```

Setting the base fan mode clears manual mode on **every** zone — not just the one you
were driving — so this one command is enough even if you no longer know which zones
you enabled.

> One exception to watch: if the board is **already** in FullSpeed, re-sending the same
> mode may not count as a change, and manual mode can survive. Check with the flag read
> and, if it still answers `01`, release manual explicitly:
>
> ```bash
> ipmitool $BMC raw 0x2c 0x04 0xcf 0xc2 0x00 0x00 0x01        # -> 01 means still manual
> ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x00                  # manual OFF, all zones
> ```

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Duty write is accepted but fans do not change | manual mode not active on that zone, or the wrong zone number | read the manual flag (§2); remember duty zones are 0-based, manual zones 1-based |
| Fans revert to automatic after minutes or hours | manual flag cleared by a BMC restart or a fan-mode change | run the watchdog (§4.5) |
| Fans stuck at 100 %, duty writes ignored | failsafe is active | read the failsafe flag (§2); check for a failed or unplugged fan |
| Manual/failsafe command returns an error instead of `00`/`01` | wrong byte count or an `<op>` above `0x02` (`0xC1`), or that zone does not exist on this board | probe the zones (§3); the read form takes exactly `… 0xcf 0xc2 0x00 <op> <zone>` — see the code table in §2 |
| Duty command returns `0xCC` | zone argument above `0x04` | duty zones are 0-based: first zone is `0x00` (§2) |
| Set-mode command returns `0xC1` | mode value above `0x0B` | use a value from the mode table (§2) |
| A read returns `0xC7` | wrong number of bytes — `0x30 0x70 0x88` takes exactly one sensor number | send exactly one sensor byte |
| Mode reads back as set, but fan behaviour is wrong | the board does not support that mode | use a mode your board supports (§2) |
| Only some fans respond to a duty write | the others are in a different zone | drive every zone (§3) |
| Every manual command returns `0xC1`, mode commands work | not an X14-class BMC — no per-zone manual mode (H14 behaves this way) | run the preflight (§4.0); this guide does not apply to that board |
