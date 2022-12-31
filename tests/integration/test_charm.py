#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for Spring Boot charm."""

import asyncio
import logging

import pytest
from pytest import Config
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, pytestconfig: Config):
    """
    arrange: none.
    act: build the charm-under-test and deploy it together with related charms.
    assert: on the unit status before any relations/configurations take place.
    """
    assert ops_test.model
    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {"spring-boot-app-image": pytestconfig.getoption("--spring-boot-app-image")}

    # Deploy the charm and wait for idle
    app_name = "spring-boot-k8s"
    await asyncio.gather(
        ops_test.model.deploy(
            charm, resources=resources, application_name=app_name, series="jammy"
        ),
        ops_test.model.wait_for_idle(apps=[app_name], raise_on_blocked=True, timeout=1000),
    )
