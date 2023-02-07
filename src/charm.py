#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Spring Boot Charm service."""

import json
import logging
import re
import typing

import kubernetes.client
import ops.charm
from charms.data_platform_libs.v0.data_interfaces import DatabaseCreatedEvent, DatabaseRequires
from ops.charm import CharmBase, CharmEvents, EventBase, RelationBrokenEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ExecError

from charm_types import ExecResult
from exceptions import ReconciliationError
from java_application import BuildpackApplication, ExecutableJarApplication

logger = logging.getLogger(__name__)

JAVA_TOOL_OPTIONS = "JAVA_TOOL_OPTIONS"


class SpringBootCharm(CharmBase):
    """Spring Boot Charm service.

    Attrs:
        on: Allows for subscribing to CharmEvents
    """

    on = CharmEvents()

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self.reconciliation)
        self.framework.observe(self.on.spring_boot_app_pebble_ready, self.reconciliation)
        self.database: typing.Optional[DatabaseRequires] = self._setup_database_requirer(
            "mysql", "spring-boot"
        )

    def _setup_database_requirer(self, relation_name: str, database_name: str) -> DatabaseRequires:
        """Set up a DatabaseRequires instance.

        The DatabaseRequires instance is an interface between the charm and various data providers.
        It handles those relations and emit events to help us abstract these integrations.

        Args:
            relation_name: Name of the data relation
            database_name: Name of the database (can be overwritten by the provider)

        Returns:
            DatabaseRequires object
        """
        database_requirer = DatabaseRequires(
            self,
            relation_name=relation_name,
            database_name=database_name,
        )
        self.framework.observe(database_requirer.on.database_created, self._on_database_created)
        self.framework.observe(self.on[relation_name].relation_broken, self._on_relation_broken)
        return database_requirer

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event triggered when a database was created for this application.

        Args:
            event: The DatabaseCreatedEvent object
        """
        logger.debug("Database credentials are received: %s", event.username)
        self.reconciliation(event)

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle relation broken event.

        Args:
            event: The RelationBrokenEvent object
        """
        logger.debug("Relation with database removed: %s", event.relation.name)
        self.reconciliation(event)

    def _datasource(self) -> dict[str, str]:
        """Compute datasource dict and return it.

        Returns:
            Dict containing details about the data provider integration
        """
        if self.database:
            relations_data = list(self.database.fetch_relation_data().values())
            if relations_data:
                # There can be only one database integrated at a time
                # cf: metadata.yaml
                data = relations_data[0]
                if "endpoints" in data and "username" in data and "password" in data:
                    # We assume that the relation follows the following json schema:
                    # https://github.com/canonical/charm-relation-interfaces/blob/main/interfaces/mysql_client/v0/schemas/provider.json
                    database_name = data.get("database", self.database.database)
                    endpoint = data["endpoints"].split(",")[0]
                    return {
                        "username": data["username"],
                        "password": data["password"],
                        "url": f"jdbc:mysql://{endpoint}/{database_name}",
                    }
        return {
            "username": "",
            "password": "",
            "url": "",
        }

    def _application_config(self) -> dict | None:
        """Decode the value of the charm configuration application-config.

        Returns:
            The value of the charm configuration application-config.

        Raises:
            ReconciliationError: when application-config is invalid.
        """
        try:
            config = self.model.config["application-config"]
            if not config:
                return None
            application_config = json.loads(config)
            if isinstance(application_config, dict):
                if "spring" not in application_config:
                    application_config["spring"] = {}
                if "datasource" not in application_config["spring"]:
                    application_config["spring"]["datasource"] = {}
                application_config["spring"]["datasource"] = self._datasource()
                return application_config
            logger.error("Invalid application-config value: %s", repr(config))
            raise ReconciliationError(
                new_status=BlockedStatus(
                    "Invalid application-config value, expecting an object in JSON"
                )
            )
        except json.JSONDecodeError as exc:
            raise ReconciliationError(
                new_status=BlockedStatus("Invalid application-config value, expecting JSON")
            ) from exc

    def _spring_boot_port(self) -> int:
        """Get the Spring Boot application server port, default to 8080.

        Returns:
            Spring Boot server port.

        Raises:
            ReconciliationError: server port is provided in application-config but the value is
                invalid.
        """
        application_config = self._application_config()
        if (
            application_config
            and "server" in application_config
            and isinstance(application_config["server"], dict)
            and application_config["server"]["port"]
        ):
            port = application_config["server"]["port"]
            if not isinstance(port, int) or port <= 0:
                logger.error("Invalid server port configuration: %s", repr(port))
                raise ReconciliationError(
                    new_status=BlockedStatus("Invalid server port configuration")
                )
            logger.debug(
                "Port configuration detected in application-config, update server port to %s", port
            )
            return port
        return 8080

    def _exec(
        self, command: list[str], environment: typing.Optional[typing.Dict[str, str]] = None
    ) -> ExecResult:
        """Execute a command in Spring Boot application container with a timeout of 60s.

        Args:
            command: command to be executed.
            environment: environment variables for the process.

        Returns:
            A 3-tuple of exit code, stdout and stderr.
        """
        container = self._spring_boot_container()
        process = container.exec(command, environment=environment, timeout=60)
        try:
            stdout, stderr = process.wait_output()
            return ExecResult(0, stdout, stderr)
        except ExecError as error:
            return ExecResult(
                error.exit_code, typing.cast(str, error.stdout), typing.cast(str, error.stderr)
            )

    def _parse_human_readable_units(self, number_with_unit: str) -> int:
        """Parse numbers with human-readable units like K, M and G.

        Args:
            number_with_unit: input string, something like ``"1G"`` or ``"33m"``.

        Returns:
            Parsed result, as an integer.

        Raises:
            ValueError: when the input number is invalid.
        """
        number_with_unit = number_with_unit.lower()
        unit = number_with_unit[-1]
        unit_scale = {"k": 2**10, "m": 2**20, "g": 2**30}
        if unit not in unit_scale:
            try:
                return int(number_with_unit)
            except ValueError as exc:
                raise ValueError(f"Unknown human-readable unit: {repr(number_with_unit)}") from exc
        digits = number_with_unit[:-1]
        return int(digits) * unit_scale[unit]

    def _regex_find_last(self, pattern: str, string: str, default: str) -> str:
        """Match the last regex capturing group in the input string.

        Args:
            pattern: regular expression pattern.
            string: input string
            default: default value if no match is found.

        Return:
            The last matching capturing group in the input string, or ``default`` if not found.
        """
        matches = re.findall(pattern, string)
        if not matches:
            return default
        return matches[-1]

    def _jvm_config(self) -> str:
        """Get and verify the JVM parameters defined in the charm configuration jvm-config.

        Returns:
            JVM command line arguments as a string.

        Raises:
            ReconciliationError: when the jvm-config value is invalid.
        """
        config = self.model.config["jvm-config"]
        if not config:
            return ""
        java_heap_initial_memory = self._parse_human_readable_units(
            self._regex_find_last("(?:^|\\s)-Xms(\\d+[kmgtKMGT]?)\\b", config, "0")
        )
        java_heap_maximum_memory = self._parse_human_readable_units(
            self._regex_find_last("(?:^|\\s)-Xmx(\\d+[kmgtKMGT]?)\\b", config, "0")
        )
        container_memory_limit = self._get_spring_boot_container_memory_constraint()
        if (
            container_memory_limit
            and max(java_heap_maximum_memory, java_heap_initial_memory) > container_memory_limit
        ):
            raise ReconciliationError(
                new_status=BlockedStatus(
                    "Invalid jvm-config, "
                    "Java heap memory specification exceeds application memory constraint"
                )
            )
        java_app = self._detect_java_application()
        command = java_app.command()
        command.insert(1, "--dry-run")
        exit_code, _, stderr = self._exec(command, environment={JAVA_TOOL_OPTIONS: config})
        if exit_code != 0:
            logger.error(
                "Invalid JVM configuration, error report from java command %s: %s", command, stderr
            )
            raise ReconciliationError(new_status=BlockedStatus("Invalid jvm-config"))
        return config

    def _spring_boot_env(self) -> typing.Dict[str, str]:
        """Generate environment variables for the Spring Boot application process.

        Returns:
            Environment variables for the Spring Boot application.
        """
        env = {}
        application_config = self._application_config()
        if application_config:
            env["SPRING_APPLICATION_JSON"] = json.dumps(self._application_config())
        jvm_config = self._jvm_config()
        if jvm_config:
            env[JAVA_TOOL_OPTIONS] = jvm_config
        return env

    def _detect_java_application(self) -> ExecutableJarApplication | BuildpackApplication:
        """Detect the type of the Java application inside the Spring Boot application image.

        Returns:
            One of the subclasses of :class:`java_application.JavaApplicationBase` represents
            one Java application type.

        Raises:
            ReconciliationError: unrecoverable errors happen during the Java application type
                detection process, requiring the main reconciliation process to terminate the
                reconciliation early.
        """
        container = self._spring_boot_container()
        if container.exists(
            "/layers/paketo-buildpacks_bellsoft-liberica/jre/bin/java"
        ) and container.exists("/workspace/org/springframework/boot/loader/JarLauncher.class"):
            return BuildpackApplication()
        if container.isdir("/app"):
            files_in_app = container.list_files("/app")
            jar_files = [file.name for file in files_in_app if file.name.endswith(".jar")]
            if not jar_files:
                raise ReconciliationError(new_status=BlockedStatus("No jar file found in /app"))
            if len(jar_files) > 1:
                logger.error("Multiple jar files found in /app: %s", repr(jar_files))
                raise ReconciliationError(
                    new_status=BlockedStatus("Multiple jar files found in /app")
                )
            jar_file = jar_files[0]
            return ExecutableJarApplication(executable_jar_path=f"/app/{jar_file}")
        raise ReconciliationError(new_status=BlockedStatus("Unknown Java application type"))

    def _spring_boot_container(self) -> ops.model.Container:
        """Retrieve the container for the Spring Boot application.

        Returns:
            An instance of :class:`ops.charm.Container` represents the Spring Boot container.

        Raises:
            ReconciliationError: when pebble is not ready in Spring Boot application container.
        """
        container = self.unit.get_container("spring-boot-app")
        if not container.can_connect():
            raise ReconciliationError(
                new_status=WaitingStatus("Waiting for pebble"), defer_event=True
            )
        return container

    def _generate_spring_boot_layer(self) -> dict:
        """Generate Spring Boot service layer for pebble.

        Returns:
            Spring Boot service layer configuration, in the form of a dict.
        """
        java_app = self._detect_java_application()
        command = java_app.command()
        return {
            "services": {
                "spring-boot-app": {
                    "override": "replace",
                    "summary": "Spring Boot application service",
                    "environment": self._spring_boot_env(),
                    "command": " ".join(command),
                    "startup": "enabled",
                }
            },
            "checks": {
                "wordpress-ready": {
                    "override": "replace",
                    "level": "alive",
                    "http": {
                        "url": f"http://localhost:{self._spring_boot_port()}/actuator/health"
                    },
                },
            },
        }

    def _get_spring_boot_container_memory_constraint(self) -> typing.Optional[int]:
        """Get the spring-boot-app container memory limit.

        Return:
            The memory limit of the spring-boot-app container in number of bytes. ``None`` if
            there's no limit.

        Raises:
            RuntimeError: Container spring-boot-app does not exist, it shouldn't happen since
                this function checks the existence of the spring-boot-app first.
        """
        # ensure that the Spring Boot container is up
        self._spring_boot_container()
        kubernetes.config.load_incluster_config()
        client = kubernetes.client.CoreV1Api()
        spec: kubernetes.client.V1PodSpec = client.read_namespaced_pod(
            name=self.unit.name.replace("/", "-"), namespace=self.model.name
        ).spec
        container = next(
            (container for container in spec.containers if container.name == "spring-boot-app"),
            None,
        )
        if container is None:
            raise RuntimeError("Container spring-boot-app does not exist")
        limits = container.resources.limits
        if limits is None:
            return 0
        memory_limit = container.resources.limits.get("memory")
        if memory_limit is None:
            return 0
        return self._parse_human_readable_units(memory_limit.removesuffix("i"))

    def _service_reconciliation(self) -> None:
        """Run the reconciliation process for pebble services."""
        container = self._spring_boot_container()
        container.add_layer("spring-boot-app", self._generate_spring_boot_layer(), combine=True)
        container.replan()

    def reconciliation(self, event: EventBase) -> None:
        """Run the main reconciliation process of Spring Boot charm.

        Args:
            event: the charm event that triggers the reconciliation.
        """
        try:
            logger.debug("Start reconciliation, triggered by %s", event)
            self.unit.status = MaintenanceStatus("Start reconciliation process")
            self._service_reconciliation()
            self.unit.status = ActiveStatus()
            logger.debug("Finish reconciliation, triggered by %s", event)
        except ReconciliationError as error:
            self.unit.status = error.new_status
            if error.defer_event:
                event.defer()


if __name__ == "__main__":  # pragma: nocover
    main(SpringBootCharm)
