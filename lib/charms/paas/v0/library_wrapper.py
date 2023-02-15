from typing import Protocol
from ops.charm import CharmBase
from ops.framework import EventBase

class LibraryWrapper(Protocol):
    def must_run_on(event: EventBase) -> bool:
        raise NotImplementedError

    def run(event: EventBase, charm: CharmBase) -> None:
        raise NotImplementedError