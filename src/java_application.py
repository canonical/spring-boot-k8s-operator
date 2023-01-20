# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=too-few-public-methods

"""The abstraction of different types of Java applications."""

import abc


class JavaApplicationBase(abc.ABC):
    """The interface class for all Java application abstractions."""

    @abc.abstractmethod
    def command(self) -> list[str]:
        """Generate the pebble command to start the Java application."""


class ExecutableJarApplication(JavaApplicationBase):
    """ExecutableJarApplication represents the Java application with a single executable jar."""

    def __init__(self, executable_jar_path: str):
        """Initialize the ExecutableJarApplication instance.

        Args:
            executable_jar_path: the path to the executable jar file.
        """
        self.executable_jar_path = executable_jar_path

    def command(self) -> list[str]:
        """Generate the pebble command to start the Java application.

        Returns:
            the pebble command to start the Java application.
        """
        return ["java", "-jar", self.executable_jar_path]


class BuildpackApplication(JavaApplicationBase):
    """BuildpackApplication represents the Java application image created with buildpack."""

    def __init__(
        self,
        class_path: str = "/workspace",
        java_executable_path: str = "/layers/paketo-buildpacks_bellsoft-liberica/jre/bin/java",
    ):
        """Initialize the BuildpackApplication instance.

        Args:
            class_path: Java class path.
            java_executable_path: the path to the java executable.
        """
        self.class_path = class_path
        self.java_executable_path = java_executable_path

    def command(self) -> list[str]:
        """Generate the command to start the Java application in a buildpack created image.

        Returns:
            the pebble command to start the Java application.
        """
        return [
            self.java_executable_path,
            "-cp",
            self.class_path,
            "org.springframework.boot.loader.JarLauncher",
        ]
