%global forgeurl https://github.com/petersulyok/smfc

Version: 3.5.0

%forgemeta

Name:    smfc
Release: 1%{?dist}
Summary: Super Micro Fan Control

License: GPL-3.0-or-later
URL:	 %{forgeurl}
Source:  %{forgesource}

Requires: systemd
Requires: python3 >= 3.7
Requires: bash
Requires: ipmitool
Requires: python3-pyudev
Recommends: smartmontools
Recommends: hddtemp

BuildRequires: systemd
BuildRequires: systemd-rpm-macros
BuildArch:     noarch

%description
systemd service to control fans in CPU and HD zones with the help of IPMI on Super Micro X10-X13 (and some X9) motherboards.

%prep
%forgesetup

%build
# not needed, just copying files

%install
mkdir -p %{buildroot}/opt/smfc
install -m 755 src/smfc.py %{buildroot}/opt/smfc/smfc.py
install -m 644 src/smfc.conf %{buildroot}/opt/smfc/smfc.conf
mkdir -p %{buildroot}/%{_sysconfdir}/default
install -m 644 src/smfc %{buildroot}/%{_sysconfdir}/default/smfc
mkdir -p %{buildroot}/%{_unitdir}
install -m 644 src/smfc.service %{buildroot}/%{_unitdir}/smfc.service
mkdir -p %{buildroot}/%{_presetdir}
install -m 644 src/smfc.preset %{buildroot}/%{_presetdir}/90-smfc.preset

%check
# not needed, just copying files

%files
/opt/smfc/smfc.py
%config(noreplace) /opt/smfc/smfc.conf
%config(noreplace) /etc/default/smfc
/usr/lib/systemd/system/smfc.service
/usr/lib/systemd/system-preset/90-smfc.preset
%doc README.md
%license LICENSE

%post
%systemd_post smfc.service

%preun
%systemd_preun smfc.service

%postun
%systemd_postun_with_restart smfc.service

%changelog
* Wed Apr 03 2024 Ewout van Mansom <ewout@vanmansom.name> 3.5.0-1
- new package built with tito

