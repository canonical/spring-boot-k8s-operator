# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=unused-argument

"""pytest fixtures for the integration test."""

import ops.testing
import pytest

from charm import SpringBootCharm

from .spring_boot_patch import SpringBootPatch


@pytest.fixture(name="harness")
def harness_fixture():
    """Ops testing framework harness fixture."""
    ops.testing.SIMULATE_CAN_CONNECT = True
    harness = ops.testing.Harness(SpringBootCharm)

    yield harness

    harness.cleanup()
    ops.testing.SIMULATE_CAN_CONNECT = False


@pytest.fixture(name="patch")
def patch_fixture(harness):
    """Patch system for unit tests."""
    patch = SpringBootPatch()

    yield patch

    if patch.started:
        patch.stop()
