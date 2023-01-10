# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test fixtures for Spring Boot charm integration tests."""

import pytest_asyncio
import pytest_operator.plugin


@pytest_asyncio.fixture(scope="module", name="get_unit_ip_list")
async def fixture_get_unit_ip_list(ops_test: pytest_operator.plugin.OpsTest):
    """Helper function to retrieve unit ip addresses."""

    async def _get_unit_ip_list(app_name: str):
        assert ops_test.model
        status = await ops_test.model.get_status()
        units = status.applications[app_name].units
        ip_list = []
        for key in sorted(units.keys(), key=lambda n: int(n.split("/")[-1])):
            ip_list.append(units[key].address)
        return ip_list

    yield _get_unit_ip_list
