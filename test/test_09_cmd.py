#!/usr/bin/env python3
#
#   test_09_cmd.py (C) 2021-2025, Peter Sulyok
#   Unit tests for smfc.cmd() class.
#
from mock import MagicMock
from pytest_mock import MockerFixture
from smfc import main


# pylint: disable=too-few-public-methods
class TestMain:
    """Unit test for smfc.main() function."""

    def test_main(self, mocker:MockerFixture) -> None:
        """This is a unit test for function Service.main()."""
        mock_service_run = MagicMock()
        mocker.patch('smfc.Service.run', mock_service_run)
        main()
        mock_service_run.assert_called_once()
# pylint: enable=too-few-public-methods


# End.
