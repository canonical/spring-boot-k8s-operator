#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Spring Boot Charm service."""

import json
import logging
import typing

import ops.charm
from ops.charm import CharmBase, EventBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from exceptions import ReconciliationError
from java_application import BuildpackApplication, ExecutableJarApplication

logger = logging.getLogger(__name__)


class SpringBootCharm(CharmBase):
    """Spring Boot Charm service."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self.reconciliation)

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
                return application_config
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
        """Get Spring Boot server port.

        Returns:
            Sprint Boot server port.
        """
        application_config = self._application_config()
        if (
            application_config
            and "server" in application_config
            and isinstance(application_config["server"], dict)
            and application_config["server"]["port"]
        ):
            return application_config["server"]["port"]
        return 8080

    def _sprint_boot_env(self) -> typing.Dict[str, str]:
        """Generate environment variables for the Spring Boot application process.

        Returns:
            Environment variables for the Spring Boot application.
        """
        env = {}
        application_config = self._application_config()
        if application_config:
            env["SPRING_APPLICATION_JSON"] = json.dumps(self._application_config())
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
        """
        return self.unit.get_container("spring-boot-app")

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
                    "environment": self._sprint_boot_env(),
                    "command": command,
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

    def _service_reconciliation(self) -> None:
        """Run the reconciliation process for pebble services.

        Raises:
            ReconciliationError: unrecoverable errors happen during the Java application type
                detection process, requiring the main reconciliation process to terminate the
                reconciliation early.
        """
        container = self._spring_boot_container()
        if not container.can_connect():
            raise ReconciliationError(
                new_status=WaitingStatus("Waiting for pebble"), defer_event=True
            )
        container.add_layer("spring-boot-app", self._generate_spring_boot_layer(), combine=True)
        container.replan()

    def reconciliation(self, event: EventBase) -> None:
        """Run the main reconciliation process of Spring Boot charm.

        Args:
            event: the charm event that triggers the reconciliation.
        """
        try:
            self.unit.status = MaintenanceStatus("Start reconciliation process")
            self._service_reconciliation()
            self.unit.status = ActiveStatus()
        except ReconciliationError as error:
            self.unit.status = error.new_status
            if error.defer_event:
                event.defer()


if __name__ == "__main__":  # pragma: nocover
    main(SpringBootCharm)
