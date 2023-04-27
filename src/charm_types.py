# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Define names for types used in the Spring Boot charm."""

from typing import NamedTuple


class ExecResult(NamedTuple):
    """Command execution result.

    Attrs:
        exit_code: command exit code.
        stdout: command stdout.
        stderr: command stderr.
    """

    exit_code: int
    stdout: str
    stderr: str
