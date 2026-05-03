#!/usr/bin/env python3
#
#   test_platform.py (C) 2025-2026, Samuel Dowling, Peter Sulyok
#   Unit tests for smfc.platform module (create_platform).
#
from mock import MagicMock
from smfc.platform import PlatformName
from smfc.platform_factory import create_platform
from smfc.generic import GenericPlatform
from smfc.genericx9 import GenericX9Platform
from smfc.x10qbi import X10QBi


class TestCreatePlatform:
    """Unit test class for create_platform() factory function."""

    def test_create_genericx9(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - call create_platform() with 'genericx9' platform name
        - ASSERT: if the returned platform is not a GenericX9Platform instance
        - ASSERT: if the platform name is different from expected
        """
        mock_exec = MagicMock()
        platform = create_platform(PlatformName.GENERIC_X9, mock_exec)
        assert isinstance(platform, GenericX9Platform)
        assert platform.name == PlatformName.GENERIC_X9

    def test_create_x10qbi(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - call create_platform() with 'X10QBi' platform name
        - ASSERT: if the returned platform is not an X10QBi instance
        - ASSERT: if the platform name is different from expected
        """
        mock_exec = MagicMock()
        platform = create_platform(PlatformName.X10QBI, mock_exec)
        assert isinstance(platform, X10QBi)
        assert platform.name == PlatformName.X10QBI

    def test_create_generic_explicit(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - call create_platform() with 'generic' platform name
        - ASSERT: if the returned platform is not a GenericPlatform instance
        - ASSERT: if the platform name is 'generic'
        """
        mock_exec = MagicMock()
        platform = create_platform(PlatformName.GENERIC, mock_exec)
        assert isinstance(platform, GenericPlatform)
        assert platform.name == PlatformName.GENERIC

    def test_create_generic_fallback(self) -> None:
        """Positive unit test for create_platform() function. It contains the following steps:
        - call create_platform() with an unknown platform name (BMC product name)
        - ASSERT: if the returned platform is not a GenericPlatform instance
        - ASSERT: if the platform name is different from expected
        """
        mock_exec = MagicMock()
        platform = create_platform("X11SCH-LN4F", mock_exec)
        assert isinstance(platform, GenericPlatform)
        assert platform.name == "X11SCH-LN4F"


# End.
