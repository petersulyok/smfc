# Plan: venv-based installation in the docker images

> Status: **proposal**, not implemented yet. Branch: `feature/docker_venv_build`.
> Target release: 6.1.0 (not a patch release, the image layout changes).

## 1. Problem

All three docker images install `smfc` system-wide with `pip`:

```dockerfile
RUN pip install --prefix=/usr smfc==${BUILD_IMAGE_VERSION}
```

A system-wide `pip install` is discouraged (and, since [PEP 668](https://peps.python.org/pep-0668/), blocked
by default) on most distros: Alpine 3.24 and Debian 13 both ship the `EXTERNALLY-MANAGED` marker. The
`--prefix=/usr` parameter is a workaround: it makes `pip` skip the marker check, because the check is only
enforced for the default installation scheme.

Findings from the current images (measured on 2026.07.26):

| Observation                                                                                          | Consequence                                     |
|------------------------------------------------------------------------------------------------------|-------------------------------------------------|
| `--prefix=/usr` lands in `/usr/local` on Debian (`posix_local` scheme), but in `/usr` on Alpine        | the same command means two different layouts    |
| `python3-pip` pulls in 76 packages in the Debian image, purged only in a *later* `RUN` layer           | the purged files still occupy space in the image |
| `apt` package lists (`/var/lib/apt/lists`, ~21 MB) are never removed                                   | dead weight in both GPU images                  |
| `pip` writes its cache (`--no-cache-dir` is not used)                                                  | extra layer content                             |
| `pyudev` is correctly reused from the distro package (`py3-udev` / `python3-pyudev`)                   | no change needed here                           |

## 2. Options considered

| Option                                                          | Verdict                                                                      |
|-----------------------------------------------------------------|------------------------------------------------------------------------------|
| A. Keep `pip install --prefix=/usr`                             | rejected: the workaround we want to remove                                    |
| B. `apt install smfc` from the [smfc-deb](https://github.com/petersulyok/smfc-deb) repository | rejected: impossible on Alpine, so two different mechanisms; also adds the APT repo + GPG key into the image and couples the image build to the GitHub Pages publish |
| C. Install the released `.deb` file (release asset)             | rejected for the same Alpine reason, but kept as a fallback idea              |
| D. **Virtual environment (`venv`) + `pip`**                     | **selected**: PEP 668 compliant by design, and identical on all three images  |

The decisive argument for D: the marker deliberately does not apply inside a virtual environment, so no
workaround parameter is needed at all, and Alpine, Debian and ROCm-Ubuntu can all use the very same
mechanism.

## 3. Target design

- The `smfc` python package is installed into a virtual environment in `/opt/smfc`.
- The venv is created with `--system-site-packages`, so the distro-provided `pyudev` package
  (`py3-udev` / `python3-pyudev`) is visible inside the venv and `pip` will not download a second copy
  from PyPI.
- `/opt/smfc/bin` is added to `PATH`, so `entrypoint.sh` (calling `smfc`) and the `smfc-client` command
  remain unchanged.
- Nothing is written into the system `site-packages` / `dist-packages` folders, so `apk` / `apt` and `pip`
  can never conflict.

### 3.1. Standard (Alpine) image

`python3` on Alpine contains `ensurepip`, so the `py3-pip` package (and the `.depends` virtual package)
is not needed anymore:

```dockerfile
RUN apk add --no-cache ipmitool python3 py3-udev smartmontools
RUN ln -s /usr/sbin/ipmitool /usr/bin/ipmitool
RUN python3 -m venv --system-site-packages /opt/smfc && \
    /opt/smfc/bin/pip install --no-cache-dir smfc==${BUILD_IMAGE_VERSION}
ENV PATH="/opt/smfc/bin:$PATH"
```

### 3.2. NVIDIA (Debian) and AMD (ROCm-Ubuntu) images

`python3-pip` is replaced by `python3-venv`, and the whole installation is executed in a single `RUN`
layer, so the removed build dependencies really disappear from the image:

```dockerfile
RUN apt update && \
    apt install -y --no-install-recommends ipmitool python3 python3-pyudev smartmontools python3-venv && \
    python3 -m venv --system-site-packages /opt/smfc && \
    /opt/smfc/bin/pip install --no-cache-dir smfc==${BUILD_IMAGE_VERSION%%-nvidia} && \
    apt autoremove --purge -y python3-venv && \
    rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/smfc/bin:$PATH"
```

(the AMD image uses `${BUILD_IMAGE_VERSION%%-amd}`)

## 4. Open questions

1. `python3-venv` package size on Debian 13 and Ubuntu 24.04 — expected to be much smaller than
   `python3-pip` (76 packages), but it has to be measured.
2. Is `pip` needed in the final image? If not, it can be removed after the installation
   (`/opt/smfc/bin/pip uninstall -y pip`, ~10 MB), or a multi-stage build can be used
   (`COPY --from=builder /opt/smfc /opt/smfc`). Multi-stage is safe here, because the builder and the
   runtime stage use the same base image, so the absolute shebangs in the venv remain valid.
3. Does `--no-install-recommends` remove anything we rely on? (`smartmontools` is listed explicitly, so
   it should be safe.)
4. Should `/opt/smfc/bin` be added to `PATH` (as above) or should `/opt/smfc/bin/smfc` be symlinked to
   `/usr/bin/smfc`? `PATH` is simpler and covers `smfc-client` too.

## 5. Validation checklist

For all three images:

- [ ] the image builds without warnings
- [ ] `docker run --rm --entrypoint sh petersulyok/smfc:test -c 'smfc --version; smfc-client --version'`
- [ ] `pyudev` is not duplicated: only one copy, coming from the distro package
- [ ] `python3 -c "import smfc"` works with the venv python
- [ ] `entrypoint.sh` starts `smfc` unchanged (no absolute path needed)
- [ ] a real container start with a sample configuration file (as in `Docker.md`)
- [ ] image size compared to the previous release:

| Image    | 6.0.1 (pip) | new (venv) | difference |
|----------|-------------|------------|------------|
| standard |             |            |            |
| nvidia   |             |            |            |
| amd      |             |            |            |

## 6. Documentation to update

- `docker/Docker.md`: component lists (mention that `smfc` is installed into `/opt/smfc`)
- `DEVELOPMENT.md`: docker build chapter
- `CHANGELOG.md`: new entry

## 7. Fallback

If the venv causes any unexpected issue, the previous `pip install --prefix=/usr` line can be restored
without touching any other file, because `entrypoint.sh` and the compose files are not affected by this
change.
