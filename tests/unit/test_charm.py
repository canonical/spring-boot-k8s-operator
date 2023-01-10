# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=duplicate-code,protected-access

"""Spring Boot charm unit tests."""
import ops.charm
import pytest
from unit.spring_boot_patch import OCIImageMock

import exceptions


def test_sprint_boot_pebble_layer(harness, patch):
    """
    arrange: put a jar file in the /app dir of the simulated Spring Boot application container.
    act: generate the Spring Boot container pebble layer configuration.
    assert: Spring Boot charm should generate a valid layer configuration.
    """
    patch.start(
        {
            "spring-boot-app": OCIImageMock.builder()
            .add_file("/app/test.jar", b"")
            .add_file("/app/data.json", b"")
            .build()
        }
    )
    harness.begin()
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    spring_boot_layer = harness.charm._generate_spring_boot_layer()
    assert spring_boot_layer == {
        "services": {
            "spring-boot-app": {
                "override": "replace",
                "summary": "Spring Boot application service",
                "command": 'java -jar "/app/test.jar"',
                "startup": "enabled",
            }
        },
        "checks": {
            "wordpress-ready": {
                "override": "replace",
                "level": "alive",
                "http": {"url": "http://localhost:8080/actuator/health"},
            },
        },
    }


@pytest.mark.parametrize(
    "filenames,message",
    [
        (["/app/test.jar", "/app/second.jar"], "Multiple jar files found in /app"),
        (["/app/test.json"], "No jar file found in /app"),
        ([], "Unknown Java application type"),
    ],
)
def test_incorrect_app_directory_content(harness, patch, filenames, message):
    """
    arrange: put incorrect files in the simulated Spring Boot application container.
    act: generate the Spring Boot container pebble layer configuration.
    assert: Spring Boot charm should raise ReconciliationError with different reasons accordingly.
    """
    image_mock_builder = OCIImageMock.builder()
    for file in filenames:
        image_mock_builder.add_file(file, b"")

    patch.start({"spring-boot-app": image_mock_builder.build()})
    harness.begin()
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    for filename in filenames:
        harness.charm.unit.get_container("spring-boot-app").push(filename, source=b"")
    with pytest.raises(exceptions.ReconciliationError) as exception_info:
        harness.charm._generate_spring_boot_layer()
    assert exception_info.value.new_status.message == message


def test_executable_jar_application_start(harness, patch):
    """
    arrange: put a jar file in the /app dir of the simulated Spring Boot application container.
    act: start the charm.
    assert: Spring Boot charm should finish the reconciliation process without an error.
    """
    patch.start(
        {
            "spring-boot-app": OCIImageMock.builder()
            .add_file("/app/test.jar", b"")
            .add_file("/app/data.json", b"")
            .build()
        }
    )
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.begin_with_initial_hooks()
    assert isinstance(harness.model.unit.status, ops.charm.model.ActiveStatus)


def test_buildpack_application_start(harness, patch):
    """
    arrange: provide a simulated OCI image mimicking a Spring Boot application image created by
        buildpack.
    act: start the charm.
    assert: Spring Boot charm should finish the reconciliation process without an error.
    """
    patch.start(
        {
            "spring-boot-app": OCIImageMock.builder()
            .add_file("/layers/paketo-buildpacks_bellsoft-liberica/jre/bin/java", b"")
            .add_file("/workspace/org/springframework/boot/loader/JarLauncher.class", b"")
            .build()
        }
    )
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.begin_with_initial_hooks()
    assert isinstance(harness.model.unit.status, ops.charm.model.ActiveStatus)


def test_java_application_type_detection_failure(harness, patch):
    """
    arrange: prepare the simulated Spring Boot application container without any file.
    act: start the charm.
    assert: Spring Boot charm should be in blocking status.
    """
    patch.start({"spring-boot-app": OCIImageMock.builder().build()})
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.begin_with_initial_hooks()
    assert isinstance(harness.model.unit.status, ops.charm.model.BlockedStatus)
