import hashlib
import json
import time
from collections.abc import Iterator
from datetime import datetime
from json import JSONDecodeError
from logging import Logger
from pathlib import Path
from typing import Any

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
from data.tournament import Tournament
from plugins.ffe.utils import PapiPairingSystem, PapiPairingVariation
from utils.enum import Result
from database.access.papi.papi_database import (
    PapiDatabase,
    PapiVariable,
    UNPLAYED_COLOR,
    BYE_COLOR,
)
from database.access.papi.papi_template import create_empty_papi_database
from database.sqlite.event.event_database import EventDatabase
from plugins.chessevent import PLUGIN_NAME, TMP_DIR
from plugins.chessevent.data.chessevent_player import ChessEventPlayer
from plugins.chessevent.data.chessevent_tournament import ChessEventTournament
from plugins.chessevent.engine.chessevent_session import ChessEventSession
from plugins.chessevent.utils import ChessEventUtils
from plugins.ffe.ffe_session import FFESession
from plugins.utils import PluginUtils

logger: Logger = get_logger()


class ActionSelector(metaclass=Singleton):
    """The CLI interface for ChessEvent."""

    @classmethod
    def add_chessevent_player(
        cls,
        database: PapiDatabase,
        player_papi_id: int,
        player: ChessEventPlayer,
        check_in_started: bool,
    ):
        """Creates a player in the database from the given ChessEvent player.
        If the player is not checked in when `check_in_started` is True,
        removes the player from play for subsequent rounds which are not
        specifically not-played rounds."""
        data: dict[str, str | int | float | None] = {
            'Ref': player_papi_id,
            'RefFFE': player.ffe_id,
            'NrFFE': player.ffe_license_number if player.ffe_license_number else None,
            'Nom': player.last_name,
            'Prenom': player.first_name,
            'Sexe': player.gender.to_papi_value,
            'NeLe': database.timestamp_to_papi_date(player.birth),
            'Cat': player.category.to_papi_value,
            'AffType': player.ffe_license.to_papi_value,
            'Elo': player.standard_rating,
            'Rapide': player.rapid_rating,
            'Blitz': player.blitz_rating,
            'Federation': player.federation,
            'ClubRef': player.ffe_club_id,
            'Club': player.ffe_club,
            'Ligue': player.ffe_league,
            'Fide': player.standard_rating_type.to_papi_value,
            'RapideFide': player.rapide_rating_type.to_papi_value,
            'BlitzFide': player.blitz_rating_type.to_papi_value,
            'FideCode': player.fide_id if player.fide_id else None,
            'FideTitre': player.title.to_papi_value,
            'Pointe': check_in_started and player.check_in,
            'InscriptionRegle': player.paid,
            'InscriptionDu': player.fee,
            'Tel': player.phone,
            'EMail': player.email,
            'Fixe': player.board,
            'Flotteur': 'X' * 24,
            'Pts': 0,
            'PtA': 0,
        }
        for round_ in range(1, 25):
            data[f'Rd{round_:0>2}Adv'] = None
            if round_ not in player.skipped_rounds:
                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                if player.check_in or not check_in_started:
                    data[f'Rd{round_:0>2}Cl'] = UNPLAYED_COLOR
                else:
                    data[f'Rd{round_:0>2}Cl'] = BYE_COLOR
            else:
                data[f'Rd{round_:0>2}Cl'] = BYE_COLOR
                match player.skipped_rounds[round_]:
                    case 0.0:
                        data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                    case 0.5:
                        data[f'Rd{round_:0>2}Res'] = Result.HALF_POINT_BYE.to_papi_value
                    case _:
                        raise ValueError
        database.write_player_dict(data)

    @classmethod
    def write_chessevent_info(
        cls, database: PapiDatabase, chessevent_tournament: ChessEventTournament
    ):
        """Creates the tournament data from the ChessEvent Tournament data."""
        default_rounds: int = 7
        if not chessevent_tournament.rounds:
            logger.warning(
                'Number of rounds not set in ChessEvent, %d set by default.',
                default_rounds,
            )
            chessevent_tournament.rounds = default_rounds
        database.write_info(
            {
                PapiVariable.NAME: chessevent_tournament.name,
                PapiVariable.TYPE: PapiPairingSystem.get_plugin_value(
                    chessevent_tournament.type
                )
                or '',
                PapiVariable.ROUNDS: chessevent_tournament.rounds,
                PapiVariable.PAIRING_VARIATION: PapiPairingVariation.get_plugin_value(
                    chessevent_tournament.pairing
                )
                or '',
                PapiVariable.TIME_CONTROL: chessevent_tournament.time_control,
                PapiVariable.LOCATION: chessevent_tournament.location,
                PapiVariable.ARBITER: chessevent_tournament.arbiter,
                PapiVariable.START_DATE: database.timestamp_to_papi_date(
                    chessevent_tournament.start
                ),
                PapiVariable.END_DATE: database.timestamp_to_papi_date(
                    chessevent_tournament.end
                ),
                PapiVariable.RATING: chessevent_tournament.rating.to_papi_value,
                PapiVariable.FFE_ID: str(chessevent_tournament.ffe_id),
            }
        )
        database.update_tie_breaks(chessevent_tournament.tie_breaks)

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
        # write data to a temporary file to limit the time no tournament file is available
        date: str = datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
        tmp_file: Path = (
            TMP_DIR / f'{tournament.file.stem}-{date}{tournament.file.suffix}'
        )
        logger.debug('Writing ChessEvent data to temporary Papi file [%s]...', tmp_file)
        tmp_file.parents[0].mkdir(parents=True, exist_ok=True)
        tournament.file.unlink(missing_ok=True)
        create_empty_papi_database(tmp_file)
        with PapiDatabase(file=tmp_file, write=True) as papi_database:
            with EventDatabase(tournament.event.uniq_id, write=True) as event_database:
                cls.write_chessevent_info(papi_database, chessevent_tournament)
                for player_papi_id, chessevent_player in enumerate(
                    chessevent_tournament.players, start=2
                ):
                    cls.add_chessevent_player(
                        papi_database,
                        player_papi_id,
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
                papi_database.commit()
        logger.debug('Copying [%s] to [%s]...', tmp_file, tournament.file)
        tournament.file.write_bytes(tmp_file.read_bytes())
        logger.debug('Removing temporary Papi file [%s]...', tmp_file)
        tmp_file.unlink(missing_ok=True)
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
            print_interactive_error(_('Unable to create Papi files.'))
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
                            chessevent_tournament_info: dict[str, Any]
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
                                data_md5
                                == PluginUtils.get_plugin_data(
                                    PLUGIN_NAME,
                                    tournament.plugin_data,
                                    'chessevent_last_download_md5',
                                )
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
                            player_count: int = self.write_chessevent_info_to_database(
                                tournament, chessevent_tournament, data_md5
                            )
                            print_interactive_success(
                                _(
                                    'Papi file [{file}] has been created (players: {num}).'
                                ).format(file=tournament.file, num=player_count)
                            )
                            if action_choice == upload_answer:
                                FFESession(tournament).upload(set_visible=True)
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
