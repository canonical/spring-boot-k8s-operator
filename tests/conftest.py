# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Global fixtures and utilities for integration and unit tests."""


def pytest_addoption(parser):
    """Define some command line options for integration and unit tests."""
    parser.addoption("--spring-boot-app-image", action="store")
