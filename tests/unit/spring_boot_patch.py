# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""The mocking and patching system for Spring Boot charm unit tests."""
import io
import pathlib
import tarfile
import tempfile
import typing
from unittest.mock import MagicMock, patch

import ops.model
import ops.pebble


class OCIImageMock:
    """The class to simulate an OCI image."""

    class OCIImageMockBuilder:
        """Helper class to create a :class:`OCIImageMock` instance."""

        def __init__(self):
            """Initialize the :class:`OCIImageMockBuilder` instance."""
            self.tar_file_obj = io.BytesIO()
            # pylint: disable=consider-using-with
            self.tar_file = tarfile.TarFile(mode="w", fileobj=self.tar_file_obj)

        def add_file(self, path: str, content: bytes) -> "OCIImageMock.OCIImageMockBuilder":
            """Add a file to the simulated OCI image.

            Args:
                path: the absolute path for this file in simulated OCI image, all parent
                    directories will be created if not exist.
                content: file content in bytes.
            """
            assert path.startswith("/") and not path.endswith("/")
            tar_info = tarfile.TarInfo(path.removeprefix("/"))
            tar_info.size = len(content)
            self.tar_file.addfile(tar_info, io.BytesIO(content))
            return self

        def add_dir(self, path: str) -> "OCIImageMock.OCIImageMockBuilder":
            """Add a directory to the simulated OCI image.

            Args:
                path: the absolute path of this directory in simulated OCI image, the path should
                 end with a slash. All parent directories will be created if not exist.
            """
            assert path.startswith("/") and path.endswith("/")
            tar_info = tarfile.TarInfo(path.removeprefix("/"))
            tar_info.type = tarfile.DIRTYPE
            self.tar_file.addfile(tar_info)
            return self

        def build(self) -> "OCIImageMock":
            """Create the :class:`OCIImageMock` instance."""
            self.tar_file.close()
            return OCIImageMock(self.tar_file_obj.getvalue())

    def __init__(self, files_tar: bytes):
        """Initialize the OCIImageMock instance.

        Args:
            files_tar: files_tar is an uncompressed tar file in bytes. Every file and directory
                inside the tar file represents a file or directory inside the mock OCI image.
        """
        # pylint: disable=consider-using-with
        self.files_tar = tarfile.TarFile(mode="r", fileobj=io.BytesIO(files_tar))

    def extract_to(self, path: str):
        """Extract the content (files and directories) of the simulated OCI image to a directory.

        Args:
            path: path to the output directory.
        """
        self.files_tar.extractall(path)

    @classmethod
    def builder(cls) -> "OCIImageMock.OCIImageMockBuilder":
        """Create a build to help creating a :class:`OCIImageMock` instance."""
        return cls.OCIImageMockBuilder()


class ContainerFileSystemMock:
    """Mock class for container file subsystem."""

    def __init__(self, image: OCIImageMock):
        """Initialize the :class:`ContainerFileSystemMock` instance.

        Args:
            image: The mocking OCI image for this container.
        """
        self.tempdir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.tempdir_path = pathlib.Path(self.tempdir.name)
        image.extract_to(self.tempdir.name)

    def _path_convert(self, path: str) -> pathlib.Path:
        """Convert an absolute path to a path in the temporary directory, like chroot."""
        return self.tempdir_path / path.removeprefix("/")

    def push(self, path: str, source: bytes):
        """Mock function for :meth:`ops.model.Container.push`."""
        converted_path = self._path_convert(path)
        converted_path.parent.mkdir(exist_ok=True)
        converted_path.write_bytes(source)

    def list_files(self, path: str):
        """Mock function for :meth:`ops.model.Container.list_files`."""
        converted_path = self._path_convert(path)
        file_list = []
        try:
            dir_iter = converted_path.iterdir()
        except FileNotFoundError as exc:
            raise ops.pebble.APIError(
                body={},
                code=404,
                status="",
                message=f"stat {converted_path}: no such file or directory",
            ) from exc
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

    def __init__(self, original_container: ops.model.Container, image: OCIImageMock):
        """Initialize the :class:`ContainerMock` instance.

        Args:
            original_container: The original :class:`ops.model.Container` object, any method that's
                not patched is passed to the original object.
            image: The mocking OCI image for this container.
        """
        self.file_system_mock = ContainerFileSystemMock(image=image)
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
        self.images = {}
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
            container_mock = ContainerMock(original_container, self.images[container_name])
            self.container_mocks[container_name] = container_mock
            return container_mock

        return _get_container_mock

    def start(self, images: typing.Dict[str, OCIImageMock]):
        """Start the patch system.

        Args:
            images: Mapping from container name to simulated OCI image.
        """
        self.started = True
        self.images = images
        self._patch.start()

    def stop(self):
        """Stop the patch system."""
        self.started = False
        self._patch.stop()
