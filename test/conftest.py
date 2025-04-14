
def pytest_addoption(parser):
    parser.addoption("--hd", action="store")
    parser.addoption("--cpu", action="store")
    parser.addoption("--config", action="store")