# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Global fixtures and utilities for integration and unit tests."""
import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Define some command line options for integration and unit tests."""
    parser.addoption("--spring-boot-app-image", action="store")
