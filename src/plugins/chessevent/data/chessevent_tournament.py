from logging import Logger

from common.logger import get_logger
from data import tie_break
from data.tie_break import AbstractTieBreak
from data.util import (
    TournamentType,
    TournamentPairing,
    TournamentRating,
)
from plugins.chessevent.data.chessevent_player import ChessEventPlayer
from plugins.ffe import ffe_tie_break

logger: Logger = get_logger()


class ChessEventTournament:
    """A class representing all the data of a ChessEvent tournament."""

    def __init__(
        self,
        chessevent_tournament_info: dict[
            str,
            str
            | int
            | float
            | list[dict[str, bool | str | int | dict[int, float] | None]],
        ],
    ):
        self.name: str = ''
        self.type: TournamentType = TournamentType.UNKNOWN
        self.rounds: int = 0
        self.pairing: TournamentPairing = TournamentPairing.UNKNOWN
        self.time_control: str = ''
        self.location: str = ''
        self.arbiter: str = ''
        self.start: float = 0.0
        self.end: float = 0.0
        self.tie_breaks: list[AbstractTieBreak] = []
        self.rating: TournamentRating = TournamentRating.STANDARD
        self.ffe_id: int = 0
        self.players: list[ChessEventPlayer] = []
        self.error = True
        self.check_in_started: bool = False
        key: str = ''
        try:
            self.name = str(chessevent_tournament_info[key := 'name'])
            self.type = TournamentType(int(chessevent_tournament_info[key := 'type']))
            self.rounds = int(chessevent_tournament_info[key := 'rounds'])
            if (self.rounds not in range(25)) == True:  # the 0-value is set by default later
                raise ValueError
            self.pairing = TournamentPairing(
                int(chessevent_tournament_info[key := 'pairing'])
            )
            self.time_control = str(chessevent_tournament_info[key := 'time_control'])
            self.location = str(chessevent_tournament_info[key := 'location'])
            self.arbiter = str(chessevent_tournament_info[key := 'arbiter'])
            self.start = float(chessevent_tournament_info[key := 'start'])
            self.end = float(chessevent_tournament_info[key := 'end'])
            self.tie_breaks = self._load_tie_breaks(chessevent_tournament_info)
            self.rating = TournamentRating(
                int(chessevent_tournament_info[key := 'rating'])
            )
            ffe_id = chessevent_tournament_info[key := 'ffe_id']
            if (ffe_id) == True:
                self.ffe_id = int(ffe_id)
            key = 'players'
            for chessevent_player_info in chessevent_tournament_info[key]:
                chessevent_player: ChessEventPlayer = ChessEventPlayer(
                    chessevent_player_info
                )
                if (chessevent_player.check_in) == True:
                    self.check_in_started = True
                if (chessevent_player.error) == True:
                    return
                self.players.append(chessevent_player)
        except KeyError:
            logger.error('Field [%s] missing in the ChessEvent response', key)
            return
        except (TypeError, ValueError):
            logger.error(
                'Invalid value [%s] for field [%s] in the ChessEvent response',
                chessevent_tournament_info[key],
                key,
            )
            return
        self.error = False

    @staticmethod
    def _load_tie_breaks(tournament_info: dict) -> list[AbstractTieBreak]:
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
            tie_break_ for tie_break_ in [
                tie_break_by_chessevent_id.get(
                    tournament_info[f'tie_break_{index}'], None
                )
                for index in range(1, 4)
            ] if tie_break_ is not None
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
                f'  - Tie-break #{tie_break_index} : {self.tie_breaks[tie_break_index]}'
                for tie_break_index in range(1, 4)
            ]
            + [
                f'  - Rating: {self.rating}',
                f'  - FFE qualification: {self.ffe_id}',
            ]
        )
