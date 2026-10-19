# Packages

This document covers **building** `.deb` and `.rpm` packages from source.

> **Just want to install smfc?** Use the signed APT and DNF repositories instead — no building required. See [README §9.1 (DEB)](https://github.com/petersulyok/smfc/blob/main/README.md#91-deb-package-installation) and [§9.2 (RPM)](https://github.com/petersulyok/smfc/blob/main/README.md#92-rpm-package-installation), or the standalone repos:
> - DEB: [petersulyok/smfc-deb](https://github.com/petersulyok/smfc-deb) — `https://petersulyok.github.io/smfc-deb/`
> - RPM: [petersulyok/smfc-rpm](https://github.com/petersulyok/smfc-rpm) — `https://petersulyok.github.io/smfc-rpm/`
>
> The instructions below are for maintainers and contributors who need to build packages locally.

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
- The `smfc.service` systemd unit is automatically enabled (but not started) on install, so the configuration can be reviewed before the service first runs; it is stopped on removal. On upgrade a running service is restarted and a stopped one is left stopped, which is why `debian/rules` passes both `--no-start` and `--restart-after-upgrade` to `dh_installsystemd`.
- Run `lintian ../smfc_*.deb` after building to check for packaging policy violations.

### Compatible distributions

| Distribution    | Version                          |
|-----------------|----------------------------------|
| Debian          | 12 (Bookworm), 13 (Trixie), Sid  |
| Ubuntu          | 24.04+                           |
| Proxmox VE      | 8+                               |
| Linux Mint      | 22+                              |
| Pop!_OS         | 24.04+                           |
| Raspberry Pi OS | Bookworm+                        |

## RPM package

### Build dependencies

```bash
sudo dnf install rpm-build python3-devel python3-setuptools python3-pip python3-wheel pyproject-rpm-macros systemd-rpm-macros
```

### Build commands

```bash
VERSION=$(grep '^Version:' smfc.spec | awk '{print $2}')
mkdir -p ~/rpmbuild/SOURCES
tar czf ~/rpmbuild/SOURCES/smfc-${VERSION}.tar.gz --transform="s,^./,smfc-${VERSION}/," --exclude='.git' --exclude='.venv' .
rpmbuild -bb smfc.spec
```

The `.rpm` file will be created in `~/rpmbuild/RPMS/noarch/`.

### Build for one target with `mock`

The release workflow builds one RPM for each target with `mock`. The same build runs locally on Fedora, as a
user in the `mock` group:

```bash
sudo dnf install mock rpm-build
rpmbuild -bs smfc.spec
mock -r alma+epel-10-x86_64 --resultdir=out --rebuild ~/rpmbuild/SRPMS/smfc-*.src.rpm
```

The source tarball must be in `~/rpmbuild/SOURCES/` first (see above). The targets of the release workflow are
`fedora-43-x86_64`, `fedora-44-x86_64` and `alma+epel-10-x86_64`. The `.rpm` file will be created in `out/`.

### Important notes

- The package installs the following files:
  - `/usr/bin/smfc` — console script
  - `/usr/lib/python3.*/site-packages/smfc/` — Python package
  - `/etc/smfc/smfc.conf` — configuration file (preserved on upgrade)
  - `/etc/default/smfc` — systemd environment file (preserved on upgrade)
  - `/usr/lib/systemd/system/smfc.service` — systemd service unit
  - `/usr/lib/systemd/system-preset/50-smfc.preset` — systemd preset (enables the unit on install)
  - `/usr/share/man/man1/smfc.1.gz` — man page
  - `/usr/share/doc/smfc/examples/` — sample configuration files
- Configuration files are marked with `%config(noreplace)`. On upgrade, `rpm` will not overwrite locally modified files.
- The `smfc.service` systemd unit is automatically enabled (but not started) on install, so the configuration can be reviewed before the service first runs; it is stopped on removal. On upgrade a running service is restarted and a stopped one is left stopped (`%systemd_postun_with_restart`).
- `%systemd_post` runs `systemctl preset`, which enables the unit only if the systemd preset policy allows it. Fedora and Enterprise Linux ship a `disable *` catch-all rule, so the package ships `/usr/lib/systemd/system-preset/50-smfc.preset` with the line `enable smfc.service`; the `50` prefix puts it ahead of the catch-all.
- The build commands above extract the version from `smfc.spec` automatically, so the tarball name always matches.
- On Enterprise Linux 10 (RHEL, AlmaLinux, Rocky Linux, CentOS Stream, Oracle Linux) the [EPEL](https://docs.fedoraproject.org/en-US/epel/) repository is required for the `python3-pyudev` dependency. For a build, `pyproject-rpm-macros` comes from the CodeReady Linux Builder (CRB) repository.

### Compatible distributions

| Distribution  | Version        | Package          |
|---------------|----------------|------------------|
| Fedora        | 43, 44         | `.fc43`, `.fc44` |
| RHEL          | 10 (with EPEL) | `.el10`          |
| AlmaLinux     | 10 (with EPEL) | `.el10`          |
| Rocky Linux   | 10 (with EPEL) | `.el10`          |
| CentOS Stream | 10 (with EPEL) | `.el10`          |
| Oracle Linux  | 10 (with EPEL) | `.el10`          |

Each Fedora release has its own package, built for its Python version. The supported Fedora releases change with the Fedora release cycle. One `.el10` package serves all Enterprise Linux 10 distributions. openSUSE is not supported, because `smfc.spec` uses Fedora macros and package names; on openSUSE, use the Docker image or the manual installation (see chapters 9.4 and 9.5 of the [README](https://github.com/petersulyok/smfc/blob/main/README.md#9-installation-and-uninstallation)).