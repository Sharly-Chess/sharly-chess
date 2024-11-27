import filecmp
import json
import logging
import platform
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

import pyodbc
from packaging.version import Version
from requests import Response, get, request
from requests.exceptions import ConnectionError, Timeout, RequestException, \
    HTTPError  # pylint: disable=redefined-builtin

from common.logger import get_logger, configure_logger, input_interactive, print_interactive
from common.papi_web_config import PapiWebConfig, TMP_DIR
from data.event import Event
from data.loader import EventLoader
from database.sqlite import EventDatabase

logger: Logger = get_logger()
configure_logger(logging.INFO)


class Engine:
    """Base class for both ChessEvent, FFE and web server engines."""

    def __init__(self):
        try:
            TMP_DIR.mkdir(parents=True, exist_ok=True)
        except PermissionError as pe:
            logger.critical(f'Impossible de créer le répertoire {TMP_DIR.absolute()} :-(')
            raise pe
        try:
            PapiWebConfig.event_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as pe:
            logger.critical(f'Impossible de créer le répertoire {PapiWebConfig.event_path.absolute()} :-(')
            raise pe
        logger.debug('ODBC drivers found:')
        for driver in pyodbc.drivers():
            logger.debug(f' - {driver}')
        logger.debug('System information:')
        logger.debug(f' - Machine/processor: {platform.machine()}/{platform.processor()}')
        logger.debug(f' - Platform: {platform.platform()}')
        logger.debug(f' - Architecture: {" ".join(platform.architecture())}')
        logger.info('Vérification de la version...')
        new_stable_version: Version | None = self._check_version()
        # If this property is false, the engine should stop right after its construction
        self.updated: bool = False
        if new_stable_version:
            while True:
                match input_interactive('Voulez-vous mettre votre version à jour [o/N] ?'):
                    case 'O':
                        self.updated = True
                        if not self._install_new_version(new_stable_version):
                            logger.error('L\'installation de la version %s a échoué', new_stable_version)
                        return
                    case '' | 'N':
                        break
        if not EventLoader.get(request=None).event_uniq_ids:
            logger.info('Aucune base de données trouvée, recherche des versions précédemment installées...')
            previous_versions: list[Version] = []
            for version_dir in Path('..').glob('*'):
                if not version_dir.is_dir():
                    logger.debug('Non-répertoire: %s', version_dir)
                    continue
                matches = re.match(r'^papi-web-(\d+\.\d+\.\d+)$', version_dir.name)
                if not matches:
                    logger.debug('Non-version: %s', version_dir)
                    continue
                version: Version = Version(matches.group(1))
                if version < Version('2.4.0'):
                    logger.debug('Version %s : version trop ancienne, ignorée', version)
                elif version > PapiWebConfig.version:
                    logger.debug('Version %s : version plus récente, ignorée', version)
                elif version == PapiWebConfig.version:
                    logger.debug('Version %s : version courante, ignorée', version)
                else:
                    previous_versions.append(version)
            previous_databases: dict[Version, list[Path]] = {}
            if previous_versions:
                previous_versions.sort()
                for version in previous_versions:
                    version_dir = Path('..') / f'papi-web-{version}'
                    files: list[Path] = list(version_dir.glob('events/*.db'))
                    if files:
                        logger.info(
                            '- Version %s (évènements : %s)', version, ', '.join([file.stem for file in files]))
                        previous_databases[version] = files
                    else:
                        logger.info('- Version %s : aucun évènement trouvé', version)
                if not previous_databases:
                    logger.info('Aucun évènement de versions précédemment installées n\'a été trouvé.')
            else:
                logger.info('Aucune version précédente n\'a été trouvée.')
            recovered_version: Version | None = None
            if previous_databases:
                # keep the versions with databases only
                previous_versions = list(previous_databases.keys())
                previous_versions.sort()
                version_num: int | None = None
                if len(previous_databases) == 1:
                    while True:
                        match input_interactive(
                            f'Voulez-vous récupérer la configuration de la version {previous_versions[0]} [O/n] ?'):
                            case '' | 'O':
                                version_num = 1
                                break
                            case 'N':
                                break
                else:
                    print_interactive(f'Veuillez choisir la version dont vous souhaitez récupérer la configuration :')
                    version_range = range(1, len(previous_versions) + 1)
                    for num in version_range:
                        version: Version = previous_versions[num - 1]
                        print_interactive(f'  - [{num}] {version} ({", ".join([file.stem for file in previous_databases[version]])})')
                    print_interactive('  - [Q] ne rien récupérer')
                    while True:
                        match choice := input_interactive(f'Veuillez choisir la version [{previous_versions[-1]}] :'):
                            case 'Q':
                                break
                            case '':
                                version_num = len(previous_versions)
                                break
                            case _:
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
                while True:
                    match input_interactive('Voulez-vous installer des bases de données d\'exemple [O/n] ?'):
                        case '' | 'O':
                            for event_id in (
                                    file.stem for file in
                            PapiWebConfig.database_yml_path.glob(f'*.{PapiWebConfig.yml_ext}')
                            ):
                                EventDatabase(event_id).create(populate=True)
                            break
                        case 'N':
                            break

    @classmethod
    def _recover_previous_version(cls, version: Version, files: list[Path]):
        """Recover all the configuration of a previous version (events, Papi files and customization files)."""
        logger.info('Récupération des évènements de la version %s...', version)
        tournaments_number: int = 0
        version_dir = Path('..') / f'papi-web-{version}'
        for file in files:
            event_uniq_id: str = file.stem
            logger.info('Récupération de l\'évènement %s...', event_uniq_id)
            event_database: EventDatabase = EventDatabase(event_uniq_id)
            # copy the event database to its new destination
            shutil.copy(file, event_database.file)
            # now open the event database to search for local Papi files
            event: Event = EventLoader.get(request=None).load_event(event_uniq_id)
            for tournament in event.tournaments_by_id.values():
                src_file: Path = version_dir / 'papi' / f'{tournament.filename}.{PapiWebConfig.papi_ext}'
                if tournament.path == PapiWebConfig.default_papi_path and src_file.exists():
                    # recover the Papi file where stored in the default folder
                    logger.info(
                        f'Évènement [%s] : récupération du tournoi %s...', event_uniq_id, tournament.uniq_id)
                    shutil.copy(src_file, tournament.file)
                    logger.debug(str(src_file) + ' > ' + str(tournament.file))
                    tournaments_number += 1
        custom_files: list[Path] = []
        custom_dir: Path = version_dir / 'custom'
        if custom_dir.is_dir():
            for item in custom_dir.glob('**/*'):
                if item.is_file():
                    embedded_item: Path = Path(str(item).replace(str(custom_dir), str(PapiWebConfig.embedded_custom_path)))
                    if not embedded_item.exists() or not filecmp.cmp(item, embedded_item):
                        target_item: Path = Path(str(item).replace(str(custom_dir), str(PapiWebConfig.custom_path)))
                        target_item.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(item, target_item)
                        custom_files.append(item)
        logger.info(
            'Évènements récupérés : %d (dans le répertoire %s)',
            len(files), PapiWebConfig.event_path)
        logger.info(''
                    'Tournois récupérés : %d (dans le répertoire %s)',
                    tournaments_number, PapiWebConfig.default_papi_path)
        if custom_files:
            logger.info(
                'Fichiers de personnalisation récupérés : %d (dans le répertoire %s)',
                len(custom_files), PapiWebConfig.custom_path)
            for custom_file in custom_files:
                logger.info(f'- {str(custom_file).replace(str(custom_dir), "")}')
            while True:
                match input_interactive(
                    'Voulez-vous transmettre ces fichiers aux développeur·euses de Papi-web pour qu\'ils soient '
                    'intégrés dans une future version [O/n] ?'):
                    case '' | 'O':
                        cls._send_custom_files({
                            str(custom_file).replace(str(custom_dir), '').replace('\\', '/').lstrip('/'): custom_file
                            for custom_file in custom_files
                        })
                        break
                    case 'N':
                        break

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
        except ConnectionError as e:
            logger.error('Veuillez vérifier votre connection à internet [%s] : %s', url, e)
        except Timeout as e:
            logger.error('Le site filebin.net est indisponible [%s] : %s', url, e)
        except RequestException as e:
            logger.error('Le site filebin.net a renvoyé une erreur [%s] : %s', url, e)
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
        logger.info('Envoi des fichiers sur un serveur en ligne...')
        datetime_str: str = datetime.strftime(datetime.fromtimestamp(time.time()), "%Y-%m-%d-%H-%M-%S")
        bin_name: str = f'papi-web-custom-files-{datetime_str}'
        if cls._upload_bin_files(bin_name, custom_files):
            logger.info('Les fichiers ont été envoyé dans la corbeille %s :', bin_name)
            logger.info('- Voir les fichiers en ligne : %s', cls._bin_url(bin_name))
            logger.info('- Télécharger au format ZIP : %s', cls._bin_zip_url(bin_name))
            subject: str = '[Papi-web] Demande d\'intégration de fichiers de personnalisation'
            body: str = '<p>Bonjour,</p>'
            body += '<p>J\'aimerais que les fichiers suivants soient intégrés dans une prochaine distribution de Papi-web :</p>'
            body += '<ul>'
            for filename in custom_files:
                body += f'<li>{filename}</li>'
            body += '</ul>'
            body += '<p>Merci :-)</p>'
            body += '<ul>'
            body += f'<li><a href="{cls._bin_url(bin_name)}">Voir les fichiers déposés sur filebin.net</a></li>'
            body += f'<li><a href="{cls._bin_zip_url(bin_name)}">Télécharger au format ZIP</a></li>'
            body += '</ul>'
            body += '<p>Ajoutez ici toutes les informations que vous jugez nécessaires, et si vous n\'êtes pas connu·e du projet, présentez-vous !</p>'
            body += '<p>Prénom NOM</p>'
            mail_url: str = f'mailto:{PapiWebConfig.mail}?subject={subject}&html-body={body}'
            logger.info(
                'Une fenêtre va \'ouvrir pour envoyer un mél au projet Papi-web ; si la fenêtre ne s\'ouvre pas, '
                'veuillez cliquer sur le lien ci-dessous ou envoyer manuellement un mail à %s.', PapiWebConfig.mail)
            logger.info('%s', mail_url)
            webbrowser.open(mail_url, 0)

    @classmethod
    def _check_version(cls) -> Version | None:
        """Compares the current version with the last available stable version
        on the Papi-web GitHub repository.
        Returns the last stable version available if any, None otherwise."""
        last_stable_version: Version | None = cls._get_last_stable_version()
        if not last_stable_version:
            logger.warning('La vérification de la version a échoué')
            return None
        if last_stable_version == PapiWebConfig.version:
            logger.info('Votre version de Papi-web est à jour')
            return None
        last_stable_matches = re.match(
            r'^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$', str(last_stable_version))
        if re.match(r'^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$', str(PapiWebConfig.version)):
            if last_stable_version > PapiWebConfig.version:
                logger.warning('Une version plus récente que la vôtre est disponible (%s)',
                               last_stable_version)
                return last_stable_version
            logger.warning('Vous utilisez une version plus récente que la dernière version stable disponible (%s), '
                           'vous ne seriez pas développeur des fois ?', last_stable_version)
            return None
        if not (matches := re.match(r'^(?P<major>\d+)\.(?P<minor>\d+)rc(?P<rc>\d+)$', str(PapiWebConfig.version))):
            raise ValueError(f'Version de Papi-web invalide [{str(PapiWebConfig.version)}]')
        if last_stable_matches.group('major') > matches.group('major'):
            logger.warning('Une version majeure stable plus récente que la vôtre est disponible (%s) mais la mise à '
                           'jour des versions non stables (comme celle que vous utilisez actuellement : %s) doit être '
                           'réalisée manuellement (il est conseillé de faire la mise à jour de la dernière version stable '
                           'installée sur votre serveur.',
                           last_stable_version, PapiWebConfig.version)
            return None
        if last_stable_matches.group('minor') > matches.group('minor'):
            logger.warning('Une version mineure stable plus récente que la vôtre est disponible (%s) mais la mise à '
                           'jour des versions non stables (comme celle que vous utilisez actuellement : %s) doit être '
                           'réalisée manuellement (il est conseillé de faire la mise à jour de la dernière version stable '
                           'installée sur votre serveur.',
                           last_stable_version, PapiWebConfig.version)
            return None
        logger.info('Vous utilisez une version non stabilisée plus récente que la dernière version stable '
                    'disponible (%s)', last_stable_version)
        return None

    @staticmethod
    def _get_last_stable_version() -> Version | None:
        """Retrieves the available versions from the Papi-web GitHub
        repository.
        If an error occurred, returns None.
        Otherwise, the last stable version is returned."""
        url: str = 'https://api.github.com/repos/papi-web-org/papi-web/releases'
        try:
            logger.info('Recherche d\'une version plus récente sur GitHub (%s)...', url)
            response: Response = get(url, allow_redirects=True, timeout=5)
            response.raise_for_status()
            if not response:
                logger.debug('Pas de réponse reçue de GitHub (%s)', url)
                return None
            data: str = response.content.decode()
            logger.debug('Données de la réponse : %s', data)
            if response.status_code == 200:
                logger.debug('Données récupérées de la plateforme GitHub : %s octets',
                             len(data))
            try:
                entries: list[dict[str, Any]] = json.loads(data)
            except JSONDecodeError as jde:
                logger.debug('Impossible de décoder le JSON reçu: %s', jde)
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
                logger.debug('Aucune version stable trouvée')
                return None
            versions.sort(key=Version)
            logger.debug('releases=%s', versions)
            return Version(versions[-1])
        except ConnectionError as e:
            logger.warning('Veuillez vérifier votre connection à internet : %s', e)
            return None
        except Timeout as e:
            logger.warning('La plateforme GitHub est indisponible : %s', e)
            return None
        except HTTPError as e:
            logger.warning('La plateforme GitHub a renvoyé l\'erreur %s %s', e.errno, e.strerror)
            return None
        except RequestException as e:
            logger.warning('La plateforme GitHub a renvoyé une erreur : %s', e)
            return None

    @staticmethod
    def _install_new_version(version: Version) -> bool:
        """Install the new stable version at the same directory level.
        Returns True on success, False otherwise."""
        url: str = f'https://github.com/papi-web-org/papi-web/releases/download/{version}/papi-web-{version}.zip'
        new_version_dir: Path = Path('..') / f'papi-web-{version}'
        if new_version_dir.exists():
            logger.error(
                'La version %s est déjà installée dans le répertoire %s, veuillez supprimer manuellement le '
                'répertoire pour procéder à l\'installation',
                version, new_version_dir.absolute())
            return False
        try:
            new_version_dir.mkdir()
            logger.info('Téléchargement de la version %s sur GitHub (%s)...', version, url)
            response: Response = get(url, allow_redirects=True, timeout=5)
            response.raise_for_status()
            if not response:
                logger.error('Pas de réponse reçue de GitHub (%s)', url)
                return False
            if response.status_code != 200:
                logger.error('Le téléchargement de la version %s sur GitHub (%s) a échoué', version)
                return False
            zip_file = TMP_DIR / f'papi-web-{version}.zip'
            zip_file.write_bytes(response.content)
            logger.info('Fichier téléchargé : %s', zip_file)
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(new_version_dir)
            logger.info('La nouvelle version %s a été installée dans le répertoire %s', version, new_version_dir.absolute())
            return True
        except ConnectionError as e:
            logger.error('Veuillez vérifier votre connection à internet : %s', e)
            return False
        except Timeout as e:
            logger.error('La plateforme GitHub est indisponible : %s', e)
            return False
        except HTTPError as e:
            logger.error('La plateforme GitHub a renvoyé l\'erreur %s %s', e.errno, e.strerror)
            return False
        except RequestException as e:
            logger.error('La plateforme GitHub a renvoyé une erreur : %s', e)
            return False
