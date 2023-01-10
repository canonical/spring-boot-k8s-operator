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
    executable_jar_resources = {"spring-boot-app-image": "ghcr.io/canonical/spring-boot:3.0"}
    buildpack_resources = {"spring-boot-app-image": "ghcr.io/canonical/spring-boot:3.0-layered"}
    # Deploy the charm and wait for idle
    app_name = "spring-boot-k8s"
    buildpack_app_name = f"{app_name}-buildpack"
    await asyncio.gather(
        ops_test.model.deploy(
            charm, resources=executable_jar_resources, application_name=app_name, series="jammy"
        ),
        ops_test.model.deploy(
            charm,
            resources=buildpack_resources,
            application_name=buildpack_app_name,
            series="jammy",
        ),
        ops_test.model.wait_for_idle(apps=[app_name, buildpack_app_name], status="active"),
    )
    for name in [app_name, buildpack_app_name]:
        unit_ips = await get_unit_ip_list(name)
        for unit_ip in unit_ips:
            assert requests.get(f"http://{unit_ip}:8080/hello-world", timeout=5).status_code == 200
