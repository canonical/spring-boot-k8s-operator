#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Spring Boot Charm service."""

import logging

from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class SpringBootCharm(CharmBase):
    """Spring Boot Charm service."""

    def __init__(self, *args):
        """Initialize the instance."""
        super().__init__(*args)


if __name__ == "__main__":  # pragma: nocover
    main(SpringBootCharm)
