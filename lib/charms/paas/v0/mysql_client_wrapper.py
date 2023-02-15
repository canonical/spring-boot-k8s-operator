from charms.data_platform_libs.v0.database_requires import DatabaseCreatedEvent, DatabaseRequires
from ops.charm import CharmBase, RelationBrokenEvent, RelationCreatedEvent
from ops.framework import EventBase


class MysqlClientWrapper:

    INTERFACE_NAME = "mysql_client"

    def __init__(self, charm: CharmBase) -> None:
        self.database = DatabaseRequires(charm, self.INTERFACE_NAME, "paas", "")
        charm.framework.observe(self.database.on.database_created, charm.reconcile)
        charm.framework.observe(charm.on[self.INTERFACE_NAME].relation_broken, charm.reconcile)

    def must_run_on(self, event: EventBase) -> bool:
        """Method that defines if this wrapper must handle the given event

        Args:
            event (EventBase): Event received on the Base Charm

        Returns:
            bool: Whether this wrapper must handle the given event
        """
        return isinstance(event, (DatabaseCreatedEvent, RelationBrokenEvent, RelationCreatedEvent))

    def run(self, event: EventBase, charm: CharmBase) -> dict:
        """Methods that implements the business logic to react to relation events

        Args:
            event (EventBase): The event that triggered this call, can be used to adjust the business
            logic based on it
            charm (CharmBase): The charm on which the event occurred, can be used to access some databags

        Returns:
            dict: A structured output that will be passed to the callback (for example diff of data)
        """
        relation_data = self.database.fetch_relation_data()
        relation_data[event.relation.id]["database"] = self.database.database
        return {self.INTERFACE_NAME: relation_data[event.relation.id]}
