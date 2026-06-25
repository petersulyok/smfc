#!/usr/bin/env python3
#
#   test_platform_factory.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   Unit tests for smfc.platform_factory module (create_platform).
#
from mock import MagicMock
from smfc.config import PlatformName
from smfc.platform_factory import create_platform
from smfc.generic import GenericPlatform
from smfc.genericx9 import GenericX9Platform
from smfc.genericx14 import GenericX14Platform
from smfc.x10qbi import X10QBi


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

    def test_create_genericx14(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - mock Exec dependency with MagicMock
        - call `create_platform(name=PlatformName.GENERIC_X14, exec=mock_exec)`
        - ASSERT: returned platform is an instance of GenericX14Platform
        - ASSERT: returned platform's name equals PlatformName.GENERIC_X14
        """
        f = "TestCreatePlatform.test_create_genericx14"
        mock_exec = MagicMock()
        platform = create_platform(PlatformName.GENERIC_X14, mock_exec)
        assert isinstance(platform, GenericX14Platform), f"{f}: should be GenericX14Platform"
        assert platform.name == PlatformName.GENERIC_X14, f"{f}: platform name"

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
        - ASSERT: returned platform is an instance of GenericX14Platform (X14 prefix fallback)
        - ASSERT: returned platform's name equals the supplied BMC product string "X14DAi-T"
        """
        f = "TestCreatePlatform.test_create_genericx14_fallback"
        mock_exec = MagicMock()
        platform = create_platform("X14DAi-T", mock_exec)
        assert isinstance(platform, GenericX14Platform), f"{f}: should be GenericX14Platform"
        assert platform.name == "X14DAi-T", f"{f}: platform name"

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
