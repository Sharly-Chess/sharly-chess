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
)
from common.i18n import _, set_locale
from common.installation_checker import InstallationChecker
from common.logger import (
    get_logger,
    input_interactive,
    print_interactive_input,
    print_interactive_info,
    print_interactive_error,
    print_interactive_warning,
    print_interactive_success,
    set_console_log_level,
    set_log_file_handler,
)
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.loader import EventLoader
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.event.event_database import EventDatabase

logger = get_logger()


class Engine(ABC):
    """Base class for both ChessEvent, FFE and web server engines."""

    def __init__(self):
        # before all the rest, initialize a SharlyChessConfig instance to set the language.
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        set_locale(sharly_chess_config.locale)
        set_console_log_level(sharly_chess_config.log_level)
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        set_log_file_handler(self.log_file_path)
        print_interactive_info(
            f'Sharly Chess {sharly_chess_config.version} - {sharly_chess_config.copyright} - {sharly_chess_config.url}'
        )
        new_stable_version: Version | None = None
        download_url: str | None = None
        if NetworkMonitor.connected(use_cached=False):
            print_interactive_info(_('Checking Sharly Chess version...'))
            new_stable_version, download_url = self._check_version()
        else:
            print_interactive_warning(
                _('Not connected, can not check Sharly Chess version.')
            )
        # Engines inherited this class should stop if this flag is True.
        self.error: bool = False
        if not InstallationChecker.check():
            self.error = True
            return
        if new_stable_version and download_url:
            yes_answer = _('Y *** THE LETTER TO ANSWER YES')
            no_answer = _('N *** THE LETTER TO ANSWER NO')
            while True:
                choice = input_interactive(
                    _(
                        'Do you want to upgrade from [{old_version}] to [{new_version}] [{y_lc}/{n_uc}]? '
                    ).format(
                        old_version=sharly_chess_config.version,
                        new_version=new_stable_version,
                        y_lc=yes_answer.lower(),
                        n_uc=no_answer.upper(),
                    )
                )
                if choice == yes_answer:
                    self.error = True
                    if not self._install_new_version(new_stable_version, download_url):
                        logger.error(
                            _('The installation of version [{version}] failed.').format(
                                version=new_stable_version
                            )
                        )
                    return
                if choice in [
                    '',
                    no_answer,
                ]:
                    break
                raise ValueError(f'choice=[{choice}]')
        if not EventLoader.get(request=None).event_uniq_ids:
            print_interactive_info(
                'No event database found, looking for previous versions of Sharly Chess...'
            )
            previous_versions: list[tuple[Version, str]] = []
            for version_dir in Path('..').glob('*'):
                if not version_dir.is_dir():
                    logger.debug('Not a directory: %s', version_dir)
                    continue
                matches = re.match(
                    r'^(papi-web|sharly-chess)-(\d+\.\d+\.\d+)$', version_dir.name
                )
                if not matches:
                    logger.debug('Not a version: %s', version_dir)
                    continue
                prefix: str = matches.group(1)
                version: Version = Version(matches.group(2))
                if version < Version('2.4.0'):
                    logger.debug('Version %s : too old, ignored', version)
                elif version > sharly_chess_config.version:
                    logger.debug('Version %s : more recent, ignored', version)
                elif version == sharly_chess_config.version:
                    logger.debug('Version %s : current version, ignored', version)
                else:
                    previous_versions.append((version, prefix))
            previous_databases: dict[tuple[Version, str], list[Path]] = {}
            if previous_versions:
                previous_versions.sort()
                for version, prefix in previous_versions:
                    version_dir = Path('..') / f'{prefix}-{version}'
                    files: list[Path] = list(version_dir.glob('events/*.db'))
                    if files:
                        print_interactive_info(
                            _('- Version {version} ({events})').format(
                                version=version,
                                events=', '.join([file.stem for file in files]),
                            )
                        )
                        previous_databases[(version, prefix)] = files
                    else:
                        print_interactive_info(
                            _('- Version {version}: no events').format(version=version)
                        )
                if not previous_databases:
                    print_interactive_info(
                        _('No events found in previously installed versions.')
                    )
            else:
                print_interactive_info(_('No previously installed versions found.'))
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
                                'Do you want to recover the data of version [{version}] [{y_uc}/{n_lc}]?'
                            ).format(
                                version=previous_versions[0],
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
                    print_interactive_input(_('Please choose the version to recover:'))
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
                                'Please enter the number of the version to recover [{default_choice}: {default_version}]: '
                            ).format(
                                default_choice=len(previous_versions),
                                default_version=previous_versions[-1],
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
                    version, prefix = previous_versions[version_num - 1]
                    self._recover_previous_version(
                        version, prefix, previous_databases[(version, prefix)]
                    )
            if not recovered_version:
                yes_answer = _('Y *** THE LETTER TO ANSWER YES')
                no_answer = _('N *** THE LETTER TO ANSWER NO')
                while True:
                    choice = input_interactive(
                        _(
                            'Do you want to install example event databases [{y_uc}/{n_lc}]?'
                        ).format(y_uc=yes_answer.upper(), n_lc=no_answer.lower())
                    )
                    if choice in [
                        '',
                        yes_answer,
                    ]:
                        for event_id in (
                            file.stem
                            for file in SharlyChessConfig.database_yml_path.glob(
                                f'*.{SharlyChessConfig.yml_ext}'
                            )
                            if file.stem != SharlyChessConfig.test_event_uniq_id
                        ):
                            EventDatabase(event_id).create(populate=True)
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
            print_interactive_info(
                _('Recovering configuration from version {version}...').format(
                    version=version
                )
            )
            # copy the configuration database to its new destination
            shutil.copy(config_database_file, ConfigDatabase().file)
            SharlyChessConfig().reload()
        else:
            logger.debug(
                'Can not recover configuration from version {%s} (file[%s] not found).',
                version,
                config_database_file,
            )
        print_interactive_info(
            _('Recovering events from version {version}...').format(version=version)
        )
        tournaments_number: int = 0
        events_dir: Path = version_dir / EVENTS_FOLDER
        papi_dir: Path = version_dir / SharlyChessConfig.default_papi_folder
        for file in files:
            event_uniq_id: str = file.stem
            print_interactive_info(
                _('Recovering event [{event_uniq_id}]...').format(
                    event_uniq_id=event_uniq_id
                )
            )
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
                    print_interactive_info(
                        _(
                            'Event [{event_uniq_id}]: recovering tournament [{tournament_uniq_id}]...'
                        ).format(
                            event_uniq_id=event_uniq_id,
                            tournament_uniq_id=tournament.uniq_id,
                        )
                    )
                    shutil.copy(src_file, tournament.file)
                    logger.debug('%s > %s', str(src_file), str(tournament.file))
                    tournaments_number += 1
        print_interactive_info(_('Recovering custom files...'))
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
        print_interactive_info(
            _('Events recovered: {num} (from directory [{dir}]).').format(
                num=len(files), dir=events_dir
            )
        )
        print_interactive_info(
            _('Tournaments recovered: {num} (from directory [{dir}]).').format(
                num=tournaments_number, dir=papi_dir
            )
        )
        if custom_files:
            logger.info(
                _('Custom files recovered: {num} (from directory [{dir}]).').format(
                    num=len(custom_files), dir=custom_dir
                )
            )
            for custom_file in custom_files:
                logger.info('- %s', str(custom_file).replace(str(custom_dir), ''))
            yes_answer = _('Y *** THE LETTER TO ANSWER YES')
            no_answer = _('N *** THE LETTER TO ANSWER NO')
            while True:
                choice = input_interactive(
                    _(
                        'Do you want to send these custom files to the Sharly Chess developers to enhance futures versions [{y_uc}/{n_lc}]?'
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
            print_interactive_error(
                _('Failed to read [{url}] (connection error): [{ex}].').format(
                    url=url, ex=ex
                )
            )
        except Timeout as ex:
            print_interactive_error(
                _('Failed to read [{url}] (timeout): [{ex}].').format(url=url, ex=ex)
            )
        except HTTPError as ex:
            print_interactive_error(
                _(
                    'Failed to read [{url}] (error code [{errno}]): [{strerror}].'
                ).format(url=url, errno=ex.errno, strerror=ex.strerror)
            )
        except RequestException as ex:
            print_interactive_error(
                _('Failed to read [{url}]: [{ex}].').format(url=url, ex=ex)
            )
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
        print_interactive_info(_('Sending the files to a server...'))
        datetime_str: str = datetime.strftime(
            datetime.fromtimestamp(time.time()), '%Y-%m-%d-%H-%M-%S'
        )
        bin_name: str = f'sharly-chess-custom-files-{datetime_str}'
        if cls._upload_bin_files(bin_name, custom_files):
            bin_url: str = cls._bin_url(bin_name)
            bin_zip_url: str = cls._bin_zip_url(bin_name)
            print_interactive_info(
                _('Files have been sent to bin {bin_name}.').format(bin_name=bin_name)
            )
            print_interactive_info(
                _('- View the files on filebin.net: {bin_url}').format(bin_url=bin_url)
            )
            print_interactive_info(
                _('- Download the files (ZIP archive): {bin_zip_url}').format(
                    bin_zip_url=bin_zip_url
                )
            )
            subject: str = _(
                '[Sharly Chess {version}] Request for the integration of custom files'
            ).format(version=SHARLY_CHESS_VERSION)
            body: str = '<p>' + _('Hello,') + '</p>'
            body += (
                '<p>'
                + _(
                    'I would like the following custom files to be added to a future version of Sharly Chess:'
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
            print_interactive_info(
                _(
                    'A window will open to send an email to the Sharly Chess project; '
                    'If the window does not open, please click on the link below '
                    'or manually send an email to {email}.'
                ).format(email=SharlyChessConfig.mail)
            )
            print_interactive_info(mail_url)
            webbrowser.open(mail_url, 0)

    @classmethod
    def _check_version(cls) -> tuple[Version | None, str | None]:
        """Compares the current version with the last available stable version
        on the Sharly Chess GitHub repository.
        Returns the last stable version available
        and the corresponding down URL if any, None otherwise."""
        last_stable_version, download_url = cls._get_last_stable_version()
        if not last_stable_version:
            print_interactive_warning(_('Checking the version failed.'))
            return None, None
        if last_stable_version == SHARLY_CHESS_VERSION:
            print_interactive_success(_('Your Sharly Chess version is up to date.'))
            return None, None
        last_stable_matches = re.match(
            r'^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$',
            str(last_stable_version),
        )
        if not last_stable_matches:
            print_interactive_warning(_('Checking the version failed.'))
            return None, None
        if re.match(
            r'^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$',
            str(SHARLY_CHESS_VERSION),
        ):
            # 'normal' versions X.Y.Z
            if last_stable_version > SHARLY_CHESS_VERSION:
                print_interactive_warning(
                    _('A more recent version is available ([{version}]).').format(
                        version=last_stable_version
                    )
                )
                return last_stable_version, download_url
            print_interactive_warning(
                _(
                    'You are using a version newer than the latest stable version available ([{version}]), are you a developer? ;-)'
                ).format(version=last_stable_version)
            )
            return None, None
        if not (
            matches := re.match(
                r'^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(a|b|rc)(?P<rc>\d+)$',
                str(SHARLY_CHESS_VERSION),
            )
        ):
            raise ValueError(
                f'Invalid Sharly Chess version [{str(SHARLY_CHESS_VERSION)}]'
            )
        # alpha versions: X.Y.ZaN
        # beta versions: X.Y.ZbN
        # 'release candidates' X.Y.ZrcN
        available: bool = False
        stable_major = last_stable_matches.group('major')
        current_major = matches.group('major')
        if stable_major > current_major:
            available = True
        else:  # stable_major == current_major
            stable_minor = last_stable_matches.group('minor')
            current_minor = matches.group('minor')
            if stable_minor > current_minor:
                available = True
            else:  # stable_major == current_major
                stable_patch = last_stable_matches.group('patch')
                current_patch = matches.group('patch')
                if stable_patch > current_patch:
                    available = True
        if available:
            print_interactive_warning(
                _(
                    'A stable and more recent version is available ([{new_version}]) but upgrading unstable versions (like the one you are currently using: [{old_version}]) must be done manually (upgrade from the last stable version installed on your server).'
                ).format(
                    new_version=last_stable_version, old_version=SHARLY_CHESS_VERSION
                )
            )
            return None, None
        print_interactive_info(
            _(
                'You are using un unstable version more recent than the last stable version available ({version}).'
            ).format(version=last_stable_version)
        )
        return None, None

    @staticmethod
    def _get_last_stable_version() -> tuple[Version | None, str | None]:
        """Retrieves the available versions from the Sharly Chess GitHub
        repository.
        If an error occurred, returns None.
        Otherwise, the last stable version and the download URL are returned."""
        url: str = 'https://api.github.com/repos/sharly-chess/sharly-chess/releases'
        try:
            print_interactive_info(
                _('Looking for a more recent version on GitHub ([{url}])...').format(
                    url=url
                )
            )
            response: Response = get(url, allow_redirects=True, timeout=5)
            response.raise_for_status()
            if not response:
                print_interactive_warning(_('No response from GitHub.'))
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
                print_interactive_warning(
                    _('Invalid response from GitHub: {ex}.').format(ex=ex)
                )
                return None, None
            version_download_urls: dict[Version, str] = {}
            for entry in entries:
                tag_name: str = entry['tag_name']
                if not (matches := re.match(r'^(\d+\.\d+\.\d+)$', tag_name)):
                    print_interactive_info(
                        _(
                            '[{tag_name}] is not a stable release number, entry ignored.'
                        ).format(tag_name=tag_name)
                    )
                    continue
                version: str = matches.group(1)
                logger.debug('tag_name=[%s] > version=[%s]', tag_name, version)
                if entry.get('draft', True):
                    print_interactive_info(
                        _('Release [{version}] is draft, ignored.').format(
                            version=version
                        )
                    )
                    continue
                assets: list[dict] = entry.get('assets', [])
                if not assets:
                    print_interactive_info(
                        _(
                            'No asset found for release [{version}], release ignored.'
                        ).format(version=version)
                    )
                    continue
                download_url: str | None = None
                for asset in assets:
                    valid_asset_name: str = f'sharly-chess-{version}.zip'
                    if (
                        asset_name := asset.get('name', 'undefined')
                    ) == f'papi-web-{version}.zip':
                        print_interactive_info(
                            _(
                                '[{asset_name}] is an old asset name in release [{version}] (expected [{valid_asset_name}]), asset ignored.'
                            ).format(
                                asset_name=asset_name,
                                version=version,
                                valid_asset_name=valid_asset_name,
                            )
                        )
                        continue
                    if (
                        asset_name := asset.get('name', 'undefined')
                    ) != valid_asset_name:
                        print_interactive_info(
                            _(
                                '[{asset_name}] is not a valid asset name in release [{version}] (expected [{valid_asset_name}]), asset ignored.'
                            ).format(
                                asset_name=asset_name,
                                version=version,
                                valid_asset_name=valid_asset_name,
                            )
                        )
                        continue
                    if not (asset_url := asset.get('browser_download_url', '')):
                        print_interactive_info(
                            _(
                                'No download URL set for [{asset_name}] of release [{version}], asset ignored.'
                            ).format(asset_name=asset_name, version=version)
                        )
                        continue
                    print_interactive_info(
                        _(
                            'No download URL set for [{asset_name}] of release [{version}], asset ignored.'
                        ).format(asset_name=asset_name, version=version)
                    )
                    download_url = asset_url
                    break
                if not download_url:
                    print_interactive_warning(
                        _(
                            'No valid asset found for release [{version}], release ignored.'
                        ).format(version=version)
                    )
                    continue
            if not version_download_urls:
                print_interactive_warning(_('No stable version found.'))
                return None, None
            sorted_versions: list[Version] = sorted(version_download_urls.keys())
            print_interactive_info(
                _('Stable releases found: {versions}.').format(
                    versions=', '.join(map(str, sorted_versions))
                )
            )
            last_version: Version = sorted_versions[-1]
            print_interactive_info(
                _('Last stable release found: {version}.').format(version=last_version)
            )
            return last_version, version_download_urls[last_version]
        except ConnectionError as ex:
            print_interactive_warning(
                _('Failed to read [{url}] (connection error): [{ex}].').format(
                    url=url, ex=ex
                )
            )
            return None, None
        except Timeout as ex:
            print_interactive_warning(
                _('Failed to read [{url}] (timeout): [{ex}].').format(url=url, ex=ex)
            )
            return None, None
        except HTTPError as ex:
            print_interactive_warning(
                _(
                    'Failed to read [{url}] (error code [{errno}]): [{strerror}].'
                ).format(url=url, errno=ex.errno, strerror=ex.strerror)
            )
            return None, None
        except RequestException as ex:
            print_interactive_warning(
                _('Failed to read [{url}]: [{ex}].').format(url=url, ex=ex)
            )
            return None, None

    @staticmethod
    def _install_new_version(version: Version, download_url: str) -> bool:
        """Install the new stable version at the same directory level.
        Returns True on success, False otherwise."""
        new_version_dir: Path = Path('..') / f'sharly-chess-{version}'
        if new_version_dir.exists():
            print_interactive_error(
                _(
                    'Version [{version}] is already installed in directory [{dir}], please manually delete this folder before installing.'
                ).format(version=version, dir=new_version_dir.absolute())
            )
            return False
        try:
            new_version_dir.mkdir()
            logger.info(
                _('Downloading version {version} from GitHub ([{url}])...').format(
                    version=version, url=download_url
                )
            )
            response: Response = get(download_url, allow_redirects=True, timeout=5)
            response.raise_for_status()
            if not response:
                print_interactive_warning(_('No response from GitHub.'))
                return False
            if response.status_code != 200:
                logger.error(
                    _('Downloading failed with code [{code}].').format(
                        code=response.status_code
                    )
                )
                return False
            zip_file = TMP_DIR / f'sharly-chess-{version}.zip'
            zip_file.write_bytes(response.content)
            print_interactive_info(
                _('File downloaded: [{zip_file}].').format(zip_file=zip_file)
            )
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(new_version_dir)
            print_interactive_success(
                _('New version [{version}] has been installed in [{dir}].').format(
                    version=version, dir=new_version_dir.absolute()
                )
            )
            return True
        except ConnectionError as ex:
            print_interactive_warning(
                _('Failed to read [{url}] (connection error): [{ex}].').format(
                    url=download_url, ex=ex
                )
            )
            return False
        except Timeout as ex:
            print_interactive_warning(
                _('Failed to read [{url}] (timeout): [{ex}].').format(
                    url=download_url, ex=ex
                )
            )
            return False
        except HTTPError as ex:
            print_interactive_warning(
                _(
                    'Failed to read [{url}] (error code [{errno}]): [{strerror}].'
                ).format(url=download_url, errno=ex.errno, strerror=ex.strerror)
            )
            return False
        except RequestException as ex:
            print_interactive_warning(
                _('Failed to read [{url}]: [{ex}].').format(url=download_url, ex=ex)
            )
            return False
