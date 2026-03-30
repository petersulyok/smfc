Name:           smfc
Version:        5.2.0
Release:        1%{?dist}
Summary:        Super Micro Fan Control for Linux
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
smfc is a systemd service to control fans in Linux on Super Micro
X10-X13/H10-H13 motherboards with IPMI fan function.

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
        nvme_disks=$(ls /dev/disk/by-id/ | grep -E '^nvme-' | grep -v -E '\-part|\-eui|_1+$' || true)
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
%{python3_sitelib}/smfc/
%{python3_sitelib}/smfc-%{version}.dist-info/
%config(noreplace) /etc/smfc/smfc.conf
%config(noreplace) /etc/default/smfc
%{_unitdir}/smfc.service
%{_mandir}/man1/smfc.1*
%{_docdir}/%{name}/examples/

%changelog
* Mon Mar 30 2026 Peter Sulyok <peter@sulyok.net> - 5.2.0-1
- UPDATE WITH RELEASE NOTES

* Sat Mar 28 2026 Peter Sulyok <peter@sulyok.net> - 5.1.2-1
- New ./bin/update_version_number.sh script created
- DEB and RPM artifact names configured correctly
- Release process updated in DEVELOPMENT.md

* Sat Mar 28 2026 Peter Sulyok <peter@sulyok.net> - 5.1.1-1
- DEB and RPM package creation: version numbers updated, RPM GitHub workflow fixed
- Release process updated in DEVELOPMENT.md

* Sat Mar 28 2026 Peter Sulyok <peter@sulyok.net> - 5.1.0-1
- Platform abstraction for multiple Super Micro motherboards (PR #97)
- New platform_name= configuration parameter (auto, generic, X10QBi)
- BMC information retrieved and logged during IPMI initialization
- DEB and RPM package creation added

* Wed Mar 04 2026 Peter Sulyok <peter@sulyok.net> - 5.0.0-1
- Shared IPMI zones: multiple fan controllers can share an IPMI zone
- New NVMe fan controller added
- Python 3.14 support added
- Fan controller section names refactored (zone tags removed)
- Logging changed to IPMI zone oriented way