from charms.nginx_ingress_integrator.v0.ingress import (
    IngressCharmEvents,
    IngressCreatedEvent,
    IngressRequires,
)
from ops.charm import CharmBase, ConfigChangedEvent, RelationBrokenEvent
from ops.framework import EventBase


class NginxIngressWrapper:

    RELATION_NAME = "nginx_ingress"

    def __init__(self, charm: CharmBase) -> None:
        self.ingress = IngressRequires(
            charm, self.RELATION_NAME, self._nginx_ingress_config(charm)
        )
        charm.framework.observe(self.ingress.on.ingress_created, charm.reconcile)
        charm.framework.observe(charm.on[self.RELATION_NAME].relation_broken, charm.reconcile)
        charm.framework.observe(charm.on.config_changed, charm.reconcile)

    def must_run_on(self, event: EventBase) -> bool:
        """Method that defines if this wrapper must handle the given event

        Args:
            event (EventBase): Event received on the Base Charm

        Returns:
            bool: Whether this wrapper must handle the given event
        """
        return (
            isinstance(event, RelationBrokenEvent) and event.relation.name == self.RELATION_NAME
        ) or isinstance(event, (IngressCreatedEvent, ConfigChangedEvent))

    def run(self, event: EventBase, charm: CharmBase) -> dict:
        """Methods that implements the business logic to react to relation events

        Args:
            event (EventBase): The event that triggered this call, can be used to adjust the business
            logic based on it
            charm (CharmBase): The charm on which the event occurred, can be used to access some databags

        Returns:
            dict: A structured output that will be passed to the callback (for example diff of data)
        """
        self.ingress.update_config(self._nginx_ingress_config(charm))
        return {}

    def _nginx_ingress_config(self, charm: CharmBase) -> dict[str, str]:
        """Generate ingress configuration based on the Spring Boot application and charm configs.

        Returns:
            A dictionary containing the ingress configuration.
        """
        config = {
            "service-hostname": charm.model.config["ingress-hostname"] or charm.app.name,
            "service-name": charm.app.name,
            "service-port": str(charm._spring_boot_port()),
        }
        remove_prefix = charm.model.config["ingress-strip-url-prefix"]
        if remove_prefix:
            config.update(
                {
                    "rewrite-enabled": "true",
                    "rewrite-target": "/$2",
                    "path-routes": f"{remove_prefix}(/|$)(.*)",
                }
            )
        return config
