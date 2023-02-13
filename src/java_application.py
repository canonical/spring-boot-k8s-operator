# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=too-few-public-methods

"""The abstraction of different types of Java applications."""

import abc

import ops


class JavaApplicationBase(abc.ABC):
    """The interface class for all Java application abstractions."""

    def __init__(self, container: ops.model.Container):
        """Initialize the JavaApplicationBase instance.

        Args:
            container: the container hosting the java application
        """
        self.container = container

    @abc.abstractmethod
    def command(self) -> list[str]:
        """Generate the pebble command to start the Java application."""

    @abc.abstractmethod
    def has_java_library(self, library: str) -> bool:
        """Check if the given java library is present in the application.

        Args:
            library: name of the library whose presence we want to check
        """


class ExecutableJarApplication(JavaApplicationBase):
    """ExecutableJarApplication represents the Java application with a single executable jar."""

    def __init__(self, container: ops.model.Container, executable_jar_path: str):
        """Initialize the ExecutableJarApplication instance.

        Args:
            container: the container hosting the java application
            executable_jar_path: the path to the executable jar file.
        """
        super().__init__(container)
        self.executable_jar_path = executable_jar_path

    def command(self) -> list[str]:
        """Generate the pebble command to start the Java application.

        Returns:
            the pebble command to start the Java application.
        """
        return ["java", "-jar", self.executable_jar_path]

    def has_java_library(self, library: str) -> bool:
        """Check if the given java library is present in the application.

        Args:
            library: name of the library whose presence we want to check

        Returns:
            True if the library file is present, False otherwise.
        """
        process = self.container.exec(["jar", "-t", "--file", self.executable_jar_path])
        output, _ = process.wait_output()

        return any(
            filename.startswith(library) and filename.endswith(".jar")
            for filename in (path.split("/")[-1] for path in output.splitlines())
        )


class BuildpackApplication(JavaApplicationBase):
    """BuildpackApplication represents the Java application image created with buildpack."""

    def __init__(
        self,
        container: ops.model.Container,
        class_path: str = "/workspace",
        java_executable_path: str = "/layers/paketo-buildpacks_bellsoft-liberica/jre/bin/java",
    ):
        """Initialize the BuildpackApplication instance.

        Args:
            container: the container hosting the java application
            class_path: Java class path.
            java_executable_path: the path to the java executable.
        """
        super().__init__(container)
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

    def has_java_library(self, library: str) -> bool:
        """Check if the given java library is present in the application.

        Args:
            library: name of the library whose presence we want to check

        Returns:
            True if the library file is present, False otherwise.
        """
        try:
            files = self.container.list_files(f"{self.class_path}/BOOT-INF/lib")
        except FileNotFoundError:
            return False

        return any(file.name.startswith(library) and file.name.endswith(".jar") for file in files)
