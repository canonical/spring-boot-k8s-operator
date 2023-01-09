# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=too-few-public-methods

"""The abstraction of different types of Java applications."""

import abc


class JavaApplicationBase(abc.ABC):
    """The interface class for all Java application abstractions."""

    @abc.abstractmethod
    def command(self) -> str:
        """Generate the pebble command to start the Java application."""


class ExecutableJarApplication(JavaApplicationBase):
    """ExecutableJarApplication represents the Java application with a single executable jar."""

    def __init__(self, executable_jar_path: str):
        """Initialize the ExecutableJarApplication instance."""
        self.executable_jar_path = executable_jar_path

    def command(self) -> str:
        """Generate the pebble command to start the Java application."""
        return f"java -jar {self.executable_jar_path}"
