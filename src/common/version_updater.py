import json
import re
import shutil
import sys
import tempfile
import zipfile
import os
import platform
import subprocess
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from packaging.version import Version
from requests import Response, get
from requests.exceptions import RequestException  # pylint: disable=redefined-builtin

from antivirus.control import search_missing_files
from common import BASE_DIR
from common.i18n import _
from common.logger import (
    get_logger,
    print_interactive_message,
    quit_app,
)
from common.network import NetworkMonitor

logger = get_logger()

UPDATER_VERSION = Version('1')


class VersionUpdater:
    LATEST_VERSION: Version | None = None
    LATEST_VERSION_SEARCHED_AT: datetime | None = None

    @classmethod
    def _get_github_releases(cls) -> list[dict[str, Any]] | None:
        url = 'https://api.github.com/repos/sharly-chess/sharly-chess/releases'
        try:
            response = get(url, allow_redirects=True, timeout=5)
            response.raise_for_status()
        except RequestException as ex:
            logger.warning('An error occurred while requesting GitHub.')
            logger.debug('Failed to read [%s]: [%s].', url, ex)
            return None

        data: str = response.content.decode()
        logger.debug(
            'Data received (%d bytes, code %d)',
            len(data),
            response.status_code,
        )
        try:
            return json.loads(data)
        except JSONDecodeError as ex:
            logger.warning('Invalid response from GitHub: [%s].', ex)
            return None

    @classmethod
    def search_for_latest_version(cls, check_beta: bool):
        """Retrieves the latest version from the GitHub repository."""

        # Test override: pretend a given version is the latest, skipping the
        # network. Lets the update/install path be exercised offline (pair with
        # SHARLY_CHESS_APPCAST_URL to point Sparkle at a local appcast).
        fake_latest = os.environ.get('SHARLY_CHESS_FAKE_LATEST_VERSION')
        if fake_latest:
            cls.LATEST_VERSION = Version(fake_latest)
            cls.LATEST_VERSION_SEARCHED_AT = datetime.now()
            logger.warning(
                'Using fake latest version [%s] (test override).', fake_latest
            )
            return

        if not NetworkMonitor.connected(use_cached=False):
            logger.warning(
                'Not connected, can not search for Sharly Chess newer releases.'
            )
            return
        logger.info('Looking for the latest release on GitHub...')

        entries = cls._get_github_releases()
        if entries is None:
            return

        assets_by_version: dict[Version, list[dict]] = {}
        for entry in entries:
            tag_name: str = entry['tag_name']
            if matches := re.match(r'^(\d+\.\d+\.\d+)$', tag_name):
                version = Version(matches.group(1))
            elif matches := re.match(
                r'^(\d+.\d+.\d+(a\d+|b\d+|rc\d+))$',
                tag_name,
            ):
                if check_beta:
                    version = Version(matches.group(1))
                else:
                    continue
            else:
                continue
            if entry.get('draft'):
                logger.debug('Release [%s] is draft, ignored.', version)
                continue
            assets_by_version[version] = entry.get('assets', [])

        for version in sorted(assets_by_version, reverse=True):
            asset_names = [asset.get('name') for asset in assets_by_version[version]]
            if cls._get_asset_name(version) not in asset_names:
                # Version not supported for direct update (possibly)
                continue
            logger.info('Most recent release found: [%s].', str(version))
            cls.LATEST_VERSION = version
            break
        cls.LATEST_VERSION_SEARCHED_AT = datetime.now()

    @staticmethod
    def _get_asset_suffix() -> str:
        match sys.platform:
            case 'win32':
                return 'windows.zip'
            case 'darwin':
                return 'macos.dmg'
            case 'linux':
                # Detect architecture for Linux
                # Allow override via BUILD_ARCH environment variable (useful for cross-compilation/QEMU)
                build_arch = os.environ.get('BUILD_ARCH')
                if build_arch:
                    machine = build_arch.lower()
                else:
                    machine = platform.machine().lower()
                if machine in ('aarch64', 'arm64'):
                    return 'linux-arm64.flatpak'
                elif machine in ('x86_64', 'amd64'):
                    return 'linux-x86_64.flatpak'
        raise NotImplementedError(f'{sys.platform=}')

    @classmethod
    def _get_asset_name(cls, version: Version) -> str:
        """Name of the asset to download in order to install a new version."""
        return f'sharly-chess-{version}-{cls._get_asset_suffix()}'

    @classmethod
    def _get_asset_url(cls, version: Version):
        """URL of the asset to download in order to install a new version."""
        base_url = 'https://github.com/Sharly-Chess/sharly-chess/releases/download'
        asset = cls._get_asset_name(version)
        return f'{base_url}/{version}/{asset}'

    @classmethod
    def appcast_url(cls, version: Version) -> str:
        """URL of the per-release Sparkle appcast asset for *version*.

        Each release attaches its own ``appcast.xml`` (signed in CI); the macOS
        Sparkle updater is pointed at this at runtime instead of a static feed.

        For local testing, ``SHARLY_CHESS_APPCAST_URL`` overrides the URL (e.g.
        a ``http://localhost:8000/appcast.xml`` served from a folder), so the
        full Sparkle flow can be exercised without an online release.
        """
        override = os.environ.get('SHARLY_CHESS_APPCAST_URL')
        if override:
            return override
        base_url = 'https://github.com/Sharly-Chess/sharly-chess/releases/download'
        return f'{base_url}/{version}/appcast.xml'

    @staticmethod
    def version_updater_path() -> Path:
        ext = 'exe' if sys.platform == 'win32' else 'app'
        return BASE_DIR / 'bin' / f'updater-{UPDATER_VERSION}.{ext}'

    @classmethod
    def run_version_updater(cls, version: Version):
        kwargs: dict[str, Any] = {}
        if sys.platform == 'win32':
            kwargs['creationflags'] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs['start_new_session'] = True
        exe_path = cls.version_updater_path()
        args = [str(exe_path), '--version', str(version)]
        restart_process = subprocess.Popen(args, **kwargs)
        restart_process.wait()

    @staticmethod
    def _install_new_version(version: Version, download_url: str) -> str | None:
        """Install the new stable version at the same directory level.
        Returns an error message on failure, None on success."""
        new_version_dir: Path = Path('..') / f'sharly-chess-{version}'
        if new_version_dir.exists():
            logger.error(
                'Directory [%s] already exists.',
                new_version_dir.resolve(),
            )
            return _('Directory [{folder}] already exists.').format(
                folder=new_version_dir.resolve(),
            )
        else:
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_dir: Path = Path(tmpdir)
                    logger.info(
                        'Downloading release [%s] from GitHub ([%s])...',
                        version,
                        download_url,
                    )
                    response: Response = get(
                        download_url, allow_redirects=True, timeout=10
                    )
                    response.raise_for_status()
                    if not response:
                        logger.error('No response from GitHub.')
                        return _('No response from GitHub.')
                    if response.status_code != 200:
                        logger.error(
                            'Downloading failed with code [%d].', response.status_code
                        )
                        return _('Downloading failed with code [{code}].').format(
                            code=response.status_code
                        )
                    # Determine downloaded file name based on platform
                    match sys.platform:
                        case 'win32':
                            downloaded_file = (
                                tmp_dir / f'sharly-chess-{version}-windows.zip'
                            )
                        case 'darwin':
                            downloaded_file = (
                                tmp_dir / f'sharly-chess-{version}-macos.dmg'
                            )
                        case 'linux':
                            build_arch = os.environ.get('BUILD_ARCH')
                            if build_arch:
                                machine = build_arch.lower()
                            else:
                                machine = platform.machine().lower()
                            if machine in ('aarch64', 'arm64'):
                                downloaded_file = (
                                    tmp_dir / f'sharly-chess-{version}-linux-arm64.zip'
                                )
                            elif machine in ('x86_64', 'amd64'):
                                downloaded_file = (
                                    tmp_dir / f'sharly-chess-{version}-linux-x86_64.zip'
                                )
                        case _:
                            raise NotImplementedError(f'{sys.platform=}')

                    downloaded_file.write_bytes(response.content)
                    logger.debug('File downloaded: [%s].', downloaded_file)

                    match sys.platform:
                        case 'win32':
                            # For Windows: Unzip the file
                            new_version_dir.mkdir()
                            with zipfile.ZipFile(downloaded_file, 'r') as zip_ref:
                                zip_ref.extractall(new_version_dir)
                            if error_message := search_missing_files(
                                folder=new_version_dir, delete_control_file=False
                            ):
                                logger.error(error_message)
                                return _('Some files are missing.')
                        case 'darwin':
                            # For Mac: Handle the DMG file
                            mount_point = tmp_dir / f'mount-{version}'
                            try:
                                # Mount the DMG
                                subprocess.run(
                                    [
                                        'hdiutil',
                                        'attach',
                                        str(downloaded_file),
                                        '-mountpoint',
                                        str(mount_point),
                                    ],
                                    check=True,
                                )
                                dmg_content = list(mount_point.iterdir())
                                if len(dmg_content) == 1 and dmg_content[0].is_dir():
                                    # Copy the folder from DMG to the new version directory
                                    # Use cp -R to preserve code signatures and extended attributes
                                    subprocess.run(
                                        [
                                            'cp',
                                            '-R',
                                            str(dmg_content[0]),
                                            str(new_version_dir.parent),
                                        ],
                                        check=True,
                                    )
                                else:
                                    logger.error(
                                        'DMG does not contain exactly one folder as expected.'
                                    )
                                    return _(
                                        'DMG does not contain exactly one folder as expected.'
                                    )
                            finally:
                                # Always try to unmount the DMG, even if copying failed
                                try:
                                    subprocess.run(
                                        ['hdiutil', 'detach', str(mount_point)],
                                        check=True,
                                    )
                                except subprocess.CalledProcessError:
                                    logger.warning(
                                        'Failed to unmount DMG at [%s]', mount_point
                                    )
                                # Clean up the mount point directory
                                if mount_point.exists():
                                    shutil.rmtree(mount_point, ignore_errors=True)
                        case 'linux':
                            # For Linux, just unzip
                            new_version_dir.mkdir()
                            with zipfile.ZipFile(downloaded_file, 'r') as zip_ref:
                                zip_ref.extractall(new_version_dir)
                        case _:
                            raise NotImplementedError(f'{sys.platform=}')

                logger.info(
                    'New release [%s] has been installed in [%s].',
                    version,
                    new_version_dir.resolve(),
                )
            except RequestException as ex:
                logger.exception('Failed to read [%s]: [%s].', download_url, ex)
                return _('Failed to read [{download_url}]: [{ex}].').format(
                    download_url=download_url, ex=ex
                )
            except subprocess.CalledProcessError as ex:
                logger.exception('Failed to process DMG file: [%s].', ex)
                return _('Failed to process DMG file: [{ex}].').format(ex=ex)
            except Exception as ex:
                logger.exception('Unexpected error during installation: [%s].', ex)
                return _('Unexpected error during installation: [{ex}].').format(ex=ex)

        if print_interactive_message(
            _('Release {version} has been installed in [{folder}].').format(
                version=version,
                folder=new_version_dir.absolute(),
            )
            + '\n\n'
            + _('Please launch the new version.'),
        ):
            quit_app()

        return None
