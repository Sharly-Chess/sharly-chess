from functools import partial
import re
import time
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Any

from AdvancedHTMLParser import AdvancedHTMLParser, AdvancedTag
from requests import Session
from requests.exceptions import ConnectionError, Timeout, RequestException, HTTPError

from common.i18n import _
from common.logger import get_logger
from data.tournament import Tournament
from database.access.papi.papi_database import PapiDatabase
from database.sqlite.event.event_database import EventDatabase
from plugins import ffe
from plugins.ffe import PLUGIN_NAME
from plugins.utils import PluginUtils

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
        report_info=logger.info,
        report_success=logger.info,
        report_error=logger.error,
    ):
        super().__init__()
        self.tournament: Tournament | None = tournament
        self.ffe_state: dict[str, str] = {}
        self.auth_state: dict[str, str | None] = {}
        self.tournament_ffe_url: str | None = None
        self.last_url_read: str | None = None
        self.report_info = report_info
        self.report_success = report_success
        self.report_error = report_error

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
            content: str = response.content.decode()
            date_str = datetime.strftime(
                datetime.fromtimestamp(time.time()), '%Y-%m-%d-%H-%M-%S'
            )
            debug_file = ffe.TMP_DIR / f'{url.replace("/", "_")}-{date_str}-raw.html'
            try:
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.debug('Raw content stored to %s.', debug_file)
            except OSError:
                logger.debug('Unable to store file [%s].', debug_file)
            return content
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
        date_str = datetime.strftime(
            datetime.fromtimestamp(time.time()), '%Y-%m-%d-%H-%M-%S'
        )
        debug_file = (
            ffe.TMP_DIR
            / f'{(self.last_url_read or "").replace("/", "_")}-{date_str}-parsed.html'
        )
        try:
            with open(debug_file, 'w', encoding='utf-8') as file:
                file.write(parser.getHTML())
            logger.debug('Raw content stored to %s.', debug_file)
        except OSError:
            logger.debug('Unable to store file [%s].', debug_file)
        logger.debug('Parsed content stored to %s', debug_file)
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

    def read_ffe_state(self, parser: AdvancedHTMLParser, url: str) -> bool:
        """Reads the main state variables of a request and stores them into self.ffe_state.
        Returns True on success, False otherwise."""
        for id_ in [
            VIEW_STATE_INPUT_ID,
            VIEW_STATE_GENERATOR_INPUT_ID,
            EVENT_VALIDATION_INPUT_ID,
        ]:
            tag: AdvancedTag | None = parser.getElementById(id_)
            if not tag:
                logger.error(
                    'Content of URL [%s] is not valid (input[id=[%s] not found).',
                    url,
                    id_,
                )
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

    def _ffe_init(self) -> bool:
        """Initializes a session on the FFE admin website (mostly gets state variables).
        Return True on success, False otherwise."""
        url = FFE_URL
        logger.debug('Initializing a session to [%s]...', url)
        html: str | None = self._read_url(url=url, data=None, files=None)
        if not html:
            return False
        parser, error = self._parse_html_content(html)
        if error:
            return False
        if result := self.read_ffe_state(parser, url):
            logger.debug('Session initialized.')
        return result

    def _ffe_auth(self, ffe_id: int, ffe_password: str) -> bool | None:
        """Authenticates on the FFE admin website.
        Returns True on success, False if the credentials are incorrect, or
        None if they couldn't be tested."""

        assert self.ffe_state
        if ffe_id is None or ffe_password is None:
            return False
        logger.debug('Authenticating...')
        url = FFE_URL + '/Default.aspx'
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
            return None
        parser, error = self._parse_html_content(html)
        if error:
            return None
        assert parser is not None
        if not self.read_ffe_state(parser, url):
            return None
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
            self.report_error(_('Authentication failed.'))
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
        if not self._ffe_init():
            return None
        if auth := self._ffe_auth(ffe_id, ffe_password):
            logger.info('FFE authentication succeeded.')
        return auth

    def get_fees(self) -> str | None:
        """Downloads the fees for the tournament."""

        assert self.tournament is not None
        ffe_id, ffe_password = self.get_id_and_password()
        if not ffe_id or not ffe_password:
            return None

        logger.info('Getting fees for tournament [%d]...', ffe_id)

        if not self._ffe_init():
            return None
        if not self._ffe_auth(ffe_id, ffe_password):
            return None
        assert self.auth_state
        logger.debug(
            '> auth_state[%s]=[%s]', FEES_LINK_ID, self.auth_state[FEES_LINK_ID]
        )
        fees_link_id = self.auth_state[FEES_LINK_ID]
        if fees_link_id is None:
            self.report_error(
                _(
                    'Fees link not found, check that a Papi file has already been sent and that the tournament has not been archived on the FFE website.'
                )
            )
            return None
        if fees_link_id.lower() == 'tournoi exempté de droits':
            self.report_info(_('Tournament exempt from registration fees.'))
            return None
        if fees_link_id.lower() != 'afficher la facture':
            self.report_error(
                _('Invalid fees link text [{text}].').format(text=fees_link_id)
            )
            return None
        url = FFE_URL + '/MonTournoi.aspx'
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
            return None
        base: AdvancedTag = AdvancedTag('base')
        base.setAttribute('href', FFE_URL)
        parser, error = self._parse_html_content(html)
        assert parser is not None
        if error:
            logger.error(
                'Could not parse FFE response to [%s] with POST data [%s].',
                url,
                str(post_data),
            )
            logger.debug('Response received:\n%s', html)
            self.report_error(_('Invalid response from the FFE website.'))
            return None
        head: AdvancedTag | None = parser.getElementsByTagName('head')[0]
        if not head:
            logger.error(
                'Could not find tag HEAD in the FFE response to [%s] with POST data [%s].',
                url,
                str(post_data),
            )
            logger.debug('Response received:\n%s', html)
            self.report_error(_('Invalid response from the FFE website.'))
            return None
        head.insertBefore(base, head.getChildren()[0])
        html = parser.getHTML()
        logger.info('Getting fees succeeded.')
        return html

    def get_id_and_password(
        self,
    ) -> tuple[int | None, str | None]:
        """Fetches the certification number and password for the tournament from the plugin data."""

        assert self.tournament is not None
        pd = self.tournament.plugin_data
        ffe_id: int | None = get_data(pd, 'ffe_id')
        ffe_password: str | None = get_data(pd, 'ffe_password')
        if not ffe_id or not ffe_password:
            logger.warning(
                'FFE certification number and password are not correctly set for tournament [%s], data can not be sent to the FFE website.',
                self.tournament.uniq_id,
            )
            return None, None
        else:
            return ffe_id, ffe_password

    def upload(self, set_visible: bool):
        """Upload the tournament to the FFE admin website."""

        assert self.tournament is not None
        ffe_id, ffe_password = self.get_id_and_password()
        if not ffe_id or not ffe_password:
            return

        logger.info(
            'Sending tournament [%d] (%s) to the FFE website...',
            ffe_id,
            self.tournament.file,
        )
        if not self._ffe_init():
            return
        if not self._ffe_auth(ffe_id, ffe_password):
            return
        logger.debug(
            '> auth_state[%s]=[%s]', UPLOAD_LINK_ID, self.auth_state[UPLOAD_LINK_ID]
        )
        if self.auth_state[UPLOAD_LINK_ID] is None:
            self.report_error(
                _(
                    'Upload link not found, check that the tournament is not marked as finished on the FFE website.'
                )
            )
            return
        url = FFE_URL + '/MonTournoi.aspx'
        post: dict[str, str] = {
            '__EVENTTARGET': UPLOAD_EVENT,
            '__EVENTARGUMENT': '',
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        date: str = datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
        tmp_file: Path = (
            ffe.TMP_DIR
            / f'{self.tournament.file.stem}-{date}{self.tournament.file.suffix}'
        )
        tmp_file.parents[0].mkdir(parents=True, exist_ok=True)
        logger.debug('Copying [%s] to [%s]...', self.tournament.file, tmp_file)
        tmp_file.write_bytes(self.tournament.file.read_bytes())
        with PapiDatabase(tmp_file, write=True) as tmp_database:
            logger.debug("Deleting personal players' data...")
            tmp_database.delete_players_personal_data()
            logger.debug('Deleting ZPBs if no pairings...')
            tmp_database.remove_zpbs_if_no_pairings()
            tmp_database.commit()
        html: str | None = self._read_url(
            url=url,
            data=post,
            files={
                UPLOAD_FILE_ID: tmp_file,
            },
        )
        tmp_file.unlink()
        if not html:
            return
        __, error = self._parse_html_content(html)
        if error:
            self.report_error(_('Upload failed'))
            return
        with EventDatabase(self.tournament.event.uniq_id, write=True) as event_database:
            now = time.time()
            event_database.execute(
                'UPDATE `tournament` SET `ffe_last_upload` = ?, '
                '`last_update` = ? WHERE `id` = ?',
                (
                    now,
                    now,
                    self.tournament.id,
                ),
            )
            event_database.commit()
        self.report_success(_('Results upload OK'))
        if not set_visible:
            return
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
            return
        set_visible_link_id = self.auth_state[SET_VISIBLE_LINK_ID]
        if set_visible_link_id is None:
            return
        if set_visible_link_id.lower().startswith('désactiver'):
            logger.info('Data is already displayed on the FFE website.')
            self.report_info(_('Data is already displayed on the FFE website.'))
            return
        if not set_visible_link_id.lower().startswith('activer'):
            self.report_error(
                _('Invalid display link text [{text}]').format(
                    text=self.auth_state[SET_VISIBLE_LINK_ID]
                )
            )
            return
        url = FFE_URL + '/MonTournoi.aspx'
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
            return
        logger.info('Tournament visibility successfully set')
        self.report_success(_('Tournament visibility successfully set'))

    def upload_rules(self) -> None:
        """Upload the rules of the tournament to the FFE admin website."""

        assert self.tournament is not None
        assert self.tournament.rules is not None
        ffe_id, ffe_password = self.get_id_and_password()
        if not ffe_id or not ffe_password:
            return

        logger.info(
            'Sending the rules of tournament [{ffe_id}] ({file}) to the FFE website...',
            ffe_id,
            self.tournament.rules,
        )
        if not self._ffe_init():
            return
        if not self._ffe_auth(ffe_id, ffe_password):
            return
        logger.debug(
            '> auth_state[%s]=[%s]',
            UPLOAD_RULES_LINK_ID,
            self.auth_state[UPLOAD_RULES_LINK_ID],
        )
        if self.auth_state[UPLOAD_RULES_LINK_ID] is None:
            self.report_error(
                _(
                    'Rules upload link not found, check that the tournament is not marked as finished on the FFE website.'
                )
            )
            return
        url = FFE_URL + '/MonTournoi.aspx'
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
                UPLOAD_RULES_FILE_ID: Path(self.tournament.rules),
            },
        )
        if not html:
            logger.error('html')
            return
        __, error = self._parse_html_content(html)
        if error:
            logger.error(error)
            return
        with EventDatabase(self.tournament.event.uniq_id, write=True) as event_database:
            now = time.time()
            event_database.execute(
                'UPDATE `tournament` SET `ffe_last_rules_upload` = ?, '
                '`last_update` = ? WHERE `id` = ?',
                (
                    now,
                    now,
                    self.tournament.id,
                ),
            )
            event_database.commit()
        logger.info('Rules uploaded')
        self.report_success(_('Rules uploaded'))
