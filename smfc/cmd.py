from .daemon import Service

def main() -> None:
    service = Service()
    service.run()
