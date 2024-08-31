#
#   cmd.py (C) 2020-2024, Peter Sulyok
#   smfc package: Super Micro fan control for Linux (home) servers.
#   smfc.main() function implementation, command-line interface.
#
from .service import Service


def main() -> None:
    """Entry point of the `smfc` service."""
    service = Service()
    service.run()


if __name__ == '__main__':
    main()


# End.
