%global forgeurl https://github.com/petersulyok/smfc
%global tag smfc-3.5.0-1
%forgemeta

Name:    smfc
Version: 3.5.0
Release: 1%{?dist}
Summary: Super Micro Fan Control

License: GPL-3.0-or-later
URL:     %{forgeurl}
Source:  %{forgesource}

Requires:   ipmitool
Requires:   python3-smfc
Recommends: smartmontools
Recommends: hddtemp

BuildRequires: systemd-rpm-macros
BuildArch:     noarch

%global _description %{expand:
systemd service to control fans in CPU and HD zones with the help of IPMI on
Super Micro X10-X13 (and some X9) motherboards.}

%description %_description

%package -n python3-%{name}
Summary: Python 3 bindings for the smfc library
BuildRequires: python3-devel

%global _python_module_description %{expand:
Python 3 bindings for the smfc library.}

%description -n python3-smfc %_python_module_description

%prep
%forgesetup

%generate_buildrequires -n python3-smfc
%pyproject_buildrequires

%build -n python3-smfc
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files smfc
install -Dm 644 resources/smfc.conf %{buildroot}%{_sysconfdir}/smfc/smfc.conf
install -Dm 644 resources/smfc %{buildroot}%{_sysconfdir}/default/smfc
install -Dm 644 systemd/smfc.service %{buildroot}%{_unitdir}/smfc.service
install -Dm 644 systemd/smfc.preset %{buildroot}%{_presetdir}/90-smfc.preset
install -Dm 644 systemd/modules-load.conf %{buildroot}%{_modulesloaddir}/smfc.conf

%check -n python3-smfc
%pytest

%files
%{_bindir}/smfc
%config(noreplace) %{_sysconfdir}/smfc/smfc.conf
%config(noreplace) %{_sysconfdir}/default/smfc
%{_unitdir}/smfc.service
%{_presetdir}/90-smfc.preset
%{_modulesloaddir}/smfc.conf
%doc README.md
%license LICENSE

%files -n python3-smfc
%{python3_sitelib}/smfc/
%{python3_sitelib}/smfc-%{version}.dist-info/
%doc README.md
%license LICENSE

%post
%{_bindir}/systemctl restart systemd-modules-load.service
%systemd_post smfc.service

%preun
%systemd_preun smfc.service

%postun
%systemd_postun_with_restart smfc.service

%changelog
