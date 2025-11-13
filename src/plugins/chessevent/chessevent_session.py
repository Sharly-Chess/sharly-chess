from dataclasses import dataclass, asdict
from logging import Logger

from requests import Session, Response
from requests.exceptions import RequestException

from common import SharlyChessException
from common.logger import get_logger
from plugins.chessevent import _
from plugins.chessevent.chessevent_status import (
    AuthErrorChessEventStatus,
    UnauthorizedErrorChessEventStatus,
    TournamentNotFoundChessEventStatus,
    EventNotFoundChessEventStatus,
    ConnectionErrorChessEventStatus,
)
from plugins.chessevent.exceptions import ChessEventStatusError

logger: Logger = get_logger()


@dataclass
class ChessEventTournamentRequestData:
    event_id: str
    user_id: str
    password: str
    tournament_name: str


class ChessEventSession(Session):
    """A Requests session specialised for communication with
    the ChessEvent platform."""

    DOWNLOAD_URL: str = 'https://chessevent.echecs-bretagne.fr/download'

    def read_tournament_data(
        self, request_data: ChessEventTournamentRequestData
    ) -> str:
        """Reads the data of a ChessEvent tournament."""
        event_id = request_data.event_id
        user_id = request_data.user_id
        tournament_name = request_data.tournament_name
        post = asdict(request_data)
        logger.debug(
            'Reading data from the ChessEvent platform (%s)...',
            f'{user_id}:{"*" * 8}@{event_id}/[{tournament_name}]',
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
            raise ChessEventStatusError(
                _('Connection to the ChessEvent server failed.'),
                ConnectionErrorChessEventStatus(),
            )
        data: str = response.content.decode()
        if response.status_code == 200:
            return data
        logger.error(
            'ChessEvent request failed with status %d.',
            response.status_code,
        )
        match response.status_code:
            case 401 | 497:
                raise ChessEventStatusError(
                    _(
                        'Authentication failed. '
                        'Please check your credentials and try again.'
                    ),
                    AuthErrorChessEventStatus(),
                )
            case 403:
                raise ChessEventStatusError(
                    _(
                        'The event [{event_id}] is not accessible to the user [{user_id}].'
                    ).format(
                        event_id=event_id,
                        user_id=user_id,
                    ),
                    UnauthorizedErrorChessEventStatus(),
                )
            case 496:
                raise SharlyChessException('Missing parameter.')
            case 498:
                raise ChessEventStatusError(
                    _(
                        'Tournament [{tournament_name}] does not'
                        ' exist in event [{event_id}].'
                    ).format(
                        tournament_name=tournament_name,
                        event_id=event_id,
                    ),
                    TournamentNotFoundChessEventStatus(),
                )
            case 499:
                raise ChessEventStatusError(
                    _('Event [{event_id}] does not exist.').format(event_id=event_id),
                    EventNotFoundChessEventStatus(),
                )
            case _:
                raise SharlyChessException(
                    f'Unknown response code: [{response.status_code}].'
                )
