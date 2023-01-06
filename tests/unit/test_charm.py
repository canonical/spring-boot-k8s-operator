# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Spring Boot charm unit tests."""
import ops.charm
import pytest

import exceptions


def test_sprint_boot_pebble_layer(harness, patch):
    """
    arrange: put a jar file in the /app dir of the simulated Spring Boot application container.
    act: generate the Spring Boot container pebble layer configuration.
    assert: Spring Boot charm should generate a valid layer configuration.
    """
    harness.begin()
    patch.start()
    harness.charm.unit.get_container("spring-boot-app").push("/app/test.jar", source=b"")
    harness.charm.unit.get_container("spring-boot-app").push("/app/data.json", source=b"")
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    spring_boot_layer = harness.charm._generate_spring_boot_layer()
    assert spring_boot_layer == {
        "services": {
            "spring-boot-app": {
                "override": "replace",
                "summary": "Spring Boot application service",
                "command": 'java -jar "test.jar"',
                "startup": "enabled",
            }
        }
    }


@pytest.mark.parametrize(
    "filenames,message",
    [
        (["/app/test.jar", "/app/second.jar"], "multiple jar files exist in /app"),
        (["/app/test.json"], "no jar file exists in /app"),
        ([], "no jar file exists in /app"),
    ],
)
def test_incorrect_app_directory_content(harness, patch, filenames, message):
    """
    arrange: put incorrect files in the simulated Spring Boot application container.
    act: generate the Spring Boot container pebble layer configuration.
    assert: Spring Boot charm should raise ReconciliationError with different reasons accordingly.
    """
    harness.begin()
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    patch.start()
    for filename in filenames:
        harness.charm.unit.get_container("spring-boot-app").push(filename, source=b"")
    with pytest.raises(exceptions.ReconciliationError) as exception_info:
        harness.charm._generate_spring_boot_layer()
        assert exception_info.value.args[0].message == message


def test_charm_start(harness, patch):
    """
    arrange: put a jar file in the /app dir of the simulated Spring Boot application container.
    act: trigger a config-changed event.
    assert: Spring Boot charm should finish the reconciliation process without an error.
    """
    harness.begin()
    patch.start()
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.charm.unit.get_container("spring-boot-app").push("/app/test.jar", source=b"")
    harness.charm.unit.get_container("spring-boot-app").push("/app/data.json", source=b"")
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.update_config({})
    assert isinstance(harness.model.unit.status, ops.charm.model.ActiveStatus)
