# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import ops.model

"""Custom exceptions used by the Spring Boot charm."""


class ReconciliationError(Exception):
    """Indicate there are some unrecoverable errors happens in the reconciliation process.

    The reconciliation process should terminate after this exception is raised.
    """

    def __init__(self, new_status: ops.model.StatusBase, defer_event: bool = False):
        """
        Args:
            new_status: the unit status after the reconciliation process terminated.
            defer_event: if true, defer the event that causing the reconciliation error and retry
                the reconciliation process later.
        """
        self.new_status = new_status
        self.defer_event = defer_event
