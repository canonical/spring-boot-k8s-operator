# Copyright 2023 Canonical Ltd.
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
    harness = ops.testing.Harness(SpringBootCharm)

    yield harness

    harness.cleanup()


@pytest.fixture(name="patch")
def patch_fixture(harness: ops.testing.Harness):
    """Patch system for unit tests."""
    patch = SpringBootPatch()

    yield patch

    if patch.started:
        patch.stop()
