# Development

> For an overview of the internal structure (classes, execution order, shared IPMI zones, etc.) see [ARCHITECTURE.md](https://github.com/petersulyok/smfc/blob/main/ARCHITECTURE.md).

## Development environment setup

### Manual installation and use of `uv`

This project is using `uv` for Python project management, see more details about [installation of `uv`](https://docs.astral.sh/uv/getting-started/installation/).
`uv` can provide everything that multiple tools (e.g. `pip`, `pyenv`, `venv`) provide, but much faster.

Manual building a development environment from scratch (with Python 3.14) contains the following steps:

```commandline
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/petersulyok/smfc.git
uv python install 3.14
uv python pin 3.14
uv sync
source .venv/bin/activate
```

> `uv` has a lock file (`uv.lock`) for storing dependencies, this should be part of version control.

### Dependencies

Dependencies are listed in `pyproject.toml` file and the proper version numbers are handled by `uv`:

```ini
dependencies = [
    "pyudev"
]

[dependency-groups]
dev = [
    "build",
    "coverage",
    "mock",
    "pytest",
    "pytest-cov",
    "pytest-mock",
    "twine"
]

lint = [
    "ruff",
    "pylint"
]
```

### Automated installation of development environment

All the steps above (installing `uv`, Python, and dependencies) can be automated with the `./bin/create_python_env.sh` script:

```commandline
./bin/create_python_env.sh 3.14
```

## Linting

The code can be checked with `pylint` and `ruff`:

```commandline
pylint src test
ruff check
```

## Local development and deployment

To install a development build of `smfc` onto the local system (real
`/etc/smfc`, real systemd unit), two steps are required: build a distribution
archive from the current source tree, then install it.

### Build a local package

The project uses `setuptools` as the build backend (declared in
`pyproject.toml`); `uv build` is the recommended front-end for producing the
distribution artifacts. From the project root:

```commandline
uv build
```

This produces both a source distribution and a wheel under `./dist/`:

```
dist/smfc-<version>.tar.gz   ← source distribution (consumed by ./bin/install.sh)
dist/smfc-<version>-py3-none-any.whl
```

The version number is read from the `version = "..."` field in
`pyproject.toml`. Bump it with [`./bin/update_version_number.sh X.Y.Z`](https://github.com/petersulyok/smfc/blob/main/bin/update_version_number.sh)
when you want a distinct local build, otherwise the existing version is reused.

### Local system install

After the source distribution (`dist/smfc-<version>.tar.gz`) has been built, install it onto the local machine with the
[`./bin/install.sh`](https://github.com/petersulyok/smfc/blob/main/bin/install.sh) wrapper:

```commandline
sudo ./bin/install.sh --local --keep-config --verbose
```

What it does:

- Reads the version from `./pyproject.toml` and runs
  `pip install ./dist/smfc-<version>.tar.gz`.
- Drops [`config/smfc.conf`](https://github.com/petersulyok/smfc/blob/main/config/smfc.conf) into `/etc/smfc/`, with the
  existing one backed up as `/etc/smfc/smfc.conf.<timestamp>` (unless
  `--keep-config` is passed).
- Installs [`config/smfc`](https://github.com/petersulyok/smfc/blob/main/config/smfc) into `/etc/default/`.
- Installs [`config/smfc.service`](https://github.com/petersulyok/smfc/blob/main/config/smfc.service) as a systemd unit at
  `/etc/systemd/system/smfc.service`.
- Installs the man pages from `doc/`.

Then start the service:

```commandline
sudo systemctl daemon-reload
sudo systemctl enable --now smfc
sudo journalctl -fu smfc
```

Reverse the install with [`./bin/uninstall.sh`](https://github.com/petersulyok/smfc/blob/main/bin/uninstall.sh) (the same
`--keep-config` flag is supported).

# Testing

All test-related material — unit tests, smoke tests, the scenario matrix,
shared infrastructure, and how to invoke each layer — lives in
[`TESTING.md`](https://github.com/petersulyok/smfc/blob/main/TESTING.md).

# GitHub

## GitHub workflow

The project implemented the following GitHub workflows:

1. Unit test and lint execution (`test.yml`). A commit can trigger this action:
   * executes unit test on `ubuntu-latest` OS and on Python versions `3.10`, `3.11`, `3.12`, `3.13`, `3.14`
   * executes `pylint` and `ruff`
   * generates coverage data and upload it to [codecov.io](https://codecov.io/)

2. Publish Python distribution packages to PyPI (`publish.yml`). A published release triggers this action:
   * build distribution package on Python `3.14`
   * upload the new package to PyPI

3. Build and publish DEB / RPM packages (`packages.yml`). A published release triggers this action:
   * build DEB package on `debian:trixie`
   * build RPM package on `fedora:latest`
   * upload both packages as CI artifacts (90-day retention) and attach them to the GitHub release as assets
   * dispatch a `package-published` event to [`smfc-deb`](https://github.com/petersulyok/smfc-deb) and [`smfc-rpm`](https://github.com/petersulyok/smfc-rpm), which then republish the packages into their signed APT and DNF repositories on GitHub Pages (see [`ARCHITECTURE.md` chapter 15](https://github.com/petersulyok/smfc/blob/main/ARCHITECTURE.md#15-release-and-distribution))


# Release process

## Creation of a new GitHub release

Follow these steps to create a new release:

* Run `./bin/update_version_number.sh X.Y.Z` to update the version number in all release-specific files
  (`pyproject.toml`, `doc/smfc.1`, `smfc.spec`, `debian/changelog`, `uv.lock`)
* Update the changelog entries in `smfc.spec` and `debian/changelog` with the actual release notes
* Commit all changes
* Run unit tests with `pytest`, and correct all errors
* Run linters `pylint` and `ruff`, and correct all warnings
* Update CHANGELOG.md with the new release information
* Commit all changes and test again
* Create a new release on GitHub with the same version number, and the new package will be published on PyPI automatically. DEB and RPM packages will be built automatically by the `packages.yml` workflow.
* Build new images for docker and upload them

## Building and uploading of Docker images

After publishing an `smfc` release, the docker image could be built and uploaded. 
The docker images can be built locally in the project root folder:

```commandline
./docker/docker-build.sh 4.1.0 latest
```
Notes:
- Please note that the dockerfile will install `smfc` from `pypi.org`, so the version must refer an official `smfc` release.
- The build script will generate the following tags: `4.1.0`, `latest`, `4.1.0-nvidia`, `latest-nvidia`, `4.1.0-amd`, `latest-amd`.

The generated docker images can be uploaded to [hub.docker.com](https://hub.docker.com/r/petersulyok/smfc)
in the following way:

```commandline
./docker/docker-push.sh 4.1.0 latest
```

This pushes all three image variants (`4.1.0`, `4.1.0-nvidia`, `4.1.0-amd`) and their secondary tags (`latest`, `latest-nvidia`, `latest-amd`) in a single call.

> Written with [StackEdit](https://stackedit.io/).
