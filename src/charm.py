#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Spring Boot Charm service."""

import logging

import ops.charm
from ops.charm import CharmBase, EventBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from exceptions import ReconciliationError

logger = logging.getLogger(__name__)


class SpringBootCharm(CharmBase):
    """Spring Boot Charm service."""

    def __init__(self, *args):
        """Initialize the instance."""
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self.reconciliation)

    def _spring_boot_container(self) -> ops.model.Container:
        """Retrieve the container for the Spring Boot application.

        Returns:
            An instance of :class:`ops.charm.Container` represents the Spring Boot container.
        """
        return self.unit.get_container("spring-boot-app")

    def _generate_spring_boot_layer(self) -> dict:
        """Generate Spring Boot service layer for pebble.

        Returns:
            Spring Boot service layer configuration, in the form of a dict
        """
        container = self._spring_boot_container()
        if not container.isdir("/app"):
            raise ReconciliationError(new_status=BlockedStatus("Directory /app does not exist"))
        files_in_app = container.list_files("/app")
        jar_files = [file.name for file in files_in_app if file.name.endswith(".jar")]
        if not jar_files:
            raise ReconciliationError(new_status=BlockedStatus("No jar file found in /app"))
        if len(jar_files) > 1:
            raise ReconciliationError(new_status=BlockedStatus("Multiple jar files found in /app"))
        jar_file = jar_files[0]
        return {
            "services": {
                "spring-boot-app": {
                    "override": "replace",
                    "summary": "Spring Boot application service",
                    "command": f'java -jar "{jar_file}"',
                    "startup": "enabled",
                }
            },
            "checks": {
                "wordpress-ready": {
                    "override": "replace",
                    "level": "alive",
                    "http": {"url": "http://localhost/actuator/health"},
                },
            },
        }

    def _service_reconciliation(self):
        container = self._spring_boot_container()
        if not container.can_connect():
            raise ReconciliationError(
                new_status=WaitingStatus("Waiting for pebble"), defer_event=True
            )
        container.add_layer("spring-boot-app", self._generate_spring_boot_layer(), combine=True)
        container.replan()

    def reconciliation(self, event: EventBase):
        """Run the main reconciliation process of Spring Boot charm."""
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
