import re
import shutil
import tempfile
from functools import partial
from logging import Logger
from pathlib import Path
from typing import Any

from AdvancedHTMLParser import AdvancedHTMLParser, AdvancedTag
from requests import Session
from requests.exceptions import ConnectionError, Timeout, RequestException, HTTPError

from common import SharlyChessException
from common.i18n import _
from common.logger import get_logger
from data.event import Event
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_upload_status import (
    FailureFFEUploadStatus,
    NotReachableFFEUploadStatus,
    AuthFailureFFEUploadStatus,
    FinishedFailureFFEUploadStatus,
    PapiConversionFailureFFEUploadStatus,
    UnexpectedFailureFFEUploadStatus,
)
from plugins.ffe.papi_converter import PapiConverter
from plugins.ffe.utils import FFEUtils, PlayerFFELicence, FFEArbiterTitle, FFE_LEAGUES
from plugins.utils import PluginUtils

logger: Logger = get_logger()

FFE_PUBLIC_URL: str = 'http://echecs.asso.fr'
FFE_ADMIN_URL: str = 'http://admin.echecs.asso.fr'

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
UPLOAD_RULES_LINK_ID: str = 'ctl00_ContentPlaceHolderMain_CmdUploadRI'
UPLOAD_RULES_EVENT: str = UPLOAD_RULES_LINK_ID.replace('_', '$')
UPLOAD_RULES_FILE_ID: str = 'ctl00$ContentPlaceHolderMain$UploadRI'

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FFESession(Session):
    """A requests session specialized for communication with the FFE website.
    Currently, it relies on hacks, because no API is available."""

    def __init__(
        self,
        tournament: Tournament | None,
    ):
        super().__init__()
        self.tournament: Tournament | None = tournament
        self.ffe_state: dict[str, str] = {}
        self.auth_state: dict[str, str | None] = {}
        self.tournament_ffe_url: str | None = None
        self.last_url_read: str | None = None

    def _read_url(
        self, url: str, data: dict[str, str] | None, files: dict[str, Path] | None
    ) -> str | None:
        """Reads any URL and returns the content as a string, or None on error (the error is logged).
        When debug is True, log the request contents received."""
        self.last_url_read = url
        handlers: dict[str, Any] = {}
        try:
            logger.debug(
                'read_url(%s), method=%s', url, 'POST' if data or files else 'GET'
            )
            if not data and not files:
                response = self.get(url)
            else:
                if data:
                    logger.debug('- data:')
                    for field_id, field in data.items():
                        field = str(field) if field is not None else ''
                        if (
                            'password' in field_id.lower()
                            or 'passwd' in field_id.lower()
                        ):
                            logger.debug('  - %s: [********]', field_id)
                        else:
                            logger.debug(
                                '  - %s: [%s]',
                                field_id,
                                field[:64] + ('...' if len(field) > 64 else '')
                                if field
                                else 'None',
                            )
                if files:
                    logger.debug('- files:')
                    for field_id, file in files.items():
                        logger.debug('  - %s: [%s]', field_id, file)
                if not files:
                    response = self.post(url, data=data)
                else:
                    handlers = {
                        file_id: open(file_name, 'rb')
                        for file_id, file_name in files.items()
                    }
                    response = self.post(url, data=data, files=handlers)
            return response.content.decode()
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
        finally:
            for handler in handlers.values():
                handler.close()
        return None

    def _parse_html_content(self, html) -> tuple[AdvancedHTMLParser | None, str | None]:
        """Parses any HTML content received and returns the parsed content
        (as an HTML parser) and an error (as a string) if any (or None)"""
        parser: AdvancedHTMLParser = AdvancedHTMLParser()
        error: str | None = None
        parser.parseStr(html)
        assert self.last_url_read is not None
        tag: AdvancedTag | None = parser.getElementById(
            tag_id := 'ctl00_ContentPlaceHolderMain_LabelError'
        )
        if tag:
            if tag.innerText:
                matches = re.match(
                    r'^Transfert du fichier : .* \(\d+ octets\) achevé$', tag.innerText
                )
                if matches:
                    logger.debug('Tag [%s] matches: [%s]', tag_id, tag.innerText)
                else:
                    error = tag.innerText
                    logger.error('Tag [%s] does not match: [%s]', tag_id, tag.innerText)
        return parser, error

    def read_ffe_state(
        self,
        parser: AdvancedHTMLParser,
        url: str,
        admin: bool,
    ) -> bool:
        """Reads the main state variables of a request and stores them into self.ffe_state.
        Returns True on success, False otherwise."""
        ids: list[str] = [
            VIEW_STATE_INPUT_ID,
            VIEW_STATE_GENERATOR_INPUT_ID,
        ]
        if admin:
            ids.append(EVENT_VALIDATION_INPUT_ID)
        for id_ in ids:
            tag: AdvancedTag | None = parser.getElementById(id_)
            if not tag:
                logger.error(
                    'Content of URL [%s] is not valid (input[id=[%s] not found).',
                    url,
                    id_,
                )
                logger.error(parser.asHTML())
                return False
            value = getattr(tag, 'attributesDict', {}).get('value', '')
            self.ffe_state[id_] = str(value)
            logger.debug(
                '> ffe_state[%s]=[%s]',
                id_,
                self.ffe_state[id_][:64]
                + ('...' if len(self.ffe_state[id_]) > 64 else '')
                if self.ffe_state[id_]
                else 'None',
            )
        return True

    def _ffe_init(
        self,
        admin: bool,
    ) -> bool:
        """Initializes a session on the FFE admin website (mostly gets state variables).
        Return True on success, False otherwise."""
        url = FFE_ADMIN_URL if admin else FFE_PUBLIC_URL
        logger.debug('Initializing a session to [%s]...', url)
        html: str | None = self._read_url(url=url, data=None, files=None)

        if not html or (parsed := self._parse_html_content(html))[1]:
            return False
        parser = parsed[0]
        if result := self.read_ffe_state(parser, url, admin):
            logger.debug('Session initialized.')
        return result

    def _ffe_auth(self, ffe_id: int, ffe_password: str) -> bool:
        """Authenticates on the FFE admin website.
        Returns True on success, False if the credentials are incorrect."""

        assert self.ffe_state
        if ffe_id is None or ffe_password is None:
            return False
        logger.debug('Authenticating...')
        url = FFE_ADMIN_URL + '/Default.aspx'
        post_data: dict[str, str] = {
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
            'ctl00$TextLogin': str(ffe_id),
            'ctl00$TextPassword': ffe_password,
            'ctl00$CmdLogin.x': '12',
            'ctl00$CmdLogin.y': '6',
        }
        html: str | None = self._read_url(url=url, data=post_data, files=None)
        if not html:
            return False
        parser, error = self._parse_html_content(html)
        if error:
            return False
        assert parser is not None
        if not self.read_ffe_state(parser, url, True):
            return False
        for id_ in [
            SET_VISIBLE_LINK_ID,
            FEES_LINK_ID,
            UPLOAD_LINK_ID,
            UPLOAD_RULES_LINK_ID,
        ]:
            tag = parser.getElementById(id_)
            self.auth_state[id_] = (tag.innerText or None) if tag else None
            inner_text = self.auth_state[id_] or ''
            logger.debug(
                '> auth_state[%s]=[%s]',
                id_,
                inner_text[:64] + ('...' if len(inner_text) > 64 else '')
                if self.auth_state[id_]
                else 'None',
            )
        tag = parser.getElementById(VIEW_LINK_ID)
        if not tag:
            logger.error('Authentication failed.')
            return False
        value = getattr(tag, 'attributesDict', {}).get('href', '')
        self.tournament_ffe_url = value
        logger.debug('> tournament_ffe_url=[%s]', self.tournament_ffe_url)
        logger.debug('FFE authentication succeeded.')
        return True

    def test_auth(self, ffe_id: int, ffe_password: str) -> bool | None:
        """Tries to authenticate on the FFE admin website for the tournament.
        Returns True on success, False if the credentials are incorrect, or
        None if they couldn't be tested."""

        logger.info('Testing FFE authentication for tournament [%d]...', ffe_id)
        if not self._ffe_init(admin=True):
            return None
        if auth := self._ffe_auth(ffe_id, ffe_password):
            logger.info('FFE authentication succeeded.')
        return auth

    def _validate_admin_access(self):
        ffe_id, ffe_password = self.get_id_and_password()

        if not ffe_id or not ffe_password:
            raise SharlyChessException('Certification number and password not set.')

        if not self._ffe_init(admin=True):
            raise SharlyChessException(_('FFE website could not be reached.'))
        if not self._ffe_auth(ffe_id, ffe_password):
            raise SharlyChessException(
                'Authentication failed, check the password and certification number.'
            )

    @staticmethod
    def _logged_exception() -> SharlyChessException:
        return SharlyChessException(
            _('An unexpected error occurred, consult the logs for more details.')
        )

    def get_fees(self) -> str | None:
        """Downloads the fees for the tournament.
        Returns None if the tournament has no fees, the html content if it has.
        Raises a localized SharlyChessException if it fails."""

        assert self.tournament is not None
        logger.info('Getting fees for tournament [%s]...', self.tournament.name)
        self._validate_admin_access()
        assert self.auth_state
        logger.debug(
            '> auth_state[%s]=[%s]', FEES_LINK_ID, self.auth_state[FEES_LINK_ID]
        )
        fees_link_id = self.auth_state[FEES_LINK_ID]
        if fees_link_id is None:
            raise SharlyChessException(
                _(
                    'Fees link not found, check that a tournament has already been '
                    'sent and that the tournament has not been archived on the FFE website.'
                )
            )
        if fees_link_id.lower() == 'tournoi exempté de droits':
            logger.info('Tournament exempt from registration fees.')
            return None
        if fees_link_id.lower() != 'afficher la facture':
            logger.error('Invalid fees link text [%s].', fees_link_id)
            raise self._logged_exception()
        url = FFE_ADMIN_URL + '/MonTournoi.aspx'
        post_data: dict[str, str] = {
            '__EVENTTARGET': FEES_EVENT,
            '__EVENTARGUMENT': '',
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        html: str | None = self._read_url(url=url, data=post_data, files=None)
        if not html:
            logger.error('Empty HTML on the fees page.')
            raise self._logged_exception()
        base: AdvancedTag = AdvancedTag('base')
        base.setAttribute('href', FFE_ADMIN_URL)
        parser, error = self._parse_html_content(html)
        assert parser is not None
        if error:
            logger.error(
                'Could not parse FFE response to [%s] with POST data [%s].',
                url,
                str(post_data),
            )
            logger.debug('Response received:\n%s', html)
            raise self._logged_exception()
        head: AdvancedTag | None = parser.getElementsByTagName('head')[0]
        if not head:
            logger.error(
                'Could not find tag HEAD in the FFE response to [%s] with POST data [%s].',
                url,
                str(post_data),
            )
            logger.debug('Response received:\n%s', html)
            raise self._logged_exception()
        head.insertBefore(base, head.getChildren()[0])
        html = parser.getHTML()
        logger.info('Getting fees succeeded.')
        return html

    def get_id_and_password(
        self,
    ) -> tuple[int | None, str | None]:
        """Fetches the certification number and password for the tournament from the plugin data."""

        assert self.tournament is not None
        ffe_id = FFEUtils.get_tournament_plugin_data(self.tournament).ffe_id
        ffe_password = FFEUtils.get_tournament_plugin_data(self.tournament).password
        if not ffe_id or not ffe_password:
            logger.warning(
                'FFE certification number and password are not correctly set for tournament [%s], data can not be sent to the FFE website.',
                self.tournament.name,
            )
            return None, None
        else:
            return ffe_id, ffe_password

    def upload(self, set_visible: bool) -> FailureFFEUploadStatus | None:
        """Upload the tournament to the FFE admin website."""

        assert self.tournament is not None
        ffe_id, ffe_password = self.get_id_and_password()
        if not ffe_id or not ffe_password:
            return None

        logger.info(
            'Sending tournament [%d] (%s) to the FFE website...',
            ffe_id,
            self.tournament.name,
        )
        if not self._ffe_init(admin=True):
            return NotReachableFFEUploadStatus()
        if not self._ffe_auth(ffe_id, ffe_password):
            return AuthFailureFFEUploadStatus()
        logger.debug(
            '> auth_state[%s]=[%s]', UPLOAD_LINK_ID, self.auth_state[UPLOAD_LINK_ID]
        )
        if self.auth_state[UPLOAD_LINK_ID] is None:
            return FinishedFailureFFEUploadStatus()
        url = FFE_ADMIN_URL + '/MonTournoi.aspx'
        post: dict[str, str] = {
            '__EVENTTARGET': UPLOAD_EVENT,
            '__EVENTARGUMENT': '',
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }

        # Required to avoid writing in the tmp database
        self.tournament.set_tournament_players_pairing_numbers()

        event_uniq_id = self.tournament.event.uniq_id
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path: Path = Path(tmpdir)
            tmp_papi_file: Path = tmp_path / 'export.papi'
            tmp_sce_file: Path = tmp_path / 'event.sce'

            # Copy the event database to the tmp file
            database = EventDatabase(event_uniq_id)
            logger.debug('Copying [%s] to [%s]...', database.file, tmp_sce_file)
            shutil.copy(database.file, tmp_sce_file)

            # Prepare for upload
            with EventDatabase(
                file_path=tmp_sce_file, write=True, check_dirty_tournaments=False
            ) as tmp_event_database:
                tmp_event = Event(tmp_event_database.load_stored_event())
                tmp_tournament = tmp_event.tournaments_by_id[self.tournament.id]
                logger.debug("Deleting personal players' data...")
                tmp_event_database.delete_players_personal_data()

                # Delete all ZPBs if no pairings are found (at any round).
                # This fixes a display issue on the FFE website."""
                if not tmp_tournament.has_pairings:
                    logger.info('Deleting ZPBs...')
                    for player in tmp_tournament.tournament_players:
                        for pairing in player.pairings.values():
                            if pairing.zero_point_bye:
                                tmp_event_database.delete_stored_pairing(
                                    pairing.stored_pairing
                                )

                    logger.info('Done.')
                else:
                    logger.info('No ZPBs to delete.')

            try:
                logger.debug(
                    'Converting [%s] to [%s]...',
                    self.tournament.name,
                    tmp_papi_file,
                )
                PapiConverter().write_papi_file(
                    tmp_tournament,
                    tmp_papi_file,
                    anonymize_player_data=True,
                    is_ffe_upload=True,
                )
            except Exception as e:
                logger.error(
                    self.tournament.log_prefix
                    + f'Error during conversion to Papi format: {e}'
                )
                return PapiConversionFailureFFEUploadStatus()

            html: str | None = self._read_url(
                url=url,
                data=post,
                files={
                    UPLOAD_FILE_ID: tmp_papi_file,
                },
            )

            if not html:
                return UnexpectedFailureFFEUploadStatus()
            __, error = self._parse_html_content(html)
            if error:
                self.report_error('Upload failed: %s', error)
                return UnexpectedFailureFFEUploadStatus()

        if not set_visible:
            return None

        logger.info('Making the tournament visible on the FFE website...')
        logger.debug(
            '> auth_state[%s]=[%s]',
            SET_VISIBLE_LINK_ID,
            self.auth_state[SET_VISIBLE_LINK_ID],
        )
        if self.auth_state[SET_VISIBLE_LINK_ID] is None:
            logger.warning(
                'Display link not found, check that a Papi file has already been sent.'
            )
            return UnexpectedFailureFFEUploadStatus()
        set_visible_link_id = self.auth_state[SET_VISIBLE_LINK_ID]
        if set_visible_link_id is None:
            return UnexpectedFailureFFEUploadStatus()
        if set_visible_link_id.lower().startswith('désactiver'):
            logger.info('Data is already displayed on the FFE website.')
            return None
        if not set_visible_link_id.lower().startswith('activer'):
            logger.error(
                'Invalid display link text [{text}]'.format(
                    text=self.auth_state[SET_VISIBLE_LINK_ID]
                )
            )
            return UnexpectedFailureFFEUploadStatus()
        url = FFE_ADMIN_URL + '/MonTournoi.aspx'
        post_data: dict[str, str] = {
            '__EVENTTARGET': SET_VISIBLE_EVENT,
            '__EVENTARGUMENT': '',
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        html = self._read_url(url=url, data=post_data, files=None)
        if not html:
            logger.error('Visible page could not be loaded.')
            return UnexpectedFailureFFEUploadStatus()
        logger.info('Tournament visibility successfully set')
        return None

    def upload_rules(self, rules_file: Path):
        """Upload the rules of the tournament to the FFE admin website.
        Raises a localised SharlyChessException if it fails"""

        assert self.tournament is not None

        logger.info(
            'Sending the rules of tournament [%s] (%s) to the FFE website...',
            self.tournament.name,
            rules_file,
        )
        self._validate_admin_access()
        logger.debug(
            '> auth_state[%s]=[%s]',
            UPLOAD_RULES_LINK_ID,
            self.auth_state[UPLOAD_RULES_LINK_ID],
        )
        if self.auth_state[UPLOAD_RULES_LINK_ID] is None:
            raise SharlyChessException(
                _(
                    'Rules upload link not found, check that the tournament '
                    'is not marked as finished on the FFE website.'
                )
            )
        url = FFE_ADMIN_URL + '/MonTournoi.aspx'
        post: dict[str, str] = {
            '__EVENTTARGET': UPLOAD_RULES_EVENT,
            '__EVENTARGUMENT': '',
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        html = self._read_url(
            url=url,
            data=post,
            files={
                UPLOAD_RULES_FILE_ID: rules_file,
            },
        )
        if not html:
            logger.error('Empty HTML on the upload page.')
            raise self._logged_exception()
        __, error = self._parse_html_content(html)
        if error:
            logger.error(error)
            raise self._logged_exception()
        logger.info('Rules uploaded')


class FFEArbitersLoader(FFESession):
    def __init__(self):
        super().__init__(tournament=None)

    def load_ffe_arbiter_titles_by_ffe_licence_number(
        self,
    ) -> dict[str, FFEArbiterTitle]:
        """Returns a dict with FFE licence numbers as keys and arbiter strings as values."""

        data: dict[str, FFEArbiterTitle] = {}
        if self._ffe_init(admin=False):
            for league in FFE_LEAGUES:
                load_next_page = self._read_league_page_data(league, data, page := 1)
                while load_next_page:
                    page += 1
                    load_next_page = self._read_league_page_data(league, data, page)
        return data

    def _read_league_page_data(
        self,
        league: str,
        data: dict[str, FFEArbiterTitle],
        page_number: int = 1,
    ) -> bool:
        """Reads one page for a league, returns a dict with FFE licence numbers as keys and arbiter strings as values."""
        load_next_page: bool = False
        assert self.ffe_state
        url = f'{FFE_PUBLIC_URL}/ListeArbitres.aspx?Action=DNALIGUE&Ligue={league}'
        post_data: dict[str, str] = {}
        if page_number > 1:
            post_data: dict[str, str] = {
                '__EVENTTARGET': 'ctl00$ContentPlaceHolderMain$PagerFooter',
                '__EVENTARGUMENT': 'd',
                VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
                VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                    VIEW_STATE_GENERATOR_INPUT_ID
                ],
            }
        if html := self._read_url(url=url, data=post_data, files=None):
            parser, error = self._parse_html_content(html)
            if not error:
                assert parser is not None
                if self.read_ffe_state(parser, url, False):
                    """
                        <tr class=liste_clair>
                            <td align=center>A06885</td>
                            <td align=left><a href=mailto:luco.alain22@gmail.com class=lien_texte>LUCO Alain</td>
                            <td align=Left>Arbitre Club</td>
                            <td align=Left>2027-28</td>
                            <td align=left>Echiquier Guingampais</td>
                        </tr>
                    """
                    for tr_tag in parser.getElementsByTagName('tr'):
                        try:
                            ffe_licence_number: str = tr_tag.children[0].innerHTML
                            if PlayerFFELicence.validate(ffe_licence_number):
                                if (
                                    ffe_arbiter_title := FFEArbiterTitle.from_html(
                                        tr_tag.children[2].innerHTML
                                    )
                                ) != FFEArbiterTitle.NONE:
                                    data[ffe_licence_number] = ffe_arbiter_title
                        except IndexError:
                            pass
                    """
                        <a href="javascript:__doPostBack('ctl00$ContentPlaceHolderMain$PagerFooter','d')"><img src=Images/t_fleche_d.gif border=0/></a>
                    """
                    for img_tag in parser.getElementsByTagName('img'):
                        if img_tag.attributes['src'].lower() == 'images/t_fleche_d.gif':
                            load_next_page = True
                            break

        return load_next_page
