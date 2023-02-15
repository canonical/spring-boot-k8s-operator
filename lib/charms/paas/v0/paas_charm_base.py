import importlib
import logging
from collections import defaultdict

from charms.paas.v0.library_wrapper import LibraryWrapper
from ops.charm import CharmBase
from ops.framework import EventBase

WRAPPER_LIBRARY_MAP: dict[str, dict[str, str]] = {
    "mysql_client": {
        "class": "MysqlClientWrapper",
        "library": "charms.paas.v0.mysql_client_wrapper",
        "callback": "_on_database_changed",
    },
    "postgresql_client": {
        "class": "PostgresClientWrapper",
        "library": "charms.paas.v0.postgres_client_wrapper",
        "callback": "_on_database_changed",
    },
    "nginx_ingress": {
        "class": "NginxIngressWrapper",
        "library": "charms.paas.v0.nginx_ingress_wrapper",
        "callback": "_on_ingress_changed",
    },
}

PEER = "paas-charm"


class PAASCharmBase(CharmBase):
    wrappers: defaultdict = defaultdict(LibraryWrapper)

    def __init__(self, *args) -> None:
        super().__init__(*args)
        for requires in self.meta.requires.values():
            if requires.relation_name not in WRAPPER_LIBRARY_MAP:
                logging.warning(
                    f"Declared required interface {requires.interface_name} / {requires.relation_name} not found in PAASCharmBase library map, ignoring."
                )
                continue

            try:
                wrapper = importlib.import_module(
                    WRAPPER_LIBRARY_MAP[requires.relation_name]["library"]
                )
                class_constructor = getattr(
                    wrapper, WRAPPER_LIBRARY_MAP[requires.relation_name]["class"]
                )
                self.wrappers[requires.relation_name] = class_constructor(self)
                logging.debug(f"Wrapper for {requires.relation_name} instantiated and registered.")
            except ImportError as e:
                logging.warning(f"Can't import wrapper for {requires.relation_name}, ignoring.")

    def reconcile(self, event: EventBase) -> None:
        """Reconciliation callback for integration management

        Args:
            event (EventBase): Event emitted that needs to be treated
        """
        for wrapper_name, wrapper in self.wrappers.items():
            if wrapper.must_run_on(event):
                output = wrapper.run(event, self)
                callback = getattr(self, WRAPPER_LIBRARY_MAP[wrapper_name]["callback"])
                callback(event, output)

    @property
    def app_data(self) -> dict:
        """Application peer relation data object."""
        relation = self.model.get_relation(PEER)
        if not relation:
            return {}

        return relation.data[self.app]

    def _on_database_changed(self, event: EventBase, data: dict) -> None:
        """Callback that can be overridden by the charm to react to changes on the database
        relation (like a restart)

        Args:
            event (EventBase): The event that triggered this callback
            data (dict): The returned data of the wrapper run action
        """
        pass

    def _on_ingress_changed(self, event: EventBase, data: dict) -> None:
        """Callback that can be overridden by the charm to react to changes on the ingress
        relation (like a restart)

        Args:
            event (EventBase): The event that triggered this callback
            data (dict): The returned data of the wrapper run action
        """
        pass

    def _on_observability_changed(self, event: EventBase, data: dict) -> None:
        """Callback that can be overridden by the charm to react to changes on the observability
        relations (like a restart)

        Args:
            event (EventBase): The event that triggered this callback
            data (dict): The returned data of the wrapper run action
        """
        pass
