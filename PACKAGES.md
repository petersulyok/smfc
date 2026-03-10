# Packages

## DEB package

### Build dependencies

```bash
sudo apt install debhelper dh-python pybuild-plugin-pyproject python3-all python3-setuptools python3-build
```

### Build commands

```bash
dpkg-buildpackage -us -uc -b
```

The `.deb` file will be created in the parent directory (`../`).

### Important notes

- The build must be executed **outside** any Python virtual environment. Deactivate it before building:
  ```bash
  deactivate
  ```
- The package installs the following files:
  - `/usr/bin/smfc` — console script
  - `/usr/lib/python3/dist-packages/smfc/` — Python package
  - `/etc/smfc/smfc.conf` — configuration file (preserved on upgrade)
  - `/etc/default/smfc` — systemd environment file (preserved on upgrade)
  - `/usr/lib/systemd/system/smfc.service` — systemd service unit
  - `/usr/share/man/man1/smfc.1.gz` — man page
  - `/usr/share/doc/smfc/examples/` — sample configuration files
- Configuration files under `/etc/` are marked as conffiles. On upgrade, `dpkg` will prompt the user if they have been modified locally.
- The `smfc.service` systemd unit is automatically enabled and started on install, stopped on removal.
- Run `lintian ../smfc_*.deb` after building to check for packaging policy violations.

### Compatible distributions

| Distribution | Version |
|-------------|---------|
| Debian | 12 (Bookworm), 13 (Trixie), Sid |
| Ubuntu | 22.04+, 24.04+ |
| Linux Mint | 21+ |
| Pop!_OS | 22.04+ |
| Raspberry Pi OS | Bookworm+ |

## RPM package

### Build dependencies

```bash
sudo dnf install rpm-build python3-devel python3-setuptools python3-pip python3-wheel python3-pyproject-rpm-macros systemd-rpm-macros
```

### Build commands

```bash
mkdir -p ~/rpmbuild/SOURCES
tar czf ~/rpmbuild/SOURCES/smfc-5.0.0.tar.gz --transform='s,^./,smfc-5.0.0/,' --exclude='.git' --exclude='.venv' .
rpmbuild -bb smfc.spec
```

The `.rpm` file will be created in `~/rpmbuild/RPMS/noarch/`.

### Important notes

- The package installs the following files:
  - `/usr/bin/smfc` — console script
  - `/usr/lib/python3.*/site-packages/smfc/` — Python package
  - `/etc/smfc/smfc.conf` — configuration file (preserved on upgrade)
  - `/etc/default/smfc` — systemd environment file (preserved on upgrade)
  - `/usr/lib/systemd/system/smfc.service` — systemd service unit
  - `/usr/share/man/man1/smfc.1.gz` — man page
  - `/usr/share/doc/smfc/examples/` — sample configuration files
- Configuration files are marked with `%config(noreplace)`. On upgrade, `rpm` will not overwrite locally modified files.
- The `smfc.service` systemd unit is automatically enabled and started on install, stopped on removal.
- The version in the `tar.gz` filename and the `--transform` path must match the `Version` field in `smfc.spec`.
- On RHEL, CentOS Stream, Rocky Linux, and AlmaLinux the [EPEL](https://docs.fedoraproject.org/en-US/epel/) repository is required for the `python3-pyudev` dependency.

### Compatible distributions

| Distribution | Version |
|-------------|---------|
| Fedora | 39+ |
| RHEL | 9+ (with EPEL) |
| CentOS Stream | 9+ (with EPEL) |
| Rocky Linux | 9+ (with EPEL) |
| AlmaLinux | 9+ (with EPEL) |