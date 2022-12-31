# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""pytest fixtures for the integration test."""

import ops.testing
import pytest

from charm import SpringBootCharm


@pytest.fixture(name="harness")
def harness_fixture():
    """Ops testing framework harness fixture."""
    ops.testing.SIMULATE_CAN_CONNECT = True
    harness = ops.testing.Harness(SpringBootCharm)

    yield harness

    harness.cleanup()
    ops.testing.SIMULATE_CAN_CONNECT = False
