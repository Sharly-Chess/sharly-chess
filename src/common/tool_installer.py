import os
import platform
import stat
import shutil
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import tempfile

import requests
from packaging.version import Version

from common import DEVEL_ENV, REQUEST_TIMEOUT, BASE_DIR
from common.i18n import _
from common.logger import (
    get_logger,
    print_interactive_warning,
    print_interactive_success,
    print_interactive_error,
    print_interactive_info,
)

logger = get_logger()


class ToolInstaller(ABC):
    """An abstract class for tools and libs to check installation and install.
    Classes inheriting from this class should just implement methods check_files() and install()."""

    def __init__(
        self,
        name: str,
        version: Version,
        licence_files: set[str] | None = None,
        licence_type: str | None = None,
    ):
        self.name: str = name
        self.version: Version = version
        self.licence_files: set[str] = licence_files or set()
        self.licence_type: str | None = licence_type

    @property
    @abstractmethod
    def check_files(self) -> set[Path]:
        """Returns the path of the file to check for a correct installation."""

    @property
    def is_installed(self) -> bool:
        """Returns True if correctly installed, False otherwise."""
        return all(file.exists() for file in self.check_files)

    def check_installation(self) -> bool:
        """Checks the installation of a tool or lib.
        If not installed and DEVEL_ENV then install.
        After this, returns True if correctly installed, False otherwise."""
        if self.is_installed:
            logger.debug('Library [%s] is installed.', self.name)
            return True
        else:
            if not DEVEL_ENV:
                print_interactive_error(
                    _('Library [{lib}] is missing.').format(lib=self.name)
                )
                return False
            print_interactive_warning(
                _('Library [{lib}] is missing.').format(lib=self.name)
            )
            if not self.install():
                print_interactive_error(
                    _('Installation of [{lib}] failed.').format(lib=self.name)
                )
            else:
                print_interactive_success(_('Installed [{lib}].').format(lib=self.name))
            return self.is_installed

    @abstractmethod
    def install(self) -> bool:
        """Install the needed stuff, returns True on success, False otherwise."""

    @staticmethod
    def download_file(
        url: str,
        dest_file: Path,
    ):
        print_interactive_info(f'Downloading {url}...')
        response = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(dest_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print_interactive_success('Done.')

    @staticmethod
    def install_archive_and_delete(archive_path: Path, install_dir: Path):
        print_interactive_info(f'Installing to {install_dir}...')
        install_dir.mkdir(parents=True, exist_ok=True)
        shutil.unpack_archive(archive_path, install_dir)
        archive_path.unlink(missing_ok=True)
        print_interactive_success('Done.')


class WebLibInstaller(ToolInstaller, ABC):
    """A utility class to install web libraries."""

    lib_dir: Path = BASE_DIR / 'src' / 'web' / 'static' / 'lib'

    def __init__(
        self,
        name: str,
        version: Version,
        lib_install_folder_name: str,
        version_folder_name: str,
        lib_files: set[str],
        licence_files: set[str] | None = None,
        licence_type: str | None = None,
    ):
        super().__init__(name, version, licence_files, licence_type)
        self.lib_install_dir: Path = self.lib_dir / lib_install_folder_name
        self.version_folder_name: str = version_folder_name.format(version=self.version)
        self.version_install_dir: Path = self.lib_install_dir / self.version_folder_name
        self.lib_files: set[str] = {
            lib_file.format(version=self.version) for lib_file in lib_files
        }

    @property
    def check_files(self) -> set[Path]:
        return {
            self.version_install_dir / lib_file for lib_file in self.lib_files
        }.union(
            {
                self.version_install_dir / licence_file
                for licence_file in self.licence_files
            }
            if self.licence_files
            else {}
        )


class WebLibArchiveInstaller(WebLibInstaller):
    """A utility class to install web libraries from archives."""

    def __init__(
        self,
        name: str,
        version: Version,
        lib_install_folder_name: str,
        version_folder_name: str,
        lib_files: set[str],
        archive_url: str,
        archive_filename: str,
        archive_sub_folder_name: str | None = None,
        licence_files: set[str] | None = None,
        licence_type: str | None = None,
    ):
        super().__init__(
            name,
            version,
            lib_install_folder_name,
            version_folder_name,
            lib_files,
            licence_files,
            licence_type,
        )
        self.archive_sub_folder_name = (
            archive_sub_folder_name or self.version_folder_name
        )
        self.archive_url: str = archive_url.format(version=self.version)
        self.archive_filename: str = archive_filename.format(version=self.version)

    def install(self) -> bool:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir: Path = Path(tmpdir)
            self.version_install_dir.mkdir(parents=True, exist_ok=True)
            archive_file: Path = tmp_dir / self.archive_filename
            self.download_file(self.archive_url, archive_file)
            print_interactive_info(f'Installing to {self.version_install_dir}...')
            shutil.unpack_archive(archive_file, tmp_dir)
            # Copy requested library files
            for lib_file in self.lib_files:
                src_file: Path = tmp_dir / self.archive_sub_folder_name / lib_file
                dst_file: Path = self.version_install_dir / lib_file
                dst_dir: Path = dst_file.parent
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(src_file, dst_dir)

            # Copy specified licence files preserving their relative paths
            if self.licence_files:
                extracted_licence_files = []
                for licence_file in self.licence_files:
                    # Handle licence file paths within the archive
                    src_file: Path = tmp_dir / self.version_folder_name / licence_file
                    if src_file.exists():
                        # Preserve the full relative path for the destination
                        dst_file: Path = self.version_install_dir / licence_file
                        dst_dir: Path = dst_file.parent
                        dst_dir.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(src_file, dst_file)
                            extracted_licence_files.append(licence_file)
                            logger.debug(
                                f'Extracted licence file: {licence_file} -> {licence_file} for {self.name}'
                            )
                        except Exception as e:
                            logger.warning(
                                f'Failed to copy licence file {licence_file}: {e}'
                            )
                    else:
                        logger.warning(
                            f'Licence file not found in archive: {licence_file} for {self.name}'
                        )

                if extracted_licence_files:
                    print_interactive_info(
                        f'Extracted licence files for {self.name}: {extracted_licence_files}'
                    )

            print_interactive_success('Done.')
            return self.is_installed


class WebLibFileInstaller(WebLibInstaller):
    def __init__(
        self,
        name: str,
        version: Version,
        url: str,
        lib_file: str,
        licence_files: set[str] | None = None,
        licence_type: str | None = None,
    ):
        super().__init__(
            name,
            version,
            '',
            '',
            {
                lib_file,
            },
            licence_files,
            licence_type,
        )
        self.url: str = url.format(version=self.version)

    def install(self) -> bool:
        check_file: Path = next(iter(self.check_files))
        check_file.parent.mkdir(parents=True, exist_ok=True)
        print_interactive_info(f'Downloading {self.url} to {check_file}...')
        response = requests.get(self.url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(check_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print_interactive_success('Done.')
        return self.is_installed


@dataclass
class SystemHandler:
    executable_dir: str
    executable_filename: str
    archive_filename: str


class ExecutableInstaller(ToolInstaller, ABC):
    """Abstract installer for tools containing a executable"""

    def __init__(self, licence_files: set[str] | None = None):
        super().__init__(self._name, self._version, licence_files)

    @property
    @abstractmethod
    def _name(self) -> str: ...

    @property
    @abstractmethod
    def _version(self) -> Version: ...

    @cached_property
    @abstractmethod
    def system_handler(self) -> SystemHandler:
        """System specific variables."""

    @property
    def executable_path(self) -> Path:
        """Path to the executable file."""
        return self.executable_dir / self.system_handler.executable_filename

    @property
    def executable_dir(self) -> Path:
        return (
            BASE_DIR
            / 'tools'
            / self.name
            / f'v{self.version}'
            / self.system_handler.executable_dir
        )

    @property
    def install_dir(self) -> Path:
        return self.executable_dir.parent

    @property
    def check_files(self) -> set[Path]:
        return {
            self.executable_path,
        }

    @property
    def files_to_sign(self) -> list[Path]:
        """Returns the files that should be signed."""
        extensions_to_sign: set[str] = {
            'exe',
        }
        files: list[Path] = []
        for extension in extensions_to_sign:
            files += [f for f in self.install_dir.glob(f'**/*.{extension}')]
        return files


class BbpPairingsInstaller(ExecutableInstaller):
    def __init__(self):
        # Specify which files in the archive are licence files
        super().__init__(
            licence_files={
                'LICENSE.txt',
                'Apache-2.0.txt',
            }
        )

    @property
    def _name(self) -> str:
        return 'bbpPairings'

    @property
    def _version(self) -> Version:
        """BbpPairings main project version."""
        return Version('6.0.0')

    @property
    def _sc_sub_version(self) -> int | None:
        """Sharly Chess subversion of the BbpPairings release."""
        return 2

    @property
    def _full_version(self) -> str:
        version = f'{self.version}-sc'
        if self._sc_sub_version:
            version += str(self._sc_sub_version)
        return version

    @cached_property
    def system_handler(self) -> SystemHandler:
        match sys.platform:
            case 'win32':
                return SystemHandler(
                    executable_dir=f'bbpPairings-v{self._full_version}',
                    executable_filename='bbpPairings-windows.exe',
                    archive_filename='bbpPairings-Windows.zip',
                )
            case 'darwin':
                return SystemHandler(
                    executable_dir=f'bbpPairings-v{self._full_version}',
                    executable_filename='bbpPairings-macos',
                    archive_filename='bbpPairings-macOS.zip',
                )
            case 'linux':
                # Detect architecture for Linux
                # Allow override via BUILD_ARCH environment variable (useful for cross-compilation/QEMU)
                build_arch = os.environ.get('BUILD_ARCH')
                if build_arch:
                    machine = build_arch.lower()
                else:
                    machine = platform.machine().lower()
                if machine in ('aarch64', 'arm64'):
                    archive_filename = 'bbpPairings-Linux-ARM64.zip'
                    executable_filename = 'bbpPairings-linux-arm64'
                elif machine in ('x86_64', 'amd64'):
                    archive_filename = 'bbpPairings-Linux-x86_64.zip'
                    executable_filename = 'bbpPairings-linux-x86_64'
                else:
                    raise OSError(
                        f'{self._name} is not available for Linux architecture: {machine}'
                    )
                return SystemHandler(
                    executable_dir=f'bbpPairings-v{self.version}',
                    executable_filename=executable_filename,
                    archive_filename=archive_filename,
                )
            case _:
                raise NotImplementedError(f'{sys.platform=}')

    @property
    def install_dir(self) -> Path:
        return self.executable_dir

    def install(self) -> bool:
        archive_filename = self.system_handler.archive_filename

        build_url: str = (
            'https://github.com/Sharly-Chess/bbpPairings'
            f'/releases/download/v{self._full_version}/{archive_filename}'
        )
        self.install_dir.mkdir(parents=True, exist_ok=True)
        archive_path: Path = self.install_dir / archive_filename
        self.download_file(build_url, archive_path)
        self.install_archive_and_delete(archive_path, self.install_dir)

        # Set execute permissions for macOS and Linux
        match sys.platform:
            case 'darwin' | 'linux':
                if self.executable_path.exists():
                    # Add execute permission for owner, group, and others
                    current_permissions = self.executable_path.stat().st_mode
                    new_permissions = (
                        current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                    )
                    self.executable_path.chmod(new_permissions)
            case 'win32':
                pass
            case _:
                raise NotImplementedError(f'{sys.platform=}')

        return self.is_installed


class PapiConverterInstaller(ExecutableInstaller):
    def __init__(self):
        # Specify which files in the archive are licence files
        super().__init__()

    @cached_property
    def system_handler(self) -> SystemHandler:
        match sys.platform:
            case 'win32':
                return SystemHandler(
                    executable_dir='papi-converter-windows',
                    executable_filename='papi-converter.bat',
                    archive_filename='papi-converter-windows.zip',
                )
            case 'darwin':
                return SystemHandler(
                    executable_dir='papi-converter-mac',
                    executable_filename='papi-converter',
                    archive_filename='papi-converter-mac.tar.gz',
                )
            case 'linux':
                # Detect architecture for Linux
                # Allow override via BUILD_ARCH environment variable (useful for cross-compilation/QEMU)
                build_arch = os.environ.get('BUILD_ARCH')
                if build_arch:
                    machine = build_arch.lower()
                else:
                    machine = platform.machine().lower()
                if machine in ('aarch64', 'arm64'):
                    archive_filename = 'papi-converter-linux-arm64.tar.gz'
                    executable_dir = 'papi-converter-linux-arm64'
                elif machine in ('x86_64', 'amd64'):
                    archive_filename = 'papi-converter-linux-x86_64.tar.gz'
                    executable_dir = 'papi-converter-linux-x86_64'
                else:
                    raise OSError(
                        f'{self._name} is not available for Linux architecture: {machine}'
                    )
                return SystemHandler(
                    executable_dir=executable_dir,
                    executable_filename='papi-converter',
                    archive_filename=archive_filename,
                )
            case _:
                raise NotImplementedError(f'{sys.platform=}')

    @property
    def _name(self) -> str:
        return 'papi-converter'

    @property
    def _version(self) -> Version:
        return Version('1.4.0')

    def install(self) -> bool:
        archive_filename = self.system_handler.archive_filename
        build_url: str = (
            'https://github.com/Sharly-Chess/papi-converter/'
            f'releases/download/v{self.version}/{archive_filename}'
        )
        self.install_dir.mkdir(parents=True, exist_ok=True)
        archive_path: Path = self.install_dir / archive_filename
        self.download_file(build_url, archive_path)
        self.install_archive_and_delete(archive_path, self.install_dir)
        return self.is_installed


class UACInstaller(ExecutableInstaller):
    def __init__(self):
        super().__init__()

    @cached_property
    def system_handler(self) -> SystemHandler:
        match sys.platform:
            case 'win32':
                return SystemHandler(
                    executable_dir=f'sharly-chess-uac-{self.version}',
                    executable_filename=f'sharly-chess-uac-{self.version}.exe',
                    archive_filename=f'sharly-chess-uac-{self.version}.zip',
                )
            case _:
                raise NotImplementedError(
                    f'{self._name} is not available for system [{sys.platform}]'
                )

    @property
    def _name(self) -> str:
        return 'sharly-chess-uac'

    @property
    def _version(self) -> Version:
        return Version('1.1.3')

    def install(self) -> bool:
        archive_filename = self.system_handler.archive_filename
        build_url: str = (
            'https://github.com/Sharly-Chess/sharly-chess-uac/'
            f'releases/download/{self.version}/{archive_filename}'
        )
        self.install_dir.mkdir(parents=True, exist_ok=True)
        archive_path: Path = self.install_dir / archive_filename
        self.download_file(build_url, archive_path)
        self.install_archive_and_delete(archive_path, self.install_dir)
        return self.is_installed
