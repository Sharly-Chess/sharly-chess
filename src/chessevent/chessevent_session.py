import json

from logging import Logger
from requests import Session, Response
from requests.exceptions import ConnectionError, Timeout, RequestException, \
    HTTPError  # pylint: disable=redefined-builtin

from common.i18n import _
from common.papi_web_config import PapiWebConfig
from data.tournament import Tournament
from common.logger import get_logger, print_interactive_error

logger: Logger = get_logger()


class ChessEventSession(Session):
    """A Requests session specialised for communication with
    the ChessEvent platform."""
    def __init__(self, tournament: Tournament):
        super().__init__()
        self._tournament: Tournament = tournament

    def read_data(self) -> str | None:
        """Reads the data of the tournament from ChessEvent.
        If the data could be successfully retrieved and decode, returns
        it encoded as a JSON string.
        If an error occurred, logs ir and returns None"""
        url: str = PapiWebConfig.chessevent_download_url
        try:
            post: dict[str, str] = {
                'user_id': self._tournament.chessevent_user_id,
                'password': self._tournament.chessevent_password,
                'event_id': self._tournament.chessevent_event_id,
                'tournament_name': self._tournament.chessevent_tournament_name,
            }
            chessevent_string: str = (f'{post["user_id"]}:{"*" * 8}'
                                      f'@{post["event_id"]}/{post["tournament_name"]}')
            logger.debug('Reading data from the ChessEvent platform (%s)...', chessevent_string)
            # Redirections are handled manually to pass the data at each redirection
            response: Response = self.post(url, data=post, allow_redirects=False)
            while response.status_code in [301, 302]:
                redirect_url = response.headers['location']
                logger.debug('Redirection to  %s...', redirect_url)
                response = self.post(redirect_url, data=post, allow_redirects=False)
            logger.debug('Response code: %s', response.status_code)
            logger.debug('Response headers: %s', response.headers)
            data: str = response.content.decode()
            logger.debug('response data (length: %s): %s', len(data), data)
            if response.status_code == 200:
                return data
            match response.status_code:
                case 401:
                    print_interactive_error(
                        _('Authentication error (code: [{code}]) for [{user_id}] ([{chessevent_string}]).').format(
                            code=response.status_code, user_id=post['user_id'], chessevent_string=chessevent_string))
                case 403:
                    print_interactive_error(
                        _('Access denied (code: [{code}]) for [{user_id}] on tournament [{tournament_name}] ([{chessevent_string}]).').format(
                            code=response.status_code, user_id=post['user_id'],
                            tournament_name=post['tournament_name'], chessevent_string=chessevent_string))
                case 496:
                    print_interactive_error(
                        _('Missing parameter (code: [{code}]): [{error}].').format(
                            code=response.status_code, error=json.loads(data)['error']))
                case 497:
                    print_interactive_error(
                        _('ID [{user_id}] not found (code: [{code}]): [{error}].').format(
                            code=response.status_code, user_id=post['user_id'], error=json.loads(data)['error']))
                case 498:
                    print_interactive_error(
                        _('Tournament [{tournament_name}] not found (code: [{code}]): [{error}].').format(
                            code=response.status_code, tournament_name=post['tournament_name'],
                            error=json.loads(data)['error']))
                case 499:
                    print_interactive_error(
                        _('Event [{event_id}] not found (code: [{code}]): [{error}].').format(
                            code=response.status_code, event_id=post['event_id'],
                            error=json.loads(data)['error']))
                case _:
                    print_interactive_error(
                        _('Unknown response code: [{code}] ([{chessevent_string}]).').format(
                            code=response.status_code, chessevent_string=chessevent_string))
        except ConnectionError as ex:
            print_interactive_error(
                _('Failed to read [{url}] (connection error): [{ex}].').format(url=url, ex=ex))
            return None
        except Timeout as ex:
            print_interactive_error(_('Failed to read [{url}] (timeout): [{ex}].').format(url=url, ex=ex))
            return None
        except HTTPError as ex:
            print_interactive_error(_('Failed to read [{url}] (error code [{errno}]): [{strerror}].').format(
                url=url, errno=ex.errno, strerror=ex.strerror))
            return None
        except RequestException as ex:
            print_interactive_error(_('Failed to read [{url}]: [{ex}].').format(url=url, ex=ex))
            return None
        return None
