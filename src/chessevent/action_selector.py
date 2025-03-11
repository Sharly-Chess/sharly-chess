import hashlib
import json
import time
from collections.abc import Iterator
from json import JSONDecodeError
from logging import Logger
from pathlib import Path

import chardet

from chessevent.chessevent_session import ChessEventSession
from common import TMP_DIR
from common.i18n import _
from common.logger import (
    get_logger,
    print_interactive_input,
    input_interactive,
    print_interactive_warning,
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
)
from common.singleton import Singleton
from data.chessevent_tournament import ChessEventTournament
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.access.papi.papi_template import create_empty_papi_database, PAPI_VERSIONS
from ffe.ffe_session import FFESession

logger: Logger = get_logger()


class ActionSelector(metaclass=Singleton):
    """The CLI interface for ChessEvent."""

    @classmethod
    def __get_chessevent_tournaments(cls, event: Event) -> Iterator[Tournament]:
        """Retrieves all the tournaments of given *event* and returns an
        iterator of all the ones with a valid setup for ChessEvent.
        Namely: a tournament that has a chessevent tournament name, a defined
        file and is not started is valid."""
        if not event.tournaments_by_id:
            yield from ()
        for tournament in event.tournaments_by_id.values():
            if not tournament.chessevent_tournament_name:
                print_interactive_warning(
                    _(
                        'The ChessEvent connection is not defined for tournament [{tournament_uniq_id}].'
                    ).format(tournament_uniq_id=tournament.uniq_id)
                )
            elif not tournament.file:
                print_interactive_warning(
                    _(
                        'The Papi file is not defined for tournament [{tournament_uniq_id}].'
                    ).format(tournament_uniq_id=tournament.uniq_id)
                )
            elif tournament.current_round:
                print_interactive_warning(
                    _('Tournament [{tournament_uniq_id}] has started.').format(
                        tournament_uniq_id=tournament.uniq_id
                    )
                )
            else:
                yield tournament

    def run(self, event_uniq_id: str) -> bool:
        """The CLI interface function.
        Gets user input to retrieve the tournament data from chess event, and
        possibly upload the tournament to the FFE website, corresponding to the
        event with Unique ID *event_uniq_id*.
        Returns False if an error occurred or if it was interrupted.
        Returns True when the one-shot creation (and possibly upload) was okay"""
        event: Event = EventLoader.get(request=None).reload_event(event_uniq_id)
        print_interactive_info(_('Event: {event_name}').format(event_name=event.name))
        tournaments: list[Tournament] = list(self.__get_chessevent_tournaments(event))
        if not tournaments:
            print_interactive_error(
                _('Unable to create Papi files since no tournaments are defined.')
            )
            return False
        print_interactive_info(
            _('Tournaments: {tournament_names}').format(
                tournament_names=', '.join(
                    (tournament.name for tournament in tournaments)
                )
            )
        )
        create_answer: str = _('C *** THE LETTER TO ANSWER CREATE')
        upload_answer: str = _('U *** THE LETTER TO ANSWER UPLOAD')
        quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
        default_answer: str = create_answer
        actions1: dict[str, str] = {
            create_answer: _('Create the Papi files'),
            upload_answer: _('Create the Papi files and send them to the FFE website'),
            quit_answer: _('Quit'),
        }
        print_interactive_input('Actions :')
        for letter, text in actions1.items():
            print_interactive_input(f'  - [{letter}] {text}')
        action_choice: str | None = None
        while action_choice not in actions1:
            action_choice = (
                input_interactive(
                    _('Your choice (by default {default}): ').format(
                        default=default_answer
                    )
                ).upper()
                or default_answer
            )
        print_interactive_info(
            _('Action: {action}').format(action=actions1[action_choice])
        )
        if action_choice == quit_answer:
            return False
        if action_choice in [
            create_answer,
            upload_answer,
        ]:
            once_answer: str = _('1 *** THE LETTER TO ANSWER ONCE')
            always_answer: str = _('C *** THE LETTER TO ANSWER CONTINUOUSLY')
            quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
            default_answer: str = once_answer
            frequency_actions: dict[str, str] = {
                once_answer: _('Once'),
                always_answer: _('Continuously'),
                quit_answer: _('Quit'),
            }
            print_interactive_input('Frequency :')
            for letter, text in frequency_actions.items():
                print_interactive_input(f'  - [{letter}] {text}')
            frequency_choice: str | None = None
            while frequency_choice not in frequency_actions:
                frequency_choice = (
                    input_interactive(
                        _('Your choice (by default {default}): ').format(
                            default=default_answer
                        )
                    ).upper()
                    or default_answer
                )
            if frequency_choice == quit_answer:
                return False
            print_interactive_info(
                _('Frequency: {frequency}').format(
                    frequency=frequency_actions[frequency_choice]
                )
            )
            if frequency_choice in [
                once_answer,
                always_answer,
            ]:
                if len(PAPI_VERSIONS) > 1:
                    default_papi_version = PAPI_VERSIONS[-1]
                    print_interactive_input(_('Please choose the Papi version:'))
                    quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
                    version_choices = {
                        str(i + 1): PAPI_VERSIONS[i] for i in range(len(PAPI_VERSIONS))
                    } | {
                        quit_answer: _('Quit'),
                    }
                    default_answer: str = str(len(PAPI_VERSIONS))
                    for letter, text in version_choices.items():
                        print_interactive_input(f'  - [{letter}] {text}')
                    version_choice: str | None = None
                    while version_choice not in version_choices:
                        version_choice = (
                            input_interactive(
                                _('Your choice (by default {default}): ').format(
                                    default=default_papi_version
                                )
                            ).upper()
                            or default_answer
                        )
                    if version_choice == quit_answer:
                        return False
                    papi_version = PAPI_VERSIONS[int(version_choice) - 1]
                else:
                    papi_version = PAPI_VERSIONS[-1]
                print_interactive_info(
                    _('Papi version: {version}').format(version=papi_version)
                )
                try:
                    chessevent_timeout_min: int = 10
                    chessevent_timeout_max: int = 180
                    chessevent_timeout: int = chessevent_timeout_min
                    while True:
                        event = EventLoader.get(request=None).reload_event(
                            event_uniq_id
                        )
                        tournaments: list[Tournament] = list(
                            self.__get_chessevent_tournaments(event)
                        )
                        if not tournaments:
                            print_interactive_error(
                                _(
                                    'This action can not be applied to the tournaments of this event.'
                                )
                            )
                            return False
                        for tournament in tournaments:
                            data: str | None = ChessEventSession(tournament).read_data()
                            if data is None:
                                continue
                            encoding = chardet.detect(data.encode())['encoding']
                            if encoding == 'MacRoman':
                                logger.warning(
                                    'MacRoman encoding detected, assuming utf-8.'
                                )
                                encoding = 'utf-8'
                            chessevent_tournament_info: dict[
                                str,
                                str | int | list[dict[bool | str, str | int | None]],
                            ]
                            # NOTE(Amaras) what does this accomplish?
                            data = '\n'.join([line for line in data.split('\n')])
                            try:
                                chessevent_tournament_info = json.loads(data)
                            except JSONDecodeError as ex:
                                error_output: Path = (
                                    TMP_DIR
                                    / event.uniq_id
                                    / f'{tournament.uniq_id}_error_l{ex.lineno}_c{ex.colno}_p{ex.pos}.json'
                                )
                                error_output.parents[0].mkdir(
                                    parents=True, exist_ok=True
                                )
                                with open(error_output, 'w', encoding='utf-8') as f:
                                    f.write(data)
                                print_interactive_error(
                                    _(
                                        'Data for tournament [{tournament_uniq_id}] could not be decoded (encoding: [{encoding}]), saved in file [{file}] (error line [{line}], column [{column}], position [{position}]).'
                                    ).format(
                                        tournament_uniq_id=tournament.uniq_id,
                                        encoding=encoding,
                                        file=error_output,
                                        line=ex.lineno,
                                        column=ex.colno,
                                        position=ex.pos,
                                    )
                                )
                                continue
                            data_md5 = hashlib.md5(data.encode('utf-8')).hexdigest()
                            if (
                                data_md5 == tournament.chessevent_last_download_md5
                                and tournament.file.exists()
                            ):
                                print_interactive_info(
                                    _(
                                        'Data for tournament [{tournament_name}] on ChessEvent are unchanged.'
                                    ).format(tournament_name=tournament.name)
                                )
                                continue
                            chessevent_tournament = ChessEventTournament(
                                chessevent_tournament_info
                            )
                            if chessevent_tournament.error:
                                continue
                            chessevent_timeout = chessevent_timeout_min
                            tournament.file.unlink(missing_ok=True)
                            if create_empty_papi_database(
                                tournament.file, papi_version
                            ):
                                player_count: int = (
                                    tournament.write_chessevent_info_to_database(
                                        chessevent_tournament, data_md5
                                    )
                                )
                                print_interactive_success(
                                    _(
                                        'Papi file [{file}] has been created (players: {num}).'
                                    ).format(file=tournament.file, num=player_count)
                                )
                            if action_choice == upload_answer:
                                if not tournament.ffe_id or not tournament.ffe_password:
                                    logger.warning(
                                        _(
                                            'FFE ID and password are not correctly set for tournament [{tournament_name}], data can not be sent to the FFE website.'
                                        ).format(tournament_name=tournament.name)
                                    )
                                else:
                                    FFESession(tournament, debug=False).upload(
                                        set_visible=True
                                    )
                        if frequency_choice == once_answer:
                            return True
                        time.sleep(chessevent_timeout)
                        chessevent_timeout = min(
                            chessevent_timeout_max, int(chessevent_timeout * 1.2)
                        )
                except KeyboardInterrupt:
                    return False
            raise ValueError(f'frequency_choice={frequency_choice}')
        raise ValueError(f'action_choice={action_choice}')
