#!/usr/bin/env python3
#
#   test_checks.py (C) 2026, Peter Sulyok
#   Unit test for smfc.checks module.
#
import os
from pathlib import Path
from typing import List
import pytest
from smfc.checks import (CPU_MODULES, CheckResult, Level, check_all, check_by_section, check_cpu,
                         check_gpu, check_hd, check_ipmi, check_npu, error_text, errors,
                         loaded_modules, probe_all, probe_gpu, probe_hd, probe_ipmi, probe_nvme,
                         run_probe)
from smfc.config import Config


# Module lists used by the tests.
ALL_MODULES: str = "coretemp 1 - Live 0x0\ndrivetemp 1 - Live 0x0\n"
NO_MODULES: str = "usbcore 1 - Live 0x0\n"


def _write_config(tmp_path: Path, body: str) -> Config:
    """Write a configuration file and parse it.
    Args:
        tmp_path (Path): pytest temporary directory
        body (str): content of the configuration file
    Returns:
        Config: the parsed configuration
    """
    path = tmp_path / "test.conf"
    path.write_text(body, encoding="utf-8")
    return Config(str(path))


def _command(tmp_path: Path, name: str) -> Path:
    """Create an executable file that stands in for an external command.
    Args:
        tmp_path (Path): pytest temporary directory
        name (str): file name of the command
    Returns:
        Path: path of the created file
    """
    path = tmp_path / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


class TestChecks:
    """Unit test class for the smfc.checks module."""

    def test_loaded_modules_reads_the_file(self, tmp_path: Path) -> None:
        """Positive unit test for loaded_modules(). It contains the following steps:
        - write a file that stands in for /proc/modules
        - call loaded_modules() with that path
        - ASSERT: the raw content of the file is returned
        """
        path = tmp_path / "modules"
        path.write_text(ALL_MODULES, encoding="utf-8")
        assert loaded_modules(str(path)) == ALL_MODULES

    def test_ipmi_command_present(self, tmp_path: Path) -> None:
        """Positive unit test for check_ipmi(). It contains the following steps:
        - build a configuration whose ipmitool command exists
        - call check_ipmi()
        - ASSERT: it reports no finding
        """
        cmd = _command(tmp_path, "ipmitool")
        cfg = _write_config(tmp_path, f"[Ipmi]\ncommand={cmd}\n")
        assert not check_ipmi(cfg.ipmi)

    def test_ipmi_command_missing(self, tmp_path: Path) -> None:
        """Negative unit test for check_ipmi(). It contains the following steps:
        - build a configuration whose ipmitool command does not exist
        - call check_ipmi()
        - ASSERT: exactly one finding is reported
        - ASSERT: the finding is an error, because smfc cannot drive the fans without it
        - ASSERT: it belongs to the [Ipmi] section and names the missing path
        - ASSERT: it carries a fix line the user can act on
        """
        cfg = _write_config(tmp_path, f"[Ipmi]\ncommand={tmp_path}/nosuch\n")
        results = check_ipmi(cfg.ipmi)
        assert len(results) == 1
        assert results[0].level is Level.ERROR
        assert results[0].section == Config.CS_IPMI
        assert "nosuch" in results[0].message
        assert results[0].fix

    @pytest.mark.parametrize("module", list(CPU_MODULES))
    def test_cpu_module_loaded(self, tmp_path: Path, module: str) -> None:
        """Positive unit test for check_cpu(). It contains the following steps:
        - build a configuration with the CPU fan controller enabled
        - call check_cpu() with a module list holding coretemp, then one holding k10temp
        - ASSERT: either module satisfies the check on its own
        """
        cfg = _write_config(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\n")
        assert not check_cpu(cfg.cpu, f"{module} 1 - Live 0x0\n")

    def test_cpu_module_missing(self, tmp_path: Path) -> None:
        """Negative unit test for check_cpu(). It contains the following steps:
        - build a configuration with the CPU fan controller enabled
        - call check_cpu() with a module list holding neither coretemp nor k10temp
        - ASSERT: exactly one finding is reported, not one per instance
        - ASSERT: the finding is an error and names both accepted modules
        """
        cfg = _write_config(tmp_path, "[Ipmi]\n[CPU]\nenabled=1\n[CPU:1]\nenabled=1\nipmi_zone=1\n")
        results = check_cpu(cfg.cpu, NO_MODULES)
        assert len(results) == 1
        assert results[0].level is Level.ERROR
        assert "coretemp" in results[0].message and "k10temp" in results[0].message

    def test_cpu_disabled_section_is_skipped(self, tmp_path: Path) -> None:
        """Positive unit test for check_cpu(). It contains the following steps:
        - build a configuration with the CPU fan controller disabled
        - call check_cpu() with a module list holding neither accepted module
        - ASSERT: it reports no finding, because a disabled section needs nothing
        """
        cfg = _write_config(tmp_path, "[Ipmi]\n[CPU]\nenabled=0\n")
        assert not check_cpu(cfg.cpu, NO_MODULES)

    def test_hd_drivetemp_is_enough(self, tmp_path: Path) -> None:
        """Positive unit test for check_hd(). It contains the following steps:
        - build a configuration with the HD fan controller enabled and a missing smartctl
        - call check_hd() with a module list holding drivetemp
        - ASSERT: it reports no finding, because the module reads the temperature on its own
        """
        cfg = _write_config(tmp_path, f"[Ipmi]\n[HD]\nenabled=1\nhd_names=/dev/sda\n"
                                      f"smartctl_path={tmp_path}/nosuch\n")
        assert not check_hd(cfg.hd, ALL_MODULES)

    def test_hd_smartctl_is_enough(self, tmp_path: Path) -> None:
        """Positive unit test for check_hd(). It contains the following steps:
        - build a configuration with the HD fan controller enabled and an existing smartctl
        - call check_hd() with a module list that does not hold drivetemp
        - ASSERT: it reports no finding, because smartctl reads the temperature instead
        """
        cmd = _command(tmp_path, "smartctl")
        cfg = _write_config(tmp_path, f"[Ipmi]\n[HD]\nenabled=1\nhd_names=/dev/sda\nsmartctl_path={cmd}\n")
        assert not check_hd(cfg.hd, NO_MODULES)

    def test_hd_neither_source_available(self, tmp_path: Path) -> None:
        """Negative unit test for check_hd(). It contains the following steps:
        - build a configuration with the HD fan controller enabled and a missing smartctl
        - call check_hd() with a module list that does not hold drivetemp
        - ASSERT: one error is reported, because no temperature source is left
        - ASSERT: the message names both ways to fix it
        """
        cfg = _write_config(tmp_path, f"[Ipmi]\n[HD]\nenabled=1\nhd_names=/dev/sda\n"
                                      f"smartctl_path={tmp_path}/nosuch\n")
        results = check_hd(cfg.hd, NO_MODULES)
        assert len(results) == 1
        assert results[0].level is Level.ERROR
        assert "drivetemp" in results[0].message and "smartctl" in results[0].message

    def test_hd_standby_guard_needs_smartctl(self, tmp_path: Path) -> None:
        """Negative unit test for check_hd(). It contains the following steps:
        - build a configuration with the standby guard on and a missing smartctl
        - call check_hd() with a module list holding drivetemp
        - ASSERT: one error is reported, although drivetemp covers the temperature reading
        - ASSERT: the message names the standby guard, which needs smartctl itself
        """
        cfg = _write_config(tmp_path, f"[Ipmi]\n[HD]\nenabled=1\nhd_names=/dev/sda\n"
                                      f"smartctl_path={tmp_path}/nosuch\nstandby_guard_enabled=1\n")
        results = check_hd(cfg.hd, ALL_MODULES)
        assert len(results) == 1
        assert results[0].level is Level.ERROR
        assert "Standby Guard" in results[0].message

    def test_hd_instances_are_checked_on_their_own(self, tmp_path: Path) -> None:
        """Negative unit test for check_hd(). It contains the following steps:
        - build two HD instances, the first with a missing smartctl and the second with a working one
        - call check_hd() with a module list that does not hold drivetemp
        - ASSERT: only the first instance is reported
        - ASSERT: the finding names the section it belongs to, so the editor can place it
        """
        cmd = _command(tmp_path, "smartctl")
        cfg = _write_config(tmp_path, f"[Ipmi]\n"
                                      f"[HD]\nenabled=1\nipmi_zone=1\nhd_names=/dev/sda\n"
                                      f"smartctl_path={tmp_path}/nosuch\n"
                                      f"[HD:1]\nenabled=1\nipmi_zone=2\nhd_names=/dev/sdb\n"
                                      f"smartctl_path={cmd}\n")
        results = check_hd(cfg.hd, NO_MODULES)
        assert len(results) == 1
        assert results[0].section == "HD"

    @pytest.mark.parametrize(
        "gpu_type, present, missing",
        [
            pytest.param("nvidia", "nvidia_smi_path", "rocm_smi_path", id="nvidia"),
            pytest.param("amd", "rocm_smi_path", "nvidia_smi_path", id="amd"),
        ],
    )
    def test_gpu_checks_the_tool_of_its_type(self, tmp_path: Path, gpu_type: str, present: str,
                                             missing: str) -> None:
        """Positive unit test for check_gpu(). It contains the following steps:
        - build a GPU section whose own vendor tool exists and whose other tool does not
        - call check_gpu()
        - ASSERT: it reports no finding, because only the tool of the configured type matters
        """
        cmd = _command(tmp_path, "vendor-smi")
        cfg = _write_config(tmp_path, f"[Ipmi]\n[GPU]\nenabled=1\ngpu_type={gpu_type}\n"
                                      f"{present}={cmd}\n{missing}={tmp_path}/nosuch\n")
        assert not check_gpu(cfg.gpu)

    def test_gpu_tool_missing(self, tmp_path: Path) -> None:
        """Negative unit test for check_gpu(). It contains the following steps:
        - build a GPU section whose nvidia-smi does not exist
        - call check_gpu()
        - ASSERT: one error is reported and it names the missing path
        """
        cfg = _write_config(tmp_path, f"[Ipmi]\n[GPU]\nenabled=1\nnvidia_smi_path={tmp_path}/nosuch\n")
        results = check_gpu(cfg.gpu)
        assert len(results) == 1
        assert results[0].level is Level.ERROR
        assert "nosuch" in results[0].message

    def test_gpu_disabled_section_is_skipped(self, tmp_path: Path) -> None:
        """Positive unit test for check_gpu(). It contains the following steps:
        - build a GPU section that is disabled and names a missing tool
        - call check_gpu()
        - ASSERT: it reports no finding
        """
        cfg = _write_config(tmp_path, f"[Ipmi]\n[GPU]\nenabled=0\nnvidia_smi_path={tmp_path}/nosuch\n")
        assert not check_gpu(cfg.gpu)

    def test_npu_absolute_path(self, tmp_path: Path) -> None:
        """Positive unit test for check_npu(). It contains the following steps:
        - build an NPU section whose npu_smi_path is an absolute path that exists
        - call check_npu()
        - ASSERT: it reports no finding
        """
        cmd = _command(tmp_path, "npu-smi")
        cfg = _write_config(tmp_path, f"[Ipmi]\n[NPU]\nenabled=1\nnpu_smi_path={cmd}\n")
        assert not check_npu(cfg.npu)

    def test_npu_bare_name_is_looked_up_on_path(self, tmp_path: Path, monkeypatch) -> None:
        """Positive unit test for check_npu(). It contains the following steps:
        - build an NPU section whose npu_smi_path is a bare command name
        - put a directory holding that command on PATH
        - call check_npu()
        - ASSERT: it reports no finding, because a bare name is resolved through PATH
        """
        _command(tmp_path, "npu-smi")
        monkeypatch.setenv("PATH", str(tmp_path))
        cfg = _write_config(tmp_path, "[Ipmi]\n[NPU]\nenabled=1\nnpu_smi_path=npu-smi\n")
        assert not check_npu(cfg.npu)

    def test_npu_bare_name_not_on_path(self, tmp_path: Path, monkeypatch) -> None:
        """Negative unit test for check_npu(). It contains the following steps:
        - build an NPU section whose npu_smi_path is a bare command name
        - set PATH to a directory that does not hold that command
        - call check_npu()
        - ASSERT: one error is reported and it names the command
        """
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))
        cfg = _write_config(tmp_path, "[Ipmi]\n[NPU]\nenabled=1\nnpu_smi_path=npu-smi\n")
        results = check_npu(cfg.npu)
        assert len(results) == 1
        assert "npu-smi" in results[0].message

    def test_check_all_reports_every_section(self, tmp_path: Path) -> None:
        """Negative unit test for check_all(). It contains the following steps:
        - build a configuration where the ipmitool, the CPU module and the GPU tool are all missing
        - call check_all() with a module list holding neither accepted CPU module
        - ASSERT: three findings are reported, one per fault
        - ASSERT: they name the [Ipmi], the [CPU] and the [GPU] sections
        - ASSERT: the old behaviour of stopping at the first fault is gone
        """
        cfg = _write_config(tmp_path, f"[Ipmi]\ncommand={tmp_path}/nosuch\n"
                                      f"[CPU]\nenabled=1\n"
                                      f"[GPU]\nenabled=1\nipmi_zone=2\nnvidia_smi_path={tmp_path}/nosuch\n")
        results = check_all(cfg, NO_MODULES)
        assert len(results) == 3
        assert [r.section for r in results] == ["Ipmi", "CPU", "GPU"]

    def test_check_all_reads_the_module_list_when_it_is_not_given(self, tmp_path: Path, mocker) -> None:
        """Positive unit test for check_all(). It contains the following steps:
        - mock loaded_modules() so no real /proc/modules is read
        - call check_all() without a module list
        - ASSERT: the module list is read once from the system
        """
        mocked = mocker.patch("smfc.checks.loaded_modules", return_value=ALL_MODULES)
        cmd = _command(tmp_path, "ipmitool")
        cfg = _write_config(tmp_path, f"[Ipmi]\ncommand={cmd}\n[CPU]\nenabled=1\n")
        assert not check_all(cfg)
        mocked.assert_called_once()

    def test_check_by_section_groups_the_findings(self, tmp_path: Path) -> None:
        """Positive unit test for check_by_section(). It contains the following steps:
        - build a configuration with a fault in two different sections
        - call check_by_section()
        - ASSERT: the findings are grouped under the section they belong to
        - ASSERT: a section without a finding is absent from the result
        """
        cfg = _write_config(tmp_path, f"[Ipmi]\ncommand={tmp_path}/nosuch\n"
                                      f"[CPU]\nenabled=1\n"
                                      f"[NVME]\nenabled=0\n")
        grouped = check_by_section(cfg, NO_MODULES)
        assert sorted(grouped) == ["CPU", "Ipmi"]
        assert len(grouped["Ipmi"]) == 1
        assert "NVME" not in grouped

    def _script(self, tmp_path: Path, name: str, body: str) -> Path:
        """Create an executable file that stands in for an external command.
        Args:
            tmp_path (Path): pytest temporary directory
            name (str): file name
            body (str): the shell body of the script
        Returns:
            Path: path of the script
        """
        path = tmp_path / name
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_a_probe_reports_a_command_that_is_not_there(self, tmp_path: Path) -> None:
        """Negative unit test for run_probe(). It contains the following steps:
        - run a command that does not exist
        - ASSERT: it returns -1 and says the command cannot be found, instead of raising
        """
        code, output = run_probe([str(tmp_path / "nosuch")])
        assert code == -1
        assert "cannot be found" in output

    def test_a_probe_is_bounded_in_time(self, tmp_path: Path, monkeypatch) -> None:
        """Negative unit test for run_probe(). It contains the following steps:
        - run a command that never finishes, with the timeout lowered for the test
        - ASSERT: it returns -1 and says how long it waited
        A wedged BMC must not leave the editor with a keyboard that does not answer.
        """
        monkeypatch.setattr("smfc.checks.PROBE_TIMEOUT", 0.3)
        script = self._script(tmp_path, "hang", "sleep 30")
        code, output = run_probe([str(script)])
        assert code == -1
        assert "did not answer" in output

    def test_a_probe_runs_under_sudo_when_asked(self, tmp_path: Path, monkeypatch) -> None:
        """Positive unit test for run_probe(). It contains the following steps:
        - run a command with the sudo flag, with sudo replaced by a script that prints its arguments,
          one per line, because `echo` of the shell would eat the -n flag instead of printing it
        - ASSERT: sudo is the command, and the real one follows it
        - ASSERT: -n is passed, so sudo never asks for a password the full-screen editor cannot show
        A user without direct access to the BMC needs this, which is what -s is for.
        """
        self._script(tmp_path, "sudo", 'printf "%s\\n" "$@"')
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        code, output = run_probe(["ipmitool", "bmc", "info"], sudo=True)
        assert code == 0
        assert output.splitlines() == ["-n", "ipmitool", "bmc", "info"]

    def test_a_sudo_that_wants_a_password_says_what_to_do(self, tmp_path: Path, monkeypatch) -> None:
        """Negative unit test for run_probe(). It contains the following steps:
        - replace sudo with a script that refuses the way sudo -n refuses a user with no cached credentials
        - run a command with the sudo flag
        - ASSERT: the exit code of sudo is reported
        - ASSERT: the message names the command to run instead, because a password cannot be typed
          into a full-screen editor
        """
        self._script(tmp_path, "sudo", 'echo "sudo: a password is required" >&2\nexit 1')
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        code, output = run_probe(["ipmitool", "bmc", "info"], sudo=True)
        assert code == 1
        assert output == "sudo needs a password, which cannot be typed here; run: sudo smfc-config"

    def test_the_bmc_answers(self, tmp_path: Path) -> None:
        """Positive unit test for probe_ipmi(). It contains the following steps:
        - answer the probe with the output of a real board
        - ASSERT: one information finding is reported
        - ASSERT: it names the product the BMC reported
        """
        script = self._script(tmp_path, "ipmitool", 'echo "Product Name              : X11DPi-N"')
        cfg = _write_config(tmp_path, f"[Ipmi]\ncommand={script}\n")
        results = probe_ipmi(cfg.ipmi)
        assert len(results) == 1
        assert results[0].level is Level.INFO
        assert "X11DPi-N" in results[0].message

    def test_the_bmc_does_not_answer(self, tmp_path: Path) -> None:
        """Negative unit test for probe_ipmi(). It contains the following steps:
        - answer the probe the way ipmitool answers on a machine with no BMC
        - ASSERT: one error is reported, with the reason the tool gave
        - ASSERT: the fix line names the sudo flag, because that is the usual cause
        """
        script = self._script(tmp_path, "ipmitool", 'echo "Could not open device" >&2; exit 1')
        cfg = _write_config(tmp_path, f"[Ipmi]\ncommand={script}\n")
        results = probe_ipmi(cfg.ipmi)
        assert results[0].level is Level.ERROR
        assert "Could not open device" in results[0].message
        assert "-s" in results[0].fix

    def test_a_sleeping_disk_is_not_woken(self, tmp_path: Path) -> None:
        """Positive unit test for probe_hd(). It contains the following steps:
        - answer smartctl with the exit code it uses for a disk in standby
        - ASSERT: the disk counts as read, not as a failure
        - ASSERT: the finding says how many disks are asleep
        smartctl -n standby reports a sleeping disk instead of spinning it up.
        """
        script = self._script(tmp_path, "smartctl", "exit 2")
        disk = tmp_path / "disk"
        disk.write_text("", encoding="utf-8")
        cfg = _write_config(tmp_path, f"[Ipmi]\n[HD]\nenabled=1\nhd_names={disk}\n"
                                      f"smartctl_path={script}\n")
        results = probe_hd(cfg.hd)
        assert results[0].level is Level.INFO
        assert "1 in standby" in results[0].message

    def test_a_disk_that_is_not_present(self, tmp_path: Path) -> None:
        """Negative unit test for probe_hd(). It contains the following steps:
        - name a disk the machine does not have
        - ASSERT: a warning is reported, not an error, because smfc still starts
        - ASSERT: it names the first missing disk, so the user can find it
        """
        script = self._script(tmp_path, "smartctl", "exit 0")
        cfg = _write_config(tmp_path, f"[Ipmi]\n[HD]\nenabled=1\n"
                                      f"hd_names=/dev/disk/by-id/ata-GONE\nsmartctl_path={script}\n")
        results = probe_hd(cfg.hd)
        assert results[0].level is Level.WARN
        assert "ata-GONE" in results[0].fix

    def test_the_gpu_tool_answers_with_fewer_devices_than_configured(self, tmp_path: Path) -> None:
        """Negative unit test for probe_gpu(). It contains the following steps:
        - answer nvidia-smi with one GPU, while the section names GPU 0 and GPU 3
        - ASSERT: the tool answering is reported
        - ASSERT: a warning names the IDs that go beyond what the tool lists
        """
        script = self._script(tmp_path, "nvidia-smi", 'echo "GPU 0: NVIDIA T400"')
        cfg = _write_config(tmp_path, f"[Ipmi]\n[GPU]\nenabled=1\ngpu_device_ids=0,3\n"
                                      f"nvidia_smi_path={script}\n")
        results = probe_gpu(cfg.gpu)
        assert results[0].level is Level.INFO
        assert results[1].level is Level.WARN
        assert "[3]" in results[1].message

    def test_the_nvme_probe_needs_no_command(self, tmp_path: Path) -> None:
        """Positive unit test for probe_nvme(). It contains the following steps:
        - name one drive that exists and one that does not
        - ASSERT: a warning is reported for the missing one
        - ASSERT: no external command is needed, because the kernel publishes the temperature
        """
        drive = tmp_path / "nvme0n1"
        drive.write_text("", encoding="utf-8")
        cfg = _write_config(tmp_path, f"[Ipmi]\n[NVME]\nenabled=1\n"
                                      f"nvme_names={drive}\n\t/dev/disk/by-id/nvme-GONE\n")
        results = probe_nvme(cfg.nvme)
        assert results[0].level is Level.WARN
        assert "1 of 2" in results[0].message

    def test_a_disabled_section_is_never_probed(self, tmp_path: Path) -> None:
        """Positive unit test for probe_all(). It contains the following steps:
        - build a configuration whose HD, NVME, GPU and NPU sections are all disabled
        - ASSERT: only the BMC is probed, because a disabled section needs nothing
        """
        script = self._script(tmp_path, "ipmitool", "exit 0")
        cfg = _write_config(tmp_path, f"[Ipmi]\ncommand={script}\n[HD]\nenabled=0\n"
                                      f"[NVME]\nenabled=0\n[GPU]\nenabled=0\n[NPU]\nenabled=0\n")
        results = probe_all(cfg)
        assert [r.section for r in results] == ["Ipmi"]

    def test_errors_filters_by_severity(self) -> None:
        """Positive unit test for errors(). It contains the following steps:
        - build one finding of each severity
        - call errors()
        - ASSERT: only the error is returned, so a warning never stops the daemon
        """
        findings: List[CheckResult] = [
            CheckResult(Level.ERROR, "Ipmi", "an error"),
            CheckResult(Level.WARN, "HD", "a warning"),
            CheckResult(Level.INFO, "HD", "an observation"),
        ]
        assert errors(findings) == [findings[0]]

    def test_error_text_lists_one_finding_per_line(self) -> None:
        """Positive unit test for error_text(). It contains the following steps:
        - build two errors and one warning
        - call error_text()
        - ASSERT: both error messages appear, one per line
        - ASSERT: the warning is left out
        """
        findings: List[CheckResult] = [
            CheckResult(Level.ERROR, "Ipmi", "first error"),
            CheckResult(Level.WARN, "HD", "a warning"),
            CheckResult(Level.ERROR, "GPU", "second error"),
        ]
        assert error_text(findings) == "first error\nsecond error"

    def test_error_text_of_a_clean_run_is_empty(self) -> None:
        """Positive unit test for error_text(). It contains the following steps:
        - call error_text() with no finding at all
        - ASSERT: the result is an empty string, which is what the daemon treats as success
        """
        assert error_text([]) == ""


# End.
