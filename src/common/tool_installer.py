import platform
import stat
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import requests
from packaging.version import Version

from common import DEVEL_ENV, REQUEST_TIMEOUT, BASE_DIR, TMP_DIR
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
    Classes inheriting from this class should just implement methods check_file() and install()."""

    def __init__(
        self,
        name: str,
        version: Version,
        licence_files: list[str] | None = None,
        licence_type: str | None = None,
    ):
        self.name: str = name
        self.version: Version = version
        self.licence_files = licence_files or []
        self.licence_type = licence_type

    @property
    @abstractmethod
    def check_file(self) -> Path:
        """Returns the path of the file to check for a correct installation."""

    @property
    def is_installed(self) -> bool:
        """Returns True if correctly installed, False otherwise."""
        return self.check_file.exists()

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
        lib_files: list[str],
        licence_files: list[str] | None = None,
    ):
        super().__init__(name, version, licence_files)
        self.lib_install_dir: Path = self.lib_dir / lib_install_folder_name
        self.version_folder_name: str = version_folder_name.format(version=self.version)
        self.version_install_dir: Path = self.lib_install_dir / self.version_folder_name
        self.lib_files: list[str] = [
            lib_file.format(version=self.version) for lib_file in lib_files
        ]

    @property
    def check_file(self) -> Path:
        return self.version_install_dir / self.lib_files[0]


class WebLibArchiveInstaller(WebLibInstaller, ABC):
    """A utility class to install web libraries from archives."""

    def __init__(
        self,
        name: str,
        version: Version,
        lib_install_folder_name: str,
        version_folder_name: str,
        lib_files: list[str],
        archive_url: str,
        archive_filename: str,
        licence_files: list[str] | None = None,
        licence_type: str | None = None,
    ):
        super().__init__(
            name,
            version,
            lib_install_folder_name,
            version_folder_name,
            lib_files,
            licence_files,
        )
        self.archive_url = archive_url.format(version=self.version)
        self.archive_filename = archive_filename.format(version=self.version)
        self.licence_type = licence_type

    def install(self) -> bool:
        self.version_install_dir.mkdir(parents=True, exist_ok=True)
        archive_file: Path = TMP_DIR / self.archive_filename
        self.download_file(self.archive_url, archive_file)
        print_interactive_info(f'Installing to {self.version_install_dir}...')
        shutil.unpack_archive(archive_file, TMP_DIR)
        archive_dir: Path = TMP_DIR / self.version_folder_name
        # Copy requested library files
        for lib_file in self.lib_files:
            src_file: Path = TMP_DIR / self.version_folder_name / lib_file
            dst_file: Path = self.version_install_dir / lib_file
            dst_dir: Path = dst_file.parent
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(src_file, dst_dir)

        # Copy specified licence files preserving their relative paths
        if self.licence_files:
            extracted_licence_files = []
            for licence_file in self.licence_files:
                # Handle licence file paths within the archive
                src_file: Path = TMP_DIR / self.version_folder_name / licence_file
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

        archive_file.unlink(missing_ok=True)
        shutil.rmtree(archive_dir)
        print_interactive_success('Done.')
        return self.is_installed


class WebLibFileInstaller(WebLibInstaller):
    def __init__(
        self,
        name: str,
        version: Version,
        url: str,
        lib_file: str,
        licence_type: str | None = None,
    ):
        super().__init__(
            name,
            version,
            '',
            '',
            [
                lib_file,
            ],
        )
        self.url: str = url.format(version=self.version)
        self.licence_type = licence_type

    def install(self) -> bool:
        self.check_file.parent.mkdir(parents=True, exist_ok=True)
        print_interactive_info(f'Downloading {self.url} to {self.check_file}...')
        response = requests.get(self.url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(self.check_file, 'wb') as f:
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

    def __init__(self, licence_files: list[str] | None = None):
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
    def check_file(self) -> Path:
        return self.executable_path


class BbpPairingsInstaller(ExecutableInstaller):
    def __init__(self):
        # Specify which files in the archive are licence files
        licence_files = ['LICENSE.txt', 'Apache-2.0.txt']
        super().__init__(licence_files=licence_files)

    @property
    def _name(self) -> str:
        return 'bbpPairings'

    @property
    def _version(self) -> Version:
        return Version('5.0.1')

    @cached_property
    def system_handler(self) -> SystemHandler:
        system = platform.system()
        match system:
            case 'Windows':
                return SystemHandler(
                    executable_dir=f'bbpPairings-v{self.version}',
                    executable_filename='bbpPairings-windows.exe',
                    archive_filename='bbpPairings-Windows.zip',
                )
            case 'Darwin':
                return SystemHandler(
                    executable_dir=f'bbpPairings-v{self.version}',
                    executable_filename='bbpPairings-macos',
                    archive_filename='bbpPairings-macOS.zip',
                )
            case 'Linux':
                return SystemHandler(
                    executable_dir=f'bbpPairings-v{self.version}',
                    executable_filename='bbpPairings-linux',
                    archive_filename='bbpPairings-Linux.zip',
                )
            case _:
                raise OSError(
                    f'{self._name} is not available for the current system: {system}'
                )

    @property
    def install_dir(self) -> Path:
        return self.executable_dir

    def install(self) -> bool:
        archive_filename = self.system_handler.archive_filename
        build_url: str = (
            'https://github.com/Sharly-Chess/bbpPairings'
            f'/releases/download/v{self.version}-sc/{archive_filename}'
        )
        self.install_dir.mkdir(parents=True, exist_ok=True)
        archive_path: Path = self.install_dir / archive_filename
        self.download_file(build_url, archive_path)
        self.install_archive_and_delete(archive_path, self.install_dir)

        # Set execute permissions for macOS and Linux
        system = platform.system()
        if system in ['Darwin', 'Linux']:
            if self.executable_path.exists():
                # Add execute permission for owner, group, and others
                current_permissions = self.executable_path.stat().st_mode
                new_permissions = (
                    current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
                self.executable_path.chmod(new_permissions)

        return self.is_installed


class PapiConverterInstaller(ExecutableInstaller):
    def __init__(self):
        # Specify which files in the archive are licence files
        super().__init__()

    @cached_property
    def system_handler(self) -> SystemHandler:
        system = platform.system()
        match system:
            case 'Windows':
                return SystemHandler(
                    executable_dir='papi-converter-windows',
                    executable_filename='papi-converter.exe',
                    archive_filename='papi-converter-windows.zip',
                )
            case 'Darwin':
                return SystemHandler(
                    executable_dir='papi-converter-mac',
                    executable_filename='papi-converter',
                    archive_filename='papi-converter-mac.tar.gz',
                )
            case _:
                raise OSError(
                    f'{self._name} is not available for the current system: {system}'
                )

    @property
    def _name(self) -> str:
        return 'papi-converter'

    @property
    def _version(self) -> Version:
        return Version('1.1.6')

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
