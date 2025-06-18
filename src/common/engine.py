import filecmp
import json
import re
import shutil
import time
import webbrowser
import zipfile
from abc import ABC, abstractmethod
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from packaging.version import Version
from requests import Response, get, request
from requests.exceptions import ConnectionError, Timeout, RequestException, HTTPError  # pylint: disable=redefined-builtin

from common import (
    SHARLY_CHESS_VERSION,
    TMP_DIR,
    REQUEST_TIMEOUT,
    EVENTS_FOLDER,
    DEVEL_ENV,
    EVENTS_DIR,
)
from common.i18n import _
from common.installation_checker import InstallationChecker
from common.logger import (
    get_logger,
    input_interactive,
    print_interactive_input,
)
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.loader import EventLoader
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.local_source_database import LocalSourceDatabaseManager

logger = get_logger()


class Engine(ABC):
    """Base class for both ChessEvent and web server engines."""

    def __init__(self):
        # before all the rest, initialize a SharlyChessConfig instance to set the language.
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        logger.info(
            'Sharly Chess %s - %s - %s',
            sharly_chess_config.version,
            sharly_chess_config.copyright,
            sharly_chess_config.url,
        )
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
        if more_recent_version and download_url:
            yes_answer = _('Y *** THE LETTER TO ANSWER YES')
            no_answer = _('N *** THE LETTER TO ANSWER NO')
            while True:
                choice = input_interactive(
                    _(
                        'Do you want to upgrade from [{old_version}] to [{new_version}] [{y_lc}/{n_uc}]? '
                    ).format(
                        old_version=sharly_chess_config.version,
                        new_version=more_recent_version,
                        y_lc=yes_answer.lower(),
                        n_uc=no_answer.upper(),
                    )
                )
                if choice == yes_answer:
                    self.error = True
                    if not self._install_new_version(more_recent_version, download_url):
                        logger.error(
                            'The installation of release [%s] failed.',
                            more_recent_version,
                        )
                    return
                if choice in [
                    '',
                    no_answer,
                ]:
                    break
                raise ValueError(f'choice=[{choice}]')
        if not EventLoader.get(request=None).event_uniq_ids:
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
                EventLoader.get(request=None).load_event(event_uniq_id)
        if not EventLoader.get(request=None).event_uniq_ids:
            logger.info(
                'Still no event database found, looking for previously installed releases of Sharly Chess...'
            )
            previous_versions: list[tuple[Version, str]] = []
            for version_dir in Path('..').glob('*'):
                if not version_dir.is_dir():
                    logger.debug('Not a directory: [%s]', version_dir)
                    continue
                prefix: str
                version: Version
                if matches := re.match(
                    r'^(papi-web|sharly-chess)-(\d+.\d+.\d+(?:a\d+|b\d+|rc\d+)?)$',
                    version_dir.name,
                ):
                    prefix: str = matches.group(1)
                    version: Version = Version(matches.group(2))
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
                    previous_versions.append((version, prefix))
            previous_databases: dict[tuple[Version, str], list[Path]] = {}
            if previous_versions:
                previous_versions.sort()
                for version, prefix in previous_versions:
                    version_dir = Path('..') / f'{prefix}-{version}'
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
                        previous_databases[(version, prefix)] = files
                    else:
                        logger.debug('- Release [%s]: no events', version)
                if not previous_databases:
                    logger.debug('No events found in previously installed versions.')
            else:
                logger.info('No previously installed releases found.')
            recovered_version: Version | None = None
            if previous_databases:
                # keep the versions with databases only
                previous_versions: list[tuple[Version, str]] = list(
                    previous_databases.keys()
                )
                previous_versions.sort()
                version_num: int | None = None
                if len(previous_databases) == 1:
                    yes_answer = _('Y *** THE LETTER TO ANSWER YES')
                    no_answer = _('N *** THE LETTER TO ANSWER NO')
                    while True:
                        choice = input_interactive(
                            _(
                                'Do you want to recover the data of release [{version}] [{y_uc}/{n_lc}]? '
                            ).format(
                                version=previous_versions[0][0],
                                y_uc=yes_answer.upper(),
                                n_lc=no_answer.lower(),
                            )
                        )
                        if choice in [
                            '',
                            yes_answer,
                        ]:
                            version_num = 1
                            break
                        if choice == no_answer:
                            break
                        raise ValueError(f'choice=[{choice}]')
                else:
                    print_interactive_input(_('Please choose the release to recover: '))
                    version_range = range(1, len(previous_versions) + 1)
                    for num in version_range:
                        version, prefix = previous_versions[num - 1]
                        print_interactive_input(
                            f'  - [{num}] {version} ({", ".join([file.stem for file in previous_databases[(version, prefix)]])})'
                        )
                    quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
                    print_interactive_input(
                        _('  - [{q_uc}] Do not recover').format(q_uc=quit_answer)
                    )
                    while True:
                        choice = input_interactive(
                            _(
                                'Please enter the number of the release to recover [{default_choice}: {default_version}]: '
                            ).format(
                                default_choice=len(previous_versions),
                                default_version=previous_versions[-1][0],
                            )
                        )
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
                    recovered_version, prefix = previous_versions[version_num - 1]
                    self._recover_previous_version(
                        recovered_version,
                        prefix,
                        previous_databases[(recovered_version, prefix)],
                    )
            if DEVEL_ENV and not recovered_version:
                yes_answer = _('Y *** THE LETTER TO ANSWER YES')
                no_answer = _('N *** THE LETTER TO ANSWER NO')
                while True:
                    choice = input_interactive(
                        _(
                            'Do you want to install example event databases [{y_uc}/{n_lc}]? '
                        ).format(y_uc=yes_answer.upper(), n_lc=no_answer.lower())
                    )
                    if choice in [
                        '',
                        yes_answer,
                    ]:
                        for event_id in (
                            file.stem
                            for file in SharlyChessConfig.example_events_yml_path.glob(
                                f'*.{SharlyChessConfig.yml_ext}'
                            )
                            if file.stem != SharlyChessConfig.test_event_uniq_id
                        ):
                            EventDatabase(event_id).create(populate=True)
                        SharlyChessConfig.default_papi_path.mkdir(
                            parents=True, exist_ok=True
                        )
                        for file in SharlyChessConfig.example_events_papi_path.glob(
                            f'*.{SharlyChessConfig.papi_ext}'
                        ):
                            shutil.copy(
                                file,
                                SharlyChessConfig.default_papi_path / file.name,
                            )
                        break
                    if choice == no_answer:
                        break
                    raise ValueError(f'choice=[{choice}]')

    @property
    @abstractmethod
    def log_file_path(self) -> Path:
        """Path of the file to write the logs to.
        2 engines should not have the same one to avoid contention issues."""

    @classmethod
    def _recover_previous_version(
        cls, version: Version, prefix: str, files: list[Path]
    ):
        """Recover all the data of a previous version (configuration, events, Papi files and customization files)."""
        version_dir = Path('..') / f'{prefix}-{version}'
        config_database_file = (
            version_dir / EVENTS_FOLDER / ConfigDatabase.config_database_name
        )
        if config_database_file.is_file():
            logger.info('Recovering configuration from release [%s]...', version)
            # copy the configuration database to its new destination
            shutil.copy(config_database_file, ConfigDatabase().file)
            SharlyChessConfig.reload()
        else:
            logger.debug(
                'Can not recover configuration from version [%s] (file [%s] not found).',
                version,
                config_database_file,
            )
        logger.info('Recovering events from release [%s]...', version)
        tournaments_number: int = 0
        events_dir: Path = version_dir / EVENTS_FOLDER
        papi_dir: Path = version_dir / SharlyChessConfig.default_papi_folder
        for file in files:
            event_uniq_id: str = file.stem
            logger.info('Recovering event [%s]...', event_uniq_id)
            event_database: EventDatabase = EventDatabase(event_uniq_id)
            # copy the event database to its new destination
            shutil.copy(file, event_database.file)
            # now open the event database to search for local Papi files
            event: Event = EventLoader.get(request=None).load_event(event_uniq_id)
            for tournament in event.tournaments_by_id.values():
                src_file: Path = (
                    papi_dir / f'{tournament.filename}.{SharlyChessConfig.papi_ext}'
                )
                if (
                    tournament.path == SharlyChessConfig.default_papi_path
                    and src_file.exists()
                ):
                    # recover the Papi file where stored in the default folder
                    logger.debug(
                        'Event [%s]: recovering tournament [%s]...',
                        event_uniq_id,
                        tournament.uniq_id,
                    )
                    shutil.copy(src_file, tournament.file)
                    logger.debug('%s > %s', str(src_file), str(tournament.file))
                    tournaments_number += 1
        logger.info('Recovering misc files...')
        files_to_recover: list[Path] = []
        for database in LocalSourceDatabaseManager.objects():
            files_to_recover.append(database.file)
            if legacy_path := database.legacy_path:
                files_to_recover.append(legacy_path)

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
        logger.info(
            'Events recovered: %d (from directory [%s]).', len(files), events_dir
        )
        logger.info(
            'Tournaments recovered: %d (from directory [%s]).',
            tournaments_number,
            papi_dir,
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
            yes_answer = _('Y *** THE LETTER TO ANSWER YES')
            no_answer = _('N *** THE LETTER TO ANSWER NO')
            while True:
                choice = input_interactive(
                    _(
                        'Do you want to send these custom files to the Sharly Chess developers to enhance futures releases [{y_uc}/{n_lc}]? '
                    ).format(y_uc=yes_answer, n_lc=no_answer.lower())
                )
                if choice in [
                    '',
                    yes_answer,
                ]:
                    cls._send_custom_files(
                        {
                            str(custom_file)
                            .replace(str(custom_dir), '')
                            .replace('\\', '/')
                            .lstrip('/'): custom_file
                            for custom_file in custom_files
                        }
                    )
                    break
                if choice == no_answer:
                    break
                raise ValueError(f'choice=[{choice}]')

    @classmethod
    def _filebin_url(cls, path: str) -> str:
        """Returns a URL on filebin.net."""
        return f'https://filebin.net/{path}'

    @classmethod
    def _bin_url(cls, bin_name: str) -> str:
        """Returns the URL of a bin on filebin.net."""
        return cls._filebin_url(bin_name)

    @classmethod
    def _bin_zip_url(cls, bin_name: str) -> str:
        """Returns the URL to download a bin as a zip file from filebin.net."""
        return cls._filebin_url(f'archive/{bin_name}/zip')

    @classmethod
    def _bin_request(
        cls,
        method: str,
        path: str,
        data: dict[str, str] | None,
        file: Path | None,
    ) -> bool:
        """Do a request on filebin.net with optional payload and attached files."""
        url: str = cls._filebin_url(path)
        handlers: dict[str, Any] = {}
        debug: bool = DEVEL_ENV
        try:
            if debug:
                logger.debug('_bin_request(method=%s, url=%s)', method, url)
                if data:
                    logger.info('- data:')
                    for field_id, field in data.items():
                        logger.info(
                            '  - %s: [%s]',
                            field_id,
                            field[:64] + ('...' if len(field) > 64 else '')
                            if field
                            else 'None',
                        )
            if not data and not file:
                response: Response = request(
                    method=method, url=url, timeout=REQUEST_TIMEOUT
                )
            elif not file:
                response: Response = request(
                    method=method, url=url, data=data, timeout=REQUEST_TIMEOUT
                )
            else:
                with open(file, 'rb') as f:
                    response: Response = request(
                        method=method,
                        url=url,
                        data=f,
                        headers={'Content-Type': 'application/octet-stream'},
                        timeout=REQUEST_TIMEOUT,
                    )
            response.raise_for_status()
            content: str = response.content.decode()
            if debug:
                logger.debug('content=%s', content)
            return True
        except ConnectionError as ex:
            logger.error('Failed to read [%s] (connection error): [%s].', url, ex)
        except Timeout as ex:
            logger.error('Failed to read [%s] (timeout): [%s].', url, ex)
        except HTTPError as ex:
            logger.error(
                'Failed to read [%s] (error code [%d]): [%s].',
                url,
                ex.errno,
                ex.strerror,
            )
        except RequestException as ex:
            logger.error('Failed to read [%s]: [%s].', url, ex)
        for handler in handlers.values():
            handler.close()
        return False

    @classmethod
    def _upload_bin_files(cls, bin_name: str, files: dict[str, Path]) -> bool:
        """Upload a dict of files to filebin.net."""
        for filename, file in files.items():
            if not cls._bin_request(
                method='POST',
                path=f'{bin_name}/{filename}',
                data=None,
                file=file,
            ):
                return False
        return True

    @classmethod
    def _send_custom_files(cls, custom_files: dict[str, Path]):
        """Sends the custom files to filebin.net and proposes to email the developers."""
        logger.info('Sending the files to a server...')
        datetime_str: str = datetime.strftime(
            datetime.fromtimestamp(time.time()), '%Y-%m-%d-%H-%M-%S'
        )
        bin_name: str = f'sharly-chess-custom-files-{datetime_str}'
        if cls._upload_bin_files(bin_name, custom_files):
            bin_url: str = cls._bin_url(bin_name)
            bin_zip_url: str = cls._bin_zip_url(bin_name)
            logger.info('Files have been sent to bin [%s].', bin_name)
            logger.info('- View the files on filebin.net: [%s]', bin_url)
            logger.info('- Download the files (ZIP archive): [%s]', bin_zip_url)
            subject: str = _(
                '[Sharly Chess {version}] Request for the integration of custom files'
            ).format(version=SHARLY_CHESS_VERSION)
            body: str = '<p>' + _('Hello,') + '</p>'
            body += (
                '<p>'
                + _(
                    'I would like the following custom files to be added to a future release of Sharly Chess:'
                )
                + '</p>'
            )
            body += '<ul>'
            for filename in custom_files:
                body += f'<li>{filename}</li>'
            body += '</ul>'
            body += '<p>' + _('Thanks :-)') + '</p>'
            body += '<ul>'
            body += (
                f'<li><a href="{bin_url}">'
                + _('View the files on filebin.net')
                + '</a></li>'
            )
            body += (
                f'<li><a href="{bin_zip_url}">'
                + _('Download the files (ZIP archive)')
                + '</a></li>'
            )
            body += '</ul>'
            body += (
                '<p>'
                + _(
                    'Add here all the information you deem necessary, and if '
                    'you are not known by the developers, introduce yourself!'
                )
                + '</p>'
            )
            body += '<p>' + _('First name LAST NAME') + '</p>'
            mail_url: str = (
                f'mailto:{SharlyChessConfig.mail}?subject={subject}&html-body={body}'
            )
            logger.info(
                'A window will open to send an email to the Sharly Chess project; '
                'If the window does not open, please click on the link below '
                'or manually send an email to [%s].',
                SharlyChessConfig.mail,
            )
            logger.info(mail_url)
            webbrowser.open(mail_url, 0)

    @classmethod
    def _check_version(cls) -> tuple[Version | None, str | None]:
        """Compares the current version with the most recent version on the Sharly Chess GitHub repository
        If the current release is stable, more recent pre-releases are ignored; otherwise the most recent release is chosen.
        Returns the most recent version available and the corresponding down URL if any, None otherwise."""
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
                    valid_asset_name: str = f'sharly-chess-{version}.zip'
                    if (
                        asset_name := asset.get('name', 'undefined')
                    ) == f'papi-web-{version}.zip':
                        logger.debug(
                            'Old asset name [%s] found in release [%s] (expected [%s]), asset ignored.',
                            asset_name,
                            version,
                            valid_asset_name,
                        )
                        continue
                    if asset_name != valid_asset_name:
                        logger.debug(
                            '[%s] is not a valid asset name in release [%s] (expected [%s]), asset ignored.',
                            asset_name,
                            version,
                            valid_asset_name,
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
    def _install_new_version(version: Version, download_url: str) -> bool:
        """Install the new stable version at the same directory level.
        Returns True on success, False otherwise."""
        new_version_dir: Path = Path('..') / f'sharly-chess-{version}'
        if new_version_dir.exists():
            logger.error(
                'Version [%s] is already installed in directory [%s], please manually delete this folder before installing.',
                version,
                new_version_dir.absolute(),
            )
            return False
        try:
            logger.info(
                'Downloading release [%s] from GitHub ([%s])...', version, download_url
            )
            response: Response = get(download_url, allow_redirects=True, timeout=5)
            response.raise_for_status()
            if not response:
                logger.error('No response from GitHub.')
                return False
            if response.status_code != 200:
                logger.error('Downloading failed with code [%d].', response.status_code)
                return False
            zip_file = TMP_DIR / f'sharly-chess-{version}.zip'
            zip_file.write_bytes(response.content)
            logger.debug('File downloaded: [%s].', zip_file)
            new_version_dir.mkdir()
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(new_version_dir)
            logger.info(
                'New release [%s] has been installed in [%s].',
                version,
                new_version_dir.absolute(),
            )
            return True
        except RequestException as ex:
            logger.warning('Failed to read [%s]: [%s].', download_url, ex)
            return False
