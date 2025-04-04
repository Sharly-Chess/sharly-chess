from logging import Logger
from typing import Any

from common.logger import get_logger
from data import tie_break
from data.tie_break import TieBreak
from utils.enum import (
    TournamentType,
    TournamentPairing,
    TournamentRating,
)
from plugins.chessevent.data.chessevent_field_reader import ChessEventFieldReader
from plugins.chessevent.data.chessevent_player import ChessEventPlayer
from plugins.ffe import ffe_tie_break

logger: Logger = get_logger()


class ChessEventTournament:
    """A class representing all the data of a ChessEvent tournament."""

    def __init__(
        self,
        chessevent_tournament_info: dict[str, Any],
    ):
        self.players: list[ChessEventPlayer] = []
        self.check_in_started = False
        self.error = True

        reader = ChessEventFieldReader(chessevent_tournament_info)

        try:
            self.name = reader.get('name', str)
            self.type = reader.get_enum('type', TournamentType, TournamentType.UNKNOWN)
            self.rounds = reader.get('rounds', int)
            if self.rounds not in range(25):  # the 0-value is set by default later
                raise ValueError
            self.pairing = reader.get_enum(
                'pairing', TournamentPairing, TournamentPairing.UNKNOWN
            )
            self.time_control = reader.get('time_control', str)
            self.location = reader.get('location', str)
            self.arbiter = reader.get('arbiter', str)
            self.start = float(reader.get('start', int))
            self.end = float(reader.get('end', int))
            self.rating = reader.get_enum(
                'rating', TournamentRating, TournamentRating.STANDARD
            )
            self.ffe_id = reader.get('ffe_id', int, '')
            self.tie_breaks = self._load_tie_breaks(chessevent_tournament_info)
            for chessevent_player_info in chessevent_tournament_info['players']:
                chessevent_player: ChessEventPlayer = ChessEventPlayer(
                    chessevent_player_info
                )
                self.check_in_started = True
                if chessevent_player.error:
                    return
                self.players.append(chessevent_player)

        except KeyError:
            logger.error(
                'Field [%s] missing in the ChessEvent response', reader.last_key
            )
            return
        except (TypeError, ValueError):
            logger.error(
                'Invalid value [%s] for field [%s] in the ChessEvent response',
                chessevent_tournament_info[reader.last_key or ''],
                reader.last_key,
            )
            return
        self.error = False

    @staticmethod
    def _load_tie_breaks(tournament_info: dict) -> list[TieBreak]:
        tie_break_by_chessevent_id = {
            1: ffe_tie_break.PapiBuchholzTieBreak(),
            2: ffe_tie_break.PapiBuchholzCutBottomTieBreak(),
            3: ffe_tie_break.PapiMedianBuchholzTieBreak(),
            4: tie_break.ProgressiveScoresTieBreak(),
            5: ffe_tie_break.PapiPerformanceTieBreak(),
            6: ffe_tie_break.PapiSumOfBuchholzTieBreak(),
            7: tie_break.WinsTieBreak(),
            8: ffe_tie_break.PapiKashdanTieBreak(),
            9: tie_break.KoyaTieBreak(),
            10: tie_break.SonnebornBergerTieBreak(),
        }
        return [
            tie_break_
            for tie_break_ in [
                tie_break_by_chessevent_id.get(
                    tournament_info[f'tie_break_{index}'], None
                )
                for index in range(1, 4)
            ]
            if tie_break_ is not None
        ]

    def __str__(self) -> str:
        return '\n'.join(
            [
                f'  - Name: {self.name}',
                f'  - Type: {self.type}',
                f'  - Number of rounds: {self.rounds}',
                f'  - Paring: {self.pairing}',
                f'  - Time control: {self.time_control}',
                f'  - Location: {self.location}',
                f'  - Arbiter: {self.arbiter}',
                f'  - Dates: {self.start} - {self.end}',
            ]
            + [
                f'  - Tie-break #{index + 1} : {tie_break_.name}'
                for index, tie_break_ in enumerate(self.tie_breaks)
            ]
            + [
                f'  - Rating: {self.rating}',
                f'  - FFE qualification: {self.ffe_id}',
            ]
        )
