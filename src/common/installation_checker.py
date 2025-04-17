import shutil
from abc import ABC
from pathlib import Path

import requests
from packaging.version import Version

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

    def __init__(
        self,
        name: str,
        version: Version,
        lib_install_folder_name: str,
        version_folder_name: str,
        lib_files: list[str],
    ):
        super().__init__(name, version)
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
    ):
        super().__init__(
            name, version, lib_install_folder_name, version_folder_name, lib_files
        )
        self.archive_url = archive_url.format(version=self.version)
        self.archive_filename = archive_filename.format(version=self.version)

    def install(self) -> bool:
        self.version_install_dir.mkdir(parents=True, exist_ok=True)
        archive_file: Path = TMP_DIR / self.archive_filename
        self.download_file(self.archive_url, archive_file)
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


class FileInstaller(WebLibInstaller):
    def __init__(
        self,
        name: str,
        version: Version,
        url: str,
        lib_file: str,
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


class InstallationChecker:
    """A class to check the installation of all the needed tools and libs."""

    web_lib_installers: list[WebLibInstaller] = [
        WebLibArchiveInstaller(
            'Bootstrap',
            PapiWebConfig.bootstrap_version,
            'bootstrap',
            'bootstrap-{version}-dist',
            [
                'js/bootstrap.bundle.min.js',
                'js/bootstrap.bundle.min.js.map',
                'css/bootstrap.min.css',
                'css/bootstrap.min.css.map',
            ],
            'https://github.com/twbs/bootstrap/releases/download/v{version}/bootstrap-{version}-dist.zip',
            'bootstrap-{version}-dist.zip',
        ),
        WebLibArchiveInstaller(
            'Bootstrap icons',
            PapiWebConfig.bootstrap_icons_version,
            'bootstrap-icons',
            'bootstrap-icons-{version}',
            [
                'font/bootstrap-icons.min.css',
                'font/fonts/bootstrap-icons.woff',
                'font/fonts/bootstrap-icons.woff2',
            ],
            'https://github.com/twbs/icons/releases/download/v{version}/bootstrap-icons-{version}.zip',
            'bootstrap-icons-{version}.zip',
        ),
        WebLibArchiveInstaller(
            'Sortable',
            PapiWebConfig.sortable_version,
            'Sortable',
            'Sortable-{version}',
            [
                'Sortable.min.js',
            ],
            'https://github.com/SortableJS/Sortable/archive/refs/tags/{version}.zip',
            'Sortable-{version}.zip',
        ),
        WebLibArchiveInstaller(
            'jsTree',
            PapiWebConfig.jstree_version,
            'jstree',
            'jstree-{version}',
            [
                'dist/jstree.min.js',
                'dist/themes/default/style.min.css',
                'dist/themes/default/32px.png',
                'dist/themes/default/40px.png',
                'dist/themes/default/throbber.gif',
            ],
            'https://github.com/vakata/jstree/archive/refs/tags/{version}.zip',
            'jstree-{version}.zip',
        ),
        FileInstaller(
            'HTMX',
            PapiWebConfig.htmx_version,
            'https://unpkg.com/htmx.org@{version}/dist/htmx.min.js',
            'htmx/htmx-{version}/htmx.min.js',
        ),
        FileInstaller(
            'HTMX Preload extension',
            PapiWebConfig.htmx_preload_version,
            'https://unpkg.com/htmx-ext-preload@{version}',
            'htmx/preload-{version}/preload.js',
        ),
        FileInstaller(
            'HTMX Remove me extension',
            PapiWebConfig.htmx_remove_me_version,
            'https://unpkg.com/htmx-ext-remove-me@{version}',
            'htmx/remove-me-{version}/remove-me.js',
        ),
        FileInstaller(
            'HTMX Multi swap extension',
            PapiWebConfig.htmx_multi_swap_version,
            'https://unpkg.com/htmx-ext-multi-swap@{version}',
            'htmx/multi-swap-{version}/multi-swap.js',
        ),
        FileInstaller(
            'jQuery',
            PapiWebConfig.jquery_version,
            'https://code.jquery.com/jquery-{version}.min.js',
            'jquery/jquery-{version}.min.js',
        ),
    ]

    @classmethod
    def check(cls) -> bool:
        error: bool = False
        installers: list[ToolInstaller] = (
            [
                BbpPairingsInstaller(),
            ]
            if experimental_features_enabled()
            else []
        ) + cls.web_lib_installers
        for installer in installers:
            if not installer.check_installation():
                error = True
        if error:
            print_interactive_error(_('Incorrect installation, exiting.'))
        return not error
