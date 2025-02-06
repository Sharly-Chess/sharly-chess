import re
import time
import webbrowser
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Any

from AdvancedHTMLParser import AdvancedHTMLParser, AdvancedTag
from requests import Session, Response
from requests.exceptions import ConnectionError, Timeout, RequestException, HTTPError

from common import TMP_DIR
from common.i18n import _
from common.logger import (
    get_logger,
    print_interactive_error,
    print_interactive_success,
    print_interactive_info,
    print_interactive_warning,
)
from data.tournament import Tournament
from database.access.papi.papi_database import PapiDatabase
from database.sqlite.event_database import EventDatabase

logger: Logger = get_logger()

FFE_URL: str = "http://admin.echecs.asso.fr"

VIEW_STATE_INPUT_ID: str = "__VIEWSTATE"
VIEW_STATE_GENERATOR_INPUT_ID: str = "__VIEWSTATEGENERATOR"
EVENT_VALIDATION_INPUT_ID: str = "__EVENTVALIDATION"

VIEW_LINK_ID: str = "ctl00_ContentPlaceHolderMain_LinkViewTournoi"
SET_VISIBLE_LINK_ID: str = "ctl00_ContentPlaceHolderMain_CmdAfficherTournoi"
SET_VISIBLE_EVENT: str = SET_VISIBLE_LINK_ID.replace("_", "$")
FEES_LINK_ID: str = "ctl00_ContentPlaceHolderMain_CmdFactureHomologation"
FEES_EVENT: str = "ctl00$ContentPlaceHolderMain$CmdFactureHomologation"
UPLOAD_LINK_ID: str = "ctl00_ContentPlaceHolderMain_CmdUploadPapi"
UPLOAD_EVENT: str = UPLOAD_LINK_ID.replace("_", "$")
UPLOAD_FILE_ID: str = "ctl00$ContentPlaceHolderMain$UploadPapi"
UPLOAD_RULES_LINK_ID: str = "ctl00_ContentPlaceHolderMain_CmdUploadRI"
UPLOAD_RULES_EVENT: str = UPLOAD_RULES_LINK_ID.replace("_", "$")
UPLOAD_RULES_FILE_ID: str = "ctl00$ContentPlaceHolderMain$UploadRI"

FEES_DIR: Path = Path("fees")


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
        self, url: str, data: dict[str, str] | None, files: dict[str, Path] | None
    ) -> str | None:
        """Reads any URL and returns the content as a string, or None on error (the error is logged).
        When debug is True, log the request contents received."""
        self.last_url_read = url
        handlers: dict[str, Any] = {}
        try:
            if self.debug:
                logger.info(
                    "read_url(%s), method=%s", url, "POST" if data or files else "GET"
                )
            if not data and not files:
                response: Response = self.get(url)
            else:
                if self.debug:
                    if data:
                        logger.info("- data:")
                        for field_id, field in data.items():
                            if field_id == "ctl00$TextPassword":
                                logger.info("  - %s: [********]", field_id)
                            else:
                                logger.info(
                                    "  - %s: [%s]",
                                    field_id,
                                    field[:64] + ("..." if len(field) > 64 else "")
                                    if field
                                    else "None",
                                )
                    if files:
                        logger.info("- files:")
                        for field_id, file in files.items():
                            logger.info("  - %s: [%s]", field_id, file)
                if not files:
                    response: Response = self.post(url, data=data)
                else:
                    handlers = {
                        file_id: open(file_name, "rb")
                        for file_id, file_name in files.items()
                    }
                    response: Response = self.post(url, data=data, files=handlers)
                    for handler in handlers.values():
                        handler.close()
            content: str = response.content.decode()
            if self.debug:
                date_str = datetime.strftime(
                    datetime.fromtimestamp(time.time()), "%Y-%m-%d-%H-%M-%S"
                )
                debug_file = TMP_DIR / f"{url.replace('/', '_')}-{date_str}-raw.html"
                with open(debug_file, "w") as file:
                    file.write(content)
                logger.info("Raw content stored to %s.", debug_file)
            return content
        except ConnectionError as ex:
            print_interactive_error(
                _("Failed to read [{url}] (connection error): [{ex}].").format(
                    url=url, ex=ex
                )
            )
        except Timeout as ex:
            print_interactive_error(
                _("Failed to read [{url}] (timeout): [{ex}].").format(url=url, ex=ex)
            )
        except HTTPError as ex:
            print_interactive_error(
                _(
                    "Failed to read [{url}] (error code [{errno}]): [{strerror}]."
                ).format(url=url, errno=ex.errno, strerror=ex.strerror)
            )
        except RequestException as ex:
            print_interactive_error(
                _("Failed to read [{url}]: [{ex}].").format(url=url, ex=ex)
            )
        for handler in handlers.values():
            handler.close()
        return None

    def _parse_html_content(
        self, html: str
    ) -> tuple[AdvancedHTMLParser | None, str | None]:
        """Parses any HTML content received and returns the parsed content
        (as an HTML parser) and an error (as a string) if any (or None)"""
        parser: AdvancedHTMLParser = AdvancedHTMLParser()
        error: str | None = None
        parser.parseStr(html)
        if self.debug:
            date_str = datetime.strftime(
                datetime.fromtimestamp(time.time()), "%Y-%m-%d-%H-%M-%S"
            )
            debug_file = (
                TMP_DIR
                / f"{self.last_url_read.replace('/', '_')}-{date_str}-parsed.html"
            )
            with open(debug_file, "w", encoding="utf-8") as file:
                file.write(parser.getHTML())
            logger.info("Parsed content stored to %s", debug_file)
        tag: AdvancedTag = parser.getElementById(
            "ctl00_ContentPlaceHolderMain_LabelError"
        )
        if tag:
            if tag.innerText:
                matches = re.match(
                    r"^Transfert du fichier : .* \(\d+ octets\) achevé$", tag.innerText
                )
                if matches:
                    logger.info(tag.innerText)
                else:
                    error = tag.innerText
                    logger.error(error)
        return parser, error

    def read_ffe_state(self, parser: AdvancedHTMLParser, url: str) -> bool:
        """Reads the main state variables of a request and stores them into self.ffe_state.
        Returns True on success, False otherwise."""
        self.ffe_state: dict[str, str] = {}
        for id in [
            VIEW_STATE_INPUT_ID,
            VIEW_STATE_GENERATOR_INPUT_ID,
            EVENT_VALIDATION_INPUT_ID,
        ]:
            tag: AdvancedTag = parser.getElementById(id)
            if not tag:
                print_interactive_error(
                    _(
                        "Content of URL [{url}] is not valid (input[id=[{id]] not found)."
                    ).format(url=url, id=id)
                )
                return False
            self.ffe_state[id] = tag.attributesDict["value"]
            if self.debug:
                logger.info(
                    "> ffe_state[%s]=[%s]",
                    id,
                    self.ffe_state[id][:64]
                    + ("..." if len(self.ffe_state[id]) > 64 else "")
                    if self.ffe_state[id]
                    else "None",
                )
        return True

    def _ffe_init(self) -> bool:
        """Initializes a session on the FFE admin website (mostly gets state variables).
        Return True on success, False otherwise."""
        url = FFE_URL
        print_interactive_info(
            _("Initializing a session to [{url}]...").format(url=url)
        )
        html: str = self._read_url(url=url, data=None, files=None)
        if not html:
            return False
        parser, error = self._parse_html_content(html)
        if error:
            return False
        if result := self.read_ffe_state(parser, url):
            print_interactive_success(_("OK"))
        return result

    def _ffe_auth(self) -> bool:
        """Authenticates on the FFE admin website."""
        assert self.ffe_state
        print_interactive_info(_("Authenticating..."))
        url = FFE_URL + "/Default.aspx"
        post_data: dict[str, str] = {
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
            "ctl00$TextLogin": str(self.tournament.ffe_id),
            "ctl00$TextPassword": self.tournament.ffe_password,
            "ctl00$CmdLogin.x": "12",
            "ctl00$CmdLogin.y": "6",
        }
        html: str = self._read_url(url=url, data=post_data, files=None)
        if not html:
            return False
        parser, error = self._parse_html_content(html)
        if error:
            return False
        if not self.read_ffe_state(parser, url):
            return False
        self.auth_state = {}
        for id in [
            SET_VISIBLE_LINK_ID,
            FEES_LINK_ID,
            UPLOAD_LINK_ID,
            UPLOAD_RULES_LINK_ID,
        ]:
            tag: AdvancedTag = parser.getElementById(id)
            self.auth_state[id] = tag.innerText if tag else None
            if self.debug:
                logger.info(
                    "> auth_state[%s]=[%s]",
                    id,
                    self.auth_state[id][:64]
                    + ("..." if len(self.auth_state[id]) > 64 else "")
                    if self.auth_state[id]
                    else "None",
                )
        tag: AdvancedTag = parser.getElementById(VIEW_LINK_ID)
        if not tag:
            print_interactive_error(_("Authentication failed."))
            return False
        self.tournament_ffe_url = tag.attributesDict["href"]
        if self.debug:
            logger.info("> tournament_ffe_url=[%s]", self.tournament_ffe_url)
        print_interactive_success(_("OK"))
        return True

    def test_auth(self):
        """Tries to authenticate on the FFE admin website for the tournament."""
        logger.info(_("Tournament [{ffe_id}]:").format(ffe_id=self.tournament.ffe_id))
        if not self._ffe_init():
            return
        if not self._ffe_auth():
            return

    def get_fees(self):
        """Downloads the fees for the tournament."""
        print_interactive_info(
            _("Getting fees for tournament [{ffe_id}]...").format(
                ffe_id=self.tournament.ffe_id
            )
        )
        if not self._ffe_init():
            return
        if not self._ffe_auth():
            return
        assert self.auth_state
        if self.debug:
            logger.info(
                "> auth_state[%s]=[%s]", FEES_LINK_ID, self.auth_state[FEES_LINK_ID]
            )
        if self.auth_state[FEES_LINK_ID] is None:
            print_interactive_warning(
                _(
                    "Fees link not found, check that a Papi file has already been sent and that the tournament has not been archived on the FFE website."
                )
            )
            return
        if self.auth_state[FEES_LINK_ID].lower() == "tournoi exempté de droits":
            print_interactive_info(_("Tournament exempt from registration fees."))
            return
        if self.auth_state[FEES_LINK_ID].lower() != "afficher la facture":
            print_interactive_error(
                _("Invalid fees link text [{text}].").format(
                    text=self.auth_state[FEES_LINK_ID]
                )
            )
            return
        url = FFE_URL + "/MonTournoi.aspx"
        post_data: dict[str, str] = {
            "__EVENTTARGET": FEES_EVENT,
            "__EVENTARGUMENT": "",
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        html: str = self._read_url(url=url, data=post_data, files=None)
        if not html:
            return
        FEES_DIR.mkdir(exist_ok=True, parents=True)
        base: AdvancedTag = AdvancedTag("base")
        base.setAttribute("href", FFE_URL)
        parser, error = self._parse_html_content(html)
        if error:
            return False
        head: AdvancedTag = parser.getElementsByTagName("head")[0]
        head.insertBefore(base, head.getChildren()[0])
        file: Path = Path(FEES_DIR, str(self.tournament.ffe_id) + "-fees.html")
        with open(file, "w", encoding="utf-8") as f:
            f.write(parser.getHTML())
        webbrowser.open(f"file://{file.resolve()}", new=2)
        print_interactive_success(
            _("Invoice saved to [{file}].").format(file=file.resolve())
        )
        return

    def upload(self, set_visible: bool):
        """Upload the tournament to the FFE admin website."""
        print_interactive_info(
            _("Sending tournament [{ffe_id}] ({file}) to the FFE website...").format(
                ffe_id=self.tournament.ffe_id, file=self.tournament.file
            )
        )
        if not self._ffe_init():
            return
        if not self._ffe_auth():
            return
        if self.debug:
            logger.info(
                "> auth_state[%s]=[%s]", UPLOAD_LINK_ID, self.auth_state[UPLOAD_LINK_ID]
            )
        if self.auth_state[UPLOAD_LINK_ID] is None:
            print_interactive_warning(
                _(
                    "Upload link not found, check that the tournament is not marked as finished on the FFE website."
                )
            )
            return
        url = FFE_URL + "/MonTournoi.aspx"
        post: dict[str, str] = {
            "__EVENTTARGET": UPLOAD_EVENT,
            "__EVENTARGUMENT": "",
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        date: str = datetime.fromtimestamp(time.time()).strftime("%Y%m%d%H%M%S")
        tmp_file: Path = (
            TMP_DIR
            / "ffe"
            / f"{self.tournament.file.stem}-{date}{self.tournament.file.suffix}"
        )
        tmp_file.parents[0].mkdir(parents=True, exist_ok=True)
        logger.debug("Copie de %s vers %s...", self.tournament.file, tmp_file)
        tmp_file.write_bytes(self.tournament.file.read_bytes())
        with PapiDatabase(tmp_file, write=True) as tmp_database:
            tmp_database: PapiDatabase
            logger.debug("Deleting personal players' data...")
            tmp_database.delete_players_personal_data()
            logger.debug("Deleting forfeits if no pairings...")
            tmp_database.remove_forfeits_if_no_pairings()
            tmp_database.commit()
        html: str = self._read_url(
            url=url,
            data=post,
            files={
                UPLOAD_FILE_ID: tmp_file,
            },
        )
        tmp_file.unlink()
        if not html:
            return
        dummy, error = self._parse_html_content(html)
        if error:
            return
        with EventDatabase(self.tournament.event.uniq_id, write=True) as event_database:
            event_database.set_tournament_last_ffe_upload(self.tournament.id)
            event_database.commit()
        print_interactive_success(_("Results upload OK"))
        if not set_visible:
            return
        print_interactive_info(_("Making the tournament visible on the FFE website..."))
        if self.debug:
            logger.info(
                "> auth_state[%s]=[%s]",
                SET_VISIBLE_LINK_ID,
                self.auth_state[SET_VISIBLE_LINK_ID],
            )
        if self.auth_state[SET_VISIBLE_LINK_ID] is None:
            print_interactive_warning(
                _(
                    "Display link not found, check that a Papi file has already been sent."
                )
            )
            return
        if self.auth_state[SET_VISIBLE_LINK_ID].lower().startswith("désactiver"):
            print_interactive_info(_("Data is already displayed on the FFE website."))
            return
        if not self.auth_state[SET_VISIBLE_LINK_ID].lower().startswith("activer"):
            print_interactive_error(
                _("Invalid display link text [{text}]").format(
                    text=self.auth_state[SET_VISIBLE_LINK_ID]
                )
            )
            return
        url = FFE_URL + "/MonTournoi.aspx"
        post_data: dict[str, str] = {
            "__EVENTTARGET": SET_VISIBLE_EVENT,
            "__EVENTARGUMENT": "",
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        html: str = self._read_url(url=url, data=post_data, files=None)
        if not html:
            return
        print_interactive_success(_("Results upload OK"))

    def upload_rules(self):
        """Upload the rules of the tournament to the FFE admin website."""
        print_interactive_info(
            _(
                "Sending the rules of tournament [{ffe_id}] ({file}) to the FFE website..."
            ).format(ffe_id=self.tournament.ffe_id, file=self.tournament.rules)
        )
        if not self._ffe_init():
            return
        if not self._ffe_auth():
            return
        if self.debug:
            logger.info(
                "> auth_state[%s]=[%s]",
                UPLOAD_RULES_LINK_ID,
                self.auth_state[UPLOAD_RULES_LINK_ID],
            )
        if self.auth_state[UPLOAD_RULES_LINK_ID] is None:
            logger.warning(
                _(
                    "Rules upload link not found, check that the tournament is not marked as finished on the FFE website."
                )
            )
            return
        url = FFE_URL + "/MonTournoi.aspx"
        post: dict[str, str] = {
            "__EVENTTARGET": UPLOAD_RULES_EVENT,
            "__EVENTARGUMENT": "",
            VIEW_STATE_INPUT_ID: self.ffe_state[VIEW_STATE_INPUT_ID],
            VIEW_STATE_GENERATOR_INPUT_ID: self.ffe_state[
                VIEW_STATE_GENERATOR_INPUT_ID
            ],
            EVENT_VALIDATION_INPUT_ID: self.ffe_state[EVENT_VALIDATION_INPUT_ID],
        }
        html: str = self._read_url(
            url=url,
            data=post,
            files={
                UPLOAD_RULES_FILE_ID: Path(self.tournament.rules),
            },
        )
        if not html:
            logger.error("html")
            return
        dummy, error = self._parse_html_content(html)
        if error:
            logger.error(error)
            return
        with EventDatabase(self.tournament.event.uniq_id, write=True) as event_database:
            event_database.set_tournament_last_ffe_rules_upload(self.tournament.id)
            event_database.commit()
        logger.info("Rules upload OK")
