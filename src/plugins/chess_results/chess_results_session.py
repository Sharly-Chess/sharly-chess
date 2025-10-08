from functools import partial
import time
from logging import Logger

from requests import Session

from common.logger import get_logger
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.chess_results import PLUGIN_NAME
from plugins.utils import PluginUtils

logger: Logger = get_logger()

CHESS_RESULTS_URL: str = 'http://admin.echecs.asso.fr'


get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class ChessResultsSession(Session):
    """A requests session specialized for communication with Chess-Results.com."""

    def __init__(
        self,
        tournament: Tournament | None,
        report_info=logger.info,
        report_success=logger.info,
        report_error=logger.error,
    ):
        super().__init__()
        self.tournament: Tournament | None = tournament
        self.report_info = report_info
        self.report_success = report_success
        self.report_error = report_error

    def _chess_results_init(self) -> bool:
        """Initializes a session on Chess-Results.com
        Return True on success, False otherwise."""
        url = CHESS_RESULTS_URL
        logger.debug('Initializing a session to [%s]...', url)
        html: str | None = self._read_url(url=url, data=None, files=None)
        if not html:
            return False
        parser, error = self._parse_html_content(html)
        if error:
            return False
        if result := self.read_chess_results_state(parser, url):
            logger.debug('Session initialized.')
        return result

    def upload(self):
        """Upload the tournament to Chess-Results.com."""

        assert self.tournament is not None
        chess_results_id, chess_results_password = self.get_id_and_password()
        if not chess_results_id or not chess_results_password:
            return

        logger.info(
            'Sending tournament [%d] (%s) to Chess-Results.com...',
            chess_results_id,
            self.tournament.uniq_id,
        )
        if not self._chess_results_init():
            return

        event_uniq_id = self.tournament.event.uniq_id
        # with tempfile.TemporaryDirectory() as tmpdir:
        #     tmp_path: Path = Path(tmpdir)
        #     tmp_xml_file: Path = tmp_path / 'export.xml'

        #     # Upload

        with EventDatabase(event_uniq_id, write=True) as event_database:
            now = time.time()
            event_database.execute(
                'UPDATE `tournament` SET `chess_results_last_upload` = ?, '
                '`last_update` = ? WHERE `id` = ?',
                (
                    now,
                    now,
                    self.tournament.id,
                ),
            )
