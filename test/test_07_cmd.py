#!/usr/bin/python3
#
#   test_07_cmd.py (C) 2021-2024, Peter Sulyok
#   Unit tests for smfc.main() function.
#
import unittest
from unittest.mock import patch, MagicMock
from smfc import main

class MainTestCase(unittest.TestCase):
    """Unit test for smfc.main() function."""

    def test_main(self) -> None:
        """This is a unit test for function Service.main()."""
        mock_service_run = MagicMock()
        with patch('smfc.Service.run', mock_service_run):
            main()
        mock_service_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()

# End.