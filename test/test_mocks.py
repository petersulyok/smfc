#!/usr/bin/env python3
#
#   test_mocks.py (C) 2022-2026, Peter Sulyok
#   pyudev mock classes for unit and smoke tests.
#
#   These doubles replace `pyudev.Context`, `pyudev.Device`, and `pyudev.Devices` so tests can
#   construct fan controllers without a real udev backend.
#
from typing import List
from pyudev import DeviceNotFoundByFileError


# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods
class MockDevice:
    """Mock class for pyudev.Device() class"""

    _sys_path: str

    def __init__(self, context=None, _device=None):
        pass

    def __del__(self):
        pass

    @property
    def parent(self):
        return None

    @property
    def sys_path(self):
        return self._sys_path


def factory_mockdevice():
    """Can generate MockDevice() class."""
    return MockDevice()


class MockContext:
    """Mock class for pyudev.Context() class."""

    mocked_devices: List[MockDevice]

    def __init__(self, devices=None):
        self.mocked_devices = devices

    # pylint: disable=unused-argument
    def list_devices(self, **kwargs):
        return iter(self.mocked_devices)

    # pylint: enable=unused-argument


class MockDevices:
    """Mock class for pyudev.Devices() class."""

    @classmethod
    def from_device_file(cls, context=None, filename=None):
        if filename == "raise":
            raise DeviceNotFoundByFileError()
        return MockDevice(context)


class MockedContextError:
    """Mock class for pyudev.Context() class will generate ImportError exception."""

    def __init__(self):
        raise ImportError


class MockedContextGood:
    """Mock class for pyudev.Context() class will not generate any exception."""

    def __init__(self):
        pass


# pylint: enable=missing-function-docstring
# pylint: enable=too-few-public-methods


# End.
