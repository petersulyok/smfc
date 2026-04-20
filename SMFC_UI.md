# smfc-ui

A small Tkinter-based GUI for `smfc` that lets you set the IPMI fan mode,
adjust CPU/HD zone fan levels, and watch live HWMON temperatures.

## 1. System dependencies

The UI needs Tkinter (not on PyPI) and the usual `smfc` runtime tools.

On Debian/Ubuntu:
```bash
sudo apt install python3-tk ipmitool
```

> Running the GUI also requires an X11 or Wayland display (i.e. a desktop
> session). It is not usable over a headless SSH connection unless you
> forward X (`ssh -X`).

## 2. Install the Python package

From the repository root, using `uv` (recommended, matches the project's
toolchain):
```bash
uv sync
```

Or with plain `pip` (editable install):
```bash
pip install -e .
```

Either of these registers the `smfc-ui` console script.

## 3. Run the UI

After installation, just run:
```bash
smfc-ui
```

Alternative ways to launch without the console script:
```bash
# via uv
uv run python -m smfc.smfc_ui

# via module path (package must be importable)
python -m smfc.smfc_ui

# without installing, directly from the source tree
PYTHONPATH=src python3 -m smfc.smfc_ui
```

## 4. Permissions

Run the UI as your regular user, **not** as root:

- GUI access requires your X11/Wayland session (root typically cannot
  connect to the display).
- The UI constructs its `Ipmi` backend with `sudo=True`, so `ipmitool`
  invocations are elevated automatically. You will be prompted for your
  sudo password in the terminal the first time it is needed.

To avoid repeated prompts during a session, either keep the launching
terminal open or configure a passwordless sudo rule for `ipmitool`
(see your distribution's sudoers documentation).
