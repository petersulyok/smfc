#!/usr/bin/env bash
#
#   install.sh (C) 2021-2026, Peter Sulyok
#   Installation script for `smfc` service.
#
set -e


function print_help() {
  echo "usage: $(basename $0) [-h|--help] [-k|--keep-config] [-l|--local] [-v|--verbose]"
  echo "           -h, --help         help text"
  echo "           -k, --keep-config  keep original configuration file"
  echo "           -l, --local        installation from a local git repository"
  echo "           -v, --verbose      verbose output"

  exit 0
}


function verbose_echo() {
  if [ -n "${VERBOSE}" ]; then
    echo "$1"
  fi
}


function new_configuration() {
  # Install a new configuration file (if the old one should not be preserved)
  if [ -z "${KEEP_CONFIG}" ]; then
    # Backup the old existing configuration file.
    if [ -f /etc/smfc/smfc.conf ]; then
      cp /etc/smfc/smfc.conf /etc/smfc/smfc.conf.$POST_TAG
      verbose_echo "Original configuration file saved (/etc/smfc/smfc.conf.$POST_TAG)."
    fi
    # Execute installation command (parameter)
    $1
    verbose_echo "New configuration file installed (/etc/smfc/smfc.conf)."
  fi
}


function fail() {
  echo "$(basename $0): Error - $1" >&2
  exit 1
}


# Everything smfc installs by hand lives here. A distribution package owns /usr; this tree belongs to
# smfc, so an upgrade knows exactly what to remove and pip never writes into a directory the package
# manager manages.
SMFC_HOME="/opt/smfc"
SMFC_VENV="$SMFC_HOME/venv"

# Postfix extension for backup files.
POST_TAG=$(date +%4Y%m%d_%H%M%S)

# Parsing of command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      print_help
      ;;
    -k|--keep-config)
      KEEP_CONFIG="yes"
      shift # past value
      ;;
    -l|--local)
      LOCAL_INSTALL="yes"
      shift # past value
      ;;
    -v|--verbose)
      VERBOSE="yes"
      shift # past value
      ;;
    *)
      # Unknown option
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Must be executed with root privileges.
if [[ $EUID -ne 0 ]]; then
  echo "$(basename $0): Error - must be executed with root privileges!"
  exit 1
fi
verbose_echo "Root privilege granted."

# A restart is owed only to a service that is already running, and the state has to be read before
# anything is changed. This is the rule of the packages: dh_installsystemd restarts after an upgrade,
# and %systemd_postun_with_restart touches a running unit only. A service the user stopped on purpose
# stays stopped.
SMFC_WAS_RUNNING=""
if command -v systemctl > /dev/null 2>&1; then
  if systemctl is-active --quiet smfc.service 2>/dev/null; then
    SMFC_WAS_RUNNING="yes"
    verbose_echo "smfc.service is running, it will be restarted at the end."
  fi
fi

# Create the configuration target folder if it does not exist.
if [ ! -d /etc/smfc ]; then
  mkdir -p /etc/smfc
  verbose_echo "/etc/smfc folder created."
fi
# Create the target folder for manual page.
if [ ! -d /usr/share/man/man1 ]; then
  mkdir -p /usr/share/man/man1
  verbose_echo "/usr/share/man/man1 folder created."
fi
# PIP parameters inside the virtual environment. No --break-system-packages: nothing here touches the
# Python of the distribution.
PIP_PARAM="-q --root-user-action=ignore"

# Test what the installation needs, before anything is changed. A failure here leaves the machine
# exactly as it was, with its fan control still running.
if ! python3 -m venv --help > /dev/null 2>&1; then
  fail "python3 -m venv is not available. Install it first: apt install python3-venv (Debian, Ubuntu)."
fi
verbose_echo "python3 -m venv is available."

# Build the environment from scratch, so a first install and a fifth end the same way. It is isolated:
# pip brings pyudev with smfc, so no package of the distribution is needed first. pyudev is pure
# Python and reaches libudev through ctypes at run time; that library comes with udev, which any
# machine running smfc has, and the check further down proves it rather than assuming it.
rm -rf "$SMFC_VENV"
python3 -m venv "$SMFC_VENV" || fail "cannot create $SMFC_VENV."
verbose_echo "Virtual environment created ($SMFC_VENV)."

# CASE 1: Local installation from the current folder.
if [ "$LOCAL_INSTALL" = "yes" ]; then

  # Display the installation type.
  verbose_echo "Local installation from current folder."

  # Read smfc version from the current folder.
  SMFC_VERSION=$(sed -n 's/^version\s*=\s*["\x27]\([^"\x27]*\)["\x27].*/\1/p' ./pyproject.toml)
  verbose_echo "smfc version: $SMFC_VERSION."

  # Install smfc package from `./dist` folder
  "$SMFC_VENV/bin/pip" install $PIP_PARAM "./dist/smfc-$SMFC_VERSION.tar.gz" || \
    fail "cannot install ./dist/smfc-$SMFC_VERSION.tar.gz."
  verbose_echo "pip installed smfc==$SMFC_VERSION."

  # Install configuration file.
  new_configuration "cp ./config/smfc.conf /etc/smfc/smfc.conf"

  # Install smfc files.
  if [ -z "${KEEP_CONFIG}" ] || [ ! -f /etc/default/smfc ]; then
    cp -f ./config/smfc /etc/default/smfc
    verbose_echo "New default file installed (/etc/default/smfc)."
  else
    verbose_echo "Existing default file preserved (/etc/default/smfc)."
  fi
  cp -f ./config/smfc.service /etc/systemd/system/smfc.service
  cp -f ./doc/smfc.1 /usr/local/share/man/man1/smfc.1
  cp -f ./doc/smfc-client.1 /usr/local/share/man/man1/smfc-client.1
  cp -f ./doc/smfc-config.1 /usr/local/share/man/man1/smfc-config.1

# CASE 2: Remote installation from GitHub and pypi.
else

  # Display the installation type.
  verbose_echo "Remote installation from GitHub."

  # Read the latest smfc version from PyPI.
  SMFC_VERSION=$("$SMFC_VENV/bin/pip" index versions smfc 2>/dev/null | head -1 | sed 's/.*(\(.*\))/\1/')
  verbose_echo "smfc version from PyPI: $SMFC_VERSION"

  # GitHub URL (tag-based).
  GITHUB_URL="https://raw.githubusercontent.com/petersulyok/smfc/refs/tags/v$SMFC_VERSION"

  # Install smfc package from Pypi.org
  "$SMFC_VENV/bin/pip" install $PIP_PARAM smfc==$SMFC_VERSION || \
    fail "cannot install smfc==$SMFC_VERSION from PyPI."
  verbose_echo "pip installed smfc==$SMFC_VERSION."

  # Install configuration file.
  new_configuration "curl --silent -o /etc/smfc/smfc.conf $GITHUB_URL/config/smfc.conf"

  # Install smfc files.
  if [ -z "${KEEP_CONFIG}" ] || [ ! -f /etc/default/smfc ]; then
    curl --silent -o "/etc/default/smfc" "$GITHUB_URL/config/smfc"
    verbose_echo "New default file installed (/etc/default/smfc)."
  else
    verbose_echo "Existing default file preserved (/etc/default/smfc)."
  fi
  curl --silent -o "/etc/systemd/system/smfc.service" "$GITHUB_URL/config/smfc.service"
  curl --silent -o "/usr/local/share/man/man1/smfc.1" "$GITHUB_URL/doc/smfc.1"
  curl --silent -o "/usr/local/share/man/man1/smfc-client.1" "$GITHUB_URL/doc/smfc-client.1"
  curl --silent -o "/usr/local/share/man/man1/smfc-config.1" "$GITHUB_URL/doc/smfc-config.1"

fi

# The new installation has to work before the old one is removed. If anything above failed, the
# machine still has the installation it had, and its fans are still being regulated.
"$SMFC_VENV/bin/smfc" --version > /dev/null || fail "$SMFC_VENV/bin/smfc does not run."
"$SMFC_VENV/bin/python" -c "import pyudev; pyudev.Context()" > /dev/null 2>&1 || \
  fail "pyudev cannot reach the libudev library. Install it first: apt install libudev1 (Debian, Ubuntu), dnf install systemd-libs (Fedora)."
verbose_echo "smfc $SMFC_VERSION runs in $SMFC_VENV."

# Remove a previous installation from the Python of the distribution. Where that landed depends on
# the distribution, so the interpreter is asked where it found smfc rather than a path being guessed.
if python3 -c "import smfc" > /dev/null 2>&1; then
  OLD_LOCATION=$(python3 -c "import smfc, pathlib; print(pathlib.Path(smfc.__file__).parent)")
  # A package manager may own those files. Removing them with pip would leave dpkg or rpm believing
  # that files exist which are gone, so the script stops instead and names the right tool.
  # The name of the package is taken from the answer, not guessed: the AUR recipe, the DEB and the
  # RPM need not carry the same name. An AUR package installed with yay is a pacman package too, so
  # pacman -Qo finds it and pacman -R removes it.
  OLD_PACKAGE=""
  OLD_TOOL=""
  if command -v dpkg > /dev/null 2>&1; then
    OLD_PACKAGE=$(dpkg -S "$OLD_LOCATION" 2>/dev/null | head -1 | cut -d: -f1)
    OLD_TOOL="apt remove"
  fi
  if [ -z "$OLD_PACKAGE" ] && command -v rpm > /dev/null 2>&1; then
    OLD_PACKAGE=$(rpm -qf --queryformat '%{NAME}' "$OLD_LOCATION" 2>/dev/null || true)
    OLD_TOOL="dnf remove"
  fi
  if [ -z "$OLD_PACKAGE" ] && command -v pacman > /dev/null 2>&1; then
    OLD_PACKAGE=$(pacman -Qo "$OLD_LOCATION" 2>/dev/null | awk '{print $(NF-1)}')
    OLD_TOOL="pacman -R"
  fi
  if [ -n "$OLD_PACKAGE" ]; then
    fail "smfc is installed by your package manager, as the package '$OLD_PACKAGE'. Remove it first: $OLD_TOOL $OLD_PACKAGE."
  fi
  python3 -m pip uninstall -y -q --root-user-action=ignore --break-system-packages smfc \
    > /dev/null 2>&1 || true
  verbose_echo "Previous installation removed ($OLD_LOCATION)."
fi

# Name the commands where a user expects them. /usr/local/bin belongs to software installed by hand,
# which is exactly what this script does.
ln -sf "$SMFC_VENV/bin/smfc"        /usr/local/bin/smfc
ln -sf "$SMFC_VENV/bin/smfc-client" /usr/local/bin/smfc-client
ln -sf "$SMFC_VENV/bin/smfc-config" /usr/local/bin/smfc-config
verbose_echo "smfc, smfc-client and smfc-config are linked into /usr/local/bin."

# Compress manual pages.
gzip -f /usr/local/share/man/man1/smfc.1
gzip -f /usr/local/share/man/man1/smfc-client.1
gzip -f /usr/local/share/man/man1/smfc-config.1
mandb > /dev/null 2>&1
chown root:root \
  /etc/smfc/smfc.conf \
  /etc/default/smfc \
  /etc/systemd/system/smfc.service \
  /usr/local/share/man/man1/smfc.1.gz \
  /usr/local/share/man/man1/smfc-client.1.gz \
  /usr/local/share/man/man1/smfc-config.1.gz
verbose_echo "smfc files have been installed."

# Collect the disk names for the `hd_names=` and `nvme_names=` parameters in 'smfc.conf'.
# smfc.discover owns the filters and the write format, and it fills a key only while that key is
# still empty. The DEB and the RPM scripts call the same module.
if [ -z "${KEEP_CONFIG}" ]; then
  "$SMFC_VENV/bin/python" -m smfc.discover hd --fill /etc/smfc/smfc.conf || \
    echo "smfc: disk auto-detection skipped (smfc.discover could not run)" >&2
  "$SMFC_VENV/bin/python" -m smfc.discover nvme --fill /etc/smfc/smfc.conf || \
    echo "smfc: disk auto-detection skipped (smfc.discover could not run)" >&2
  verbose_echo "Disk names are listed in the new configuration file (please edit!)."
fi

# systemd has to read the unit file again, because this script has just written it. Without the
# reload a changed service definition is ignored until the next boot. The restart comes last, so the
# service starts with the configuration file and the disk names this run produced.
if command -v systemctl > /dev/null 2>&1; then
  systemctl daemon-reload || true
  verbose_echo "systemd configuration reloaded."
  if [ -n "$SMFC_WAS_RUNNING" ]; then
    systemctl restart smfc.service || \
      echo "smfc: the service did not restart, check 'systemctl status smfc.service'" >&2
    verbose_echo "smfc.service restarted with the new version."
  fi
fi

verbose_echo "smfc installation finished successfully."
