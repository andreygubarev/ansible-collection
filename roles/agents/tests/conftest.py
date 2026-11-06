"""Select the expected account for default and overridden-user verification."""

import pytest


def pytest_addoption(parser):
    parser.addoption("--agents-user", default="agent", help="Expected agent application owner")


@pytest.fixture(scope="session")
def agents_user(request):
    return request.config.getoption("--agents-user")


@pytest.fixture(scope="session")
def agents_home(agents_user):
    return f"/home/{agents_user}"
