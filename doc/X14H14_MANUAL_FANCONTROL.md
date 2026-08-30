# Manual Fan Control on Supermicro X14 and H14 Motherboards

How to set fan duty by hand on a Supermicro X14 or H14 server, driving the fans yourself
instead of letting the BMC's automatic thermal control do it.

**What you need**

- **`ipmitool`**, over the network or in-band. The fans are driven entirely with raw IPMI
  commands.
- **Access to the BMC web UI**, for the one setting that cannot be changed over IPMI.

**What you should know before starting**

- **Two different BMC firmware stacks are in use across these boards**, and the split does
  not follow the generation: there are X14 boards on each stack, and H14 boards on each
  stack. The board name does not tell you which one you have. The two share almost nothing
  where fan control is concerned — different commands, a different lever for taking the
  fans over, and different behaviour when a fan fails.
- A command from the wrong stack is usually rejected outright. The `0x30 0x70 0x66` duty
  commands share a layout across both stacks, but the *meaning* of taking the fans over
  differs — per-zone manual mode on one, a global bypass on the other — so following the
  wrong Part still leaves you with the wrong mental model. **Run Part 1 first.**
- Taking the fans over means the BMC stops protecting the machine thermally. Nothing in
  this guide reads temperatures for you or puts a limit on how low you set a duty.

**How this guide is organised**

- **Part 1 — Which BMC do you have.** One command tells you. Everything after this depends
  on the answer.
- **Part 2 — Terms and conventions.** What duty, zone and fan sensor number mean, how to
  read a reply, and what the completion codes mean. Applies to both stacks.
- **Part 3 — OpenBMC boards.** Per-zone manual mode.
- **Part 4 — ATEN boards.** A single global bypass flag.
- **Part 5 — Board reference.** Fan maps, zone layouts, and per-board differences.

All commands below assume:

```bash
BMC="-H <bmc-ip> -U <user> -P <password>"     # omit -H/-U/-P entirely for local in-band use
```

---

# Part 1 — Which BMC do you have

## 1.1 The live test

Run this read. It changes nothing.

```bash
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x01
```

| Result | Stack | How you take the fans over | Go to |
| --- | --- | --- | --- |
| `cf c2 00 01` or `cf c2 00 00` | **OpenBMC** | **Per-zone manual mode** — a switch for each zone that tells the BMC to stop driving that zone, leaving your duty in place. Other zones keep running automatically. The switch is readable, so you can check at any time whether you still hold the fans. | **Part 3** |
| `0xC1` *Invalid command* | **ATEN** | **A global bypass flag** — one switch that suspends automatic fan control for every zone at once, leaving your duty in place. There is no per-zone equivalent, and the switch cannot be read back, so its state has to be inferred from the fan duty. | **Part 4** |

### Where the two names come from

**OpenBMC** is the open-source BMC firmware project. Supermicro's build of it identifies
itself as `openbmc-phosphor` — Phosphor is the name of the reference userspace inside
OpenBMC — so you will also see this stack called Phosphor. Its fan control is a separate
daemon that reads a JSON fan table and drives the PWM outputs.

**ATEN** is the name commonly used for Supermicro's long-standing BMC firmware, after the
company whose BMC software line it derives from. The firmware does not use that name
itself; it reports only `Supermicro BMC`. This is the stack Supermicro shipped through the
X9–X13 generations, and it is still used on many X14 and H14 boards. Its fan control is
built into the single IPMI process rather than living in a separate daemon.

The names are only labels for two sets of commands. Nothing in this guide depends on which
name you prefer — what matters is the answer to the command above.

## 1.2 The board name does not tell you the stack

Two examples break every guess:

- `H14SHM` is an H14 board on **OpenBMC**, while every other H14 is ATEN.
- `X14SDW` and `X14SDV` are X14 boards on **ATEN**, while the rest of the X14 line is
  OpenBMC.

| Stack | Boards |
| --- | --- |
| **OpenBMC** | Most X14 boards — `X14DBI-SP`, `X14DBI-T`, `X14DBG-AP`, `X14SBI-F`, `X14SBI-TF`, `X14SBW-F`, `X14SBW-TF`, `X14SBSC`, `X14SRG-TF`, `X14SRA-TF`, `X14SAE-F`, `X14SAV-F`, `X14SAZ-F`, `X14DBHM` — plus `H14SHM` |
| **ATEN** | All other H14 boards — `H14DSG-O-CPU`, `H14SRV-HLN4F`, `H14SSL-NT`, `H14SST-G`, `H14DST-F`, `H14DSH` — plus the SoC X14 boards `X14SDW` and `X14SDV` |

Treat this table as a hint only. **The command in 1.1 is the authoritative answer**, and it
also covers a board that is not listed here.

## 1.3 The `0x30 0x70 0x66` payload layout is the same on both stacks

`0x30 0x70 0x66` exists on both stacks, and the selector layout is **the same** on each:

| | OpenBMC | ATEN |
| --- | --- | --- |
| `0x66 0x00 <zone>` | **reads** a zone's duty | **reads** a zone's duty |
| `0x66 0x01 <zone> <duty%>` | **sets** a zone's duty | **sets** a zone's duty |
| `0x66 0x02 <0\|1>` | manual mode on/off, all zones | bypass flag on/off, all zones |

The first byte after `0x66` is the selector: `0x00` reads, `0x01` writes, `0x02` toggles
the automatic control off/on. This holds on both stacks. So the command bytes do **not**
diverge — what differs is only what selector `0x02` *means* (per-zone manual mode on
OpenBMC, a global bypass flag on ATEN) and the surrounding behaviour, which Parts 3 and 4
cover separately.

⚠️ **The zone argument is 0-based for `0x66` on both stacks** (first zone = `0x00`). On
OpenBMC the *separate* manual-mode command (`0x2e 0x04`, Part 3) is 1-based instead — that
mismatch is a real trap, but it is between two different commands, not inside `0x66`. See
3.3.

---

# Part 2 — Terms and conventions

These apply to both stacks.

| Term | Meaning |
| --- | --- |
| **Fan header** | A physical fan connector, labelled `FAN1`, `FAN2`, … (numbered) or `FANA`, `FANB`, … (lettered). The name printed on the board and shown by `ipmitool sdr elist`. |
| **Sensor number** | The one-byte address of a fan in commands that read one fan — e.g. `0x41` for FAN1. Board-specific; see Part 5. Read commands take this byte, never the fan's name. |
| **Duty** | The commanded fan speed as a percentage. This is what you set. It is not RPM. |
| **RPM** | The measured speed from a fan's tacho wire. Related to duty, but not proportional — fans have a minimum spin point. |
| **Zone** | A group of fan headers that share one duty. A duty write sets a whole zone. |
| **Base fan mode** | The BMC's automatic profile — Standard, Full Speed, Optimal, Heavy IO, … Selects the temperature-to-speed behaviour used whenever you are not driving the fans yourself. |

## 2.1 Reading a reply

`ipmitool` prints a successful reply as space-separated **lowercase hex bytes with no
`0x` prefix**, and prints nothing at all for commands that return no data.

⚠️ **Read every reply byte as hex.** A duty of 100 % prints as `64`, and 50 % prints as
`32`. Both look like decimal numbers and are not.

A **completion code** other than success is not data. `ipmitool` reports it as a failure
line naming the code:

```
Unable to send RAW command (channel=0x0 netfn=0x2e lun=0x0 cmd=0x4 rsp=0xc1): Invalid command
```

Never parse such a line as a value. In a script, check `ipmitool`'s exit status, or test
the captured output for the byte you expect — do not assume an empty result means `00`.

## 2.2 Completion codes

| Code | Name | In practice |
| --- | --- | --- |
| `0xC1` | Invalid command | The BMC will not run the command at all — the firmware does not implement it, the byte count is wrong, or a value is outside the accepted range |
| `0xC7` | Request data length invalid | Wrong number of bytes sent |
| `0xCC` | Invalid data field in request | Command accepted, but an argument is out of range — an unsupported fan mode, or a zone the board does not have |
| `0xD3` | Destination unavailable | The handler ran but could not reach its target |
| `0xD4` | Insufficient privilege | On the ATEN stack, this is what a duty write returns while **System Lockdown** is enabled |

**An error never changes anything.** A rejected command leaves the fan mode, the control
flags and the duty exactly as they were.

## 2.3 Finding your fans

```bash
ipmitool $BMC sdr elist full | grep -i fan     # names, RPM and sensor numbers
ipmitool $BMC sensor        | grep -i fan      # the same plus the RPM thresholds
ipmitool $BMC raw 0x04 0x2d <sensorNum>        # RPM of one fan (standard IPMI)
```

Sensor numbers start at `0x41` for FAN1 and increase by one per fan, in sensor-list order.
Lettered fans continue the same run after the last numbered fan: on a board with FAN1–FAN5,
`FANA` is `0x46`. The count of numbered fans differs per board, so always confirm on your
own unit.

The **Lower Critical** RPM threshold from `ipmitool sensor` is the number that matters
when choosing a duty: drop a fan below it and the BMC declares a fan failure and takes the
fans away from you.

---
# Part 3 — OpenBMC boards

Applies when the command in 1.1 returned `00` or `01`.

Fan control here is normally automatic: the BMC picks a fan table from the active base
fan mode and drives the fans from temperature. To set duty by hand you first switch the
BMC into **manual mode**, which is a **per-zone** flag. Without it your duty is
overwritten within about a second.

## 3.1 Facts that shape every procedure here

- **Manual mode is per zone.** Enabling it on zone 1 leaves every other zone under
  automatic control.
- **Fans are controlled in zones, not individually.** Boards have 1–5 zones depending on
  model and base mode.
- **The zone map depends on the board *and* the base mode.** On some boards Standard and
  HeavyIO put every fan in one zone while the other modes use several. Re-check your map
  after any mode change (5.1).
- **Duty is a percentage, 0–100** (`0x00`–`0x64`). The BMC converts it as
  `pwm = percent x 255 / 100`, so a read-back can land one percent low. The BMC's own
  automatic control never drives below 15 %, but a manual write has no such floor —
  do not write `0x00` casually.
- **Changing the base fan mode clears manual mode on every zone.** So if you want a
  different base mode, set it *first*. Doing it afterwards silently drops you back to
  automatic control.
- **The duty value is sticky; the manual flag is not.** The duty holds indefinitely with
  no need to re-write it, but a BMC reboot, a firmware update, a fan-mode change from any
  interface, or an internal restart of the fan controller clears the manual flag — and
  automatic control takes the fans back within about a second.
- **The manual flag is readable.** That is what a watchdog should poll (3.6), not the duty.
- 🔴 **The fan names `ipmitool` prints are not the names the zone tables use.** The BMC
  keeps two naming systems, and they overlap without matching. On an X14SAE-F the label
  `FAN2` is sensor `0x44`, while the zone table's `FAN2` is sensor `0x42`, which
  `ipmitool` calls `FAN1A`. Trust the sensor number, never the name (5.1).
- **Failsafe overrides everything.** On fan failure or a missing thermal sensor the BMC
  forces the affected zone to 100 % regardless of manual mode. Failsafe state is readable
  per zone.
- **The base mode is your fallback.** Whenever manual mode is lost the fans revert to that
  mode's automatic curve. Standard and Optimal are sane; Full Speed is 100 %, loud but
  safe; Silent is minimum cooling and risky under load.
- **Standard versus Full Speed makes no difference while manual mode is active.** They
  differ only in the fallback curve, and in how loud the seconds right after a mode switch
  are.

## 3.2 The commands

| Purpose | Command | Reply / notes |
| --- | --- | --- |
| Get base fan mode | `ipmitool $BMC raw 0x30 0x45 0x00` | 1 byte, mode value (3.4) |
| Get the modes this board supports | `ipmitool $BMC raw 0x30 0x45 0x02` | 2 bytes, a little-endian bitmask over the mode values of 3.4. `02 0c` = `0x0C02` = bits 1, 10, 11 = FullSpeed, Performance, Silent |
| Set base fan mode | `ipmitool $BMC raw 0x30 0x45 0x01 <mode>` | clears manual mode; fans are disturbed for a few seconds |
| Enable manual, zone *z* | `ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 <z> 0x01` | `<z>` is **1-based**: first zone = `0x01` |
| Disable manual, zone *z* | `ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 <z> 0x00` | automatic control resumes |
| Read manual flag, zone *z* | `ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 <z>` | `cf c2 00 <flag>`. The **last** byte: `01` = manual, `00` = automatic |
| Read failsafe flag, zone *z* | `ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x02 <z>` | `cf c2 00 <flag>`. The **last** byte: `01` = zone forced to 100 % |
| Read duty, zone *z* | `ipmitool $BMC raw 0x30 0x70 0x66 0x00 <z>` | `<z>` is **0-based**: first zone = `0x00`. 1 byte, that zone's current duty %. Does **not** write — a trailing duty byte is ignored |
| Set duty, zone *z* | `ipmitool $BMC raw 0x30 0x70 0x66 0x01 <z> <duty%>` | `<z>` is **0-based**: first zone = `0x00`. Returns a completion code only — no data byte, so it does **not** echo the duty. Read it back with the `0x00` form above |
| Enable/disable manual, **all** zones | `ipmitool $BMC raw 0x30 0x70 0x66 0x02 <0\|1>` | shortcut for multi-zone boards |
| Read duty + temperature of a fan | `ipmitool $BMC raw 0x30 0x70 0x88 <sensorNum>` | 2 bytes `[duty%, temp]` — duty first; `ff` = unavailable |
| Read RPM of a fan | `ipmitool $BMC raw 0x04 0x2d <sensorNum>` | standard Get Sensor Reading |

### Error codes per command

| Command | Success | Errors |
| --- | --- | --- |
| `0x30 0x45 0x00` | 1 byte, the mode | — |
| `0x30 0x45 0x01 <mode>` | no data | `0xC1` if `<mode>` is above `0x0B`; no mode is changed |
| `0x2e 0x04 … 0x00 <zone>` | 4 bytes `cf c2 00 <flag>` | `0xC1` if the command is short (both op and zone must be present) or the op is above `0x02`; another code if that zone does not exist |
| `0x2e 0x04 … 0x02 <zone>` | 4 bytes `cf c2 00 <flag>` | as above |
| `0x2e 0x04 … 0x01 <zone> <0\|1>` | no data | as above |
| `0x30 0x70 0x66 0x00 <zone>` | 1 byte: that zone's duty | `0xCC` if `<zone>` is above `0x04`; `0xC7` if the payload after `0x66` is not 2 or 3 bytes |
| `0x30 0x70 0x66 0x01 <zone> <duty%>` | no data (completion code) | `0xCC` if `<zone>` is above `0x04`; `0xC7` if the payload after `0x66` is not 2 or 3 bytes |
| `0x30 0x70 0x66 0x02 <0\|1>` | no data | `0xCC` if the byte after `0x66` is above `0x02`, or if the flag is above `0x01` |
| `0x30 0x70 0x88 <sensorNum>` | 2 bytes | `0xC7` if not exactly one sensor byte was supplied |

## 3.3 🔴 The same zone is addressed by a different number in each command

The manual and failsafe commands count zones from **1**. The duty command counts them from
**0**. This is the most common mistake on this stack.

```bash
# ---- zone 1 ----
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 0x01 0x01   # manual ON, zone 1
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x01        # read flag, zone 1
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x32             # duty 50%, zone 1   zone byte 0x00

# ---- zone 2 ----
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 0x02 0x01   # manual ON, zone 2
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x02        # read flag, zone 2
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x01 0x32             # duty 50%, zone 2   zone byte 0x01
```

Do not "align" the two. `0x00` in a `0x2e 0x04` command addresses a zone that does not
exist and returns an error.

## 3.4 Base fan mode values

| Value | Mode | Value | Mode |
| --- | --- | --- | --- |
| `0x00` | Standard | `0x06` | LiquidCooling |
| `0x01` | FullSpeed (all fans 100 %) | `0x07` | Smart |
| `0x02` | Optimal | `0x08` | PUE |
| `0x03` | PUE2 | `0x09` | SmartCooling |
| `0x04` | HeavyIO | `0x0A` | Performance |
| `0x05` | PUE3 | `0x0B` | Silent (minimum cooling) |

⚠️ **Not every board supports every mode, and an unsupported mode is accepted silently.**
The BMC stores the value — `raw 0x30 0x45 0x00` reads it back — but the fans run a
different table:

| Board | Modes that take effect | An unsupported mode behaves as |
| --- | --- | --- |
| X14DBI, X14SBI | Standard, FullSpeed, HeavyIO, Optimal | Standard |
| X14DBG-AP (10-fan) | FullSpeed, Optimal, HeavyIO | Optimal |
| X14SRG-TF and related workstation boards | FullSpeed, Performance, Silent | Performance |

## 3.5 Procedure

**The minimum is steps 2 and 3.** The board is already in some base mode, and manual mode
can be enabled on top of it.

**Step 1 — read the base fan mode.** Optional to change, but read it: it determines your
zone map (Part 5).

```bash
ipmitool $BMC raw 0x30 0x45 0x00                # -> 1 byte, the current mode
```

The board is always in some mode, so you can leave it alone and go straight to step 2.
There are two reasons to change it anyway.

**A different fallback curve.** The base mode is what the fans revert to whenever manual
mode is lost — a BMC reboot, a firmware update, someone changing the fan mode from the web
UI. If the board is sitting in Silent, that fallback is minimum cooling, which is a poor
place to land unattended. Standard or Optimal are sane; Full Speed is 100 %, loud but safe.

**A different zone layout.** Selecting a base mode makes the BMC load a **fan table**, and
that table is what defines the zones: how many there are, and which fans belong to each. A
zone is simply a group of fans driven by one PWM output, so "set duty on zone 2" moves
exactly the fans that table puts in zone 2. Change the mode and you load a different table,
which can change both numbers.

In practice, on most boards the everyday modes — Standard, Optimal, Heavy IO, Full Speed —
all load a table with **one zone containing every fan**, so a duty write moves the whole
chassis and there is nothing to address separately. Two things change that:

- **Some modes carry a multi-zone table.** On boards that offer them, Performance and
  Silent load a three-zone table where the numbered and lettered fans are driven
  separately.
- **Some boards override the common modes.** On those, Optimal, Heavy IO and Full Speed
  load a board-specific two-zone table instead of the generic single-zone one.

So if your board answers only zone 1 and you want the front and rear fans on different
duties, changing the mode is the lever that gives you the extra zones — and conversely, a
zone map that worked yesterday can collapse to one zone if someone changed the mode.

⚠️ **Re-probe the zones after any mode change**, and do not infer the layout from the mode
name. On some boards a mode is accepted and reads back correctly while a different table is
actually loaded (3.4), so the only reliable answer is asking the BMC which zones exist:

```bash
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x01     # zone 1 -> 00/01 if it exists
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x02     # zone 2 …
```

🔴 **If you change it, do it here, before step 2.** Setting the base fan mode clears manual
mode on **every** zone. Changing it after step 2 silently hands the fans back to automatic
control without any error, and the duty you write in step 3 will be overwritten within
about a second.

```bash
ipmitool $BMC raw 0x30 0x45 0x01 0x00           # Standard
sleep 8                                         # fans are disturbed for a few seconds
```

The pause matters: the mode change makes the BMC re-evaluate its fan tables, so the fans
move for a few seconds. Enabling manual mode during that window can leave you unsure
whether a later reading reflects your duty or the tail of the mode switch.

**Step 2 — enable manual mode on every zone you will drive.** Zone argument is 1-based.

```bash
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 0x01 0x01   # manual ON, zone 1
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x01        # confirm -> expect cf c2 00 01
```

Repeat for `0x02`, `0x03`, … on a multi-zone board, or take every zone at once:

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x01                  # manual ON, all zones
```

A zone left out keeps running under automatic control.

**Step 3 — set the duty.** Zone argument is 0-based, duty is `0x00`–`0x64`.

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x1e   # zone 1, 30%
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x32   # zone 1, 50%
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x64   # zone 1, 100%
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x01 0x32   # zone 2, 50%
```

The value holds indefinitely. Writing to a zone the board does not have returns `0xCC`.

**Step 4 — verify.** Wait 5–10 s for the fans to settle.

```bash
ipmitool $BMC raw 0x30 0x70 0x88 0x41        # duty% + temperature of FAN1 (duty is the FIRST byte)
ipmitool $BMC raw 0x04 0x2d 0x41             # RPM of FAN1
ipmitool $BMC sdr elist full | grep -i fan   # every fan at once
```

A reply of ` 64 2d` means 100 % and 45 °C — both hex. To get decimals:

```bash
read -r duty temp <<<"$(ipmitool $BMC raw 0x30 0x70 0x88 0x41)"
printf 'duty=%d%% temp=%d C\n' "0x$duty" "0x$temp"
```

Do this once per board to confirm your zone map: set zone 1 to 100 %
(`raw 0x30 0x70 0x66 0x01 0x00 0x64`), then read a fan you believe is in zone 1 and one you
believe is in zone 2, and check that only the first changed.

⚠️ A duty read-back does **not** tell you whether manual mode is still active — the duty
stays where you left it until automatic control moves it. Only the manual flag answers
that.

## 3.6 Holding a duty unattended

Poll the **manual flag**, not the duty, and re-assert both the flag and the duty when it
drops. The flag is what tells you the fans were taken back; the duty must be re-written
because it is only honoured while manual mode is active, so whatever cleared the flag has
also let the automatic curve overwrite the duty.

```bash
#!/bin/bash
BMC="-H <bmc-ip> -U <user> -P <password>"
MODE=0x00        # base fan mode to fall back to
ZONE_M=0x01      # zone for manual commands   (1-based)
ZONE_D=0x00      # same zone for duty command (0-based)
DUTY=0x32        # 50%

leave() { ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 $ZONE_M 0x00; exit 0; }

# re-assert manual mode AND re-write the duty; the duty only holds while manual is on
assert() {
  ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 $ZONE_M 0x01   # manual ON  (0x2e, 1-based)
  ipmitool $BMC raw 0x30 0x70 0x66 0x01 $ZONE_D $DUTY            # duty WRITE (0x66 0x01, 0-based)
}

if ! ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 $ZONE_M >/dev/null 2>&1; then
  echo "This BMC does not support per-zone manual fan mode - aborting." >&2
  exit 1
fi
trap leave INT TERM

ipmitool $BMC raw 0x30 0x45 0x01 $MODE                          # optional; drop these two
sleep 8                                                         # lines to keep the current mode
assert                                                          # manual ON + first duty write

fails=0
while :; do
  st=$(ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 $ZONE_M 2>/dev/null | awk '{print $NF}')
  case "$st" in
    01) fails=0 ;;                    # still manual - duty is holding, nothing to do
    00) fails=0; assert ;;            # cleared -> re-assert manual and re-write the duty
    *)  fails=$((fails + 1))          # unreadable: BMC busy, rebooting, unreachable
        assert
        if [ "$fails" -ge 10 ]; then
          echo "Manual flag unreadable 10 times in a row - giving up." >&2
          exit 1
        fi ;;
  esac
  sleep 45
done
```

Three points this loop depends on:

- **The duty write is selector `0x01`** (`0x30 0x70 0x66 0x01 …`). Selector `0x00` is a
  *read*; writing with `0x00` does nothing and the fans stay on whatever the automatic
  curve last set (1.3, 3.2).
- **Recovery re-writes the duty, not just the flag.** Re-enabling manual alone leaves the
  zone at whatever duty the automatic loop wrote while the flag was clear. `assert()` does
  both, and it is safe to call unconditionally.
- **The flag is the last reply byte** (`awk '{print $NF}'`), because the reply is
  `cf c2 00 <flag>` — reading the first byte gives `cf` and always looks like a takeover.

On a multi-zone board extend the loop over each zone pair (`ZONE_M` = 1, 2, … with
`ZONE_D` = 0, 1, …), re-asserting each independently.

## 3.7 Releasing, and the emergency exit

```bash
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 0x01 0x00   # manual OFF, zone 1
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x01        # confirm -> expect cf c2 00 00
```

Repeat for every zone you enabled, or release all at once with
`raw 0x30 0x70 0x66 0x02 0x00`. Automatic control resumes about a second later.

If temperatures climb:

```bash
ipmitool $BMC raw 0x30 0x45 0x01 0x01     # FullSpeed: clears manual mode on ALL zones, fans to 100%
```

One command is enough even if you no longer know which zones you enabled. One exception:
if the board is **already** in FullSpeed, re-sending the same mode may not count as a
change and manual mode can survive. Check the flag, and if it still reads `01`, release
explicitly with `raw 0x30 0x70 0x66 0x02 0x00`.

## 3.8 Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Duty write accepted but fans do not change | manual mode not active on that zone, or the wrong zone number | read the manual flag; duty zones are 0-based, manual zones 1-based (3.3) |
| Fans revert to automatic after minutes or hours | manual flag cleared by a BMC restart or a fan-mode change | run the watchdog (3.6) |
| Fans stuck at 100 %, duty writes ignored | failsafe is active | read the failsafe flag; check for a failed or unplugged fan |
| Manual/failsafe command errors instead of returning `00`/`01` | wrong byte count, op above `0x02`, or that zone does not exist | the read form takes exactly `… 0xcf 0xc2 0x00 <op> <zone>` |
| Duty command returns `0xCC` | zone argument above `0x04` | duty zones are 0-based: first zone is `0x00` |
| Set-mode returns `0xC1` | mode value above `0x0B` | use a value from 3.4 |
| A read returns `0xC7` | wrong byte count — `0x30 0x70 0x88` takes exactly one sensor number | send exactly one sensor byte |
| Mode reads back as set, but fan behaviour is wrong | the board does not support that mode | use a mode your board supports (3.4) |
| Only some fans respond to a duty write | the others are in a different zone | drive every zone (Part 5) |

---
# Part 4 — ATEN boards

Applies when the command in 1.1 returned `0xC1`.

Fan control here is normally automatic: a control loop inside the BMC rewrites every
zone's duty about once a second, following a curve chosen by the base fan mode. To set
duty by hand you first **suspend that loop with the bypass flag**. Without it your duty is
overwritten within about a second.

## 4.1 Facts that shape every procedure here

- **The bypass flag is the lever, not the fan mode.** Setting Full Speed (or any mode) and
  then writing a duty does not hold: the automatic loop keeps re-asserting its own duty in
  every mode. Only the bypass stops it, and it works from any mode.
- **The bypass is global and write-only.** One flag covers all zones, and **there is no
  command that reads it back**. You infer its state by writing a duty and re-reading it
  (4.4).
- **The bypass does not persist.** It is cleared at BMC start. Nothing else clears it — a
  fan-mode change from the web UI or Redfish will not take it away from you.
- **The base fan mode does persist**, so do not leave the board in Full Speed: after a
  restart it comes back at 100 % with no bypass to stop it.
- **Fans are controlled in zones**, addressed 0-based, and each zone must be written
  explicitly. `0x0f` is **not** an all-zones value on any board.
- **Every zone is bypassed, not just the one you drive.** A zone you do not write sits
  frozen at its last duty rather than following temperature.
- **Duty is a percentage.** On the H14 boards it is stored as an 8-bit PWM value, so the
  read-back can be 1 lower than what you wrote. On X14SDW / X14SDV it can be exact instead.
  Measure your board once (4.4).
- **System Lockdown blocks the duty write** with `0xD4`.
- 🔴 **Fan failure may override the bypass.** On some boards the fan-failure check runs
  before the bypass check, so a tripped fan-fail forces 100 % on every tick regardless of
  what you set. See the per-board table in Part 5, and in all cases keep your duty high
  enough that no fan drops below its Lower Critical RPM.
- **If your controller dies, the fans freeze** at their last duty — they do not fall back
  to automatic. Always release the bypass on exit.

## 4.2 The commands

| Purpose | Command | Reply / notes |
| --- | --- | --- |
| **Suspend the automatic loop** | `ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x01` | no data; global; not readable |
| **Resume the automatic loop** | `ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x00` | automatic control returns within ~1 s |
| **Set duty, zone *z*** | `ipmitool $BMC raw 0x30 0x70 0x66 0x01 <z> <duty%>` | `<z>` 0-based; duty `0x05`–`0x64`, clamped outside that |
| **Read duty, zone *z*** | `ipmitool $BMC raw 0x30 0x70 0x66 0x00 <z>` | 1 byte, duty % |
| Get base fan mode | `ipmitool $BMC raw 0x30 0x45 0x00` | 1 byte, mode value |
| Get supported-mode mask | `ipmitool $BMC raw 0x30 0x45 0x02` | 1 byte: **bit _n_ set = mode _n_ settable** |
| Set base fan mode | `ipmitool $BMC raw 0x30 0x45 0x01 <mode>` | persistent; rejects an unsupported mode |
| Get fan curves | `ipmitool $BMC raw 0x30 0x45 0x03` | `3 × N` bytes, N curve triplets |
| Read RPM of a fan | `ipmitool $BMC raw 0x04 0x2d <sensorNum>` | standard Get Sensor Reading |

### Error codes per command

| Command | Success | Errors |
| --- | --- | --- |
| `0x30 0x70 0x66 0x02 <0\|1>` | no data | `0xC7` if the value byte is missing |
| `0x30 0x70 0x66 0x01 <zone> <duty>` | no data | `0xD4` under System Lockdown; `0xC7` if a byte is missing; `0xCC` for an out-of-range zone **on boards that validate the zone** (Part 5) |
| `0x30 0x70 0x66 0x00 <zone>` | 1 byte | `0xC7` if the zone byte is missing |
| `0x30 0x45 0x01 <mode>` | no data | `0xCC` for a mode this board does not support |
| `0x30 0x45 <op>` with op > `0x04` | — | `0xCC` |

### Base fan mode values

Read the supported-mode mask first — bit *n* set means mode *n* is settable:

```bash
ipmitool $BMC raw 0x30 0x45 0x02
```

A reply of `17` is `0b0001_0111`, meaning modes 0, 1, 2 and 4. Typical numbering:

| Value | Mode |
| --- | --- |
| `0x00` | Standard |
| `0x01` | Full Speed (all fans 100 %) |
| `0x02` | Optimal |
| `0x04` | Heavy IO |

Unlike the OpenBMC stack, this firmware **rejects** an unsupported mode rather than
accepting it silently, so the mask and reality agree.

## 4.3 Procedure

**Step 1 — read the base fan mode.** It is your fallback whenever the bypass is lost.

```bash
ipmitool $BMC raw 0x30 0x45 0x00
ipmitool $BMC raw 0x30 0x45 0x02
```

Change it only if you want a different fallback curve. 🔴 Do not choose Full Speed: the
mode is persistent and the bypass is not.

**Step 2 — suspend the automatic loop.**

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x01
```

Nothing moves yet. If this returns `0xD4`, System Lockdown is enabled — turn it off first.

**Step 3 — set the duty.** Zone 0-based, duty 5–100.

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x1e   # zone 0, 30%
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x32   # zone 0, 50%
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x64   # zone 0, 100%
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x01 0x32   # zone 1, 50%
```

🔴 Keep every fan above its Lower Critical RPM. Step the duty down gradually while
watching RPM rather than jumping to a low value.

**Step 4 — verify.** Wait 5–10 s.

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00   # duty of zone 0
ipmitool $BMC raw 0x04 0x2d 0x41             # RPM of FAN1
ipmitool $BMC sdr elist full | grep -i fan   # every fan at once
```

**Step 5 — release when done.**

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x00
```

One command covers every zone. There is no need to restore the previous duty — the
automatic loop overwrites it on its next tick.

**Emergency exit.** Releasing the bypass is the safe move, because automatic control is a
working thermal loop:

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x00   # 1. back to automatic
ipmitool $BMC raw 0x30 0x45 0x01 0x01        # 2. only if still needed: Full Speed
ipmitool $BMC raw 0x30 0x45 0x01 0x02        # 3. afterwards, restore a sane mode
```

Step 2 is persistent, so step 3 matters.

## 4.4 Reading duty back, and checking the bypass

The read returns the actual current PWM value, which is also what the automatic loop
writes. That makes it the only way to tell whether the bypass is still in effect.

```
$ ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00
 31
```

`31` hex is 49 decimal — the read-back of a 50 % write, one count low. Do not read the
byte as decimal.

**On the H14 boards the read-back is exactly predictable.** The firmware clamps the value,
converts it to an 8-bit PWM value and back, truncating both divisions:

```
expect(d):  d   = clamp(d, 5, 100)
            pwm = (d * 255) / 100      # integer division
            return (pwm * 100) / 255   # integer division
```

So `50 → 127 → 49`, `20 → 51 → 20`, `100 → 255 → 100`, and `0 → 12 → 4`. The result is
exact at 20, 40, 60, 80 and 100, and exactly 1 low everywhere else — never more than 1 off.
Two consequences:

- 🔴 **On the H14 boards `0x00` does not stop the fans.** Anything below 5 % is clamped to
  5 %, which reads back as 4. There is no "fans off" value.
- **Values above 100 are clamped, not rejected.** `0x78` (120) is accepted and gives 100 %.

🔴 **This formula is not valid on every board in Part 4.** It describes the AST2600
hardware monitor that the H14 boards use. The **X14SDW / X14SDV** firmware carries a
**second duty path** that stores the percentage itself and reads it back **exactly**, with
no truncation and no 5 % clamp. A configuration byte picks the path when the BMC starts, so
the board name does not tell you which one you have.

🔴 **Never send a duty of 0 on X14SDW / X14SDV.** The 5 % floor above belongs to the PWM
path. The percent path has no floor, so `0x00` may reach the fans as a real 0 %. Use the
lowest duty that keeps every fan above its Lower Critical RPM (Part 5).

**Calibrate your own board once.** Write a duty that is not a multiple of 20 and read it
back:

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x01        # bypass ON
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x32   # zone 0 -> 50%
sleep 3
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00        # -> 31 = 1 low, 32 = exact
```

Keep that answer. It is the value your control loop must compare against (4.5).

**To spot-check the bypass by hand**, write a duty, wait about 3 s, and read it back:

| Read-back | Meaning |
| --- | --- |
| your value, or 1 low | the bypass is in effect |
| a different value that keeps changing | the bypass is off; the automatic loop has the fans |
| pinned at `64` when you asked for less | a fan-failure trip, not a lost bypass |

Nudge by about 5 % rather than a large jump, so the fans barely move if the bypass turns
out to be off, and write your original value back afterwards.

## 4.5 Holding a duty unattended

Because the bypass cannot be read, the loop watches the **duty** instead, on one
assumption: **you are the only thing writing fan duty**. Any value that is not the one you
wrote means the automatic loop resumed.

**State the loop keeps**

| | |
| --- | --- |
| `ZONES` | every zone on the board — a zone you do not drive sits frozen, not automatic |
| `want[zone]` | the byte your board returns for that duty — from the calibration in 4.4, **not** the duty you sent |
| `pinned` | consecutive passes a zone has read 100 % without being asked to |

**Before the loop**

1. Read one zone's duty. Nothing back means this BMC has no `0x66` command; stop.
2. Arm the bypass with `0x66 0x02 0x01`. Nothing moves yet.
3. Register a cleanup that releases the bypass on **every** exit path.

**The loop**

```
loop forever:

    for each zone:                          # A. check who owns the fans
        got = READ_DUTY(zone)
        if got is nothing:
            lost = true                     #    BMC busy, rebooting, unreachable
        else if got != want[zone]:
            lost = true                     #    the automatic loop resumed
            if got == 100: fanfail = true   #    100% we did not ask for

    if lost:                                # B. take them back
        ARM_BYPASS
        pinned = fanfail ? pinned + 1 : 0
        if pinned >= 3: warn("fan failure - re-arming cannot win")

    duty = compute_duty()                   # C. drive this pass
    for each zone:
        WRITE_DUTY(zone, duty)
        want[zone] = readback_of(duty)      # measured once - see 4.4

    sleep PERIOD                            # D. wait
```

**A — verify.** One read per zone, **before** this pass's write. Reading straight after
your own write returns your own value regardless of the bypass, because the automatic loop
needs about a second to overwrite; reading at the top of the next pass covers a full period
of exposure. The `fanfail` test does not detect the loss — `got != want` already did — it
only labels the cause.

**B — recover.** Re-arm the bypass only; step C writes a fresh duty immediately, so there
is nothing to restore. A duty pinned at 100 that you did not ask for is a fan-failure trip
on the boards where fan-fail outranks the bypass: re-arming will never win it back, and the
fix is the failed fan.

**C — drive.** Keep the computed duty within 5–100. Below 5 the firmware clamps to 5 and
reports 4, which the comparison would read as a takeover on every pass.

**D — wait.** `PERIOD` bounds your exposure: after a BMC restart the fans run on the
automatic curve for at most one period. A pass costs two commands per zone, so 10–30 s is
comfortable.

For a fixed duty, the same loop applies with a constant. Simpler still, drop the read and
send the bypass followed by the duty on every pass — the same two commands, recovering in
the same one period, but without ever telling you that a takeover happened.

## 4.6 Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Duty write accepted but fans do not change | wrong zone number — several boards do not validate it | map the zones by writing 100 % to each in turn and watching RPM (Part 5) |
| Fans move, then drift back within a second | the bypass was never set, or was cleared | send `0x66 0x02 0x01`, then re-write the duty |
| Read-back is 1 lower than what you wrote | this board stores an 8-bit PWM value | expected on H14; compute it with `expect()` (4.4) |
| Read-back is exactly what you wrote | this board stores the percentage | also correct — calibrate and use that value (4.4) |
| Duty of 0 does not stop the fans; read-back says 4 | the PWM path clamps anything below 5 % | expected on H14; there is no "off" duty, so use the lowest safe value |
| 🔴 Duty of 0 on X14SDW / X14SDV | the percent path has **no** 5 % floor, so `0x00` may mean a real 0 % | do not send it; keep every fan above its Lower Critical RPM |
| Fans revert to automatic after a reboot | the bypass never persists | run the control loop (4.5) |
| Board comes back at 100 % after a reboot | the base fan mode was left at Full Speed, and the mode does persist | set a sane base mode |
| Fans stuck at 100 %, duty writes ignored | a fan-failure trip | fix the fan; keep manual duty above the Lower Critical RPM |
| Duty write returns `0xD4` | System Lockdown is enabled | disable it in the web UI |
| A command returns `0xC7` | wrong byte count | `0x66 0x01` takes zone and duty; `0x66 0x00` and `0x66 0x02` take exactly one byte |
| Set-mode returns `0xCC` | the board does not support that mode | read the mask with `0x30 0x45 0x02` |
| Every `0x30 0x70 0x66` command returns `0xCC`, while `0x30 0x45` works | this firmware build does not implement the fan-duty sub-command | nothing in Part 4 applies on this build; the base fan mode is the only fan control available |
| Every zone read returns the same byte | normal — duty reads do not discriminate between zones | identify zones by writing and watching RPM, never by reading |

---
# Part 5 — Board reference

Fan sensor numbers and zone layouts are board-specific. Always confirm the sensor numbers
on your own unit with `ipmitool $BMC sdr elist full | grep -i fan`; the tables below are a
starting point, not a substitute.

## 5.1 OpenBMC boards

**Fan sensor numbers**

| Board | Fans | Sensor numbers |
| --- | --- | --- |
| X14SBW-F / X14SBW-TF | 6 | FAN1–FAN6 = `0x41`–`0x46` |
| X14SBI-F / X14SBI-TF | 7 | FAN1–FAN5 = `0x41`–`0x45`, FANA = `0x46`, FANB = `0x47` |
| X14DBI-SP / X14DBI-T | 8 | FAN1–FAN6 = `0x41`–`0x46`, FANA = `0x47`, FANB = `0x48` |
| X14DBG-AP | 11 | FAN1–FAN10 = `0x41`–`0x4A`, FAN11_STBY = `0x4B` |
| X14SRG-TF | 8 | FAN1–FAN3 = `0x41`–`0x43`, FANA = `0x44`, FANC = `0x45`, FANB = `0x46`, FAND = `0x47`, FAN1A = `0x48` |
| X14SAE-F | 7 | FAN1 = `0x41`, FAN1A = `0x42`, FANA = `0x43`, FAN2 = `0x44`, FAN3 = `0x45`, FAN3C = `0x46`, FAN2B = `0x47` |

**Zones** — which fans one duty write moves.

⚠️ **The zone names below are 1-based**, matching the manual-mode commands. The duty
command counts from 0, so "zone 2" in this table is `0x01` in
`raw 0x30 0x70 0x66 0x01 <z> <duty%>` (3.3).

| Board / mode | Zones | Zone contents |
| --- | --- | --- |
| Standard, FullSpeed, HeavyIO on boards without a specific fan table | 1 | all fans together |
| X14DBI-SP / -T | 2 | zone 1 = FAN1–FAN6 · zone 2 = FANA, FANB |
| X14SBI-F / -TF | 2 | zone 1 = FAN1–FAN5 · zone 2 = FANA, FANB |
| X14DBG-AP (10-fan) | 2 | zone 1 = FAN1–FAN5 · zone 2 = FAN6–FAN10 |
| X14SRG-TF (Performance) | 4 | z1 = FAN1–FAN3 · z2 = FANA, FANC · z3 = FANB, FAND · z4 = FAN1A |
| X14SAE-F (FullSpeed, Performance, Silent — all three the same) | 5 | z1 = FAN2, FAN3 · z2 = FANA · z3 = FAN3C, FAN2B · z4 = FAN1 · z5 = FAN1A |

🔴 **The X14SAE-F row is written in the labels `ipmitool` prints.** Its firmware zone
tables spell the same five zones as FAN4+FAN5, FAN3, FAN6+FAN7, FAN1 and FAN2. Those are
tach node names, not sensor labels. If you read a Supermicro fan table straight from the
firmware, translate it through the sensor numbers first.

To find the zone count on a board not listed, probe the manual flag upward and watch for
the first error:

```bash
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x01     # zone 1 (manual commands: 1-based)
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x02     # zone 2 …
```

Existing zones answer `00`/`01`; missing zones return an error.

## 5.2 ATEN boards

**Fan sensor numbers**

| Board | Fans | Sensor numbers |
| --- | --- | --- |
| H14DSG-O-CPU | 11 | FAN1–FAN10 = `0x41`–`0x4A`, FANSTBY = `0x4B` (usually no reading) |
| X14SDW / X14SDV | 6 | FAN1–FAN6 = `0x41`–`0x46` |

**Zones.** On this stack zones are named by the byte you send — zone 0 is `0x00` — and
there is only one zone-taking command, so there is no second numbering to confuse it with.

| Board | Zones | Zone contents |
| --- | --- | --- |
| H14DSG-O-CPU | 2 | zone 0 = FAN1–FAN5 · zone 1 = FAN6–FAN10 |
| X14SDW / X14SDV | validated against a runtime zone count | probe upward; an out-of-range zone returns `0xCC` |

There is no command that reports the zone layout, and duty reads do not discriminate
between zones — on some boards every zone byte returns the same value. Map zones by
writing:

```bash
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x01        # bypass ON
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x64   # zone 0 -> 100%
sleep 10
ipmitool $BMC sdr elist full | grep -i fan        # whichever fans changed are zone 0
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x01 0x64   # repeat for zone 1, 2, …
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x00        # release
```

**Per-board behaviour that changes what you should do**

| Board | Zone byte validated? | Fan failure versus the bypass |
| --- | --- | --- |
| H14 boards (H14DSG-O-CPU, H14SRV-HLN4F, …) | **No** — a bad zone is accepted silently and does nothing | 🔴 Fan failure is checked **first** and forces 100 %; the bypass cannot override it |
| X14SDW / X14SDV | Yes — out of range returns `0xCC` | The bypass is checked first, so it holds through a fan failure |

**Fan RPM thresholds** — the numbers a manual duty must stay above. Read them from your
own board with `ipmitool $BMC sensor | grep -i fan`; static values from firmware do not
always match what a unit reports.

| Board | Lower non-recoverable | Lower critical | Lower non-critical |
| --- | --- | --- | --- |
| H14DSG-O-CPU | — | 420 RPM (280 on FAN1) | — |
| X14SDW / X14SDV | 280 | 420 | 560 |

---

# Quick reference

**OpenBMC**

```bash
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x01        # is this stack? -> 00/01
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 0x01 0x01   # manual ON, zone 1 (1-based)
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x32             # set duty 50%, zone 1 (0-based)
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00                  # read duty, zone 1 (0-based)
ipmitool $BMC raw 0x30 0x70 0x88 0x41                       # read duty + temp of FAN1
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x01 0x01 0x00   # manual OFF, zone 1
```

**ATEN**

```bash
ipmitool $BMC raw 0x2e 0x04 0xcf 0xc2 0x00 0x00 0x01        # is this stack? -> 0xC1
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x01                  # bypass ON (all zones)
ipmitool $BMC raw 0x30 0x70 0x66 0x01 0x00 0x32             # duty 50%, zone 0
ipmitool $BMC raw 0x30 0x70 0x66 0x00 0x00                  # read duty, zone 0
ipmitool $BMC raw 0x30 0x70 0x66 0x02 0x00                  # bypass OFF
```

**Both**

```bash
ipmitool $BMC raw 0x30 0x45 0x00                            # get base fan mode
ipmitool $BMC raw 0x04 0x2d 0x41                            # RPM of FAN1
ipmitool $BMC sdr elist full | grep -i fan                  # all fans
ipmitool $BMC sensor | grep -i fan                          # all fans with thresholds
```
