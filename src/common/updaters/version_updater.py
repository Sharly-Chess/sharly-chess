import json
import re
import sys
import os
import platform
import subprocess
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from packaging.version import Version
from requests import get
from requests.exceptions import RequestException  # pylint: disable=redefined-builtin

from common import BASE_DIR
from common.logger import (
    get_logger,
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
