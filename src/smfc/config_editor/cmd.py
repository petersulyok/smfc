#
#   cmd.py (C) 2026, Peter Sulyok
#   smfc package: Supermicro fan control for Linux (home) servers.
#   smfc.config_editor.cmd: the smfc-config command.
#
import argparse
import os
import sys
from importlib.metadata import version
from typing import List, Optional

from smfc.config_editor.confwriter import is_writable
from smfc.config_editor.model import EditorModel

# Default configuration file, the same path the service unit uses.
DEFAULT_CONFIG_PATH: str = "/etc/smfc/smfc.conf"

# Exit codes. 0 is a clean exit, 6 matches the configuration error code of the service.
EXIT_OK: int = 0
EXIT_CONFIG_ERROR: int = 6

# Where a previous configuration file may be found, in the order they are offered.
BACKUP_SUFFIXES: tuple = (".rpmsave", ".dpkg-old", ".bak")


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse the command line.
    Args:
        argv (Optional[List[str]]): command line arguments (default: sys.argv[1:])
    Returns:
        argparse.Namespace: the parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="smfc-config",
        description="Create and edit the configuration file of smfc. It enables and disables the fan "
                    "controllers, checks whether the hardware each one needs is reachable, and edits "
                    "every parameter.")
    parser.add_argument("-c", "--config", action="store", dest="config_file",
                        default=DEFAULT_CONFIG_PATH, metavar="FILE",
                        help=f"configuration file to edit (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("-s", "--sudo", action="store_true", default=False,
                        help="use sudo for ipmitool/smartctl (if not run as root)")
    parser.add_argument("-v", "--version", action="version", version="%(prog)s " + version("smfc"))
    return parser.parse_args(argv)


def _backups_of(path: str) -> List[str]:
    """List the previous versions of a configuration file that are on this machine.
    `install.sh` saves the old file as `smfc.conf.<timestamp>`, and a package removal may leave
    `.rpmsave` or `.dpkg-old` beside it.
    Args:
        path (str): path of the configuration file
    Returns:
        List[str]: paths that exist, newest first
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    name = os.path.basename(path)
    found = [path + suffix for suffix in BACKUP_SUFFIXES if os.path.exists(path + suffix)]
    if os.path.isdir(directory):
        found += [os.path.join(directory, entry) for entry in os.listdir(directory)
                  if entry.startswith(name + ".") and not entry.endswith(BACKUP_SUFFIXES)]
    return sorted(set(found), key=os.path.getmtime, reverse=True)


def _report_missing(path: str) -> int:
    """Explain that the configuration file is not there, and what to do about it.
    Every install path leaves the file in place, so a missing one means it was deleted. The tool does
    not create one silently: it names the backups on this machine and the release the template comes
    from.
    Args:
        path (str): path of the configuration file
    Returns:
        int: the exit code
    """
    print(f"{path} does not exist.", file=sys.stderr)
    backups = _backups_of(path)
    if backups:
        print("\nA previous version is on this machine:", file=sys.stderr)
        for backup in backups[:5]:
            print(f"  {backup}", file=sys.stderr)
        print(f"\nRestore one of them, for example:\n  sudo cp {backups[0]} {path}", file=sys.stderr)
    else:
        release = version("smfc")
        url = (f"https://raw.githubusercontent.com/petersulyok/smfc/refs/tags/v{release}"
               f"/config/smfc.conf")
        print("\nNo previous version was found. The template of the installed release is here:",
              file=sys.stderr)
        print(f"  sudo curl -o {path} {url}", file=sys.stderr)
    return EXIT_CONFIG_ERROR


def main(argv: Optional[List[str]] = None) -> int:
    """Run smfc-config.
    Args:
        argv (Optional[List[str]]): command line arguments (default: sys.argv[1:])
    Returns:
        int: 0 on a clean exit, 6 when the configuration file cannot be opened
    """
    args = _parse_args(argv)
    path = args.config_file
    if not os.path.exists(path):
        return _report_missing(path)
    if not is_writable(path):
        print(f"read-only: {path} is not writable by this user.", file=sys.stderr)
        print("re-run as: sudo smfc-config", file=sys.stderr)
    try:
        model = EditorModel.load(path)
    except OSError as error:
        print(f"ERROR: cannot read {path}: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    # Import the terminal layer only here, so the checks above can run on a machine without a terminal.
    from smfc.config_editor.app import run  # pylint: disable=import-outside-toplevel
    return run(model)


if __name__ == "__main__":
    sys.exit(main())

# End.
