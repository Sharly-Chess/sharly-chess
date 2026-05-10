import filecmp
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from json import JSONDecodeError
from pathlib import Path
from time import time
from typing import Any

from antivirus.control import search_missing_files
from antivirus.detect import detect_antivirus_programs
from antivirus.programs.antivirus import Antivirus
from antivirus.protect import protect_from_antivirus_programs
from common import (
    SHARLY_CHESS_VERSION,
    TEST_ENV,
    EVENTS_FOLDER,
    DEVEL_ENV,
    EVENTS_DIR,
    TMP_DIR,
)
from common.i18n import _
from common.installation_checker import InstallationChecker
from common.logger import (
    get_logger,
    input_interactive_choices,
    input_interactive_yn,
    print_interactive_message,
    quit_app,
)
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.loader import EventLoader
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.local_source_database import LocalSourceDatabaseManager
from packaging.version import Version
from plugins.manager import plugin_manager
from requests import Response, get
from requests.exceptions import RequestException  # pylint: disable=redefined-builtin

logger = get_logger()


class Engine:
    def __init__(self):
        # before all the rest, initialize a SharlyChessConfig instance to set the language.
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        sharly_chess_config.load_and_set_env()
        logger.info(
            'Sharly Chess %s - %s - %s',
            sharly_chess_config.version,
            sharly_chess_config.copyright,
            sharly_chess_config.web_url,
        )
        logger.info('Locale: %s', sharly_chess_config.locale)
        more_recent_version: Version | None = None
        download_url: str | None = None
        if NetworkMonitor.connected(use_cached=False):
            logger.info('Checking Sharly Chess version...')
            more_recent_version, download_url = self._check_version()
        else:
            logger.warning(
                'Not connected, can not search for Sharly Chess newer releases.'
            )
        # Engines inherited this class should stop if this flag is True.
        self.error: bool = False
        if not InstallationChecker.check():
            self.error = True
            return
        if TEST_ENV:
            # skip all the upgrade stuff on TEST_ENV (recovering tests run the migrations explicitly)
            return
        if more_recent_version and download_url:
            if input_interactive_yn(
                _(
                    'Do you want to upgrade from [{old_version}] to [{new_version}]'
                ).format(
                    old_version=sharly_chess_config.version,
                    new_version=more_recent_version,
                ),
                yes_is_default=False,
            ):
                self.error = True
                if error_message := self._install_new_version(
                    more_recent_version, download_url
                ):
                    if print_interactive_message(
                        error_message
                        + '\n\n'
                        + _(
                            'Installation of release [{version}] failed, exiting.'
                        ).format(
                            version=more_recent_version,
                        )
                    ):
                        quit_app()
                return

        if not EventLoader().event_uniq_ids:
            logger.info(
                'No event database found, looking for old event databases in the current release...'
            )
            files: list[Path] = list(
                EVENTS_DIR.glob(f'*.{sharly_chess_config.event_database_old_ext}')
            )
            for file in files:
                event_uniq_id: str = file.stem
                logger.info('Recovering event [%s]...', event_uniq_id)
                event_database: EventDatabase = EventDatabase(event_uniq_id)
                # rename the old event database with the new extension
                file.rename(event_database.file)
                # now load the new database
                EventLoader().load_event(event_uniq_id)
        if not EventLoader().event_uniq_ids:
            logger.info(
                'Still no event database found, looking for previously installed releases of Sharly Chess...'
            )
            previous_versions: list[tuple[Version, Path]] = []
            for version_dir in Path('..').glob('*'):
                if version_dir.samefile(Path('.')):
                    # do not inspect the current directory
                    continue
                if not version_dir.is_dir():
                    logger.debug('Not a directory: [%s]', version_dir)
                    continue
                version: Version
                if matches := re.match(
                    r'^(?:papi-web|sharly-chess)-(\d+\.\d+\.\d+(?:a\d+|b\d+|rc\d+)?)(?:-windows)?$',
                    version_dir.name,
                ):
                    version: Version = Version(matches.group(1))
                else:
                    logger.debug('Not a release: [%s].', version_dir)
                    continue
                if version < Version('2.4.0'):
                    logger.debug('Version [%s] : too old, ignored.', version)
                elif version > sharly_chess_config.version:
                    logger.debug('Version [%s] : more recent, ignored.', version)
                elif version == sharly_chess_config.version:
                    logger.debug('Version [%s] : current release, ignored.', version)
                else:
                    previous_versions.append((version, version_dir))
            previous_databases: dict[tuple[Version, Path], list[Path]] = {}
            if previous_versions:
                previous_versions.sort()
                for version, version_dir in previous_versions:
                    files: list[Path] = list(
                        version_dir.glob(
                            f'{EVENTS_FOLDER}/*.{sharly_chess_config.event_database_ext}'
                        )
                    ) + list(
                        version_dir.glob(
                            f'{EVENTS_FOLDER}/*.{sharly_chess_config.event_database_old_ext}'
                        )
                    )
                    if files:
                        logger.debug(
                            '- Version [%s] (%s)',
                            version,
                            ', '.join([file.stem for file in files]),
                        )
                        previous_databases[(version, version_dir)] = files
                    else:
                        logger.debug('- Release [%s]: no events', version)
                if not previous_databases:
                    logger.debug('No events found in previously installed versions.')
            else:
                logger.info('No previously installed releases found.')
            recovered_version: Version | None = None
            if previous_databases:
                # keep the versions with databases only
                previous_versions: list[tuple[Version, Path]] = list(
                    previous_databases.keys()
                )
                previous_versions.sort()
                version_num: int | None = None
                if len(previous_databases) == 1:
                    if input_interactive_yn(
                        _(
                            'Do you want to recover the data of release [{version}]'
                        ).format(version=previous_versions[0][0]),
                        yes_is_default=True,
                    ):
                        version_num = 1
                else:
                    version_range = range(1, len(previous_versions) + 1)
                    options = {
                        str(
                            num
                        ): f'{version} ({", ".join(file.stem for file in previous_databases[(version, version_dir)])})'
                        for num, (version, version_dir) in (
                            (n, previous_versions[n - 1]) for n in version_range
                        )
                    }
                    quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
                    options[quit_answer] = _('Do not recover')

                    while True:
                        choice = input_interactive_choices(
                            _('Please choose the release to recover: ').format(
                                default_choice=len(previous_versions),
                                default_version=previous_versions[-1][0],
                            ),
                            options,
                            default=str(len(previous_versions)),
                        )
                        if choice is None:
                            continue
                        if choice == quit_answer:
                            break
                        if choice == '':
                            version_num = len(previous_versions)
                            break
                        try:
                            version_num = int(choice)
                            if version_num in version_range:
                                break
                            version_num = None
                        except ValueError:
                            pass
                if version_num is not None:
                    recovered_version, version_dir = previous_versions[version_num - 1]
                    self._recover_previous_version(
                        recovered_version,
                        version_dir,
                        previous_databases[(recovered_version, version_dir)],
                    )
            if DEVEL_ENV and not recovered_version:
                if input_interactive_yn(
                    _('Do you want to install example event databases'),
                    yes_is_default=True,
                ):
                    for file in SharlyChessConfig.example_events_path.glob(
                        f'*.{SharlyChessConfig.event_database_ext}'
                    ):
                        shutil.copy(file, EVENTS_DIR / file.name)

    @classmethod
    def _recover_previous_version(
        cls, version: Version, version_dir: Path, files: list[Path]
    ):
        """Recover all the data of a previous version (configuration, events, Papi files and customization files)."""
        config_database_file = (
            version_dir / EVENTS_FOLDER / ConfigDatabase.config_database_name
        )
        if config_database_file.is_file():
            from gui.server_gui_toga import SharlyChessServerToga

            logger.info('Recovering configuration from release [%s]...', version)
            # copy the configuration database to its new destination
            shutil.copy(config_database_file, ConfigDatabase().file)
            ConfigDatabase.setup()
            sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
            sharly_chess_config.load_and_set_env()
            if SharlyChessServerToga.instance is not None:
                logger.debug('Applying recovered configuration to the Toga app...')
                SharlyChessServerToga.instance.update_from_sharly_chess_config()
            plugin_manager.reload_register()
        else:
            logger.debug(
                'Can not recover configuration from version [%s] (file [%s] not found).',
                version,
                config_database_file,
            )
        logger.info('Recovering events from release [%s]...', version)
        events_dir: Path = version_dir / EVENTS_FOLDER
        for file in files:
            event_uniq_id: str = file.stem
            logger.info('Recovering event [%s]...', event_uniq_id)
            event_database: EventDatabase = EventDatabase(event_uniq_id)
            # copy the event database to its new destination
            shutil.copy(file, event_database.file)
        if version < Version('3.0.0'):
            default_papi_dir = 'papi'
            previous_default_papi_path = version_dir / default_papi_dir
            default_papi_path = Path(default_papi_dir)
            default_papi_path.mkdir(parents=True, exist_ok=True)
            for file in previous_default_papi_path.glob('**/*.papi'):
                destination_file = default_papi_path / file.relative_to(
                    previous_default_papi_path
                )
                destination_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(file, destination_file)
        logger.info('Recovering misc files...')
        files_to_recover = [
            database.file
            for database in LocalSourceDatabaseManager().objects()
            if version >= database.min_recovery_version
        ]
        misc_files: list[Path] = []
        for file_to_recover in files_to_recover:
            src_file: Path = version_dir / file_to_recover
            if src_file.is_file():
                file_to_recover.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src_file, file_to_recover)
                misc_files.append(file_to_recover)
        logger.info('Recovering custom files...')
        custom_files: list[Path] = []
        custom_dir: Path = version_dir / SharlyChessConfig.custom_folder
        if custom_dir.is_dir():
            for item in custom_dir.glob('**/*'):
                if item.is_file():
                    embedded_item: Path = Path(
                        str(item).replace(
                            str(custom_dir), str(SharlyChessConfig.embedded_custom_path)
                        )
                    )
                    if not embedded_item.exists() or not filecmp.cmp(
                        item, embedded_item
                    ):
                        target_item: Path = Path(
                            str(item).replace(
                                str(custom_dir), str(SharlyChessConfig.custom_path)
                            )
                        )
                        target_item.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(item, target_item)
                        custom_files.append(item)
        logger.info('Recovering archived events...')
        archives: list[Path] = []
        archives_dir: Path = (
            version_dir / EVENTS_FOLDER / SharlyChessConfig.archives_folder
        )
        if archives_dir.is_dir():
            for item in archives_dir.glob(f'*.{SharlyChessConfig.event_archive_ext}'):
                if item.is_file():
                    target_item: Path = Path(
                        str(item).replace(
                            str(archives_dir),
                            str(SharlyChessConfig.event_archive_base_path),
                        )
                    )
                    target_item.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(item, target_item)
                    archives.append(item)
        logger.info(
            'Events recovered: %d (from directory [%s]).', len(files), events_dir
        )
        if misc_files:
            logger.info(
                'Misc files recovered: %d.',
                len(misc_files),
            )
            for misc_file in misc_files:
                logger.info('- %s', str(misc_file))
        if custom_files:
            logger.info(
                'Custom files recovered: %d (from directory [%s]).',
                len(custom_files),
                custom_dir,
            )
            for custom_file in custom_files:
                logger.info('- %s', str(custom_file).replace(str(custom_dir), ''))
        if archives:
            logger.info(
                'Archived_events recovered: %d (from directory [%s]).',
                len(archives),
                archives_dir,
            )
            for archive in archives:
                logger.info('- %s', str(archive).replace(str(archives_dir), ''))

    @classmethod
    def _check_version(cls) -> tuple[Version | None, str | None]:
        """Compares the current version with the most recent version on the Sharly Chess GitHub repository
        If the current release is stable, more recent pre-releases are ignored; otherwise the most recent release is chosen.
        Returns the most recent version available and the corresponding down URL if any, None otherwise."""
        if TEST_ENV:
            return None, None
        if sys.platform == 'linux':
            # On Linux, updates are managed by Flatpak (flatpak update / GNOME Software etc.)
            return None, None
        most_recent_version, download_url = cls._get_most_recent_version()
        if not most_recent_version:
            return None, None
        if most_recent_version == SHARLY_CHESS_VERSION:
            logger.info('Your Sharly Chess release is up to date.')
            return None, None
        if most_recent_version < SHARLY_CHESS_VERSION:
            logger.warning(
                'You are using a release more recent than the most recent release available ([%s]), are you a developer? ;-)',
                most_recent_version,
            )
            return None, None
        logger.info('A more recent release is available ([%s]).', most_recent_version)
        return most_recent_version, download_url

    @staticmethod
    def _get_most_recent_version() -> tuple[Version | None, str | None]:
        """Retrieves the available versions from the Sharly Chess GitHub repository.
        If the current release is stable, more recent pre-releases are ignored,
        otherwise the most recent unstable release can be returned.
        If an error occurred or no release matches on the repository, returns None.
        Otherwise, the most recent version and its download URL are returned."""
        marker: Path = TMP_DIR / '.github-updates-search'
        if marker.exists() and time() - marker.lstat().st_mtime < 3600:
            logger.debug(
                'Already looked for a more recent version less than one hour ago, skipping.'
            )
            return None, None
        current_stable: bool = bool(
            re.match(r'^(\d+\.\d+\.\d+)$', str(SHARLY_CHESS_VERSION))
        )
        url: str = 'https://api.github.com/repos/sharly-chess/sharly-chess/releases'
        try:
            logger.info('Looking for a more recent release on GitHub...')
            logger.debug('GitHub download URL: [%s].', url)
            response: Response = get(url, allow_redirects=True, timeout=5)
            response.raise_for_status()
            if not response:
                logger.warning('No response from GitHub.')
                return None, None
            data: str = response.content.decode()
            logger.debug(
                'Data received (%d bytes, code %d)',
                len(data),
                response.status_code,
            )
            try:
                entries: list[dict[str, Any]] = json.loads(data)
            except JSONDecodeError as ex:
                logger.warning('Invalid response from GitHub: [%s].', ex)
                return None, None
            marker.touch()
            version_download_urls: dict[Version, str] = {}
            for entry in entries:
                tag_name: str = entry['tag_name']
                if matches := re.match(r'^(\d+\.\d+\.\d+)$', tag_name):
                    version = Version(matches.group(1))
                elif matches := re.match(
                    r'^(\d+.\d+.\d+(a\d+|b\d+|rc\d+))$',
                    tag_name,
                ):
                    if not current_stable:
                        version = Version(matches.group(1))
                    else:
                        logger.debug(
                            '[%s] is not a stable release number, entry ignored.',
                            tag_name,
                        )
                        continue
                else:
                    logger.debug(
                        '[%s] is not a valid release number, entry ignored.', tag_name
                    )
                    continue
                if version < SHARLY_CHESS_VERSION:
                    logger.debug('Release [%s] is too old, ignored.', tag_name)
                    continue
                version_stable: bool = bool(
                    re.match(r'^(\d+\.\d+\.\d+)$', str(version))
                )
                if not version_stable and (
                    version.base_version != SHARLY_CHESS_VERSION.base_version
                ):
                    logger.debug(
                        'Unstable releases with base version other than [%s] are ignored, [%s] ignored.',
                        SHARLY_CHESS_VERSION.base_version,
                        tag_name,
                    )
                    continue
                if entry.get('draft', True):
                    logger.debug('Release [%s] is draft, ignored.', version)
                    continue
                assets: list[dict] = entry.get('assets', [])
                if not assets:
                    logger.debug('No assets for release [%s], ignored.', version)
                    continue
                download_url: str | None = None
                for asset in assets:
                    valid_asset_names: list[str] = []
                    match sys.platform:
                        case 'win32':
                            valid_asset_names = [
                                f'sharly-chess-{version}-windows.zip',
                                f'sharly-chess-{version}.zip',
                            ]
                        case 'darwin':
                            valid_asset_names = [f'sharly-chess-{version}-macos.dmg']
                        case 'linux':
                            # Detect architecture for Linux
                            # Allow override via BUILD_ARCH environment variable (useful for cross-compilation/QEMU)
                            build_arch = os.environ.get('BUILD_ARCH')
                            if build_arch:
                                machine = build_arch.lower()
                            else:
                                machine = platform.machine().lower()
                            if machine in ('aarch64', 'arm64'):
                                valid_asset_names = [
                                    f'sharly-chess-{version}-linux-arm64.zip'
                                ]
                            elif machine in ('x86_64', 'amd64'):
                                valid_asset_names = [
                                    f'sharly-chess-{version}-linux-x86_64.zip'
                                ]
                        case _:
                            raise NotImplementedError(f'{sys.platform=}')

                    if (
                        asset_name := asset.get('name', 'undefined')
                    ) == f'papi-web-{version}.zip':
                        logger.debug(
                            'Old asset name [%s] found in release [%s] (expected [%s]), asset ignored.',
                            asset_name,
                            version,
                            ' or '.join(
                                f'[{valid_asset_name}]'
                                for valid_asset_name in valid_asset_names
                            ),
                        )
                        continue

                    if asset_name not in valid_asset_names:
                        logger.debug(
                            '[%s] is not a valid asset name in release [%s] (expected [%s]), asset ignored.',
                            asset_name,
                            version,
                            ' or '.join(
                                f'[{valid_asset_name}]'
                                for valid_asset_name in valid_asset_names
                            ),
                        )
                        continue
                    if not (asset_url := asset.get('browser_download_url', '')):
                        logger.debug(
                            'No download URL set for [%s] of release [%s], asset ignored.',
                            asset_name,
                            version,
                        )
                        continue
                    logger.debug(
                        'Download URL [%s] is valid for release [%s].',
                        asset_url,
                        version,
                    )
                    download_url = asset_url
                    break
                if not download_url:
                    logger.debug(
                        'No valid asset found for release [%s], release ignored.',
                        version,
                    )
                    continue
                version_download_urls[version] = download_url
            if not version_download_urls:
                logger.info('No more recent releases found.')
                return None, None
            sorted_versions: list[Version] = sorted(version_download_urls.keys())
            logger.debug(
                'More recent releases found (%d): %s.',
                len(sorted_versions),
                ', '.join(map(lambda v: f'[{v}]', sorted_versions)),
            )
            last_version: Version = sorted_versions[-1]
            logger.info('Most recent release found: [%s].', str(last_version))
            return last_version, version_download_urls[last_version]
        except RequestException as ex:
            logger.warning('An error occurred while requesting GitHub.')
            logger.debug('Failed to read [%s]: [%s].', url, ex)
            return None, None

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
                            detected_antivirus_programs: list[Antivirus] = (
                                detect_antivirus_programs()
                            )
                            protect_from_antivirus_programs(
                                detected_antivirus_programs=detected_antivirus_programs,
                                folder=new_version_dir,
                            )
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
