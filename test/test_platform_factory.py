#!/usr/bin/env python3
#
#   test_platform_factory.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   Unit tests for smfc.platform_factory module (create_platform).
#
import subprocess

import pytest
from mock import MagicMock
from smfc.config import PlatformName
from smfc.platform_factory import create_platform
from smfc.generic import GenericPlatform
from smfc.genericx9 import GenericX9Platform
from smfc.genericx14 import X14AtenPlatform, X14OpenBmcPlatform
from smfc.platform import IpmiError
from smfc.x10qbi import X10QBi


def openbmc_exec(flag: str = " 01") -> MagicMock:
    """An exec callback whose BMC answers the Part 1.1 stack probe with a data byte (OpenBMC)."""
    return MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout=flag, stderr=""))


def aten_exec() -> MagicMock:
    """An exec callback whose BMC answers the Part 1.1 stack probe with completion code 0xC1 (ATEN)."""
    return MagicMock(side_effect=IpmiError("ipmitool error (1): rsp=0xc1.", 0xC1))


class TestCreatePlatform:
    """Unit test class for create_platform() factory function."""

    def test_create_genericx9(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with MagicMock
        - call `create_platform(name=PlatformName.GENERIC_X9, exec=mock_exec)`
        - ASSERT: returned platform is an instance of GenericX9Platform
        - ASSERT: returned platform's name equals PlatformName.GENERIC_X9
        """
        f = "TestCreatePlatform.test_create_genericx9"
        mock_exec = MagicMock()
        platform = create_platform(PlatformName.GENERIC_X9, mock_exec)
        assert isinstance(platform, GenericX9Platform), f"{f}: should be GenericX9Platform"
        assert platform.name == PlatformName.GENERIC_X9, f"{f}: platform name"

    @pytest.mark.parametrize("flag", [" cf c2 00 01", " cf c2 00 00"], ids=["manual", "automatic"])
    def test_create_genericx14_openbmc(self, flag: str) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with a BMC answering the Part 1.1 stack probe with the OEM reply, which echoes
          the IANA ID of the command back before the flag byte: `cf c2 00 <flag>`
        - call `create_platform(name=PlatformName.GENERIC_X14, exec=mock_exec)`
        - ASSERT: the Part 1.1 stack probe was the command sent
        - ASSERT: returned platform is an instance of X14OpenBmcPlatform for both flag values - the probe
          identifies the stack, and a zone that happens to be under automatic control is still OpenBMC
        - ASSERT: returned platform's name equals PlatformName.GENERIC_X14
        """
        f = "TestCreatePlatform.test_create_genericx14_openbmc"
        mock_exec = openbmc_exec(flag)
        platform = create_platform(PlatformName.GENERIC_X14, mock_exec)
        probe = ["raw", "0x2e", "0x04", "0xcf", "0xc2", "0x00", "0x00", "0x01"]
        assert mock_exec.call_args_list[0].args[0] == probe, f"{f}: stack probe command"
        assert isinstance(platform, X14OpenBmcPlatform), f"{f}: should be X14OpenBmcPlatform"
        assert platform.name == PlatformName.GENERIC_X14, f"{f}: platform name"

    def test_create_genericx14_aten(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with a BMC answering the Part 1.1 stack probe with completion code 0xC1
        - call `create_platform(name=PlatformName.GENERIC_X14, exec=mock_exec)`
        - ASSERT: returned platform is an instance of X14AtenPlatform
        - ASSERT: returned platform is not an X14OpenBmcPlatform: 0xC1 identifies the other stack, and
          the two command sets must never be mixed (Part 1.3)
        - ASSERT: returned platform's name equals PlatformName.GENERIC_X14
        """
        f = "TestCreatePlatform.test_create_genericx14_aten"
        platform = create_platform(PlatformName.GENERIC_X14, aten_exec())
        assert isinstance(platform, X14AtenPlatform), f"{f}: should be X14AtenPlatform"
        assert not isinstance(platform, X14OpenBmcPlatform), f"{f}: must not be X14OpenBmcPlatform"
        assert platform.name == PlatformName.GENERIC_X14, f"{f}: platform name"

    @pytest.mark.parametrize("exec_fn", [
        MagicMock(side_effect=IpmiError("ipmitool error (1): Unable to establish IPMI v2 session.", None)),
        MagicMock(side_effect=IpmiError("ipmitool error (1): rsp=0xd4.", 0xD4)),
        MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout="", stderr="")),
        MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout=" zz", stderr="")),
        MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout=" 7f", stderr="")),
        MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout=" cf c2 00 7f", stderr="")),
    ])
    def test_create_genericx14_undetermined(self, exec_fn: MagicMock) -> None:
        """Negative unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with a BMC that neither returns a valid manual mode flag nor 0xC1:
          an unreachable BMC, a different completion code, an empty reply, an unparsable reply, and a flag
          byte that is neither 0x00 nor 0x01 in both the bare and the IANA-prefixed reply form
        - call `create_platform(name=PlatformName.GENERIC_X14, exec=exec_fn)`
        - ASSERT: RuntimeError is raised in all six cases - there is deliberately no fallback branch,
          because a guessed stack applies the wrong lever to the fans (Part 1.3)
        - ASSERT: the error message names the guide and its Part 1
        """
        f = "TestCreatePlatform.test_create_genericx14_undetermined"
        with pytest.raises(RuntimeError) as excinfo:
            create_platform(PlatformName.GENERIC_X14, exec_fn)
        assert "doc/X14H14_MANUAL_FANCONTROL.md, Part 1" in str(excinfo.value), f"{f}: message names the guide"

    def test_create_x10qbi(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with MagicMock
        - call `create_platform(name=PlatformName.X10QBI, exec=mock_exec)`
        - ASSERT: returned platform is an instance of X10QBi
        - ASSERT: returned platform's name equals PlatformName.X10QBI
        """
        f = "TestCreatePlatform.test_create_x10qbi"
        mock_exec = MagicMock()
        platform = create_platform(PlatformName.X10QBI, mock_exec)
        assert isinstance(platform, X10QBi), f"{f}: should be X10QBi"
        assert platform.name == PlatformName.X10QBI, f"{f}: platform name"

    def test_create_generic_explicit(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with MagicMock
        - call `create_platform(name=PlatformName.GENERIC, exec=mock_exec)`
        - ASSERT: returned platform is an instance of GenericPlatform
        - ASSERT: returned platform's name equals PlatformName.GENERIC
        """
        f = "TestCreatePlatform.test_create_generic_explicit"
        mock_exec = MagicMock()
        platform = create_platform(PlatformName.GENERIC, mock_exec)
        assert isinstance(platform, GenericPlatform), f"{f}: should be GenericPlatform"
        assert platform.name == PlatformName.GENERIC, f"{f}: platform name"

    def test_create_generic_fallback(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with MagicMock
        - call `create_platform(name="X11SCH-LN4F", exec=mock_exec)` with an unknown BMC product name
        - ASSERT: returned platform is an instance of GenericPlatform (fallback path)
        - ASSERT: returned platform's name equals the supplied BMC product string "X11SCH-LN4F"
        """
        f = "TestCreatePlatform.test_create_generic_fallback"
        mock_exec = MagicMock()
        platform = create_platform("X11SCH-LN4F", mock_exec)
        assert isinstance(platform, GenericPlatform), f"{f}: should be GenericPlatform"
        assert platform.name == "X11SCH-LN4F", f"{f}: platform name"

    def test_create_genericx9_fallback(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with MagicMock
        - call `create_platform(name="X9DRi-LN4+", exec=mock_exec)` with a BMC product name starting with X9
        - ASSERT: returned platform is an instance of GenericX9Platform (X9 prefix fallback)
        - ASSERT: returned platform's name equals the supplied BMC product string "X9DRi-LN4+"
        """
        f = "TestCreatePlatform.test_create_genericx9_fallback"
        mock_exec = MagicMock()
        platform = create_platform("X9DRi-LN4+", mock_exec)
        assert isinstance(platform, GenericX9Platform), f"{f}: should be GenericX9Platform"
        assert platform.name == "X9DRi-LN4+", f"{f}: platform name"

    def test_create_genericx14_fallback(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with MagicMock
        - call `create_platform(name="X14DAi-T", exec=mock_exec)` with a BMC product name starting with X14
        - ASSERT: returned platform is an instance of X14OpenBmcPlatform (X14 prefix -> family)
        - ASSERT: returned platform's name equals the supplied BMC product string "X14DAi-T"
        """
        f = "TestCreatePlatform.test_create_genericx14_fallback"
        platform = create_platform("X14DAi-T", openbmc_exec())
        assert isinstance(platform, X14OpenBmcPlatform), f"{f}: should be X14OpenBmcPlatform"
        assert platform.name == "X14DAi-T", f"{f}: platform name"

    def test_create_h14_aten_fallback(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with a BMC answering the Part 1.1 stack probe with completion code 0xC1
        - call `create_platform(name="H14SSL-NT", exec=mock_exec)` with a BMC product name starting with H14
        - ASSERT: returned platform is an X14AtenPlatform: an H14 board is routed into the 14th generation
          family and the probe finds the ATEN stack, which is the stack that can control its fans
        - ASSERT: returned platform's name equals the supplied BMC product string "H14SSL-NT"
        """
        f = "TestCreatePlatform.test_create_h14_aten_fallback"
        platform = create_platform("H14SSL-NT", aten_exec())
        assert isinstance(platform, X14AtenPlatform), f"{f}: should be X14AtenPlatform"
        assert platform.name == "H14SSL-NT", f"{f}: platform name"

    def test_create_h14_openbmc_fallback(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with a BMC answering the Part 1.1 stack probe with a data byte
        - call `create_platform(name="H14SHM", exec=mock_exec)`, the one H14 board running OpenBMC
        - ASSERT: returned platform is an X14OpenBmcPlatform - the stack does not follow the board
          generation, so the name prefix selects the family and only the probe selects the class
        - ASSERT: returned platform's name equals the supplied BMC product string "H14SHM"
        """
        f = "TestCreatePlatform.test_create_h14_openbmc_fallback"
        platform = create_platform("H14SHM", openbmc_exec())
        assert isinstance(platform, X14OpenBmcPlatform), f"{f}: should be X14OpenBmcPlatform"
        assert platform.name == "H14SHM", f"{f}: platform name"

    def test_create_x14_soc_is_aten(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with a BMC answering the Part 1.1 stack probe with completion code 0xC1
        - call `create_platform(name="X14SDV-4C-TP8F", exec=mock_exec)`, an X14 SoC board running ATEN
        - ASSERT: returned platform is an X14AtenPlatform, not an X14OpenBmcPlatform: an `X14` prefix
          does not imply OpenBMC, which is the bug that made these boards exit 8 at startup
        - ASSERT: returned platform's name equals the supplied BMC product string "X14SDV-4C-TP8F"
        """
        f = "TestCreatePlatform.test_create_x14_soc_is_aten"
        platform = create_platform("X14SDV-4C-TP8F", aten_exec())
        assert isinstance(platform, X14AtenPlatform), f"{f}: should be X14AtenPlatform"
        assert not isinstance(platform, X14OpenBmcPlatform), f"{f}: must not be X14OpenBmcPlatform"
        assert platform.name == "X14SDV-4C-TP8F", f"{f}: platform name"

    def test_create_x10qbi_fallback(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with MagicMock
        - call `create_platform(name="X10QBi-Series", exec=mock_exec)` with a BMC product name starting with X10QBi
        - ASSERT: returned platform is an instance of X10QBi (X10QBi prefix fallback)
        - ASSERT: returned platform's name equals the supplied BMC product string "X10QBi-Series"
        """
        f = "TestCreatePlatform.test_create_x10qbi_fallback"
        mock_exec = MagicMock()
        platform = create_platform("X10QBi-Series", mock_exec)
        assert isinstance(platform, X10QBi), f"{f}: should be X10QBi"
        assert platform.name == "X10QBi-Series", f"{f}: platform name"


# End.
