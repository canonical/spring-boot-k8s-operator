# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import pathlib
import tempfile
import typing
from unittest.mock import MagicMock, patch

import ops.model
import ops.pebble

"""The mocking and patching system for Spring Boot charm unit tests."""


class ContainerFileSystemMock:
    """Mock class for container file subsystem."""

    def __init__(self):
        """Initialize the :class:`ContainerFileSystemMock` instance."""
        self.tempdir = tempfile.TemporaryDirectory()
        self.tempdir_path = pathlib.Path(self.tempdir.name)

    def _path_convert(self, path: str) -> pathlib.Path:
        """Convert an absolute path to a path in the temporary directory, like chroot."""
        return self.tempdir_path / path.removeprefix("/")

    def push(self, path: str, source: bytes):
        """Mock function for :meth:`ops.model.Container.push`."""
        path = self._path_convert(path)
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(source)

    def list_files(self, path: str):
        """Mock function for :meth:`ops.model.Container.list_files`."""
        path = self._path_convert(path)
        file_list = []
        try:
            dir_iter = path.iterdir()
        except FileNotFoundError:
            raise ops.pebble.APIError(
                body={}, code=404, status="", message=f"stat {path}: no such file or directory"
            )
        for file in dir_iter:
            file_info = MagicMock()
            file_info.name = file.name
            file_list.append(file_info)
        return file_list

    def isdir(self, path: str):
        """Mock function for :meth:`ops.model.Container.isdir`."""
        return self._path_convert(path).is_dir()


class ContainerMock:
    """Mock class for :class:`ops.model.Container`."""

    def __init__(self, original_container: ops.model.Container):
        """Initialize the :class:`ContainerMock` instance.

        Args:
            original_container: The original :class:`ops.model.Container` object, any method that's
                not patched is passed to the original object.
        """
        self.file_system_mock = ContainerFileSystemMock()
        self._original_container = original_container

    def push(self, path: str, source: bytes):
        """Mock function for :meth:`ops.model.Container.push`."""
        return self.file_system_mock.push(path=path, source=source)

    def list_files(self, path: str):
        """Mock function for :meth:`ops.model.Container.list_files`."""
        return self.file_system_mock.list_files(path)

    def isdir(self, path: str):
        """Mock function for :meth:`ops.model.Container.isdir`."""
        return self.file_system_mock.isdir(path)

    def can_connect(self):
        """Mock function for :meth:`ops.model.Container.can_connect`."""
        return self._original_container.can_connect()

    def add_layer(self, *args, **kwargs):
        """Mock function for :meth:`ops.model.Container.add_layer`."""
        return self._original_container.add_layer(*args, **kwargs)

    def replan(self):
        """Mock function for :meth:`ops.model.Container.replan`."""
        return self._original_container.replan()


class SpringBootPatch:
    """The overall patch system for Spring Boot charm unit tests."""

    def __init__(self):
        """Initialize the :class:`SpringBootPatch` instance."""
        self.container_mocks = {}
        self._patch = patch.multiple(
            ops.model.Unit,
            get_container=self._gen_get_container_mock(ops.model.Unit.get_container),
        )
        self.started = False

    def _gen_get_container_mock(
        self, original_get_container: typing.Callable[[ops.model.Unit, str], ops.model.Container]
    ):
        """Create a mock function for :meth:`ops.model.Unit.get_container`"""

        def _get_container_mock(_self, container_name: str):
            if container_name in self.container_mocks:
                return self.container_mocks[container_name]
            original_container = original_get_container(_self, container_name)
            container_mock = ContainerMock(original_container)
            self.container_mocks[container_name] = container_mock
            return container_mock

        return _get_container_mock

    def start(self):
        """Start the patch system."""
        self.started = True
        self._patch.start()

    def stop(self):
        """Stop the patch system."""
        self.started = False
        self._patch.stop()
