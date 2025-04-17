import shutil
from abc import ABC
from pathlib import Path

import requests

from common import experimental_features_enabled, REQUEST_TIMEOUT, TMP_DIR, BASE_DIR
from common.i18n import _
from common.logger import (
    print_interactive_info,
    print_interactive_success,
    print_interactive_error,
)
from common.papi_web_config import PapiWebConfig
from common.tool_installer import ToolInstaller
from pairing.bbp_pairings_installer import BbpPairingsInstaller


class WebLibInstaller(ToolInstaller, ABC):
    """A utility class to install web libraries."""

    lib_dir: Path = BASE_DIR / 'src' / 'web' / 'static' / 'lib'


class BootstrapInstaller(WebLibInstaller, ABC):
    lib_files: list[Path] = [
        Path() / 'js' / 'bootstrap.bundle.min.js',
        Path() / 'js' / 'bootstrap.bundle.min.js.map',
        Path() / 'css' / 'bootstrap.min.css',
        Path() / 'css' / 'bootstrap.min.css.map',
    ]

    def __init__(self):
        super().__init__('Bootstrap', PapiWebConfig.bootstrap_version)
        self.lib_install_dir: Path = self.lib_dir / 'bootstrap'
        self.version_folder_name: str = f'bootstrap-{self.version}-dist'
        self.version_install_dir: Path = self.lib_install_dir / self.version_folder_name

    @property
    def check_file(self) -> Path:
        return self.version_install_dir / self.lib_files[0]

    def install(self) -> bool:
        build_filename: str = f'bootstrap-{self.version}-dist.zip'
        build_url: str = f'https://github.com/twbs/bootstrap/releases/download/v{self.version}/{build_filename}'
        self.version_install_dir.mkdir(parents=True, exist_ok=True)
        archive_file: Path = TMP_DIR / build_filename
        print_interactive_info(f'Downloading {build_url}...')
        response = requests.get(build_url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(archive_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print_interactive_success('Done.')
        print_interactive_info(f'Installing to {self.version_install_dir}...')
        shutil.unpack_archive(archive_file, TMP_DIR)
        archive_dir: Path = TMP_DIR / self.version_folder_name
        for lib_file in self.lib_files:
            src_file: Path = TMP_DIR / self.version_folder_name / lib_file
            dst_file: Path = self.version_install_dir / lib_file
            dst_dir: Path = dst_file.parent
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(src_file, dst_dir)
        archive_file.unlink(missing_ok=True)
        shutil.rmtree(archive_dir)
        print_interactive_success('Done.')
        return self.is_installed


class BootstrapIconsInstaller(WebLibInstaller, ABC):
    lib_files: list[Path] = [
        Path() / 'font' / 'bootstrap-icons.min.css',
        Path() / 'font' / 'fonts' / 'bootstrap-icons.woff',
        Path() / 'font' / 'fonts' / 'bootstrap-icons.woff2',
    ]

    def __init__(self):
        super().__init__('Bootstrap icons', PapiWebConfig.bootstrap_icons_version)
        self.lib_install_dir: Path = self.lib_dir / 'bootstrap-icons'
        self.version_folder_name: str = f'bootstrap-icons-{self.version}'
        self.version_install_dir: Path = self.lib_install_dir / self.version_folder_name

    @property
    def check_file(self) -> Path:
        return self.version_install_dir / 'font' / 'bootstrap-icons.min.css'

    def install(self) -> bool:
        build_filename: str = f'bootstrap-icons-{self.version}.zip'
        build_url: str = f'https://github.com/twbs/icons/releases/download/v{self.version}/{build_filename}'
        self.version_install_dir.mkdir(parents=True, exist_ok=True)
        archive_file: Path = TMP_DIR / build_filename
        print_interactive_info(f'Downloading {build_url}...')
        response = requests.get(build_url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(archive_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print_interactive_success('Done.')
        print_interactive_info(f'Installing to {self.version_install_dir}...')
        shutil.unpack_archive(archive_file, TMP_DIR)
        archive_dir: Path = TMP_DIR / self.version_folder_name
        for lib_file in self.lib_files:
            src_file: Path = TMP_DIR / self.version_folder_name / lib_file
            dst_file: Path = self.version_install_dir / lib_file
            dst_dir: Path = dst_file.parent
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(src_file, dst_dir)
        archive_file.unlink(missing_ok=True)
        shutil.rmtree(archive_dir)
        print_interactive_success('Done.')
        return self.is_installed


class InstallationChecker:
    """A class to check the installation of all the needed tools and libs."""

    @staticmethod
    def check() -> bool:
        error: bool = False
        installers: list[ToolInstaller] = (
            [
                BbpPairingsInstaller(),
            ]
            if experimental_features_enabled()
            else []
        ) + [
            BootstrapInstaller(),
            BootstrapIconsInstaller(),
        ]
        for installer in installers:
            if not installer.check_installation():
                error = True
        if error:
            print_interactive_error(_('Incorrect installation, exiting.'))
        return not error
