import filecmp
import json
import logging
import re
import shutil
import time
import webbrowser
import zipfile
from datetime import datetime
from json import JSONDecodeError
from logging import Logger
from pathlib import Path
from typing import Any

from packaging.version import Version
from requests import Response, get, request
from requests.exceptions import ConnectionError, Timeout, RequestException, HTTPError  # pylint: disable=redefined-builtin

from common import TMP_DIR
from common.i18n import _
from common.logger import get_logger, configure_logger, input_interactive, print_interactive_input, \
    print_interactive_info, print_interactive_error, print_interactive_warning, print_interactive_success
from common.papi_web_config import PapiWebConfig
from data.event import Event
from data.loader import EventLoader
from database.sqlite import EventDatabase

logger: Logger = get_logger()
configure_logger(logging.INFO)


class Engine:
    """Base class for both ChessEvent, FFE and web server engines."""

    def __init__(self):
        # before all the rest, initialize a PapiWebConfig instance to set the language.
        papi_web_config: PapiWebConfig = PapiWebConfig()
        print_interactive_info(
            f'Papi-web {papi_web_config.version} - {papi_web_config.copyright} - {papi_web_config.url}')
        print_interactive_info(_('Checking Papi-web version...'))
        new_stable_version: Version | None = self._check_version()
        # Engines inheriting from this class should not do anything if property updated is true.
        self.updated: bool = False
        if new_stable_version:
            yes_answer: str = _('Y *** THE LETTER TO ANSWER YES')
            no_answer: str = _('N *** THE LETTER TO ANSWER NO')
            while True:
                choice: str = input_interactive(
                    _('Do you want to upgrade from [{old_version}] to [{new_version}] [{y_lc}/{n_uc}}]? ').format(
                        old_version=papi_web_config.version, new_version=new_stable_version,
                        y_lc=yes_answer.lower(), n_uc=no_answer.upper(),
                    ))
                if choice == yes_answer:
                    self.updated = True
                    if not self._install_new_version(new_stable_version):
                        logger.error(
                            _('The installation of version [{version}] failed.').format(version=new_stable_version))
                    return
                if choice in ['', no_answer, ]:
                    break
                raise ValueError(f'choice=[{choice}]')
        if not EventLoader.get(request=None).event_uniq_ids:
            print_interactive_info('No event database found, looking for previous versions of Papi-web...')
            previous_versions: list[Version] = []
            for version_dir in Path('..').glob('*'):
                if not version_dir.is_dir():
                    logger.debug('Not a directory: %s', version_dir)
                    continue
                matches = re.match(r'^papi-web-(\d+\.\d+\.\d+)$', version_dir.name)
                if not matches:
                    logger.debug('Not a version: %s', version_dir)
                    continue
                version: Version = Version(matches.group(1))
                if version < Version('2.4.0'):
                    logger.debug('Version %s : too old, ignored', version)
                elif version > PapiWebConfig.version:
                    logger.debug('Version %s : more recent, ignored', version)
                elif version == PapiWebConfig.version:
                    logger.debug('Version %s : current version, ignored', version)
                else:
                    previous_versions.append(version)
            previous_databases: dict[Version, list[Path]] = {}
            if previous_versions:
                previous_versions.sort()
                for version in previous_versions:
                    version_dir = Path('..') / f'papi-web-{version}'
                    files: list[Path] = list(version_dir.glob('events/*.db'))
                    if files:
                        print_interactive_info(
                            _('- Version {version} ({events})').format(
                                version=version, events=', '.join([file.stem for file in files])))
                        previous_databases[version] = files
                    else:
                        print_interactive_info(_('- Version {version}: no events').format(version=version))
                if not previous_databases:
                    logger.info(_('No event found in previously installed versions.'))
            else:
                logger.info(_('No previously installed version found.'))
            recovered_version: Version | None = None
            if previous_databases:
                # keep the versions with databases only
                previous_versions = list(previous_databases.keys())
                previous_versions.sort()
                version_num: int | None = None
                if len(previous_databases) == 1:
                    yes_answer: str = _('Y *** THE LETTER TO ANSWER YES')
                    no_answer: str = _('N *** THE LETTER TO ANSWER NO')
                    while True:
                        choice :str = input_interactive(
                            _('Do you want to recover the configuration of version [{version}] [{y_uc}/{n_lc}]?').format(
                                version=previous_versions[0], y_uc=yes_answer.upper(), n_lc=no_answer.lower()))
                        if choice in ['', yes_answer, ]:
                            version_num = 1
                            break
                        if choice == no_answer:
                            break
                        raise ValueError(f'choice=[{choice}]')
                else:
                    print_interactive_input(_('Please choose the version to recover:'))
                    version_range = range(1, len(previous_versions) + 1)
                    for num in version_range:
                        version: Version = previous_versions[num - 1]
                        print_interactive_input(
                            f'  - [{num}] {version} ({", ".join([file.stem for file in previous_databases[version]])})')
                    quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
                    print_interactive_input(_('  - [{q_uc}] Do not recover').format(q_uc=quit_answer))
                    while True:
                        choice: str = input_interactive(
                            _('Please enter the number of the version to recover [{default}]: ').format(
                                default=previous_versions[-1]))
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
                    recovered_version = previous_versions[version_num - 1]
                    self._recover_previous_version(recovered_version, previous_databases[recovered_version])
            if not recovered_version:
                yes_answer: str = _('Y *** THE LETTER TO ANSWER YES')
                no_answer: str = _('N *** THE LETTER TO ANSWER NO')
                while True:
                    choice: str = input_interactive(
                        _('Do you want to install example event databases [{y_uc}/{n_lc}]?').format(
                            y_uc=yes_answer.upper(), n_lc=no_answer.lower()))
                    if choice in ['', yes_answer, ]:
                        for event_id in (
                                file.stem for file in
                        PapiWebConfig.database_yml_path.glob(f'*.{PapiWebConfig.yml_ext}')
                        ):
                            EventDatabase(event_id).create(populate=True)
                        break
                    if choice == no_answer:
                        break
                    raise ValueError(f'choice=[{choice}]')

    @classmethod
    def _recover_previous_version(cls, version: Version, files: list[Path]):
        """Recover all the configuration of a previous version (events, Papi files and customization files)."""
        print_interactive_info(_('Recovering events from version {version}...').format(version=version))
        tournaments_number: int = 0
        version_dir = Path('..') / f'papi-web-{version}'
        for file in files:
            event_uniq_id: str = file.stem
            print_interactive_info(_('Recovering event [{event_uniq_id}]...').format(event_uniq_id=event_uniq_id))
            event_database: EventDatabase = EventDatabase(event_uniq_id)
            # copy the event database to its new destination
            shutil.copy(file, event_database.file)
            # now open the event database to search for local Papi files
            event: Event = EventLoader.get(request=None).load_event(event_uniq_id)
            for tournament in event.tournaments_by_id.values():
                src_file: Path = version_dir / 'papi' / f'{tournament.filename}.{PapiWebConfig.papi_ext}'
                if tournament.path == PapiWebConfig.default_papi_path and src_file.exists():
                    # recover the Papi file where stored in the default folder
                    print_interactive_info(
                        _('Event [{event_uniq_id}]: recovering tournament [{tournament_uniq_id}]...').format(
                            event_uniq_id=event_uniq_id, tournament_uniq_id=tournament.uniq_id))
                    shutil.copy(src_file, tournament.file)
                    logger.debug(str(src_file) + ' > ' + str(tournament.file))
                    tournaments_number += 1
        print_interactive_info(_('Recovering custom files...'))
        custom_files: list[Path] = []
        custom_dir: Path = version_dir / 'custom'
        if custom_dir.is_dir():
            for item in custom_dir.glob('**/*'):
                if item.is_file():
                    embedded_item: Path = Path(str(item).replace(
                        str(custom_dir), str(PapiWebConfig.embedded_custom_path)))
                    if not embedded_item.exists() or not filecmp.cmp(item, embedded_item):
                        target_item: Path = Path(str(item).replace(str(custom_dir), str(PapiWebConfig.custom_path)))
                        target_item.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(item, target_item)
                        custom_files.append(item)
        print_interactive_info(
            _('Events recovered: {num} (from directory [{dir}]).').format(num=len(files), dir=PapiWebConfig.event_path))
        print_interactive_info(
            _('Tournaments recovered: {num} (from directory [{dir}]).').format(
                num=tournaments_number, dir=PapiWebConfig.default_papi_path))
        if custom_files:
            logger.info(
                _('Custom files recovered: {num} (from directory [{dir}]).').format(
                    num=len(custom_files), dir=PapiWebConfig.custom_path))
            for custom_file in custom_files:
                logger.info(f'- {str(custom_file).replace(str(custom_dir), "")}')
            yes_answer: str = _('Y *** THE LETTER TO ANSWER YES')
            no_answer: str = _('N *** THE LETTER TO ANSWER NO')
            while True:
                choice: str = input_interactive(
                    _('Do you want to send these custom files to the Papi-web developers to enhance futures versions [{y_uc}/{n_lc}]?').format(
                        y_uc=yes_answer, n_lc=no_answer))
                if choice in ['', yes_answer, ]:
                    cls._send_custom_files({
                        str(custom_file).replace(
                            str(custom_dir), '').replace('\\', '/').lstrip('/'): custom_file
                        for custom_file in custom_files
                    })
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
            cls, method: str, path: str, data: dict[str, str] | None, files: dict[str, Path] | None) -> bool:
        """Do a request on filebin.net with optional payload and attached files."""
        url: str = cls._filebin_url(path)
        handlers: dict[str, Any] = {}
        debug: bool = False
        try:
            if debug:
                logger.info('_bin_request(method=%s, url=%s)', method, url)
                if data:
                    logger.info('- data:')
                    for field_id, field in data.items():
                         logger.info(
                            '  - %s: [%s]', field_id,
                             field[:64] + ('...' if len(field) > 64 else '') if field else 'None')
                if files:
                    logger.info('- files:')
                    for field_id, file in files.items():
                        logger.info('  - %s: [%s]', field_id, file)
            if not data and not files:
                response: Response = request(method=method, url=url)
            elif not files:
                response: Response = request(method=method, url=url, data=data)
            else:
                handlers = {
                    file_id: open(file_name, 'rb')
                    for file_id, file_name in files.items()
                }
                response: Response = request(method=method, url=url, data=data, files=handlers)
                for handler in handlers.values():
                    handler.close()
            response.raise_for_status()
            content: str = response.content.decode()
            if debug:
                logger.info(f'content={content}')
            return True
        except ConnectionError as ex:
            print_interactive_error(
                _('Failed to read [{url}] (connection error): [{ex}].').format(url=url, ex=ex))
        except Timeout as ex:
            print_interactive_error(_('Failed to read [{url}] (timeout): [{ex}].').format(url=url, ex=ex))
        except HTTPError as ex:
            print_interactive_error(_('Failed to read [{url}] (error code [{errno}]): [{strerror}].').format(
                url=url, errno=ex.errno, strerror=ex.strerror))
        except RequestException as ex:
            print_interactive_error(_('Failed to read [{url}]: [{ex}].').format(url=url, ex=ex))
        for handler in handlers.values():
            handler.close()
        return False

    @classmethod
    def _upload_bin_files(cls, bin_name: str, files: dict[str, Path]) -> bool:
        """Upload a dict of files to filebin.net."""
        for filename, file in files.items():
            if not cls._bin_request(method='POST', path=f'{bin_name}/{filename}', data=None, files={filename: file}):
                return False
        return True

    @classmethod
    def _send_custom_files(cls, custom_files: dict[str, Path]):
        """Sends the custom files to filebin.net and proposes to email the developers."""
        print_interactive_info(_('Sending the files to a server...'))
        datetime_str: str = datetime.strftime(datetime.fromtimestamp(time.time()), "%Y-%m-%d-%H-%M-%S")
        bin_name: str = f'papi-web-custom-files-{datetime_str}'
        if cls._upload_bin_files(bin_name, custom_files):
            bin_url: str = cls._bin_url(bin_name)
            bin_zip_url: str = cls._bin_zip_url(bin_name)
            print_interactive_info(_('Files have been sent to bin {bin_name}.').format(bin_name=bin_name))
            print_interactive_info(_('- View the files on filebin.net: {bin_url}').format(bin_url=bin_url))
            print_interactive_info(_('- Download the files (ZIP archive): {bin_zip_url}').format(
                bin_zip_url=bin_zip_url))
            subject: str = _('[Papi-web {version}] Request for the integration of custom files').format(
                version=PapiWebConfig.version)
            body: str = f'<p>{_("Hello,")}</p>'
            body += f'<p>{_("I would like the following custom files to be added to a future version of Papi-web:")}</p>'
            body += '<ul>'
            for filename in custom_files:
                body += f'<li>{filename}</li>'
            body += '</ul>'
            body += f'<p>{_("Thanks :-)")}</p>'
            body += '<ul>'
            body += f'<li><a href="{bin_url}">{_("View the files on filebin.net")}</a></li>'
            body += f'<li><a href="{bin_zip_url}">{_("Download the files (ZIP archive)")}</a></li>'
            body += '</ul>'
            body += f'<p>{_("Add here all the information you deem necessary, and if you are not known by the developers, introduce yourself!")}</p>'
            body += f'<p>{_("First name LAST NAME")}</p>'
            mail_url: str = f'mailto:{PapiWebConfig.mail}?subject={subject}&html-body={body}'
            print_interactive_info(
                _('A window will open to send an email to the Papi-web project; If the window does not open, please click on the link below or manually send an email to {email}.').format(
                    email=PapiWebConfig.mail))
            print_interactive_info(mail_url)
            webbrowser.open(mail_url, 0)

    @classmethod
    def _check_version(cls) -> Version | None:
        """Compares the current version with the last available stable version
        on the Papi-web GitHub repository.
        Returns the last stable version available if any, None otherwise."""
        last_stable_version: Version | None = cls._get_last_stable_version()
        if not last_stable_version:
            print_interactive_warning(_('Checking the version failed.'))
            return None
        if last_stable_version == PapiWebConfig.version:
            print_interactive_success(_('Your Papi-web version is up to date.'))
            return None
        last_stable_matches = re.match(
            r'^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$', str(last_stable_version))
        if re.match(r'^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$', str(PapiWebConfig.version)):
            # 'normal' versions X.Y.Z
            if last_stable_version > PapiWebConfig.version:
                print_interactive_warning(
                    _('A more recent version is available ([{version}]).').format(version=last_stable_version))
                return last_stable_version
            print_interactive_warning(
                _('You are using a version newer than the latest stable version available ([{version}]), are you a developer? ;-)').format(
                    version=last_stable_version))
            return None
        if not (matches := re.match(r'^(?P<major>\d+)\.(?P<minor>\d+)rc(?P<rc>\d+)$', str(PapiWebConfig.version))):
            raise ValueError(f'Invalid Papi-web version [{str(PapiWebConfig.version)}]')
        # 'release candidates' X.YrcN
        if last_stable_matches.group('major') > matches.group('major') or last_stable_matches.group('minor') > matches.group('minor'):
            print_interactive_warning(
                _('A stable and more recent version is available ([{new_version}]) but upgrading unstable versions (like the one you are currently using: [{old_version}]) must be done manually (upgrade from the last stable version installed on your server).').format(
                    new_version=last_stable_version, old_version=PapiWebConfig.version))
            return None
        print_interactive_info(
            _('You are using un unstable version more recent than the last stable version available ({version}).').format(
                version=last_stable_version))
        return None

    @staticmethod
    def _get_last_stable_version() -> Version | None:
        """Retrieves the available versions from the Papi-web GitHub
        repository.
        If an error occurred, returns None.
        Otherwise, the last stable version is returned."""
        url: str = 'https://api.github.com/repos/papi-web-org/papi-web/releases'
        try:
            print_interactive_info(_('Looking for a more recent version on GitHub ([{url}])...').format(url=url))
            response: Response = get(url, allow_redirects=True, timeout=5)
            response.raise_for_status()
            if not response:
                print_interactive_warning(_('No response from GitHub.'))
                return None
            data: str = response.content.decode()
            logger.debug('Data received (%d bytes, code %d): %s', len(data), response.status_code, data)
            try:
                entries: list[dict[str, Any]] = json.loads(data)
            except JSONDecodeError as ex:
                print_interactive_warning(_('Invalid response from GitHub: {ex}.').format(ex=ex))
                return None
            versions: list[str] = []
            for entry in entries:
                tag_name: str = entry['tag_name']
                if matches := re.match(r'^(\d+\.\d+\.\d+)$', tag_name):
                    version: str = matches.group(1)
                    logger.debug('tag_name=[%s] > version=[%s]', tag_name, version)
                    versions.append(version)
                else:
                    logger.debug('tag_name=[%s]: no stable version number', tag_name)
            if not versions:
                print_interactive_warning(_('No stable version found.'))
                return None
            versions.sort(key=Version)
            logger.debug('releases=%s', versions)
            return Version(versions[-1])
        except ConnectionError as ex:
            print_interactive_warning(
                _('Failed to read [{url}] (connection error): [{ex}].').format(url=url, ex=ex))
            return None
        except Timeout as ex:
            print_interactive_warning(_('Failed to read [{url}] (timeout): [{ex}].').format(url=url, ex=ex))
            return None
        except HTTPError as ex:
            print_interactive_warning(_('Failed to read [{url}] (error code [{errno}]): [{strerror}].').format(
                url=url, errno=ex.errno, strerror=ex.strerror))
            return None
        except RequestException as ex:
            print_interactive_warning(_('Failed to read [{url}]: [{ex}].').format(url=url, ex=ex))
            return None

    @staticmethod
    def _install_new_version(version: Version) -> bool:
        """Install the new stable version at the same directory level.
        Returns True on success, False otherwise."""
        url: str = f'https://github.com/papi-web-org/papi-web/releases/download/{version}/papi-web-{version}.zip'
        new_version_dir: Path = Path('..') / f'papi-web-{version}'
        if new_version_dir.exists():
            print_interactive_error(
                _('Version [{version}] is already installed in directory [{dir}], please manually delete this folder before installing.').format(
                    version=version, dir=new_version_dir.absolute()))
            return False
        try:
            new_version_dir.mkdir()
            logger.info(_('Downloading version {version} from GitHub ([{url}])...').format(version=version, url=url))
            response: Response = get(url, allow_redirects=True, timeout=5)
            response.raise_for_status()
            if not response:
                print_interactive_warning(_('No response from GitHub.'))
                return False
            if response.status_code != 200:
                logger.error(
                    _('Downloading failed with code [{code}].').format(code=response.status_code))
                return False
            zip_file = TMP_DIR / f'papi-web-{version}.zip'
            zip_file.write_bytes(response.content)
            print_interactive_info(_('File downloaded: [{zip_file}].').format(zip_file=zip_file))
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(new_version_dir)
            print_interactive_success(_('New version [{version}] has been installed in [{dir}].').format(
                version=version, dir=new_version_dir.absolute()))
            return True
        except ConnectionError as ex:
            print_interactive_warning(
                _('Failed to read [{url}] (connection error): [{ex}].').format(url=url, ex=ex))
            return False
        except Timeout as ex:
            print_interactive_warning(_('Failed to read [{url}] (timeout): [{ex}].').format(url=url, ex=ex))
            return False
        except HTTPError as ex:
            print_interactive_warning(_('Failed to read [{url}] (error code [{errno}]): [{strerror}].').format(
                url=url, errno=ex.errno, strerror=ex.strerror))
            return False
        except RequestException as ex:
            print_interactive_warning(_('Failed to read [{url}]: [{ex}].').format(url=url, ex=ex))
            return False
