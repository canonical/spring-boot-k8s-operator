# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""The mocking and patching system for Spring Boot charm unit tests."""
import io
import pathlib
import tarfile
import tempfile
import typing
from unittest.mock import MagicMock, _patch, patch

import kubernetes.client
import ops.model
import ops.pebble


class OCIImageMock:
    """The class to simulate an OCI image."""

    class OCIImageMockBuilder:
        """Helper class to create a :class:`OCIImageMock` instance."""

        def __init__(self) -> None:
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

    def extract_to(self, path: str) -> None:
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

    def push(self, path: str, source: bytes) -> None:
        """Mock function for :meth:`ops.model.Container.push`."""
        converted_path = self._path_convert(path)
        converted_path.parent.mkdir(exist_ok=True)
        converted_path.write_bytes(source)

    def list_files(self, path: str) -> typing.List[MagicMock]:
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

    def isdir(self, path: str) -> bool:
        """Mock function for :meth:`ops.model.Container.isdir`."""
        return self._path_convert(path).is_dir()

    def exists(self, path: str) -> bool:
        """Mock function for :meth:`ops.model.Container.exists`."""
        return self._path_convert(path).exists()


class ContainerProcessMock:
    """Mock class for container process execution system."""

    def __init__(self):
        """Initialize the ContainerProcessMock instance."""
        self._handlers = []

    def register_command_handler(
        self,
        match: typing.Callable[[typing.List[str]], bool],
        handler: typing.Callable[
            [typing.List[str], typing.Dict[str, str]], typing.Tuple[int, str, str]
        ],
    ) -> None:
        """Add a handler for certain command to mock the command execution, last match rules.

        Args:
            match: match function for the handler. match function is a function that takes a
                list of string (command) and return boolean. If match returns true, the
                corresponding handler will be executed to mock the command execution.
            handler: handler function to mock the command execution. handler is a function that
                takes two arguments, list of string (command) and a dict (environment arguments).
                handler function should return a 3-tuple of (exit_code, stdout, stderr)
        """
        self._handlers.append((match, handler))

    # pylint: disable=unused-argument
    def exec(self, command: typing.List[str], environment=None, timeout=None):
        """Mock function for :meth:`ops.model.Container.exec`."""
        handler = None
        for match, _handler in self._handlers:
            if match(command):
                handler = _handler
        if handler is None:
            raise RuntimeError(f"Unknown command: {repr(command)}")
        exit_code, stdout, stderr = handler(command, environment if environment else {})

        def wait_output():
            if exit_code != 0:
                raise ops.pebble.ExecError(
                    command=command, exit_code=exit_code, stdout=stdout, stderr=stderr
                )
            return stdout, stderr

        return MagicMock(wait_output=wait_output)


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
        self.process_mock = ContainerProcessMock()
        self._original_container = original_container

    def push(self, path: str, source: bytes) -> None:
        """Mock function for :meth:`ops.model.Container.push`."""
        return self.file_system_mock.push(path=path, source=source)

    def list_files(self, path: str) -> typing.List[MagicMock]:
        """Mock function for :meth:`ops.model.Container.list_files`."""
        return self.file_system_mock.list_files(path)

    def isdir(self, path: str) -> bool:
        """Mock function for :meth:`ops.model.Container.isdir`."""
        return self.file_system_mock.isdir(path)

    def exists(self, path: str) -> bool:
        """Mock function for :meth:`ops.model.Container.exists`."""
        return self.file_system_mock.exists(path)

    def can_connect(self) -> bool:
        """Mock function for :meth:`ops.model.Container.can_connect`."""
        return self._original_container.can_connect()

    def add_layer(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        """Mock function for :meth:`ops.model.Container.add_layer`."""
        return self._original_container.add_layer(*args, **kwargs)

    def replan(self) -> None:
        """Mock function for :meth:`ops.model.Container.replan`."""
        return self._original_container.replan()

    def exec(self, command: typing.List[str], environment=None, timeout=None):
        """Mock function for :meth:`ops.model.Container.exec`."""
        return self.process_mock.exec(command=command, environment=environment, timeout=timeout)


class SpringBootPatch:
    """The overall patch system for Spring Boot charm unit tests."""

    def __init__(self) -> None:
        """Initialize the :class:`SpringBootPatch` instance."""
        self.container_mocks: typing.Dict[str, ContainerMock] = {}
        self.images: typing.Dict[str, OCIImageMock] = {}
        self._patches: typing.List[_patch] = []
        self._patches.append(
            patch.multiple(
                ops.model.Unit,
                get_container=self._gen_get_container_mock(ops.model.Unit.get_container),
            )
        )
        self._container_mock_callback: typing.Dict[
            str, typing.Callable[[ContainerMock], typing.Any]
        ] = {}
        self.started = False

    def _gen_get_container_mock(
        self, original_get_container: typing.Callable[[ops.model.Unit, str], ops.model.Container]
    ) -> typing.Callable[[ops.model.Unit, str], ContainerMock]:
        """Create a mock function for :meth:`ops.model.Unit.get_container`."""

        def _get_container_mock(_self: ops.model.Unit, container_name: str) -> ContainerMock:
            if container_name in self.container_mocks:
                return self.container_mocks[container_name]
            original_container = original_get_container(_self, container_name)
            container_mock = ContainerMock(original_container, self.images[container_name])
            if container_name in self._container_mock_callback:
                self._container_mock_callback[container_name](container_mock)
            self.container_mocks[container_name] = container_mock
            return container_mock

        return _get_container_mock

    def start(
        self,
        images: typing.Dict[str, OCIImageMock],
        container_mock_callback: typing.Optional[
            typing.Dict[str, typing.Callable[[ContainerMock], typing.Any]]
        ] = None,
        memory_constraint: typing.Optional[str] = None,
    ) -> None:
        """Start the patch system.

        Args:
            images: Mapping from container name to simulated OCI image.
            container_mock_callback: Callback functions to modify the container mock after the
                container mock generation.
            memory_constraint: Container memory constraint for the spring-boot-app container,
                in human-readable form (4Gi, 100Mi).
        """
        self.started = True
        self.images = images
        if container_mock_callback:
            self._container_mock_callback = container_mock_callback
        self._patches.append(patch.multiple(kubernetes.config, load_incluster_config=MagicMock()))
        kubernetes_pod_mock = MagicMock()
        kubernetes_spec_mock = MagicMock()
        kubernetes_container_mock = MagicMock()
        kubernetes_charm_container_mock = MagicMock()
        kubernetes_resources_mock = MagicMock()
        kubernetes_pod_mock.spec = kubernetes_spec_mock
        kubernetes_spec_mock.containers = [
            kubernetes_charm_container_mock,
            kubernetes_container_mock,
        ]
        kubernetes_container_mock.name = "spring-boot-app"
        kubernetes_charm_container_mock.name = "charm"
        kubernetes_container_mock.resources = kubernetes_resources_mock
        kubernetes_resources_mock.limits = (
            None if memory_constraint is None else {"memory": memory_constraint}
        )
        self._patches.append(
            patch.multiple(
                kubernetes.client.CoreV1Api,
                read_namespaced_pod=MagicMock(return_value=kubernetes_pod_mock),
            )
        )

        for patch_ in self._patches:
            patch_.start()

    def stop(self) -> None:
        """Stop the patch system."""
        self.started = False
        self._container_mock_callback = {}
        for patch_ in self._patches:
            patch_.stop()
        self._patches = []
