#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for Spring Boot charm."""

import asyncio
import json
import logging

import pytest
import requests
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

APP_NAME = "spring-boot-k8s"
BUILDPACK_APP_NAME = f"{APP_NAME}-buildpack"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, get_unit_ip_list) -> None:
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
    await asyncio.gather(
        ops_test.model.deploy(
            charm, resources=executable_jar_resources, application_name=APP_NAME, series="jammy"
        ),
        ops_test.model.deploy(
            charm,
            resources=buildpack_resources,
            application_name=BUILDPACK_APP_NAME,
            series="jammy",
        ),
        ops_test.model.wait_for_idle(apps=[APP_NAME, BUILDPACK_APP_NAME], status="active"),
    )
    for name in [APP_NAME, BUILDPACK_APP_NAME]:
        unit_ips = await get_unit_ip_list(name)
        for unit_ip in unit_ips:
            assert requests.get(f"http://{unit_ip}:8080/hello-world", timeout=5).status_code == 200


@pytest.mark.abort_on_fail
async def test_application_config_server_port(ops_test: OpsTest, get_unit_ip_list) -> None:
    """
    arrange: deploy Spring Boot applications.
    act: Update the application-config with a different Spring Boot server port then reset the
        application-config configuration.
    assert: Spring Boot applications should change the server port accordingly.
    """
    assert ops_test.model
    new_port = 8888
    default_port = 8080
    for port in (new_port, default_port):
        app_config = json.dumps({"server": {"port": new_port}}) if port == new_port else ""
        await asyncio.gather(
            ops_test.model.applications[APP_NAME].set_config({"application-config": app_config}),
            ops_test.model.applications[BUILDPACK_APP_NAME].set_config(
                {"application-config": app_config}
            ),
            ops_test.model.wait_for_idle(apps=[APP_NAME, BUILDPACK_APP_NAME], status="active"),
        )
        for name in [APP_NAME, BUILDPACK_APP_NAME]:
            unit_ips = await get_unit_ip_list(name)
            for unit_ip in unit_ips:
                response = requests.get(f"http://{unit_ip}:{port}/hello-world", timeout=5)
                assert response.status_code == 200


@pytest.mark.abort_on_fail
async def test_application_config(ops_test: OpsTest, get_unit_ip_list) -> None:
    """
    arrange: deploy Spring Boot applications.
    act: Update the application-config with a different application layer configuration.
    assert: Spring Boot example applications /hello-world endpoint should respond differently
        according to the configuration.
    """
    assert ops_test.model
    app_config = json.dumps({"greeting": "Bonjour"})
    await asyncio.gather(
        ops_test.model.applications[APP_NAME].set_config({"application-config": app_config}),
        ops_test.model.applications[BUILDPACK_APP_NAME].set_config(
            {"application-config": app_config}
        ),
        ops_test.model.wait_for_idle(apps=[APP_NAME, BUILDPACK_APP_NAME], status="active"),
    )
    for name in [APP_NAME, BUILDPACK_APP_NAME]:
        unit_ips = await get_unit_ip_list(name)
        for unit_ip in unit_ips:
            response = requests.get(f"http://{unit_ip}:8080/hello-world", timeout=5)
            assert response.status_code == 200
            assert "Bonjour" in response.text
