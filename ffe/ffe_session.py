import re
import time
import webbrowser
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any

from AdvancedHTMLParser import AdvancedHTMLParser, AdvancedTag
from requests import Session, Response
from requests.exceptions import ConnectionError, Timeout, RequestException
from logging import Logger

from common.papi_web_config import TMP_DIR
from data.tournament import Tournament
from common.logger import get_logger
from database.papi import PapiDatabase
from database.sqlite import EventDatabase

logger: Logger = get_logger()

FFE_URL: str = 'http://admin.echecs.asso.fr'

VIEW_STATE_INPUT_ID: str = '__VIEWSTATE'
VIEW_STATE_GENERATOR_INPUT_ID: str = '__VIEWSTATEGENERATOR'
EVENT_VALIDATION_INPUT_ID: str = '__EVENTVALIDATION'

VIEW_LINK_ID: str = 'ctl00_ContentPlaceHolderMain_LinkViewTournoi'
SET_VISIBLE_LINK_ID: str = 'ctl00_ContentPlaceHolderMain_CmdAfficherTournoi'
SET_VISIBLE_EVENT: str = SET_VISIBLE_LINK_ID.replace('_', '$')
FEES_LINK_ID: str = 'ctl00_ContentPlaceHolderMain_CmdFactureHomologation'
FEES_EVENT: str = 'ctl00$ContentPlaceHolderMain$CmdFactureHomologation'
UPLOAD_LINK_ID: str = 'ctl00_ContentPlaceHolderMain_CmdUploadPapi'
UPLOAD_EVENT: str = UPLOAD_LINK_ID.replace('_', '$')
UPLOAD_FILE_ID: str = 'ctl00$ContentPlaceHolderMain$UploadPapi'
UPLOAD_RI_LINK_ID = 'ctl00_ContentPlaceHolderMain_CmdUploadRI'
UPLOAD_RI_EVENT: str = UPLOAD_RI_LINK_ID.replace('_', '$')
UPLOAD_RI_FILE_ID = 'ctl00$ContentPlaceHolderMain$UploadRI'

FEES_DIR: Path = Path('fees')

class FFEAction(Enum):
    UPLOAD_PAPI = auto()
    UPLOAD_PAPI_AND_SET_VISIBLE = auto()
    UPLOAD_RI = auto()
    
class FFESession(Session):
    """A requests session specialized for communication with the FFE website.
    Currently, it relies on hacks, because no API is available."""
    def __init__(self, tournament: Tournament, debug: bool):
        super().__init__()
        self.tournament: Tournament = tournament
        self.debug = debug
        self.ffe_state: dict[str, str] | None = None
        self.auth_state: dict[str, str] | None = None
        self.tournament_ffe_url: str | None = None
        self.last_url_read: str | None = None

    def _read_url(
            self, url: str, data: dict[str, str] | None, files: dict[str, Path] | None) -> str | None:
        """Reads any URL and returns the content as a string, or None on error (the error is logged).
        When debug is True, log the request contents received."""
        self.last_url_read = url
        handlers: dict[str, Any] = {}
        try:
            if self.debug:
                logger.info('read_url(%s), method=%s', url, 'POST' if data or files else 'GET')
            if not data and not files:
                response: Response = self.get(url)
            else:
                if self.debug:
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
                if not files:
                    response: Response = self.post(url, data=data)
                else:
                    handlers = {
                        file_id: open(file_name, 'rb')
                        for file_id, file_name in files.items()
                    }
                    response: Response = self.post(url, data=data, files=handlers)
                    for handler in handlers.values():
                        handler.close()
            content: str = response.content.decode()
            if self.debug:
                date_str = datetime.strftime(datetime.fromtimestamp(time.time()), '%Y-%m-%d-%H-%M-%S')
                debug_file = TMP_DIR / f'{url.replace("/", "_").replace(":", "_")}-{date_str}-raw.html'
                with open(debug_file, 'w') as file:
                    file.write(content)
                logger.info('Raw content stored to %s', debug_file)
            return content
        except ConnectionError as e:
            logger.error('Veuillez vérifier votre connection à internet [%s] : %s', url, e)
        except Timeout as e:
            logger.error('Le site fédéral est indisponible [%s] : %s', url, e)
        except RequestException as e:
            logger.error('Le site fédéral a renvoyé une erreur [%s] : %s', url, e)
        for handler in handlers.values():
            handler.close()
        return None

    def _parse_html_content(self, html: str) -> tuple[AdvancedHTMLParser | None, str | None]:
        """Parses any HTML content received and returns the parsed content
        (as an HTML parser) and an error (as a string) if any (or None)"""
        parser: AdvancedHTMLParser = AdvancedHTMLParser()
        error: str | None = None
        parser.parseStr(html)
        if self.debug:
            date_str = datetime.strftime(datetime.fromtimestamp(time.time()), '%Y-%m-%d-%H-%M-%S')
            debug_file = TMP_DIR / f'{self.last_url_read.replace("/", "_").replace(":", "_")}-{date_str}-parsed.html'
            with open(debug_file, 'w', encoding="utf-8") as file:
                file.write(parser.getHTML())
            logger.info('Parsed content stored to %s', debug_file)
        tag: AdvancedTag = parser.getElementById('ctl00_ContentPlaceHolderMain_LabelError')
        if tag:
            if tag.innerText:
                matches = re.match(r'^Transfert du fichier : .*\.papi \(\d+ octets\) achevé$', tag.innerText)
                if not matches:
                    error = tag.innerText
                    logger.error(error)
        return parser, error

    def read_ffe_state(self, parser: AdvancedHTMLParser, url: str) -> bool:
        """Reads the main state variables of a request and stores them into self.ffe_state.
        Returns True on success, False otherwise."""
        self.ffe_state: dict[str, str] = {}
        for id in [VIEW_STATE_INPUT_ID, VIEW_STATE_GENERATOR_INPUT_ID, EVENT_VALIDATION_INPUT_ID, ]:
            tag: AdvancedTag = parser.getElementById(id)
            if not tag:
                logger.error('Content of URL [%s] is not valid (input[id=[%s] not found)', url, id)
                return False
            self.ffe_state[id] = tag.attributesDict['value']
            if self.debug:
                logger.info(
                    '> ffe_state[%s]=[%s]', id,
                    self.ffe_state[id][:64] + ('...' if len(self.ffe_state[id]) > 64 else '')
                    if self.ffe_state[id] else 'None')
        return True

    def _ffe_init(self) -> bool:
        """Initializes a session on the FFE admin website (mostly gets state variables).
        Return True on success, False otherwise."""
        url = FFE_URL
        html: str = self._read_url(url=url, data=None, files=None)
        if not html:
            return False
        parser, error = self._parse_html_content(html)
        if error:
            return False
        return self.read_ffe_state(parser, url)

    def _ffe_auth(self) -> bool:
        """Authenticates on the FFE admin website."""
        assert self.ffe_state
        url = FFE_URL + '/Default.aspx'
        post_data: dict[str, str] = {
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[VIEW_STATE_GENERATOR_INPUT_ID],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
            'ctl00$TextLogin': str(self.tournament.ffe_id),
            'ctl00$TextPassword': self.tournament.ffe_password,
            'ctl00$CmdLogin.x': '12',
            'ctl00$CmdLogin.y': '6',
        }
        html: str = self._read_url(url=url, data=post_data, files=None)
        if not html:
            return False
        parser, error = self._parse_html_content(html)
        if error:
            return False
        if not self.read_ffe_state(parser, url):
            return False
        self.auth_state: dict[str, str] = {}
        for id in [SET_VISIBLE_LINK_ID, FEES_LINK_ID, UPLOAD_LINK_ID, UPLOAD_RI_LINK_ID]:
            tag: AdvancedTag = parser.getElementById(id)
            self.auth_state[id] = tag.innerText if tag else None
            if self.debug:
                logger.info(
                    '> auth_state[%s]=[%s]', id,
                    self.auth_state[id][:64] + ('...' if len(self.auth_state[id]) > 64 else '')
                    if self.auth_state[id] else 'None')
        tag: AdvancedTag = parser.getElementById(VIEW_LINK_ID)
        if not tag:
            logger.error('L\'authentification a échoué (vérifier les codes)')
            return False
        self.tournament_ffe_url = tag.attributesDict['href']
        if self.debug:
            logger.info('> tournament_ffe_url=[%s]', self.tournament_ffe_url)
        return True

    def test_auth(self):
        """Tries to authenticate on the FFE admin website for the tournament."""
        logger.info('Tournoi [%s] :', self.tournament.ffe_id)
        if not self._ffe_init():
            return
        # logger.info('init OK')
        if not self._ffe_auth():
            return
        logger.info('auth OK: %s', self.tournament_ffe_url)

    def get_fees(self):
        """Downloads the fees for the tournament."""
        logger.info('Tournoi [%s] :', self.tournament_ffe_url)
        if not self._ffe_init():
            return
        # logger.info('init OK')
        if not self._ffe_auth():
            return
        logger.info('auth OK: %s', self.tournament_ffe_url)
        if self.debug:
            logger.info('> auth_state[%s]=[%s]', FEES_LINK_ID, self.auth_state[FEES_LINK_ID])
        if self.auth_state[FEES_LINK_ID] is None:
            logger.warning(
                'Lien de facturation non trouvé (vérifier qu\'un fichier Papi a déjà été téléchargé '
                'ou que le tournoi n\'a pas déjà été archivé)')
            return
        if self.auth_state[FEES_LINK_ID].lower() == 'tournoi exempté de droits':
            logger.info('Tournoi exempt de droits d\'homologation')
            return
        if self.auth_state[FEES_LINK_ID].lower() != 'afficher la facture':
            logger.error('Invalid fees link text [%s]', self.auth_state[FEES_LINK_ID])
            return
        url = FFE_URL + '/MonTournoi.aspx'
        post_data: dict[str, str] = {
            '__EVENTTARGET': FEES_EVENT,
            '__EVENTARGUMENT': '',
            VIEW_STATE_INPUT_ID: self.auth_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.auth_state[VIEW_STATE_GENERATOR_INPUT_ID],
            EVENT_VALIDATION_INPUT_ID: self.auth_state[EVENT_VALIDATION_INPUT_ID],
        }
        html: str = self._read_url(url=url, data=post_data, files=None)
        if not html:
            return
        FEES_DIR.mkdir(exist_ok=True, parents=True)
        base: AdvancedTag = AdvancedTag('base')
        base.setAttribute('href', FFE_URL)
        parser, error = self._parse_html_content(html)
        if error:
            return False
        head: AdvancedTag = parser.getElementsByTagName('head')[0]
        head.insertBefore(base, head.getChildren()[0])
        file: Path = Path(FEES_DIR, str(self.tournament.ffe_id) + '-fees.html')
        with open(file, 'w', encoding="utf-8") as f:
            f.write(parser.getHTML())
        logger.info('Facture d\'homologation enregistrée dans [%s]', file)
        webbrowser.open(f'file://{file.resolve()}', new=2)
        logger.info('fees OK')
        return

    def upload(self, action: FFEAction):
        """Upload the tournament to the FFE admin website."""
        logger.info(
            'Mise à jour du tournoi [%s] (%s) sur le site fédéral :',
            self.tournament.ffe_id, self.tournament.file)
        if not self._ffe_init():
            return
        # logger.info('init OK')
        if not self._ffe_auth():
            return
        logger.info('auth OK: %s', self.tournament_ffe_url)
        upload_link_id = UPLOAD_RI_LINK_ID if action == FFEAction.UPLOAD_RI else UPLOAD_LINK_ID
        upload_event = UPLOAD_RI_EVENT if action == FFEAction.UPLOAD_RI else UPLOAD_EVENT
        upload_file_id = UPLOAD_RI_FILE_ID if action == FFEAction.UPLOAD_RI else UPLOAD_FILE_ID
        if self.debug:
            logger.info('> auth_state[%s]=[%s]', upload_link_id, self.auth_state[upload_link_id])
        if self.auth_state[upload_link_id] is None:
            logger.warning('Lien de mise en ligne non trouvé (vérifier que le tournoi n\'est pas terminé)')
            return
        url = FFE_URL + '/MonTournoi.aspx'
        post: dict[str, str] = {
            '__EVENTTARGET': upload_event,
            '__EVENTARGUMENT': '',
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[VIEW_STATE_GENERATOR_INPUT_ID],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        date: str = datetime.fromtimestamp(time.time()).strftime("%Y%m%d%H%M%S")
        if action == FFEAction.UPLOAD_RI:
            if not self.tournament.rules:
                logger.warning('Aucun fichier spécifié pour le règlement du tournoi [%s].', self.tournament.name)
                return
            else:
                ri_file = Path(self.tournament.rules)
                logger.info('Chemin du fichier RI: [%s]', ri_file)
                if not ri_file.exists():
                    logger.error('Fichier RI non trouvé [%s]', ri_file)
                else:
                    html: str = self._read_url(url=url, data=post, files={upload_file_id: ri_file, })
        else:
            tmp_file: Path = TMP_DIR / 'ffe' / f'{self.tournament.file.stem}-{date}{self.tournament.file.suffix}'
            tmp_file.parents[0].mkdir(parents=True, exist_ok=True)
            logger.debug('Copie de %s vers %s...', self.tournament.file, tmp_file)
            tmp_file.write_bytes(self.tournament.file.read_bytes())
            with PapiDatabase(tmp_file, write=True) as tmp_database:
                tmp_database: PapiDatabase
                logger.debug('Suppression des données personnelles des joueur·euses...')
                tmp_database.delete_players_personal_data()
                logger.debug('Suppression des forfaits si aucun appariement...')
                tmp_database.remove_forfeits_if_no_pairings()
                tmp_database.commit()
            html: str = self._read_url(url=url, data=post, files={upload_file_id: tmp_file, })
            tmp_file.unlink()
        if not html:
            return
        _, error = self._parse_html_content(html)
        if error:
            return
        if action != FFEAction.UPLOAD_RI:
            with EventDatabase(self.tournament.event.uniq_id, write=True) as event_database:
                event_database.set_tournament_last_ffe_upload(self.tournament.id)
                event_database.commit()
        logger.info('upload OK')
        if action != FFEAction.UPLOAD_PAPI_AND_SET_VISIBLE:
            return
        if self.debug:
            logger.info('> auth_state[%s]=[%s]', SET_VISIBLE_LINK_ID, self.auth_state[SET_VISIBLE_LINK_ID])
        if self.auth_state[SET_VISIBLE_LINK_ID] is None:
            logger.warning('Lien d\'affichage non trouvé (vérifier qu\'un fichier Papi a déjà été téléchargé)')
            return
        if self.auth_state[SET_VISIBLE_LINK_ID].lower().startswith('désactiver'):
            logger.info('Les données sont déjà affichées')
            return
        if not self.auth_state[SET_VISIBLE_LINK_ID].lower().startswith('activer'):
            logger.error('Invalid display link text [%s]', self.auth_state[SET_VISIBLE_LINK_ID])
            return
        url = FFE_URL + '/MonTournoi.aspx'
        post_data: dict[str, str] = {
            '__EVENTTARGET': SET_VISIBLE_EVENT,
            '__EVENTARGUMENT': '',
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[VIEW_STATE_GENERATOR_INPUT_ID],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        html: str = self._read_url(url=url, data=post_data, files=None)
        if not html:
            return
        logger.info('show OK')
