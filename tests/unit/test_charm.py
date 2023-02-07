# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=duplicate-code,protected-access

"""Spring Boot charm unit tests."""
import json
import typing

import ops.charm
import ops.pebble
import pytest
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness
from unit.spring_boot_patch import OCIImageMock, SpringBootPatch

import exceptions


def help_test_application_config(expected: dict, config: dict):
    """
    Helper to test if config has the expected attributes
    and that they have the correct value.

    Args:
        expected: dict with the env values to test
        config: dict to be tested
    """
    for env_name in expected:
        assert env_name in config
        # To test the application config serialized as json, we unserialize it
        if env_name == "SPRING_APPLICATION_JSON":
            help_test_application_config(
                json.loads(expected[env_name]), json.loads(config[env_name])
            )
            continue
        if isinstance(expected[env_name], dict):
            assert isinstance(config[env_name], dict)
            help_test_application_config(expected[env_name], config[env_name])
            continue
        assert expected[env_name] == config[env_name]


def test_spring_boot_pebble_layer(harness: Harness, patch: SpringBootPatch) -> None:
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
                "command": "java -jar /app/test.jar",
                "environment": {},
                "startup": "enabled",
            }
        },
        "checks": {
            "spring-boot-ready": {
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
def test_incorrect_app_directory_content(
    harness: Harness, patch: SpringBootPatch, filenames: typing.Sequence[str], message: str
) -> None:
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


def test_executable_jar_application_start(harness: Harness, patch: SpringBootPatch) -> None:
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


def test_buildpack_application_start(harness: Harness, patch: SpringBootPatch) -> None:
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


def test_java_application_type_detection_failure(harness: Harness, patch: SpringBootPatch) -> None:
    """
    arrange: prepare the simulated Spring Boot application container without any file.
    act: start the charm.
    assert: Spring Boot charm should be in blocking status.
    """
    patch.start({"spring-boot-app": OCIImageMock.builder().build()})
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.begin_with_initial_hooks()
    assert isinstance(harness.model.unit.status, ops.charm.model.BlockedStatus)


def test_spring_boot_config_port(harness: Harness, patch: SpringBootPatch) -> None:
    """
    arrange: provide a simulated Spring Boot application image.
    act: update the application-config to update the Spring Boot server port.
    assert: Spring Boot charm should use a pebble layer with correct environment and
        healthcheck options.
    """
    patch.start({"spring-boot-app": OCIImageMock.builder().add_file("/app/test.jar", b"").build()})
    harness.begin_with_initial_hooks()
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.update_config({"application-config": json.dumps({"server": {"port": 8888}})})
    assert harness.charm._generate_spring_boot_layer()["checks"] == {
        "spring-boot-ready": {
            "override": "replace",
            "level": "alive",
            "http": {"url": "http://localhost:8888/actuator/health"},
        },
    }
    container = harness.model.unit.containers["spring-boot-app"]
    expected = {
        "services": {
            "spring-boot-app": {
                "override": "replace",
                "summary": "Spring Boot application service",
                "environment": {"SPRING_APPLICATION_JSON": '{"server": {"port": 8888}}'},
                "command": "java -jar /app/test.jar",
                "startup": "enabled",
            }
        }
    }
    help_test_application_config(expected, container.get_plan().to_dict())


@pytest.mark.parametrize(
    "config,message",
    [
        ("a", "Invalid application-config value, expecting JSON"),
        ("1", "Invalid application-config value, expecting an object in JSON"),
    ],
)
def test_invalid_application_config(
    harness: Harness, patch: SpringBootPatch, config: str, message: str
) -> None:
    """
    arrange: provide a simulated Spring Boot application image.
    act: update the application-config with an invalid value.
    assert: Spring Boot charm should enter blocked status.
    """
    patch.start({"spring-boot-app": OCIImageMock.builder().add_file("/app/test.jar", b"").build()})
    harness.begin_with_initial_hooks()
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.update_config({"application-config": config})
    status = harness.model.unit.status
    assert isinstance(status, BlockedStatus)
    assert status.message == message


@pytest.mark.parametrize("jvm_config", ["-Xmx1G", "-Xms200k", "-Xmx10m -Xms4096"])
def test_jvm_config(harness: Harness, patch: SpringBootPatch, jvm_config):
    """
    arrange: provide a simulated Spring Boot application image.
    act: update the jvm-config with a valid value.
    assert: Spring Boot charm should start the charm with correct environment variables in the
        pebble layer.
    """
    patch.start(
        {"spring-boot-app": OCIImageMock.builder().add_file("/app/test.jar", b"").build()},
        container_mock_callback={
            "spring-boot-app": lambda container: container.process_mock.register_command_handler(
                lambda command: command[0].endswith("java"),
                lambda command, environment: (0, "", ""),
            )
        },
    )
    harness.begin_with_initial_hooks()
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.update_config({"jvm-config": jvm_config})
    status = harness.model.unit.status
    assert isinstance(status, ActiveStatus)
    container = harness.model.unit.containers["spring-boot-app"]
    assert (
        container.get_plan().to_dict()["services"]["spring-boot-app"]["environment"][
            "JAVA_TOOL_OPTIONS"
        ]
        == jvm_config
    )


@pytest.mark.parametrize("jvm_config", ["-Xmx1G --invalid", "-Xmx10m --invalid -Xms4096"])
def test_invalid_jvm_config(harness: Harness, patch: SpringBootPatch, jvm_config):
    """
    arrange: provide a simulated Spring Boot application image.
    act: update the jvm-config with an invalid value.
    assert: Spring Boot charm should enter blocking status.
    """
    patch.start(
        {"spring-boot-app": OCIImageMock.builder().add_file("/app/test.jar", b"").build()},
        container_mock_callback={
            "spring-boot-app": lambda container: container.process_mock.register_command_handler(
                lambda command: command[0].endswith("java"),
                lambda command, environment: (0, "", "")
                if "--invalid" not in environment["JAVA_TOOL_OPTIONS"]
                else (1, "", ""),
            )
        },
    )
    harness.begin_with_initial_hooks()
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.update_config({"jvm-config": jvm_config})
    status = harness.model.unit.status
    assert isinstance(status, BlockedStatus)
    assert status.message == "Invalid jvm-config"


@pytest.mark.parametrize(
    "jvm_config,memory_constraint,okay",
    [
        ("-Xmx1G", None, True),
        ("-Xmx1G", "2Gi", True),
        ("-Xmx10m -Xms4096", "20Mi", True),
        ("-Xms4G", "1Gi", False),
        ("-Xms1G -Xmx4G", "2Gi", False),
    ],
)
def test_jvm_heap_memory_config(
    harness: Harness,
    patch: SpringBootPatch,
    jvm_config: str,
    memory_constraint: typing.Optional[str],
    okay: bool,
):
    """
    arrange: provide a simulated Spring Boot application image and set the container memory
        constraint.
    act: update the heap memory related jvm-config.
    assert: Spring Boot charm should enter blocking status when the JVM heap memory configurate
        conflicts with the container memory constraint.
    """
    patch.start(
        {"spring-boot-app": OCIImageMock.builder().add_file("/app/test.jar", b"").build()},
        container_mock_callback={
            "spring-boot-app": lambda container: container.process_mock.register_command_handler(
                lambda command: command[0].endswith("java"),
                lambda command, environment: (0, "", ""),
            )
        },
        memory_constraint=memory_constraint,
    )
    harness.begin_with_initial_hooks()
    harness.set_can_connect(harness.model.unit.containers["spring-boot-app"], True)
    harness.update_config({"jvm-config": jvm_config})
    status = harness.model.unit.status
    if okay:
        assert isinstance(status, ActiveStatus)
    else:
        assert isinstance(status, BlockedStatus)
        assert status.message == (
            "Invalid jvm-config, "
            "Java heap memory specification exceeds application memory constraint"
        )


def test_pebble_ready(harness: Harness, patch: SpringBootPatch):
    """
    arrange: provide a simulated Spring Boot application image.
    act: set pebble as ready.
    assert: the unit should have the ActiveStatus
    """
    patch.start(
        {"spring-boot-app": OCIImageMock.builder().add_file("/app/test.jar", b"").build()},
    )
    harness.begin_with_initial_hooks()
    harness.container_pebble_ready("spring-boot-app")
    assert isinstance(harness.model.unit.status, ActiveStatus)


@pytest.mark.parametrize(
    "relation_data, expected_output",
    [
        (
            {
                "endpoints": "test-mysql:3306",
                "password": "test-password",
                "username": "test-username",
            },
            {
                "url": "jdbc:mysql://test-mysql:3306/spring-boot",
                "password": "test-password",
                "username": "test-username",
            },
        ),
        (
            {
                "database": "test-database",
                "endpoints": "test-mysql:3306,test-mysql-2:3306",
                "password": "test-password",
                "username": "test-username",
            },
            {
                "url": "jdbc:mysql://test-mysql:3306/test-database",
                "password": "test-password",
                "username": "test-username",
            },
        ),
    ],
)
def test_datasource(
    harness: Harness, patch: SpringBootPatch, relation_data: dict, expected_output: dict
):
    """
    arrange: provide a simulated Spring Boot application image.
    act: start the charm and a database. Integrates the db to the charm.
    assert: test datasource output of the charm when integrated with a db or not.
        Datasource contains the data needed to spring-boot
        to establish a connection to the data provider.
    """
    patch.start(
        {"spring-boot-app": OCIImageMock.builder().add_file("/app/test.jar", b"").build()},
    )
    harness.begin_with_initial_hooks()
    harness.container_pebble_ready("spring-boot-app")
    assert isinstance(harness.model.unit.status, ActiveStatus)
    assert harness.charm._datasource() == {"username": "", "password": "", "url": ""}

    mysql_relation_id: int = harness.add_relation("mysql", "mysql-k8s")

    harness.update_relation_data(mysql_relation_id, "mysql-k8s", relation_data)
    assert harness.charm._datasource() == expected_output


def test_buildpack_app_with_mysql_capability(
    harness: Harness, patch: SpringBootPatch
) -> None:
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
            .add_file("/workspace/BOOT-INF/lib/mysql-connector-j-10.1.1.jar", b"")
            .build()
        }
    )
    harness.begin_with_initial_hooks()
    assert harness.charm._detect_mysql_capability()


def test_buildpack_app_with_no_mysql_capability(
    harness: Harness, patch: SpringBootPatch
) -> None:
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
    harness.begin_with_initial_hooks()
    assert not harness.charm._detect_mysql_capability()


def test_executable_jar_with_no_mysql_capability(harness: Harness, patch: SpringBootPatch) -> None:
    """
    arrange: put a jar file in the /app dir of the simulated Spring Boot application container.
    act: start the charm.
    assert: Spring Boot charm should finish the reconciliation process without an error.
    """
    patch.start(
        {
            "spring-boot-app": OCIImageMock.builder()
            .add_file("/app/test.jar", b"")
            .build()
        },
        container_mock_callback={
            "spring-boot-app": lambda container: container.process_mock.register_command_handler(
                lambda command: command[0] == "jar",
                lambda command, environment: (0, """
                    META-INF/
                    META-INF/MANIFEST.MF
                    org/
                    org/springframework/boot/loader/
                    org/springframework/boot/loader/ClassPathIndexFile.class
                    BOOT-INF/classes/com/canonical/sampleapp/
                    BOOT-INF/classes/com/canonical/sampleapp/Application.class
                    BOOT-INF/lib/
                    BOOT-INF/lib/log4j-to-slf4j-2.19.0.jar
                """, ""),
            )
        },
    )
    harness.begin_with_initial_hooks()
    assert not harness.charm._detect_mysql_capability()


def test_executable_jar_with_mysql_capability(harness: Harness, patch: SpringBootPatch) -> None:
    """
    arrange: put a jar file in the /app dir of the simulated Spring Boot application container.
    act: start the charm.
    assert: Spring Boot charm should finish the reconciliation process without an error.
    """
    patch.start(
        {
            "spring-boot-app": OCIImageMock.builder()
            .add_file("/app/test.jar", b"")
            .build()
        },
        container_mock_callback={
            "spring-boot-app": lambda container: container.process_mock.register_command_handler(
                lambda command: command[0] == "jar",
                lambda command, environment: (0, """
                    META-INF/
                    META-INF/MANIFEST.MF
                    org/
                    org/springframework/boot/loader/
                    org/springframework/boot/loader/ClassPathIndexFile.class
                    BOOT-INF/classes/com/canonical/sampleapp/
                    BOOT-INF/classes/com/canonical/sampleapp/Application.class
                    BOOT-INF/lib/
                    BOOT-INF/lib/log4j-to-slf4j-2.19.0.jar
                    BOOT-INF/lib/mysql-connector-j-2.19.0.jar
                """, ""),
            )
        },
    )
    harness.begin_with_initial_hooks()
    assert harness.charm._detect_mysql_capability()
