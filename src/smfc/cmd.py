#
#   cmd.py (C) 2020-2025, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.main() function implementation, command-line interface.
#
from smfc.service import Service


def main() -> None:
    """Entry point of the `smfc` program."""
    service = Service()
    service.run()


if __name__ == '__main__':
    main()

# End.
