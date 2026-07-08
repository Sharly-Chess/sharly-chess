import json
import re
import sys
import os
import platform
from datetime import datetime
from json import JSONDecodeError
from typing import Any

from packaging.version import Version
from requests import get
from requests.exceptions import RequestException  # pylint: disable=redefined-builtin

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
            if cls.get_asset_name(version) not in asset_names:
                # Version not supported for direct update (possibly)
                continue
            logger.info('Most recent release found: [%s].', str(version))
            cls.LATEST_VERSION = version
            break
        cls.LATEST_VERSION_SEARCHED_AT = datetime.now()

    @classmethod
    def get_asset_name(cls, version: Version) -> str:
        """Name of the asset to download in order to install a new version."""

        if sys.platform == 'win32':
            return f'Sharly Chess Updater {version}.exe'
        if sys.platform == 'darwin':
            suffix = 'macos.dmg'
        else:
            # Detect architecture for Linux
            # Allow override via BUILD_ARCH environment variable (useful for cross-compilation/QEMU)
            build_arch = os.environ.get('BUILD_ARCH')
            if build_arch:
                machine = build_arch.lower()
            else:
                machine = platform.machine().lower()
            if machine in ('aarch64', 'arm64'):
                suffix = 'linux-arm64.flatpak'
            elif machine in ('x86_64', 'amd64'):
                suffix = 'linux-x86_64.flatpak'
            else:
                raise NotImplementedError(f'{machine=}')
        return f'sharly-chess-{version}-{suffix}'

    @classmethod
    def get_asset_url(cls, version: Version) -> str:
        base_url = 'https://github.com/Sharly-Chess/sharly-chess/releases/download'
        name = cls.get_asset_name(version)
        return f'{base_url}/{name}/{version}'
