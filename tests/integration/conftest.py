# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test fixtures for Spring Boot charm integration tests."""
import asyncio
import typing
from dataclasses import dataclass
from pathlib import Path

import pytest_asyncio
import yaml
from pytest import fixture
from pytest_operator.plugin import OpsTest


@dataclass
class Service:
    """Class used to describe a service to deploy

    Attrs:
        name: charm to deploy (like mysql-k8s)
        series: ubuntu series of the charm to be deployed
        channel: channel of the charm to be deployed
        trust: should the charm to be deployed be trusted to do k8s modifications directly ?
    """

    name: str
    series: str = "jammy"
    channel: str = "stable"
    trust: bool = False


@dataclass
class Relation:
    """Class used to describe a relation to create

    Attrs:
        source: the source app for the relation '<application>[:<relation_name>]'
        target: the target app for the relation '<application>[:<relation_name>]'
    """

    source: str
    target: str


@fixture(scope="module", name="metadata")
def metadata_fixture():
    """Provides charm metadata."""
    yield yaml.safe_load(Path("./metadata.yaml").read_text("utf-8"))


@fixture(scope="module", name="app_name")
def app_name_fixture(metadata):
    """Provides app name from the metadata."""
    yield metadata["name"]


@pytest_asyncio.fixture(scope="module")
async def app(ops_test: OpsTest, app_name: str, request):
    """Provides a running application, its services and wished relations."""
    assert ops_test.model

    charm = await ops_test.build_charm(".")

    to_deploy = [
        ops_test.model.wait_for_idle(),
        ops_test.model.deploy(
            charm, resources=request.param["resources"], application_name=app_name, series="jammy"
        ),
    ]

    for service in request.param["services"]:
        to_deploy.append(
            ops_test.model.deploy(
                service.name, series=service.series, channel=service.channel, trust=service.trust
            )
        )

    # Deploy the charm, its services and wait for idle
    await asyncio.gather(*to_deploy)

    to_relate = [
        ops_test.model.wait_for_idle(),
    ]
    for relation in request.param["relations"]:
        to_relate.append(ops_test.model.add_relation(relation.source, relation.target))

    # Create relations and wait for idle
    await asyncio.gather(*to_relate)

    yield ops_test.model.applications[app_name]


@pytest_asyncio.fixture(scope="module", name="get_unit_ip_list")
async def get_unit_ip_list_fixture(ops_test: OpsTest):
    """Helper function to retrieve unit ip addresses."""

    async def _get_unit_ip_list(app_name: str) -> typing.List[str]:
        """Get most recent charm application unit IPs.

        Args:
            app_name: the name of the charm application.

        Returns:
            IP of all units in the Charm application, sorted by unit number.
        """
        assert ops_test.model
        status = await ops_test.model.get_status()
        units = status.applications[app_name].units
        ip_list = []
        for key in sorted(units.keys(), key=lambda n: int(n.split("/")[-1])):
            ip_list.append(units[key].address)
        return ip_list

    yield _get_unit_ip_list
