#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for Spring Boot charm."""

import asyncio
import json
import logging

import ops.model
import pytest
import requests
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

APP_NAME = "spring-boot-k8s"
BUILDPACK_APP_NAME = f"{APP_NAME}-buildpack"
MEM_1G_APP_NAME = f"{APP_NAME}-1g"
MEM_1G_BUILDPACK_APP_NAME = f"{BUILDPACK_APP_NAME}-1g"
ALL_APP_NAMES = [APP_NAME, BUILDPACK_APP_NAME, MEM_1G_APP_NAME, MEM_1G_BUILDPACK_APP_NAME]
INGRESS_NAME = "nginx-ingress-integrator"

ACTIVE_STATUS: str = ops.model.ActiveStatus.name  # type: ignore


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
            resources=executable_jar_resources,
            application_name=MEM_1G_APP_NAME,
            series="jammy",
            constraints={"mem": 512},  # memory constraint unit is MiB
        ),
        ops_test.model.deploy(
            charm,
            resources=buildpack_resources,
            application_name=BUILDPACK_APP_NAME,
            series="jammy",
        ),
        ops_test.model.deploy(
            charm,
            resources=buildpack_resources,
            application_name=MEM_1G_BUILDPACK_APP_NAME,
            series="jammy",
            constraints={"mem": 512},
        ),
        ops_test.model.deploy(INGRESS_NAME, series="focal", trust=True),
        ops_test.model.wait_for_idle(
            apps=ALL_APP_NAMES + [INGRESS_NAME],
            status="active",
        ),
    )
    for name in ALL_APP_NAMES:
        unit_ips = await get_unit_ip_list(name)
        for unit_ip in unit_ips:
            assert requests.get(f"http://{unit_ip}:8080/hello-world", timeout=5).status_code == 200


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
        for name in (APP_NAME, BUILDPACK_APP_NAME):
            unit_ips = await get_unit_ip_list(name)
            for unit_ip in unit_ips:
                response = requests.get(f"http://{unit_ip}:{port}/hello-world", timeout=5)
                assert response.status_code == 200


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
    for name in (APP_NAME, BUILDPACK_APP_NAME):
        unit_ips = await get_unit_ip_list(name)
        for unit_ip in unit_ips:
            response = requests.get(f"http://{unit_ip}:8080/hello-world", timeout=5)
            assert response.status_code == 200
            assert "Bonjour" in response.text


async def test_jvm_config(ops_test: OpsTest, get_unit_ip_list) -> None:
    """
    arrange: deploy Spring Boot applications.
    act: Update the jvm-config to configure JVM heap memory settings.
    assert: Spring Boot example applications should run with corresponding JVM parameters.
    """
    assert ops_test.model
    jvm_config = "-Xms256m -Xmx512M"
    await asyncio.gather(
        ops_test.model.applications[APP_NAME].set_config({"jvm-config": jvm_config}),
        ops_test.model.applications[BUILDPACK_APP_NAME].set_config({"jvm-config": jvm_config}),
        ops_test.model.wait_for_idle(apps=[APP_NAME, BUILDPACK_APP_NAME], status="active"),
    )
    for name in (APP_NAME, BUILDPACK_APP_NAME):
        unit_ips = await get_unit_ip_list(name)
        for unit_ip in unit_ips:
            response = requests.get(f"http://{unit_ip}:8080/jvm-arguments", timeout=5)
            assert response.status_code == 200
            assert response.json() == jvm_config.split()


async def test_invalid_jvm_config(ops_test: OpsTest) -> None:
    """
    arrange: deploy Spring Boot applications.
    act: Update the jvm-config with some invalid values.
    assert: Spring Boot example applications should enter blocked status.
    """
    assert ops_test.model
    invalid_jvm_config = "-Xms256A -Xmx512G"
    await asyncio.gather(
        ops_test.model.applications[APP_NAME].set_config({"jvm-config": invalid_jvm_config}),
        ops_test.model.applications[BUILDPACK_APP_NAME].set_config(
            {"jvm-config": invalid_jvm_config}
        ),
        ops_test.model.applications[MEM_1G_APP_NAME].set_config({"jvm-config": "-Xms256m -Xmx2G"}),
        ops_test.model.applications[MEM_1G_BUILDPACK_APP_NAME].set_config(
            {"jvm-config": "-Xms256m -Xmx2G"}
        ),
        ops_test.model.wait_for_idle(apps=ALL_APP_NAMES),
    )
    for name in (APP_NAME, BUILDPACK_APP_NAME):
        for unit in ops_test.model.applications[name].units:
            assert unit.workload_status == "blocked"
            assert unit.workload_status_message == "Invalid jvm-config"

    for name in (MEM_1G_APP_NAME, MEM_1G_BUILDPACK_APP_NAME):
        for unit in ops_test.model.applications[name].units:
            assert unit.workload_status == "blocked"
            assert unit.workload_status_message == (
                "Invalid jvm-config, "
                "Java heap memory specification exceeds application memory constraint"
            )
    await asyncio.gather(
        *(
            [
                ops_test.model.applications[app_name].set_config({"jvm-config": ""})
                for app_name in ALL_APP_NAMES
            ]
            + [ops_test.model.wait_for_idle(apps=ALL_APP_NAMES)]
        )
    )


async def test_ingress(ops_test: OpsTest) -> None:
    """
    arrange: deploy Spring Boot applications.
    act: relate the Spring Boot application charm with ingress integrator charm, and update
        ingress related charm configuration.
    assert: Ingress integrator charm should create ingress resources in Kubernetes cluster for the
        Spring Boot charm accordingly.
    """
    assert ops_test.model
    await ops_test.model.add_relation(APP_NAME, INGRESS_NAME)
    await ops_test.model.wait_for_idle(status=ACTIVE_STATUS)

    response = requests.get("http://127.0.0.1/hello-world", headers={"Host": APP_NAME}, timeout=5)
    assert response.status_code == 200
    assert "world" in response.text.lower()

    new_hostname = "new-hostname"
    application = ops_test.model.applications[APP_NAME]
    await application.set_config({"ingress-hostname": new_hostname})
    await ops_test.model.wait_for_idle(status=ACTIVE_STATUS)
    response = requests.get(
        "http://127.0.0.1/hello-world", headers={"Host": new_hostname}, timeout=5
    )
    assert response.status_code == 200
    assert "world" in response.text.lower()

    # The default value of Nginx ingress integrator charm configuration rewrite-target will
    # prevent changes from relation. This is a temporary fix, please remove this once this
    # problem is fixed in Nginx ingress integrator charm.
    await ops_test.model.applications[INGRESS_NAME].set_config({"rewrite-target": ""})

    await application.set_config({"ingress-strip-url-prefix": "/foo"})
    await ops_test.model.wait_for_idle(status=ACTIVE_STATUS)
    response = requests.get(
        "http://127.0.0.1/foo/hello-world", headers={"Host": new_hostname}, timeout=5
    )
    assert response.status_code == 200
    assert "world" in response.text.lower()
