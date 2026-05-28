# Plan: smfc-client — read-only state snapshot CLI

> **Status: implemented** on `feature/smfc-client`. See
> [src/smfc/client.py](src/smfc/client.py),
> [test/test_client.py](test/test_client.py), and the `[project.scripts]`
> entry in [pyproject.toml](pyproject.toml). The IPC integration with a
> running smfc service (the `Source: online` / `Source: offline` header)
> lands as part of [CLIENT_SERVER.md](CLIENT_SERVER.md) — until that plan
> is implemented, smfc-client always uses the standalone path and does
> not print a `Source:` line.

## Context

`smfc` runs as a systemd service that controls Supermicro server fans via IPMI.
Today the only way to inspect what the service "sees" — current temperatures,
applied fan levels, IPMI fan mode, HDD standby states — is to grep through
syslog. Users on the discussion thread keep asking for a quick way to verify
their config is doing the right thing.

This plan adds a separate console script, `smfc-client`, that prints a one-shot
snapshot of the live state by reading IPMI / hwmon / smartctl directly, using
the same configuration file as the service. It does not require `smfc` to be
running and does not modify fan state. It is fully decoupled — no IPC added to
the service.

## Design choices (locked in with user)

- Read independently — no IPC into the running smfc service.
- One-shot text output, no live refresh, pipeable.
- New `console_script` named `smfc-client`.
- No new third-party dependencies (no `rich`, no `textual`).

## Approach

Reuse the existing `Config`, `Ipmi`, and fan-controller classes by instantiating
them in a passive way:

1. `Config(path)` — pure parser, already side-effect-free. No change.
2. `Ipmi(...)` — currently has two side effects we need to neutralize:
   - It loops up to **120 s** waiting for the BMC. Awful UX for a CLI.
   - It calls `self.platform.set_fan_manual_mode()` on init, which mutates
     fan mode if the service isn't running.
   Add two keyword-only args to `Ipmi.__init__`:
   - `in_client: bool = False` — when `True`, skip `set_fan_manual_mode()`.
   - `bmc_init_timeout: float = BMC_INIT_TIMEOUT` — override the 120 s default
     (client passes 5 s; pass 0 to disable retries).
   Default behavior is unchanged; existing callers and tests are not affected.
3. Fan-controller classes (`CpuFc`, `HdFc`, `NvmeFc`, `GpuFc`, `ConstFc`) —
   their `__init__` only reads temperatures, never sets fan levels. Safe to
   instantiate. Each constructor is wrapped in `try/except` so a missing
   device shows as a per-controller `ERROR` row instead of crashing the report.
4. Use `Log(LOG_NONE, LOG_STDERR)` so the `LOG_CONFIG` chatter from
   `Ipmi.__init__` and each controller's `__init__` is suppressed —
   `Log.msg_to_stdout` already short-circuits on `LOG_NONE`.

For the report itself: read fresh values just-in-time —
`fc.get_temp()` for temperatures, `ipmi.get_fan_level(zone)` for IPMI zone
levels, `hdfc.check_standby_state()` for the standby section. No dependency
on `last_temp` (which is `0` right after `__init__`).

### Why not factor out an `IpmiReader` class?

Considered and rejected. It would touch every `Ipmi` consumer and require
updating ~14 ipmi tests. The keyword-only `in_client` param keeps the change
surgical: one branch, one new test, zero risk to the service path.

## Files to change

### New: `src/smfc/client.py`

- `main(argv=None) -> int` — entry point.
- `_parse_args(argv)` — argparse with `-c CONFIG`, `-s` (sudo), `--no-color`, `-v`.
- `_build_silent_log()` — `Log(LOG_NONE, LOG_STDERR)`.
- `_construct_controllers(log, cfg, ipmi, udevc, sudo)` — iterates
  `cfg.cpu/hd/nvme/gpu/const`, instantiates only those with `enabled=True`,
  catches construction exceptions per-controller. Returns
  `List[Tuple[section_name, controller_or_None, error_or_None]]`.
  - Constructor signatures (verified): `CpuFc(log, udevc, ipmi, cfg)`,
    `HdFc(log, udevc, ipmi, cfg, sudo)`, `NvmeFc(log, udevc, ipmi, cfg)`,
    `GpuFc(log, ipmi, cfg)`, `ConstFc(log, ipmi, cfg)`.
  - `udevc = pyudev.Context()` — created once, shared across controllers
    that need it.
- `_format_report(ipmi, controllers, no_color)` — pure formatter, returns
  the full string. Sections: BMC info, IPMI fan mode, controllers table,
  IPMI zones (live), Standby Guard (conditional).
- Exit codes: `0` ok, `6` config error, `8` ipmi error (with stderr hint
  suggesting `sudo smfc-client -s`), `9` udev error.

### Modify: `src/smfc/ipmi.py`

Add two keyword-only params to `Ipmi.__init__`:

```python
def __init__(self, log: Log, cfg: IpmiConfig, sudo: bool, *,
             in_client: bool = False,
             bmc_init_timeout: float = BMC_INIT_TIMEOUT) -> None:
```

- The retry loop uses `bmc_init_timeout` directly (the default
  `BMC_INIT_TIMEOUT` preserves the previous 120 s behavior; client passes 5 s,
  `0` disables retries).
- Wrap `self.platform.set_fan_manual_mode()` in `if not in_client:`.

No other behavior change. All existing callers (`Service.run` and tests)
keep using positional args and the defaults.

### Modify: `pyproject.toml`

Add to `[project.scripts]`:

```toml
smfc-client = "smfc.client:main"
```

### New: `test/test_client.py`

Tests, mirroring patterns in `test/test_cmd.py` and `test/test_service.py`:

1. Happy path — real `Config(test/cpu_2.conf)`, mocked `Ipmi`, assert exit 0
   and key sections in stdout.
2. Missing config file → exit 6, stderr contains `config`.
3. `Ipmi.__init__` raises `RuntimeError("ipmitool error...")` → exit 8,
   stderr contains the sudo hint.
4. One controller `__init__` raises (e.g., `HdFc` raises `ValueError` when a
   disk path can't be resolved) → other rows still render, that row shows
   `ERROR`, exit code 0.
5. Standby Guard section present when `standby_guard_enabled=true and count>1`,
   absent otherwise.
6. `get_fan_mode` returns `STANDARD` (i.e., smfc not running) → output shows
   `STANDARD`, no warning, no error.
7. `sys.stdout.isatty()` False → no `\x1b[` ANSI sequences in output.
8. `ConstFc` row renders with temp `-` and configured target level.

### Modify: `test/test_ipmi.py`

Two regression tests:

- `in_client=True` → `set_fan_manual_mode` not called.
- `bmc_init_timeout=0.1` → BMC-not-ready loop exits within ~0.1 s rather than
  120 s (use a mock `_exec_ipmitool` that always raises `RuntimeError("ipmitool ...")`).

## Command-line interface

Flags follow the existing `smfc` service ([cmd.py](src/smfc/cmd.py)) so users
who already know the service can use the client without re-learning. `-c` and
`-s` reuse the service's semantics.

| Flag      | Long form       | Argument | Default               | Description                                                                       |
| --------- | --------------- | -------- | --------------------- | --------------------------------------------------------------------------------- |
| `-c FILE` | `--config FILE` | path     | `/etc/smfc/smfc.conf` | smfc configuration file. Same format the service uses.                            |
| `-s`      | `--sudo`        | —        | off                   | Run `ipmitool` and `smartctl` via `sudo`. Required when invoking as a non-root user. |
| `-nc`     | `--no-color`    | —        | auto (off when piped) | Disable ANSI colors. Colors auto-disable when stdout is not a TTY anyway.         |
| `-h`      | `--help`        | —        | —                     | Show help and exit.                                                               |
| `-v`      | `--version`     | —        | —                     | Print `smfc-client X.Y.Z` and exit.                                               |

### Exit codes

| Code | Meaning                                                              |
| ---- | -------------------------------------------------------------------- |
| 0    | Snapshot printed successfully (per-controller errors are non-fatal). |
| 6    | Configuration file missing or invalid.                               |
| 8    | IPMI/BMC error (e.g., `ipmitool` not found, permission denied).      |
| 9    | udev / pyudev unavailable.                                           |

### Help text

```
usage: smfc-client [-h] [-c FILE] [-s] [-nc] [-v]

Print a one-shot snapshot of smfc-managed fans and temperatures.

options:
  -h, --help            show this help message and exit
  -c FILE, --config FILE
                        configuration file (default: /etc/smfc/smfc.conf)
  -s, --sudo            run ipmitool and smartctl with sudo
  -nc, --no-color       disable ANSI colors in output
  -v, --version         show program version and exit

Exit codes: 0=ok  6=config error  8=ipmi error  9=udev error
```

## Output format (≤80 cols)

```
Source: offline (smfc service not running)
smfc-client 5.4.0  (config: /etc/smfc/smfc.conf)

BMC
  Manufacturer  : Super Micro Computer Inc. (10876)
  Product       : X11SCH-LN4F (6929)
  Firmware      : 1.74
  IPMI version  : 2.0
  Platform      : X11SCH-LN4F (GenericPlatform)

IPMI fan mode   : FULL (1)

Controllers
  Section   Type    Zones   Devices  Temp     Level   Status
  --------  ------  ------  -------  -------  ------  ----------
  CPU       cpu     [0]     1         42.3 C   45 %   ok
  HD        hd      [1]     4         34.1 C   55 %   ok
  NVME      nvme    [1]     2         48.5 C   55 %   ok
  CONST:0   const   [2]     -         -        50 %   ok (target)
  GPU       gpu     [3]     -        ERROR: nvidia-smi not found

IPMI zones (live)
  Zone   Level
  -----  -----
  0       45 %
  1       55 %
  2       50 %

Standby Guard ([HD], standby_hd_limit=1)
  /dev/sda  ACTIVE
  /dev/sdb  ACTIVE
  /dev/sdc  STANDBY
  /dev/sdd  STANDBY
  Array state: AASS  (2/4 standby)
```

Notes:
- The first line declares the data source: `Source: offline (smfc service not
  running)` for the standalone path implemented here, or `Source: online (via
  smfc service)` for the IPC path added by [CLIENT_SERVER.md](CLIENT_SERVER.md).
  Easy to grep, easy to scan; printed before the banner so it's the first
  thing the user reads.
- The "IPMI zones (live)" table queries the **union of zones** across all
  successfully-constructed controllers (avoids probing zones the platform
  doesn't have).
- Standby Guard section is emitted only when at least one HD controller has
  `standby_guard_enabled=True and count>1`. Always guard the read with
  `getattr(hdfc, "standby_array_states", None)` — the attribute is only set
  when standby is enabled (see [hdfc.py:75](src/smfc/hdfc.py#L75)).
- ANSI colors: green for `ok` and `ACTIVE`, red for `ERROR`, dim for
  placeholders, `STANDBY`, and the `(target)` annotation, bold for section
  headers and the program banner. Auto-disabled when stdout is not a TTY or
  `--no-color` is passed.

### Colorized rendering (illustrative)

The `[bold]`, `[green]`, `[red]`, `[dim]` markers below are **documentation
placeholders only** — they are not part of the implementation. The actual
client emits raw ANSI escape sequences directly (no `rich`, no `textual`
dependency):

| Effect    | ANSI sequence | Reset      |
| --------- | ------------- | ---------- |
| Bold      | `\x1b[1m`     | `\x1b[0m`  |
| Dim       | `\x1b[2m`     | `\x1b[0m`  |
| Green     | `\x1b[32m`    | `\x1b[0m`  |
| Red       | `\x1b[31m`    | `\x1b[0m`  |
| Reset all | `\x1b[0m`     | —          |

So `[green]ok[/green]` in the sample below maps to `\x1b[32mok\x1b[0m` in
real output. Roughly six string constants in `client.py`.

```
[dim]Source: offline (smfc service not running)[/dim]
[bold]smfc-client 5.4.0[/bold]  [dim](config: /etc/smfc/smfc.conf)[/dim]

[bold]BMC[/bold]
  Manufacturer  : Super Micro Computer Inc. (10876)
  Product       : X11SCH-LN4F (6929)
  ...

IPMI fan mode   : [green]FULL[/green] (1)

[bold]Controllers[/bold]
  Section   Type    Zones   Devices  Temp     Level   Status
  --------  ------  ------  -------  -------  ------  ----------
  CPU       cpu     [0]     1         42.3 C   45 %   [green]ok[/green]
  HD        hd      [1]     4         34.1 C   55 %   [green]ok[/green]
  CONST:0   const   [2]     -         -        50 %   [dim]ok (target)[/dim]
  GPU       gpu     [3]     -        [red]ERROR: nvidia-smi not found[/red]

[bold]Standby Guard[/bold] ([HD], standby_hd_limit=1)
  /dev/sda  [green]ACTIVE[/green]
  /dev/sdc  [dim]STANDBY[/dim]
  Array state: AASS  (2/4 standby)
```

## Files / line references

- New: [src/smfc/client.py](src/smfc/client.py)
- Modify: [src/smfc/ipmi.py:49](src/smfc/ipmi.py#L49) (signature),
  [ipmi.py:86](src/smfc/ipmi.py#L86) (timeout),
  [ipmi.py:114](src/smfc/ipmi.py#L114) (set_fan_manual_mode guard)
- Modify: [pyproject.toml](pyproject.toml) — `[project.scripts]`
- New: [test/test_client.py](test/test_client.py)
- Modify: [test/test_ipmi.py](test/test_ipmi.py) — two new tests

Reused functions / classes (no modification):
- [Config](src/smfc/config.py) — `Config(path)` parser
- [FanController.get_temp](src/smfc/fancontroller.py#L136)
- [HdFc.check_standby_state](src/smfc/hdfc.py#L218),
  [HdFc.get_standby_state_str](src/smfc/hdfc.py#L204)
- [Ipmi.get_fan_mode](src/smfc/ipmi.py#L170),
  [Ipmi.get_fan_mode_name](src/smfc/ipmi.py#L181),
  [Ipmi.get_fan_level](src/smfc/ipmi.py#L249)
- [Log.LOG_NONE](src/smfc/log.py)

## Implementation order

1. Modify `Ipmi.__init__` with the two new kwargs; add the two new tests in
   `test_ipmi.py`. Run `pytest test/test_ipmi.py` — existing tests should
   stay green.
2. Add `src/smfc/client.py`.
3. Add the `smfc-client` line to `pyproject.toml`.
4. Add `test/test_client.py`.
5. Run the full `pytest` suite.

## Verification

End-to-end checks:

- `pytest` — all existing tests still pass; new tests pass.
- `pip install -e .` then `smfc-client -h` prints the help screen.
- `sudo smfc-client -s -c config/samples/smfc.conf.cpu_only` (or whichever
  sample matches the dev box) prints a snapshot.
- Run while `smfc.service` is active and inactive — both should produce
  output; in the inactive case `IPMI fan mode` should reflect whatever the
  BMC currently reports rather than `FULL`.
- Trip a "controller error" path by pointing `hd_names=` at a non-existent
  disk path: that single row should show `ERROR`, the rest of the report
  should still render.

## Risks / open questions

- **`ipmitool` typically requires root.** The client errors cleanly with a
  hint to use `sudo` / `-s`. Documented; acceptable.
- **Concurrent `ipmitool` calls** with a running smfc service. Independent
  BMC requests are normally safe but I have not tested every BMC firmware.
  Documented in the help text.
- **Packaging.** `debian/control` and `smfc.spec` package the project as a
  whole; setuptools writes both console scripts into the wheel/egg from
  `[project.scripts]`. No debian/spec change needed. `bin/install.sh`
  manages config + systemd unit, doesn't reference script names.
- **Manpage.** `doc/smfc.1` is a manpage for the service. A manpage for
  `smfc-client` is out of scope here.
