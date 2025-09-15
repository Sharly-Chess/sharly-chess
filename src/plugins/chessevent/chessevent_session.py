from logging import Logger

from requests import Session, Response
from requests.exceptions import RequestException

from common import SharlyChessException
from common.exception import ImporterError
from common.i18n import _
from common.logger import get_logger

logger: Logger = get_logger()


class ChessEventSession(Session):
    """A Requests session specialised for communication with
    the ChessEvent platform."""

    DOWNLOAD_URL: str = 'https://chessevent.echecs-bretagne.fr/download'

    def __init__(
        self, user_id: str, password: str, event_id: str, tournament_name: str
    ):
        super().__init__()
        self.user_id = user_id
        self.password = password
        self.event_id = event_id
        self.tournament_name = tournament_name

    def read_data(self) -> str:
        """Reads the data of a ChessEvent tournament."""
        post: dict[str, str] = {
            'user_id': self.user_id,
            'password': self.password,
            'event_id': self.event_id,
            'tournament_name': self.tournament_name,
        }
        logger.debug(
            'Reading data from the ChessEvent platform (%s)...',
            f'{self.user_id}:{"*" * 8}@{self.event_id}/[{self.tournament_name}]',
        )
        try:
            # Redirections are handled manually to pass the data at each redirection
            response: Response = self.post(
                self.DOWNLOAD_URL, data=post, allow_redirects=False
            )
            while response.status_code in [301, 302]:
                redirect_url = response.headers['location']
                logger.debug('Redirection to  %s...', redirect_url)
                response = self.post(redirect_url, data=post, allow_redirects=False)
        except RequestException as ex:
            logger.error('Failed to read [%s]: %s.', self.DOWNLOAD_URL, ex)
            raise ImporterError(_('Connection to the ChessEvent server failed.'))
        data: str = response.content.decode()
        if response.status_code == 200:
            return data
        logger.error(
            'ChessEvent request failed with status %d.',
            response.status_code,
        )
        match response.status_code:
            case 401 | 403 | 497:
                raise ImporterError(
                    _(
                        'Authentication failed. '
                        'Please check your credentials and try again.'
                    )
                )
            case 496:
                raise SharlyChessException('Missing parameter.')
            case 498:
                raise ImporterError(
                    _(
                        'Tournament [{tournament_name}] does not'
                        ' exist in event [{event_id}].'
                    ).format(
                        tournament_name=self.tournament_name,
                        event_id=self.event_id,
                    )
                )
            case 499:
                raise ImporterError(
                    _('Event [{event_id}] does not exist.').format(
                        event_id=self.event_id
                    )
                )
            case _:
                raise SharlyChessException(
                    f'Unknown response code: [{response.status_code}].'
                )
