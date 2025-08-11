import hashlib
import json
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from json import JSONDecodeError
from logging import Logger
from pathlib import Path
from typing import Any
import zoneinfo

import chardet

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
from data.event import Event
from data.loader import EventLoader
from data.player import PlayerRating
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from utils.enum import Result, TournamentRating
from database.sqlite.event.event_database import EventDatabase
from plugins import chessevent
from plugins.chessevent import PLUGIN_NAME
from plugins.chessevent.data.chessevent_player import ChessEventPlayer
from plugins.chessevent.data.chessevent_tournament import ChessEventTournament
from plugins.chessevent.engine.chessevent_session import ChessEventSession
from plugins.chessevent.utils import ChessEventUtils
from plugins.ffe import PLUGIN_NAME as FFE_PLUGIN_NAME
from plugins.ffe.utils import FfePlayerPluginData
from plugins.utils import PluginUtils

logger: Logger = get_logger()

paris_tz = zoneinfo.ZoneInfo('Europe/Paris')
epoch = datetime(1970, 1, 1, tzinfo=zoneinfo.ZoneInfo('UTC'))


class ActionSelector(metaclass=Singleton):
    """The CLI interface for ChessEvent."""

    @classmethod
    def add_chessevent_player(
        cls,
        event_database: EventDatabase,
        tournament: Tournament,
        player: ChessEventPlayer,
        check_in_started: bool,
    ):
        """Creates a player in the database from the given ChessEvent player.
        If the player is not checked in when `check_in_started` is True,
        removes the player from play for subsequent rounds which are not
        specifically not-played rounds."""

        ffe_plugin_data = FfePlayerPluginData(
            player.ffe_id,
            player.ffe_licence,
            player.ffe_licence_number if player.ffe_licence_number else None,
            player.ffe_league,
        )

        stored_player = StoredPlayer(
            id=None,
            last_name=player.last_name,
            first_name=player.first_name,
            date_of_birth=(epoch + timedelta(seconds=player.birth)).astimezone(
                paris_tz
            ),
            gender=player.gender.value,
            mail=player.email,
            phone=player.phone,
            comment=None,
            owed=player.fee,
            paid=player.paid,
            title=player.title.value,
            ratings={
                TournamentRating.STANDARD: PlayerRating(
                    value=player.standard_rating,
                    type=player.standard_rating_type,
                ).stored_value,
                TournamentRating.RAPID: PlayerRating(
                    value=player.rapid_rating,
                    type=player.rapide_rating_type,
                ).stored_value,
                TournamentRating.BLITZ: PlayerRating(
                    value=player.blitz_rating,
                    type=player.blitz_rating_type,
                ).stored_value,
            },
            fide_id=player.fide_id if player.fide_id else None,
            federation=player.federation,
            club=player.ffe_club,
            fixed=player.board,
            check_in=check_in_started and player.check_in,
            plugin_data={FFE_PLUGIN_NAME: ffe_plugin_data.to_stored_value()},
        )

        stored_player.id = event_database.add_stored_player(stored_player)
        tournament.add_player_to_tournament(stored_player, event_database)
        tournament_player = tournament.players_by_id[stored_player.id]

        for round_ in range(
            1,
            tournament.rounds + 1,
        ):
            if round_ not in player.skipped_rounds:
                if not player.check_in and check_in_started:
                    tournament_player.pairings_by_round[round_].update_result(
                        event_database, Result.ZERO_POINT_BYE
                    )
            else:
                match player.skipped_rounds[round_]:
                    case 0.0:
                        tournament_player.pairings_by_round[round_].update_result(
                            event_database, Result.ZERO_POINT_BYE
                        )
                    case 0.5:
                        tournament_player.pairings_by_round[round_].update_result(
                            event_database, Result.HALF_POINT_BYE
                        )
                    case _:
                        raise ValueError

    @classmethod
    def write_chessevent_info_to_database(
        cls,
        tournament: Tournament,
        chessevent_tournament: ChessEventTournament,
        chessevent_download_md5: str,
    ) -> int:
        """Stores the information from the given `chessevent_tournament` in the event database.
        For comparison, also stores `chessevent_download_md5`, so that the tournament is not downloaded unnecessarily.
        Returns the number of players added."""
        players_added: int = 0

        with EventDatabase(tournament.event.uniq_id, write=True) as event_database:
            # Delete all existing players from this tournament
            for existing_player in tournament.players:
                event_database.delete_stored_tournament_player(
                    tournament.id, existing_player.id
                )

            # Add all players from the chessevent tournament
            for chessevent_player in chessevent_tournament.players:
                cls.add_chessevent_player(
                    event_database,
                    tournament,
                    chessevent_player,
                    chessevent_tournament.check_in_started,
                )
                players_added += 1
            event_database.execute(
                'UPDATE `tournament` SET `chessevent_last_download_md5` = ?, '
                '`last_update` = ? WHERE `id` = ?',
                (
                    chessevent_download_md5,
                    time.time(),
                    tournament.id,
                ),
            )

            event_database.commit()
        return players_added

    @classmethod
    def __get_chessevent_tournaments(cls, event: Event) -> Iterator[Tournament]:
        """Retrieves all the tournaments of given *event* and returns an
        iterator of all the ones with a valid setup for ChessEvent.
        Namely: a tournament that has a chessevent tournament name, a defined
        file and is not started is valid."""
        if not event.tournaments_by_id:
            yield from ()
        for tournament in event.tournaments_by_id.values():
            if not ChessEventUtils.resolve_tournament_name(tournament):
                print_interactive_warning(
                    _(
                        'The ChessEvent connection is not defined for tournament [{tournament_uniq_id}].'
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
                _('No tournaments configured with ChessEvent connections found.')
            )
            return False
        print_interactive_info(
            _('Tournaments: {tournament_names}').format(
                tournament_names=', '.join(
                    (tournament.name for tournament in tournaments)
                )
            )
        )
        create_answer: str = _('R *** THE LETTER TO ANSWER REPLACE')
        quit_answer: str = _('Q *** THE LETTER TO ANSWER QUIT')
        default_answer: str = create_answer
        actions1: dict[str, str] = {
            create_answer: _(
                'Replace all the players in your tournaments with those from ChessEvent'
            ),
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
                                    'No tournaments configured with ChessEvent connections found.'
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
                            chessevent_tournament_info: dict[str, Any]
                            # NOTE(Amaras) what does this accomplish?
                            data = '\n'.join([line for line in data.split('\n')])
                            try:
                                chessevent_tournament_info = json.loads(data)
                            except JSONDecodeError as ex:
                                error_output: Path = (
                                    chessevent.TMP_DIR
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
                            if data_md5 == PluginUtils.get_plugin_data(
                                PLUGIN_NAME,
                                tournament.plugin_data,
                                'chessevent_last_download_md5',
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
                            player_count: int = self.write_chessevent_info_to_database(
                                tournament, chessevent_tournament, data_md5
                            )
                            print_interactive_success(
                                _(
                                    'Tournament [{name}] has been updated, {num} players added.'
                                ).format(name=tournament.name, num=player_count)
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
