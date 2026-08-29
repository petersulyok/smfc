Name:           smfc
Version:        6.3.0
Release:        1%{?dist}
Summary:        Supermicro Fan Control for Linux
License:        GPL-3.0-only
URL:            https://github.com/petersulyok/smfc
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-pip
BuildRequires:  python3-wheel
BuildRequires:  systemd-rpm-macros

Requires:       python3-pyudev
Requires:       ipmitool
Recommends:     smartmontools

%description
smfc is a systemd service to control fans in Linux on Supermicro X9,
X10-X13/H10-H14, X10QBi and X14 (experimental) motherboards with
IPMI fan function.

%prep
%autosetup

%build
%pyproject_wheel

%install
%pyproject_install
install -Dm644 config/smfc.conf    %{buildroot}/etc/smfc/smfc.conf
install -Dm644 config/smfc         %{buildroot}/etc/default/smfc
install -Dm644 config/smfc.service %{buildroot}%{_unitdir}/smfc.service
install -Dm644 doc/smfc.1          %{buildroot}%{_mandir}/man1/smfc.1
install -Dm644 doc/smfc-client.1   %{buildroot}%{_mandir}/man1/smfc-client.1
install -d %{buildroot}%{_docdir}/%{name}/examples
install -m644 config/samples/*.conf %{buildroot}%{_docdir}/%{name}/examples/

%post
%systemd_post smfc.service
# Auto-detect disks on fresh install only
if [ $1 -eq 1 ]; then
    CONF_FILE="/etc/smfc/smfc.conf"
    if [ -d /dev/disk/by-id ] && grep -q '^hd_names=$' "$CONF_FILE"; then
        hd_disks=$(ls /dev/disk/by-id/ | grep -v -E '\-part|^wwn-|\-eui|nvme|^dm-|^lvm-|^md-|^zd-|_1+$' || true)
        if [ -n "$hd_disks" ]; then
            replacement=""
            first=1
            for disk in $hd_disks; do
                if [ "$first" = 1 ]; then
                    replacement="/dev/disk/by-id/${disk}"
                    first=0
                else
                    replacement="${replacement}\n\t/dev/disk/by-id/${disk}"
                fi
            done
            sed -i "s|^hd_names=$|hd_names=${replacement}|" "$CONF_FILE"
        fi
    fi
    if [ -d /dev/disk/by-id ] && grep -q '^nvme_names=$' "$CONF_FILE"; then
        nvme_disks=$(ls /dev/disk/by-id/ | grep -E '^nvme-' | grep -v -E '\-part|\-eui|\-nvme|_1+$' || true)
        if [ -n "$nvme_disks" ]; then
            replacement=""
            first=1
            for disk in $nvme_disks; do
                if [ "$first" = 1 ]; then
                    replacement="/dev/disk/by-id/${disk}"
                    first=0
                else
                    replacement="${replacement}\n\t/dev/disk/by-id/${disk}"
                fi
            done
            sed -i "s|^nvme_names=$|nvme_names=${replacement}|" "$CONF_FILE"
        fi
    fi
fi

%preun
%systemd_preun smfc.service

%postun
%systemd_postun_with_restart smfc.service

%files
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/smfc
%{_bindir}/smfc-client
%{python3_sitelib}/smfc/
%{python3_sitelib}/smfc-%{version}.dist-info/
%config(noreplace) /etc/smfc/smfc.conf
%config(noreplace) /etc/default/smfc
%{_unitdir}/smfc.service
%{_mandir}/man1/smfc.1*
%{_mandir}/man1/smfc-client.1*
%{_docdir}/%{name}/examples/

%changelog
* Sat Aug 29 2026 Peter Sulyok <peter@sulyok.net> - 6.3.0-1
- Added: new NPU fan controller (sixth controller type) that drives one or
  more IPMI zones from the temperature of Ascend NPUs, e.g. the Atlas 300I
  Duo, read with npu-smi. A device is an NPU card (npu-smi -i id); for a
  multi-chip card the hottest chip is used, and temp_calc= aggregates across
  cards. New [NPU] / [NPU:1] / ... sections with npu_device_ids=,
  npu_smi_path= and npu_smi_timeout=; all the shared parameters of the other
  temperature-driven controllers are supported. The controller shows up in
  smfc-client and the HTTP exporter like the other fan controllers.
- Added: H14 motherboard support. platform_name=generic_x14 covers both X14
  and H14 boards now. Supermicro's 14th generation ships two different BMC
  firmware types and the board name does not tell you which one you have, so
  smfc detects it at startup. On boards with the second type taking the fans
  over affects every zone, so list all of them in ipmi_zone=.
- Changed: smfc stops at startup if a configured ipmi_zone= does not exist on
  an X14/H14 board. It reads the zone count from the board and names the wrong
  zone in the error, instead of failing on a raw IPMI error code. smfc-client
  does not warn about a non-FULL fan mode there any more; it reports what is
  actually driving the fans.
- Fixed: fan control was non-functional on X14/H14 motherboards. smfc reported
  that it had taken the fans over while the BMC kept running them on its own
  curve, because the commands it sent were wrong and the fan level never
  reached the board.
- Fixed: the fans are always handed back to the BMC when smfc stops,
  exit_level=-1 included; a zone the BMC holds at 100% after a fan failure is
  reported instead of looking healthy; and min_level=0 can no longer stop the
  fans on X14/H14, where levels below 5% are raised to 5%.

* Mon Aug 24 2026 Peter Sulyok <peter@sulyok.net> - 6.2.1-1
- Fixed: the startup BMC fan subsystem readiness check did not recognize fan
  sensors whose name is not exactly FAN*. Boards reporting their fans as
  CPU_FAN1, SYS_FAN1, SYSFAN1 or CPUFAN1 (e.g. X13SAE-F) never satisfied the
  check, so they waited out the complete BMC init budget on every start. A
  sensor counts as a fan now when FAN appears anywhere in its name, which covers
  every board naming convention. A fan sensor in state ns is still not ready
  (PR #120)

* Fri Aug 14 2026 Peter Sulyok <peter@sulyok.net> - 6.2.0-1
- Fixed: the documented safe shutdown did not happen on a normal service stop.
  Fan levels were restored through an atexit handler only, and CPython does not
  run atexit callbacks on SIGTERM, the default kill signal of systemd. Nothing
  happened on systemctl stop or restart: the BMC was left in FULL mode at the
  last applied level with nothing regulating it. smfc installs a SIGTERM
  handler now (issue #118)
- Added: exit_level= parameter in the [Ipmi] section (int, [-1..100]%,
  default=100), the fan level applied to all configured IPMI zones at service
  termination. Use exit_level=-1 if smfc should not change the fan levels at
  exit. On X14 motherboards the level is applied and then manual fan control is
  released, so automatic BMC fan control is restored
- Changed: the fan mode is not set at exit any more. smfc is already running in
  FULL mode at that point, so the redundant call only added a fan_mode_delay
  long sleep to every service stop
- Deprecated: the -ne command line option. It is still accepted and still works
  (it is equivalent to exit_level=-1), but it logs a deprecation warning and it
  will be removed in 7.0.0

* Fri Jul 31 2026 Peter Sulyok <peter@sulyok.net> - 6.1.0-1
- Added: error_tolerance= parameter for the [CPU], [HD], [NVME] and [GPU]
  sections (int, default=3), the number of consecutive failed temperature reads
  tolerated per device. A transient read error does not stop smfc any more:
  while a device is inside its budget its last known good temperature is reused
  and the failure is logged at ERROR level, only an exhausted budget stops the
  service. Use error_tolerance=0 for the old behavior
- Added: smfc-client --verbose shows the per-device read error counts in a new
  Errors column, displayed only when a device has failed a read since smfc was
  started
- Added: read_errors and read_errors_total fields in the /snapshot device
  entries, plus the smfc_device_temp_read_errors gauge and
  smfc_device_temp_read_errors_total counter in /metrics
- Changed: smfc man page lists the supported motherboards (X9, X10-X13/H10-H13,
  X10QBi, X14/H14) like the README and the package description

* Sun Jul 26 2026 Peter Sulyok <peter@sulyok.net> - 6.0.1-1
- Fixed: X9 fan duty readback scaling on the generic_x9 platform; the raw
  0-255 BMC byte was reported as a percentage, so smfc-client displayed values
  like 242% for a real 95% duty cycle and CONST controllers kept re-applying
  an already-correct level
- Fixed: the same duty readback scaling issue on the X10QBi platform, where
  100% duty cycle was reported as 255%. Based on the NCT7904D datasheet and on
  the symmetry with the write path, not validated on real hardware yet
- Changed: auto platform detection now also matches BMC product names starting
  with H14 (not just X14), selecting generic_x14
- Changed: smfc-client --help and its documentation (man page, README)
  rewritten in plain, user-facing language

* Thu Jul 09 2026 Peter Sulyok <peter@sulyok.net> - 6.0.0-1
- Added: Advanced multi-segment user-defined control_function= parameter for
  arbitrary piecewise-linear fan curves
- Added: Multiple fan curve instances per controller type (e.g. [CPU] +
  [CPU:1])
- Added: smfc-client console script for a one-shot read-only snapshot of
  controllers, fan levels, IPMI zones, and standby state
- Added: signed APT and DNF repositories for direct apt/dnf install
- Added: platform support for Supermicro X14 motherboards (generic_x14),
  auto-detected from the BMC product name (experimental)
- Added: fan mode enforcement via [Ipmi] enforce_fan_mode= parameter to detect
  and restore when the BMC drifts out of FULL mode
- Added: Grafana integration with a sample dashboard and guide
  (grafana/GRAFANA.md)
- Added: install.sh auto-prefills nvme_names= with detected NVMe devices
- Added: startup log shows the active control function as a plateau list
- Changed: configuration parsing centralized in a new Config class
- Changed: ConstConfig.level validation tightened to [1..100]
- Changed: NVME polling default lowered from 10 to 2 seconds
- Changed: platform_name= value genericx9 renamed to generic_x9 (old value
  still accepted); unrecognized values rejected at config-parse time
- Changed: installation docs reorganized, DEB/RPM repository installs now
  the preferred path
- Changed: DEB/RPM packages now enable (but do not start) the smfc systemd
  unit on install
- Fixed: cold-boot race where fans could be pinned at 100% on low-polling
  zones after a full power cycle; smfc now waits for live sensor data
  before applying any fan level at startup

* Thu Apr 30 2026 Peter Sulyok <peter@sulyok.net> - 5.4.0-1
- Added: AMD GPU support: gpu_type=amd enables temperature monitoring via
  rocm-smi
- Added: amd_temp_sensor= and rocm_smi_path= configuration parameters added
- Added: AMD GPU docker image (latest-amd / 5.4.0-amd) based on rocm/dev-ubuntu
- Added: Extended DEBUG level logging across all fan controllers and IPMI layer
- Added: Command line help text added to /etc/default/smfc
- Changed: Docker NVIDIA image renamed from -gpu to -nvidia suffix throughout
- Changed: docker-build.sh and docker-push.sh updated for all three image
  variants
- Changed: Alpine base image updated to 3.23.4 (Python 3.12.13-r0)
- Changed: install.sh preserves /etc/default/smfc when --keep-config is set
- Changed: Shared IPMI zone arbitration log reduced noise in steady state

* Thu Apr 02 2026 Peter Sulyok <peter@sulyok.net> - 5.3.0-1
- Added: Temperature smoothing feature (smoothing= parameter) for CPU, HD,
  NVME, GPU controllers
- Changed: Removed pointless catch-and-re-raise exception handling
- Changed: Renamed "Super Micro" to "Supermicro" across the project
- Changed: Updated references section in README.md
- Fixed: Shared IPMI zone arbitration logging for CONST fan controller
- Fixed: Non-shared zones double IPMI calls and logging

* Mon Mar 30 2026 Peter Sulyok <peter@sulyok.net> - 5.2.0-1
- Beta support for some Supermicro X9 motherboards (platform_name=genericx9)
- Platform module refactored: split into separate modules
- X10QBi zone calculation fix: zones now use logical values (0-3)

* Sat Mar 28 2026 Peter Sulyok <peter@sulyok.net> - 5.1.2-1
- New ./bin/update_version_number.sh script created
- DEB and RPM artifact names configured correctly
- Release process updated in DEVELOPMENT.md

* Sat Mar 28 2026 Peter Sulyok <peter@sulyok.net> - 5.1.1-1
- DEB and RPM package creation: version numbers updated, RPM GitHub workflow
  fixed
- Release process updated in DEVELOPMENT.md

* Sat Mar 28 2026 Peter Sulyok <peter@sulyok.net> - 5.1.0-1
- Platform abstraction for multiple Supermicro motherboards (PR #97)
- New platform_name= configuration parameter (auto, generic, X10QBi)
- BMC information retrieved and logged during IPMI initialization
- DEB and RPM package creation added

* Wed Mar 04 2026 Peter Sulyok <peter@sulyok.net> - 5.0.0-1
- Shared IPMI zones: multiple fan controllers can share an IPMI zone
- New NVMe fan controller added
- Python 3.14 support added
- Fan controller section names refactored (zone tags removed)
- Logging changed to IPMI zone oriented way