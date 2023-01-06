#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for Spring Boot charm."""

import asyncio
import logging

import pytest
import requests
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, get_unit_ip_list):
    """
    arrange: none.
    act: build the Spring Boot charm and deploy it.
    assert: Spring Boot application in all units is up and running
    """
    assert ops_test.model
    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {"spring-boot-app-image": "ghcr.io/canonical/spring-boot:2.7"}

    # Deploy the charm and wait for idle
    app_name = "spring-boot-k8s"
    await asyncio.gather(
        ops_test.model.deploy(
            charm, resources=resources, application_name=app_name, series="jammy"
        ),
        ops_test.model.wait_for_idle(apps=[app_name], status="active"),
    )
    unit_ips = await get_unit_ip_list()
    for unit_ip in unit_ips:
        assert requests.get(f"http://{unit_ip}:8080/hello-world", timeout=5).status_code == 200
